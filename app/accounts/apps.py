"""
This file is used to configure the app name for the accounts app.
"""
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """
    Configuration for the accounts app
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
