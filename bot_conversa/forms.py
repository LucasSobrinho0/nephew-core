from django import forms

from common.forms import BootstrapFormMixin
from people.forms import PersonCreateForm


class BotConversaPersonSyncForm(BootstrapFormMixin, forms.Form):
    person_public_id = forms.UUIDField(widget=forms.HiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class BotConversaFlowRefreshForm(BootstrapFormMixin, forms.Form):
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class BotConversaTagRefreshForm(BootstrapFormMixin, forms.Form):
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class BotConversaDispatchCreateForm(BootstrapFormMixin, forms.Form):
    HUBSPOT_DEAL_TARGET_CHOICES = (
        ('company', 'Negocio da empresa'),
        ('person', 'Negocio da pessoa'),
    )

    flow_public_id = forms.ChoiceField(label='Fluxo', choices=(), widget=forms.Select())
    tag_public_ids = forms.MultipleChoiceField(
        label='Etiquetas do Bot Conversa',
        choices=(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    person_public_ids = forms.MultipleChoiceField(
        label='Pessoas para envio',
        choices=(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    preflight_tag_public_ids = forms.MultipleChoiceField(
        label='Etiquetas do Bot Conversa',
        required=False,
        choices=(),
        widget=forms.SelectMultiple(
            attrs={
                'data-enhanced-multiselect': 'true',
                'data-placeholder': 'Pesquisar etiquetas',
            }
        ),
    )
    skip_tag_preflight = forms.BooleanField(required=False, widget=forms.HiddenInput())
    tag_preflight_action = forms.CharField(required=False, widget=forms.HiddenInput())
    skip_hubspot_preflight = forms.BooleanField(required=False, widget=forms.HiddenInput())
    hubspot_preflight_action = forms.CharField(required=False, widget=forms.HiddenInput())
    hubspot_create_deal_now = forms.BooleanField(
        label='Criar novo negocio no HubSpot antes do disparo',
        required=False,
    )
    hubspot_deal_target_type = forms.ChoiceField(
        label='Tipo do negocio',
        required=False,
        choices=HUBSPOT_DEAL_TARGET_CHOICES,
    )
    hubspot_target_company_public_id = forms.ChoiceField(
        label='Empresa do negocio',
        required=False,
        choices=(),
    )
    hubspot_target_person_public_id = forms.ChoiceField(
        label='Pessoa do negocio',
        required=False,
        choices=(),
    )
    hubspot_deal_person_public_ids = forms.MultipleChoiceField(
        label='Contatos do negocio',
        required=False,
        choices=(),
        widget=forms.SelectMultiple(
            attrs={
                'data-enhanced-multiselect': 'true',
                'data-placeholder': 'Selecionar contatos locais para o negocio',
            }
        ),
    )
    hubspot_pipeline_public_id = forms.ChoiceField(
        label='Pipeline do negocio',
        required=False,
        choices=(),
    )
    hubspot_stage_id = forms.ChoiceField(
        label='Coluna do negocio',
        required=False,
        choices=(),
    )
    min_delay_seconds = forms.IntegerField(label='Delay minimo (segundos)', min_value=0, initial=0)
    max_delay_seconds = forms.IntegerField(label='Delay maximo (segundos)', min_value=0, initial=0)

    def __init__(
        self,
        *args,
        flow_choices=(),
        person_choices=(),
        tag_choices=(),
        hubspot_enabled=False,
        hubspot_company_choices=(),
        hubspot_person_choices=(),
        hubspot_deal_person_choices=(),
        hubspot_pipeline_choices=(),
        hubspot_stage_choices=(),
        hubspot_default_target_type='',
        hubspot_default_company_public_id='',
        hubspot_default_person_public_id='',
        hubspot_default_deal_person_public_ids=None,
        hubspot_company_contact_warning='',
        hubspot_allow_manual_company_contacts=False,
        form_id='',
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.fields['flow_public_id'].choices = flow_choices
        self.fields['tag_public_ids'].choices = tag_choices
        self.fields['person_public_ids'].choices = person_choices
        self.fields['preflight_tag_public_ids'].choices = tag_choices
        self.fields['hubspot_target_company_public_id'].choices = [('', 'Selecione')] + list(hubspot_company_choices)
        self.fields['hubspot_target_person_public_id'].choices = [('', 'Selecione')] + list(hubspot_person_choices)
        self.fields['hubspot_deal_person_public_ids'].choices = list(hubspot_deal_person_choices)
        self.fields['hubspot_pipeline_public_id'].choices = [('', 'Selecione')] + list(hubspot_pipeline_choices)
        self.fields['hubspot_stage_id'].choices = [('', 'Selecione')] + list(hubspot_stage_choices)
        self.fields['tag_public_ids'].widget.attrs['class'] = 'bot-selection-checkbox'
        self.fields['tag_public_ids'].widget.attrs['data-checkbox-group'] = 'bot-tag-dispatch-selection'
        self.fields['person_public_ids'].widget.attrs['class'] = 'bot-selection-checkbox'
        self.fields['person_public_ids'].widget.attrs['data-checkbox-group'] = 'bot-dispatch-selection'
        self.hubspot_enabled = hubspot_enabled
        self.hubspot_company_contact_warning = hubspot_company_contact_warning
        self.hubspot_allow_manual_company_contacts = hubspot_allow_manual_company_contacts
        if form_id:
            self.fields['preflight_tag_public_ids'].widget.attrs['form'] = form_id
            self.fields['hubspot_create_deal_now'].widget.attrs['form'] = form_id
            self.fields['hubspot_deal_target_type'].widget.attrs['form'] = form_id
            self.fields['hubspot_target_company_public_id'].widget.attrs['form'] = form_id
            self.fields['hubspot_target_person_public_id'].widget.attrs['form'] = form_id
            self.fields['hubspot_deal_person_public_ids'].widget.attrs['form'] = form_id
            self.fields['hubspot_pipeline_public_id'].widget.attrs['form'] = form_id
            self.fields['hubspot_stage_id'].widget.attrs['form'] = form_id

        if hubspot_default_target_type and 'hubspot_deal_target_type' not in self.data:
            self.initial['hubspot_deal_target_type'] = hubspot_default_target_type
        if hubspot_default_company_public_id and 'hubspot_target_company_public_id' not in self.data:
            self.initial['hubspot_target_company_public_id'] = hubspot_default_company_public_id
        if hubspot_default_person_public_id and 'hubspot_target_person_public_id' not in self.data:
            self.initial['hubspot_target_person_public_id'] = hubspot_default_person_public_id
        if hubspot_default_deal_person_public_ids and 'hubspot_deal_person_public_ids' not in self.data:
            self.initial['hubspot_deal_person_public_ids'] = list(hubspot_default_deal_person_public_ids)

    def clean_person_public_ids(self):
        return self.cleaned_data.get('person_public_ids') or []

    def clean(self):
        cleaned_data = super().clean()
        min_delay_seconds = cleaned_data.get('min_delay_seconds')
        max_delay_seconds = cleaned_data.get('max_delay_seconds')
        person_public_ids = cleaned_data.get('person_public_ids') or []
        tag_public_ids = cleaned_data.get('tag_public_ids') or []

        if not person_public_ids and not tag_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma pessoa ou uma etiqueta para o disparo do fluxo.')

        if min_delay_seconds is None or max_delay_seconds is None:
            return cleaned_data

        if max_delay_seconds < min_delay_seconds:
            raise forms.ValidationError('O delay maximo nao pode ser menor que o delay minimo.')

        if (
            cleaned_data.get('hubspot_preflight_action') == 'apply'
            and cleaned_data.get('hubspot_create_deal_now')
        ):
            if not cleaned_data.get('hubspot_deal_target_type'):
                self.add_error('hubspot_deal_target_type', 'Selecione como o negocio sera criado.')
            if not cleaned_data.get('hubspot_pipeline_public_id'):
                self.add_error('hubspot_pipeline_public_id', 'Selecione um pipeline para criar o negocio.')
            if not cleaned_data.get('hubspot_stage_id'):
                self.add_error('hubspot_stage_id', 'Selecione a coluna do negocio.')
            if cleaned_data.get('hubspot_deal_target_type') == 'person' and not cleaned_data.get('hubspot_target_person_public_id'):
                self.add_error('hubspot_target_person_public_id', 'Selecione a pessoa do negocio.')

        return cleaned_data


class BotConversaRemoteContactSearchForm(BootstrapFormMixin, forms.Form):
    search = forms.CharField(
        label='Filtro local',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Filtrar por nome ou telefone (opcional)'}),
    )


class BotConversaListForm(BootstrapFormMixin, forms.Form):
    load = forms.CharField(required=False, widget=forms.HiddenInput(), initial='1')


class BotConversaRemoteContactSaveForm(BootstrapFormMixin, forms.Form):
    external_subscriber_id = forms.CharField(widget=forms.HiddenInput())
    first_name = forms.CharField(required=False, widget=forms.HiddenInput())
    last_name = forms.CharField(required=False, widget=forms.HiddenInput())
    external_name = forms.CharField(required=False, widget=forms.HiddenInput())
    phone = forms.CharField(widget=forms.HiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class BotConversaBulkPersonSyncForm(BootstrapFormMixin, forms.Form):
    person_public_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())
    tag_public_ids = forms.MultipleChoiceField(
        label='Etiquetas do Bot Conversa',
        required=False,
        choices=(),
        widget=forms.SelectMultiple(
            attrs={
                'data-enhanced-multiselect': 'true',
                'data-placeholder': 'Pesquisar etiquetas',
            }
        ),
    )
    skip_tag_preflight = forms.BooleanField(required=False, widget=forms.HiddenInput())
    tag_preflight_action = forms.CharField(required=False, widget=forms.HiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, person_choices=(), tag_choices=(), form_id='', **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person_public_ids'].choices = person_choices
        self.fields['tag_public_ids'].choices = tag_choices
        if form_id:
            self.fields['tag_public_ids'].widget.attrs['form'] = form_id

    def clean_person_public_ids(self):
        person_public_ids = self.cleaned_data.get('person_public_ids') or []
        if not person_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma pessoa para sincronizar.')
        return person_public_ids


class BotConversaBulkRemoteContactSaveForm(BootstrapFormMixin, forms.Form):
    external_subscriber_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, subscriber_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['external_subscriber_ids'].choices = subscriber_choices

    def clean_external_subscriber_ids(self):
        external_subscriber_ids = self.cleaned_data.get('external_subscriber_ids') or []
        if not external_subscriber_ids:
            raise forms.ValidationError('Selecione pelo menos um contato remoto para salvar.')
        return external_subscriber_ids


class BotConversaPersonTagAssignForm(BootstrapFormMixin, forms.Form):
    tag_public_id = forms.ChoiceField(label='Etiqueta', choices=())
    person_public_ids = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, tag_choices=(), person_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tag_public_id'].choices = tag_choices
        self.fields['person_public_ids'].choices = person_choices

    def clean_person_public_ids(self):
        person_public_ids = self.cleaned_data.get('person_public_ids') or []
        if not person_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma pessoa para vincular a etiqueta.')
        return person_public_ids


class BotConversaPersonCreateForm(PersonCreateForm):
    tag_public_ids = forms.MultipleChoiceField(
        label='Etiquetas do Bot Conversa',
        choices=(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )

    def __init__(self, *args, tag_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tag_public_ids'].choices = list(tag_choices)
        self.fields['tag_public_ids'].widget.attrs['class'] = 'bot-selection-checkbox'
        self.fields['tag_public_ids'].widget.attrs['data-checkbox-group'] = 'bot-person-create-tags'

    def clean_tag_public_ids(self):
        return self.cleaned_data.get('tag_public_ids') or []
