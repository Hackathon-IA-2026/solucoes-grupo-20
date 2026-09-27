from pathlib import Path
import os

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'predicta-local-mvp-change-me')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
configured_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
ALLOWED_HOSTS = sorted({
    host.strip()
    for host in [*configured_hosts, render_host, 'predic-atano-g34dtbz0dtaz-34196584.us-west-2.elb.amazonaws.com','hackathon-ia-2026.onrender.com', '0.0.0.0']
    if host.strip()
})

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'drf_spectacular',
    'web.studio',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'web.predicta_web.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'web.studio.context_processors.project_context',
    ]},
}]
WSGI_APPLICATION = 'web.predicta_web.wsgi.application'
ASGI_APPLICATION = 'web.predicta_web.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'data' / 'web' / 'predicta_web.sqlite3',
    }
}

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

PREDICTA_PROJECT_ROOT = BASE_DIR
PREDICTA_ALLOW_PIPELINE_EXECUTION = os.environ.get('PREDICTA_ALLOW_PIPELINE_EXECUTION', '1') == '1'
PREDICTA_RUN_LOG_DIR = BASE_DIR / 'outputs' / 'web' / 'runs'
PREDICTA_S3_CACHE_ROOT = BASE_DIR / 'data' / 'web' / 's3_cache'
PREDICTA_RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / 'data' / 'web').mkdir(parents=True, exist_ok=True)

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Predicta API',
    'DESCRIPTION': 'API REST para a simulacao de tarifa dinamica do Predicta Studio.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'TAGS': [
        {'name': 'Simulacao', 'description': 'Executa a mesma simulacao disponivel na pagina Produto.'},
        {'name': 'Catalogo', 'description': 'Areas de concessao e perfis tarifarios.'},
    ],
}

# Frontend Next.js (predicta-frontend, publicado na Vercel) chama a API a partir de outra origem.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        'DJANGO_CORS_ALLOWED_ORIGINS',
        'http://localhost:3000,http://127.0.0.1:3000,https://frontend-web-hackathon-ia-2026.vercel.app',
    ).split(',')
    if origin.strip()
]
# Previews da Vercel ganham um subdomínio novo a cada push, então não cabem na lista fixa.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^https://[a-zA-Z0-9-]+\.vercel\.app$',
]
CORS_URLS_REGEX = r'^/api/.*$'
CSRF_TRUSTED_ORIGINS = [*CORS_ALLOWED_ORIGINS, 'https://*.vercel.app']
