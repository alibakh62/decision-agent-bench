# syntax=docker/dockerfile:1.7
FROM python:3.15.0rc3-slim-bookworm@sha256:ea93de1a70a03fffd10ad8cfde8f4ba969fe2658f0578af02855d1d32f49e6c2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN useradd --create-home --uid 10001 benchmark

COPY requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes --requirement requirements.lock

COPY pyproject.toml README.md LICENSE ./
COPY data ./data
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps .

USER benchmark
ENTRYPOINT ["decision-agent-bench"]
CMD ["verify-closed-loop-reference"]
