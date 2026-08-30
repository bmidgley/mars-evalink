"""
Test settings for Django tests
This file disables MQTT connections and other external services during testing
"""

from .settings import *

# Disable MQTT during tests
MQTT_ENABLED = False

# Use a test-specific database (env overrides for local runs; CI defaults match workflow)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.getenv('HOST', 'localhost'),
        'NAME': os.getenv('NAME', 'test_db'),
        'PORT': os.getenv('PORT', '5432'),
        'USER': os.getenv('DBUSER', 'postgres'),
        'PASSWORD': os.getenv('PASSWORD', 'postgres'),
        'OPTIONS': {'sslmode': os.getenv('SSLMODE', 'disable')},
    }
}

# Disable external services
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver']

# Use in-memory cache for tests
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Disable logging during tests
LOGGING_CONFIG = None
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['null'],
    },
}
