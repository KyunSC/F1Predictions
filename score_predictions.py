"""Score the saved podium predictions in results/ against the actual classifications.

Each `results/*_prediction_*.md` snapshot is matched to its session by its title, e.g.
"Podium prediction: 2026 Bahrain Grand Prix (Sepang, Oct 4)" or "... 2026 Singapore Sprint ...".
The title's date is the scored session's date; FastF1's UTC date may differ from it by a day
(a Saturday-night race such as Las Vegas). The actual classification is read from
`results/actual/<year>-<event>-<kind>.json`. When that file is missing (or with --refresh) it is
fetched through FastF1 and saved there, so the scored result is recorded next to the prediction.
A snapshot whose session has not happened yet, or whose result cannot be fetched, is listed as
not scored yet. The scorecard is written to results/scorecard.md.

Run: python score_predictions.py [--refresh]
"""
import argparse
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'results'
ACTUAL_DIR = RESULTS / 'actual'
SCORECARD = RESULTS / 'scorecard.md'
CACHE_DIR = ROOT / 'cache'
SESSION_CODES = {'race': 'R', 'sprint': 'S'}
# FastF1 ClassifiedPosition letters for drivers without a classified position.
NOT_CLASSIFIED = {'R': 'DNF', 'D': 'DSQ', 'E': 'EXCL', 'W': 'DNS', 'F': 'DNQ', 'N': 'NC'}
TITLE = re.compile(r'^# Podium prediction: (\d{4}) (.+?) (Grand Prix|Sprint) \((.+), (\w{3}) (\d{1,2})\)\s*$', re.M)
MONTHS = {m: i for i, m in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}
BEST = re.compile(r'\*\*1\. ([^,]+), 2\. ([^,]+), 3\. ([^*]+?)\.?\*\*')
CODE = re.compile(r'^([A-Z]{3})\b')


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def utc_today():
    return datetime.now(timezone.utc).date()


def fold(name):
    """Last word of a name, lower-cased and without accents: 'Sergio Pérez' -> 'perez'."""
    return unicodedata.normalize('NFKD', name.split()[-1]).encode('ascii', 'ignore').decode().lower()


def parse_prediction(path):
    """Session identity, best single answer (surnames) and per-model podiums (codes)."""
    text = path.read_text()
    title = TITLE.search(text)
    if not title:
        raise ValueError(f'{path.name}: no "# Podium prediction: <year> <event> (<venue>, <Mon> <day>)" title')
    year, name, kind_word, venue, month, day = title.groups()
    best = BEST.search(text)
    if not best:
        raise ValueError(f'{path.name}: no "**1. A, 2. B, 3. C**" best single answer')
    section = text.split('## Predicted podium by model', 1)
    if len(section) < 2:
        raise ValueError(f'{path.name}: no "Predicted podium by model" section')
    models = {}
    for line in section[1].split('\n## ', 1)[0].splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) != 4 or cells[0] == 'Model' or set(cells[0]) <= set('-: '):
            continue
        codes = [CODE.match(c) for c in cells[1:]]
        if not all(codes):
            raise ValueError(f'{path.name}: model row {cells[0]!r} does not start each place with a driver code')
        models[cells[0]] = [c.group(1) for c in codes]
    if not models:
        raise ValueError(f'{path.name}: the "Predicted podium by model" table has no rows')
    return dict(file=path.name, year=int(year), event=f'{name} Grand Prix', kind='race' if kind_word == 'Grand Prix' else 'sprint',
                label=f'{year} {name} {kind_word}', venue=venue,
                date=date(int(year), MONTHS[month], int(day)).isoformat(),
                best=[s.strip() for s in best.groups()], models=models)


def actual_path(pred):
    return ACTUAL_DIR / f"{pred['year']}-{slug(pred['event'])}-{pred['kind']}.json"


def fetch_fastf1(pred, renew=False):
    """Official classification through FastF1, checked against the prediction's session date.

    `renew` bypasses FastF1's local cache, so a refresh picks up post-race penalties.
    """
    import fastf1
    import pandas as pd
    CACHE_DIR.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR), force_renew=renew)
    session = fastf1.get_session(pred['year'], pred['event'], SESSION_CODES[pred['kind']])
    session_date = session.date.date()
    if abs((session_date - date.fromisoformat(pred['date'])).days) > 1:
        raise ValueError(f"FastF1 dates {pred['label']} {session_date}, the prediction says {pred['date']}")
    session.load(laps=False, telemetry=False, weather=False, messages=False)
    results = session.results
    if results is None or results.empty:
        raise ValueError(f"FastF1 returned no results for {pred['label']}")
    if pd.isna(results['Position']).all():
        raise ValueError(f"FastF1 results for {pred['label']} have no positions")
    rows = []
    for _, row in results.sort_values('Position').iterrows():
        classified, status = str(row['ClassifiedPosition']), str(row['Status'])
        if classified.isdigit():
            finished = status in ('Finished', 'Lapped') or status.startswith('+')
            rows.append(dict(position=int(classified), code=row['Abbreviation'], name=row['FullName'],
                             status='Finished' if finished else 'DNF'))
        else:
            rows.append(dict(position=None, code=row['Abbreviation'], name=row['FullName'],
                             status=NOT_CLASSIFIED.get(classified, status)))
    if sorted(r['position'] for r in rows if r['position'] is not None)[:3] != [1, 2, 3]:
        raise ValueError(f"FastF1 results for {pred['label']} do not classify positions 1 to 3")
    return dict(year=pred['year'], event=pred['event'], kind=pred['kind'], date=pred['date'],
                source=f'FastF1 {fastf1.__version__}', retrieved=date.today().isoformat(), classification=rows)


def dump_actual(actual):
    """JSON with one classification row per line, so diffs stay readable."""
    head = {k: v for k, v in actual.items() if k != 'classification'}
    lines = [f' {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},' for k, v in head.items()]
    rows = [f'  {json.dumps(r, ensure_ascii=False)}' for r in actual['classification']]
    return '{\n' + '\n'.join(lines) + '\n "classification": [\n' + ',\n'.join(rows) + '\n ]\n}\n'


def load_actual(pred, refresh=False, fetch=True):
    """The saved or fetched classification, or None while the session has no result yet.

    With fetch=False only saved results are read, so nothing touches the network.
    """
    path = actual_path(pred)
    if path.exists() and not refresh:
        actual = json.loads(path.read_text())
    elif not fetch or date.fromisoformat(pred['date']) > utc_today():
        return None
    else:
        try:
            actual = fetch_fastf1(pred, renew=refresh)
        except Exception as error:
            if not path.exists():
                print(f'No result for {pred["label"]} yet: FastF1 failed ({error}). To score it, save the official '
                      f'classification (e.g. from formula1.com/en/results) to {path.relative_to(ROOT)} in the same '
                      'format as the files already there.')
                return None
            print(f'FastF1 refresh failed for {pred["label"]} ({error}); keeping {path.relative_to(ROOT)}')
            actual = json.loads(path.read_text())
        else:
            ACTUAL_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(dump_actual(actual))
    for key in ('year', 'event', 'kind', 'date'):
        if actual[key] != pred[key]:
            raise ValueError(f'{path.name}: {key} is {actual[key]!r}, the prediction says {pred[key]!r}')
    return actual


def surname_codes(actual, surnames):
    by_surname = {}
    for r in actual['classification']:
        by_surname.setdefault(fold(r['name']), []).append(r['code'])
    missing = [s for s in surnames if fold(s) not in by_surname]
    if missing:
        raise ValueError(f"best single answer names {', '.join(missing)}, not in the classification")
    shared = [s for s in surnames if len(by_surname[fold(s)]) > 1]
    if shared:
        raise ValueError(f"best single answer names {', '.join(shared)}, a surname shared by several drivers")
    return [by_surname[fold(s)][0] for s in surnames]


def finish(actual, code):
    row = next((r for r in actual['classification'] if r['code'] == code), None)
    if row is None:
        return 'did not start'
    if row['position'] is None:
        return row['status']
    return f"P{row['position']}" + (f" ({row['status']})" if row['status'] != 'Finished' else '')


def score(predicted, actual):
    podium = [r['code'] for r in sorted((r for r in actual['classification'] if r['position'] is not None),
                                        key=lambda r: r['position'])[:3]]
    if len(podium) < 3:
        raise ValueError(f"{actual.get('event', 'result')}: fewer than three classified finishers")
    return dict(predicted=predicted, podium=podium,
                hits=[c for c in predicted if c in podium],
                misses=[(c, finish(actual, c)) for c in predicted if c not in podium],
                places=len(set(predicted) & set(podium)),
                exact=sum(p == a for p, a in zip(predicted, podium)),
                winner=predicted[0] == podium[0])


def score_all(refresh=False, fetch=True):
    """Scored sessions, and the predictions that have no result yet."""
    sessions, pending = [], []
    for pred in sorted((parse_prediction(p) for p in RESULTS.glob('*_prediction_*.md')), key=lambda p: p['date']):
        actual = load_actual(pred, refresh, fetch)
        if actual is None:
            pending.append(pred)
            continue
        sessions.append(dict(pred=pred, actual=actual, best=score(surname_codes(actual, pred['best']), actual),
                             models={m: score(p, actual) for m, p in pred['models'].items()}))
    return sessions, pending


def yes(flag):
    return 'yes' if flag else 'no'


def render(sessions, pending=()):
    out = ['# Prediction scorecard', '',
           'Written by `score_predictions.py` from the snapshots in this folder and the actual '
           'classifications in `actual/`; rerun it after adding a snapshot. A hit is a predicted '
           'podium driver who finished on the podium, in any order. "Exact" counts the places '
           'called in the right position.', '',
           '## Best single answer', '',
           '| Session | Predicted | Actual podium | Podium places | Exact | Winner |', '|---|---|---|---:|---:|---|']
    for s in sessions:
        b = s['best']
        out.append(f"| {s['pred']['label']} | {', '.join(b['predicted'])} | {', '.join(b['podium'])} | "
                   f"{b['places']} of 3 | {b['exact']} of 3 | {yes(b['winner'])} |")
    if pending:
        out += ['', '## Not scored yet', '', 'No result saved yet for:', '']
        out += [f"- {p['label']} ({p['venue']}, {p['date']}): [`{p['file']}`]({p['file']})" for p in pending]
    n = len(sessions)
    named = list(dict.fromkeys(m for s in sessions for m in s['models']))
    models = [m for m in named if all(m in s['models'] for s in sessions)]
    out += ['', f'## By model, over {n} session{"s" * (n != 1)}', '']
    if len(models) < len(named):
        out += [f"Left out because they are missing from some sessions: {', '.join(m for m in named if m not in models)}.", '']
    out += ['| Model | Podium places | Exact | Winners |', '|---|---:|---:|---:|']
    for m in models:
        rows = [s['models'][m] for s in sessions]
        out.append(f"| {m} | {sum(r['places'] for r in rows)} of {3 * n} | {sum(r['exact'] for r in rows)} of {3 * n} | "
                   f"{sum(r['winner'] for r in rows)} of {n} |")
    for s in sessions:
        pred, actual = s['pred'], s['actual']
        out += ['', f"## {pred['label']} ({pred['venue']}, {pred['date']})", '',
                f"Prediction: [`{pred['file']}`]({pred['file']}). Actual podium: **{', '.join(s['best']['podium'])}**. "
                f"Result from {actual['source']}, retrieved {actual['retrieved']}.", '',
                '| Model | Predicted | Hits | Misses (actual finish) | Podium places | Exact | Winner |',
                '|---|---|---|---|---:|---:|---|']
        for m, r in [('Best single answer', s['best']), *s['models'].items()]:
            misses = ', '.join(f'{c} {where}' for c, where in r['misses']) or '–'
            out.append(f"| {m} | {', '.join(r['predicted'])} | {', '.join(r['hits']) or '–'} | {misses} | "
                       f"{r['places']} | {r['exact']} | {yes(r['winner'])} |")
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--refresh', action='store_true', help='refetch every result through FastF1')
    args = parser.parse_args()
    sessions, pending = score_all(args.refresh)
    SCORECARD.write_text(render(sessions, pending))
    for s in sessions:
        b = s['best']
        print(f"{s['pred']['label']}: called {', '.join(b['predicted'])}, podium {', '.join(b['podium'])}; "
              f"{b['places']}/3 places, {b['exact']}/3 exact, winner {yes(b['winner'])}")
    for p in pending:
        print(f"{p['label']}: not scored yet")
    print(f'Wrote {SCORECARD.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
