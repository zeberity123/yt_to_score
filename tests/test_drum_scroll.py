"""Scrolling staff pages should keep complete occurrences, including written repeats."""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pytest

from drumscore.extract import extract
from drumscore.matching import row_number
from drumscore.vision import Region, clean_score, difference, split_systems, system_signature
from test_pipeline import score, make_video


def scrolling_pages():
    rows = []
    for index in range(6):
        row = score(note=180+index*60, height=200, width=1000)
        # A low drum stem extends below a fully visible bottom staff rule.
        cv2.ellipse(row, (460, 115), (7, 5), 0, 0, 360, (0, 0, 0), -1)
        cv2.line(row, (454, 115), (454, 164), (0, 0, 0), 2)
        rows.append(row)
    header = np.full((160, 1000, 3), 255, np.uint8)
    cv2.putText(header, 'Song title and credits', (180, 150), cv2.FONT_HERSHEY_SIMPLEX,
                1.4, (0, 0, 0), 3)
    canvas = np.concatenate([header, *rows, np.full((160, 1000, 3), 255, np.uint8)])
    return [canvas[top:top+800] for top in (0, 111, 160, 230, 360, 510, 560)]


def test_scrolling_page_keeps_each_complete_drum_row_once(tmp_path):
    path = tmp_path/'scroll.avi'
    make_video(path, scrolling_pages())
    project = extract(path, tmp_path, region=Region(), interval=.25)
    assert len(project.lines) == 6
    # The initial title stays in the exported row even though matching ignores it.
    images = [np.array(Image.open(project.directory/line.path)) for line in project.lines]
    assert images[0].shape[0] > images[1].shape[0]+40
    # Every captured bass stem is whole, including the bottom row after scrolling.
    for image in images:
        ys = np.flatnonzero(image[:, 454] < 90)
        assert len(ys) >= 40
    unfiltered = extract(path, tmp_path, region=Region(), interval=.25, remove_overlap=False)
    assert len(unfiltered.lines) > 6


def test_page_heading_does_not_change_row_identity_or_hide_note_changes():
    a = score(top=130, height=250, width=1920)
    b = a.copy()
    cv2.putText(a, 'Title', (450, 35), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
    # Heading is far from the staff; the closer A/section label stays meaningful.
    full = [system_signature(clean_score(im)) for im in (a, b)]
    core = [system_signature(clean_score(im), ignore_page_heading=True) for im in (a, b)]
    assert difference(*full) > .035
    assert difference(*core) < .035
    b = score(note=400, top=130, height=250, width=1920)
    assert difference(core[0], system_signature(clean_score(b), ignore_page_heading=True)) > .035


def test_edge_detection_waits_for_cut_stems_without_removing_complete_rows():
    pages = scrolling_pages()
    clipped = split_systems(clean_score(pages[1]), with_bounds=True)
    complete = split_systems(clean_score(pages[1]), with_bounds=True, skip_clipped=True)
    assert len(clipped) == 4 and len(complete) == 3
    assert len(split_systems(clean_score(pages[2]), skip_clipped=True)) == 4


def test_numbered_identical_rhythms_and_later_page_returns_survive(tmp_path):
    rows = []
    for number in (9, 13, 17, 21):
        row = score(width=1000)
        row[35:65, 10:100] = 255
        cv2.putText(row, str(number), (25, 60), cv2.FONT_HERSHEY_SIMPLEX,
                    .7, (0, 0, 0), 2)
        rows.append(row)
    path = tmp_path/'numbered.avi'
    make_video(path, [np.concatenate(rows[:2]), np.concatenate(rows[2:]), np.concatenate(rows[:2])])
    project = extract(path, tmp_path, region=Region(), interval=.25)
    assert len(project.lines) == 6
    assert [line.time for line in project.lines] == [0, 0, 2, 2, 4, 4]


def test_thin_serif_row_labels_are_not_misread_as_partial_digits():
    try:
        font = ImageFont.truetype('times.ttf', 22)
    except OSError:
        pytest.skip('Windows serif font is unavailable')
    for text, expected in (('13', 13), ('17', 17), ('21', 21), ('Intro', None)):
        image = score(width=1000)
        image[25:75, :120] = 255
        image = Image.fromarray(image)
        ImageDraw.Draw(image).text((15, 42), text, font=font, fill=(160, 160, 160))
        assert row_number(clean_score(np.array(image))) == expected
