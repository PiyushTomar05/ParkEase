from django import forms
from django.utils import timezone

from .models import Booking
from .services import is_slot_available_for_period
from parking.models import ParkingLocation, ParkingSlot


class BookingForm(forms.ModelForm):
    """
    ModelForm for drivers to create parking reservations.
    Enforces comprehensive server-side temporal and relational validation.
    """
    location = forms.ModelChoiceField(
        queryset=ParkingLocation.objects.filter(is_active=True),
        empty_label="— Select Parking Facility —",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_location',
        }),
        help_text="Choose an operational parking facility."
    )

    slot = forms.ModelChoiceField(
        queryset=ParkingSlot.objects.filter(is_active=True),
        empty_label="— Select Parking Bay —",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_slot',
        }),
        help_text="Choose a designated parking slot."
    )

    vehicle_type = forms.ChoiceField(
        choices=Booking.VehicleType.choices,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_vehicle_type',
        })
    )

    vehicle_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. MH-12-AB-1234',
            'autocomplete': 'off',
            'id': 'id_vehicle_number',
        }),
        help_text="Enter your official vehicle registration number."
    )

    start_time = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control',
            'type': 'datetime-local',
            'id': 'id_start_time',
        }),
        help_text="Reservation start schedule."
    )

    end_time = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control',
            'type': 'datetime-local',
            'id': 'id_end_time',
        }),
        help_text="Expected departure schedule."
    )

    class Meta:
        model = Booking
        fields = [
            'location',
            'vehicle_type',
            'slot',
            'vehicle_number',
            'start_time',
            'end_time',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Restrict slots dropdown dynamically if location is selected
        location_id = None
        vehicle_type = None

        if 'location' in self.data:
            try:
                location_id = int(self.data.get('location'))
            except (ValueError, TypeError):
                pass
        elif self.initial.get('location'):
            location_val = self.initial.get('location')
            location_id = location_val.pk if hasattr(location_val, 'pk') else location_val
        elif self.instance and self.instance.pk:
            location_id = self.instance.location_id

        if 'vehicle_type' in self.data:
            vehicle_type = self.data.get('vehicle_type')
        elif self.initial.get('vehicle_type'):
            vehicle_type = self.initial.get('vehicle_type')
        elif self.instance and self.instance.pk:
            vehicle_type = self.instance.vehicle_type

        slots_qs = ParkingSlot.objects.filter(is_active=True)
        if location_id:
            slots_qs = slots_qs.filter(location_id=location_id)
        if vehicle_type:
            slots_qs = slots_qs.filter(slot_type=vehicle_type)

        self.fields['slot'].queryset = slots_qs.order_by('slot_number')

    def clean_vehicle_number(self):
        v_num = self.cleaned_data.get('vehicle_number', '').strip().upper()
        if not v_num:
            raise forms.ValidationError("Vehicle registration number is required.")
        return v_num

    def clean_start_time(self):
        start_time = self.cleaned_data.get('start_time')
        if start_time and start_time <= timezone.now():
            raise forms.ValidationError("Booking start time must be in the future.")
        return start_time

    def clean(self):
        cleaned_data = super().clean()
        location = cleaned_data.get('location')
        slot = cleaned_data.get('slot')
        vehicle_type = cleaned_data.get('vehicle_type')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        # 1. Temporal bounds validation
        if start_time and end_time:
            if end_time <= start_time:
                self.add_error('end_time', "End time must be later than start time.")

        # 2. Facility active validation
        if location and not location.is_active:
            self.add_error('location', f"Parking facility '{location.name}' is currently inactive.")

        # 3. Slot active validation
        if slot and not slot.is_active:
            self.add_error('slot', f"Slot '{slot.slot_number}' is currently inactive or under maintenance.")

        # 4. Slot belongs to location
        if slot and location and slot.location_id != location.id:
            self.add_error(
                'slot',
                f"Selected slot '{slot.slot_number}' does not belong to facility '{location.name}'."
            )

        # 5. Slot type matches vehicle type
        if slot and vehicle_type and slot.slot_type != vehicle_type:
            self.add_error(
                'slot',
                f"Slot '{slot.slot_number}' is for {slot.get_slot_type_display()}s, but you selected vehicle type {dict(Booking.VehicleType.choices).get(vehicle_type)}."
            )

        # 6. Overlapping reservation availability validation
        if slot and start_time and end_time and end_time > start_time:
            exclude_id = self.instance.pk if self.instance and self.instance.pk else None
            if not is_slot_available_for_period(slot, start_time, end_time, exclude_booking_id=exclude_id):
                self.add_error(
                    'slot',
                    f"Slot '{slot.slot_number}' is already reserved or occupied during the selected time period. Please choose another slot or time."
                )

        return cleaned_data

