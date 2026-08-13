#!/bin/sh
set -eu

export HOME="${HOME:-/opt/data}"
export HERMES_HOME="${HERMES_HOME:-/opt/data/profiles/wxpost}"
export PYTHONPATH="/opt/soarhigh${PYTHONPATH:+:${PYTHONPATH}}"

exec /opt/hermes/.venv/bin/python \
  -m wxpost_controller.http_server \
  --host 0.0.0.0 \
  --port 8787
