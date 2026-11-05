from django.db import models


class ParkingLocation(models.Model):
    name = models.CharField(max_length=100)
    address = models.TextField()
    description = models.TextField(blank=True)
    total_slots = models.PositiveIntegerField()
    opening_time = models.TimeField()
    closing_time = models.TimeField()
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Parking Location'
        verbose_name_plural = 'Parking Locations'

    def __str__(self):
        return f"{self.name} (₹{self.hourly_rate}/hr)"


class ParkingSlot(models.Model):
    class SlotType(models.TextChoices):
        CAR = 'CAR', 'Car'
        BIKE = 'BIKE', 'Bike'

    location = models.ForeignKey(
        ParkingLocation,
        on_delete=models.CASCADE,
        related_name='slots'
    )
    slot_number = models.CharField(max_length=20)
    slot_type = models.CharField(
        max_length=10,
        choices=SlotType.choices,
        default=SlotType.CAR
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['location', 'slot_number'],
                name='unique_location_slot'
            )
        ]
        ordering = ['location', 'slot_number']
        verbose_name = 'Parking Slot'
        verbose_name_plural = 'Parking Slots'

    def __str__(self):
        return f"{self.location.name} - Slot {self.slot_number} ({self.get_slot_type_display()})"
