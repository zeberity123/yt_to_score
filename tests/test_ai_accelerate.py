import copy
import json
import threading
import time

import cv2
import numpy as np
import pytest

from ai_score.accelerate import compact_schema, expand_result, windows, prepare_frames, review_windows, score_band, parallel_batches
from ai_score.contracts import validate_schema
from ai_score.providers import check_cancel
from drumscore.server import Workspace


@pytest.mark.parametrize('instrument', ['bass', 'guitar', 'piano', 'drums'])
def test_compact_schema_keeps_every_musical_field(instrument):
    note = {'string': 2, 'fret': '8', 'marks': 'slide-in'} if instrument in ('bass', 'guitar') else (
        {'step': 'F', 'alter': 1, 'octave': 4, 'marks': 'tie-stop'} if instrument == 'piano' else
        {'step': 'G', 'octave': 5, 'drum': 'closed hi-hat', 'marks': 'ghost'})
    result = {'bars': [dict(number=1, meter=[4, 4], pickup=False, confidence=1., timestamp=0,
                           issues=[], system_end=True, tempo_bpm=0, rehearsal='', multirest=0,
                           events=[dict(onset=0, duration=4, staff=1, voice=1, marks='', notes=[note])])],
              'observations': []}
    validate_schema(result, compact_schema(instrument))
    expanded = expand_result(result)
    full_note = expanded['bars'][0]['events'][0]['notes'][0]
    assert all(full_note[k] == value for k, value in note.items())
    assert len(json.dumps(result)) < len(json.dumps(expanded))


def test_windows_cover_timeline_without_overlap_only_tail():
    frames = list(range(121))
    batches = list(windows(frames))
    assert len(batches) == 18
    assert set(n for window in batches for n in window) == set(frames)
    assert len(list(windows(list(range(8))))) == 1
    assert all(a[-1] == b[0] for a, b in zip(batches, batches[1:]))


def panel():
    frame = np.full((500, 960, 3), 255, np.uint8)
    for y in (220, 230, 240, 250):
        cv2.line(frame, (20, y), (940, y), (0, 0, 0), 1)
    cv2.putText(frame, '12', (60, 214), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 0), 1)
    return frame


class Capture:
    def __init__(self, frames): self.frames, self.index = frames, 0
    def set(self, key, value): self.index = round(value/2000)
    def read(self): return True, self.frames[self.index].copy()


def test_local_planner_never_globally_deduplicates_or_drops_unnumbered_repeats(tmp_path):
    same = panel()
    frames = [same]*12
    times = list(range(0, 24, 2))
    selected, stats = prepare_frames(Capture(frames), times, tmp_path/'unnumbered', 'bass', False,
                                    threading.Event(), lambda _: None)
    assert [r['time'] for r in selected] == times
    assert stats['prepared_pixels'] < stats['source_pixels']
    selected, _ = prepare_frames(Capture(frames), times, tmp_path/'numbered', 'bass', True,
                                 threading.Event(), lambda _: None)
    assert len(selected) < len(times)
    assert selected[0]['time'] == 0 and selected[-1]['time'] == 22
    changed = same.copy()
    cv2.putText(changed, '8', (300, 243), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 0), 2)
    selected, _ = prepare_frames(Capture([same, changed, same]), [0, 2, 4], tmp_path/'returns', 'bass', True,
                                 threading.Event(), lambda _: None)
    assert [r['time'] for r in selected] == [0, 2, 4]


def test_crop_keeps_paired_staffs_and_uncertain_frames():
    frame = np.full((600, 960, 3), 255, np.uint8)
    for base in (170, 300):
        for y in range(base, base+41, 10):
            cv2.line(frame, (10, y), (950, y), (0, 0, 0), 1)
    top, bottom, _ = score_band(frame, 'piano')
    assert top < 170 and bottom > 340
    blank = np.full_like(frame, 255)
    assert score_band(blank, 'piano') == (0, 600, None)
    assert score_band(frame, 'chord') == (0, 600, None)


def test_review_groups_share_nearby_evidence_but_keep_all_targets():
    bars = {n: {'timestamp': t} for n, t in [(1, 2), (2, 3), (3, 4), (4, 20)]}
    groups = list(review_windows([1, 2, 3, 4, 5], bars, 25))
    assert groups[0][0] == [1, 2, 3]
    assert sorted(n for numbers, _ in groups for n in numbers) == [1, 2, 3, 4, 5]
    assert all(0 <= t < 25 for _, times in groups for t in times)


def test_user_crop_preserves_exact_area_and_annotations(tmp_path):
    frame = panel()
    area = [.1, .3, .9, .8]
    records, stats = prepare_frames(Capture([frame]), [0], tmp_path, 'piano', True,
                                    threading.Event(), lambda _: None, selected_crop=area)
    image = cv2.imread(str(records[0]['path']))
    assert image.shape[:2] == (250, 768)
    assert records[0]['crop'] == area
    assert stats['cropped_frames'] == 1
    assert stats['prepared_pixels'] == 250*768


@pytest.mark.parametrize('crop', [[0, 0, 1], [0, .8, 1, .2], [0, 0, 2, 1], [0, 0, 1, float('nan')]])
def test_invalid_user_crop_rejected_before_provider(crop):
    from ai_score.pipeline import validate_crop
    with pytest.raises(ValueError, match='score area'):
        validate_crop(crop)


def test_elapsed_timer_freezes_on_cancel_and_survives_preview_jobs(tmp_path):
    workspace = Workspace(tmp_path)
    assert workspace.state()['elapsedSeconds'] is None
    def task():
        workspace.cancel.wait(3)
        check_cancel(workspace.cancel)
    workspace.start(task, timed=True)
    first = workspace.state()['elapsedSeconds']
    time.sleep(.03)
    assert workspace.state()['elapsedSeconds'] > first
    workspace.command('cancel', {})
    deadline = time.monotonic()+3
    while workspace.busy and time.monotonic() < deadline: time.sleep(.01)
    assert not workspace.busy and not workspace.error
    elapsed = workspace.state()['elapsedSeconds']
    workspace.start(lambda: None)
    time.sleep(.02)
    assert workspace.state()['elapsedSeconds'] == elapsed


def test_parallel_numbered_batches_bound_concurrency_and_account_cached_usage(tmp_path):
    from unittest.mock import patch
    from ai_score.providers import Client
    from ai_score.contracts import FORMAT, default_format
    client = Client('Codex', 'gpt-6-astra', '', tmp_path, max_requests=None, budget=None)
    client.auth_checked = True
    mutex = threading.Lock()
    active, maximum = 0, 0
    def transport(self, prompt, schema, images, identity):
        nonlocal active, maximum
        with mutex:
            active += 1
            maximum = max(maximum, active)
        time.sleep(.04)
        with mutex: active -= 1
        return default_format(prompt), {'input_tokens': 10, 'output_tokens': 5}
    def read(number, batch, worker):
        return worker.request(str(number), FORMAT)
    with patch.object(Client, '_codex', transport):
        results = dict(parallel_batches(client, [1, 2, 3], read))
        assert sorted(results) == [1, 2, 3] and maximum == 2 and active == 0
        assert client.usage['requests'] == 3 and client.usage['input_tokens'] == 30
        assert client.usage['output_tokens'] == 15
        list(parallel_batches(client, [1, 2, 3], read))
        assert client.usage['requests'] == 3 and client.usage['cache_hits'] == 3


def test_cancel_drains_successful_inflight_batch(tmp_path):
    from ai_score.providers import Client, Cancelled
    client = Client('Codex', 'gpt-6-astra', '', tmp_path, max_requests=None, budget=None)
    both_started = threading.Barrier(2)
    def read(number, batch, worker):
        both_started.wait(timeout=3)
        if number == 1:
            raise Cancelled('test cancellation')
        time.sleep(.03)
        return {'saved': True}
    results = []
    with pytest.raises(Cancelled):
        for number, result in parallel_batches(client, [1, 2], read):
            results.append((number, result))
    assert results == [(2, {'saved': True})]
