# -------- BUILDER --------
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    cargo \
    rustc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --target=/install -r requirements.txt && \
    find /install -type d -name "__pycache__" -exec rm -rf {} +


# -------- RUNTIME --------
FROM python:3.11-slim-bookworm AS runtime

ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libgpiod2 && \
    if [ "$TARGETARCH" = "arm64" ]; then \
    apt-get install -y --no-install-recommends python3-rpi.gpio || true; \
    fi && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local/lib/python3.11/site-packages
COPY app/ /app/app/

CMD ["python", "-u", "-m", "app.main"]


# -------- DEV --------
FROM runtime AS dev