from django.urls import path

from dispatch_flow.views import (
    DispatchFlowCreateView,
    DispatchFlowDetailView,
    DispatchFlowView,
)

app_name = 'dispatch_flow'

urlpatterns = [
    path('fluxo-disparo/', DispatchFlowView.as_view(), name='index'),
    path('fluxo-disparo/create/', DispatchFlowCreateView.as_view(), name='create_dispatch'),
    path('fluxo-disparo/status/', DispatchFlowDetailView.as_view(), name='dispatch_detail'),
]
