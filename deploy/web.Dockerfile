# Caddy: HTTPS (automatic certificates), security headers, the React app and Django's static files.
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.13-slim AS static
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
RUN DJANGO_DEBUG=false DJANGO_SECRET_KEY=build-time-collectstatic-only DJANGO_ALLOWED_HOSTS=build.invalid \
    STATIC_ROOT=/static python manage.py collectstatic --noinput

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /src/dist /srv/app
COPY --from=static /static /srv/static
