"""Cross-platform local launcher. Uses only the Python standard library."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import platform
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
ENV = ROOT / '.venv'
PYTHON = ENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
LOG = ROOT / 'launch.log'


def run_logged(command):
    with LOG.open('a', encoding='utf-8') as log:
        log.write('\n$ ' + ' '.join(map(str, command)) + '\n')
        log.flush()
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}). See {LOG.name}.')


def main():
    parser = argparse.ArgumentParser(description='Prepare and launch Invest Social Intelligence')
    parser.add_argument('--check', action='store_true', help='Install and verify dependencies without starting the server')
    parser.add_argument('--diagnose', action='store_true', help='Print system information without installing anything')
    args = parser.parse_args()
    if args.diagnose:
        print('System:', platform.system(), platform.machine())
        print('Python:', platform.python_version())
        print('Python 3.12+:', sys.version_info >= (3, 12))
        print('venv support:', importlib.util.find_spec('venv') is not None)
        print('Project files:', all((ROOT / p).is_file() for p in ['app.py', 'requirements.txt', 'data/accounts.json']))
        print('Local environment:', PYTHON.is_file())
        return 0
    if sys.version_info < (3, 12):
        print('Python 3.12 or newer is required. Install Python from https://www.python.org/downloads/')
        return 1
    try:
        with LOG.open('w', encoding='utf-8') as log:
            log.write(f'{platform.system()} {platform.machine()}, Python {platform.python_version()}\n')
        if not PYTHON.is_file():
            print('Preparing local Python environment...')
            venv.EnvBuilder(with_pip=True).create(ENV)
        requirements = ROOT / 'requirements.txt'
        fingerprint = hashlib.sha256(requirements.read_bytes() + sys.version.encode()).hexdigest()
        marker = ENV / '.isi-dependencies'
        if not marker.is_file() or marker.read_text() != fingerprint:
            print('Installing dependencies. First launch may take several minutes. Details: launch.log')
            run_logged([str(PYTHON), '-m', 'pip', 'install', '-r', str(requirements)])
            run_logged([str(PYTHON), '-m', 'pip', 'check'])
            run_logged([str(PYTHON), '-c', 'import streamlit, sqlalchemy, pandas, plotly, openpyxl'])
            marker.write_text(fingerprint)
        if args.check:
            run_logged([str(PYTHON), '-c', 'import streamlit, sqlalchemy, pandas, plotly, openpyxl'])
            print('Dependencies verified. Ready to launch.')
            return 0
        print('Opening the application. Keep this window open; Ctrl+C stops the server.')
        print('If the browser does not open, enter http://localhost:8501 in your browser.')
        return subprocess.call([str(PYTHON), '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
                                '--server.address=127.0.0.1', '--server.port=8501',
                                '--server.headless=false', '--browser.gatherUsageStats=false'], cwd=ROOT)
    except KeyboardInterrupt:
        return 0
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        with LOG.open('a', encoding='utf-8') as log:
            log.write('\n' + str(exc) + '\n')
        print('Setup failed. Please send the error from launch.log. Do not send passwords or API keys.')
        print(str(exc))
        return 1


if __name__ == '__main__':
    sys.exit(main())
