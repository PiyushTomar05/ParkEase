"""
Business logic and services for booking fees and slot availability validation.
"""

from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone

from .models import Booking
from parking.models import ParkingSlot


def calculate_booking_fee(hourly_rate, start_time, end_time):
    """
    Calculate the total reservation fee proportionally based on exact duration.

    Calculation logic:
    1. Calculate duration in seconds = (end_time - start_time).total_seconds()
    2. Convert to fractional hours = duration_seconds / 3600
    3. Total Fee = hourly_rate * hours
    4. Round to 2 decimal places using Decimal ROUND_HALF_UP.

    Example:
        Rate: ₹30.00/hr, Duration: 2.5 hours (2h 30m)
        Total: 30 * 2.5 = ₹75.00
    """
    if not start_time or not end_time or end_time <= start_time:
        return Decimal('0.00')

    duration_seconds = Decimal(str((end_time - start_time).total_seconds()))
    hours = duration_seconds / Decimal('3600')
    rate = Decimal(str(hourly_rate))
    total_fee = (rate * hours).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return total_fee


def calculate_actual_parking_fee(hourly_rate, actual_entry_time, actual_exit_time):
    """
    Calculate final parking fee based on actual parked duration.
    Duration = (actual_exit_time - actual_entry_time).total_seconds() / 3600
    Uses Decimal with ROUND_HALF_UP rounding.
    Raises ValueError if actual_exit_time <= actual_entry_time.
    """
    if not actual_entry_time or not actual_exit_time or actual_exit_time <= actual_entry_time:
        raise ValueError("Exit time must be strictly later than entry time.")

    duration_seconds = Decimal(str((actual_exit_time - actual_entry_time).total_seconds()))
    hours = duration_seconds / Decimal('3600')
    rate = Decimal(str(hourly_rate))
    total_fee = (rate * hours).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return total_fee


def is_slot_available_for_period(slot, start_time, end_time, exclude_booking_id=None):
    """
    Verify whether a parking slot is free from overlapping blocking reservations.

    Overlap condition:
        existing_start < requested_end AND existing_end > requested_start

    Blocking statuses:
        - PENDING
        - CONFIRMED
        - ACTIVE

    Non-blocking statuses:
        - CANCELLED
        - COMPLETED

    Args:
        slot (ParkingSlot): The slot to check.
        start_time (datetime): Reservation start time.
        end_time (datetime): Reservation end time.
        exclude_booking_id (int, optional): ID of a booking to exclude (e.g. when editing).

    Returns:
        bool: True if slot is available, False if conflicting reservation exists or slot/location is inactive.
    """
    if not slot or not slot.is_active:
        return False

    if not slot.location.is_active:
        return False

    if not start_time or not end_time or end_time <= start_time:
        return False

    blocking_statuses = [
        Booking.BookingStatus.PENDING,
        Booking.BookingStatus.CONFIRMED,
        Booking.BookingStatus.ACTIVE,
    ]

    conflicting_bookings = Booking.objects.filter(
        slot=slot,
        status__in=blocking_statuses,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )

    if exclude_booking_id:
        conflicting_bookings = conflicting_bookings.exclude(pk=exclude_booking_id)

    if conflicting_bookings.exists():
        return False

    # Harmonize with live bay occupancy: if bay has an active vehicle session
    # and the requested window starts now or in the past, bay is occupied
    now = timezone.now()
    if start_time <= now:
        active_session = Booking.objects.filter(
            slot=slot,
            status=Booking.BookingStatus.ACTIVE
        )
        if exclude_booking_id:
            active_session = active_session.exclude(pk=exclude_booking_id)
        if active_session.exists():
            return False

    return True


def get_available_slots_for_period(location, vehicle_type=None, start_time=None, end_time=None, exclude_booking_id=None):
    """
    Query active slots belonging to a location that are not blocked by overlapping reservations.

    Args:
        location (ParkingLocation): Location to query.
        vehicle_type (str, optional): 'CAR' or 'BIKE'.
        start_time (datetime, optional): Window start.
        end_time (datetime, optional): Window end.
        exclude_booking_id (int, optional): Current booking ID to exclude.

    Returns:
        QuerySet: Available ParkingSlot instances.
    """
    if not location or not location.is_active:
        return ParkingSlot.objects.none()

    slots = ParkingSlot.objects.filter(location=location, is_active=True)

    if vehicle_type:
        slots = slots.filter(slot_type=vehicle_type)

    if start_time and end_time and end_time > start_time:
        blocking_statuses = [
            Booking.BookingStatus.PENDING,
            Booking.BookingStatus.CONFIRMED,
            Booking.BookingStatus.ACTIVE,
        ]

        busy_bookings = Booking.objects.filter(
            location=location,
            status__in=blocking_statuses,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )

        if exclude_booking_id:
            busy_bookings = busy_bookings.exclude(pk=exclude_booking_id)

        busy_slot_ids = set(busy_bookings.values_list('slot_id', flat=True))

        now = timezone.now()
        if start_time <= now:
            active_ids = Booking.objects.filter(
                location=location,
                status=Booking.BookingStatus.ACTIVE
            )
            if exclude_booking_id:
                active_ids = active_ids.exclude(pk=exclude_booking_id)
            busy_slot_ids.update(active_ids.values_list('slot_id', flat=True))

        slots = slots.exclude(id__in=busy_slot_ids)

    return slots.order_by('slot_number')

