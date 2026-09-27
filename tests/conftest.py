import os

import django
from django.test.utils import setup_test_environment


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web.predicta_web.settings')
os.environ.setdefault('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,testserver')
django.setup()
setup_test_environment()