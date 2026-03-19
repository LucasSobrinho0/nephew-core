from django import forms

from common.documents import normalize_cnpj
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
    cnpj = forms.CharField(
        label='CNPJ',
        required=False,
        max_length=18,
        widget=forms.TextInput(attrs={'placeholder': 'Somente numeros'}),
    )
    phone = forms.CharField(
        label='Telefone',
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={'placeholder': '+55 11 4000-0000'}),
    )
    email = forms.EmailField(
        label='Email',
        required=False,
        max_length=254,
        widget=forms.EmailInput(attrs={'placeholder': 'contato@empresa.com'}),
    )
    segment = forms.CharField(
        label='Segmento',
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Logistics, SaaS, Retail...'}),
    )
    employee_count = forms.IntegerField(
        label='Quantidade de funcionarios',
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'placeholder': '120'}),
    )
    hubspot_company_id = forms.CharField(
        label='ID da empresa no HubSpot',
        required=False,
        max_length=128,
        widget=forms.TextInput(attrs={'placeholder': 'Opcional'}),
    )
    apollo_company_id = forms.CharField(
        label='ID da empresa no Apollo',
        required=False,
        max_length=128,
        widget=forms.TextInput(attrs={'placeholder': 'Opcional'}),
    )

    def __init__(self, *args, show_hubspot_fields=False, show_apollo_fields=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not show_hubspot_fields:
            self.fields.pop('hubspot_company_id')
        if not show_apollo_fields:
            self.fields.pop('apollo_company_id')

    def clean_name(self):
        return self.cleaned_data['name'].strip()

    def clean_website(self):
        return self.cleaned_data.get('website', '').strip()

    def clean_cnpj(self):
        return normalize_cnpj(self.cleaned_data.get('cnpj', ''))

    def clean_phone(self):
        return self.cleaned_data.get('phone', '').strip()

    def clean_email(self):
        return self.cleaned_data.get('email', '').strip().lower()

    def clean_segment(self):
        return self.cleaned_data.get('segment', '').strip()

    def clean_hubspot_company_id(self):
        return self.cleaned_data.get('hubspot_company_id', '').strip()

    def clean_apollo_company_id(self):
        return self.cleaned_data.get('apollo_company_id', '').strip()


class CompanyCreateForm(CompanyForm):
    pass


class CompanyUpdateForm(CompanyForm):
    pass
