# Django API served by gunicorn. Build from the repository root:
#   docker compose -f deploy/docker-compose.prod.yml build
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PRIVATE_MEDIA_ROOT=/data/private_media STATIC_ROOT=/app/staticfiles

RUN useradd --create-home --uid 10001 app \
 && mkdir -p /data/private_media \
 && chown app:app /data/private_media
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh \
 && DJANGO_DEBUG=false DJANGO_SECRET_KEY=build-time-collectstatic-only DJANGO_ALLOWED_HOSTS=build.invalid \
    python manage.py collectstatic --noinput

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request as u; h=os.environ.get('DJANGO_ALLOWED_HOSTS','localhost').split(',')[0].strip(); r=u.Request('http://127.0.0.1:8000/api/v1/health/', headers={'Host': h}); sys.exit(0 if u.urlopen(r, timeout=4).status == 200 else 1)"]
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", \
     "--access-logfile", "-", "--forwarded-allow-ips", "*"]
