import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pymupdf
import pytest

from drumscore.editing import edit_line, archive_project, open_project
from drumscore.extract import Extraction, ScoreLine
from drumscore.pdf import export_pdf
from drumscore.print_layout import print_rows, tab_measures, validate_bars
from drumscore.vision import Region
from test_instruments import music


def tab(bars=3,rules=6,offset=0):
    width=bars*160+1
    image=np.full((220,width,3),255,np.uint8)
    for y in range(55,55+rules*20,20):cv2.line(image,(0,y),(width-1,y),(150,150,150),1)
    for x in range(0,width,160):cv2.line(image,(x,55),(x,55+(rules-1)*20),(20,20,20),2)
    for n in range(bars):
        cv2.rectangle(image,(n*160+64,83),(n*160+94,102),(255,255,255),-1)
        cv2.putText(image,str(n+offset),(n*160+65,99),cv2.FONT_HERSHEY_SIMPLEX,.6,(10,10,10),2)
    return Image.fromarray(image)


def project_at(folder,count=5,notation='guitar'):
    folder.mkdir(exist_ok=True)
    lines=[]
    for index in range(count):
        name=f'line_{index}.png'
        tab(offset=index*3,rules=4 if notation=='bass' else 6).save(folder/name)
        lines.append(ScoreLine(name,index,1,source_path=name,crop=[0,0,1,1],original_path=name,original_crop=[0,0,1,1]))
    return Extraction(folder,'Layout test','',Region(),lines,[],notation)


@pytest.mark.parametrize('rules',[4,6])
def test_measure_partition_preserves_every_pixel_including_double_barlines(rules):
    image=tab(rules=rules)
    gray=np.array(image)
    cv2.line(gray,(165,55),(165,55+(rules-1)*20),(20,20,20),1)
    image=Image.fromarray(gray)
    cuts,first,spacing=tab_measures(image,rules)
    assert len(cuts)==3
    rebuilt=np.concatenate([np.array(image)[:,a:b] for a,b in cuts],axis=1)
    np.testing.assert_array_equal(rebuilt,np.array(image))


@pytest.mark.parametrize('notation',['guitar','bass'])
def test_reflow_joins_measures_and_does_not_enlarge_last_short_line(tmp_path,notation):
    project=project_at(tmp_path,notation=notation)
    before=[(tmp_path/line.path).read_bytes() for line in project.lines]
    rows,notes=print_rows(project,6)
    assert not notes
    assert [row.bars for row in rows]==[6,6,3]
    assert rows[0].width_fraction==rows[1].width_fraction==1
    assert .45 < rows[-1].width_fraction < .55
    assert [(tmp_path/line.path).read_bytes() for line in project.lines]==before
    assert len(print_rows(project,4)[0])==4


def test_unknown_and_combined_panels_are_kept_intact(tmp_path):
    project=project_at(tmp_path,count=1,notation='bass')
    Image.fromarray(music('bass')).save(tmp_path/project.lines[0].path)
    rows,notes=print_rows(project,6)
    assert len(rows)==len(notes)==1 and rows[0].bars is None
    np.testing.assert_array_equal(np.array(rows[0].image),music('bass'))


def test_single_measure_capture_can_join_when_both_boundaries_are_known(tmp_path):
    project=project_at(tmp_path,count=6)
    for line in project.lines:tab(bars=1).save(tmp_path/line.path)
    rows,notes=print_rows(project,6)
    assert not notes
    assert len(rows)==1 and rows[0].bars==6


def test_gray_playback_border_is_not_an_extra_barline():
    image=np.array(tab())
    cv2.line(image,(450,30),(450,195),(170,170,170),1)
    result=tab_measures(Image.fromarray(image),6)
    assert result is not None and len(result[0])==3


def test_reflow_uses_included_lines_in_current_order(tmp_path):
    project=project_at(tmp_path,count=3)
    project.lines.reverse()
    project.lines[1].included=False
    rows,_=print_rows(project,6)
    assert len(rows)==1 and rows[0].bars==6
    # Order is pixel-verifiable without reading fret digits.
    first=Image.open(tmp_path/project.lines[0].path).convert('RGB')
    cuts,_,spacing=tab_measures(first,6)
    part=first.crop((cuts[0][0],0,cuts[0][1],first.height))
    part=part.resize((round(part.width*24/spacing),round(part.height*24/spacing)),Image.Resampling.LANCZOS)
    np.testing.assert_array_equal(np.array(rows[0].image)[:,:part.width],np.array(part))


def test_ratio_edits_do_not_resample_sources_and_round_trip_with_layout(tmp_path):
    project=project_at(tmp_path/'working',count=2)
    project.bars_per_line=8
    original=[(project.directory/line.path).read_bytes() for line in project.lines]
    edit_line(project,0,crop=[0,0,1,1],height_scale=.75,all_heights=True)
    assert [line.height_scale for line in project.lines]==[.75,.75]
    assert [(project.directory/line.path).read_bytes() for line in project.lines]==original
    edit_line(project,0,height_scale=.5)
    edit_line(project,0,height_scale=.75)
    assert not list(project.directory.glob('edit_*.png'))
    bundle=archive_project(project,tmp_path/'score.drumscore')
    reopened=open_project(bundle,tmp_path/'opened')
    assert reopened.bars_per_line==8
    assert [line.height_scale for line in reopened.lines]==[.75,.75]
    edit_line(reopened,0,reset=True)
    assert [line.height_scale for line in reopened.lines]==[1,.75]


def test_ratio_edit_rolls_back_all_lines_on_save_failure(tmp_path,monkeypatch):
    project=project_at(tmp_path,count=2)
    def fail():raise OSError('Disk full')
    monkeypatch.setattr(project,'save',fail)
    with pytest.raises(OSError):edit_line(project,0,height_scale=.7,all_heights=True)
    assert [line.height_scale for line in project.lines]==[1,1]


def test_old_project_defaults_to_original_layout_and_height(tmp_path):
    project=project_at(tmp_path,count=1);project.save()
    name=tmp_path/'project.json';data=json.loads(name.read_text())
    data.pop('bars_per_line')
    data['lines'][0].pop('height_scale')
    name.write_text(json.dumps(data))
    old=Extraction.load(name)
    assert old.bars_per_line==0 and old.lines[0].height_scale==1


def test_pdf_layout_reduces_pages_and_height_changes_drawn_ratio(tmp_path):
    project=project_at(tmp_path,count=15)
    original=export_pdf(project,tmp_path/'original.pdf')
    arranged=export_pdf(project,tmp_path/'six.pdf',bars_per_line=6)
    assert arranged<original
    edit_line(project,0,height_scale=.75,all_heights=True)
    export_pdf(project,tmp_path/'flat.pdf',bars_per_line=6)
    with pymupdf.open(tmp_path/'six.pdf') as a,pymupdf.open(tmp_path/'flat.pdf') as b:
        box_a=a[0].get_image_info()[0]['bbox'];box_b=b[0].get_image_info()[0]['bbox']
        assert (box_b[3]-box_b[1])/(box_a[3]-box_a[1])==pytest.approx(.75,abs=.01)


@pytest.mark.parametrize('value',[3,17,6.5,float('nan'),None])
def test_invalid_bar_counts_rejected(value):
    with pytest.raises(ValueError):validate_bars(value)


def test_height_boundaries_and_instrument_restriction(tmp_path):
    project=project_at(tmp_path,count=1)
    for scale in [0,float('nan'),2.1]:
        with pytest.raises(ValueError):edit_line(project,0,height_scale=scale)
    project.notation='piano'
    with pytest.raises(ValueError,match='guitar and bass'):print_rows(project,6)
