from django.contrib import admin
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'location',
        'slot',
        'vehicle_number',
        'vehicle_type',
        'start_time',
        'end_time',
        'status',
        'total_amount',
        'created_at',
    )
    list_filter = (
        'status',
        'vehicle_type',
        'location',
        'created_at',
    )
    search_fields = (
        'vehicle_number',
        'user__username',
        'user__email',
        'location__name',
        'slot__slot_number',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'start_time'
