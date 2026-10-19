"""Metadata-only authentication audit events; no passwords or request bodies."""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from .privacy import audit

@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    audit('auth.login', actor=user)

@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user and user.pk:
        audit('auth.logout', actor=user)

@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    audit('auth.login_failed', outcome='denied')
