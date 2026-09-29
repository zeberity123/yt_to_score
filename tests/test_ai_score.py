import copy
import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_score.contracts import (BAR, FORMAT, default_format, printed_slots, bar_issues,
                                 validate_schema, validate_score)
from ai_score.providers import Client
from ai_score.render import render, musicxml


def note(**updates):
    n = dict(string=1, fret='5', step='C', alter=0, octave=5, drum='snare', marks='')
    n.update(updates)
    return n


def event(onset=0, duration=4, staff=1, voice=1, notes=None):
    return dict(onset=onset, duration=duration, voice=voice, staff=staff, notes=notes or [], marks='')


def score(instrument='bass', count=8):
    bars = [dict(number=n, meter=[4, 4], pickup=False,
                 events=[event(notes=[note()])] + ([event(staff=2, notes=[note(step='C', octave=3)])] if instrument == 'piano' else []),
                 confidence=1., timestamp=n*2., issues=[], system_end=n % 4 == 0,
                 tempo_bpm=0, rehearsal='', multirest=0) for n in range(1, count+1)]
    return {'meta': dict(title='Test '+instrument, instrument=instrument, strings=6 if instrument == 'guitar' else 4,
                         meter=[4, 4], bpm=120, key_fifths=0, first_bar=1, last_bar=count), 'bars': bars}


def test_rest_merge_preserves_measure_count_and_following_rows():
    s = score(count=121)
    for n in (116, 117):
        s['bars'][n-1]['events'] = [event()]
    layout = default_format('Ado', 4)
    layout['merge_rests'] = [[116, 117]]
    rows = printed_slots(s, layout)
    assert [b['source_numbers'] for b in rows[28]] == [[113], [114], [115], [116, 117]]
    assert [b['number'] for b in rows[29]] == [118, 119, 120, 121]
    assert sum(len(b['source_numbers']) for row in rows for b in row) == 121
    assert len(s['bars']) == 121
    s['bars'][116]['events'] = [event(notes=[note()])]
    with pytest.raises(ValueError, match='not a verified'):
        printed_slots(s, layout)


def test_normalize_bar_lifts_legacy_tempo_and_section_text():
    from ai_score.contracts import normalize_bar
    legacy = []
    for text in ('A tempo quarter=110', 'C ♩=144', 'B', 'A tempo', 'cresc.'):
        b = score('drums', 1)['bars'][0]
        for key in ('tempo_bpm', 'rehearsal', 'multirest'):
            b.pop(key)
        b['events'][0]['marks'] = text
        legacy.append(normalize_bar(b))
    assert [(b['rehearsal'], b['tempo_bpm'], b['events'][0]['marks']) for b in legacy] == [
        ('A', 110, ''), ('C', 144, ''), ('B', 0, ''), ('', 0, 'A tempo'), ('', 0, 'cresc.')]
    assert all(b['multirest'] == 0 for b in legacy)
    validate_schema(legacy[0], BAR)


def test_multirest_follows_video_and_override_merges_runs():
    s = score('drums', 12)
    for n in (*range(1, 9), 10, 11):
        s['bars'][n-1]['events'] = [event()]
    s['bars'][0]['multirest'] = 8  # printed as one 8-bar block; bars 10-11 are separate rests
    follow = default_format('t', 0)
    slots = [b['source_numbers'] for row in printed_slots(s, follow) for b in row]
    assert slots[0] == list(range(1, 9)) and [10] in slots and [11] in slots
    assert printed_slots(s, follow)[0][0]['system_end']  # bar 8 ended the source row
    override = default_format('t', 4)
    override['merge_rests_auto'] = True
    slots = [b['source_numbers'] for row in printed_slots(s, override) for b in row]
    assert slots[0] == list(range(1, 9)) and [10, 11] in slots
    override['merge_rests_auto'] = False
    slots = [b['source_numbers'] for row in printed_slots(s, override) for b in row]
    assert slots[0] == list(range(1, 9)) and [10] in slots
    s['bars'][3]['events'] = [event(notes=[note()])]  # a claimed block with notes is ignored, not an error
    assert printed_slots(s, follow)[0][0]['source_numbers'] == [1]


def test_staff_marks_print_once_without_part_label():
    import xml.etree.ElementTree as ET
    s = score('drums', 4)
    s['bars'][0].update(rehearsal='A', tempo_bpm=110)
    s['bars'][1].update(tempo_bpm=110)  # unchanged tempo is not printed again
    s['bars'][2].update(rehearsal='B', tempo_bpm=144)
    s['bars'][0]['events'][0]['marks'] = 'cresc.'
    second = event(voice=2, notes=[note(step='F', octave=4, drum='bass drum')])
    second['marks'] = 'cresc.'
    s['bars'][0]['events'].append(second)
    xml = musicxml(s, default_format('t', 4))
    root = ET.fromstring(xml)
    assert [m.text for m in root.findall('.//per-minute')] == ['110', '144']
    assert [r.text for r in root.findall('.//rehearsal')] == ['A', 'B']
    assert len(root.findall('.//words')) == 1
    assert not (root.find('.//part-name').text or '')
    import verovio
    from importlib.resources import files
    verovio.setDefaultResourcePath(str(files('verovio')/'data'))
    toolkit = verovio.toolkit()
    toolkit.setOptions({'inputFrom': 'musicxml', 'breaks': 'encoded', 'mnumInterval': 0})
    assert toolkit.loadData(xml)
    svg = toolkit.renderToSVG(1)
    assert 'Drums' not in svg and 'class="reh"' in svg and 'class="tempo"' in svg


def test_tab_marks_are_drawn(tmp_path):
    import pymupdf
    s = score('bass', 4)
    s['bars'][0].update(rehearsal='A', tempo_bpm=110)
    s['bars'][1].update(tempo_bpm=110)
    path = tmp_path/'tab.pdf'
    render(s, default_format('Marks', 4), path)
    with pymupdf.open(path) as doc:
        text = doc[0].get_text()
    assert text.count('= 110') == 1 and 'A' in text


def test_rhythm_and_piano_staff_checks():
    s = score('piano')
    assert not validate_score(s)
    s['bars'][0]['events'][0]['duration'] = 3
    assert any('Incomplete rhythm' in i for i in validate_score(s))
    s['bars'][1]['events'].pop()
    assert any('both staves' in i for i in validate_score(s))


def test_missing_bars_and_unknown_end():
    s = score(count=4)
    s['bars'].pop(1)
    assert 'Missing bars: 2' in validate_score(s)
    s['meta']['last_bar'] = 0
    assert 'Missing bars: 2' in validate_score(s)


@pytest.mark.parametrize('instrument', ['bass', 'guitar', 'drums', 'piano'])
def test_four_instruments_vector_pdf(tmp_path, instrument):
    import pymupdf
    s = score(instrument, 12)
    if instrument in ('guitar', 'piano'):
        s['bars'][0]['events'][0]['notes'].append(note(string=2, step='E'))
    s['bars'][2]['events'][0] = event()
    layout = default_format('Clean test', 4)
    path = tmp_path/(instrument+'.pdf')
    render(s, layout, path)
    doc = pymupdf.open(path)
    assert doc.page_count >= 1
    assert 'Clean test' in doc[0].get_text()
    assert all(not page.get_images() for page in doc)
    assert path.stat().st_size > 1000
    if instrument in ('piano', 'drums'):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(musicxml(s, layout))
        assert len(root.findall('.//measure')) == 12
        assert len(root.findall('.//print')) == 3
        assert len(root.findall('.//chord')) == (1 if instrument == 'piano' else 0)


def test_cache_and_usage_do_not_charge_twice(tmp_path):
    client = Client('OpenAI', 'gpt-6-luna', 'secret', tmp_path)
    layout = default_format('test')
    with patch.object(client, '_api', return_value=(layout, {'input_tokens': 1000, 'cached_input_tokens': 500, 'output_tokens': 200})) as call:
        assert client.request('test', FORMAT) == layout
        assert client.request('test', FORMAT) == layout
        assert call.call_count == 1
    assert client.usage['cache_hits'] == 1
    assert client.usage['estimated_usd'] == pytest.approx(.000155)
    assert 'secret' not in ''.join(p.read_text() for p in tmp_path.glob('*.json'))


def test_budget_cancellation_and_bad_json(tmp_path):
    client = Client('OpenAI', 'gpt-6-astra', 'secret', tmp_path, budget=.01)
    with patch.object(client, '_api') as call:
        with pytest.raises(RuntimeError, match='spend guard'):
            client.request('test', FORMAT)
        call.assert_not_called()
    client = Client('OpenAI', 'gpt-6-luna', 'secret', tmp_path)
    with patch.object(client, '_api', return_value=({'invalid': 1}, {'input_tokens': 100, 'output_tokens': 10})):
        with pytest.raises(ValueError):
            client.request('test', FORMAT)
    assert client.usage['output_tokens'] == 10
    assert not [p for p in tmp_path.glob('*.json') if p.name != 'usage-latest.json']


@pytest.mark.parametrize('provider', ['OpenAI', 'DeepSeek', 'Anthropic'])
def test_provider_image_transport(tmp_path, provider):
    from ai_score.providers import PROVIDERS
    client = Client(provider, PROVIDERS[provider]['model'], 'not-a-real-key', tmp_path)
    payload = client._payload('Inspect this', FORMAT, [b'image'])
    assert payload['model'] == PROVIDERS[provider]['model']
    assert 'aW1hZ2U=' in json.dumps(payload)
    assert 'not-a-real-key' not in json.dumps(payload)


def test_schema_rejects_non_finite_and_extra_fields():
    b = score()['bars'][0]
    validate_schema(b, BAR)
    b['confidence'] = float('nan')
    with pytest.raises(ValueError, match='non-finite'):
        validate_schema(b, BAR)


@pytest.mark.parametrize('instrument', ['drums', 'piano'])
def test_staff_multirest_does_not_consume_following_notes(instrument):
    import verovio
    import xml.etree.ElementTree as ET
    s = score(instrument, 8)
    for n in (2, 3):
        s['bars'][n-1]['events'] = [event()] + ([event(staff=2)] if instrument == 'piano' else [])
    layout = default_format('Merge', 4)
    layout['merge_rests'] = [[2, 3]]
    xml = musicxml(s, layout)
    toolkit = verovio.toolkit()
    assert toolkit.loadData(xml)
    mei = ET.fromstring(toolkit.getMEI())
    ns = {'m': 'http://www.music-encoding.org/ns/mei'}
    measures = mei.findall('.//m:measure', ns)
    assert len(measures) == 7
    assert any(m.attrib.get('n') == '4' and m.find('.//m:note', ns) is not None for m in measures)
    assert mei.find('.//m:multiRest', ns).attrib['num'] == '2'


@pytest.mark.parametrize('provider', ['OpenAI', 'DeepSeek', 'Anthropic'])
def test_api_response_and_usage_parsing(tmp_path, provider):
    import io
    from ai_score.providers import PROVIDERS
    layout = default_format('Provider test')
    if provider == 'OpenAI':
        body = {'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': json.dumps(layout)}]}],
                'usage': {'input_tokens': 100, 'input_tokens_details': {'cached_tokens': 20}, 'output_tokens': 30}}
    elif provider == 'DeepSeek':
        body = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(layout)}}],
                'usage': {'prompt_tokens': 100, 'prompt_cache_hit_tokens': 20, 'completion_tokens': 30}}
    else:
        body = {'stop_reason': 'tool_use', 'content': [{'type': 'tool_use', 'name': 'score_result', 'input': layout}],
                'usage': {'input_tokens': 80, 'cache_read_input_tokens': 20, 'output_tokens': 30}}
    client = Client(provider, PROVIDERS[provider]['model'], 'secret-test-key', tmp_path)
    def transport(request, timeout):
        assert request.full_url == PROVIDERS[provider]['url']
        assert 'secret-test-key' not in request.data.decode()
        return io.BytesIO(json.dumps(body).encode())
    with patch('urllib.request.urlopen', side_effect=transport):
        assert client.request('test', FORMAT) == layout
    assert client.usage['input_tokens'] == 100
    assert client.usage['cached_input_tokens'] == 20
    assert client.usage['output_tokens'] == 30


def test_frame_cache_changes_with_video_identity_and_end_is_decodable(tmp_path):
    import cv2
    import numpy as np
    from ai_score.pipeline import extract
    from ai_score.providers import Client
    clip = tmp_path/'input.avi'
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 240))
    for _ in range(30):
        writer.write(np.full((240, 320, 3), 255, np.uint8))
    writer.release()
    meta = dict(title='Fixture', instrument='bass', numbered=True, first_bar=1, last_bar=1,
                meter=[4, 4], bpm=120, key_fifths=0, strings=4, crop=[0, 0, 1, 1], observations=[])
    transcription = {'bars': score(count=1)['bars'], 'observations': [], 'repeats': []}
    client = Client('OpenAI', 'gpt-6-luna', 'fake-key', tmp_path/'responses')
    with patch.object(client, 'request', side_effect=[meta, transcription]):
        project, pdf, result = extract(client, str(clip), 'bass', tmp_path/'job')
    assert project.exists() and pdf.exists()
    assert not result['review']
    assert len(list((tmp_path/'job/frames').glob('*/frame*.jpg'))) > 1


def test_dotted_and_triplet_rhythm_flags():
    from ai_score.render import flag_count, rhythm, beam_groups
    assert flag_count(.375) == 2  # Dotted sixteenth, not an eighth.
    assert flag_count(.75) == 1
    assert flag_count(1/3) == 1  # Eighth-note triplet.
    assert rhythm(1/3)[2]
    notes = [event(i/3, 1/3, notes=[note()]) for i in range(3)]
    assert beam_groups(notes, [4, 4]) == {0: [(1, 'begin')], 1: [(1, 'continue')], 2: [(1, 'end')]}
