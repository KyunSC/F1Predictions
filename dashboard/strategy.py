"""Pit strategy advisor: when each car should stop, and whether to box under a safety car or VSC.

Display only, like the rejoin projection it builds on. Inputs are the live timing feed
(stints, lap count, gaps, track status) and the pit-loss table; nothing feeds the notebook.

Tyre life per compound comes from stints already completed in this race once enough cars
have stopped, otherwise from a share of the race distance. Under a safety car or VSC a
stop costs the neutralised pit loss instead of the green-flag one, so a stop the car needs
anyway is cheaper now; a car with no stop left boxes only when it keeps its position.
"""
import math
import statistics
from . import pit_loss as pit

DRY = ('SOFT', 'MEDIUM', 'HARD')
WET = ('INTERMEDIATE', 'WET')
# Expected tyre life as a share of race laps until this race shows its own.
LIFE_SHARE = {'SOFT': .3, 'MEDIUM': .45, 'HARD': .6, 'INTERMEDIATE': .5, 'WET': .5}
MIN_OBSERVED = 3   # completed stints of a compound before this race's tyre life replaces the default
SHORT_STINT = 5    # shorter stints are lap-one or damage stops, not tyre life
OPEN_SHARE = .75   # the window opens at this share of expected life
STRETCH = 1.1      # a tyre can run this far past its expected life
FRESH = 3          # laps on new tyres before a neutralised stop is worth another one
MIN_TO_GO = 3      # fewer laps left and fresh tyres cannot pay back a stop
OLD_SHARE = .5     # tyre age (share of life) from which pulling a needed stop forward is worth it
STACK_GAP = 3.0    # seconds: a team-mate this close ahead and also boxing means queueing
NEUTRAL = {'4': 'sc', '6': 'vsc', '7': 'vsc'}
NAMES = {'sc': 'Safety car', 'vsc': 'VSC'}


def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ordered_stints(line):
    stints = (line or {}).get('Stints', {})
    return [stints[k] for k in sorted((k for k in stints if str(k).isdigit()), key=int) if isinstance(stints[k], dict)]


def tyre_lives(tyres, total_laps):
    """Expected tyre age at which each compound is changed, with where that number came from."""
    observed = {}
    for line in tyres.values():
        for stint in ordered_stints(line)[:-1]:  # every stint but the current one has ended in a stop
            age, start = number(stint.get('TotalLaps')), number(stint.get('StartLaps')) or 0
            if stint.get('Compound') in LIFE_SHARE and age is not None and age - start >= SHORT_STINT:
                observed.setdefault(stint['Compound'], []).append(age)
    lives = {}
    for compound, share in LIFE_SHARE.items():
        seen = observed.get(compound, [])
        if len(seen) >= MIN_OBSERVED:
            lives[compound] = dict(laps=round(statistics.median(seen)), basis='race', stints=len(seen))
        else:
            lives[compound] = dict(laps=max(1, round(share * total_laps)), basis='default', stints=len(seen))
    return lives


def plan(stints, lap, total, lives):
    """Stops left and the next pit window for one car, or None without tyre data."""
    if not stints:
        return None
    current = stints[-1]
    compound, age = current.get('Compound'), number(current.get('TotalLaps'))
    if compound not in LIFE_SHARE or age is None:
        return None
    life = lives[compound]['laps']
    to_go = max(0, total - lap + 1)  # includes the lap in progress
    used = {s.get('Compound') for s in stints}
    # Dry races require two dry compounds; using intermediates or wets lifts the rule.
    must_change = not used & set(WET) and len(used & set(DRY)) < 2
    left_on_tyre = max(0, math.floor(life * STRETCH) - age)
    longest = max(lives[c]['laps'] for c in (WET if compound in WET else DRY))
    if to_go <= left_on_tyre:
        stops = 1 if must_change and to_go > 1 else 0
    else:
        stops = math.ceil((to_go - left_on_tyre) / (longest * STRETCH))
    result = dict(compound=compound, age=age, life=life, to_go=to_go, stops=stops, must_change=must_change,
                  window=None, final_stint=to_go <= longest * STRETCH, reaches_end=to_go <= left_on_tyre)
    if stops:
        close = min(lap + left_on_tyre, total - 1)
        # On the last stop the next set must reach the flag.
        last_set = total - math.floor(longest * STRETCH) + 1 if stops == 1 else lap
        open_ = max(lap + max(0, math.ceil(life * OPEN_SHARE) - age), last_set, lap)
        result['window'] = [min(open_, close), close]
    return result


def green_call(p):
    tyre = f"{p['compound'].title()} {p['age']}/{p['life']} laps"
    if not p['stops']:
        return 'no_stop', 'TO END', f'{tyre}: can reach the flag'
    if p['reaches_end']:
        tyre += ' would reach the flag, but a second dry compound is required'
    first, last = p['window']
    if p['age'] >= p['life'] * STRETCH:
        return 'box', 'BOX', f'{tyre}: past expected life'
    if p['current_lap'] >= last:
        return 'box', 'BOX', f'{tyre}: last lap of the window'
    if p['current_lap'] >= first:
        return 'window', 'WINDOW', f'{tyre}: window open until lap {last}'
    return 'stay_out', f'L{first}' if first == last else f'L{first}–{last}', f'{tyre}: window laps {first}–{last}'


def neutral_call(p, rejoin, kind, saving):
    cheaper = f'saves {saving:.1f} s on a green-flag stop' if saving and saving > 0 else 'same loss as a green-flag stop'
    where = f"rejoins P{rejoin['position']}" if rejoin else 'rejoin unknown'
    lost = (rejoin or {}).get('positions_lost')
    if p['age'] < FRESH:
        return 'stay_out', 'STAY OUT', f"Stopped {p['age']} laps ago"
    if p['to_go'] < MIN_TO_GO:
        return 'stay_out', 'STAY OUT', 'Too few laps left for fresh tyres to pay back'
    if p['stops']:
        if p['final_stint'] or p['age'] >= p['life'] * OLD_SHARE:
            return 'box', 'BOX', f"Cheap stop: {cheaper}, {where}" + ('' if p['final_stint'] else '; one more stop after')
        free = ' without losing a place' if lost is not None and lost <= 0 else ''
        return 'consider', 'MAYBE', f"Tyres only {p['age']}/{p['life']} laps old; boxing {cheaper}{free} but still needs another stop"
    if lost is not None and lost <= 0:
        return 'box', 'BOX', f"Free stop: {where} on fresh tyres for {p['to_go']} laps"
    if p['age'] >= p['life'] * OLD_SHARE and p['to_go'] >= 2 * MIN_TO_GO:
        return 'consider', 'MAYBE', f"Can reach the flag, but {p['age']}-lap tyres vs fresh ones; {where}" + (f', {lost} places lost' if lost else '')
    return 'stay_out', 'STAY OUT', 'Keep track position' + (f': boxing loses {lost} place{"" if lost == 1 else "s"}' if lost else '')


def advise(drivers, tyres, laps, status, loss, green):
    """Per-car strategy calls, keyed by racing number, and a summary of the track condition."""
    status = str(status or '')
    kind = NEUTRAL.get(status)
    lap, total = number((laps or {}).get('CurrentLap')), number((laps or {}).get('TotalLaps'))
    neutral_loss = loss.get('seconds') if kind and loss.get('condition') == kind else None
    saving = round(green - neutral_loss, 1) if green is not None and neutral_loss is not None else None
    summary = dict(condition='red' if status == '5' else kind or 'green', saving=saving, loss=loss.get('seconds'),
                   green_loss=green, boxes=[], lives={}, reason=None)
    if status == '5':
        return {}, dict(summary, reason='Red flag: teams may change tyres in the pit lane without losing time.')
    if not lap or not total or not tyres:
        return {}, dict(summary, reason='Awaiting lap count and tyre data.')
    lives = tyre_lives(tyres, total)
    summary['lives'] = lives
    times = pit.race_times(drivers)
    calls = {}
    for driver in drivers:
        p = plan(ordered_stints(tyres.get(driver['number'])), lap, total, lives)
        if driver.get('retired') or p is None:
            calls[driver['number']] = None
            continue
        p['current_lap'] = lap
        if driver.get('in_pit'):
            call = ('in_pit', 'IN PIT', 'In the pit lane now')
        elif kind:
            call = neutral_call(p, driver.get('pit_rejoin'), kind, saving)
            if status == '7' and call[0] == 'box':
                call = ('consider', 'MAYBE', 'VSC ending: the green flag may come before the stop. ' + call[2])
        else:
            call = green_call(p)
        calls[driver['number']] = dict(call=call[0], label=call[1], reason=call[2], window=p['window'],
                                       stops=p['stops'], compound=p['compound'], age=p['age'], life=p['life'],
                                       stack=None)
    boxing = [d for d in drivers if (calls.get(d['number']) or {}).get('call') == 'box']
    for driver in boxing:
        mates = [d for d in boxing if d is not driver and d.get('team') and d.get('team') == driver.get('team')]
        for mate in mates:
            mine, theirs = times.get(driver['number']), times.get(mate['number'])
            if mine is not None and theirs is not None and 0 <= mine - theirs <= STACK_GAP:
                calls[driver['number']]['stack'] = mate['number']
    summary['boxes'] = [d['number'] for d in boxing]
    if kind and neutral_loss is None:
        summary['reason'] = f'No {NAMES[kind]} pit-loss history; calls assume the green-flag loss.'
    return calls, summary
