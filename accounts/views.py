from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from bookings.models import Booking
from parking.models import ParkingLocation, ParkingSlot
from .forms import UserLoginForm, UserRegisterForm


def get_user_dashboard_redirect(user):
    """
    Determine the appropriate landing dashboard URL based on the user's role:
    - Staff administrators and superusers redirect to the staff operations dashboard.
    - Regular customers redirect to the customer driver dashboard.
    """
    if user.is_staff or user.is_superuser:
        return 'operations_dashboard'
    return 'dashboard'


def register_view(request):
    """
    Handle user registration.
    Redirects already authenticated users to their role-appropriate dashboard.
    """
    if request.user.is_authenticated:
        return redirect(get_user_dashboard_redirect(request.user))

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f"Account created successfully for {user.username}! Please log in below."
            )
            return redirect('login')
    else:
        form = UserRegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    """
    Handle user login via Django's authentication system.
    Redirects already authenticated users to their role-appropriate dashboard:
    - Staff administrators and superusers -> operations_dashboard
    - Customers -> customer dashboard
    - Preserves intended 'next' destination when it is safe, valid, and not the landing page.
    """
    if request.user.is_authenticated:
        return redirect(get_user_dashboard_redirect(request.user))

    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")

            # Redirect to 'next' URL if safe, otherwise default to role-appropriate dashboard
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure()
            ):
                # If next_url points to landing page ('/' or reverse('home')), redirect to role dashboard instead
                if next_url not in ['/', reverse('home')]:
                    return redirect(next_url)

            return redirect(get_user_dashboard_redirect(user))
    else:
        form = UserLoginForm(request)

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """
    Handle user logout strictly via POST request.
    Rejects or redirects GET requests to adhere to secure logout requirements.
    """
    if request.method == 'POST':
        logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect('home')

    # Guard against accidental GET requests
    messages.warning(request, "Logout must be submitted via a secure POST request.")
    return redirect('home')


@login_required(login_url='login')
def dashboard_view(request):
    """
    Authenticated user dashboard.
    Renders a role-tailored interface:
    - Staff / Superusers receive operational management metrics, quick facility links,
      and system-wide recent reservation activity.
    - Standard drivers receive personal booking statistics, quick reservation links,
      and their personal booking history.
    """
    user_bookings = request.user.bookings.select_related('location', 'slot').all()
    now = timezone.now()

    personal_total_bookings = user_bookings.count()
    personal_active_bookings = user_bookings.filter(status=Booking.BookingStatus.ACTIVE)
    personal_upcoming_bookings = user_bookings.filter(
        status__in=[Booking.BookingStatus.CONFIRMED, Booking.BookingStatus.PENDING],
        start_time__gte=now
    ).order_by('start_time')
    personal_recent_bookings = user_bookings.order_by('-created_at')[:5]

    if request.user.is_staff:
        # Staff and Administrator view: system-wide metrics and operations
        system_total_bookings = Booking.objects.count()
        system_active_bookings = Booking.objects.filter(status=Booking.BookingStatus.ACTIVE).count()
        system_upcoming_bookings = Booking.objects.filter(
            status__in=[Booking.BookingStatus.CONFIRMED, Booking.BookingStatus.PENDING],
            start_time__gte=now
        ).count()
        total_locations = ParkingLocation.objects.count()
        active_locations = ParkingLocation.objects.filter(is_active=True).count()
        total_slots = ParkingSlot.objects.count()
        active_slots = ParkingSlot.objects.filter(is_active=True).count()
        recent_system_bookings = Booking.objects.select_related('user', 'location', 'slot').order_by('-created_at')[:6]

        context = {
            'is_staff_dashboard': True,
            'is_superuser': request.user.is_superuser,
            # System Metrics
            'total_bookings': system_total_bookings,
            'active_count': system_active_bookings,
            'upcoming_count': system_upcoming_bookings,
            'total_locations': total_locations,
            'active_locations': active_locations,
            'total_slots': total_slots,
            'active_slots': active_slots,
            'recent_system_bookings': recent_system_bookings,
            # Personal bookings preserved for staff if needed
            'personal_total_bookings': personal_total_bookings,
            'personal_active_count': personal_active_bookings.count(),
            'personal_upcoming_count': personal_upcoming_bookings.count(),
        }
    else:
        # Customer / Driver view: personal reservations and search
        context = {
            'is_staff_dashboard': False,
            'is_superuser': False,
            'total_bookings': personal_total_bookings,
            'active_bookings': personal_active_bookings,
            'active_count': personal_active_bookings.count(),
            'upcoming_bookings': personal_upcoming_bookings,
            'upcoming_count': personal_upcoming_bookings.count(),
            'recent_bookings': personal_recent_bookings,
        }

    return render(request, 'accounts/dashboard.html', context)
