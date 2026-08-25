FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

FROM python:3.13-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid 10001 incidentlens \
    && useradd --uid 10001 --gid incidentlens --create-home incidentlens

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=incidentlens:incidentlens . .

USER incidentlens
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/ready', timeout=2)"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
