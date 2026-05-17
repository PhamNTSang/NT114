FROM python:3.14.4-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

RUN apk add --no-cache g++ linux-headers

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14.4-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENABLE_PROFILER=1

RUN apk add --no-cache libstdc++ \
    && addgroup -S appgroup \
    && adduser -S -G appgroup appuser

WORKDIR /email_server

COPY --from=builder /install /usr/local
COPY --chown=appuser:appgroup . .

USER appuser
EXPOSE 8080
ENTRYPOINT ["python", "email_server.py"]
