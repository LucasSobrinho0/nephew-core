from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from admin_panel.forms import AdminAccessLogListForm
from admin_panel.services import (
    AdminAuthorizationService,
    AdminPanelNavigationService,
    AdminPanelOverviewService,
    AdminPanelQueryService,
)


class AdminPanelAccessMixin(LoginRequiredMixin):
    permission_denied_redirect_url = 'dashboard:home'
    permission_denied_message = 'Somente usuarios do grupo Admin podem acessar o Painel Admin.'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not AdminAuthorizationService.has_panel_access(request.user):
            messages.error(request, self.permission_denied_message)
            return redirect(self.permission_denied_redirect_url)

        return super().dispatch(request, *args, **kwargs)

    def build_base_context(self, *, active_tab):
        return {
            'admin_panel_tabs': AdminPanelNavigationService.build_navigation_items(),
            'admin_panel_active_tab': active_tab,
        }


class AdminPanelOverviewView(AdminPanelAccessMixin, TemplateView):
    template_name = 'admin_panel/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context(active_tab='overview'))
        context['summary'] = AdminPanelOverviewService.build_summary()
        return context


class AdminPanelIpLogListView(AdminPanelAccessMixin, TemplateView):
    template_name = 'admin_panel/ip_logs.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get('filter_form') or AdminAccessLogListForm(self.request.GET or None)
        if not form.is_valid():
            form = AdminAccessLogListForm({'per_page': 25})
            form.is_valid()

        page_result = AdminPanelQueryService.build_ip_log_list(
            page_size=form.cleaned_data.get('per_page', 25),
            cursor_value=self.request.GET.get('cursor', ''),
            direction=self.request.GET.get('direction', 'next'),
        )
        base_url = reverse('admin_panel:ip_logs')

        context.update(self.build_base_context(active_tab='ip_logs'))
        context.update(
            {
                'filter_form': form,
                'ip_logs': page_result.records,
                'pagination': {
                    'total_count': page_result.total_count,
                    'page_size': page_result.page_size,
                    'previous_url': AdminPanelQueryService.build_cursor_url(
                        base_url=base_url,
                        page_size=page_result.page_size,
                        cursor_value=page_result.previous_cursor,
                        direction='previous',
                    ),
                    'next_url': AdminPanelQueryService.build_cursor_url(
                        base_url=base_url,
                        page_size=page_result.page_size,
                        cursor_value=page_result.next_cursor,
                        direction='next',
                    ),
                },
            }
        )
        return context
