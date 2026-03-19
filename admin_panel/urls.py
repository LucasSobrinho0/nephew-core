from django.urls import path

from admin_panel.views import AdminPanelIpLogListView, AdminPanelOverviewView

app_name = 'admin_panel'

urlpatterns = [
    path('admin-panel/', AdminPanelOverviewView.as_view(), name='index'),
    path('admin-panel/ips/', AdminPanelIpLogListView.as_view(), name='ip_logs'),
]

