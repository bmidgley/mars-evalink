# evalink Django app. Build from repo root: docker build -t evalink .
#
# Runs Gunicorn for the Django web app. The MQTT client thread is started
# from evalink/__init__.py at import time, so the same container also acts
# as the MQTT subscriber.
#
# Database env: HOST, NAME, PORT, DBUSER, PASSWORD, SSLMODE (see
# evalink/evalink/settings.py). HTTP listen port: WEB_PORT (default 8000).

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=evalink.settings

WORKDIR /app

# Build deps for pygraphviz/psycopg, plus runtime tools (postgresql-client
# is used by the entrypoint to wait for the database to be ready).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        graphviz \
        libgraphviz-dev \
        pkg-config \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt \
    && apt-get update \
    && apt-get purge -y --auto-remove build-essential libgraphviz-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY evalink/ /app/evalink/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /app/static /app/media

WORKDIR /app/evalink

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn"]
