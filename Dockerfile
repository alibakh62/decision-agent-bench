# syntax=docker/dockerfile:1.7
FROM python:3.14.6-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30

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
CMD ["verify-reference"]
