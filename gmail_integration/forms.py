from django import forms

from common.forms import BootstrapFormMixin


class GmailCredentialSaveForm(BootstrapFormMixin, forms.Form):
    next = forms.CharField(required=False, widget=forms.HiddenInput())
    credentials_file = forms.FileField(label='credentials.json')
    token_file = forms.FileField(label='token.json')


class GmailTemplateForm(BootstrapFormMixin, forms.Form):
    name = forms.CharField(
        label='Nome do template',
        max_length=120,
        widget=forms.TextInput(attrs={'placeholder': 'Follow-up inicial'}),
    )
    subject = forms.CharField(
        label='Assunto',
        max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Assunto do email'}),
    )
    body = forms.CharField(
        label='Corpo do email',
        widget=forms.Textarea(
            attrs={
                'rows': 8,
                'placeholder': 'Ola ${nome},\n\nEscreva aqui a mensagem do template.',
            }
        ),
    )
    is_active = forms.BooleanField(label='Template ativo', required=False, initial=True)

    def clean_name(self):
        return self.cleaned_data['name'].strip()

    def clean_subject(self):
        return self.cleaned_data['subject'].strip()

    def clean_body(self):
        return self.cleaned_data['body'].strip()


class GmailDispatchCreateForm(BootstrapFormMixin, forms.Form):
    HUBSPOT_DEAL_TARGET_CHOICES = (
        ('company', 'Negocio da empresa'),
        ('person', 'Negocio da pessoa'),
    )

    template_public_id = forms.ChoiceField(label='Template salvo', required=True, choices=())
    person_public_ids = forms.MultipleChoiceField(
        label='Destinatarios',
        choices=(),
        widget=forms.CheckboxSelectMultiple(),
    )
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
    cc_emails = forms.CharField(
        label='Copias',
        required=False,
        widget=forms.Textarea(
            attrs={
                'rows': 4,
                'placeholder': 'copia1@empresa.com, copia2@empresa.com',
            }
        ),
    )
    min_delay_seconds = forms.IntegerField(label='Delay minimo (segundos)', min_value=0, initial=0)
    max_delay_seconds = forms.IntegerField(label='Delay maximo (segundos)', min_value=0, initial=0)

    def __init__(
        self,
        *args,
        template_choices=(),
        person_choices=(),
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
        self.fields['template_public_id'].choices = list(template_choices)
        self.fields['person_public_ids'].choices = person_choices
        self.fields['hubspot_target_company_public_id'].choices = [('', 'Selecione')] + list(hubspot_company_choices)
        self.fields['hubspot_target_person_public_id'].choices = [('', 'Selecione')] + list(hubspot_person_choices)
        self.fields['hubspot_deal_person_public_ids'].choices = list(hubspot_deal_person_choices)
        self.fields['hubspot_pipeline_public_id'].choices = [('', 'Selecione')] + list(hubspot_pipeline_choices)
        self.fields['hubspot_stage_id'].choices = [('', 'Selecione')] + list(hubspot_stage_choices)
        self.fields['person_public_ids'].widget.attrs['class'] = 'bot-selection-checkbox'
        self.fields['person_public_ids'].widget.attrs['data-checkbox-group'] = 'gmail-dispatch-selection'
        self.hubspot_enabled = hubspot_enabled
        self.hubspot_company_contact_warning = hubspot_company_contact_warning
        self.hubspot_allow_manual_company_contacts = hubspot_allow_manual_company_contacts
        if form_id:
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
        person_public_ids = self.cleaned_data.get('person_public_ids') or []
        if not person_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma pessoa para o disparo.')
        return person_public_ids

    def clean_cc_emails(self):
        raw_cc_emails = self.cleaned_data.get('cc_emails', '')
        normalized_entries = raw_cc_emails.replace('\r', '\n').replace(';', ',')
        email_entries = []

        for raw_email in normalized_entries.replace('\n', ',').split(','):
            cleaned_email = raw_email.strip().lower()
            if not cleaned_email:
                continue
            try:
                email_entries.append(forms.EmailField().clean(cleaned_email))
            except forms.ValidationError as exc:
                raise forms.ValidationError(f'Email de copia invalido: {cleaned_email}.') from exc

        unique_emails = []
        seen_emails = set()
        for email_address in email_entries:
            if email_address in seen_emails:
                continue
            unique_emails.append(email_address)
            seen_emails.add(email_address)

        return unique_emails

    def clean(self):
        cleaned_data = super().clean()
        min_delay_seconds = cleaned_data.get('min_delay_seconds')
        max_delay_seconds = cleaned_data.get('max_delay_seconds')

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
