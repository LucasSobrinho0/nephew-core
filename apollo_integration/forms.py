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


class ApolloPeopleSearchForm(BootstrapFormMixin, forms.Form):
    search = forms.CharField(required=False, widget=forms.HiddenInput(), initial='1')
    company_public_id = forms.ChoiceField(
        label='Empresa do CRM',
        required=False,
        choices=(),
        widget=forms.Select(),
    )
    q_organization_name = forms.CharField(
        label='Nome da empresa',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Buscar por nome da empresa'}),
    )
    q_organization_domains = forms.CharField(
        label='Dominios da empresa',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'empresa.com, outra.com'}),
    )
    person_titles = forms.CharField(
        label='Cargos',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'financial supervisor, it manager'}),
    )
    q_keywords = forms.CharField(
        label='Nome ou palavra-chave',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Joao, Maria, FP&A'}),
    )
    contact_email_status = forms.ChoiceField(
        label='Status do email',
        required=False,
        choices=(
            ('', 'Qualquer status'),
            ('verified', 'Somente email verificado'),
        ),
    )
    page = forms.IntegerField(required=False, min_value=1, initial=1, widget=forms.HiddenInput())
    per_page = forms.ChoiceField(
        label='Resultados por pagina',
        required=False,
        choices=(('10', '10'), ('25', '25'), ('50', '50'), ('100', '100')),
        initial='25',
    )

    def __init__(self, *args, company_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_public_id'].choices = [('', 'Qualquer empresa')] + list(company_choices)

    def clean_company_public_id(self):
        return (self.cleaned_data.get('company_public_id') or '').strip()

    def clean_q_organization_name(self):
        return (self.cleaned_data.get('q_organization_name') or '').strip()

    def clean_q_organization_domains(self):
        return self._split_csv_values(self.cleaned_data.get('q_organization_domains', ''))

    def clean_person_titles(self):
        return self._split_csv_values(self.cleaned_data.get('person_titles', ''))

    def clean_q_keywords(self):
        return (self.cleaned_data.get('q_keywords') or '').strip()

    def clean_per_page(self):
        return int(self.cleaned_data.get('per_page') or 25)

    @staticmethod
    def _split_csv_values(value):
        normalized = (value or '').replace(';', ',').replace('\n', ',').replace('\r', ',')
        return [item.strip() for item in normalized.split(',') if item.strip()]


class ApolloBulkRemotePersonImportForm(BootstrapFormMixin, forms.Form):
    apollo_person_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())
    current_query = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, person_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['apollo_person_ids'].choices = person_choices

    def clean_apollo_person_ids(self):
        apollo_person_ids = self.cleaned_data.get('apollo_person_ids') or []
        if not apollo_person_ids:
            raise forms.ValidationError('Selecione pelo menos uma pessoa remota para salvar.')
        return apollo_person_ids


class ApolloPeopleEnrichmentForm(BootstrapFormMixin, forms.Form):
    person_public_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())
    fetch_phone = forms.BooleanField(
        required=False,
        initial=False,
        label='Pegar telefone',
        help_text='Ativa o webhook do Apollo para tentar revelar telefone por callback HTTPS.',
    )

    def __init__(self, *args, person_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person_public_ids'].choices = person_choices

    def clean_person_public_ids(self):
        person_public_ids = self.cleaned_data.get('person_public_ids') or []
        if not person_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma pessoa sincronizada com o Apollo para enriquecer.')
        return person_public_ids
