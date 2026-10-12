"""Import F1 raw archives for dashboard replay; never loads prediction sessions.

Archive framing follows FastF1's documented fetch_page implementation:
https://github.com/theOehrly/Fast-F1/blob/master/fastf1/_api.py
Requires curl for HTTPS downloads; successful responses are cached locally.
"""
import argparse
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from .state import TOPICS

BASE = 'https://livetiming.formula1.com/static/'
CACHE = Path(__file__).resolve().parents[1] / 'cache' / 'historical'
RECORDINGS = Path(__file__).resolve().parent / 'recordings'
FIRST_YEAR = 2018
# The archive publishes a session's streams some time after it ends; waiting avoids
# caching incomplete streams forever.
PUBLISH_DELAY = timedelta(hours=1)


def download(relative, cache=CACHE, refresh=False):
    """Fetch an archive file, cached forever; `refresh` refetches but falls back to the cache offline."""
    # Archive folders use accented event names (e.g. 2025 "São_Paulo"), so allow
    # Unicode word characters per segment while still rejecting traversal.
    if any(s in ('.', '..') or not re.fullmatch(r'[\w.-]+', s) for s in relative.split('/')):
        raise ValueError('Invalid archive path')
    path = cache / relative
    if path.exists() and not refresh:
        return path.read_text(encoding='utf-8-sig')
    try:
        result = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--max-time', '60',
                                 BASE + quote(relative)], capture_output=True, check=True)
    except (subprocess.CalledProcessError, OSError):
        if refresh and path.exists():
            return path.read_text(encoding='utf-8-sig')
        raise
    text = result.stdout.decode('utf-8-sig')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return text


def http_client_error(exc):
    """Whether curl --fail stopped on an HTTP 4xx (the archive answers 403 for a missing stream).

    curl exits 22 for this, but over HTTP/2 some versions (e.g. 8.7) exit 56 and only
    the message names the status.
    """
    return exc.returncode == 22 or re.search(rb'returned error: 4\d\d\b', exc.stderr or b'') is not None


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


def load_index(year, now, fetch=download):
    """The season's archive index; the current season's is refetched because it still grows."""
    relative = f'{year}/Index.json'
    return json.loads(fetch(relative, refresh=True) if year >= now.year else fetch(relative))


def utc_time(session, field):
    """`StartDate`/`EndDate` are local track time; `GmtOffset` converts them to aware UTC."""
    try:
        moment = datetime.fromisoformat(session[field])
        if moment.tzinfo is None:
            offset = session['GmtOffset']
            moment = datetime.fromisoformat(session[field] + (offset if offset.startswith(('+', '-')) else '+' + offset))
    except (KeyError, TypeError, ValueError):
        return None
    return moment.astimezone(timezone.utc)


def utc_end(session):
    return utc_time(session, 'EndDate')


def available(session, now):
    end = utc_end(session)
    return end is not None and end + PUBLISH_DELAY <= now


def slug(name):
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', ascii_name.casefold()).strip('-')


def recording_path(year, meeting, session, recordings=None):
    return (recordings or RECORDINGS) / f"archive-{year}-{slug(meeting['Name'])}-{slug(session['Name'])}-{session['Key']}.jsonl"


def catalog(year, now, fetch=download, recordings=None):
    """Every meeting and session in the season's index, in index order."""
    def start(session):
        moment = utc_time(session, 'StartDate')
        return moment and moment.isoformat()
    return [dict(event=m['Name'], key=m.get('Key'), location=m.get('Location'), sessions=[
        dict(key=s['Key'], name=s['Name'], type=s.get('Type'), start_utc=start(s),
             available=available(s, now), cached=recording_path(year, m, s, recordings).exists())
        for s in m.get('Sessions', [])]) for m in load_index(year, now, fetch)['Meetings']]


def find_session(index, key):
    """(meeting, session) by the session's numeric Key; meeting names repeat (two 2026 tests)."""
    for meeting in index['Meetings']:
        for session in meeting.get('Sessions', []):
            if session.get('Key') == key:
                return meeting, session
    return None


def latest_race(now, fetch=download):
    """The newest archived Grand Prix ("Race", not "Sprint"), from this season or else the last."""
    for year in (now.year, now.year - 1):
        races = [(utc_end(s), m, s) for m in load_index(year, now, fetch)['Meetings']
                 for s in m.get('Sessions', []) if s['Name'] == 'Race' and available(s, now)]
        if races:
            _, meeting, session = max(races, key=lambda r: r[0])
            return dict(year=year, meeting=meeting, session=session)
    return None


def import_session(year, event, session, output, fetch=download):
    index = json.loads(fetch(f'{year}/Index.json'))
    meetings = [m for m in index['Meetings'] if m['Name'].casefold() == event.casefold()]
    sessions = [s for m in meetings for s in m['Sessions'] if s['Name'].casefold() == session.casefold()]
    if len(sessions) != 1:
        raise ValueError('Event/session must identify exactly one archive session')
    return import_path(year, sessions[0]['Path'], output, fetch)


def import_by_key(year, key, output, fetch=download):
    found = find_session(json.loads(fetch(f'{year}/Index.json')), key)
    if not found:
        raise ValueError(f'No archive session {key} in {year}')
    return import_path(year, found[1]['Path'], output, fetch)


def import_path(year, path, output, fetch=download):
    if not path.startswith(f'{year}/'):
        raise ValueError('Archive year mismatch')
    events, missing = [], []
    for topic in TOPICS:
        try:
            events.extend(parse_stream(fetch(path + topic + '.jsonStream'), topic))
        except subprocess.CalledProcessError as exc:
            if not http_client_error(exc):  # Do not silently downgrade network failures.
                raise
            missing.append(topic)
    if not any(e['topic'] == 'SessionInfo' for e in events):
        raise ValueError('Archive lacks SessionInfo')
    events.sort(key=lambda e: (e['at'], e['topic'] != 'SessionInfo'))
    for e in events:
        e['provenance'] = BASE + path
    output.parent.mkdir(parents=True, exist_ok=True)
    # Write then rename: an existing recording is taken as a complete import.
    partial = output.with_suffix('.partial' + output.suffix)
    partial.write_text(''.join(json.dumps(e) + '\n' for e in events))
    partial.replace(output)
    return dict(events=len(events), missing_streams=missing, source=BASE+path,
                playback='Reconstructed archive clock; live receipt/network delays unavailable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--latest-race', action='store_true',
                        help='import the most recent archived Grand Prix if missing and print its recording path')
    parser.add_argument('--year', type=int)
    parser.add_argument('--event')
    parser.add_argument('--session', default='Race')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.latest_race:
        found = latest_race(datetime.now(timezone.utc))
        if not found:
            parser.exit(1, 'No archived race found\n')
        year, meeting, session = found['year'], found['meeting'], found['session']
        output = args.output or recording_path(year, meeting, session)
        if not output.exists():
            print(f"Importing {year} {meeting['Name']} · {session['Name']} for Historical replay...",
                  file=sys.stderr, flush=True)
            import_path(year, session['Path'], output)
        print(json.dumps(dict(output=str(output), event=meeting['Name'], session=session['Name'])))
        return
    if args.year is None or not args.event or args.output is None:
        parser.error('--year, --event and --output are required unless --latest-race is given')
    print(json.dumps(import_session(args.year, args.event, args.session, args.output), indent=2))


if __name__ == '__main__':
    main()
