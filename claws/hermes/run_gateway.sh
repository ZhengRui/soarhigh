#!/usr/bin/env sh

set -eu

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

hermes serve --host 127.0.0.1 --port 9119 &
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
