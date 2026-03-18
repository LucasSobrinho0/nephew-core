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
    template_public_id = forms.ChoiceField(label='Template salvo', required=True, choices=())
    person_public_ids = forms.MultipleChoiceField(
        label='Destinatarios',
        choices=(),
        widget=forms.CheckboxSelectMultiple(),
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

    def __init__(self, *args, template_choices=(), person_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['template_public_id'].choices = list(template_choices)
        self.fields['person_public_ids'].choices = person_choices
        self.fields['person_public_ids'].widget.attrs['class'] = 'bot-selection-checkbox'
        self.fields['person_public_ids'].widget.attrs['data-checkbox-group'] = 'gmail-dispatch-selection'

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

        return cleaned_data
