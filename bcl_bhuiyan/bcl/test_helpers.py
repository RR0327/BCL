"""MFA-aware Django test helper: establish an actual confirmed OTP device in test session."""
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

def force_verified_staff(client, user):
    """Use only in tests that exercise post-MFA permissions; never bypass production middleware."""
    if not user.is_staff:
        raise ValueError('Only staff accounts can use this helper')
    client.force_login(user)
    device, _ = TOTPDevice.objects.get_or_create(user=user, name='test-primary', defaults={'confirmed': True})
    if not device.confirmed:
        device.confirmed = True
        device.save(update_fields=['confirmed'])
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
