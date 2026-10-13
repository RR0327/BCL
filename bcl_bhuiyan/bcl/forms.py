from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
)

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

        if len(password1) < 8:
            raise forms.ValidationError(
                "Password must be at least 8 characters long."
            )

        return password1


    def save(self, commit=True):
        user = super().save(commit=False)

        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()

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
