"""
URL configuration for evalink project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('admin/', admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path('features.json', views.features, name='features'),
    path('texts.json', views.texts, name='texts'),
    path('path.json', views.path, name='path'),
    path('point', views.point, name='point'),
    path('inventory/', views.inventory, name='inventory'),
    path('search/', views.search, name='search'),
    path('chat/', views.chat, name='chat'),
    path('campuses.json', views.campuses, name='campuses'),
    path('add-location-to-plan', views.add_location_to_plan, name='add_location_to_plan'),
    path('delete-planner-point', views.delete_planner_point, name='delete_planner_point'),
    path('eva-statistics/', views.eva_statistics, name='eva_statistics'),
    path('oldest-consecutive-inside', views.oldest_consecutive_inside, name='oldest_consecutive_inside'),
    path('clear-redundant-logs', views.clear_redundant_logs, name='clear_redundant_logs'),
    path('aircraft.json', views.aircraft, name='aircraft'),
    path('aprs.json', views.aprs, name='aprs'),
]
