from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from parking.models import ParkingLocation, ParkingSlot


class Booking(models.Model):
    class VehicleType(models.TextChoices):
        CAR = 'CAR', 'Car'
        BIKE = 'BIKE', 'Bike'

    class BookingStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    location = models.ForeignKey(
        ParkingLocation,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    vehicle_number = models.CharField(max_length=20)
    vehicle_type = models.CharField(
        max_length=10,
        choices=VehicleType.choices,
        default=VehicleType.CAR
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    actual_entry_time = models.DateTimeField(null=True, blank=True)
    actual_exit_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING
    )
    total_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0.00
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Booking'
        verbose_name_plural = 'Bookings'

    def clean(self):
        super().clean()
        errors = {}

        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors['end_time'] = "End time must be after start time."

        if self.slot_id and self.location_id:
            if self.slot.location_id != self.location_id:
                errors['slot'] = (
                    f"Selected slot '{self.slot.slot_number}' does not belong "
                    f"to location '{self.location.name}'."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        booking_id = self.id if self.id else "New"
        return f"Booking #{booking_id} - {self.vehicle_number} ({self.get_status_display()})"
