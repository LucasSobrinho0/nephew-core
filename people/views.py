from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from companies.repositories import CompanyRepository
from common.mixins import ActiveOrganizationRequiredMixin
from people.forms import PersonCreateForm, PersonUpdateForm
from people.repositories import PersonRepository
from people.services import PersonService


class PeopleListView(ActiveOrganizationRequiredMixin, TemplateView):
    template_name = 'people/index.html'

    def build_company_choices(self):
        return [
            (str(company.public_id), company.name)
            for company in CompanyRepository.list_for_organization(self.request.active_organization)
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                'person_rows': PersonRepository.list_for_organization(self.request.active_organization),
                'create_form': kwargs.get('create_form') or PersonCreateForm(company_choices=self.build_company_choices()),
            }
        )
        return context


class PersonCreateView(ActiveOrganizationRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        company_choices = [
            (str(company.public_id), company.name)
            for company in CompanyRepository.list_for_organization(request.active_organization)
        ]
        form = PersonCreateForm(request.POST, company_choices=company_choices)
        if not form.is_valid():
            view = PeopleListView()
            view.request = request
            view.args = args
            view.kwargs = kwargs
            return view.render_to_response(view.get_context_data(create_form=form))

        company = None
        if form.cleaned_data['company_public_id']:
            company = CompanyRepository.get_for_organization_and_public_id(
                request.active_organization,
                form.cleaned_data['company_public_id'],
            )

        try:
            PersonService.create_person(
                user=request.user,
                organization=request.active_organization,
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                email=form.cleaned_data['email'],
                phone=form.cleaned_data['phone'],
                company=company,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else str(exc))
            return redirect('people:index')

        messages.success(request, 'Pessoa cadastrada com sucesso.')
        return redirect('people:index')


class PersonUpdateView(ActiveOrganizationRequiredMixin, TemplateView):
    template_name = 'people/edit.html'

    def get_person(self):
        return PersonRepository.get_for_organization_and_public_id(
            self.request.active_organization,
            self.kwargs['person_public_id'],
        )

    def dispatch(self, request, *args, **kwargs):
        self.person = self.get_person()
        if self.person is None:
            messages.error(request, 'A pessoa selecionada nao foi encontrada.')
            return redirect('people:index')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_choices = [
            (str(company.public_id), company.name)
            for company in CompanyRepository.list_for_organization(self.request.active_organization)
        ]
        form = kwargs.get('form') or PersonUpdateForm(
            company_choices=company_choices,
            initial={
                'first_name': self.person.first_name,
                'last_name': self.person.last_name,
                'email': self.person.email,
                'phone': self.person.phone,
                'company_public_id': str(self.person.company.public_id) if self.person.company else '',
            }
        )
        context.update(
            {
                'person': self.person,
                'form': form,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        company_choices = [
            (str(company.public_id), company.name)
            for company in CompanyRepository.list_for_organization(request.active_organization)
        ]
        form = PersonUpdateForm(request.POST, company_choices=company_choices)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        company = None
        if form.cleaned_data['company_public_id']:
            company = CompanyRepository.get_for_organization_and_public_id(
                request.active_organization,
                form.cleaned_data['company_public_id'],
            )

        try:
            PersonService.update_person(
                user=request.user,
                organization=request.active_organization,
                person=self.person,
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                email=form.cleaned_data['email'],
                phone=form.cleaned_data['phone'],
                company=company,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else str(exc))
            return self.render_to_response(self.get_context_data(form=form))

        messages.success(request, 'Pessoa atualizada com sucesso.')
        return redirect('people:index')
