from django import forms

from common.forms import BootstrapFormMixin


class DispatchFlowFilterForm(BootstrapFormMixin, forms.Form):
    AUDIENCE_FILTER_CHOICES = (
        ('all', 'Toda a base'),
        ('email_unsent', 'Nao enviados por e-mail'),
        ('whatsapp_unsent', 'Nao enviados por WhatsApp'),
        ('unsent_both', 'Nao enviados em nenhum canal'),
    )

    load = forms.CharField(required=False, widget=forms.HiddenInput(), initial='1')
    audience_filter = forms.ChoiceField(
        label='Filtro de audiencia',
        choices=AUDIENCE_FILTER_CHOICES,
        required=False,
        initial='all',
    )


class DispatchFlowCreateForm(BootstrapFormMixin, forms.Form):
    person_public_ids = forms.MultipleChoiceField(
        required=False,
        widget=forms.MultipleHiddenInput(),
    )
    bot_conversa_tag_public_ids = forms.MultipleChoiceField(
        label='Etiquetas do Bot Conversa',
        required=False,
        choices=(),
        widget=forms.SelectMultiple(
            attrs={
                'data-enhanced-multiselect': 'true',
                'data-placeholder': 'Pesquisar etiquetas do Bot Conversa',
            }
        ),
    )
    skip_bot_conversa_tag_preflight = forms.BooleanField(required=False, widget=forms.HiddenInput())
    bot_conversa_tag_preflight_action = forms.CharField(required=False, widget=forms.HiddenInput())
    send_bot_conversa = forms.BooleanField(
        label='Enviar por WhatsApp',
        required=False,
    )
    send_gmail = forms.BooleanField(
        label='Enviar por Gmail',
        required=False,
    )
    flow_public_id = forms.ChoiceField(
        label='Fluxo do WhatsApp',
        required=False,
        choices=(),
    )
    gmail_template_public_id = forms.ChoiceField(
        label='Template de e-mail',
        required=False,
        choices=(),
    )
    gmail_cc_emails = forms.CharField(
        label='Copias do e-mail',
        required=False,
        widget=forms.Textarea(
            attrs={
                'rows': 3,
                'placeholder': 'copia1@empresa.com, copia2@empresa.com',
            }
        ),
    )
    bot_min_delay_seconds = forms.IntegerField(label='Delay minimo WhatsApp', min_value=0, initial=0)
    bot_max_delay_seconds = forms.IntegerField(label='Delay maximo WhatsApp', min_value=0, initial=0)
    gmail_min_delay_seconds = forms.IntegerField(label='Delay minimo e-mail', min_value=0, initial=0)
    gmail_max_delay_seconds = forms.IntegerField(label='Delay maximo e-mail', min_value=0, initial=0)

    def __init__(
        self,
        *args,
        person_choices=(),
        bot_flow_choices=(),
        bot_tag_choices=(),
        gmail_template_choices=(),
        bot_enabled=False,
        gmail_enabled=False,
        form_id='',
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fields['person_public_ids'].choices = list(person_choices)
        self.fields['bot_conversa_tag_public_ids'].choices = list(bot_tag_choices)
        self.fields['flow_public_id'].choices = [('', 'Selecione')] + list(bot_flow_choices)
        self.fields['gmail_template_public_id'].choices = [('', 'Selecione')] + list(gmail_template_choices)
        self.bot_enabled = bot_enabled
        self.gmail_enabled = gmail_enabled
        if form_id:
            self.fields['bot_conversa_tag_public_ids'].widget.attrs['form'] = form_id

    def clean_person_public_ids(self):
        person_public_ids = self.cleaned_data.get('person_public_ids') or []
        if not person_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma pessoa para o disparo.')
        return person_public_ids

    def clean_gmail_cc_emails(self):
        raw_cc_emails = self.cleaned_data.get('gmail_cc_emails', '')
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
        send_bot_conversa = cleaned_data.get('send_bot_conversa', False)
        send_gmail = cleaned_data.get('send_gmail', False)

        if not send_bot_conversa and not send_gmail:
            raise forms.ValidationError('Selecione pelo menos um canal para o disparo.')

        if send_bot_conversa and not self.bot_enabled:
            self.add_error('send_bot_conversa', 'O Bot Conversa nao esta disponivel na organizacao ativa.')
        if send_gmail and not self.gmail_enabled:
            self.add_error('send_gmail', 'O Gmail nao esta disponivel na organizacao ativa.')

        if send_bot_conversa and not cleaned_data.get('flow_public_id'):
            self.add_error('flow_public_id', 'Selecione um fluxo do WhatsApp.')
        if send_gmail and not cleaned_data.get('gmail_template_public_id'):
            self.add_error('gmail_template_public_id', 'Selecione um template de e-mail.')

        bot_min = cleaned_data.get('bot_min_delay_seconds')
        bot_max = cleaned_data.get('bot_max_delay_seconds')
        if send_bot_conversa and bot_min is not None and bot_max is not None and bot_max < bot_min:
            self.add_error('bot_max_delay_seconds', 'O delay maximo do WhatsApp nao pode ser menor que o minimo.')

        gmail_min = cleaned_data.get('gmail_min_delay_seconds')
        gmail_max = cleaned_data.get('gmail_max_delay_seconds')
        if send_gmail and gmail_min is not None and gmail_max is not None and gmail_max < gmail_min:
            self.add_error('gmail_max_delay_seconds', 'O delay maximo do e-mail nao pode ser menor que o minimo.')

        return cleaned_data
