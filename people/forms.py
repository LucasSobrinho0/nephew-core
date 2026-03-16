from django import forms

from common.forms import BootstrapFormMixin


class PersonCreateForm(BootstrapFormMixin, forms.Form):
    first_name = forms.CharField(
        label='Nome',
        max_length=120,
        widget=forms.TextInput(attrs={'placeholder': 'Nome'}),
    )
    last_name = forms.CharField(
        label='Sobrenome',
        max_length=120,
        widget=forms.TextInput(attrs={'placeholder': 'Sobrenome'}),
    )
    phone = forms.CharField(
        label='Telefone',
        max_length=32,
        widget=forms.TextInput(attrs={'placeholder': '+55 11 91234-5678'}),
    )

    def clean_first_name(self):
        return self.cleaned_data['first_name'].strip()

    def clean_last_name(self):
        return self.cleaned_data['last_name'].strip()

    def clean_phone(self):
        return self.cleaned_data['phone'].strip()
