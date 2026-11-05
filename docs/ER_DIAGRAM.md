# ParkEase: Entity-Relationship (ER) Diagram & Schema Specification

**Document:** Entity-Relationship (ER) Diagram  
**Project:** Cost-Effective Smart Parking Management System (ParkEase)  
**Architecture:** Django 5.x ORM / Relational Database Schema  

---

## 1. Overview

The ParkEase database schema is designed around four relational entities:
1. **User (`auth_user`)**: Django built-in authentication model supporting Driver, Staff, and Administrator roles.
2. **ParkingLocation (`parking_parkinglocation`)**: Represents a physical parking facility with operating hours, rates, and capacity.
3. **ParkingSlot (`parking_parkingslot`)**: Represents a physical parking bay designated for either Cars or Bikes within a specific facility.
4. **Booking (`bookings_booking`)**: Represents a lifecycle reservation linking a Driver, Facility, and Parking Bay with time tracking and billing metrics.

---

## 2. Mermaid Entity-Relationship Diagram

```mermaid
erDiagram
    USER ||--o{ BOOKING : "places (1:N)"
    PARKING_LOCATION ||--|{ PARKING_SLOT : "contains (1:N)"
    PARKING_LOCATION ||--o{ BOOKING : "hosts (1:N)"
    PARKING_SLOT ||--o{ BOOKING : "allocated_to (1:N)"

    USER {
        int id PK "Primary Key (Auto-increment)"
        string username UK "Unique Username"
        string email "User Email Address"
        string password "Hashed Secret (PBKDF2/SHA-256)"
        boolean is_staff "Staff Operator Flag"
        boolean is_superuser "Administrator Flag"
        string first_name "First Name"
        string last_name "Last Name"
        boolean is_active "Active Account Status"
        datetime date_joined "Account Registration Timestamp"
    }

    PARKING_LOCATION {
        int id PK "Primary Key (Auto-increment)"
        string name "Facility Name (Max 100)"
        text address "Physical Street Address"
        text description "Facility Amenities & Details"
        int total_slots "Positive Integer Capacity"
        time opening_time "Daily Opening Time"
        time closing_time "Daily Closing Time"
        decimal hourly_rate "Hourly Billing Rate (8, 2)"
        boolean is_active "Operational Status (Default True)"
        datetime created_at "Facility Record Timestamp"
    }

    PARKING_SLOT {
        int id PK "Primary Key (Auto-increment)"
        int location_id FK "Foreign Key to ParkingLocation"
        string slot_number "Bay Identifier e.g. C-01, B-02"
        string slot_type "Vehicle Classification: CAR | BIKE"
        boolean is_active "Bay Availability Status (Default True)"
    }

    BOOKING {
        int id PK "Primary Key (Auto-increment)"
        int user_id FK "Foreign Key to auth_user"
        int location_id FK "Foreign Key to ParkingLocation"
        int slot_id FK "Foreign Key to ParkingSlot"
        string vehicle_number "Vehicle Registration Number (Max 20)"
        string vehicle_type "Vehicle Type: CAR | BIKE"
        datetime start_time "Scheduled Arrival Window"
        datetime end_time "Scheduled Departure Window"
        datetime actual_entry_time "Actual Check-In Timestamp (Nullable)"
        datetime actual_exit_time "Actual Check-Out Timestamp (Nullable)"
        string status "Lifecycle Status: PENDING | CONFIRMED | ACTIVE | COMPLETED | CANCELLED"
        decimal total_amount "Total Calculated Fee (8, 2)"
        datetime created_at "Reservation Creation Timestamp"
    }
```

---

## 3. Relational Constraints & Integrity Rules

1. **Foreign Key Integrity:**
   - `ParkingSlot.location` $\to$ `ParkingLocation` with `on_delete=models.CASCADE`.
   - `Booking.user` $\to$ `User` with `on_delete=models.CASCADE`.
   - `Booking.location` $\to$ `ParkingLocation` with `on_delete=models.CASCADE`.
   - `Booking.slot` $\to$ `ParkingSlot` with `on_delete=models.CASCADE`.

2. **Composite Uniqueness:**
   - `ParkingSlot` enforces a unique constraint on `(location, slot_number)` named `unique_location_slot`.
   - Ensures slot identifiers (e.g., `C-01`) cannot be duplicated within the same physical facility.

3. **Status Enumeration:**
   - `BookingStatus`:
     - `PENDING`: Initial state during payment or confirmation processing.
     - `CONFIRMED`: Active reservation awaiting driver arrival.
     - `ACTIVE`: Vehicle checked in; driver is currently parked in the bay.
     - `COMPLETED`: Vehicle checked out; duration and final fee calculated.
     - `CANCELLED`: Driver or operator cancelled the reservation; releases bay availability.
   - `SlotType` / `VehicleType`:
     - `CAR`: Standard 4-wheeler passenger vehicle.
     - `BIKE`: 2-wheeler motorcycle or scooter.

4. **Model Clean Validation (`clean()`):**
   - Temporal Check: `start_time < end_time`.
   - Slot-Location Coherence: `slot.location_id == location_id`.
   - Type Matching: `slot.slot_type == booking.vehicle_type`.

