from django.shortcuts import redirect
from django.views import View


class RootRedirectView(View):
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard:home')
        return redirect('accounts:login')
