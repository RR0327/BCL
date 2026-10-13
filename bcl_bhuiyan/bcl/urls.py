from django.urls import path
from . import views

app_name = 'bcl'

urlpatterns = [
    path('', views.home, name='home'),
]
