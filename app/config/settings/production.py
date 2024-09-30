from celery.schedules import crontab
from decouple import config
from google.auth.environment_vars import AWS_DEFAULT_REGION

from .base import *


# Celery
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://redis:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://redis:6379/0')

CELERY_BEAT_SCHEDULE = {
    'send_self_checkin_reminders': {
        'task': 'celery_tasks.tasks.send_self_checkin_reminders',
        'schedule': crontab(hour="8", minute="0"),  # Every day at 8 AM
    },
}
CELERY_TIMEZONE = 'Europe/Rome'

# AWS S3
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com'
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_DEFAULT_ACL = None
# AWS_QUERYSTRING_AUTH = False

# Media and static files
MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, '../../vol/', 'staticfiles')

STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3.S3Storage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
