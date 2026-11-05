from django import forms
from .models import ParkingLocation, ParkingSlot


class ParkingLocationForm(forms.ModelForm):
    """
    Form for administrators to create and update parking locations.
    """
    class Meta:
        model = ParkingLocation
        fields = [
            'name',
            'address',
            'description',
            'total_slots',
            'opening_time',
            'closing_time',
            'hourly_rate',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Metro Central Parking Garage',
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Enter full street address and landmarks',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Facility amenities, security details, entry instructions...',
            }),
            'total_slots': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'placeholder': 'e.g. 50',
            }),
            'opening_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
            }),
            'closing_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
            }),
            'hourly_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.50',
                'min': '0',
                'placeholder': 'e.g. 30.00',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def clean_total_slots(self):
        total_slots = self.cleaned_data.get('total_slots')
        if total_slots is None or total_slots <= 0:
            raise forms.ValidationError("Total parking slots must be at least 1.")
        return total_slots

    def clean_hourly_rate(self):
        hourly_rate = self.cleaned_data.get('hourly_rate')
        if hourly_rate is None or hourly_rate < 0:
            raise forms.ValidationError("Hourly rate cannot be negative.")
        return hourly_rate


class ParkingSlotForm(forms.ModelForm):
    """
    Form for administrators to add and edit individual parking slots.
    Enforces uniqueness of slot_number per parking location.
    """
    class Meta:
        model = ParkingSlot
        fields = ['slot_number', 'slot_type', 'is_active']
        widgets = {
            'slot_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. C-01, B-10',
                'autocomplete': 'off',
            }),
            'slot_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, location=None, **kwargs):
        self.location = location
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.location:
            self.location = self.instance.location

    def clean_slot_number(self):
        slot_number = self.cleaned_data.get('slot_number', '').strip().upper()
        if not slot_number:
            raise forms.ValidationError("Slot number cannot be blank.")

        location = self.location or (self.instance.location if self.instance.pk else None)
        if location:
            query = ParkingSlot.objects.filter(location=location, slot_number__iexact=slot_number)
            if self.instance and self.instance.pk:
                query = query.exclude(pk=self.instance.pk)
            if query.exists():
                raise forms.ValidationError(
                    f"Slot number '{slot_number}' already exists in {location.name}."
                )

        return slot_number

