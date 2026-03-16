from django import forms

from common.forms import BootstrapFormMixin


class BotConversaPersonSyncForm(BootstrapFormMixin, forms.Form):
    person_public_id = forms.UUIDField(widget=forms.HiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class BotConversaFlowRefreshForm(BootstrapFormMixin, forms.Form):
    next = forms.CharField(required=False, widget=forms.HiddenInput())


class BotConversaDispatchCreateForm(BootstrapFormMixin, forms.Form):
    flow_public_id = forms.ChoiceField(label='Fluxo', choices=(), widget=forms.Select())
    person_public_ids = forms.MultipleChoiceField(
        label='Pessoas para envio',
        choices=(),
        widget=forms.CheckboxSelectMultiple(),
    )

    def __init__(self, *args, flow_choices=(), person_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['flow_public_id'].choices = flow_choices
        self.fields['person_public_ids'].choices = person_choices
        self.fields['person_public_ids'].widget.attrs['class'] = 'bot-selection-checkbox'

    def clean_person_public_ids(self):
        person_public_ids = self.cleaned_data.get('person_public_ids') or []
        if not person_public_ids:
            raise forms.ValidationError('Selecione pelo menos uma pessoa para o disparo do fluxo.')
        return person_public_ids


class BotConversaRemoteContactSearchForm(BootstrapFormMixin, forms.Form):
    search = forms.CharField(
        label='Filtro local',
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Filtrar por nome ou telefone (opcional)'}),
    )


class BotConversaRemoteContactSaveForm(BootstrapFormMixin, forms.Form):
    external_subscriber_id = forms.CharField(widget=forms.HiddenInput())
    first_name = forms.CharField(required=False, widget=forms.HiddenInput())
    last_name = forms.CharField(required=False, widget=forms.HiddenInput())
    external_name = forms.CharField(required=False, widget=forms.HiddenInput())
    phone = forms.CharField(widget=forms.HiddenInput())
    next = forms.CharField(required=False, widget=forms.HiddenInput())
