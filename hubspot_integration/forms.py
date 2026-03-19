from django import forms

from common.forms import BootstrapFormMixin
from companies.forms import CompanyCreateForm
from people.forms import PersonCreateForm


class HubSpotRemoteListForm(BootstrapFormMixin, forms.Form):
    load = forms.CharField(required=False, widget=forms.HiddenInput(), initial='1')


class HubSpotCompanySyncForm(BootstrapFormMixin, forms.Form):
    company_public_id = forms.UUIDField(widget=forms.HiddenInput())


class HubSpotPersonSyncForm(BootstrapFormMixin, forms.Form):
    person_public_id = forms.UUIDField(widget=forms.HiddenInput())


class HubSpotBulkCompanySyncForm(BootstrapFormMixin, forms.Form):
    company_public_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())
    create_deal_now = forms.BooleanField(
        label='Criar negocio ao sincronizar',
        required=False,
    )
    pipeline_public_id = forms.ChoiceField(
        label='Pipeline do negocio',
        required=False,
        choices=(),
    )
    stage_id = forms.ChoiceField(
        label='Coluna do negocio',
        required=False,
        choices=(),
    )
    confirm_existing_remote_deals = forms.BooleanField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, company_choices=(), pipeline_choices=(), stage_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_public_ids'].choices = company_choices
        self.fields['pipeline_public_id'].choices = [('', 'Selecione')] + list(pipeline_choices)
        self.fields['stage_id'].choices = [('', 'Selecione')] + list(stage_choices)

    def clean_company_public_ids(self):
        company_public_ids = self.cleaned_data.get('company_public_ids') or []
        if not company_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma empresa para sincronizar.')
        return company_public_ids

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('create_deal_now'):
            return cleaned_data

        if not cleaned_data.get('pipeline_public_id'):
            self.add_error('pipeline_public_id', 'Selecione um pipeline para criar o negocio.')
        if not cleaned_data.get('stage_id'):
            self.add_error('stage_id', 'Selecione a coluna do negocio.')
        return cleaned_data


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


class HubSpotAttachPersonToDealForm(BootstrapFormMixin, forms.Form):
    person_public_id = forms.ChoiceField(
        label='Pessoa',
        choices=(),
    )
    deal_public_id = forms.ChoiceField(
        label='Negocio',
        required=False,
        choices=(),
    )

    def __init__(self, *args, person_choices=(), deal_search_url='', selected_deal_choice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person_public_id'].choices = [('', 'Selecione')] + list(person_choices)
        base_choices = [('', 'Selecione')]
        if selected_deal_choice:
            base_choices.append(selected_deal_choice)
        self.fields['deal_public_id'].choices = base_choices
        self.fields['deal_public_id'].widget.attrs.update(
            {
                'data-remote-select': 'true',
                'data-remote-url': deal_search_url,
                'data-placeholder': 'Pesquisar negocio',
                'data-remote-min-chars': '0',
            }
        )

    def clean_person_public_id(self):
        return self.cleaned_data.get('person_public_id', '').strip()

    def clean_deal_public_id(self):
        return self.cleaned_data.get('deal_public_id', '').strip()


class HubSpotPipelineRefreshForm(BootstrapFormMixin, forms.Form):
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class HubSpotDealCreateForm(BootstrapFormMixin, forms.Form):
    company_public_id = forms.ChoiceField(label='Empresa', choices=())
    pipeline_public_id = forms.ChoiceField(label='Pipeline', choices=())
    stage_id = forms.ChoiceField(label='Coluna do negocio', choices=())
    deal_name = forms.CharField(
        label='Nome do negocio',
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Nome do negocio'}),
    )
    amount = forms.CharField(
        label='Valor',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '15000'}),
    )

    def __init__(self, *args, company_choices=(), pipeline_choices=(), stage_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_public_id'].choices = company_choices
        self.fields['pipeline_public_id'].choices = pipeline_choices
        self.fields['stage_id'].choices = stage_choices

    def clean_deal_name(self):
        return self.cleaned_data['deal_name'].strip()

    def clean_amount(self):
        return self.cleaned_data.get('amount', '').strip()

    def clean_stage_id(self):
        return self.cleaned_data['stage_id'].strip()


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
    create_deal_now = forms.BooleanField(
        label='Criar negocio agora',
        required=False,
    )
    pipeline_public_id = forms.ChoiceField(
        label='Pipeline do negocio',
        required=False,
        choices=(),
    )
    stage_id = forms.ChoiceField(
        label='Coluna do negocio',
        required=False,
        choices=(),
    )
    deal_name = forms.CharField(
        label='Nome do negocio',
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Nome do negocio'}),
    )
    amount = forms.CharField(
        label='Valor do negocio',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '15000'}),
    )

    def __init__(self, *args, pipeline_choices=(), stage_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pipeline_public_id'].choices = [('', 'Selecione')] + list(pipeline_choices)
        self.fields['stage_id'].choices = [('', 'Selecione')] + list(stage_choices)

    def clean_deal_name(self):
        return self.cleaned_data.get('deal_name', '').strip()

    def clean_amount(self):
        return self.cleaned_data.get('amount', '').strip()

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('create_deal_now'):
            return cleaned_data

        if not cleaned_data.get('pipeline_public_id'):
            self.add_error('pipeline_public_id', 'Selecione um pipeline para criar o negocio.')
        if not cleaned_data.get('stage_id'):
            self.add_error('stage_id', 'Selecione a coluna do negocio.')
        if not cleaned_data.get('deal_name'):
            cleaned_data['deal_name'] = cleaned_data.get('name', '').strip()
        return cleaned_data


class HubSpotPersonCreateForm(PersonCreateForm):
    deal_public_id = forms.ChoiceField(
        label='Negocio',
        required=False,
        choices=(),
    )

    def __init__(self, *args, company_choices=(), deal_search_url='', selected_deal_choice=None, **kwargs):
        super().__init__(*args, company_choices=company_choices, **kwargs)
        base_choices = [('', 'Selecione')]
        if selected_deal_choice:
            base_choices.append(selected_deal_choice)
        self.fields['deal_public_id'].choices = base_choices
        self.fields['deal_public_id'].widget.attrs.update(
            {
                'data-remote-select': 'true',
                'data-remote-url': deal_search_url,
                'data-placeholder': 'Pesquisar negocio',
                'data-remote-min-chars': '0',
            }
        )

    def clean_deal_public_id(self):
        return self.cleaned_data.get('deal_public_id', '').strip()
