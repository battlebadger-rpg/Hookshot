"""
Delivery runner: starts the HookShot Flask server, logs in, and calls /api/deliver
for each model with the correct video counts for a 7-day schedule.

  Annabelle  3 accounts × 5 videos/day × 7 days = 105
  Naomi      2 accounts × 5 videos/day × 7 days =  70
  Silvia     2 accounts × 5 videos/day × 7 days =  70
  Klonoa     2 accounts × 5 videos/day × 7 days =  70

Logs progress to delivery_run.log in the same folder.
"""

import subprocess
import sys
import os
import time
import requests
import json

LOG_PATH = os.path.join(os.path.dirname(__file__), 'delivery_run.log')
BASE_URL  = 'http://localhost:5002'

DELIVERY_PLAN = [
    {'models': ['Annabelle'], 'count': 1},
    {'models': ['Naomi'],     'count': 3},
    {'models': ['Silvia'],    'count': 1},
    {'models': ['Klonoa'],    'count': 2},
]

def log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def wait_for_server(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f'{BASE_URL}/login', timeout=3)
            if r.status_code in (200, 302):
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    return False

def run():
    # Clear log
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('')

    log('=== HookShot Delivery Run — Retry 7 failures ===')
    log(f'Target: 7 replacement videos (Annabelle x1, Naomi x3, Silvia x1, Klonoa x2)')

    # Start Flask app
    log('Starting app.py ...')
    app_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(app_dir, 'venv', 'Scripts', 'python.exe')
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable

    server = subprocess.Popen(
        [python_exe, 'app.py'],
        cwd=app_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log(f'Server PID: {server.pid}')

    log('Waiting for server to be ready ...')
    if not wait_for_server(timeout=30):
        log('ERROR: Server did not start within 30 seconds. Aborting.')
        server.terminate()
        return

    log('Server is up.')

    # Log in
    session = requests.Session()
    resp = session.post(
        f'{BASE_URL}/login',
        data={'username': 'todd', 'pin': '1981'},
        allow_redirects=True,
        timeout=15,
    )
    if 'Invalid' in resp.text:
        log('ERROR: Login failed. Aborting.')
        server.terminate()
        return
    log('Logged in as todd.')

    # Run delivery for each model group
    grand_total_uploaded = 0
    grand_total_errors   = 0

    for plan in DELIVERY_PLAN:
        models = plan['models']
        count  = plan['count']
        label  = ', '.join(models)
        log(f'--- Delivering {count} videos for: {label} ---')

        try:
            resp = session.post(
                f'{BASE_URL}/api/deliver',
                json={'models': models, 'count': count},
                timeout=7200,  # 2-hour timeout per batch
            )
            data = resp.json()
        except Exception as e:
            log(f'ERROR calling /api/deliver for {label}: {e}')
            continue

        for result in data.get('results', []):
            m        = result.get('model', '?')
            uploaded = result.get('uploaded', 0)
            errors   = result.get('errors', 0)
            skipped  = result.get('skipped', False)
            reason   = result.get('reason', '')
            details  = result.get('error_details', [])

            if skipped:
                log(f'  {m}: SKIPPED — {reason}')
            else:
                log(f'  {m}: {uploaded} uploaded, {errors} errors')
                for d in details:
                    log(f'    ! {d}')
            grand_total_uploaded += uploaded
            grand_total_errors   += errors

    log('=== DONE ===')
    log(f'Total uploaded: {grand_total_uploaded}')
    log(f'Total errors:   {grand_total_errors}')

    server.terminate()
    log('Server stopped.')

if __name__ == '__main__':
    run()
