FROM python:3.11

ENV PIP_DISABLE_PIP_VERSION_CHECK 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

ENV STATIC_ROOT /data/static/
ENV MEDIA_ROOT /data/media/
ENV LOG_ROOT /data/log/

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-dev build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -rf /tmp/requirements.txt

# Create a non-root user for celery
RUN adduser --disabled-password --gecos '' celeryuser \
    && chown -R celeryuser /app \
    && chown -R celeryuser /celery_tasks

WORKDIR /app
COPY ./scripts /scripts/
COPY ./app .
COPY ./templates /templates/
COPY ./initial_data /app/initial_data/

ENTRYPOINT ["/scripts/docker/wait-for-it.sh", "database:5432" , "-s", "--"]
CMD ["/scripts/docker/starter.sh"]
