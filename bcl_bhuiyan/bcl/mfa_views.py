"""Staff TOTP enrollment and second-factor verification."""
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

def _staff(request):
    return request.user.is_staff or request.user.is_superuser

@login_required
@require_http_methods(['GET', 'POST'])
def mfa_setup(request):
    if not _staff(request):
        return HttpResponseForbidden('Staff only')
    if request.user.is_verified():
        return redirect('bcl:dashboard')
    if TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
        return redirect('bcl:mfa_verify')
    device, _ = TOTPDevice.objects.get_or_create(user=request.user, name='primary', confirmed=False)
    error = None
    if request.method == 'POST':
        if device.verify_token(request.POST.get('token', '').strip()):
            device.confirmed = True
            device.save(update_fields=['confirmed'])
            otp_login(request, device)
            request.session.cycle_key()
            return redirect('bcl:dashboard')
        error = 'Invalid verification code.'
    return render(request, 'security/mfa.html', {'enrolling': True, 'secret': device.config_url, 'error': error})

@login_required
@require_http_methods(['GET', 'POST'])
def mfa_verify(request):
    if not _staff(request):
        return HttpResponseForbidden('Staff only')
    if request.user.is_verified():
        return redirect('bcl:dashboard')
    devices = TOTPDevice.objects.filter(user=request.user, confirmed=True)
    if not devices.exists():
        return redirect('bcl:mfa_setup')
    error = None
    if request.method == 'POST':
        token = request.POST.get('token', '').strip()
        for device in devices:
            if device.verify_token(token):
                otp_login(request, device)
                request.session.cycle_key()
                return redirect('bcl:dashboard')
        error = 'Invalid verification code.'
    return render(request, 'security/mfa.html', {'enrolling': False, 'error': error})
