from django.conf import settings


def platform_branding(request):
    return {
        "platform_name": getattr(settings, "APP_NAME", "BCL_Bhuiyan"),
    }
