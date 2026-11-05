"""
Service layer for parking slot availability calculations and location metrics.
"""

from django.db.models import Q
from django.utils import timezone

from bookings.models import Booking
from .models import ParkingLocation, ParkingSlot

SLOT_STATUS_AVAILABLE = 'AVAILABLE'
SLOT_STATUS_OCCUPIED = 'OCCUPIED'
SLOT_STATUS_RESERVED = 'RESERVED'
SLOT_STATUS_INACTIVE = 'INACTIVE'


def get_slots_with_availability(location, target_time=None):
    """
    Calculate and return the availability status of all slots for a given parking location.

    Status resolution hierarchy:
    1. is_active == False -> INACTIVE (Gray)
    2. Booking status == ACTIVE (or currently checked in) -> OCCUPIED (Red)
    3. Booking status == CONFIRMED/PENDING overlapping target_time -> RESERVED (Yellow)
    4. Otherwise -> AVAILABLE (Green)

    Returns:
        tuple: (slot_data_list, stats_dict)
    """
    if target_time is None:
        target_time = timezone.now()

    slots = location.slots.all().order_by('slot_number')

    # Fetch active or overlapping reservations for this location in a single query
    relevant_bookings = Booking.objects.filter(
        location=location,
        status__in=[
            Booking.BookingStatus.ACTIVE,
            Booking.BookingStatus.CONFIRMED,
            Booking.BookingStatus.PENDING,
        ]
    ).filter(
        Q(status=Booking.BookingStatus.ACTIVE) |
        Q(start_time__lte=target_time, end_time__gte=target_time)
    ).values('id', 'slot_id', 'status', 'start_time', 'end_time', 'vehicle_number')

    occupied_slot_ids = set()
    reserved_slot_ids = set()
    booking_by_slot = {}

    for b in relevant_bookings:
        slot_id = b['slot_id']
        if b['status'] == Booking.BookingStatus.ACTIVE:
            occupied_slot_ids.add(slot_id)
            booking_by_slot[slot_id] = b
        elif b['status'] in [Booking.BookingStatus.CONFIRMED, Booking.BookingStatus.PENDING]:
            if slot_id not in occupied_slot_ids:
                reserved_slot_ids.add(slot_id)
                booking_by_slot[slot_id] = b

    slot_data_list = []
    available_count = 0
    occupied_count = 0
    reserved_count = 0
    inactive_count = 0

    car_available = 0
    bike_available = 0

    for slot in slots:
        if not slot.is_active:
            status = SLOT_STATUS_INACTIVE
            status_display = 'Inactive'
            css_class = 'slot-inactive'
            badge_class = 'bg-secondary'
            inactive_count += 1
        elif slot.id in occupied_slot_ids:
            status = SLOT_STATUS_OCCUPIED
            status_display = 'Occupied'
            css_class = 'slot-occupied'
            badge_class = 'bg-danger'
            occupied_count += 1
        elif slot.id in reserved_slot_ids:
            status = SLOT_STATUS_RESERVED
            status_display = 'Reserved'
            css_class = 'slot-reserved'
            badge_class = 'bg-warning text-dark'
            reserved_count += 1
        else:
            status = SLOT_STATUS_AVAILABLE
            status_display = 'Available'
            css_class = 'slot-available'
            badge_class = 'bg-success'
            available_count += 1
            if slot.slot_type == ParkingSlot.SlotType.CAR:
                car_available += 1
            else:
                bike_available += 1

        slot_data_list.append({
            'slot': slot,
            'status': status,
            'status_display': status_display,
            'css_class': css_class,
            'badge_class': badge_class,
            'current_booking': booking_by_slot.get(slot.id),
        })

    stats = {
        'total_slots': location.total_slots,
        'configured_slots': slots.count(),
        'active_slots_count': slots.filter(is_active=True).count(),
        'available_count': available_count,
        'occupied_count': occupied_count,
        'reserved_count': reserved_count,
        'inactive_count': inactive_count,
        'car_available': car_available,
        'bike_available': bike_available,
    }

    return slot_data_list, stats


def get_available_slots(location, target_time=None):
    """
    Return a QuerySet of active ParkingSlot objects for the given location
    that are neither currently occupied nor reserved at target_time.
    """
    if target_time is None:
        target_time = timezone.now()

    busy_slot_ids = Booking.objects.filter(
        location=location,
        status__in=[
            Booking.BookingStatus.ACTIVE,
            Booking.BookingStatus.CONFIRMED,
            Booking.BookingStatus.PENDING,
        ]
    ).filter(
        Q(status=Booking.BookingStatus.ACTIVE) |
        Q(start_time__lte=target_time, end_time__gte=target_time)
    ).values_list('slot_id', flat=True)

    return location.slots.filter(is_active=True).exclude(id__in=busy_slot_ids)


def get_locations_with_availability(target_time=None, query_text=None):
    """
    Fetch active ParkingLocations and compute available slot metrics dynamically.
    Optional query_text filters by name or address.
    """
    if target_time is None:
        target_time = timezone.now()

    locations = ParkingLocation.objects.filter(is_active=True)
    if query_text:
        locations = locations.filter(
            Q(name__icontains=query_text) |
            Q(address__icontains=query_text) |
            Q(description__icontains=query_text)
        )

    locations = locations.prefetch_related('slots')

    busy_slot_ids = set(
        Booking.objects.filter(
            status__in=[
                Booking.BookingStatus.ACTIVE,
                Booking.BookingStatus.CONFIRMED,
                Booking.BookingStatus.PENDING,
            ]
        ).filter(
            Q(status=Booking.BookingStatus.ACTIVE) |
            Q(start_time__lte=target_time, end_time__gte=target_time)
        ).values_list('slot_id', flat=True)
    )

    result = []
    for loc in locations:
        configured_slots = loc.slots.all()
        active_slots = [s for s in configured_slots if s.is_active]
        available_slots = [s for s in active_slots if s.id not in busy_slot_ids]

        result.append({
            'location': loc,
            'total_slots': loc.total_slots,
            'configured_slots_count': len(configured_slots),
            'active_slots_count': len(active_slots),
            'available_slots_count': len(available_slots),
        })

    return result

