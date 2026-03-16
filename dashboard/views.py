from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from dashboard.services import DashboardMetricsService


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dashboard_summary'] = DashboardMetricsService.build_summary(
            organization=getattr(self.request, 'active_organization', None)
        )
        return context


class AppsPlaceholderView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/apps.html'


class ApiKeysPlaceholderView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/api_keys.html'
