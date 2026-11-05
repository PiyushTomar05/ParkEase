from django.contrib import admin
from .models import ParkingLocation, ParkingSlot


class ParkingSlotInline(admin.TabularInline):
    model = ParkingSlot
    extra = 1
    fields = ('slot_number', 'slot_type', 'is_active')


@admin.register(ParkingLocation)
class ParkingLocationAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'hourly_rate',
        'total_slots',
        'opening_time',
        'closing_time',
        'is_active',
        'created_at',
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'address', 'description')
    ordering = ('name',)
    inlines = [ParkingSlotInline]


@admin.register(ParkingSlot)
class ParkingSlotAdmin(admin.ModelAdmin):
    list_display = (
        'slot_number',
        'location',
        'slot_type',
        'is_active',
    )
    list_filter = ('location', 'slot_type', 'is_active')
    search_fields = ('slot_number', 'location__name')
    ordering = ('location', 'slot_number')
