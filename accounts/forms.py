from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm

from accounts.models import User
from common.encryption import build_email_lookup, normalize_email_address
from common.forms import BootstrapFormMixin


class LoginForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(
        label='E-mail',
        widget=forms.EmailInput(
            attrs={
                'placeholder': 'name@company.com',
                'autocomplete': 'email',
            }
        )
    )
    password = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(
            attrs={
                'placeholder': 'Sua senha',
                'autocomplete': 'current-password',
            }
        )
    )
    remember_me = forms.BooleanField(required=False, label='Manter conectado')

    error_messages = {
        'invalid_login': 'E-mail ou senha invalidos.',
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self._user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            self._user = authenticate(self.request, email=email, password=password)
            if self._user is None:
                raise forms.ValidationError(self.error_messages['invalid_login'])

        return cleaned_data

    def get_user(self):
        return self._user


class RegistrationForm(BootstrapFormMixin, UserCreationForm):
    full_name = forms.CharField(
        label='Nome completo',
        max_length=255,
        widget=forms.TextInput(
            attrs={
                'placeholder': 'Seu nome completo',
                'autocomplete': 'name',
            }
        ),
    )
    email = forms.EmailField(
        label='E-mail',
        widget=forms.EmailInput(
            attrs={
                'placeholder': 'name@company.com',
                'autocomplete': 'email',
            }
        )
    )
    password1 = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(
            attrs={
                'placeholder': 'Crie uma senha forte',
                'autocomplete': 'new-password',
            }
        ),
    )
    password2 = forms.CharField(
        label='Confirmar senha',
        widget=forms.PasswordInput(
            attrs={
                'placeholder': 'Repita sua senha',
                'autocomplete': 'new-password',
            }
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('full_name', 'email')

    def clean_email(self):
        email = normalize_email_address(self.cleaned_data['email'])
        if User.objects.filter(email_lookup=build_email_lookup(email)).exists():
            raise forms.ValidationError('Ja existe uma conta com este e-mail.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.full_name = self.cleaned_data['full_name']
        user.email = self.cleaned_data['email']

        if commit:
            user.save()
        return user
