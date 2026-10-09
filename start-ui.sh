#!/usr/bin/env bash
# Start API server and React UI together
set -e
cd "$(dirname "$0")"

if [ ! -f .venv/bin/activate ]; then
  echo "Missing .venv. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
if [ ! -d ui/node_modules ]; then
  echo "Missing UI dependencies. Run: (cd ui && npm install)"
  exit 1
fi
[ -f .env ] || echo "Warning: no .env found; using defaults (run: cp env.template .env)"

source .venv/bin/activate

echo "Starting API on http://127.0.0.1:8000"
python -m uvicorn api.server:app --host 127.0.0.1 --port 8000 &
API_PID=$!

cleanup() {
  kill $API_PID 2>/dev/null || true
}
trap cleanup EXIT

sleep 1
echo "Starting UI on http://localhost:5173"
cd ui && npm run dev
