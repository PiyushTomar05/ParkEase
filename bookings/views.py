from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from .forms import BookingForm
from .models import Booking
from .services import (
    calculate_booking_fee,
    get_available_slots_for_period,
    is_slot_available_for_period,
)
from parking.models import ParkingLocation, ParkingSlot


@login_required(login_url='login')
def create_booking_view(request):
    """
    Handle reservation creation for authenticated drivers.
    Enforces server-side concurrency checking within an atomic transaction.
    """
    initial_data = {}
    if request.method == 'GET':
        location_id = request.GET.get('location')
        slot_id = request.GET.get('slot')
        if location_id:
            try:
                initial_data['location'] = int(location_id)
            except (ValueError, TypeError):
                pass
        if slot_id:
            try:
                initial_data['slot'] = int(slot_id)
            except (ValueError, TypeError):
                pass

    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            slot = form.cleaned_data['slot']
            location = form.cleaned_data['location']
            start_time = form.cleaned_data['start_time']
            end_time = form.cleaned_data['end_time']

            # Double booking prevention with database transaction and row-level locking attempt
            with transaction.atomic():
                # On databases like PostgreSQL, select_for_update locks the row.
                # On SQLite, atomic() provides database-level transaction locking.
                try:
                    locked_slot = ParkingSlot.objects.select_for_update().get(pk=slot.pk)
                except Exception:
                    locked_slot = ParkingSlot.objects.get(pk=slot.pk)

                # Re-verify availability inside the transaction immediately before saving
                if not is_slot_available_for_period(locked_slot, start_time, end_time):
                    form.add_error(
                        'slot',
                        f"Slot '{locked_slot.slot_number}' was just reserved by another session for this time window. Please choose another slot."
                    )
                    return render(request, 'bookings/booking_form.html', {'form': form})

                booking = form.save(commit=False)
                # Assign authenticated user securely
                booking.user = request.user
                booking.location = location
                booking.slot = locked_slot
                # Authoritative server-side fee calculation using Decimal
                booking.total_amount = calculate_booking_fee(
                    location.hourly_rate,
                    start_time,
                    end_time
                )
                booking.status = Booking.BookingStatus.CONFIRMED
                booking.save()

            messages.success(
                request,
                f"Booking pass #{booking.id} created successfully for slot {booking.slot.slot_number} at {booking.location.name}!"
            )
            return redirect('booking_detail', pk=booking.pk)
    else:
        form = BookingForm(initial=initial_data)

    context = {
        'form': form,
    }
    return render(request, 'bookings/booking_form.html', context)


@login_required(login_url='login')
def booking_detail_view(request, pk):
    """
    Detailed booking confirmation pass.
    Accessible only to the booking owner or authorized staff users.
    """
    booking = get_object_or_404(
        Booking.objects.select_related('location', 'slot', 'user'),
        pk=pk
    )

    if booking.user != request.user and not request.user.is_staff:
        raise PermissionDenied("You do not have authorization to view this booking pass.")

    # Calculate duration
    duration = booking.end_time - booking.start_time
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    estimated_amount = calculate_booking_fee(
        booking.location.hourly_rate,
        booking.start_time,
        booking.end_time
    )

    actual_duration_str = None
    if booking.actual_entry_time:
        exit_time = booking.actual_exit_time or timezone.now()
        if exit_time > booking.actual_entry_time:
            act_dur = exit_time - booking.actual_entry_time
            act_sec = int(act_dur.total_seconds())
            act_h = act_sec // 3600
            act_m = (act_sec % 3600) // 60
            actual_duration_str = f"{act_h}h {act_m}m"

    context = {
        'booking': booking,
        'duration_hours': hours,
        'duration_minutes': minutes,
        'estimated_amount': estimated_amount,
        'actual_duration_str': actual_duration_str,
        'can_cancel': booking.status in [Booking.BookingStatus.PENDING, Booking.BookingStatus.CONFIRMED],
    }
    return render(request, 'bookings/booking_detail.html', context)


@login_required(login_url='login')
def my_bookings_view(request):
    """
    List all reservations belonging strictly to the currently authenticated driver.
    Supports filtering by booking status tabs.
    """
    status_filter = request.GET.get('status', '').upper()
    user_bookings = request.user.bookings.select_related('location', 'slot').all()

    # Calculate status counts for filter badges
    status_counts = {
        'ALL': user_bookings.count(),
        'PENDING': user_bookings.filter(status=Booking.BookingStatus.PENDING).count(),
        'CONFIRMED': user_bookings.filter(status=Booking.BookingStatus.CONFIRMED).count(),
        'ACTIVE': user_bookings.filter(status=Booking.BookingStatus.ACTIVE).count(),
        'COMPLETED': user_bookings.filter(status=Booking.BookingStatus.COMPLETED).count(),
        'CANCELLED': user_bookings.filter(status=Booking.BookingStatus.CANCELLED).count(),
    }

    if status_filter in Booking.BookingStatus.values:
        filtered_bookings = user_bookings.filter(status=status_filter)
    else:
        status_filter = 'ALL'
        filtered_bookings = user_bookings

    context = {
        'bookings': filtered_bookings,
        'status_filter': status_filter,
        'status_counts': status_counts,
    }
    return render(request, 'bookings/my_bookings.html', context)


@login_required(login_url='login')
@require_POST
def cancel_booking_view(request, pk):
    """
    Cancel an existing reservation.
    Only PENDING and CONFIRMED bookings may be cancelled.
    Restricted to booking owner or staff.
    """
    booking = get_object_or_404(Booking, pk=pk)

    if booking.user != request.user and not request.user.is_staff:
        raise PermissionDenied("You do not have permission to cancel this booking.")

    if booking.status not in [Booking.BookingStatus.PENDING, Booking.BookingStatus.CONFIRMED]:
        messages.error(
            request,
            f"Reservation #{booking.id} cannot be cancelled because it is already {booking.get_status_display().lower()}."
        )
        return redirect('booking_detail', pk=booking.pk)

    booking.status = Booking.BookingStatus.CANCELLED
    booking.save()

    messages.success(
        request,
        f"Reservation #{booking.id} for slot {booking.slot.slot_number} has been cancelled successfully."
    )
    return redirect('booking_detail', pk=booking.pk)


def available_slots_view(request):
    """
    AJAX endpoint returning active, non-overlapping slots for dynamic dropdown updates.
    """
    location_id = request.GET.get('location_id')
    vehicle_type = request.GET.get('vehicle_type')
    start_str = request.GET.get('start_time')
    end_str = request.GET.get('end_time')

    if not location_id:
        return JsonResponse({'slots': []})

    location = get_object_or_404(ParkingLocation, pk=location_id, is_active=True)

    start_dt = None
    end_dt = None
    if start_str:
        start_dt = parse_datetime(start_str)
        if start_dt and timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
    if end_str:
        end_dt = parse_datetime(end_str)
        if end_dt and timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)

    slots = get_available_slots_for_period(
        location=location,
        vehicle_type=vehicle_type,
        start_time=start_dt,
        end_time=end_dt
    )

    data = [
        {
            'id': s.id,
            'slot_number': s.slot_number,
            'slot_type': s.get_slot_type_display(),
        }
        for s in slots
    ]

    hourly_rate = float(location.hourly_rate)

    return JsonResponse({
        'slots': data,
        'hourly_rate': hourly_rate,
        'location_name': location.name,
    })
