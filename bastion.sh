#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -f .venv/bin/activate ] || python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -q 2>/dev/null
[ -f .env ] && set -a && source .env && set +a
export PYTHONPATH="$(pwd)"
python3 main.py
