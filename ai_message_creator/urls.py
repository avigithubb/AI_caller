from django.urls import path
from . import views

urlpatterns = [
    path("call/gemini/", views.call_gemini),
    path("template/", views.generate_templates),
]