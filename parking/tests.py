from datetime import time, timedelta
from decimal import Decimal
from io import StringIO
from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from bookings.services import calculate_actual_parking_fee
from .forms import ParkingLocationForm, ParkingSlotForm
from .models import ParkingLocation, ParkingSlot
from .services import (
    SLOT_STATUS_AVAILABLE,
    SLOT_STATUS_INACTIVE,
    SLOT_STATUS_OCCUPIED,
    SLOT_STATUS_RESERVED,
    get_available_slots,
    get_slots_with_availability,
)

User = get_user_model()


class ParkingLocationModelAndFormTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff_admin',
            email='staff@example.com',
            password='Password123!',
            is_staff=True
        )

    def test_parking_location_creation(self):
        loc = ParkingLocation.objects.create(
            name='City Center Garage',
            address='123 Main Street',
            description='Centrally located indoor multi-level garage',
            total_slots=40,
            opening_time=time(6, 0),
            closing_time=time(22, 0),
            hourly_rate=50.00,
            is_active=True
        )
        self.assertEqual(loc.name, 'City Center Garage')
        self.assertEqual(loc.total_slots, 40)
        self.assertIn('City Center Garage', str(loc))
        self.assertIn('/hr', str(loc))

    def test_location_form_validation(self):
        # Invalid: 0 slots
        invalid_data = {
            'name': 'Test Loc',
            'address': 'Test Address',
            'total_slots': 0,
            'opening_time': '06:00',
            'closing_time': '22:00',
            'hourly_rate': '30.00',
            'is_active': True,
        }
        form = ParkingLocationForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        self.assertIn('total_slots', form.errors)

        # Invalid: negative hourly rate
        invalid_data['total_slots'] = 20
        invalid_data['hourly_rate'] = '-10.00'
        form2 = ParkingLocationForm(data=invalid_data)
        self.assertFalse(form2.is_valid())
        self.assertIn('hourly_rate', form2.errors)


class ParkingSlotModelAndFormTests(TestCase):
    def setUp(self):
        self.location = ParkingLocation.objects.create(
            name='Metro Plaza',
            address='456 Market St',
            total_slots=25,
            opening_time=time(5, 0),
            closing_time=time(23, 0),
            hourly_rate=30.00
        )
        self.other_location = ParkingLocation.objects.create(
            name='Airport Terminal Lot',
            address='789 Airport Rd',
            total_slots=100,
            opening_time=time(0, 0),
            closing_time=time(23, 59),
            hourly_rate=60.00
        )

    def test_parking_slot_creation(self):
        slot = ParkingSlot.objects.create(
            location=self.location,
            slot_number='C-01',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=True
        )
        self.assertEqual(slot.slot_number, 'C-01')
        self.assertEqual(slot.slot_type, ParkingSlot.SlotType.CAR)
        self.assertTrue(slot.is_active)
        self.assertIn('C-01', str(slot))

    def test_duplicate_slot_number_in_same_location_rejected(self):
        ParkingSlot.objects.create(
            location=self.location,
            slot_number='C-01',
            slot_type=ParkingSlot.SlotType.CAR
        )

        form = ParkingSlotForm(
            data={'slot_number': 'C-01', 'slot_type': 'CAR', 'is_active': True},
            location=self.location
        )
        self.assertFalse(form.is_valid())
        self.assertIn('slot_number', form.errors)
        self.assertIn("already exists", form.errors['slot_number'][0])

        # Also case-insensitive check (c-01 vs C-01)
        form_lower = ParkingSlotForm(
            data={'slot_number': 'c-01', 'slot_type': 'CAR', 'is_active': True},
            location=self.location
        )
        self.assertFalse(form_lower.is_valid())
        self.assertIn('slot_number', form_lower.errors)

    def test_same_slot_number_allowed_in_different_locations(self):
        ParkingSlot.objects.create(
            location=self.location,
            slot_number='C-01',
            slot_type=ParkingSlot.SlotType.CAR
        )

        form = ParkingSlotForm(
            data={'slot_number': 'C-01', 'slot_type': 'CAR', 'is_active': True},
            location=self.other_location
        )
        self.assertTrue(form.is_valid())


class PublicLocationViewsTests(TestCase):
    def setUp(self):
        self.active_location = ParkingLocation.objects.create(
            name='Grand Central Parking',
            address='10 Station Square',
            description='Convenient indoor commuter parking',
            total_slots=10,
            opening_time=time(6, 0),
            closing_time=time(22, 0),
            hourly_rate=40.00,
            is_active=True
        )
        self.inactive_location = ParkingLocation.objects.create(
            name='Old Warehouse Lot',
            address='99 Industrial Ave',
            total_slots=5,
            opening_time=time(8, 0),
            closing_time=time(18, 0),
            hourly_rate=20.00,
            is_active=False
        )
        self.slot1 = ParkingSlot.objects.create(
            location=self.active_location,
            slot_number='A-01',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=True
        )
        self.slot2 = ParkingSlot.objects.create(
            location=self.active_location,
            slot_number='B-01',
            slot_type=ParkingSlot.SlotType.BIKE,
            is_active=True
        )

    def test_location_listing_public_access(self):
        response = self.client.get(reverse('location_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'parking/location_list.html')
        # Active location should appear
        self.assertContains(response, 'Grand Central Parking')
        self.assertContains(response, '₹40.00')
        # Inactive location should NOT appear
        self.assertNotContains(response, 'Old Warehouse Lot')

    def test_location_listing_empty_state(self):
        ParkingLocation.objects.all().delete()
        response = self.client.get(reverse('location_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No Parking Locations Found')

    def test_location_listing_search(self):
        response = self.client.get(reverse('location_list') + '?q=Station')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Central Parking')

        response_empty = self.client.get(reverse('location_list') + '?q=NonExistent')
        self.assertContains(response_empty, 'No facilities matched your search')

    def test_location_detail_public_access(self):
        response = self.client.get(reverse('location_detail', kwargs={'pk': self.active_location.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'parking/location_detail.html')
        self.assertContains(response, 'Grand Central Parking')
        self.assertContains(response, 'A-01')
        self.assertContains(response, 'B-01')
        self.assertContains(response, 'slot-available')

    def test_inactive_location_hidden_from_public(self):
        response = self.client.get(reverse('location_detail', kwargs={'pk': self.inactive_location.pk}))
        self.assertEqual(response.status_code, 404)


class StaffAccessAndUserRestrictionsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='admin_boss',
            email='admin@parkease.com',
            password='StrongPassword123!',
            is_staff=True
        )
        self.regular_user = User.objects.create_user(
            username='regular_driver',
            email='driver@parkease.com',
            password='StrongPassword123!',
            is_staff=False
        )
        self.location = ParkingLocation.objects.create(
            name='Harbor Parking Deck',
            address='20 Harbor Way',
            total_slots=30,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
            hourly_rate=35.00,
            is_active=True
        )
        self.slot = ParkingSlot.objects.create(
            location=self.location,
            slot_number='H-01',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=True
        )

    def test_anonymous_user_redirected_to_login(self):
        manage_urls = [
            reverse('manage_locations'),
            reverse('add_location'),
            reverse('edit_location', kwargs={'pk': self.location.pk}),
            reverse('manage_slots', kwargs={'location_id': self.location.pk}),
            reverse('add_slot', kwargs={'location_id': self.location.pk}),
            reverse('edit_slot', kwargs={'pk': self.slot.pk}),
        ]
        for url in manage_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse('login')))

    def test_regular_user_cannot_access_staff_views(self):
        self.client.force_login(self.regular_user)
        manage_urls = [
            reverse('manage_locations'),
            reverse('add_location'),
            reverse('edit_location', kwargs={'pk': self.location.pk}),
            reverse('manage_slots', kwargs={'location_id': self.location.pk}),
            reverse('add_slot', kwargs={'location_id': self.location.pk}),
            reverse('edit_slot', kwargs={'pk': self.slot.pk}),
        ]
        for url in manage_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_staff_user_can_access_all_management_views(self):
        self.client.force_login(self.staff_user)
        manage_urls = [
            reverse('manage_locations'),
            reverse('add_location'),
            reverse('edit_location', kwargs={'pk': self.location.pk}),
            reverse('manage_slots', kwargs={'location_id': self.location.pk}),
            reverse('add_slot', kwargs={'location_id': self.location.pk}),
            reverse('edit_slot', kwargs={'pk': self.slot.pk}),
        ]
        for url in manage_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

    def test_staff_can_add_location(self):
        self.client.force_login(self.staff_user)
        payload = {
            'name': 'New Tech Park Lot',
            'address': '800 Innovation Way',
            'description': 'EV charging and covered bays',
            'total_slots': 60,
            'opening_time': '07:00',
            'closing_time': '21:00',
            'hourly_rate': '45.00',
            'is_active': True,
        }
        response = self.client.post(reverse('add_location'), data=payload, follow=True)
        self.assertRedirects(response, reverse('manage_locations'))
        self.assertTrue(ParkingLocation.objects.filter(name='New Tech Park Lot').exists())
        self.assertContains(response, "created successfully")

    def test_staff_can_edit_location(self):
        self.client.force_login(self.staff_user)
        payload = {
            'name': 'Harbor Parking Deck Updated',
            'address': '20 Harbor Way',
            'description': 'Updated description',
            'total_slots': 35,
            'opening_time': '05:30',
            'closing_time': '23:30',
            'hourly_rate': '40.00',
            'is_active': True,
        }
        response = self.client.post(
            reverse('edit_location', kwargs={'pk': self.location.pk}),
            data=payload,
            follow=True
        )
        self.assertRedirects(response, reverse('manage_locations'))
        self.location.refresh_from_db()
        self.assertEqual(self.location.name, 'Harbor Parking Deck Updated')
        self.assertEqual(self.location.total_slots, 35)

    def test_staff_can_toggle_location_status_via_post(self):
        self.client.force_login(self.staff_user)
        self.assertTrue(self.location.is_active)

        # Deactivate
        response = self.client.post(
            reverse('toggle_location_status', kwargs={'pk': self.location.pk}),
            follow=True
        )
        self.assertRedirects(response, reverse('manage_locations'))
        self.location.refresh_from_db()
        self.assertFalse(self.location.is_active)
        self.assertContains(response, 'deactivated')

        # Activate
        response2 = self.client.post(
            reverse('toggle_location_status', kwargs={'pk': self.location.pk}),
            follow=True
        )
        self.location.refresh_from_db()
        self.assertTrue(self.location.is_active)
        self.assertContains(response2, 'activated')

    def test_toggle_location_status_requires_post(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('toggle_location_status', kwargs={'pk': self.location.pk}))
        self.assertEqual(response.status_code, 405)

    def test_staff_can_add_slot(self):
        self.client.force_login(self.staff_user)
        payload = {
            'slot_number': 'H-02',
            'slot_type': 'BIKE',
            'is_active': True,
        }
        response = self.client.post(
            reverse('add_slot', kwargs={'location_id': self.location.pk}),
            data=payload,
            follow=True
        )
        self.assertRedirects(response, reverse('manage_slots', kwargs={'location_id': self.location.pk}))
        self.assertTrue(ParkingSlot.objects.filter(location=self.location, slot_number='H-02').exists())
        self.assertContains(response, "added to Harbor Parking Deck")

    def test_staff_can_edit_slot(self):
        self.client.force_login(self.staff_user)
        payload = {
            'slot_number': 'H-01-VIP',
            'slot_type': 'CAR',
            'is_active': True,
        }
        response = self.client.post(
            reverse('edit_slot', kwargs={'pk': self.slot.pk}),
            data=payload,
            follow=True
        )
        self.assertRedirects(response, reverse('manage_slots', kwargs={'location_id': self.location.pk}))
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.slot_number, 'H-01-VIP')

    def test_staff_can_toggle_slot_status_via_post(self):
        self.client.force_login(self.staff_user)
        self.assertTrue(self.slot.is_active)

        # Deactivate slot
        response = self.client.post(
            reverse('toggle_slot_status', kwargs={'pk': self.slot.pk}),
            follow=True
        )
        self.assertRedirects(response, reverse('manage_slots', kwargs={'location_id': self.location.pk}))
        self.slot.refresh_from_db()
        self.assertFalse(self.slot.is_active)
        self.assertContains(response, 'deactivated')

    def test_toggle_slot_status_requires_post(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('toggle_slot_status', kwargs={'pk': self.slot.pk}))
        self.assertEqual(response.status_code, 405)


class SlotAvailabilityCalculationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='driver_tester',
            password='TestPassword123!'
        )
        self.location = ParkingLocation.objects.create(
            name='Speedway Lot',
            address='500 Race Track Road',
            total_slots=4,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
            hourly_rate=50.00
        )
        # Create 4 slots
        self.slot_available = ParkingSlot.objects.create(
            location=self.location,
            slot_number='S-01',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=True
        )
        self.slot_occupied = ParkingSlot.objects.create(
            location=self.location,
            slot_number='S-02',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=True
        )
        self.slot_reserved = ParkingSlot.objects.create(
            location=self.location,
            slot_number='S-03',
            slot_type=ParkingSlot.SlotType.BIKE,
            is_active=True
        )
        self.slot_inactive = ParkingSlot.objects.create(
            location=self.location,
            slot_number='S-04',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=False
        )

        now = timezone.now()

        # Slot S-02 has ACTIVE booking (Occupied)
        Booking.objects.create(
            user=self.user,
            location=self.location,
            slot=self.slot_occupied,
            vehicle_number='KA-05-MM-1111',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=100.00
        )

        # Slot S-03 has CONFIRMED booking overlapping now (Reserved)
        Booking.objects.create(
            user=self.user,
            location=self.location,
            slot=self.slot_reserved,
            vehicle_number='KA-05-MM-2222',
            vehicle_type=Booking.VehicleType.BIKE,
            start_time=now - timedelta(minutes=30),
            end_time=now + timedelta(hours=1),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=50.00
        )

        # Slot S-01 had a COMPLETED booking in the past (Available)
        Booking.objects.create(
            user=self.user,
            location=self.location,
            slot=self.slot_available,
            vehicle_number='KA-05-MM-3333',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=now - timedelta(days=1),
            end_time=now - timedelta(days=1, hours=-2),
            status=Booking.BookingStatus.COMPLETED,
            total_amount=80.00
        )

    def test_slot_status_resolution(self):
        slot_data_list, stats = get_slots_with_availability(self.location)

        status_by_number = {d['slot'].slot_number: d['status'] for d in slot_data_list}
        self.assertEqual(status_by_number['S-01'], SLOT_STATUS_AVAILABLE)
        self.assertEqual(status_by_number['S-02'], SLOT_STATUS_OCCUPIED)
        self.assertEqual(status_by_number['S-03'], SLOT_STATUS_RESERVED)
        self.assertEqual(status_by_number['S-04'], SLOT_STATUS_INACTIVE)

    def test_availability_stats(self):
        _, stats = get_slots_with_availability(self.location)
        self.assertEqual(stats['total_slots'], 4)
        self.assertEqual(stats['configured_slots'], 4)
        self.assertEqual(stats['active_slots_count'], 3)
        self.assertEqual(stats['available_count'], 1)
        self.assertEqual(stats['occupied_count'], 1)
        self.assertEqual(stats['reserved_count'], 1)
        self.assertEqual(stats['inactive_count'], 1)

    def test_get_available_slots_queryset(self):
        available_slots = get_available_slots(self.location)
        self.assertEqual(available_slots.count(), 1)
        self.assertEqual(available_slots.first().slot_number, 'S-01')

    def test_future_reservation_does_not_block_current_availability(self):
        # A booking scheduled tomorrow should not block availability right now
        now = timezone.now()
        Booking.objects.create(
            user=self.user,
            location=self.location,
            slot=self.slot_available,
            vehicle_number='KA-05-MM-9999',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=2),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=100.00
        )

        slot_data_list, _ = get_slots_with_availability(self.location, target_time=now)
        status_by_number = {d['slot'].slot_number: d['status'] for d in slot_data_list}
        self.assertEqual(status_by_number['S-01'], SLOT_STATUS_AVAILABLE)


class ParkingOperationsAndAnalyticsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff_op',
            email='staff_op@example.com',
            password='Password123!',
            is_staff=True
        )
        self.driver = User.objects.create_user(
            username='driver_john',
            email='john@example.com',
            password='Password123!',
            is_staff=False
        )
        self.location = ParkingLocation.objects.create(
            name='Downtown Operations Garage',
            address='456 Central Ave',
            description='Modern facility with electronic sensors',
            total_slots=10,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
            hourly_rate=Decimal('40.00'),
            is_active=True
        )
        self.slot = ParkingSlot.objects.create(
            location=self.location,
            slot_number='OP-01',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=True
        )
        self.slot_bike = ParkingSlot.objects.create(
            location=self.location,
            slot_number='OP-02',
            slot_type=ParkingSlot.SlotType.BIKE,
            is_active=True
        )
        self.now = timezone.now().replace(second=0, microsecond=0)
        self.confirmed_booking = Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-AB-1234',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now + timedelta(hours=1),
            end_time=self.now + timedelta(hours=3),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('80.00')
        )

    # 1. Staff user can access operations dashboard
    def test_01_staff_user_can_access_operations_dashboard(self):
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.get(reverse('operations_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'parking/operations_dashboard.html')

    # 2. Anonymous user cannot access operations dashboard
    def test_02_anonymous_user_cannot_access_operations_dashboard(self):
        response = self.client.get(reverse('operations_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    # 3. Regular driver cannot access operations dashboard
    def test_03_regular_driver_cannot_access_operations_dashboard(self):
        self.client.login(username='driver_john', password='Password123!')
        response = self.client.get(reverse('operations_dashboard'))
        self.assertEqual(response.status_code, 403)

    # 4. Staff can check in a CONFIRMED booking
    def test_04_staff_can_check_in_confirmed_booking(self):
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.post(reverse('check_in_booking', kwargs={'pk': self.confirmed_booking.pk}))
        self.assertRedirects(response, reverse('booking_detail', kwargs={'pk': self.confirmed_booking.pk}))
        self.confirmed_booking.refresh_from_db()
        self.assertEqual(self.confirmed_booking.status, Booking.BookingStatus.ACTIVE)

    # 5. Staff cannot check in a CANCELLED booking
    def test_05_staff_cannot_check_in_cancelled_booking(self):
        cancelled_booking = Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-XX-9999',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now + timedelta(hours=4),
            end_time=self.now + timedelta(hours=6),
            status=Booking.BookingStatus.CANCELLED,
            total_amount=Decimal('80.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.post(reverse('check_in_booking', kwargs={'pk': cancelled_booking.pk}))
        cancelled_booking.refresh_from_db()
        self.assertEqual(cancelled_booking.status, Booking.BookingStatus.CANCELLED)

    # 6. Staff cannot check in a COMPLETED booking
    def test_06_staff_cannot_check_in_completed_booking(self):
        completed_booking = Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-CC-8888',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now - timedelta(hours=4),
            end_time=self.now - timedelta(hours=2),
            actual_entry_time=self.now - timedelta(hours=4),
            actual_exit_time=self.now - timedelta(hours=2),
            status=Booking.BookingStatus.COMPLETED,
            total_amount=Decimal('80.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.post(reverse('check_in_booking', kwargs={'pk': completed_booking.pk}))
        completed_booking.refresh_from_db()
        self.assertEqual(completed_booking.status, Booking.BookingStatus.COMPLETED)

    # 7. Check-in sets actual_entry_time
    def test_07_check_in_sets_actual_entry_time(self):
        self.client.login(username='staff_op', password='Password123!')
        self.client.post(reverse('check_in_booking', kwargs={'pk': self.confirmed_booking.pk}))
        self.confirmed_booking.refresh_from_db()
        self.assertIsNotNone(self.confirmed_booking.actual_entry_time)
        delta_seconds = abs((timezone.now() - self.confirmed_booking.actual_entry_time).total_seconds())
        self.assertLess(delta_seconds, 10)

    # 8. Staff can check out an ACTIVE booking
    def test_08_staff_can_check_out_active_booking(self):
        active_booking = Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-AC-7777',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now - timedelta(hours=2),
            end_time=self.now + timedelta(hours=1),
            actual_entry_time=self.now - timedelta(hours=2),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=Decimal('120.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.post(reverse('check_out_booking', kwargs={'pk': active_booking.pk}))
        self.assertRedirects(response, reverse('booking_detail', kwargs={'pk': active_booking.pk}))
        active_booking.refresh_from_db()
        self.assertEqual(active_booking.status, Booking.BookingStatus.COMPLETED)

    # 9. Check-out sets actual_exit_time
    def test_09_check_out_sets_actual_exit_time(self):
        active_booking = Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-AC-6666',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now - timedelta(hours=1),
            end_time=self.now + timedelta(hours=1),
            actual_entry_time=self.now - timedelta(hours=1),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=Decimal('80.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        self.client.post(reverse('check_out_booking', kwargs={'pk': active_booking.pk}))
        active_booking.refresh_from_db()
        self.assertIsNotNone(active_booking.actual_exit_time)
        self.assertGreater(active_booking.actual_exit_time, active_booking.actual_entry_time)

    # 10. Check-out updates status to COMPLETED
    def test_10_check_out_updates_status_to_completed(self):
        active_booking = Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-AC-5555',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now - timedelta(hours=1),
            end_time=self.now + timedelta(hours=1),
            actual_entry_time=self.now - timedelta(hours=1),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=Decimal('80.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        self.client.post(reverse('check_out_booking', kwargs={'pk': active_booking.pk}))
        active_booking.refresh_from_db()
        self.assertEqual(active_booking.status, Booking.BookingStatus.COMPLETED)

    # 11. Actual fee calculation is correct
    def test_11_actual_fee_calculation_is_correct(self):
        # 2 hours 30 mins at 40/hr = 100.00
        t_entry = self.now - timedelta(hours=2, minutes=30)
        t_exit = self.now
        fee = calculate_actual_parking_fee(Decimal('40.00'), t_entry, t_exit)
        self.assertEqual(fee, Decimal('100.00'))

        # Check out via view calculates proportional fee correctly
        active_booking = Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-AC-4444',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now - timedelta(hours=3),
            end_time=self.now,
            actual_entry_time=timezone.now() - timedelta(hours=2),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=Decimal('120.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        self.client.post(reverse('check_out_booking', kwargs={'pk': active_booking.pk}))
        active_booking.refresh_from_db()
        # 2 hours * 40 = 80.00
        self.assertAlmostEqual(float(active_booking.total_amount), 80.00, delta=1.0)

    # 12. Negative parking duration is rejected
    def test_12_negative_parking_duration_is_rejected(self):
        t_now = timezone.now()
        with self.assertRaises(ValueError):
            calculate_actual_parking_fee(Decimal('40.00'), t_now, t_now - timedelta(minutes=30))
        with self.assertRaises(ValueError):
            calculate_actual_parking_fee(Decimal('40.00'), t_now, t_now)

    # 13. Duplicate check-in is rejected
    def test_13_duplicate_check_in_is_rejected(self):
        self.client.login(username='staff_op', password='Password123!')
        self.client.post(reverse('check_in_booking', kwargs={'pk': self.confirmed_booking.pk}))
        self.confirmed_booking.refresh_from_db()
        first_entry_time = self.confirmed_booking.actual_entry_time

        # Second attempt
        response = self.client.post(reverse('check_in_booking', kwargs={'pk': self.confirmed_booking.pk}))
        self.confirmed_booking.refresh_from_db()
        self.assertEqual(self.confirmed_booking.actual_entry_time, first_entry_time)
        self.assertEqual(self.confirmed_booking.status, Booking.BookingStatus.ACTIVE)

    # 14. Duplicate check-out is rejected
    def test_14_duplicate_check_out_is_rejected(self):
        active_booking = Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-AC-3333',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now - timedelta(hours=1),
            end_time=self.now + timedelta(hours=1),
            actual_entry_time=self.now - timedelta(hours=1),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=Decimal('80.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        self.client.post(reverse('check_out_booking', kwargs={'pk': active_booking.pk}))
        active_booking.refresh_from_db()
        first_exit_time = active_booking.actual_exit_time

        # Second attempt
        response = self.client.post(reverse('check_out_booking', kwargs={'pk': active_booking.pk}))
        active_booking.refresh_from_db()
        self.assertEqual(active_booking.actual_exit_time, first_exit_time)
        self.assertEqual(active_booking.status, Booking.BookingStatus.COMPLETED)

    # 15. GET requests cannot perform check-in
    def test_15_get_requests_cannot_perform_check_in(self):
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.get(reverse('check_in_booking', kwargs={'pk': self.confirmed_booking.pk}))
        self.assertEqual(response.status_code, 405)
        self.confirmed_booking.refresh_from_db()
        self.assertEqual(self.confirmed_booking.status, Booking.BookingStatus.CONFIRMED)

    # 16. GET requests cannot perform check-out
    def test_16_get_requests_cannot_perform_check_out(self):
        active_booking = Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-AC-2222',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now - timedelta(hours=1),
            end_time=self.now + timedelta(hours=1),
            actual_entry_time=self.now - timedelta(hours=1),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=Decimal('80.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.get(reverse('check_out_booking', kwargs={'pk': active_booking.pk}))
        self.assertEqual(response.status_code, 405)
        active_booking.refresh_from_db()
        self.assertEqual(active_booking.status, Booking.BookingStatus.ACTIVE)

    # 17. Revenue calculations exclude cancelled bookings
    def test_17_revenue_calculations_exclude_cancelled_bookings(self):
        Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-REV-1',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now - timedelta(hours=2),
            end_time=self.now,
            actual_entry_time=self.now - timedelta(hours=2),
            actual_exit_time=self.now,
            status=Booking.BookingStatus.COMPLETED,
            total_amount=Decimal('100.00')
        )
        Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-REV-CANCEL',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now,
            end_time=self.now + timedelta(hours=2),
            status=Booking.BookingStatus.CANCELLED,
            total_amount=Decimal('500.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.get(reverse('operations_dashboard'))
        self.assertEqual(response.context['total_completed_revenue'], Decimal('100.00'))

    # 18. Revenue calculations exclude confirmed bookings
    def test_18_revenue_calculations_exclude_confirmed_bookings(self):
        Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-REV-2',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now - timedelta(hours=1),
            end_time=self.now,
            actual_entry_time=self.now - timedelta(hours=1),
            actual_exit_time=self.now,
            status=Booking.BookingStatus.COMPLETED,
            total_amount=Decimal('60.00')
        )
        Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot,
            vehicle_number='KA-01-REV-CONFIRM',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=self.now + timedelta(hours=1),
            end_time=self.now + timedelta(hours=3),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('400.00')
        )
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.get(reverse('operations_dashboard'))
        self.assertEqual(response.context['total_completed_revenue'], Decimal('60.00'))

    # 19. Dashboard statistics are correct
    def test_19_dashboard_statistics_are_correct(self):
        self.client.login(username='staff_op', password='Password123!')
        response = self.client.get(reverse('operations_dashboard'))
        self.assertIn('total_locations', response.context)
        self.assertIn('active_locations', response.context)
        self.assertIn('total_slots', response.context)
        self.assertIn('total_available_slots', response.context)
        self.assertIn('occupied_bays_count', response.context)
        self.assertIn('reserved_bays_count', response.context)
        self.assertIn('active_sessions_count', response.context)
        self.assertIn('today_completed_count', response.context)
        self.assertIn('today_revenue', response.context)

    # 20. Booking filters work correctly
    def test_20_booking_filters_work_correctly(self):
        Booking.objects.create(
            user=self.driver,
            location=self.location,
            slot=self.slot_bike,
            vehicle_number='KA-02-FILTER-BIKE',
            vehicle_type=Booking.VehicleType.BIKE,
            start_time=self.now + timedelta(days=2),
            end_time=self.now + timedelta(days=2, hours=1),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=Decimal('20.00')
        )
        self.client.login(username='staff_op', password='Password123!')

        # Filter by vehicle_type
        res_bike = self.client.get(reverse('operations_dashboard') + '?vehicle_type=BIKE')
        self.assertTrue(all(b.vehicle_type == 'BIKE' for b in res_bike.context['bookings']))

        # Filter by status
        res_conf = self.client.get(reverse('operations_dashboard') + '?status=CONFIRMED')
        self.assertTrue(all(b.status == 'CONFIRMED' for b in res_conf.context['bookings']))

        # Filter by search
        res_search = self.client.get(reverse('operations_dashboard') + '?q=KA-02-FILTER-BIKE')
        self.assertEqual(len(res_search.context['bookings']), 1)
        self.assertEqual(res_search.context['bookings'][0].vehicle_number, 'KA-02-FILTER-BIKE')


class SeedDemoDataCommandTests(TestCase):
    def test_seed_demo_data_creates_roles_locations_and_bookings(self):
        out = StringIO()
        call_command('seed_demo_data', stdout=out)

        # 1. Verify User Roles
        admin_user = User.objects.filter(username='demo_admin').first()
        self.assertIsNotNone(admin_user)
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)

        staff_user = User.objects.filter(username='demo_staff').first()
        self.assertIsNotNone(staff_user)
        self.assertTrue(staff_user.is_staff)
        self.assertFalse(staff_user.is_superuser)

        driver_user = User.objects.filter(username='demo_driver').first()
        self.assertIsNotNone(driver_user)
        self.assertFalse(driver_user.is_staff)
        self.assertFalse(driver_user.is_superuser)

        # Verify authentication with default password
        auth_user = authenticate(username='demo_driver', password='ParkEase@Demo2026')
        self.assertIsNotNone(auth_user)

        # 2. Verify Locations and Slot Uniqueness
        locations = ParkingLocation.objects.all()
        self.assertEqual(locations.count(), 3)
        for loc in locations:
            slots = ParkingSlot.objects.filter(location=loc)
            self.assertGreater(slots.count(), 0)
            slot_numbers = list(slots.values_list('slot_number', flat=True))
            self.assertEqual(len(slot_numbers), len(set(slot_numbers)), "Slot numbers must be unique per location")
            self.assertTrue(slots.filter(slot_type=ParkingSlot.SlotType.CAR).exists())
            self.assertTrue(slots.filter(slot_type=ParkingSlot.SlotType.BIKE).exists())

        # 3. Verify Demo Bookings and Status Lifecycle
        bookings = Booking.objects.all()
        self.assertEqual(bookings.count(), 8)

        # Confirmed
        confirmed_bookings = bookings.filter(status=Booking.BookingStatus.CONFIRMED)
        self.assertTrue(confirmed_bookings.exists())
        for b in confirmed_bookings:
            self.assertIsNone(b.actual_entry_time)
            self.assertIsNone(b.actual_exit_time)
            self.assertGreater(b.total_amount, Decimal('0.00'))

        # Active
        active_bookings = bookings.filter(status=Booking.BookingStatus.ACTIVE)
        self.assertTrue(active_bookings.exists())
        for b in active_bookings:
            self.assertIsNotNone(b.actual_entry_time)
            self.assertIsNone(b.actual_exit_time)

        # Completed
        completed_bookings = bookings.filter(status=Booking.BookingStatus.COMPLETED)
        self.assertTrue(completed_bookings.exists())
        for b in completed_bookings:
            self.assertIsNotNone(b.actual_entry_time)
            self.assertIsNotNone(b.actual_exit_time)
            self.assertGreater(b.actual_exit_time, b.actual_entry_time)
            self.assertGreater(b.total_amount, Decimal('0.00'))

        # Cancelled
        cancelled_bookings = bookings.filter(status=Booking.BookingStatus.CANCELLED)
        self.assertTrue(cancelled_bookings.exists())
        for b in cancelled_bookings:
            self.assertIsNone(b.actual_entry_time)
            self.assertIsNone(b.actual_exit_time)

    def test_seed_demo_data_idempotency(self):
        out1 = StringIO()
        call_command('seed_demo_data', stdout=out1)
        users_count_1 = User.objects.count()
        loc_count_1 = ParkingLocation.objects.count()
        slot_count_1 = ParkingSlot.objects.count()
        booking_count_1 = Booking.objects.count()

        # Run second time
        out2 = StringIO()
        call_command('seed_demo_data', stdout=out2)
        self.assertEqual(User.objects.count(), users_count_1)
        self.assertEqual(ParkingLocation.objects.count(), loc_count_1)
        self.assertEqual(ParkingSlot.objects.count(), slot_count_1)
        self.assertEqual(Booking.objects.count(), booking_count_1)

    def test_seed_demo_data_custom_password_and_no_bookings(self):
        out = StringIO()
        call_command('seed_demo_data', '--password', 'CustomEval@999', '--no-bookings', stdout=out)

        auth_user = authenticate(username='demo_admin', password='CustomEval@999')
        self.assertIsNotNone(auth_user)
        self.assertEqual(Booking.objects.count(), 0)

