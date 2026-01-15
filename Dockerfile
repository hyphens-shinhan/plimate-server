# syntax=docker/dockerfile:1

FROM python:3.14.2-alpine3.23 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN apk add --no-cache \
    build-base \
    curl

RUN pip install --no-cache-dir "poetry==1.7.1"

RUN python -m venv /opt/.venv
ENV VIRTUAL_ENV=/opt/.venv
ENV PATH="/opt/.venv/bin:$PATH"

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main


FROM python:3.14.2-alpine3.23 AS runtime

WORKDIR /app

RUN addgroup -S app && adduser -S -G app -s /bin/false app

COPY --from=builder --chown=app:app /opt/.venv /opt/.venv
COPY --chown=app:app . .

USER app
ENV PATH="/opt/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
