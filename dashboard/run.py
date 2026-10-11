"""Start and supervise both localhost dashboard services with ./start.sh."""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    argparse.ArgumentParser(description='Start the local F1 dashboard. Switch between historical replay and '
                            'live timing from the header. Ctrl+C stops both services.').parse_args()
    children = []

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        for port in (8000, 5173):
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    probe.bind(('127.0.0.1', port))
                except OSError:
                    raise RuntimeError(f'Port {port} is already in use. Stop the existing dashboard/server first.')
        if not shutil.which('npm') or not shutil.which('node'):
            raise RuntimeError('Install Node.js 20.19+ (including npm), then run ./start.sh again.')
        python = ROOT / '.venv/bin/python'
        if not python.exists():
            creator = shutil.which('python3.12')
            if not creator:
                raise RuntimeError('Install Python 3.12, then run ./start.sh again.')
            subprocess.run([creator, '-m', 'venv', str(ROOT / '.venv')], check=True)
        check = subprocess.run([str(python), '-c', 'import fastapi, uvicorn, httpx, websockets'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check.returncode:
            subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
        next_bin = ROOT / 'frontend/node_modules/next/dist/bin/next'
        if not next_bin.exists():
            subprocess.run(['npm', 'ci'], cwd=ROOT / 'frontend', check=True)
        archive = ROOT / 'dashboard/recordings/archive-2026-bahrain-race.jsonl'
        if not archive.exists():
            print('Importing the 2026 Bahrain GP (Kuala Lumpur) archive for Historical replay...', flush=True)
            imported = subprocess.run([str(python), '-m', 'dashboard.historical', '--year', '2026', '--event',
                                       'Bahrain Grand Prix', '--session', 'Race', '--output', str(archive)],
                                      cwd=ROOT, stdout=subprocess.DEVNULL)
            if imported.returncode:
                print('Warning: archive import failed; Historical mode will use the six-driver demo.', flush=True)
        env = os.environ.copy()
        env.setdefault('NEXT_TELEMETRY_DISABLED', '1')
        print('\nStarting F1 dashboard. Switch Historical/Live from the header; Ctrl+C stops both services.\n',
              flush=True)
        commands = [
            [str(python), '-m', 'uvicorn', 'dashboard.app:app', '--host', '127.0.0.1', '--port', '8000'],
            ['node', str(next_bin), 'dev', '--hostname', '127.0.0.1', '--port', '5173'],
        ]
        for command, cwd in zip(commands, [ROOT, ROOT / 'frontend']):
            children.append(subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True))
        deadline = time.monotonic() + 30
        ready = False
        while True:
            for child in children:
                if child.poll() is not None:
                    raise RuntimeError(f'A dashboard service exited (code {child.returncode}). See its output above.')
            if not ready:
                try:
                    for url in ('http://127.0.0.1:8000/api/state', 'http://127.0.0.1:5173'):
                        with urlopen(url, timeout=10) as response:
                            if response.status != 200:
                                raise OSError('Service not ready')
                    ready = True
                    print('\nDashboard ready: http://127.0.0.1:5173\n', flush=True)
                except OSError:
                    if time.monotonic() > deadline:
                        raise RuntimeError('Dashboard startup timed out. See service output above.')
            time.sleep(.25)
    except KeyboardInterrupt:
        print('\nStopping dashboard...', flush=True)
        return 0
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'\n{exc}', file=sys.stderr)
        return 1
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


if __name__ == '__main__':
    sys.exit(main())
