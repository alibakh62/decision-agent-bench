# syntax=docker/dockerfile:1.7
FROM python:3.15.0rc1-slim-bookworm@sha256:6e3246a49a188d62360dcd248aafbc1834db4d86eff6b28f40ba13269c1bcc57

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
