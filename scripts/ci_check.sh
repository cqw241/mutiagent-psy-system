#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

"$PYTHON_BIN" -m pytest -q --tb=short
"$PYTHON_BIN" scripts/run_risk_eval.py --mode mock --output-json /tmp/risk_eval_mock.json

pnpm --dir frontend run test:node
pnpm --dir frontend run lint
pnpm --dir frontend run build
