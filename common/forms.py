from django import forms


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()

    def _apply_bootstrap_classes(self):
        for field in self.fields.values():
            widget = field.widget

            if isinstance(widget, forms.HiddenInput):
                continue

            if isinstance(widget, forms.CheckboxInput):
                css_class = 'form-check-input'
            elif isinstance(widget, forms.Select):
                css_class = 'form-select'
            else:
                css_class = 'form-control'

            existing_classes = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing_classes} {css_class}'.strip()
