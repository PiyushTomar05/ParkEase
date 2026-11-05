from datetime import datetime
from decimal import Decimal
from functools import wraps
import json

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from bookings.models import Booking
from bookings.services import calculate_actual_parking_fee
from .forms import ParkingLocationForm, ParkingSlotForm
from .models import ParkingLocation, ParkingSlot
from .services import (
    get_locations_with_availability,
    get_slots_with_availability,
)


def staff_required(view_func):
    """
    Decorator requiring an authenticated user with is_staff=True.
    Redirects anonymous users to the login page.
    Raises PermissionDenied (HTTP 403) for authenticated non-staff users.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url='login')
        if not request.user.is_staff:
            raise PermissionDenied("Administrative privileges are required to access this resource.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# -----------------------------------------------------------------------------
# Public Views
# -----------------------------------------------------------------------------

def location_list_view(request):
    """
    Public listing of active parking facilities with live availability stats.
    Supports optional search querying by name or address.
    """
    search_query = request.GET.get('q', '').strip()
    locations_data = get_locations_with_availability(query_text=search_query)

    context = {
        'locations_data': locations_data,
        'search_query': search_query,
    }
    return render(request, 'parking/location_list.html', context)


def location_detail_view(request, pk):
    """
    Detailed view for a specific parking facility showing real-time slot grid
    with color-coded availability (Green=Available, Red=Occupied, Yellow=Reserved, Gray=Inactive).
    """
    if request.user.is_authenticated and request.user.is_staff:
        location = get_object_or_404(ParkingLocation, pk=pk)
    else:
        location = get_object_or_404(ParkingLocation, pk=pk, is_active=True)

    slot_data_list, stats = get_slots_with_availability(location)

    context = {
        'location': location,
        'slot_data_list': slot_data_list,
        'stats': stats,
    }
    return render(request, 'parking/location_detail.html', context)


# -----------------------------------------------------------------------------
# Staff Administrative Views - Parking Locations
# -----------------------------------------------------------------------------

@staff_required
def manage_locations_view(request):
    """
    Administrative overview of all registered parking locations with management actions.
    Leverages prefetched slots cache to avoid N+1 queries.
    """
    locations = ParkingLocation.objects.all().prefetch_related('slots').order_by('name')

    locations_list = []
    for loc in locations:
        all_slots = loc.slots.all()
        configured = len(all_slots)
        active = sum(1 for s in all_slots if s.is_active)
        locations_list.append({
            'location': loc,
            'configured_slots': configured,
            'active_slots': active,
        })

    context = {
        'locations_list': locations_list,
        'total_locations': len(locations_list),
    }
    return render(request, 'parking/manage_locations.html', context)


@staff_required
def add_location_view(request):
    """
    Create a new parking location facility.
    """
    if request.method == 'POST':
        form = ParkingLocationForm(request.POST)
        if form.is_valid():
            location = form.save()
            messages.success(request, f"Parking location '{location.name}' created successfully!")
            return redirect('manage_locations')
    else:
        form = ParkingLocationForm()

    context = {
        'form': form,
        'title': 'Add Parking Location',
        'is_edit': False,
    }
    return render(request, 'parking/location_form.html', context)


@staff_required
def edit_location_view(request, pk):
    """
    Edit details of an existing parking location.
    """
    location = get_object_or_404(ParkingLocation, pk=pk)

    if request.method == 'POST':
        form = ParkingLocationForm(request.POST, instance=location)
        if form.is_valid():
            location = form.save()
            messages.success(request, f"Parking location '{location.name}' updated successfully!")
            return redirect('manage_locations')
    else:
        form = ParkingLocationForm(instance=location)

    context = {
        'form': form,
        'location': location,
        'title': f'Edit Location: {location.name}',
        'is_edit': True,
    }
    return render(request, 'parking/location_form.html', context)


@staff_required
@require_POST
def toggle_location_status_view(request, pk):
    """
    Activate or deactivate a parking facility via secure POST request.
    """
    location = get_object_or_404(ParkingLocation, pk=pk)
    location.is_active = not location.is_active
    location.save()

    status_str = "activated" if location.is_active else "deactivated"
    messages.success(request, f"Parking location '{location.name}' has been {status_str}.")
    return redirect('manage_locations')


# -----------------------------------------------------------------------------
# Staff Administrative Views - Parking Slots
# -----------------------------------------------------------------------------

@staff_required
def manage_slots_view(request, location_id):
    """
    Administrative management view for all slots within a parking facility.
    Supports filtering by slot_type and active status.
    """
    location = get_object_or_404(ParkingLocation, pk=location_id)
    slot_data_list, stats = get_slots_with_availability(location)

    # Optional filtering
    slot_type_filter = request.GET.get('type')
    status_filter = request.GET.get('status')

    if slot_type_filter:
        slot_data_list = [d for d in slot_data_list if d['slot'].slot_type == slot_type_filter]
    if status_filter:
        if status_filter.upper() == 'ACTIVE':
            slot_data_list = [d for d in slot_data_list if d['slot'].is_active]
        elif status_filter.upper() == 'INACTIVE':
            slot_data_list = [d for d in slot_data_list if not d['slot'].is_active]
        elif status_filter.upper() in ['AVAILABLE', 'OCCUPIED', 'RESERVED']:
            slot_data_list = [d for d in slot_data_list if d['status'] == status_filter.upper()]

    context = {
        'location': location,
        'slot_data_list': slot_data_list,
        'stats': stats,
        'slot_type_filter': slot_type_filter,
        'status_filter': status_filter,
    }
    return render(request, 'parking/manage_slots.html', context)


@staff_required
def add_slot_view(request, location_id):
    """
    Add a new parking slot to a facility.
    """
    location = get_object_or_404(ParkingLocation, pk=location_id)

    if request.method == 'POST':
        form = ParkingSlotForm(request.POST, location=location)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.location = location
            slot.save()
            messages.success(
                request,
                f"Slot '{slot.slot_number}' ({slot.get_slot_type_display()}) added to {location.name}!"
            )
            return redirect('manage_slots', location_id=location.id)
    else:
        form = ParkingSlotForm(location=location)

    context = {
        'form': form,
        'location': location,
        'title': f'Add Parking Slot — {location.name}',
        'is_edit': False,
    }
    return render(request, 'parking/slot_form.html', context)


@staff_required
def edit_slot_view(request, pk):
    """
    Edit an existing parking slot.
    """
    slot = get_object_or_404(ParkingSlot, pk=pk)
    location = slot.location

    if request.method == 'POST':
        form = ParkingSlotForm(request.POST, instance=slot, location=location)
        if form.is_valid():
            slot = form.save()
            messages.success(request, f"Slot '{slot.slot_number}' updated successfully!")
            return redirect('manage_slots', location_id=location.id)
    else:
        form = ParkingSlotForm(instance=slot, location=location)

    context = {
        'form': form,
        'slot': slot,
        'location': location,
        'title': f'Edit Slot {slot.slot_number} — {location.name}',
        'is_edit': True,
    }
    return render(request, 'parking/slot_form.html', context)


@staff_required
@require_POST
def toggle_slot_status_view(request, pk):
    """
    Activate or deactivate a slot via secure POST request.
    """
    slot = get_object_or_404(ParkingSlot, pk=pk)
    location_id = slot.location_id
    slot.is_active = not slot.is_active
    slot.save()

    status_str = "activated" if slot.is_active else "deactivated"
    messages.success(request, f"Slot '{slot.slot_number}' has been {status_str}.")
    return redirect('manage_slots', location_id=location_id)


# -----------------------------------------------------------------------------
# Staff Parking Operations & Admin Analytics Dashboard
# -----------------------------------------------------------------------------

@staff_required
def operations_dashboard_view(request):
    """
    Comprehensive staff parking operations and analytics dashboard.
    Displays facility metrics, occupancy, realized revenue stats,
    Chart.js visual summaries, and an interactive operations booking table.
    """
    now = timezone.now()
    today = now.date()

    # 1. Facility & Slot Availability Metrics
    locations_data = get_locations_with_availability(target_time=now)
    total_locations = ParkingLocation.objects.count()
    active_locations = sum(1 for loc in locations_data if loc['location'].is_active)
    total_slots = ParkingSlot.objects.count()
    active_slots = sum(loc['active_slots_count'] for loc in locations_data)
    total_available_slots = sum(loc['available_slots_count'] for loc in locations_data)

    # 2. Operational Bay Metrics
    active_sessions_count = Booking.objects.filter(
        status=Booking.BookingStatus.ACTIVE
    ).count()

    reserved_bays_count = Booking.objects.filter(
        status__in=[Booking.BookingStatus.CONFIRMED, Booking.BookingStatus.PENDING],
        start_time__lte=now,
        end_time__gte=now
    ).values('slot_id').distinct().count()

    # 3. Revenue & Completed Sessions Reporting (COMPLETED bookings strictly)
    completed_qs = Booking.objects.filter(status=Booking.BookingStatus.COMPLETED)

    today_completed_count = completed_qs.filter(actual_exit_time__date=today).count()
    today_revenue = (
        completed_qs.filter(actual_exit_time__date=today)
        .aggregate(Sum('total_amount'))['total_amount__sum']
        or Decimal('0.00')
    )

    month_revenue = (
        completed_qs.filter(
            actual_exit_time__year=now.year,
            actual_exit_time__month=now.month
        ).aggregate(Sum('total_amount'))['total_amount__sum']
        or Decimal('0.00')
    )

    total_completed_revenue = (
        completed_qs.aggregate(Sum('total_amount'))['total_amount__sum']
        or Decimal('0.00')
    )
    total_completed_sessions = completed_qs.count()

    # 4. Chart 1: Daily Revenue for the past 7 days (including today)
    daily_revenue_labels = []
    daily_revenue_data = []
    for i in range(6, -1, -1):
        day = today - timezone.timedelta(days=i)
        day_str = day.strftime('%b %d')
        day_rev = (
            completed_qs.filter(actual_exit_time__date=day)
            .aggregate(Sum('total_amount'))['total_amount__sum']
            or Decimal('0.00')
        )
        daily_revenue_labels.append(day_str)
        daily_revenue_data.append(float(day_rev))

    # 5. Chart 2: Booking Status Distribution
    status_counts_dict = {
        'CONFIRMED': Booking.objects.filter(status=Booking.BookingStatus.CONFIRMED).count(),
        'ACTIVE': active_sessions_count,
        'COMPLETED': total_completed_sessions,
        'CANCELLED': Booking.objects.filter(status=Booking.BookingStatus.CANCELLED).count(),
    }
    status_labels = ['Confirmed', 'Active', 'Completed', 'Cancelled']
    status_counts = [
        status_counts_dict['CONFIRMED'],
        status_counts_dict['ACTIVE'],
        status_counts_dict['COMPLETED'],
        status_counts_dict['CANCELLED'],
    ]

    # 6. Operations Booking Table Queryset and Filters
    bookings_qs = Booking.objects.select_related('user', 'location', 'slot').all().order_by('-created_at')

    # Status filter
    status_filter = request.GET.get('status', '').strip().upper()
    if status_filter and status_filter in Booking.BookingStatus.values:
        bookings_qs = bookings_qs.filter(status=status_filter)

    # Location filter
    location_filter = request.GET.get('location', '').strip()
    if location_filter and location_filter.isdigit():
        bookings_qs = bookings_qs.filter(location_id=int(location_filter))

    # Vehicle type filter
    vehicle_type_filter = request.GET.get('vehicle_type', '').strip().upper()
    if vehicle_type_filter and vehicle_type_filter in Booking.VehicleType.values:
        bookings_qs = bookings_qs.filter(vehicle_type=vehicle_type_filter)

    # Date filter
    date_filter = request.GET.get('date', '').strip()
    if date_filter:
        try:
            parsed_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            bookings_qs = bookings_qs.filter(
                Q(start_time__date=parsed_date) |
                Q(actual_entry_time__date=parsed_date) |
                Q(created_at__date=parsed_date)
            )
        except ValueError:
            pass

    # Search filter
    search_query = request.GET.get('q', '').strip()
    if search_query:
        if search_query.isdigit():
            bookings_qs = bookings_qs.filter(
                Q(id=int(search_query)) |
                Q(vehicle_number__icontains=search_query) |
                Q(user__username__icontains=search_query) |
                Q(location__name__icontains=search_query)
            )
        else:
            bookings_qs = bookings_qs.filter(
                Q(vehicle_number__icontains=search_query) |
                Q(user__username__icontains=search_query) |
                Q(location__name__icontains=search_query)
            )

    # 7. Pagination (15 bookings per page)
    paginator = Paginator(bookings_qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Clean query parameters for pagination URLs
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    filter_querystring = query_params.urlencode()

    all_locations = ParkingLocation.objects.all().order_by('name')

    context = {
        # Metrics
        'total_locations': total_locations,
        'active_locations': active_locations,
        'total_slots': total_slots,
        'active_slots': active_slots,
        'total_available_slots': total_available_slots,
        'occupied_bays_count': active_sessions_count,
        'reserved_bays_count': reserved_bays_count,
        'active_sessions_count': active_sessions_count,
        'today_completed_count': today_completed_count,
        # Revenue summary
        'today_revenue': today_revenue,
        'month_revenue': month_revenue,
        'total_completed_revenue': total_completed_revenue,
        'total_completed_sessions': total_completed_sessions,
        # Chart JSON data
        'daily_revenue_labels': json.dumps(daily_revenue_labels),
        'daily_revenue_data': json.dumps(daily_revenue_data),
        'status_labels': json.dumps(status_labels),
        'status_counts': json.dumps(status_counts),
        # Table & filters
        'page_obj': page_obj,
        'bookings': page_obj.object_list,
        'all_locations': all_locations,
        'filter_querystring': filter_querystring,
        'selected_status': status_filter,
        'selected_location': location_filter,
        'selected_vehicle_type': vehicle_type_filter,
        'selected_date': date_filter,
        'search_query': search_query,
        'vehicle_types': Booking.VehicleType.choices,
        'booking_statuses': Booking.BookingStatus.choices,
    }
    return render(request, 'parking/operations_dashboard.html', context)


@staff_required
@require_POST
def check_in_booking_view(request, pk):
    """
    Staff-only check-in action.
    Transitions a CONFIRMED booking to ACTIVE, validating facility and bay status.
    Records actual_entry_time as timezone.now().
    """
    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_related('location', 'slot', 'user'),
            pk=pk
        )

        if booking.status != Booking.BookingStatus.CONFIRMED:
            messages.error(
                request,
                f"Booking #{booking.id} cannot be checked in because its current status is '{booking.get_status_display()}'. Only CONFIRMED bookings are eligible for check-in."
            )
            return redirect('booking_detail', pk=booking.id)

        if not booking.location.is_active:
            messages.error(
                request,
                f"Cannot check in booking #{booking.id}: Parking facility '{booking.location.name}' is currently inactive."
            )
            return redirect('booking_detail', pk=booking.id)

        if not booking.slot.is_active:
            messages.error(
                request,
                f"Cannot check in booking #{booking.id}: Allocated bay '{booking.slot.slot_number}' is currently inactive."
            )
            return redirect('booking_detail', pk=booking.id)

        if booking.actual_entry_time is not None:
            messages.error(
                request,
                f"Booking #{booking.id} already has a recorded check-in timestamp."
            )
            return redirect('booking_detail', pk=booking.id)

        booking.actual_entry_time = timezone.now()
        booking.status = Booking.BookingStatus.ACTIVE
        booking.save(update_fields=['actual_entry_time', 'status'])

        messages.success(
            request,
            f"Check-in successful! Vehicle '{booking.vehicle_number}' checked into Bay {booking.slot.slot_number} at {booking.location.name}."
        )
        return redirect('booking_detail', pk=booking.id)


@staff_required
@require_POST
def check_out_booking_view(request, pk):
    """
    Staff-only check-out action.
    Transitions an ACTIVE booking to COMPLETED.
    Records actual_exit_time and computes total_amount based on actual parked duration.
    """
    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_related('location', 'slot', 'user'),
            pk=pk
        )

        if booking.status != Booking.BookingStatus.ACTIVE:
            messages.error(
                request,
                f"Booking #{booking.id} cannot be checked out because its current status is '{booking.get_status_display()}'. Only ACTIVE sessions can be checked out."
            )
            return redirect('booking_detail', pk=booking.id)

        if not booking.actual_entry_time:
            messages.error(
                request,
                f"Booking #{booking.id} has no valid check-in entry timestamp."
            )
            return redirect('booking_detail', pk=booking.id)

        if booking.actual_exit_time is not None:
            messages.error(
                request,
                f"Booking #{booking.id} has already been checked out."
            )
            return redirect('booking_detail', pk=booking.id)

        now = timezone.now()
        # Guarantee exit time is strictly later than entry time
        if now <= booking.actual_entry_time:
            now = booking.actual_entry_time + timezone.timedelta(seconds=1)

        actual_fee = calculate_actual_parking_fee(
            booking.location.hourly_rate,
            booking.actual_entry_time,
            now
        )

        booking.actual_exit_time = now
        booking.total_amount = actual_fee
        booking.status = Booking.BookingStatus.COMPLETED
        booking.save(update_fields=['actual_exit_time', 'total_amount', 'status'])

        messages.success(
            request,
            f"Check-out completed for Vehicle '{booking.vehicle_number}'! Total actual parking fee billed: ₹{actual_fee}."
        )
        return redirect('booking_detail', pk=booking.id)
