ARG HERMES_IMAGE=nousresearch/hermes-agent:latest
FROM ${HERMES_IMAGE}

COPY wxpost_controller/requirements.txt /tmp/wxpost-controller-requirements.txt
RUN uv pip install \
    --no-cache \
    --python /opt/hermes/.venv/bin/python \
    --requirement /tmp/wxpost-controller-requirements.txt
