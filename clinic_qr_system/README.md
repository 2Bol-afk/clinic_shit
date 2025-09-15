# Clinic QR System

## Setup

1. python3 -m venv .venv && source .venv/bin/activate
2. pip install django==5.1.1 pillow==10.4.0 qrcode[pil]==7.4.2 pandas==2.2.2 psycopg2-binary==2.9.9 python-dotenv==1.0.1 django-crispy-forms==2.3 crispy-bootstrap5==2024.2 openpyxl==3.1.5
3. Create a .env file in project root based on environment variables in settings (see .env.example in project root)
4. python manage.py migrate
5. python manage.py createsuperuser
6. python manage.py runserver

## Features
- Patient registration with QR code email
- Visit logging per service station
- Role-based dashboards (Admin, Reception, Doctor, Laboratory, Pharmacy, Vaccination)
- CSV/Excel daily reports

## Roles & Permissions
Run the bootstrap command to create default groups and assign baseline permissions:

```bash
python manage.py bootstrap_roles
```

Create users and assign them to groups (examples):

```bash
python manage.py shell -c "from django.contrib.auth.models import User, Group; u=User.objects.create_user('reception1', password='TempPass123!'); u.groups.add(Group.objects.get(name='Reception'))"
python manage.py shell -c "from django.contrib.auth.models import User, Group; u=User.objects.create_user('dr1', password='TempPass123!'); u.groups.add(Group.objects.get(name='Doctor'))"
python manage.py shell -c "from django.contrib.auth.models import User, Group; u=User.objects.create_user('lab1', password='TempPass123!'); u.groups.add(Group.objects.get(name='Laboratory'))"
python manage.py shell -c "from django.contrib.auth.models import User, Group; u=User.objects.create_user('pharm1', password='TempPass123!'); u.groups.add(Group.objects.get(name='Pharmacy'))"
python manage.py shell -c "from django.contrib.auth.models import User, Group; u=User.objects.create_user('vax1', password='TempPass123!'); u.groups.add(Group.objects.get(name='Vaccination'))"
```

Access:
- Login: /accounts/login/
- Reception dashboard: /dashboard/reception/
- Doctor dashboard: /dashboard/doctor/
- Lab dashboard: /dashboard/lab/
- Pharmacy dashboard: /dashboard/pharmacy/
- Vaccination dashboard: /dashboard/vaccination/
- Admin root dashboard: /dashboard/

## Apps
- patients
- visits
- dashboard

## Notes
- Default email backend is console in DEBUG.
- To enable PostgreSQL, set DB_* envs and install a server.
