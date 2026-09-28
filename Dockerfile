FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir .

RUN addgroup --system --gid 10001 simpleconvbot \
    && adduser --system --uid 10001 --ingroup simpleconvbot --home /app simpleconvbot \
    && mkdir -p /app/var/jobs \
    && chown -R simpleconvbot:simpleconvbot /app

USER simpleconvbot

CMD ["python", "-m", "simpleconvbot"]
