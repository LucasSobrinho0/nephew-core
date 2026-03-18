from django import forms

from apollo_integration.constants import APOLLO_EMPLOYEE_RANGE_CHOICES
from common.forms import BootstrapFormMixin


class ApolloLocalCompanyListForm(BootstrapFormMixin, forms.Form):
    load_local = forms.CharField(required=False, widget=forms.HiddenInput(), initial='1')


class ApolloOrganizationSearchForm(BootstrapFormMixin, forms.Form):
    search = forms.CharField(required=False, widget=forms.HiddenInput(), initial='1')
    q_organization_name = forms.CharField(
        label='Nome da empresa',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Buscar por nome'}),
    )
    q_organization_domains = forms.CharField(
        label='Dominios',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'empresa.com, outra.com'}),
    )
    organization_locations = forms.CharField(
        label='Paises ou regioes',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Brazil, Mexico'}),
    )
    organization_industries = forms.CharField(
        label='Segmentos',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'environmental services, logistics'}),
    )
    organization_num_employees_ranges = forms.MultipleChoiceField(
        label='Faixas de funcionarios',
        required=False,
        choices=APOLLO_EMPLOYEE_RANGE_CHOICES,
        widget=forms.SelectMultiple(),
    )
    page = forms.IntegerField(required=False, min_value=1, initial=1, widget=forms.HiddenInput())
    per_page = forms.ChoiceField(
        label='Resultados por pagina',
        required=False,
        choices=(('10', '10'), ('25', '25'), ('50', '50'), ('100', '100')),
        initial='25',
    )

    def clean_q_organization_name(self):
        return (self.cleaned_data.get('q_organization_name') or '').strip()

    def clean_q_organization_domains(self):
        return self._split_csv_values(self.cleaned_data.get('q_organization_domains', ''))

    def clean_organization_locations(self):
        return self._split_csv_values(self.cleaned_data.get('organization_locations', ''))

    def clean_organization_industries(self):
        return self._split_csv_values(self.cleaned_data.get('organization_industries', ''))

    def clean_per_page(self):
        return int(self.cleaned_data.get('per_page') or 25)

    @staticmethod
    def _split_csv_values(value):
        normalized = (value or '').replace(';', ',').replace('\n', ',').replace('\r', ',')
        return [item.strip() for item in normalized.split(',') if item.strip()]


class ApolloBulkRemoteCompanyImportForm(BootstrapFormMixin, forms.Form):
    apollo_company_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())
    current_query = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, company_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['apollo_company_ids'].choices = company_choices

    def clean_apollo_company_ids(self):
        apollo_company_ids = self.cleaned_data.get('apollo_company_ids') or []
        if not apollo_company_ids:
            raise forms.ValidationError('Selecione pelo menos uma empresa remota para salvar.')
        return apollo_company_ids


class ApolloBulkCompanyHubSpotSyncForm(BootstrapFormMixin, forms.Form):
    company_public_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())

    def __init__(self, *args, company_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_public_ids'].choices = company_choices

    def clean_company_public_ids(self):
        company_public_ids = self.cleaned_data.get('company_public_ids') or []
        if not company_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma empresa para sincronizar com o HubSpot.')
        return company_public_ids
