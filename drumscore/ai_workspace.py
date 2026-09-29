"""Bridge structured AI scores into the existing line review/project/export workspace."""
import copy
from pathlib import Path
import uuid
from PIL import ImageChops, ImageOps
from ai_score.contracts import default_format, printed_slots, normalize_score
from ai_score.render import render
from .extract import Extraction, ScoreLine
from .vision import Region


def pdf_images(path, scale=1.8):
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(str(path))
    try:
        for index in range(len(document)):
            page = document[index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil().convert('RGB').copy()
            bitmap.close(); page.close()
            yield image
    finally:
        document.close()


def review_score(project):
    score = copy.deepcopy(project.ai_score)
    if score['meta']['instrument'] == 'chord':
        by_id = {line['number']: line for line in score['lead_lines']}
        score['lead_lines'] = [by_id[n] for line in project.lines if line.included for n in line.ai_bar_ids if n in by_id]
    else:
        score['print_rows'] = [line.ai_bar_ids for line in project.lines if line.included]
    score['layout']['title'] = project.title
    return score


def row_layout(score):
    layout = {**default_format(), **score['layout']}
    layout.update(title='', subtitle='', footer='', show_metadata=False, page_numbers=False)
    return layout


def render_row(score, layout, ids, directory):
    """Engrave one print row (bar numbers or lead-line numbers) to a trimmed PNG; returns its name."""
    chord = score['meta']['instrument'] == 'chord'
    by_id = {b['number']: b for b in (score['lead_lines'] if chord else score['bars'])}
    part = copy.deepcopy(score)
    if chord:
        part['lead_lines'] = [by_id[n] for n in ids]
    else:
        part['print_rows'] = [ids]
    temporary = Path(directory)/'ai-row.pdf'
    render(part, layout, temporary)
    image = next(pdf_images(temporary, 2.2))
    bbox = ImageChops.invert(image).getbbox()
    if bbox:
        image = ImageOps.expand(image.crop(bbox), border=18, fill='white')
    name = 'ai-line-'+uuid.uuid4().hex[:12]+'.png'
    image.save(Path(directory)/name)
    image.close()
    temporary.unlink(missing_ok=True)
    temporary.with_suffix('.musicxml').unlink(missing_ok=True)
    return name


def make_lines(project):
    score = project.ai_score
    layout = row_layout(score)
    chord = score['meta']['instrument'] == 'chord'
    # A row keeps every source bar of a merged rest block, so un-merging later restores them.
    rows = [[line['number']] for line in score.get('lead_lines', [])] if chord else [
        [n for b in row for n in b['source_numbers']] for row in printed_slots(score, layout)]
    by_id = {b['number']: b for b in (score['lead_lines'] if chord else score['bars'])}
    project.lines = [ScoreLine(render_row(score, layout, ids, project.directory), by_id[ids[0]]['timestamp'], 1,
                               original_path=None, ai_bar_ids=ids) for ids in rows]
    for line in project.lines:
        line.original_path = line.path
    project.bars_per_line = layout['bars_per_line']
    project.save()


def rerender_rows(project):
    """Regroup the retained bar sequence under the current layout and engrave every row again.

    Exclusions and manual ordering survive; only the grouping of the kept bars changes.
    """
    score = project.ai_score
    layout = {**default_format(), **score['layout']}
    if score['meta']['instrument'] != 'chord':
        slots = {b['number']: b for row in printed_slots(score, layout) for b in row}
        sequence = [n for line in project.lines if line.included for n in line.ai_bar_ids]
        rows, row = [], []
        for n in sequence:
            if n not in slots:
                continue
            row.append(n)
            if (layout['bars_per_line'] and len(row) == layout['bars_per_line']) or (not layout['bars_per_line'] and slots[n].get('system_end')):
                rows.append(row); row = []
        if row:
            rows.append(row)
        if not layout['bars_per_line'] and not any(slots[n].get('system_end') for n in sequence if n in slots):
            count = score['meta'].get('source_bars_per_line') or 4
            kept = [n for n in sequence if n in slots]
            rows = [kept[i:i+count] for i in range(0, len(kept), count)]
        score['print_rows'] = rows
    make_lines(project)
    score.pop('print_rows', None)
    project.save()


def create_project(score, directory, source):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    score = normalize_score(copy.deepcopy(score))
    instrument = score['meta']['instrument']
    project = Extraction(directory, score['layout']['title'], source, Region(), [], score.get('review', []),
                         'staff' if instrument == 'drums' else instrument, ai_score=copy.deepcopy(score))
    make_lines(project)
    return project


def update_layout(project, data, rerender=True):
    """Apply page settings; returns whether the printed rows changed (re-engraved unless rerender=False)."""
    layout = {**default_format(), **project.ai_score['layout']}
    chord = project.ai_score['meta']['instrument'] == 'chord'
    for name in ('title', 'subtitle', 'footer', 'song_info'):
        if name in data:
            value = str(data[name])
            limit = {'title': 1, 'subtitle': 1, 'footer': 4, 'song_info': 3}[name]
            if len(value) > 2000 or len(value.splitlines()) > limit:
                raise ValueError(f'{name.replace("_", " ").title()} supports up to {limit} line(s) and 2000 characters.')
            layout[name] = value
    for name in ('title_first_page_only', 'show_metadata', 'page_numbers', 'merge_rests_auto'):
        if name in data:
            layout[name] = bool(data[name])
    if 'bars_per_line' in data:
        bars = int(data['bars_per_line'])
        if not 0 <= bars <= 16:
            raise ValueError('Choose 1–16 bars per line, or turn the override off to follow the video.')
        if not chord:
            layout['bars_per_line'] = bars
    if 'merge_rests' in data and not chord:
        layout['merge_rests'] = [[int(n) for n in group] for group in data['merge_rests']]
    if 'break_after' in data and not chord:
        layout['break_after'] = [int(n) for n in data['break_after']]
    if not chord:
        printed_slots(project.ai_score, layout)  # Reject invalid rest groups before touching the project.
    previous = {**default_format(), **project.ai_score['layout']}
    changed_rows = any(layout[k] != previous[k] for k in ('bars_per_line', 'merge_rests_auto', 'merge_rests', 'break_after'))
    project.ai_score['layout'] = layout
    project.title = layout['title']
    if changed_rows and rerender:
        rerender_rows(project)
    project.save()
    return changed_rows


def apply_ai_edit(client, project, text):
    """Apply one plain-language edit request to an engraved AI project; returns notes for the review panel."""
    from ai_score.edit import edit_score, apply_marks, reread_bars, FORMAT_FIELDS
    score = project.ai_score
    result = edit_score(client, score, text)
    changed = apply_marks(score, result['set_marks'])
    observations = reread_bars(client, score, result['reread_bars']) if result['reread_bars'] else []
    rows_changed = update_layout(project, {k: result[k] for k in FORMAT_FIELDS if k != 'unsupported_requests'}, rerender=False)
    if rows_changed or changed or result['reread_bars']:
        rerender_rows(project)
    notes = {'request': text, 'marks': changed, 'reread': result['reread_bars'],
             'unsupported': result['unsupported_requests'], 'observations': observations}
    score.setdefault('edits', []).append({k: notes[k] for k in ('request', 'marks', 'reread', 'unsupported')})
    project.warnings = list(dict.fromkeys(project.warnings+observations+[f'Not applied: {item}' for item in notes['unsupported']]))
    project.save()
    return notes


def export_ai(project, destination, **page_settings):
    score = review_score(project)
    page_settings['left'] = page_settings.pop('left_margin_mm', 12)
    page_settings['right'] = page_settings.pop('right_margin_mm', 12)
    score['page_settings'] = page_settings
    render(score, score['layout'], destination)
