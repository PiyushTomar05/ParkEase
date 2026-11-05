from django.urls import path
from . import views

urlpatterns = [
    # Public views
    path('', views.location_list_view, name='location_list'),
    path('locations/<int:pk>/', views.location_detail_view, name='location_detail'),

    # Administrative parking location management views
    path('manage/', views.manage_locations_view, name='manage_locations'),
    path('manage/add/', views.add_location_view, name='add_location'),
    path('manage/<int:pk>/edit/', views.edit_location_view, name='edit_location'),
    path('manage/<int:pk>/toggle-status/', views.toggle_location_status_view, name='toggle_location_status'),

    # Administrative slot management views
    path('manage/<int:location_id>/slots/', views.manage_slots_view, name='manage_slots'),
    path('manage/<int:location_id>/slots/add/', views.add_slot_view, name='add_slot'),
    path('manage/slots/<int:pk>/edit/', views.edit_slot_view, name='edit_slot'),
    path('manage/slots/<int:pk>/toggle-status/', views.toggle_slot_status_view, name='toggle_slot_status'),

    # Administrative parking operations and dashboard views
    path('operations/', views.operations_dashboard_view, name='operations_dashboard'),
    path('operations/bookings/<int:pk>/check-in/', views.check_in_booking_view, name='check_in_booking'),
    path('operations/bookings/<int:pk>/check-out/', views.check_out_booking_view, name='check_out_booking'),
]

