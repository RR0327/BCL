"""Require a verified second factor for authenticated staff on every application route."""
from django.shortcuts import redirect
from django.urls import reverse

class StaffMFAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            allowed = (reverse('bcl:mfa_setup'), reverse('bcl:mfa_verify'), reverse('bcl:logout'))
            if not request.path.startswith('/static/') and request.path not in allowed:
                if not user.is_verified():
                    from django_otp.plugins.otp_totp.models import TOTPDevice
                    enrolled = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
                    return redirect('bcl:mfa_verify' if enrolled else 'bcl:mfa_setup')
        return self.get_response(request)
