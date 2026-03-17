from django import forms

from common.forms import BootstrapFormMixin
from companies.forms import CompanyCreateForm


class HubSpotCompanySyncForm(BootstrapFormMixin, forms.Form):
    company_public_id = forms.UUIDField(widget=forms.HiddenInput())


class HubSpotPersonSyncForm(BootstrapFormMixin, forms.Form):
    person_public_id = forms.UUIDField(widget=forms.HiddenInput())


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


class HubSpotRemoteContactImportForm(BootstrapFormMixin, forms.Form):
    hubspot_contact_id = forms.CharField(widget=forms.HiddenInput())
    first_name = forms.CharField(required=False, widget=forms.HiddenInput())
    last_name = forms.CharField(required=False, widget=forms.HiddenInput())
    email = forms.CharField(required=False, widget=forms.HiddenInput())
    phone = forms.CharField(required=False, widget=forms.HiddenInput())
    company_name = forms.CharField(required=False, widget=forms.HiddenInput())
    company_hubspot_id = forms.CharField(required=False, widget=forms.HiddenInput())


class HubSpotCompanyCreateForm(CompanyCreateForm):
    pass
