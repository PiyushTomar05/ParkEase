from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_booking_view, name='create_booking'),
    path('my-bookings/', views.my_bookings_view, name='my_bookings'),
    path('available-slots/', views.available_slots_view, name='available_slots'),
    path('<int:pk>/', views.booking_detail_view, name='booking_detail'),
    path('<int:pk>/cancel/', views.cancel_booking_view, name='cancel_booking'),
]

