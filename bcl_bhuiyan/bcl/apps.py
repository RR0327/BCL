from django.apps import AppConfig

class BclConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bcl'

    def ready(self):
        from . import signals  # noqa: F401
