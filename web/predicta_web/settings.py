from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'predicta-local-mvp-change-me')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
configured_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
ALLOWED_HOSTS = sorted({
    host.strip()
    for host in [*configured_hosts, render_host, 'hackathon-ia-2026.onrender.com']
    if host.strip()
})

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'web.studio',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
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
