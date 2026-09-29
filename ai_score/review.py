"""Targeted visual review: separate music disagreements from engraving limitations."""
import copy
import json
from .accelerate import compact_schema
from .contracts import bar_issues, obj, arr, I, S, TRANSCRIPTION


def music_signature(bar):
    events = []
    for event in bar['events']:
        notes = []
        for note in event['notes']:
            note = dict(note)
            note['marks'] = ' '.join(sorted(note['marks'].split()))
            notes.append(note)
        events.append({**{k: event[k] for k in ('voice', 'staff')},
                       'onset': round(float(event['onset']), 5), 'duration': round(float(event['duration']), 5),
                       'notes': sorted(notes, key=lambda n: json.dumps(n, sort_keys=True)),
                       # Event prose is retained in the score/warnings, but wording
                       # differences do not justify another visual transcription.
                       'grace': event['duration'] == 0})
    return json.dumps({'meter': bar['meter'], 'pickup': bar['pickup'],
                       'tempo_bpm': bar.get('tempo_bpm', 0), 'rehearsal': bar.get('rehearsal', ''),
                       'multirest': bar.get('multirest', 0),
                       'events': sorted(events, key=lambda e: (e['staff'], e['voice'], e['onset'], json.dumps(e)))}, sort_keys=True)


def needs_visual_review(bar, meta):
    # Free-text limitations are still shown in review notes. Re-reading cannot
    # implement a missing engraving feature or supply an absent percussion legend.
    clean = {**bar, 'issues': []}
    problems = bar_issues(clean, meta['instrument'], meta['strings'])
    return any(not p.startswith(('Notation requiring manual engraving:',
                                 'Independent TAB voices require manual engraving')) for p in problems)


def schema(instrument, numbers, compact=True):
    base = compact_schema(instrument) if compact else copy.deepcopy(TRANSCRIPTION)
    bar = base['properties']['bars']['items']
    bar['properties']['number'] = {'type': 'integer', 'enum': list(numbers)}
    return obj({'bars': {'type': 'array', 'items': bar, 'maxItems': len(numbers)},
                'confirmed': arr({'type': 'integer', 'enum': list(numbers)}),
                'unreadable': arr(obj({'number': {'type': 'integer', 'enum': list(numbers)}, 'reason': S})),
                'observations': arr(S)})


def prompt(reading_prompt):
    return (reading_prompt.replace('Transcribe every complete readable measure in this time window.',
            'Verify ONLY the measures listed in review_only_bars against the images.') + '''
This is a targeted correction request, not a full transcription. Do not return
neighboring bars. If a prior bar has the same notes, rhythms and written marks,
return only its number in confirmed. Return full bar data in bars ONLY when an
actual correction is needed. For an unreadable bar, return its number and reason
in unreadable; never guess a replacement. Every requested number must occur in
exactly one of bars, confirmed or unreadable. Do not reword unchanged event marks.
Missing engraving support or an absent percussion legend is a limitation to keep
in observations, not a reason to regenerate the same notes. For piano/drums,
explicit grace notes have duration=0 and event marks such as 'slashed grace eighth'.
Never use duration=0 for ordinary notes or rests.''')


def apply_result(result, numbers, bars, conflicts, observations, meta, expand):
    requested = set(numbers)
    changed = expand({'bars': result['bars'], 'observations': []})['bars'] if expand else result['bars']
    changed_ids = [b['number'] for b in changed]
    confirmed = result['confirmed']
    unreadable = [item['number'] for item in result['unreadable']]
    ids = changed_ids+confirmed+unreadable
    if set(ids)-requested or len(ids) != len(set(ids)):
        raise ValueError('AI review returned unrelated or duplicate measure decisions.')
    for bar in changed:
        bars[bar['number']] = bar
        if not needs_visual_review(bar, meta):
            conflicts.discard(bar['number'])
    for number in confirmed:
        if number in bars and not needs_visual_review(bars[number], meta):
            conflicts.discard(number)
    for item in result['unreadable']:
        observations.append(f"Bar {item['number']}: {item['reason']}")
    for number in requested-set(ids):
        observations.append(f'Bar {number}: AI review returned no decision; verify manually.')
    observations.extend(result['observations'])
