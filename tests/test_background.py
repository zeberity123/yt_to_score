from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from drumscore.background import render_background
from drumscore.editing import archive_project, open_project
from drumscore.extract import Extraction, ScoreLine
from drumscore.print_layout import print_rows, tab_measures
from drumscore.server import Workspace
from drumscore.vision import Region
from test_free import overlay
from test_print_layout import tab


def test_chord_cleanup_preserves_blue_and_lyrics_with_reversible_background():
    source = Image.fromarray(overlay(['Am7 G /', 'First lyric'])[:,:,::-1])
    white = np.array(render_background(source, 'free', 'white'))
    black = np.array(render_background(source, 'free', 'black'))
    assert np.all(white[300:] == 255) and np.all(black[300:] == 0)
    assert np.count_nonzero(np.all(white[90:155] == 0, axis=2)) > 100
    assert np.count_nonzero(np.all(black[90:155] == 255, axis=2)) > 100
    assert np.count_nonzero(white[:,:,2].astype(int)-white[:,:,0] > 100) > 100
    np.testing.assert_array_equal(render_background(source, 'free', 'original'), source)


@pytest.mark.parametrize('notation', ['staff','guitar','bass','piano'])
def test_background_modes_keep_clean_notation_and_faint_rules(notation):
    image = tab(rules=4 if notation == 'bass' else 6)
    original = np.array(image)
    np.testing.assert_array_equal(render_background(image, notation, 'white'), original)
    np.testing.assert_array_equal(render_background(image, notation, 'black'), 255-original)


def test_background_setting_roundtrip_default_and_rendering(tmp_path):
    source = Image.fromarray(overlay(['Am7'])[:,:,::-1])
    source.save(tmp_path/'line.png')
    project = Extraction(tmp_path, 'Chord', '', Region(), [ScoreLine('line.png',0,1)], [], 'free')
    assert project.background == 'white'
    before = (tmp_path/'line.png').read_bytes()
    workspace = Workspace(tmp_path/'workspace')
    workspace.projects['free'] = project
    workspace.mode = 'free'
    workspace.command('background', {'background':'black'})
    assert workspace.state()['background'] == 'black'
    rows, _ = print_rows(project)
    assert np.all(np.array(rows[0].image)[300:] == 0)
    bundle = archive_project(project, tmp_path/'chord.drumscore')
    restored = open_project(bundle, tmp_path/'opened')
    assert restored.background == 'black'
    workspace.command('background', {'background':'original'})
    np.testing.assert_array_equal(print_rows(project)[0][0].image, source)
    assert (tmp_path/'line.png').read_bytes() == before
    with pytest.raises(ValueError):
        workspace.command('background', {'background':'unknown'})
    assert project.background == 'original'


def test_manual_margin_after_final_bar_is_not_an_extra_measure():
    original = tab(bars=2)
    padded = Image.new('RGB', (original.width+20, original.height), 'white')
    padded.paste(original, (10,0))
    cuts, _, _ = tab_measures(padded,6)
    assert len(cuts) == 2
    np.testing.assert_array_equal(np.concatenate([np.array(padded)[:,a:b] for a,b in cuts],axis=1), padded)


def test_user_tuki_archive_reflows_all_29_captures(tmp_path):
    archive = Path(__file__).resolve().parents[1]/'screen_sample/tuki_test1.drumscore'
    if not archive.exists():
        pytest.skip('Local user reference archive is not bundled.')
    project = open_project(archive,tmp_path)
    before = [(project.directory/line.path).read_bytes() for line in project.lines]
    rows, notes = print_rows(project,4)
    assert not notes
    assert [row.bars for row in rows] == [4]*14+[2]
    project.background = 'black'
    black, notes = print_rows(project,4)
    assert not notes and [row.bars for row in black] == [4]*14+[2]
    assert [(project.directory/line.path).read_bytes() for line in project.lines] == before
