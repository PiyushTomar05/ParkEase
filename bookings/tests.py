from datetime import time, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import BookingForm
from .models import Booking
from .services import calculate_booking_fee, is_slot_available_for_period
from parking.models import ParkingLocation, ParkingSlot

User = get_user_model()


class BookingSystemTests(TestCase):
    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(
            username='driver_one',
            email='driver1@example.com',
            password='TestPassword123!'
        )
        self.user2 = User.objects.create_user(
            username='driver_two',
            email='driver2@example.com',
            password='TestPassword123!'
        )
        self.staff_user = User.objects.create_user(
            username='staff_manager',
            email='staff@example.com',
            password='TestPassword123!',
            is_staff=True
        )

        # Create active parking location
        self.location = ParkingLocation.objects.create(
            name='Silicon Plaza Deck',
            address='100 Tech Blvd',
            total_slots=10,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
            hourly_rate=Decimal('40.00'),
            is_active=True
        )

        # Create inactive parking location
        self.inactive_location = ParkingLocation.objects.create(
            name='Closed Facility',
            address='200 Deserted Way',
            total_slots=5,
            opening_time=time(8, 0),
            closing_time=time(18, 0),
            hourly_rate=Decimal('25.00'),
            is_active=False
        )

        # Create parking slots for active location
        self.slot_car = ParkingSlot.objects.create(
            location=self.location,
            slot_number='C-01',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=True
        )
        self.slot_bike = ParkingSlot.objects.create(
            location=self.location,
            slot_number='B-01',
            slot_type=ParkingSlot.SlotType.BIKE,
            is_active=True
        )
        self.slot_inactive = ParkingSlot.objects.create(
            location=self.location,
            slot_number='C-02',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=False
        )

        # Create slot for inactive location
        self.slot_other_loc = ParkingSlot.objects.create(
            location=self.inactive_location,
            slot_number='C-99',
            slot_type=ParkingSlot.SlotType.CAR,
            is_active=True
        )

    # -------------------------------------------------------------------------
    # 1. Authenticated user can create a booking
    # -------------------------------------------------------------------------
    def test_authenticated_user_can_create_booking(self):
        self.client.force_login(self.user1)
        now = timezone.now()
        start = now + timedelta(hours=2)
        end = now + timedelta(hours=4)

        payload = {
            'location': self.location.pk,
            'slot': self.slot_car.pk,
            'vehicle_type': 'CAR',
            'vehicle_number': 'ka-01-ab-1234',  # lower case to test normalization
            'start_time': start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': end.strftime('%Y-%m-%dT%H:%M'),
        }

        response = self.client.post(reverse('create_booking'), data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        # Check booking in database
        self.assertTrue(Booking.objects.filter(user=self.user1).exists())
        booking = Booking.objects.get(user=self.user1)
        self.assertEqual(booking.vehicle_number, 'KA-01-AB-1234')  # normalized uppercase
        self.assertEqual(booking.status, Booking.BookingStatus.CONFIRMED)
        self.assertEqual(booking.total_amount, Decimal('80.00'))  # 2 hours * 40.00
        self.assertRedirects(response, reverse('booking_detail', kwargs={'pk': booking.pk}))
        self.assertContains(response, 'created successfully')

    # -------------------------------------------------------------------------
    # 2. Anonymous user cannot create a booking
    # -------------------------------------------------------------------------
    def test_anonymous_user_cannot_create_booking(self):
        response = self.client.get(reverse('create_booking'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))

        response_post = self.client.post(reverse('create_booking'), data={})
        self.assertEqual(response_post.status_code, 302)
        self.assertTrue(response_post.url.startswith(reverse('login')))

    # -------------------------------------------------------------------------
    # 3. Booking form rejects past start times
    # -------------------------------------------------------------------------
    def test_booking_form_rejects_past_start_times(self):
        self.client.force_login(self.user1)
        now = timezone.now()
        past_start = now - timedelta(hours=1)
        future_end = now + timedelta(hours=2)

        data = {
            'location': self.location.pk,
            'slot': self.slot_car.pk,
            'vehicle_type': 'CAR',
            'vehicle_number': 'MH-12-CD-5678',
            'start_time': past_start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': future_end.strftime('%Y-%m-%dT%H:%M'),
        }
        form = BookingForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('start_time', form.errors)
        self.assertIn('must be in the future', form.errors['start_time'][0])

    # -------------------------------------------------------------------------
    # 4. Booking form rejects invalid end times (end <= start)
    # -------------------------------------------------------------------------
    def test_booking_form_rejects_invalid_end_times(self):
        self.client.force_login(self.user1)
        now = timezone.now()
        start = now + timedelta(hours=2)
        invalid_end = start - timedelta(minutes=30)

        data = {
            'location': self.location.pk,
            'slot': self.slot_car.pk,
            'vehicle_type': 'CAR',
            'vehicle_number': 'MH-12-CD-5678',
            'start_time': start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': invalid_end.strftime('%Y-%m-%dT%H:%M'),
        }
        form = BookingForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('end_time', form.errors)
        self.assertIn('later than start time', form.errors['end_time'][0])

    # -------------------------------------------------------------------------
    # 5. Booking form rejects mismatched slot and location
    # -------------------------------------------------------------------------
    def test_booking_form_rejects_mismatched_slot_and_location(self):
        self.client.force_login(self.user1)
        now = timezone.now()
        start = now + timedelta(hours=2)
        end = now + timedelta(hours=4)

        data = {
            'location': self.location.pk,
            'slot': self.slot_other_loc.pk,  # slot belongs to inactive_location
            'vehicle_type': 'CAR',
            'vehicle_number': 'MH-12-CD-5678',
            'start_time': start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': end.strftime('%Y-%m-%dT%H:%M'),
        }
        form = BookingForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('slot', form.errors)

    # -------------------------------------------------------------------------
    # 6. Booking form rejects mismatched vehicle and slot types
    # -------------------------------------------------------------------------
    def test_booking_form_rejects_mismatched_vehicle_and_slot_types(self):
        self.client.force_login(self.user1)
        now = timezone.now()
        start = now + timedelta(hours=2)
        end = now + timedelta(hours=4)

        # Select BIKE vehicle type for CAR slot
        data = {
            'location': self.location.pk,
            'slot': self.slot_car.pk,  # Car slot
            'vehicle_type': 'BIKE',     # Bike vehicle
            'vehicle_number': 'MH-12-CD-5678',
            'start_time': start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': end.strftime('%Y-%m-%dT%H:%M'),
        }
        form = BookingForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('slot', form.errors)

    # -------------------------------------------------------------------------
    # 7. Booking form rejects inactive slots
    # -------------------------------------------------------------------------
    def test_booking_form_rejects_inactive_slots(self):
        self.client.force_login(self.user1)
        now = timezone.now()
        start = now + timedelta(hours=2)
        end = now + timedelta(hours=4)

        data = {
            'location': self.location.pk,
            'slot': self.slot_inactive.pk,  # inactive slot
            'vehicle_type': 'CAR',
            'vehicle_number': 'MH-12-CD-5678',
            'start_time': start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': end.strftime('%Y-%m-%dT%H:%M'),
        }
        form = BookingForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('slot', form.errors)

    # -------------------------------------------------------------------------
    # 8. Overlapping reservations are rejected
    # -------------------------------------------------------------------------
    def test_overlapping_reservations_are_rejected(self):
        now = timezone.now()
        # Existing confirmed booking from 14:00 to 16:00
        Booking.objects.create(
            user=self.user1,
            location=self.location,
            slot=self.slot_car,
            vehicle_number='KA-01-AA-1111',
            vehicle_type='CAR',
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('80.00')
        )

        # Attempt overlapping booking from 15:00 to 17:00 (overlaps!)
        data = {
            'location': self.location.pk,
            'slot': self.slot_car.pk,
            'vehicle_type': 'CAR',
            'vehicle_number': 'KA-02-BB-2222',
            'start_time': (now + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M'),
            'end_time': (now + timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M'),
        }
        form = BookingForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('slot', form.errors)
        self.assertIn('already reserved or occupied', form.errors['slot'][0])

    # -------------------------------------------------------------------------
    # 9. Non-overlapping reservations are allowed
    # -------------------------------------------------------------------------
    def test_non_overlapping_reservations_are_allowed(self):
        now = timezone.now().replace(second=0, microsecond=0)
        # Existing booking from now+2h to now+4h
        Booking.objects.create(
            user=self.user1,
            location=self.location,
            slot=self.slot_car,
            vehicle_number='KA-01-AA-1111',
            vehicle_type='CAR',
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('80.00')
        )

        # Booking starts exactly when previous ends (now+4h to now+6h) -> non-overlapping
        data = {
            'location': self.location.pk,
            'slot': self.slot_car.pk,
            'vehicle_type': 'CAR',
            'vehicle_number': 'KA-02-BB-2222',
            'start_time': (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M'),
            'end_time': (now + timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M'),
        }
        form = BookingForm(data=data)
        self.assertTrue(form.is_valid())

    # -------------------------------------------------------------------------
    # 10. Cancelled bookings do not block availability
    # -------------------------------------------------------------------------
    def test_cancelled_bookings_do_not_block_availability(self):
        now = timezone.now()
        start = now + timedelta(hours=2)
        end = now + timedelta(hours=4)

        Booking.objects.create(
            user=self.user1,
            location=self.location,
            slot=self.slot_car,
            vehicle_number='KA-01-AA-1111',
            vehicle_type='CAR',
            start_time=start,
            end_time=end,
            status=Booking.BookingStatus.CANCELLED,
            total_amount=Decimal('80.00')
        )

        self.assertTrue(is_slot_available_for_period(self.slot_car, start, end))

    # -------------------------------------------------------------------------
    # 11. Completed bookings do not block availability
    # -------------------------------------------------------------------------
    def test_completed_bookings_do_not_block_availability(self):
        now = timezone.now()
        start = now + timedelta(hours=2)
        end = now + timedelta(hours=4)

        Booking.objects.create(
            user=self.user1,
            location=self.location,
            slot=self.slot_car,
            vehicle_number='KA-01-AA-1111',
            vehicle_type='CAR',
            start_time=start,
            end_time=end,
            status=Booking.BookingStatus.COMPLETED,
            total_amount=Decimal('80.00')
        )

        self.assertTrue(is_slot_available_for_period(self.slot_car, start, end))

    # -------------------------------------------------------------------------
    # 12. Booking fee calculation is correct
    # -------------------------------------------------------------------------
    def test_booking_fee_calculation(self):
        hourly_rate = Decimal('30.00')

        now = timezone.now()
        # Exactly 2 hours
        fee_2h = calculate_booking_fee(hourly_rate, now, now + timedelta(hours=2))
        self.assertEqual(fee_2h, Decimal('60.00'))

        # 2 hours 30 minutes (2.5 hours * 30 = 75.00)
        fee_2h30m = calculate_booking_fee(hourly_rate, now, now + timedelta(hours=2, minutes=30))
        self.assertEqual(fee_2h30m, Decimal('75.00'))

        # 1 hour 15 minutes (1.25 hours * 40 = 50.00)
        fee_1h15m = calculate_booking_fee(Decimal('40.00'), now, now + timedelta(hours=1, minutes=15))
        self.assertEqual(fee_1h15m, Decimal('50.00'))

        # 45 minutes (0.75 hours * 40 = 30.00)
        fee_45m = calculate_booking_fee(Decimal('40.00'), now, now + timedelta(minutes=45))
        self.assertEqual(fee_45m, Decimal('30.00'))

    # -------------------------------------------------------------------------
    # 13. Users cannot view another user's booking
    # -------------------------------------------------------------------------
    def test_users_cannot_view_another_users_booking(self):
        now = timezone.now()
        booking = Booking.objects.create(
            user=self.user1,
            location=self.location,
            slot=self.slot_car,
            vehicle_number='KA-01-AA-1111',
            vehicle_type='CAR',
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('80.00')
        )

        # User 2 tries to view User 1's booking
        self.client.force_login(self.user2)
        response = self.client.get(reverse('booking_detail', kwargs={'pk': booking.pk}))
        self.assertEqual(response.status_code, 403)

        # User 1 can view their own booking
        self.client.force_login(self.user1)
        response_owner = self.client.get(reverse('booking_detail', kwargs={'pk': booking.pk}))
        self.assertEqual(response_owner.status_code, 200)

        # Staff user can view User 1's booking
        self.client.force_login(self.staff_user)
        response_staff = self.client.get(reverse('booking_detail', kwargs={'pk': booking.pk}))
        self.assertEqual(response_staff.status_code, 200)

    # -------------------------------------------------------------------------
    # 14. Users cannot cancel another user's booking
    # -------------------------------------------------------------------------
    def test_users_cannot_cancel_another_users_booking(self):
        now = timezone.now()
        booking = Booking.objects.create(
            user=self.user1,
            location=self.location,
            slot=self.slot_car,
            vehicle_number='KA-01-AA-1111',
            vehicle_type='CAR',
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('80.00')
        )

        # User 2 attempts to cancel User 1's booking
        self.client.force_login(self.user2)
        response = self.client.post(reverse('cancel_booking', kwargs={'pk': booking.pk}))
        self.assertEqual(response.status_code, 403)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.BookingStatus.CONFIRMED)

        # User 1 can cancel their own booking
        self.client.force_login(self.user1)
        response_owner = self.client.post(reverse('cancel_booking', kwargs={'pk': booking.pk}), follow=True)
        self.assertEqual(response_owner.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.BookingStatus.CANCELLED)

    # -------------------------------------------------------------------------
    # 15. GET requests cannot cancel bookings
    # -------------------------------------------------------------------------
    def test_get_requests_cannot_cancel_bookings(self):
        now = timezone.now()
        booking = Booking.objects.create(
            user=self.user1,
            location=self.location,
            slot=self.slot_car,
            vehicle_number='KA-01-AA-1111',
            vehicle_type='CAR',
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('80.00')
        )

        self.client.force_login(self.user1)
        response = self.client.get(reverse('cancel_booking', kwargs={'pk': booking.pk}))
        self.assertEqual(response.status_code, 405)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.BookingStatus.CONFIRMED)

    # -------------------------------------------------------------------------
    # 16. Booking detail page renders correctly
    # -------------------------------------------------------------------------
    def test_booking_detail_page_renders_correctly(self):
        now = timezone.now()
        booking = Booking.objects.create(
            user=self.user1,
            location=self.location,
            slot=self.slot_car,
            vehicle_number='KA-01-AA-1111',
            vehicle_type='CAR',
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('80.00')
        )

        self.client.force_login(self.user1)
        response = self.client.get(reverse('booking_detail', kwargs={'pk': booking.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'bookings/booking_detail.html')
        self.assertContains(response, f'Reservation Pass #{booking.id}')
        self.assertContains(response, 'Silicon Plaza Deck')
        self.assertContains(response, 'C-01')
        self.assertContains(response, 'KA-01-AA-1111')
        self.assertContains(response, '₹80.00')

    # -------------------------------------------------------------------------
    # 17. My Bookings page displays only the current user's bookings
    # -------------------------------------------------------------------------
    def test_my_bookings_page_displays_only_current_users_bookings(self):
        now = timezone.now()
        # Booking for User 1
        b1 = Booking.objects.create(
            user=self.user1,
            location=self.location,
            slot=self.slot_car,
            vehicle_number='KA-01-AA-1111',
            vehicle_type='CAR',
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('80.00')
        )

        # Booking for User 2
        b2 = Booking.objects.create(
            user=self.user2,
            location=self.location,
            slot=self.slot_bike,
            vehicle_number='KA-02-BB-2222',
            vehicle_type='BIKE',
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            status=Booking.BookingStatus.CONFIRMED,
            total_amount=Decimal('80.00')
        )

        self.client.force_login(self.user1)
        response = self.client.get(reverse('my_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'bookings/my_bookings.html')
        self.assertContains(response, f'#{b1.id}')
        self.assertContains(response, 'KA-01-AA-1111')
        self.assertNotContains(response, f'#{b2.id}')
        self.assertNotContains(response, 'KA-02-BB-2222')

    # -------------------------------------------------------------------------
    # 18. AJAX available_slots view
    # -------------------------------------------------------------------------
    def test_available_slots_ajax_view(self):
        now = timezone.now()
        start = (now + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
        end = (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M')

        response = self.client.get(
            reverse('available_slots'),
            {
                'location_id': self.location.pk,
                'vehicle_type': 'CAR',
                'start_time': start,
                'end_time': end,
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('slots', data)
        slot_numbers = [s['slot_number'] for s in data['slots']]
        self.assertIn('C-01', slot_numbers)
        self.assertNotIn('B-01', slot_numbers)  # filtered out by vehicle_type CAR
        self.assertNotIn('C-02', slot_numbers)  # inactive slot
