FROM python:3.12-slim

RUN useradd --create-home --uid 10001 gateway
WORKDIR /opt/soarhigh
COPY wechat_gateway /opt/soarhigh/wechat_gateway

USER gateway
EXPOSE 8790
CMD ["python", "-m", "wechat_gateway.http_server", "--host", "0.0.0.0", "--port", "8790"]
