#!/bin/sh
# Generate Q&A profile data from documents
# Requires: .venv with dependencies
# Set BACKEND_URI or use --endpoint URL
# Script auto-loads from .azure/<env-name>/.env (BACKEND_URI) if present

. ./scripts/load_python_env.sh 2>/dev/null || true

./.venv/bin/python scripts/generate_qa_profile_data.py "$@"
