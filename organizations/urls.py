from django.urls import path

from organizations.views import (
    InviteGenerateView,
    InviteListView,
    OnboardingCreateOrganizationView,
    OnboardingJoinOrganizationView,
    OnboardingView,
    OrganizationsView,
    SwitchActiveOrganizationView,
)

app_name = 'organizations'

urlpatterns = [
    path('onboarding/', OnboardingView.as_view(), name='onboarding'),
    path('onboarding/create/', OnboardingCreateOrganizationView.as_view(), name='onboarding_create'),
    path('onboarding/join/', OnboardingJoinOrganizationView.as_view(), name='onboarding_join'),
    path('organizations/', OrganizationsView.as_view(), name='index'),
    path('organizations/switch/', SwitchActiveOrganizationView.as_view(), name='switch'),
    path('invites/', InviteListView.as_view(), name='invites'),
    path('invites/generate/', InviteGenerateView.as_view(), name='generate_invite'),
]
