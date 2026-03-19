from django import forms

from common.forms import BootstrapFormMixin


class AdminAccessLogListForm(BootstrapFormMixin, forms.Form):
    PAGE_SIZE_CHOICES = (
        ('10', '10'),
        ('25', '25'),
        ('50', '50'),
        ('100', '100'),
    )
    ALLOWED_PAGE_SIZES = {10, 25, 50, 100}

    per_page = forms.ChoiceField(choices=PAGE_SIZE_CHOICES, required=False, initial='25', label='Mostrar')

    def clean_per_page(self):
        page_size = int(self.cleaned_data.get('per_page') or 25)
        if page_size not in self.ALLOWED_PAGE_SIZES:
            raise forms.ValidationError('Escolha uma quantidade valida por pagina.')
        return page_size
