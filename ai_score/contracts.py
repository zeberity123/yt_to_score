"""Small, provider-neutral contracts. AI output is data, never executable code."""
import copy
import math
import re


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def arr(items):
    return {'type': 'array', 'items': items}


S = {'type': 'string'}
N = {'type': 'number'}
I = {'type': 'integer'}
B = {'type': 'boolean'}
NOTE = obj({'string': I, 'fret': S, 'step': S, 'alter': I, 'octave': I,
            'drum': S, 'marks': S})
EVENT = obj({'onset': N, 'duration': N, 'voice': I, 'staff': I, 'notes': arr(NOTE), 'marks': S})
BAR = obj({'number': I, 'meter': arr(I), 'pickup': B, 'events': arr(EVENT),
           'confidence': N, 'timestamp': N, 'issues': arr(S), 'system_end': B,
           'tempo_bpm': N, 'rehearsal': S, 'multirest': I})
# Fields added after the first schema; older projects and journals omit them.
BAR_DEFAULTS = {'tempo_bpm': 0, 'rehearsal': '', 'multirest': 0}
RECON = obj({'title': S, 'instrument': {'type': 'string', 'enum': ['bass', 'guitar', 'drums', 'piano']},
             'numbered': B, 'first_bar': I, 'last_bar': I, 'meter': arr(I), 'bpm': N,
             'key_fifths': I, 'strings': I, 'crop': arr(N), 'observations': arr(S), 'source_bars_per_line': I})
TRANSCRIPTION = obj({'bars': arr(BAR), 'observations': arr(S)})
FORMAT = obj({'title': S, 'title_first_page_only': B, 'subtitle': S, 'footer': S,
              'show_metadata': B, 'page_numbers': B, 'bars_per_line': I,
              'merge_rests': arr(arr(I)), 'break_after': arr(I), 'unsupported_requests': arr(S), 'song_info': S,
              'merge_rests_auto': B})
LEAD_LINE = obj({'number': I, 'section': S, 'timestamp': N, 'confidence': N, 'issues': arr(S),
                 'segments': arr(obj({'chord': S, 'lyric': S}))})
LEAD_TRANSCRIPTION = obj({'lines': arr(LEAD_LINE), 'observations': arr(S)})
# A plain-language edit of a finished score: layout fields, per-bar printed marks, bars to re-read.
EDIT = obj({**FORMAT['properties'],
            'set_marks': arr(obj({'bar': I, 'tempo_bpm': N, 'rehearsal': S, 'remove_words': arr(S)})),
            'reread_bars': arr(I)})
# The same for a project made of captured line images.
LINE_EDIT = obj({'exclude_lines': arr(I), 'move_line': arr(obj({'line': I, 'before': I})),
                 'retranscribe_lines': arr(I), 'notes': arr(S), 'unsupported_requests': arr(S)})
# What the AI reports about each captured row image: printed range, completeness, duplicates.
LINE_CHECK = obj({'lines': arr(obj({'index': I, 'first_bar': I, 'last_bar': I, 'complete': B, 'duplicate_of': I,
                                    'problems': arr(S), 'order_confidence': N})), 'observations': arr(S)})


def default_format(title='', bars_per_line=4):
    return dict(title=title, title_first_page_only=True, subtitle='', footer='',
                show_metadata=False, page_numbers=True, bars_per_line=bars_per_line,
                merge_rests=[], break_after=[], unsupported_requests=[], song_info='',
                merge_rests_auto=False)


TEMPO_MARK = re.compile(r'(?:[♩\U0001D15F]|\bquarter(?:[ -]note)?|\bq)\s*=\s*(\d{2,3})\b', re.I)
LABEL_MARK = re.compile(r'^[A-Z]\d?$')


def normalize_bar(bar):
    """Fill fields added after the first schema and lift legacy tempo/section text out of marks.

    Early transcriptions wrote "A tempo quarter=110" or "C ♩=144" as event words; the renderer
    now prints those from tempo_bpm/rehearsal so they get a real metronome glyph and never repeat.
    """
    for key, value in BAR_DEFAULTS.items():
        bar.setdefault(key, value)
    for event in bar['events']:
        text = event.get('marks', '')
        if not text:
            continue
        found = TEMPO_MARK.search(text)
        if found:
            if not bar['tempo_bpm']:
                bar['tempo_bpm'] = int(found.group(1))
            text = (text[:found.start()]+text[found.end():]).strip()
            text = re.sub(r'\s*\btempo\b\s*$', '', text, flags=re.I).strip()
        if event['onset'] == 0 and LABEL_MARK.match(text):
            if not bar['rehearsal']:
                bar['rehearsal'] = text
            text = ''
        event['marks'] = text
    return bar


def normalize_score(score):
    for bar in score.get('bars', []):
        normalize_bar(bar)
    return score


def validate_schema(value, schema, path='response'):
    """Validate the subset used by all providers, including finite numbers."""
    kind = schema['type']
    types = {'object': dict, 'array': list, 'string': str, 'number': (int, float),
             'integer': int, 'boolean': bool}
    if not isinstance(value, types[kind]) or (kind in ('number', 'integer') and isinstance(value, bool)):
        raise ValueError(f'{path}: expected {kind}')
    if kind in ('number', 'integer') and not math.isfinite(value):
        raise ValueError(f'{path}: non-finite number')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path}: unsupported value')
    if kind == 'object':
        if set(value) != set(schema['properties']):
            raise ValueError(f'{path}: missing or unexpected fields')
        for key, child in schema['properties'].items():
            validate_schema(value[key], child, f'{path}.{key}')
    if kind == 'array':
        for index, item in enumerate(value):
            validate_schema(item, schema['items'], f'{path}[{index}]')


def is_grace(event):
    return (event['duration'] == 0 and bool(event['notes']) and
            bool(re.search(r'\bgrace\b', event.get('marks', ''), re.I)))


def bar_issues(bar, instrument, strings=4):
    issues = list(bar.get('issues', []))
    meter = bar['meter']
    if len(meter) != 2 or not 1 <= meter[0] <= 32 or meter[1] not in (1, 2, 4, 8, 16, 32):
        return issues + ['Invalid time signature']
    beats = meter[0] * 4 / meter[1]
    if not 0 <= bar['confidence'] <= 1:
        issues.append('Invalid confidence')
    if bar['confidence'] < .85:
        issues.append('Visual reading needs review')
    voices = {}
    for e in bar['events']:
        grace = is_grace(e) and instrument in ('drums', 'piano')
        if (e['duration'] <= 0 and not grace) or e['onset'] < 0 or e['onset'] + e['duration'] > beats + .001:
            issues.append('Event falls outside the measure')
        if e['staff'] not in ((1, 2) if instrument == 'piano' else (1,)) or not 1 <= e['voice'] <= 8:
            issues.append('Invalid staff or voice')
        voices.setdefault((e['staff'], e['voice']), []).append(e)
        for n in e['notes']:
            supported = ({'tie-start', 'tie-stop', 'hammer-start', 'hammer-stop', 'pull-start', 'pull-stop',
                          'slide-up', 'slide-down', 'slide-in', 'slap', 'pop', 'vibrato', 'muted', 'ghost'}
                         if instrument in ('bass', 'guitar') else
                         {'tie-start', 'tie-stop', 'slur-start', 'slur-stop', 'staccato', 'accent', 'tenuto', 'muted', 'ghost'})
            unsupported = set(n['marks'].split())-supported
            if unsupported:
                issues.append('Notation requiring manual engraving: '+', '.join(sorted(unsupported)))
            if instrument in ('bass', 'guitar'):
                if not 1 <= n['string'] <= strings or not (n['fret'].isdigit() and int(n['fret']) <= 36 or n['fret'].upper() == 'X'):
                    issues.append('Invalid TAB string or fret')
            elif instrument == 'piano':
                if n['step'] not in 'CDEFGAB' or len(n['step']) != 1 or not 0 <= n['octave'] <= 9 or not -2 <= n['alter'] <= 2:
                    issues.append('Invalid pitch')
            elif not n['drum'] or n['step'] not in list('CDEFGAB') or not 0 <= n['octave'] <= 9:
                issues.append('Missing percussion instrument or invalid staff position')
    if instrument in ('bass', 'guitar') and len(voices) > 1:
        issues.append('Independent TAB voices require manual engraving')
    if not voices:
        issues.append('Measure has no rhythmic events')
    if instrument == 'piano' and {s for s, v in voices} != {1, 2}:
        issues.append('Piano measure must include both staves, including rests')
    for key, events in voices.items():
        cursor = 0
        for e in sorted(events, key=lambda item: item['onset']):
            if is_grace(e) and instrument in ('drums', 'piano'):
                continue
            if abs(e['onset'] - cursor) > .001:
                issues.append(f'Gap or overlap in staff {key[0]}, voice {key[1]}')
            cursor = e['onset'] + e['duration']
        if not bar['pickup'] and abs(cursor - beats) > .001:
            issues.append(f'Incomplete rhythm in staff {key[0]}, voice {key[1]}')
    return list(dict.fromkeys(issues))


def validate_score(score):
    bars = score['bars']
    problems = []
    numbers = [b['number'] for b in bars]
    if len(numbers) != len(set(numbers)):
        problems.append('Duplicate measure numbers')
    if numbers:
        expected = set(range(score['meta'].get('first_bar', min(numbers)),
                             score['meta'].get('last_bar', 0) or max(numbers) + 1))
        # last_bar is inclusive when known.
        if score['meta'].get('last_bar', 0):
            expected.add(score['meta']['last_bar'])
        missing = sorted(expected - set(numbers))
        if missing:
            problems.append('Missing bars: ' + ', '.join(map(str, missing)))
    else:
        problems.append('No measures transcribed')
    for bar in bars:
        for issue in bar_issues(bar, score['meta']['instrument'], score['meta']['strings']):
            problems.append(f"Bar {bar['number']}: {issue}")
    return problems


def whole_rest(bar, instrument, strings):
    """A complete measure of rest that may join a multi-measure rest block.

    Free-text issues and a low confidence flag do not disqualify a rest bar; structural
    problems (notes, gaps, wrong meter) do.
    """
    if bar['pickup'] or not bar['events'] or any(e['notes'] for e in bar['events']):
        return False
    problems = bar_issues({**bar, 'issues': []}, instrument, strings)
    return not [p for p in problems if p != 'Visual reading needs review']


def merge_groups(score, layout, bars, by_number):
    """Explicit rest groups, then printed multi-measure blocks, or every rest run under an override."""
    instrument, strings = score['meta']['instrument'], score['meta'].get('strings', 0)
    groups, consumed = [], set()
    for group in layout['merge_rests']:
        if len(group) < 2 or group != list(range(group[0], group[-1] + 1)):
            raise ValueError('A rest group must contain consecutive measure numbers.')
        if consumed.intersection(group) or any(n not in by_number for n in group):
            raise ValueError('Rest groups overlap or refer to missing bars.')
        meter = by_number[group[0]]['meter']
        for number in group:
            bar = by_number[number]
            if bar['pickup'] or bar['meter'] != meter or any(e['notes'] for e in bar['events']) or bar_issues(bar, instrument, strings):
                raise ValueError(f'Bar {number} is not a verified whole-measure rest.')
        groups.append(list(group))
        consumed.update(group)
    candidates = []
    if layout['bars_per_line'] and layout['merge_rests_auto']:
        run = []
        for bar in bars:
            n = bar['number']
            rest = whole_rest(bar, instrument, strings)
            if rest and run and n == run[-1]+1 and bar['meter'] == by_number[run[0]]['meter']:
                run.append(n)
                continue
            if len(run) > 1:
                candidates.append(run)
            run = [n] if rest else []
        if len(run) > 1:
            candidates.append(run)
    else:
        for bar in bars:
            count = int(bar.get('multirest') or 0)
            if count < 2:
                continue
            group = list(range(bar['number'], bar['number']+count))
            if all(n in by_number and by_number[n]['meter'] == bar['meter'] and whole_rest(by_number[n], instrument, strings) for n in group):
                candidates.append(group)
    for group in candidates:
        if not consumed.intersection(group):
            groups.append(group)
            consumed.update(group)
    return groups


def printed_slots(score, layout):
    layout = {**default_format(), **layout}
    validate_schema(layout, FORMAT)
    if not 0 <= layout['bars_per_line'] <= 16:
        raise ValueError('Bars per line must be 0 (follow video) or between 1 and 16.')
    bars = [normalize_bar(b) for b in sorted(copy.deepcopy(score['bars']), key=lambda b: b['number'])]
    by_number = {b['number']: b for b in bars}
    merged = {}
    consumed = set()
    for group in merge_groups(score, layout, bars, by_number):
        merged[group[0]] = group
        consumed.update(group)
    slots = []
    for bar in bars:
        n = bar['number']
        if n in consumed and n not in merged:
            continue
        bar['source_numbers'] = merged.get(n, [n])
        if len(bar['source_numbers']) > 1:
            # The printed block ends a row when any of its bars did.
            bar['system_end'] = any(by_number[m].get('system_end') for m in bar['source_numbers'])
        slots.append(bar)
    if 'print_rows' in score:
        lookup = {b['number']: b for b in slots}
        return [[copy.deepcopy(lookup[n]) for n in row if n in lookup] for row in score['print_rows'] if any(n in lookup for n in row)]
    rows, row = [], []
    limit = layout['bars_per_line']
    source_ends = {b['number'] for b in bars if b.get('system_end')}
    if not limit and not source_ends:
        limit = max(1, min(16, score['meta'].get('source_bars_per_line', 0) or 4))
    for bar in slots:
        row.append(bar)
        if (limit and len(row) == limit) or (not layout['bars_per_line'] and any(n in source_ends for n in bar['source_numbers'])) or any(n in layout['break_after'] for n in bar['source_numbers']):
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows
