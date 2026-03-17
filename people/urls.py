from django.urls import path

from people.views import PeopleListView, PersonCreateView, PersonUpdateView

app_name = 'people'

urlpatterns = [
    path('people/', PeopleListView.as_view(), name='index'),
    path('people/create/', PersonCreateView.as_view(), name='create'),
    path('people/<uuid:person_public_id>/edit/', PersonUpdateView.as_view(), name='edit'),
]
