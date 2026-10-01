"""Guitar staff + TAB pairs on a white bottom panel whose height changes per line."""
import cv2
import numpy as np
from PIL import Image

from drumscore.extract import extract
from drumscore.notation import clean_notation, detect_region, follow_region, panel_moves, system_groups
from drumscore.vision import clean_tab, cursor_columns, difference, tab_signature, without_cursor

W, H = 1280, 720


def frame(panel_top=420, frets=('8', '7', '5'), cursor=None, system_right=W-20, ledger=False):
    """Footage above, a white score panel below: section box, chords, staff and six-string TAB."""
    image = np.full((H, W, 3), 70, np.uint8)
    image[panel_top-70:panel_top, 300:760] = 242  # bright clothing right above the panel
    for x in range(100, 1100, 9):  # guitar strings/frets in the footage
        cv2.line(image, (x, 200), (x, 260), (150, 150, 150), 1)
    image[panel_top:] = 246
    staff_top, tab_top = panel_top+86, panel_top+176
    staff = [staff_top+i*10 for i in range(5)]
    tab = [tab_top+i*16 for i in range(6)]
    for y in staff+tab:
        cv2.line(image, (20, y), (system_right, y), (60, 60, 60), 1)
    cv2.line(image, (20, staff[0]), (20, tab[-1]), (20, 20, 20), 2)
    bars = np.linspace(20, system_right, 5 if system_right > W//2 else 3).astype(int)
    for x in bars[1:]:
        cv2.line(image, (int(x), staff[0]), (int(x), staff[-1]), (20, 20, 20), 2)
        cv2.line(image, (int(x), tab[0]), (int(x), tab[-1]), (20, 20, 20), 2)
    cv2.rectangle(image, (22, panel_top+8), (62, panel_top+38), (20, 20, 20), 2)
    cv2.putText(image, 'A', (32, panel_top+32), cv2.FONT_HERSHEY_SIMPLEX, .8, (20, 20, 20), 2)
    for x, name in zip(bars[:-1], ('Cmaj7', 'Bm7', 'Am7', 'G')):
        cv2.putText(image, name, (int(x)+40, panel_top+66), cv2.FONT_HERSHEY_SIMPLEX, .8, (20, 20, 20), 2)
    for index, x in enumerate(range(70, system_right-40, 62)):
        cv2.ellipse(image, (x, staff[1]+5), (6, 4), -20, 0, 360, (20, 20, 20), -1)
        cv2.line(image, (x+5, staff[1]+5), (x+5, staff[-1]+22), (20, 20, 20), 2)
        if ledger:  # notes on the first ledger line above the staff
            cv2.line(image, (x-12, staff[0]-10), (x+12, staff[0]-10), (60, 60, 60), 1)
            cv2.ellipse(image, (x, staff[0]-10), (6, 4), -20, 0, 360, (20, 20, 20), -1)
        active = cursor is not None and cursor <= x <= cursor+34
        # Repeated strums are printed grey and turn solid while the cursor is over them.
        color = (20, 20, 20) if index % 3 == 0 else (220, 110, 20) if active else (170, 170, 170)
        for string, fret in zip((1, 2, 5), frets):
            y = tab[string]
            cv2.rectangle(image, (x-7, y-7), (x+9, y+7), (246, 246, 246), -1)
            cv2.putText(image, fret, (x-6, y+6), cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1)
    if cursor is not None:
        band = image[panel_top+60:, cursor:cursor+34].astype(np.float32)
        image[panel_top+60:, cursor:cursor+34] = (band*np.array([.97, .88, .75])).astype(np.uint8)
    return image


def lower(image):
    return clean_notation(image[H//2:], 'guitar')


def test_staff_above_tab_is_one_guitar_system():
    groups = system_groups(lower(frame()), 'guitar')
    assert len(groups) == 1
    first, last, spacing = groups[0]
    assert first+H//2 == 420+86 and last+H//2 == 420+176+80 and spacing == 10
    # A row of ledger notes one space above the staff must not turn the staff into a second TAB.
    assert len(system_groups(lower(frame(ledger=True)), 'guitar')) == 1
    region = detect_region(frame(), 'guitar', 'auto')
    assert abs(region.top*H-420) <= 3  # the panel edge, so the section box and chords are inside


def test_follow_keeps_the_whole_panel_and_the_selected_width():
    region = detect_region(frame(), 'guitar', 'auto')
    taller = follow_region(frame(380), region, 'guitar')
    assert abs(taller.top*H-380) <= 3 and taller.bottom*H >= 380+176+80+40  # room for stems under the TAB
    shorter = follow_region(frame(450), region, 'guitar')
    assert abs(shorter.top*H-450) <= 3  # the bright clothing above the panel is not score
    # A short system keeps the full width so it prints at the same scale as the others.
    short = follow_region(frame(system_right=W//2), region, 'guitar')
    assert short.left < .01 and short.right == 1
    assert panel_moves([frame(420), frame(380), frame(450), frame(420)], region, 'guitar')
    assert not panel_moves([frame(420)]*4, region, 'guitar')


def test_cursor_band_is_left_out_of_the_view_comparison():
    a, b = frame(cursor=128), frame(cursor=700)
    crop = lambda image: image[420:]
    first, second = tab_signature(clean_tab(crop(a))), tab_signature(clean_tab(crop(b)))
    cursors = cursor_columns(crop(a)), cursor_columns(crop(b))
    assert cursors[0] is not None and 20 <= cursors[0].sum() <= 60
    assert difference(first, second, fine=True, stable=False) > .035  # recolored strums under the cursor
    assert difference(*without_cursor(first, second, *cursors), fine=True, stable=False) <= .035
    changed = tab_signature(clean_tab(crop(frame(frets=('12', '10', '14'), cursor=700))))
    assert difference(*without_cursor(first, changed, cursors[0], cursors[1]), fine=True, stable=False) > .035
    assert cursor_columns(np.full((200, 400, 3), (250, 220, 180), np.uint8)) is None  # a tinted page is no cursor


def test_extract_follows_a_resizing_panel_and_keeps_staff_and_chords(tmp_path):
    video = tmp_path/'pair.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 6, (W, H))
    assert writer.isOpened()
    for top, frets in ((420, ('8', '7', '5')), (380, ('3', '2', '0'))):
        for step in range(14):
            writer.write(frame(top, frets, cursor=60+step*80))
    writer.release()
    region = detect_region(frame(), 'guitar', 'auto')
    project = extract(video, tmp_path, region=region, interval=.25, notation='guitar')
    assert len(project.lines) == 2
    assert any('followed automatically' in warning for warning in project.warnings)
    sizes = [Image.open(project.directory/line.path).size for line in project.lines]
    assert {width for width, _ in sizes} == {W}
    # Section box and chords above the staff down to the last string, for both panel heights.
    assert all(height >= 86+90+80-12 for _, height in sizes)
    tops = [line.crop[1]*H for line in project.lines]
    assert abs(tops[0]-420) <= 12 and abs(tops[1]-380) <= 12
    first = np.array(Image.open(project.directory/project.lines[0].path).convert('L'))
    assert np.mean(first < 120) > .01 and first[:, :8].mean() > 200  # notation, no footage at the edge
