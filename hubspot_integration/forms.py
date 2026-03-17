from django import forms

from common.forms import BootstrapFormMixin
from companies.forms import CompanyCreateForm


class HubSpotRemoteListForm(BootstrapFormMixin, forms.Form):
    load = forms.CharField(required=False, widget=forms.HiddenInput(), initial='1')


class HubSpotCompanySyncForm(BootstrapFormMixin, forms.Form):
    company_public_id = forms.UUIDField(widget=forms.HiddenInput())


class HubSpotPersonSyncForm(BootstrapFormMixin, forms.Form):
    person_public_id = forms.UUIDField(widget=forms.HiddenInput())


class HubSpotBulkCompanySyncForm(BootstrapFormMixin, forms.Form):
    company_public_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())

    def __init__(self, *args, company_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_public_ids'].choices = company_choices

    def clean_company_public_ids(self):
        company_public_ids = self.cleaned_data.get('company_public_ids') or []
        if not company_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma empresa para sincronizar.')
        return company_public_ids


class HubSpotBulkPersonSyncForm(BootstrapFormMixin, forms.Form):
    person_public_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())

    def __init__(self, *args, person_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person_public_ids'].choices = person_choices

    def clean_person_public_ids(self):
        person_public_ids = self.cleaned_data.get('person_public_ids') or []
        if not person_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma pessoa para sincronizar.')
        return person_public_ids


class HubSpotPipelineRefreshForm(BootstrapFormMixin, forms.Form):
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class HubSpotDealCreateForm(BootstrapFormMixin, forms.Form):
    company_public_id = forms.ChoiceField(label='Empresa', choices=())
    pipeline_public_id = forms.ChoiceField(label='Pipeline', choices=())
    deal_name = forms.CharField(
        label='Nome do deal',
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Nome do deal'}),
    )
    amount = forms.CharField(
        label='Valor',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '15000'}),
    )

    def __init__(self, *args, company_choices=(), pipeline_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_public_id'].choices = company_choices
        self.fields['pipeline_public_id'].choices = pipeline_choices

    def clean_deal_name(self):
        return self.cleaned_data['deal_name'].strip()

    def clean_amount(self):
        return self.cleaned_data.get('amount', '').strip()


class HubSpotRemoteCompanyImportForm(BootstrapFormMixin, forms.Form):
    hubspot_company_id = forms.CharField(widget=forms.HiddenInput())
    name = forms.CharField(widget=forms.HiddenInput())
    website = forms.CharField(required=False, widget=forms.HiddenInput())
    phone = forms.CharField(required=False, widget=forms.HiddenInput())


class HubSpotBulkRemoteCompanyImportForm(BootstrapFormMixin, forms.Form):
    hubspot_company_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())

    def __init__(self, *args, company_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hubspot_company_ids'].choices = company_choices

    def clean_hubspot_company_ids(self):
        hubspot_company_ids = self.cleaned_data.get('hubspot_company_ids') or []
        if not hubspot_company_ids:
            raise forms.ValidationError('Selecione pelo menos uma empresa remota para salvar.')
        return hubspot_company_ids


class HubSpotRemoteContactImportForm(BootstrapFormMixin, forms.Form):
    hubspot_contact_id = forms.CharField(widget=forms.HiddenInput())
    first_name = forms.CharField(required=False, widget=forms.HiddenInput())
    last_name = forms.CharField(required=False, widget=forms.HiddenInput())
    email = forms.CharField(required=False, widget=forms.HiddenInput())
    phone = forms.CharField(required=False, widget=forms.HiddenInput())
    company_name = forms.CharField(required=False, widget=forms.HiddenInput())
    company_hubspot_id = forms.CharField(required=False, widget=forms.HiddenInput())


class HubSpotBulkRemoteContactImportForm(BootstrapFormMixin, forms.Form):
    hubspot_contact_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())

    def __init__(self, *args, contact_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hubspot_contact_ids'].choices = contact_choices

    def clean_hubspot_contact_ids(self):
        hubspot_contact_ids = self.cleaned_data.get('hubspot_contact_ids') or []
        if not hubspot_contact_ids:
            raise forms.ValidationError('Selecione pelo menos um contato remoto para salvar.')
        return hubspot_contact_ids


class HubSpotContactCompanySyncForm(BootstrapFormMixin, forms.Form):
    load = forms.CharField(required=False, widget=forms.HiddenInput(), initial='1')


class HubSpotCompanyCreateForm(CompanyCreateForm):
    pass
