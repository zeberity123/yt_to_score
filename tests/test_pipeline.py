from pathlib import Path
import threading

import cv2
import numpy as np
from PIL import Image
import pymupdf
import pytest

from drumscore.extract import Extraction, ScoreLine, extract
from drumscore.pdf import export_pdf
from drumscore.video import Cancelled, frames, youtube_url
from drumscore.vision import Region, auto_region, clean_score, difference, signature, split_systems, staffs


def score(note=150, top=80, height=210, width=800):
    image = np.full((height, width, 3), 255, np.uint8)
    for y in range(top, top+41, 10):
        cv2.line(image, (20, y), (width-20, y), (120, 120, 120), 1)
    for x in range(25, width-10, 190):
        cv2.line(image, (x, top), (x, top+40), (0, 0, 0), 2)
    cv2.ellipse(image, (note, top+30), (7, 5), -20, 0, 360, (0, 0, 0), -1)
    cv2.line(image, (note+6, top+30), (note+6, top-25), (0, 0, 0), 2)
    cv2.putText(image, 'A', (25, top-20), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 0), 2)
    return image


def make_video(path, images, repeats=12):
    h, w = images[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 6, (w, h))
    assert writer.isOpened()
    for image in images:
        for _ in range(repeats):
            writer.write(image)
    writer.release()


def test_temporal_extraction_retains_later_repeated_passages(tmp_path):
    video = tmp_path/'repeat.avi'
    a, b = score(), score(400)
    make_video(video, [a, b, a])
    result = extract(video, tmp_path, region=Region(), interval=.25)
    assert len(result.lines) == 3
    assert [line.time for line in result.lines] == sorted(line.time for line in result.lines)
    assert np.array_equal(np.array(Image.open(result.directory/result.lines[0].path)),
                          np.array(Image.open(result.directory/result.lines[2].path)))
    result.lines[1].included = False
    result.title = 'Drum test'
    result.save()
    reopened = Extraction.load(result.directory/'project.json')
    assert [l.included for l in reopened.lines] == [True, False, True]
    destination = tmp_path/'score.pdf'
    assert export_pdf(reopened, destination) == 1
    with pymupdf.open(destination) as pdf:
        assert len(pdf[0].get_image_info()) == 2
        assert 'Drum test' in pdf[0].get_text()


def test_single_changed_note_on_a_large_page_is_not_merged():
    a = np.concatenate([score() for _ in range(6)], axis=0)
    b = a.copy()
    b[420:630] = score(400)
    assert difference(signature(clean_score(a)), signature(clean_score(b))) > .035


def test_overlapping_pages_keep_each_line_once_and_can_be_disabled(tmp_path):
    a, b, c = score(150), score(400), score(620)
    path = tmp_path/'pages.avi'
    make_video(path, [np.concatenate([a, b]), np.concatenate([b, c])])
    result = extract(path, tmp_path, region=Region(), interval=.25)
    assert len(result.lines) == 3
    kept = extract(path, tmp_path, region=Region(), interval=.25, remove_overlap=False)
    assert len(kept.lines) == 4


def test_split_page_preserves_top_markings_and_reduces_space():
    page = np.concatenate([score(top=110, height=270), score(top=110, height=270)], axis=0)
    lines = split_systems(clean_score(page))
    assert len(lines) == 2
    assert sum(len(line) for line in lines) < len(page)*.65
    # Section letters and note stems above the staff must remain.
    assert np.count_nonzero(lines[0][:30] < 100) > 20


def test_colored_noteheads_survive_light_playback_wash():
    image = score()
    image[110, 150] = (0, 0, 255)
    image[20:40, 300:400] = (190, 215, 255)
    clean = clean_score(image)
    assert clean[110, 150] < 50
    assert clean[30, 350] == 255


def test_faded_view_does_not_duplicate_a_score(tmp_path):
    path = tmp_path/'fade.avi'
    original = score()
    faded = (original.astype(np.float32)*.2+204).astype(np.uint8)
    make_video(path, [original, faded, original])
    result = extract(path, tmp_path, region=Region(), interval=.25)
    assert len(result.lines) == 1


def test_video_border_does_not_expand_score_strip():
    image = score()
    cv2.line(image, (0, 0), (799, 0), (0, 0, 0), 1)
    strip = split_systems(clean_score(image))[0]
    assert len(strip) < 150


def test_translucent_background_cleanup_preserves_faint_staff_rules():
    image = np.full((210, 800, 3), 200, np.uint8)
    for y in range(80, 121, 10):
        cv2.line(image, (20, y), (780, y), (160, 160, 160), 1)
    cv2.ellipse(image, (150, 110), (7, 5), 0, 0, 360, (0, 0, 0), -1)
    cleaned = clean_score(image)
    assert len(staffs(cleaned)) == 1
    assert cleaned[30, 400] == 255


def test_auto_crop_excludes_picture_in_picture():
    frame = np.full((600, 1000, 3), 90, np.uint8)
    frame[390:, 200:] = score()
    region = auto_region(frame)
    assert region.left > .15
    assert .6 < region.top < .85


def test_empty_video_is_a_helpful_error(tmp_path):
    path = tmp_path/'blank.avi'
    make_video(path, [np.full((200, 800, 3), 255, np.uint8)])
    with pytest.raises(ValueError, match='No stable score'):
        extract(path, tmp_path, region=Region())


def test_cancelled_scan_releases_decoder(tmp_path):
    path = tmp_path/'cancel.avi'
    make_video(path, [score()])
    cancel = threading.Event()
    iterator = frames(path, cancel=cancel)
    next(iterator)
    cancel.set()
    with pytest.raises(Cancelled):
        next(iterator)


@pytest.mark.parametrize('url', ['https://example.com/watch?v=kgNjaXTh0rU', 'https://youtube.com/playlist?list=123', 'file:///test'])
def test_reject_non_video_links(url):
    with pytest.raises(ValueError):
        youtube_url(url)


def test_normalize_youtube_link():
    assert youtube_url('https://youtu.be/kgNjaXTh0rU?t=30') == 'https://www.youtube.com/watch?v=kgNjaXTh0rU'


def test_invalid_crop_and_empty_export(tmp_path):
    with pytest.raises(ValueError):
        Region(.8, 0, .2, 1)
    project = Extraction(tmp_path, 'Empty', '', Region(), [], [])
    with pytest.raises(ValueError, match='at least one'):
        export_pdf(project, tmp_path/'empty.pdf')


@pytest.mark.parametrize('paper, dimensions_mm', [
    ('A4', (210, 297)), ('A3', (297, 420)), ('A5', (148, 210)),
    ('B4', (250, 353)), ('B5', (176, 250)), ('Letter', (215.9, 279.4)),
    ('Legal', (215.9, 355.6)), ('Tabloid', (279.4, 431.8)),
])
def test_export_paper_dimensions(tmp_path, paper, dimensions_mm):
    Image.fromarray(score()).save(tmp_path/'line.png')
    project = Extraction(tmp_path, 'Sheet music', '', Region(), [ScoreLine('line.png', 0, 1)], [])
    destination = tmp_path/'score.pdf'
    export_pdf(project, destination, paper=paper)
    with pymupdf.open(destination) as pdf:
        assert (pdf[0].rect.width, pdf[0].rect.height) == pytest.approx(
            tuple(mm*72/25.4 for mm in dimensions_mm), abs=.01)
        assert len(pdf[0].get_image_info()) == 1
        assert pdf.metadata['author'] == 'Video Sheet to PDF'


def test_export_rejects_unknown_paper_size(tmp_path):
    project = Extraction(tmp_path, 'Sheet music', '', Region(), [ScoreLine('line.png', 0, 1)], [])
    with pytest.raises(ValueError, match='Unsupported paper size'):
        export_pdf(project, tmp_path/'score.pdf', paper='Unknown')
    assert not (tmp_path/'score.pdf').exists()


@pytest.mark.skipif(not Path('C:/Windows/Fonts/meiryo.ttc').exists(), reason='Windows CJK font coverage')
def test_pdf_title_preserves_mixed_korean_and_japanese(tmp_path):
    title = '기타 ギター 楽譜'
    Image.fromarray(score()).save(tmp_path/'line.png')
    project = Extraction(tmp_path, title, '', Region(), [ScoreLine('line.png', 0, 1)], [])
    export_pdf(project,tmp_path/'cjk.pdf')
    with pymupdf.open(tmp_path/'cjk.pdf') as pdf:
        assert title in pdf[0].get_text()
        assert pdf.metadata['title'] == title


@pytest.mark.parametrize('paper', ['A4', 'Letter'])
@pytest.mark.parametrize('margins', [{}, {'left_margin_mm': 0, 'right_margin_mm': 0},
                                  {'left_margin_mm': 3, 'right_margin_mm': 18}])
def test_pdf_side_margins_across_pages(tmp_path, paper, margins):
    Image.fromarray(score()).save(tmp_path/'line.png')
    project = Extraction(tmp_path, 'Margin check', '', Region(),
                         [ScoreLine('line.png', i, i) for i in range(12)], [])
    destination = tmp_path/'margins.pdf'
    export_pdf(project, destination, paper=paper, **margins)
    left = margins.get('left_margin_mm', 3)*72/25.4
    right = margins.get('right_margin_mm', 3)*72/25.4
    with pymupdf.open(destination) as pdf:
        assert len(pdf) > 1
        assert sum(len(page.get_image_info()) for page in pdf) == 12
        for page in pdf:
            for info in page.get_image_info():
                x0, y0, x1, y1 = info['bbox']
                assert x0 == pytest.approx(left, abs=.01)
                assert x1 == pytest.approx(page.rect.width-right, abs=.01)
                assert (y1-y0)/(x1-x0) == pytest.approx(210/800, abs=.001)
                assert y0 >= 12*72/25.4-.01
                assert y1 <= page.rect.height-12*72/25.4+.01
        title = next(block for block in pdf[0].get_text('blocks') if 'Margin check' in block[4])
        assert title[0] == pytest.approx(left, abs=.01)
