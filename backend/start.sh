#!/bin/bash
# Start the TariffShield FastAPI backend

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if it exists, else create it
if [ ! -d ".venv" ]; then
  echo "Creating virtualenv…"
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies…"
pip install -q -r requirements.txt
if [ -f "../scudo_claude_Hackathon/tariffpilot/requirements.txt" ]; then
  pip install -q -r ../scudo_claude_Hackathon/tariffpilot/requirements.txt
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
  if [ -f "../.env" ]; then
    export $(grep -v '^#' ../.env | xargs)
  fi
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "ERROR: ANTHROPIC_API_KEY not set. Export it or put it in .env at project root."
  exit 1
fi

echo ""
echo "  TariffShield API → http://localhost:8000"
echo "  Docs             → http://localhost:8000/docs"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
