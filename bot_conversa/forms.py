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
    min_delay_seconds = forms.IntegerField(label='Delay minimo (segundos)', min_value=0, max_value=60, initial=0)
    max_delay_seconds = forms.IntegerField(label='Delay maximo (segundos)', min_value=0, max_value=60, initial=0)

    def __init__(self, *args, flow_choices=(), person_choices=(), tag_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['flow_public_id'].choices = flow_choices
        self.fields['tag_public_ids'].choices = tag_choices
        self.fields['person_public_ids'].choices = person_choices
        self.fields['tag_public_ids'].widget.attrs['class'] = 'bot-selection-checkbox'
        self.fields['tag_public_ids'].widget.attrs['data-checkbox-group'] = 'bot-tag-dispatch-selection'
        self.fields['person_public_ids'].widget.attrs['class'] = 'bot-selection-checkbox'
        self.fields['person_public_ids'].widget.attrs['data-checkbox-group'] = 'bot-dispatch-selection'

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
    next = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, person_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person_public_ids'].choices = person_choices

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
