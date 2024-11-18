FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONFAULTHANDLER=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y \
    cron \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir /app/data /app/logs

COPY . /app/

COPY scripts/update_feeds.sh /app/scripts/update_feeds.sh
COPY scripts/entrypoint.sh /app/scripts/entrypoint.sh

RUN chmod +x /app/scripts/update_feeds.sh /app/scripts/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
