from django import forms

from common.forms import BootstrapFormMixin
from organizations.models import Organization, OrganizationInvite


class OrganizationCreateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Organization
        fields = ('name', 'segment', 'team_size')
        labels = {
            'name': 'Nome',
            'segment': 'Segmento',
            'team_size': 'Tamanho da equipe',
        }
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Nome da organização'}),
        }


class InviteRedeemForm(BootstrapFormMixin, forms.Form):
    code = forms.CharField(
        label='Codigo de convite',
        max_length=24,
        widget=forms.TextInput(
            attrs={
                'placeholder': 'ADM XXXXXXXX or USR XXXXXXXX',
                'autocomplete': 'off',
            }
        ),
    )


class InviteGenerationForm(BootstrapFormMixin, forms.Form):
    target_role = forms.ChoiceField(label='Tipo de convite', choices=OrganizationInvite.TargetRole.choices)


class OrganizationSwitchForm(forms.Form):
    organization_public_id = forms.UUIDField(widget=forms.HiddenInput())
