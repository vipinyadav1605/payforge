from django.contrib import admin
from django.urls import path

urlpatterns = [path("", admin.site.urls)]  # the admin IS the app: served at the site root
