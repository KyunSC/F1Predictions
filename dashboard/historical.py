"""Import F1 raw archives for dashboard replay; never loads prediction sessions.

Archive framing follows FastF1's documented fetch_page implementation:
https://github.com/theOehrly/Fast-F1/blob/master/fastf1/_api.py
Requires curl for HTTPS downloads; successful responses are cached locally.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path
from .state import TOPICS

BASE = 'https://livetiming.formula1.com/static/'
CACHE = Path(__file__).resolve().parents[1] / 'cache' / 'historical'


def download(relative, cache=CACHE):
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', relative) or '..' in relative.split('/'):
        raise ValueError('Invalid archive path')
    path = cache / relative
    if path.exists():
        return path.read_text(encoding='utf-8-sig')
    result = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--max-time', '60',
                             BASE + relative], capture_output=True, check=True)
    text = result.stdout.decode('utf-8-sig')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def parse_stream(text, topic):
    events = []
    for number, line in enumerate(text.lstrip('\ufeff').splitlines(), 1):
        if not line.strip():
            continue
        match = re.match(r'^(\d{2}):(\d{2}):(\d{2})\.(\d{3})(.+)$', line)
        if not match:
            raise ValueError(f'{topic} line {number}: invalid archive clock')
        h, m, s, ms = map(int, match.groups()[:4])
        if m >= 60 or s >= 60:
            raise ValueError('Invalid archive clock')
        events.append(dict(at=h*3600+m*60+s+ms/1000, topic=topic,
                           data=json.loads(match[5]), reconstructed=True))
    return events


def import_session(year, event, session, output, fetch=download):
    index = json.loads(fetch(f'{year}/Index.json'))
    meetings = [m for m in index['Meetings'] if m['Name'].casefold() == event.casefold()]
    sessions = [s for m in meetings for s in m['Sessions'] if s['Name'].casefold() == session.casefold()]
    if len(sessions) != 1:
        raise ValueError('Event/session must identify exactly one archive session')
    path = sessions[0]['Path']
    if not path.startswith(f'{year}/'):
        raise ValueError('Archive year mismatch')
    events, missing = [], []
    for topic in TOPICS:
        try:
            events.extend(parse_stream(fetch(path + topic + '.jsonStream'), topic))
        except subprocess.CalledProcessError as exc:
            if exc.returncode != 22:  # Do not silently downgrade network failures.
                raise
            missing.append(topic)
    if not any(e['topic'] == 'SessionInfo' for e in events):
        raise ValueError('Archive lacks SessionInfo')
    events.sort(key=lambda e: (e['at'], e['topic'] != 'SessionInfo'))
    for e in events:
        e['provenance'] = BASE + path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(json.dumps(e) + '\n' for e in events))
    return dict(events=len(events), missing_streams=missing, source=BASE+path,
                playback='Reconstructed archive clock; live receipt/network delays unavailable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--event', required=True)
    parser.add_argument('--session', default='Race')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(import_session(args.year, args.event, args.session, args.output), indent=2))


if __name__ == '__main__':
    main()
