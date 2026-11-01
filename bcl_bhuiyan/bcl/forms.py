import re

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
)

from .models import CandidateProfile

User = get_user_model()


class CandidateRegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=150,
        required=True,
        label="First Name",
    )

    last_name = forms.CharField(
        max_length=150,
        required=True,
        label="Last Name",
    )

    email = forms.EmailField(
        required=True,
        label="Email Address",
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "username",
            "email",
            "password1",
            "password2",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists."
            )

        return email

    def clean_password1(self):
        password1 = self.cleaned_data.get("password1", "")

        errors = []

        if len(password1) < 8:
            errors.append(
                "Password must be at least 8 characters long."
            )

        if not re.search(r'[A-Z]', password1):
            errors.append(
                "Password must contain at least one uppercase letter (A-Z)."
            )

        if not re.search(r'[a-z]', password1):
            errors.append(
                "Password must contain at least one lowercase letter (a-z)."
            )

        if not re.search(r'[0-9]', password1):
            errors.append(
                "Password must contain at least one number (0-9)."
            )

        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-\+\=\[\]\\\/~`]', password1):
            errors.append(
                "Password must contain at least one special character "
                "(@, #, !, etc.)."
            )

        if errors:
            raise forms.ValidationError(errors)

        return password1

    def save(self, commit=True):
        user = super().save(commit=False)

        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.is_active = False  # Keep account inactive until approved by an administrator

        if commit:
            user.save()
            CandidateProfile.objects.create(
                user=user,
                status=CandidateProfile.ApprovalStatus.PENDING,
            )

        return user


class CandidateLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username",
        max_length=150,
    )

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
    )

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username is not None and password:
            self.user_cache = authenticate(
                self.request, username=username, password=password
            )
            if self.user_cache is None:
                user_obj = User.objects.filter(username__iexact=username).first()
                if user_obj and user_obj.check_password(password):
                    profile = getattr(user_obj, "candidate_profile", None)
                    if profile:
                        if profile.status == CandidateProfile.ApprovalStatus.PENDING:
                            raise forms.ValidationError(
                                "Your account is pending administrator approval. "
                                "You will be able to log in once an admin approves your registration."
                            )
                        elif profile.status == CandidateProfile.ApprovalStatus.REJECTED:
                            reason_msg = f" Reason: {profile.rejection_reason}" if profile.rejection_reason else ""
                            raise forms.ValidationError(
                                f"Your registration request was rejected by an administrator.{reason_msg}"
                            )
                    if not user_obj.is_active:
                        raise forms.ValidationError(
                            "This account is inactive. Please contact the administrator."
                        )
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data
