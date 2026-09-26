FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1 \
	VIRTUAL_ENV=/opt/venv \
	PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
	&& apt-get install --no-install-recommends -y build-essential \
	&& python -m venv "$VIRTUAL_ENV" \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt pyproject.toml ./
RUN sed '/^-e file:/d' requirements.txt > requirements-docker.txt \
	&& pip install --upgrade pip \
	&& pip install -r requirements-docker.txt \
	&& pip install gunicorn

COPY . .
RUN pip install --no-deps .

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	DJANGO_DEBUG=0 \
	DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost \
	VIRTUAL_ENV=/opt/venv \
	PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --shell /usr/sbin/nologin predicta

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=predicta:predicta . .

RUN mkdir -p /app/data/web /app/outputs/web/runs \
	&& chown -R predicta:predicta /app

USER predicta
EXPOSE 5000

RUN python manage.py collectstatic --noinput \
	&& python manage.py check

CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 web.predicta_web.wsgi:application"]