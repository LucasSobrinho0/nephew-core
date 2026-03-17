from django import forms

from common.forms import BootstrapFormMixin


class CompanyForm(BootstrapFormMixin, forms.Form):
    name = forms.CharField(
        label='Empresa',
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Nome da empresa'}),
    )
    website = forms.URLField(
        label='Website',
        required=False,
        widget=forms.URLInput(attrs={'placeholder': 'https://empresa.com'}),
    )
    phone = forms.CharField(
        label='Telefone',
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={'placeholder': '+55 11 4000-0000'}),
    )

    def clean_name(self):
        return self.cleaned_data['name'].strip()

    def clean_website(self):
        return self.cleaned_data.get('website', '').strip()

    def clean_phone(self):
        return self.cleaned_data.get('phone', '').strip()


class CompanyCreateForm(CompanyForm):
    pass


class CompanyUpdateForm(CompanyForm):
    pass
