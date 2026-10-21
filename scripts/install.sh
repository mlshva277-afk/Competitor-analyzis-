#!/usr/bin/env bash
set -euo pipefail
cd /workspace/Competitor-analyzis-
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ required"'
if [ ! -x /workspace/isi-venv/bin/python ]; then
  python3 -m venv /workspace/isi-venv
fi
/workspace/isi-venv/bin/python -m pip install --cache-dir /tmp/isi-pip-cache -r requirements.lock
/workspace/isi-venv/bin/python -m pip check
