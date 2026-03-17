from django import forms

from common.forms import BootstrapFormMixin


class PersonForm(BootstrapFormMixin, forms.Form):
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
    email = forms.EmailField(
        label='Email',
        required=False,
        max_length=254,
        widget=forms.EmailInput(attrs={'placeholder': 'contato@empresa.com'}),
    )
    phone = forms.CharField(
        label='Telefone',
        max_length=32,
        widget=forms.TextInput(attrs={'placeholder': '+55 11 91234-5678'}),
    )
    company_public_id = forms.ChoiceField(
        label='Empresa',
        required=False,
        choices=(),
        widget=forms.Select(),
    )

    def __init__(self, *args, company_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_public_id'].choices = [('', 'Sem empresa')] + list(company_choices)

    def clean_first_name(self):
        return self.cleaned_data['first_name'].strip()

    def clean_last_name(self):
        return self.cleaned_data['last_name'].strip()

    def clean_email(self):
        return self.cleaned_data.get('email', '').strip().lower()

    def clean_phone(self):
        return self.cleaned_data['phone'].strip()


class PersonCreateForm(PersonForm):
    pass


class PersonUpdateForm(PersonForm):
    pass
