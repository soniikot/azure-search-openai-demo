#!/bin/sh
# Verify Azure Search index contents and configuration

. ./scripts/load_python_env.sh 2>/dev/null || true

./.venv/bin/python scripts/verify_index.py "$@"
