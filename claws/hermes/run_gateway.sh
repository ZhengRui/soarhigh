#!/usr/bin/env sh

set -eu

root_home="${HERMES_HOME:-/opt/data}"
profile_home="${root_home}/profiles/wxpost"

/opt/hermes/.venv/bin/python /opt/soarhigh/wxpost_profile/configure.py \
  --root-home "${root_home}" \
  --source-skill /opt/soarhigh/skills/soarhigh-wxpost-authoring \
  --source-soul /opt/soarhigh/wxpost_profile/SOUL.md

# The image reconciles persisted profile gateway state before this command is
# run. Stop any gateway it restored, then make the managed profile the sticky
# default so this container owns exactly one Feishu connection.
HERMES_HOME="${root_home}" /opt/hermes/.venv/bin/hermes profile use wxpost
HERMES_HOME="${root_home}" /opt/hermes/.venv/bin/hermes gateway stop --all

export HERMES_HOME="${root_home}"
export HERMES_PROFILE=wxpost

serve_pid=''
gateway_pid=''

stop_children() {
  trap - INT TERM EXIT
  if [ -n "${gateway_pid}" ]; then
    kill "${gateway_pid}" 2>/dev/null || true
  fi
  if [ -n "${serve_pid}" ]; then
    kill "${serve_pid}" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

trap stop_children INT TERM EXIT

hermes serve --isolated --host 127.0.0.1 --port 9119 &
serve_pid=$!

hermes gateway run &
gateway_pid=$!

while kill -0 "${serve_pid}" 2>/dev/null &&
  kill -0 "${gateway_pid}" 2>/dev/null; do
  sleep 1
done

if ! kill -0 "${serve_pid}" 2>/dev/null; then
  wait "${serve_pid}"
else
  wait "${gateway_pid}"
fi
