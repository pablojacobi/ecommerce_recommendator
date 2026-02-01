"""Forms for accounts app."""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

User = get_user_model()


class RegisterForm(UserCreationForm):
    """User registration form."""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "placeholder": "Email",
                "autocomplete": "email",
            }
        ),
    )

    class Meta:
        """Form meta options."""

        model = User
        fields = ("username", "email", "password1", "password2")
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Username",
                    "autocomplete": "username",
                }
            ),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize form with styled widgets."""
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(
            {
                "class": "form-input",
                "placeholder": "Password",
                "autocomplete": "new-password",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                "class": "form-input",
                "placeholder": "Confirm Password",
                "autocomplete": "new-password",
            }
        )


class LoginForm(AuthenticationForm):
    """User login form."""

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Username",
                "autocomplete": "username",
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Password",
                "autocomplete": "current-password",
            }
        )
    )
