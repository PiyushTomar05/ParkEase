from datetime import time, timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from parking.models import ParkingLocation, ParkingSlot

User = get_user_model()


class UserRegistrationTests(TestCase):
    def test_registration_page_renders(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/register.html')
        self.assertContains(response, 'Create an Account')

    def test_successful_registration(self):
        payload = {
            'username': 'driver_jn',
            'email': 'john@example.com',
            'password1': 'StrongP@ssw0rd2026',
            'password2': 'StrongP@ssw0rd2026',
        }
        response = self.client.post(reverse('register'), data=payload, follow=True)
        self.assertRedirects(response, reverse('login'))

        # Verify user is saved and password is not in plain text
        self.assertTrue(User.objects.filter(username='driver_jn').exists())
        user = User.objects.get(username='driver_jn')
        self.assertEqual(user.email, 'john@example.com')
        self.assertNotEqual(user.password, 'StrongP@ssw0rd2026')
        self.assertTrue(user.check_password('StrongP@ssw0rd2026'))

        # Verify success message was displayed on the login page
        self.assertContains(response, 'Account created successfully for driver_jn!')

    def test_username_exactly_10_characters_accepted(self):
        payload = {
            'username': 'user_10chr',  # exactly 10 characters
            'email': 'ten@example.com',
            'password1': 'StrongP@ssw0rd2026',
            'password2': 'StrongP@ssw0rd2026',
        }
        response = self.client.post(reverse('register'), data=payload, follow=True)
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username='user_10chr').exists())

    def test_username_longer_than_10_characters_rejected(self):
        payload = {
            'username': 'toolongname',  # 11 characters
            'email': 'long@example.com',
            'password1': 'StrongP@ssw0rd2026',
            'password2': 'StrongP@ssw0rd2026',
        }
        response = self.client.post(reverse('register'), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='toolongname').exists())
        self.assertFormError(
            response.context['form'],
            'username',
            'Username must be 10 characters or fewer.'
        )

    def test_empty_username_rejected(self):
        payload = {
            'username': '',
            'email': 'empty@example.com',
            'password1': 'StrongP@ssw0rd2026',
            'password2': 'StrongP@ssw0rd2026',
        }
        response = self.client.post(reverse('register'), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context['form'],
            'username',
            'Username is required.'
        )

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username='driver_jn', email='first@example.com', password='StrongP@ssw0rd2026')
        payload = {
            'username': 'driver_jn',
            'email': 'second@example.com',
            'password1': 'StrongP@ssw0rd2026',
            'password2': 'StrongP@ssw0rd2026',
        }
        response = self.client.post(reverse('register'), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'username', 'A user with that username already exists.')

    def test_mismatched_passwords_rejected(self):
        payload = {
            'username': 'driver_mis',
            'email': 'mismatch@example.com',
            'password1': 'StrongP@ssw0rd2026',
            'password2': 'DifferentPassword123',
        }
        response = self.client.post(reverse('register'), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='driver_mis').exists())

    def test_invalid_short_password_rejected(self):
        payload = {
            'username': 'driver_sh',
            'email': 'short@example.com',
            'password1': 'abc',
            'password2': 'abc',
        }
        response = self.client.post(reverse('register'), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='driver_sh').exists())
        form = response.context['form']
        self.assertTrue('password2' in form.errors or 'password1' in form.errors)

    def test_invalid_numeric_password_rejected(self):
        payload = {
            'username': 'driver_num',
            'email': 'numeric@example.com',
            'password1': '12345678',
            'password2': '12345678',
        }
        response = self.client.post(reverse('register'), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='driver_num').exists())
        form = response.context['form']
        self.assertTrue('password2' in form.errors or 'password1' in form.errors)

    def test_email_required_for_registration(self):
        payload = {
            'username': 'driver_no',
            'email': '',
            'password1': 'StrongP@ssw0rd2026',
            'password2': 'StrongP@ssw0rd2026',
        }
        response = self.client.post(reverse('register'), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email', 'Email address is required.')

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username='first_user', email='same@example.com', password='StrongP@ssw0rd2026')
        payload = {
            'username': 'second_usr',
            'email': 'same@example.com',
            'password1': 'StrongP@ssw0rd2026',
            'password2': 'StrongP@ssw0rd2026',
        }
        response = self.client.post(reverse('register'), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email', 'A user with that email already exists.')

    def test_authenticated_user_redirected_away_from_register(self):
        user = User.objects.create_user(username='reg_user', password='StrongP@ssw0rd2026')
        self.client.force_login(user)
        response = self.client.get(reverse('register'))
        self.assertRedirects(response, reverse('dashboard'))


class UserLoginTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='user_cust',
            email='cust@example.com',
            password='TestPassword123!'
        )
        self.staff_user = User.objects.create_user(
            username='user_staff',
            email='staff@example.com',
            password='TestPassword123!',
            is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            username='user_admin',
            email='admin@example.com',
            password='TestPassword123!'
        )
        # Account with legacy username length > 10
        self.legacy_user = User.objects.create_user(
            username='legacy_long_user',  # 16 characters
            email='legacy@example.com',
            password='TestPassword123!'
        )

    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')
        self.assertContains(response, 'Welcome Back')

    def test_customer_login_redirects_to_customer_dashboard(self):
        response = self.client.post(reverse('login'), data={
            'username': 'user_cust',
            'password': 'TestPassword123!'
        }, follow=True)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.customer.pk)
        self.assertContains(response, 'Welcome back, user_cust!')

    def test_staff_login_redirects_to_operations_dashboard(self):
        response = self.client.post(reverse('login'), data={
            'username': 'user_staff',
            'password': 'TestPassword123!'
        }, follow=True)
        self.assertRedirects(response, reverse('operations_dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.staff_user.pk)
        self.assertContains(response, 'Welcome back, user_staff!')

    def test_superuser_login_redirects_to_operations_dashboard(self):
        response = self.client.post(reverse('login'), data={
            'username': 'user_admin',
            'password': 'TestPassword123!'
        }, follow=True)
        self.assertRedirects(response, reverse('operations_dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.superuser.pk)
        self.assertContains(response, 'Welcome back, user_admin!')

    def test_login_preserves_safe_next_url(self):
        target_url = reverse('create_booking')
        login_url_with_next = f"{reverse('login')}?next={target_url}"
        response = self.client.post(login_url_with_next, data={
            'username': 'user_cust',
            'password': 'TestPassword123!'
        }, follow=True)
        self.assertRedirects(response, target_url)

    def test_login_with_home_next_url_redirects_to_role_dashboard(self):
        # A next parameter of '/' or home should not strand logged-in user on landing page
        login_url_with_home = f"{reverse('login')}?next=/"
        response = self.client.post(login_url_with_home, data={
            'username': 'user_cust',
            'password': 'TestPassword123!'
        }, follow=True)
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_rejects_unsafe_external_next_url(self):
        unsafe_url = "https://malicious.example.com/steal-credentials/"
        login_url_with_unsafe = f"{reverse('login')}?next={unsafe_url}"
        response = self.client.post(login_url_with_unsafe, data={
            'username': 'user_cust',
            'password': 'TestPassword123!'
        }, follow=True)
        # Falls back safely to customer dashboard
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_works_for_existing_user_with_username_over_10_characters(self):
        # Users created prior to the 10-char rule must remain able to log in
        response = self.client.post(reverse('login'), data={
            'username': 'legacy_long_user',
            'password': 'TestPassword123!'
        }, follow=True)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.legacy_user.pk)

    def test_invalid_credentials_rejected(self):
        response = self.client.post(reverse('login'), data={
            'username': 'user_cust',
            'password': 'WrongPassword123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')
        self.assertContains(response, 'Please enter a correct username and password')

    def test_authenticated_customer_visiting_login_redirected_to_customer_dashboard(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('login'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_authenticated_staff_visiting_login_redirected_to_operations_dashboard(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('login'))
        self.assertRedirects(response, reverse('operations_dashboard'))


class UserLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='logout_usr',
            password='TestPassword123!'
        )

    def test_logout_via_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('logout'), follow=True)
        self.assertRedirects(response, reverse('home'))
        # Session should no longer have authenticated user id
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(response, 'You have been logged out successfully.')

    def test_logout_via_get_does_not_clear_session(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('logout'))
        # GET redirects to home with warning and does NOT log user out
        self.assertRedirects(response, reverse('home'))
        self.assertIn('_auth_user_id', self.client.session)


class UserDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='dash_user',
            email='dash@example.com',
            password='TestPassword123!'
        )

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse('dashboard'))
        expected_redirect = f"{reverse('login')}?next={reverse('dashboard')}"
        self.assertRedirects(response, expected_redirect)

    def test_authenticated_user_can_access_dashboard(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/dashboard.html')
        self.assertContains(response, 'Welcome back, dash_user!')
        self.assertContains(response, 'No Parking Bookings Yet')

    def test_dashboard_displays_user_bookings(self):
        location = ParkingLocation.objects.create(
            name='Central Plaza Garage',
            address='100 Main Street',
            total_slots=50,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
            hourly_rate=40.00
        )
        slot = ParkingSlot.objects.create(
            location=location,
            slot_number='C-01',
            slot_type=ParkingSlot.SlotType.CAR
        )
        now = timezone.now()
        Booking.objects.create(
            user=self.user,
            location=location,
            slot=slot,
            vehicle_number='KA-01-AB-1234',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=80.00
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Central Plaza Garage')
        self.assertContains(response, 'KA-01-AB-1234')
        self.assertContains(response, 'C-01')
        self.assertEqual(response.context['active_count'], 1)
        self.assertEqual(response.context['total_bookings'], 1)


class GeneralPagesTests(TestCase):
    def test_landing_page_renders(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Smart Parking. Simple Experience.')

    def test_admin_portal_accessible(self):
        response = self.client.get(reverse('admin:index'))
        self.assertIn(response.status_code, [200, 302])


class RoleBasedDashboardAndNavigationTests(TestCase):
    def setUp(self):
        # Customer driver
        self.customer = User.objects.create_user(
            username='cust_drvr',
            email='driver@example.com',
            password='DriverPassword123!'
        )
        # Staff administrator
        self.staff_user = User.objects.create_user(
            username='staff_adm',
            email='staff@example.com',
            password='StaffPassword123!',
            is_staff=True
        )
        # Superuser
        self.superuser = User.objects.create_superuser(
            username='super_adm',
            email='super@example.com',
            password='SuperPassword123!'
        )
        # Facilities & Bays
        self.location = ParkingLocation.objects.create(
            name='Central Metro Parking',
            address='200 Railway Ave',
            total_slots=30,
            opening_time=time(5, 0),
            closing_time=time(23, 30),
            hourly_rate=30.00
        )
        self.slot1 = ParkingSlot.objects.create(
            location=self.location,
            slot_number='A-101',
            slot_type=ParkingSlot.SlotType.CAR
        )
        self.slot2 = ParkingSlot.objects.create(
            location=self.location,
            slot_number='A-102',
            slot_type=ParkingSlot.SlotType.BIKE
        )
        # Booking for customer
        now = timezone.now()
        self.customer_booking = Booking.objects.create(
            user=self.customer,
            location=self.location,
            slot=self.slot1,
            vehicle_number='KA-05-MM-1212',
            vehicle_type=Booking.VehicleType.CAR,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            status=Booking.BookingStatus.ACTIVE,
            total_amount=60.00
        )

    def test_customer_dashboard_content(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_staff_dashboard'])
        # Contains customer elements
        self.assertContains(response, 'Driver Portal')
        self.assertContains(response, 'Welcome back, cust_drvr!')
        self.assertContains(response, 'Find Parking')
        self.assertContains(response, 'Book a Slot')
        self.assertContains(response, 'My Bookings Overview')
        # Does not contain staff administration banners
        self.assertNotContains(response, 'Parking Staff Operations')
        self.assertNotContains(response, 'System-Wide Recent Bookings')

    def test_staff_dashboard_content(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_staff_dashboard'])
        # Contains staff elements
        self.assertContains(response, 'Parking Staff Operations')
        self.assertContains(response, 'Welcome back, staff_adm!')
        self.assertContains(response, 'Parking Operations')
        self.assertContains(response, 'Manage Parking')
        self.assertContains(response, 'System Bookings')
        self.assertContains(response, 'Active Sessions')
        self.assertContains(response, 'System-Wide Recent Bookings')
        # System metrics check
        self.assertEqual(response.context['total_bookings'], 1)
        self.assertEqual(response.context['active_count'], 1)
        self.assertEqual(response.context['total_locations'], 1)
        # Does not have Driver Portal badge in staff header
        self.assertNotContains(response, 'Driver Portal')

    def test_superuser_dashboard_content(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_staff_dashboard'])
        self.assertTrue(response.context['is_superuser'])
        self.assertContains(response, 'System Administration')
        self.assertContains(response, 'Django Admin')
        self.assertContains(response, reverse('admin:index'))

    def test_customer_navbar_links(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        # Customer sees
        self.assertContains(response, reverse('location_list'))
        self.assertContains(response, reverse('dashboard'))
        self.assertContains(response, reverse('my_bookings'))
        # Customer does NOT see staff navigation in main navbar
        self.assertNotContains(response, reverse('operations_dashboard'))
        self.assertNotContains(response, reverse('manage_locations'))

    def test_staff_navbar_links(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Staff sees operational navigation
        self.assertIn('Parking Operations', content)
        self.assertIn('Manage Parking', content)
        self.assertIn('View Public Site', content)
        # Staff main navbar does NOT contain customer links (Home or How It Works)
        # Check navbar-nav section specifically
        navbar_slice = content.split('<ul class="navbar-nav')[1].split('</ul>')[0]
        self.assertNotIn('>Home<', navbar_slice)
        self.assertNotIn('>Find Parking<', navbar_slice)
        self.assertNotIn('>My Bookings<', navbar_slice)
        self.assertNotIn('>How It Works<', navbar_slice)

    def test_anonymous_navbar_links(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('location_list'))
        self.assertContains(response, reverse('login'))
        self.assertContains(response, reverse('register'))
        self.assertNotContains(response, reverse('dashboard'))
        self.assertNotContains(response, reverse('my_bookings'))
        self.assertNotContains(response, reverse('operations_dashboard'))
        self.assertNotContains(response, reverse('manage_locations'))
