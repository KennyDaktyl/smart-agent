FROM python:3.11-slim AS base

ARG TARGETARCH

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
    && \
    if [ "$TARGETARCH" = "arm" ] || [ "$TARGETARCH" = "arm64" ]; then \
        if apt-get install -y --no-install-recommends libgpiod2 python3-rpi.gpio; then \
            echo "Installed Raspberry Pi GPIO packages for $TARGETARCH"; \
        else \
            echo "GPIO apt packages not available for $TARGETARCH, continuing without them"; \
        fi; \
        if apt-get install -y --no-install-recommends cargo rustc; then \
            echo "Installed Rust toolchain for $TARGETARCH (pydantic-core build support)"; \
        else \
            echo "Rust apt packages not available for $TARGETARCH, continuing without them"; \
        fi; \
    else \
        echo "Skipping Raspberry Pi GPIO packages for $TARGETARCH"; \
    fi && \
    rm -rf /var/lib/apt/lists/*

FROM base AS deps

COPY requirements.txt .

RUN printf "maturin==1.5.1\n" > /tmp/pip-constraints.txt && \
    PIP_CONSTRAINT=/tmp/pip-constraints.txt pip install --upgrade pip && \
    PIP_CONSTRAINT=/tmp/pip-constraints.txt pip install -r requirements.txt

FROM base AS prod

COPY --from=deps /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=deps /usr/local/bin /usr/local/bin

COPY . .

CMD ["python", "-u", "-m", "app.main"]


FROM base AS dev

COPY --from=deps /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=deps /usr/local/bin /usr/local/bin

CMD ["python", "-u", "-m", "app.main"]
