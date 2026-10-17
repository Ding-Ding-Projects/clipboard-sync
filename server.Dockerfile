# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY server-requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r server-requirements.txt; else pip install --no-cache-dir -r server-requirements.txt; fi \
    && useradd --uid 10001 --create-home relay
COPY --chown=relay:relay sync_server ./sync_server
USER relay
EXPOSE 8787
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3)" || exit 1
CMD ["python", "-m", "sync_server"]
