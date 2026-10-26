from django.urls import path
from . import views

urlpatterns = [
    path("make-call/", views.make_call),
    path("trial/", views.make_call),
    path("vonage/event/", views.vonage_event),
    path("status/<uuid:call_id>/", views.call_status)
]