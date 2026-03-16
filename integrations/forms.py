from django import forms

from common.forms import BootstrapFormMixin
from integrations.constants import REVEAL_CONFIRMATION_WORD


class AppInstallForm(BootstrapFormMixin, forms.Form):
    app_public_id = forms.UUIDField(widget=forms.HiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class ApiKeySaveForm(BootstrapFormMixin, forms.Form):
    installation_public_id = forms.UUIDField(widget=forms.HiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())
    api_key = forms.CharField(
        label='Chave de API',
        strip=True,
        widget=forms.PasswordInput(
            attrs={
                'placeholder': 'Cole a chave de API do aplicativo instalado',
                'autocomplete': 'off',
            }
        ),
    )

    def clean_api_key(self):
        api_key = self.cleaned_data['api_key'].strip()
        if not api_key:
            raise forms.ValidationError('Informe uma chave de API valida.')
        return api_key


class ApiKeyRevealForm(BootstrapFormMixin, forms.Form):
    confirmation_word = forms.CharField(
        label='Palavra de confirmacao',
        max_length=32,
        widget=forms.TextInput(
            attrs={
                'placeholder': REVEAL_CONFIRMATION_WORD,
                'autocomplete': 'off',
            }
        ),
    )
