from django import forms

from common.forms import BootstrapFormMixin


class ImportUploadForm(BootstrapFormMixin, forms.Form):
    file = forms.FileField(
        label='Planilha XLSX',
        widget=forms.ClearableFileInput(attrs={'accept': '.xlsx'}),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        file_name = (uploaded_file.name or '').lower()
        if not file_name.endswith('.xlsx'):
            raise forms.ValidationError('Envie um arquivo XLSX valido.')
        return uploaded_file
