# syntax=docker/dockerfile:1.7
FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d

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
