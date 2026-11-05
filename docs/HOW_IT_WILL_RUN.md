# How to Run ParkEase (Smart Parking Management System)

This guide provides clear, step-by-step instructions to set up, run, seed demo data, test, and demonstrate the **ParkEase** project locally on your machine.

---

## 1. Prerequisites

Ensure you have the following installed on your system:
- **Python 3.10+** (Python 3.12 recommended)
- **pip** (Python package installer)
- **Git** (for repository version control)

---

## 2. Setup Instructions

### Step 2.1: Open Terminal in Project Directory
Navigate to the project root folder:
```bash
cd CostEffectiveParking
```

### Step 2.2: Create and Activate Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On Windows (Command Prompt - cmd):**
```cmd
python -m venv venv
.\venv\Scripts\activate.bat
```

**On Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

*(You should see `(venv)` in your terminal prompt indicating the virtual environment is active).*

---

### Step 2.3: Install Dependencies
Install all required packages from `requirements.txt`:
```bash
pip install -r requirements.txt
```

---

### Step 2.4: Configure Environment Variables (Optional)
Copy the example environment configuration:
```bash
# On Windows
copy .env.example .env

# On Linux / macOS
cp .env.example .env
```
*(By default, standard development settings in `config/settings.py` work out-of-the-box without extra configuration).*

---

### Step 2.5: Apply Database Migrations
Initialize the SQLite database schema:
```bash
python manage.py migrate
```

---

### Step 2.6: Seed Demonstration Data
Populate realistic academic demonstration facilities, parking bays (Car & Bike), and sample bookings:
```bash
python manage.py seed_demo_data
```

This creates pre-configured demonstration accounts:

| Role | Username | Password | Capabilities |
| :--- | :--- | :--- | :--- |
| **System Admin** | `demo_admin` | `ParkEase@Demo2026` | Full system access, Django admin, facility management |
| **Parking Staff** | `demo_staff` | `ParkEase@Demo2026` | Operations dashboard, vehicle check-in & check-out |
| **Driver (Customer)** | `demo_driver` | `ParkEase@Demo2026` | Slot search, visual bay reservation, booking history |

*(Optional: Use a custom password by specifying `python manage.py seed_demo_data --password <your_password>` or setting the `PARKEASE_DEMO_PASSWORD` environment variable).*

---

## 3. Starting the Application

Launch the Django development server:
```bash
python manage.py runserver
```

Once running, open your web browser and visit:
- **ParkEase Web Portal:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Django Administration:** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## 4. Running Automated Tests

To run the complete automated test suite (102 tests):
```bash
# Verify system integrity
python manage.py check

# Run all automated tests
python manage.py test
```

Expected output:
```text
Found 102 test(s).
Creating test database for alias 'default'...
Ran 102 tests in ~140s
OK
Destroying test database for alias 'default'...
```

---

## 5. Demonstration & Evaluation Walkthrough

For an academic project evaluation or viva demonstration:

1. **Driver Walkthrough (Customer Portal):**
   - Log in as `demo_driver` / `ParkEase@Demo2026`.
   - Click **Find Parking** to browse active facilities (`University Main Parking`, `City Center Parking`).
   - View the visual bay grid (Car and Bike slots).
   - Select an available bay and book a slot.
   - Go to **My Bookings** to view the generated digital parking pass.

2. **Staff Operations Walkthrough (Human Gatekeeper):**
   - Log in as `demo_staff` / `ParkEase@Demo2026`.
   - Open the **Parking Operations Dashboard**.
   - Review live occupancy rates and active vehicle counts.
   - Select a confirmed arrival and click **Check-In** (records actual entry time).
   - Select an active parking session and click **Check-Out** (automatically calculates pro-rata duration fee and restores bay availability).

3. **Admin Analytics Walkthrough (Management Portal):**
   - Log in as `demo_admin` / `ParkEase@Demo2026`.
   - Open **Manage Parking** to add facilities or configure bay counts.
   - Inspect Chart.js operational graphs for revenue and turnover.
   - Access Django Admin at `/admin/` to inspect relational records.
