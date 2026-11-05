"""
Django Management Command: seed_demo_data

Seeds realistic demonstration data for ParkEase Smart Parking Management System,
specifically tailored for 7th-semester academic project evaluations.

Created roles:
1. Admin (Superuser + Staff) -> demo_admin
2. Parking Staff (Staff Operator) -> demo_staff
3. Driver (Customer) -> demo_driver

Features:
- Idempotent: Can be run multiple times safely without creating duplicates.
- Non-destructive: Does not wipe existing production/user data.
- Flexible credentials: Reads --password argument or PARKEASE_DEMO_PASSWORD env var.
- Realistic scenarios: Generates locations, car/bike slots, and bookings
  across all 4 statuses (CONFIRMED, ACTIVE, COMPLETED, CANCELLED) with
  valid timestamps, fee calculations, and no conflicting slot reservations.
"""

import os
from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from bookings.models import Booking
from bookings.services import (
    calculate_actual_parking_fee,
    calculate_booking_fee,
)
from parking.models import ParkingLocation, ParkingSlot

User = get_user_model()


class Command(BaseCommand):
    help = "Seed realistic demonstration data (users, locations, slots, bookings) for academic evaluation."

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            type=str,
            default=None,
            help='Password for demo users. Defaults to PARKEASE_DEMO_PASSWORD env var or "ParkEase@Demo2026".'
        )
        parser.add_argument(
            '--reset-passwords',
            action='store_true',
            help='Force-reset passwords of existing demo user accounts to the demo password.'
        )
        parser.add_argument(
            '--no-bookings',
            action='store_true',
            help='Seed only locations, slots, and users without creating demo bookings.'
        )
        parser.add_argument(
            '--keep-times',
            action='store_true',
            help='Do not update timestamps of existing demo bookings to be relative to the current time.'
        )

    def handle(self, *args, **options):
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS("  ParkEase: Seeding Realistic Academic Demonstration Data"))
        self.stdout.write("=" * 70)

        # 1. Resolve Demo Password
        demo_password = options['password'] or os.environ.get('PARKEASE_DEMO_PASSWORD')
        if not demo_password:
            demo_password = 'ParkEase@Demo2026'
            self.stdout.write(
                self.style.NOTICE(
                    "[*] No password provided via --password or PARKEASE_DEMO_PASSWORD.\n"
                    f"    Using evaluation demo default: '{demo_password}'"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("[*] Using configured demo password from argument / environment.")
            )

        reset_passwords = options['reset_passwords']
        skip_bookings = options['no_bookings']
        keep_times = options['keep_times']

        with transaction.atomic():
            # 2. Seed Users
            users = self._seed_users(demo_password, reset_passwords)

            # 3. Seed Parking Locations and Slots
            locations = self._seed_locations_and_slots()

            # 4. Seed Demo Bookings
            if not skip_bookings:
                self._seed_demo_bookings(users['driver'], locations, keep_times)
            else:
                self.stdout.write(self.style.NOTICE("[*] Skipping demo bookings as requested (--no-bookings)."))

        # 5. Output Summary Guide
        self._print_summary(demo_password, users)

    def _seed_users(self, demo_password, reset_passwords):
        """Create or reuse demo users for Admin, Staff, and Driver roles."""
        self.stdout.write("\n[1/3] Setting up Demo Users...")

        user_definitions = [
            {
                'key': 'admin',
                'username': 'demo_admin',
                'email': 'admin@parkease.demo',
                'first_name': 'ParkEase',
                'last_name': 'Administrator',
                'is_staff': True,
                'is_superuser': True,
                'role_title': 'System Administrator (Full Access)',
            },
            {
                'key': 'staff',
                'username': 'demo_staff',
                'email': 'staff@parkease.demo',
                'first_name': 'Operations',
                'last_name': 'Staff',
                'is_staff': True,
                'is_superuser': False,
                'role_title': 'Parking Staff (Operations & Check-In/Out)',
            },
            {
                'key': 'driver',
                'username': 'demo_driver',
                'email': 'driver@parkease.demo',
                'first_name': 'Rahul',
                'last_name': 'Sharma',
                'is_staff': False,
                'is_superuser': False,
                'role_title': 'Driver / Customer (Booking & History)',
            },
        ]

        seeded_users = {}

        for udata in user_definitions:
            user = User.objects.filter(username=udata['username']).first()
            if user:
                self.stdout.write(
                    self.style.WARNING(
                        f"  -> Reusing existing user: '{user.username}' ({udata['role_title']})"
                    )
                )
                if reset_passwords:
                    user.set_password(demo_password)
                    user.save()
                    self.stdout.write(f"     Updated password to demo password for '{user.username}'.")
            else:
                user = User.objects.create_user(
                    username=udata['username'],
                    email=udata['email'],
                    password=demo_password,
                    first_name=udata['first_name'],
                    last_name=udata['last_name'],
                    is_staff=udata['is_staff'],
                    is_superuser=udata['is_superuser'],
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  -> Created user: '{user.username}' ({udata['role_title']})"
                    )
                )

            seeded_users[udata['key']] = user

        return seeded_users

    def _seed_locations_and_slots(self):
        """Create realistic demo parking locations with car and bike slots."""
        self.stdout.write("\n[2/3] Setting up Demo Parking Locations and Slots...")

        locations_data = [
            {
                'name': 'University Main Parking',
                'address': 'North Campus, Gate 4, Academic Boulevard',
                'description': 'Multi-tier academic campus parking facility with dedicated student and faculty bays.',
                'opening_time': time(6, 0),
                'closing_time': time(23, 0),
                'hourly_rate': Decimal('20.00'),
                'total_slots': 15,
                'car_slots': 10,
                'bike_slots': 5,
            },
            {
                'name': 'City Center Parking',
                'address': 'Commercial Hub, MG Road, Central Business District',
                'description': 'Modern automated multi-level facility adjacent to the central metro station and CBD offices.',
                'opening_time': time(7, 0),
                'closing_time': time(23, 30),
                'hourly_rate': Decimal('40.00'),
                'total_slots': 18,
                'car_slots': 12,
                'bike_slots': 6,
            },
            {
                'name': 'Shopping Complex Parking',
                'address': 'Grand Retail Mall, Lower Ground Level, Ring Road',
                'description': 'Spacious underground retail parking facility with wide parking bays and automated ticketing.',
                'opening_time': time(9, 0),
                'closing_time': time(22, 0),
                'hourly_rate': Decimal('30.00'),
                'total_slots': 12,
                'car_slots': 8,
                'bike_slots': 4,
            },
        ]

        seeded_locations = {}

        for ldata in locations_data:
            location, loc_created = ParkingLocation.objects.get_or_create(
                name=ldata['name'],
                defaults={
                    'address': ldata['address'],
                    'description': ldata['description'],
                    'opening_time': ldata['opening_time'],
                    'closing_time': ldata['closing_time'],
                    'hourly_rate': ldata['hourly_rate'],
                    'total_slots': ldata['total_slots'],
                    'is_active': True,
                }
            )

            if not loc_created:
                # Update metadata if existing
                location.address = ldata['address']
                location.description = ldata['description']
                location.opening_time = ldata['opening_time']
                location.closing_time = ldata['closing_time']
                location.hourly_rate = ldata['hourly_rate']
                location.total_slots = ldata['total_slots']
                location.is_active = True
                location.save()
                self.stdout.write(
                    self.style.WARNING(f"  -> Reusing existing location: '{location.name}'")
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"  -> Created location: '{location.name}' (Rate: Rs {location.hourly_rate}/hr)")
                )

            # Create Slots for Car
            car_created_count = 0
            for i in range(1, ldata['car_slots'] + 1):
                slot_num = f"C-{i:02d}"
                slot, s_created = ParkingSlot.objects.get_or_create(
                    location=location,
                    slot_number=slot_num,
                    defaults={
                        'slot_type': ParkingSlot.SlotType.CAR,
                        'is_active': True,
                    }
                )
                if not s_created and not slot.is_active:
                    slot.is_active = True
                    slot.save()
                if s_created:
                    car_created_count += 1

            # Create Slots for Bike
            bike_created_count = 0
            for i in range(1, ldata['bike_slots'] + 1):
                slot_num = f"B-{i:02d}"
                slot, s_created = ParkingSlot.objects.get_or_create(
                    location=location,
                    slot_number=slot_num,
                    defaults={
                        'slot_type': ParkingSlot.SlotType.BIKE,
                        'is_active': True,
                    }
                )
                if not s_created and not slot.is_active:
                    slot.is_active = True
                    slot.save()
                if s_created:
                    bike_created_count += 1

            total_slots_count = location.slots.count()
            self.stdout.write(
                f"     Slots verified: {total_slots_count} total ({ldata['car_slots']} Cars, {ldata['bike_slots']} Bikes)"
            )
            seeded_locations[location.name] = location

        return seeded_locations

    def _seed_demo_bookings(self, driver_user, locations, keep_times):
        """
        Create realistic bookings covering all lifecycle stages:
        - CONFIRMED: Future reservation created
        - ACTIVE: Driver currently parked (entry recorded, exit pending)
        - COMPLETED: Finished session (entry & exit recorded, final fee calculated)
        - CANCELLED: Cancelled booking (does not block bay)
        """
        self.stdout.write("\n[3/3] Setting up Demo Bookings across all Lifecycle Stages...")

        now = timezone.now()

        # Define 8 realistic sample bookings across the 3 facilities
        demo_booking_specs = [
            # 1. CONFIRMED Car Reservation (Upcoming later today)
            {
                'location_name': 'University Main Parking',
                'slot_number': 'C-01',
                'vehicle_number': 'DL-01-AB-1234',
                'vehicle_type': Booking.VehicleType.CAR,
                'status': Booking.BookingStatus.CONFIRMED,
                'start_time': now + timedelta(hours=2),
                'end_time': now + timedelta(hours=5),
                'actual_entry_time': None,
                'actual_exit_time': None,
                'description': 'Upcoming Car Reservation (starts in 2h)',
            },
            # 2. CONFIRMED Bike Reservation (Upcoming later today)
            {
                'location_name': 'University Main Parking',
                'slot_number': 'B-01',
                'vehicle_number': 'DL-01-BK-2020',
                'vehicle_type': Booking.VehicleType.BIKE,
                'status': Booking.BookingStatus.CONFIRMED,
                'start_time': now + timedelta(hours=3),
                'end_time': now + timedelta(hours=6),
                'actual_entry_time': None,
                'actual_exit_time': None,
                'description': 'Upcoming Bike Reservation (starts in 3h)',
            },
            # 3. ACTIVE Car Booking (Currently parked in CBD facility)
            {
                'location_name': 'City Center Parking',
                'slot_number': 'C-01',
                'vehicle_number': 'DL-02-CD-5678',
                'vehicle_type': Booking.VehicleType.CAR,
                'status': Booking.BookingStatus.ACTIVE,
                'start_time': now - timedelta(hours=1, minutes=15),
                'end_time': now + timedelta(hours=2),
                'actual_entry_time': now - timedelta(hours=1, minutes=10),
                'actual_exit_time': None,
                'description': 'Active Parked Car (entry 1h10m ago, exit pending)',
            },
            # 4. ACTIVE Bike Booking (Currently parked in Shopping Complex)
            {
                'location_name': 'Shopping Complex Parking',
                'slot_number': 'B-01',
                'vehicle_number': 'HR-26-BK-7777',
                'vehicle_type': Booking.VehicleType.BIKE,
                'status': Booking.BookingStatus.ACTIVE,
                'start_time': now - timedelta(minutes=45),
                'end_time': now + timedelta(hours=1, minutes=30),
                'actual_entry_time': now - timedelta(minutes=40),
                'actual_exit_time': None,
                'description': 'Active Parked Bike (entry 40m ago, exit pending)',
            },
            # 5. COMPLETED Car Booking (Yesterday - City Center)
            {
                'location_name': 'City Center Parking',
                'slot_number': 'C-02',
                'vehicle_number': 'HR-26-EE-9999',
                'vehicle_type': Booking.VehicleType.CAR,
                'status': Booking.BookingStatus.COMPLETED,
                'start_time': now - timedelta(days=1, hours=4),
                'end_time': now - timedelta(days=1, hours=1),
                'actual_entry_time': now - timedelta(days=1, hours=3, minutes=55),
                'actual_exit_time': now - timedelta(days=1, hours=1, minutes=5),
                'description': 'Completed Car Session (Yesterday, 2h 50m duration)',
            },
            # 6. COMPLETED Car Booking (2 days ago - Shopping Complex)
            {
                'location_name': 'Shopping Complex Parking',
                'slot_number': 'C-01',
                'vehicle_number': 'UP-16-FF-3333',
                'vehicle_type': Booking.VehicleType.CAR,
                'status': Booking.BookingStatus.COMPLETED,
                'start_time': now - timedelta(days=2, hours=5),
                'end_time': now - timedelta(days=2, hours=2),
                'actual_entry_time': now - timedelta(days=2, hours=4, minutes=50),
                'actual_exit_time': now - timedelta(days=2, hours=2, minutes=10),
                'description': 'Completed Car Session (2 days ago, 2h 40m duration)',
            },
            # 7. COMPLETED Bike Booking (3 days ago - University)
            {
                'location_name': 'University Main Parking',
                'slot_number': 'B-02',
                'vehicle_number': 'DL-05-BK-4444',
                'vehicle_type': Booking.VehicleType.BIKE,
                'status': Booking.BookingStatus.COMPLETED,
                'start_time': now - timedelta(days=3, hours=3),
                'end_time': now - timedelta(days=3, hours=1),
                'actual_entry_time': now - timedelta(days=3, hours=2, minutes=55),
                'actual_exit_time': now - timedelta(days=3, hours=1),
                'description': 'Completed Bike Session (3 days ago, ~2h duration)',
            },
            # 8. CANCELLED Car Reservation (Non-blocking, does not consume slot)
            {
                'location_name': 'University Main Parking',
                'slot_number': 'C-03',
                'vehicle_number': 'MH-01-GG-1111',
                'vehicle_type': Booking.VehicleType.CAR,
                'status': Booking.BookingStatus.CANCELLED,
                'start_time': now - timedelta(days=1, hours=2),
                'end_time': now - timedelta(days=1),
                'actual_entry_time': None,
                'actual_exit_time': None,
                'description': 'Cancelled Car Reservation (Bay C-03 remains free)',
            },
        ]

        created_count = 0
        updated_count = 0

        for spec in demo_booking_specs:
            location = locations.get(spec['location_name'])
            if not location:
                continue

            slot = ParkingSlot.objects.filter(
                location=location,
                slot_number=spec['slot_number']
            ).first()

            if not slot:
                continue

            # Calculate Fee realistically based on status
            if spec['status'] == Booking.BookingStatus.COMPLETED:
                fee = calculate_actual_parking_fee(
                    location.hourly_rate,
                    spec['actual_entry_time'],
                    spec['actual_exit_time']
                )
            else:
                fee = calculate_booking_fee(
                    location.hourly_rate,
                    spec['start_time'],
                    spec['end_time']
                )

            # Query existing booking by unique demo slot + vehicle_number
            existing_booking = Booking.objects.filter(
                slot=slot,
                vehicle_number=spec['vehicle_number']
            ).first()

            if existing_booking:
                if not keep_times:
                    existing_booking.user = driver_user
                    existing_booking.location = location
                    existing_booking.vehicle_type = spec['vehicle_type']
                    existing_booking.start_time = spec['start_time']
                    existing_booking.end_time = spec['end_time']
                    existing_booking.actual_entry_time = spec['actual_entry_time']
                    existing_booking.actual_exit_time = spec['actual_exit_time']
                    existing_booking.status = spec['status']
                    existing_booking.total_amount = fee
                    existing_booking.save()
                    updated_count += 1
                self.stdout.write(
                    f"  -> Reused booking for {spec['vehicle_number']} [{spec['status']}] at {location.name} ({spec['slot_number']})"
                )
            else:
                booking = Booking.objects.create(
                    user=driver_user,
                    location=location,
                    slot=slot,
                    vehicle_number=spec['vehicle_number'],
                    vehicle_type=spec['vehicle_type'],
                    start_time=spec['start_time'],
                    end_time=spec['end_time'],
                    actual_entry_time=spec['actual_entry_time'],
                    actual_exit_time=spec['actual_exit_time'],
                    status=spec['status'],
                    total_amount=fee,
                )
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  -> Created booking #{booking.id}: {spec['vehicle_number']} [{spec['status']}] at {location.name} ({spec['slot_number']}) - Rs {fee}"
                    )
                )

        self.stdout.write(
            f"     Bookings ready: {created_count} created, {updated_count} refreshed."
        )

    def _print_summary(self, demo_password, users):
        """Print neat terminal demonstration guide."""
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("  DEMO SETUP COMPLETE! READY FOR ACADEMIC EVALUATION"))
        self.stdout.write("=" * 70)
        self.stdout.write("\nCredentials for Academic Demonstration:\n")
        self.stdout.write(
            f"{'Role':<22} | {'Username':<14} | {'Password':<18} | {'Primary Access'}\n"
            f"{'-' * 22}-+-{'-' * 14}-+-{'-' * 18}-+-{'-' * 28}"
        )
        self.stdout.write(
            f"{'Admin (Superuser)':<22} | {'demo_admin':<14} | {demo_password:<18} | /admin/ & /parking/manage/locations/\n"
            f"{'Parking Staff':<22} | {'demo_staff':<14} | {demo_password:<18} | /parking/operations/\n"
            f"{'Driver (Customer)':<22} | {'demo_driver':<14} | {demo_password:<18} | /parking/locations/ & /bookings/my/\n"
        )
        self.stdout.write(
            self.style.NOTICE(
                "Tip: You can re-run 'python manage.py seed_demo_data' at any time before a presentation\n"
                "     to refresh relative timestamps without creating duplicate records or deleting data.\n"
            )
        )
