# سঞ্জীবনী (SANJEEVANI) – Blood Donor Connection Platform
## Complete Django Application

---

## 🩸 About Sanjeevani

**Sanjeevani (സഞ്ജീവനി)** means "life-giving" in Malayalam. This is a fully functional, bilingual (English + Malayalam) blood donor connection platform built for the people of Kerala.

**Tagline:** Donate Blood. Save Lives.  
**Malayalam Tagline:** ഒരു തുള്ളി രക്തം, ഒരു ജീവന് പ്രതീക്ഷ.

---

## ⚡ Quick Start (Windows)

### Option 1: Double-click the batch file
Just **double-click `run.bat`** in the `sanjeevaniweb` folder. It will:
1. Install all requirements
2. Run database migrations
3. Start the server
4. Open your browser at http://127.0.0.1:8000

### Option 2: Manual setup (Command Prompt or PowerShell)

```
cd sanjeevaniweb
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Then open: **http://127.0.0.1:8000**

---

## 👤 Create Admin Account

```
python manage.py createsuperuser
```

Admin panel: http://127.0.0.1:8000/admin/

---

## 🧪 Load Sample Donors (for testing)

```
python manage.py create_sample_data
```

This creates **15 sample donors** across all 14 Kerala districts with all blood groups.

**Sample login:**
- Username (mobile): `9876543201`
- Password: `Sanjeevani@123`

---

## 📁 Project Structure

```
sanjeevaniweb/
├── manage.py              ← Django management script
├── requirements.txt       ← Python dependencies
├── run.bat               ← Windows startup batch file
├── .env                  ← Environment variables
├── .env.example          ← Environment template
├── db.sqlite3            ← SQLite database (auto-created)
│
├── sanjeevaniweb/        ← Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── core/                 ← Main application
│   ├── models.py         ← Database models
│   ├── views.py          ← All views/logic
│   ├── forms.py          ← Django forms
│   ├── urls.py           ← URL routing
│   ├── admin.py          ← Admin configuration
│   ├── context_processors.py
│   └── management/
│       └── commands/
│           └── create_sample_data.py
│
├── templates/            ← HTML templates
│   ├── base.html         ← Master template (navbar + footer)
│   ├── home.html         ← Homepage
│   ├── notifications.html
│   ├── auth/
│   │   ├── login.html
│   │   └── register.html
│   ├── donors/
│   │   ├── _donor_card.html   ← Reusable donor card
│   │   ├── directory.html     ← Searchable donor list
│   │   ├── contact.html       ← Contact + confirmation flow
│   │   ├── whatsapp_confirm.html
│   │   ├── hospital_location.html
│   │   └── hospital_location_preview.html
│   ├── dashboard/
│   │   ├── donor.html         ← Donor dashboard
│   │   ├── receiver.html      ← Receiver dashboard
│   │   └── edit_profile.html
│   ├── pages/
│   │   ├── about.html
│   │   ├── contact.html
│   │   ├── privacy.html
│   │   └── terms.html
│   └── errors/
│       ├── 404.html
│       └── 500.html
│
├── static/
│   ├── css/main.css      ← All custom styles
│   └── js/main.js        ← JavaScript
│
└── locale/
    ├── en/LC_MESSAGES/django.po   ← English strings
    └── ml/LC_MESSAGES/django.po   ← Malayalam translations
```

---

## ✨ Features

### 🔐 Authentication
- Register with mobile number (auto-login after registration)
- Login with mobile number + password
- Secure password hashing via Django

### 🗓️ Donor Registration
- All 14 Kerala districts
- All 8 blood groups (A+, A-, B+, B-, AB+, AB-, O+, O-)
- Consent controls: directory visibility, contact sharing, donation date visibility
- Instant directory listing — no admin approval needed

### 🔍 Donor Directory
- Search by blood group, district, locality
- Filter available donors only
- Pagination (12 per page)
- Call button (tel: link) on every eligible card

### 📞 Two-Sided Confirmation System
1. **Receiver** clicks "Call Now" → phone dialer opens
2. **Receiver** confirms the call in Sanjeevani
3. **Donor** sees request in dashboard → Confirm or Decline
4. **Receiver** gets instant status popup (polls every 5–10 seconds)

### 💬 WhatsApp Integration
- **Message 1:** Confirmation message (after both sides confirm)
- **Message 2:** Hospital location (separate, after Message 1)
- Uses `wa.me` Click-to-Chat — no API key needed
- Pre-filled messages, user presses Send manually

### 🗺️ Manual Hospital Location
- Receiver enters: hospital name, district, full address, Google Maps link
- Google Maps link is validated before sending
- Separate from the confirmation WhatsApp message

### 📊 Admin Dashboard
- Full donor management
- Filter by blood group and district
- Activate/deactivate accounts
- View all contact request records
- Review abuse reports
- Activity logs

### 🌐 Bilingual (EN/ML)
- Language switcher in navbar on every page
- Session-based language memory
- Noto Sans Malayalam font for proper rendering

### 📱 Responsive Design
- Mobile-first Bootstrap 5
- Works on Android, iPhone, tablet, laptop, desktop

---

## 🗄️ Database Models

| Model | Purpose |
|-------|---------|
| `DonorProfile` | Donor's blood group, district, availability, consent |
| `DonorContactRequest` | Tracks each receiver→donor contact interaction |
| `HospitalLocationDetails` | Manual hospital info for location WhatsApp |
| `Notification` | In-app notifications for donors and receivers |
| `ContactMessage` | Contact form submissions |
| `AbuseReport` | Reports about inappropriate profiles |
| `ActivityLog` | Admin audit log |

---

## 🌐 Pages & URLs

| URL | Page |
|-----|------|
| `/` | Homepage |
| `/donors/` | Donor Directory |
| `/register/` | Donor Registration |
| `/login/` | Login |
| `/logout/` | Logout |
| `/contact/<id>/` | Contact + Confirmation Flow |
| `/dashboard/donor/` | Donor Dashboard |
| `/dashboard/receiver/` | Receiver Dashboard |
| `/profile/edit/` | Edit Donor Profile |
| `/notifications/` | All Notifications |
| `/about/` | About Sanjeevani |
| `/contact/` | Contact Us |
| `/privacy/` | Privacy Policy |
| `/terms/` | Terms and Conditions |
| `/admin/` | Admin Panel |

---

## 🔒 Security Features
- CSRF protection on all forms
- Login-required decorators on all protected views
- Server-side permission checks (can't see other users' requests)
- Secure password hashing (Django PBKDF2)
- Donor contact number hidden unless consent given
- WhatsApp URL only shown after mutual confirmation
- Environment variable for SECRET_KEY

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.13 + Django 5.2 |
| Database | SQLite (built-in) |
| Frontend | HTML5, CSS3, JavaScript |
| UI Framework | Bootstrap 5.3 |
| Icons | Bootstrap Icons 1.11 |
| Fonts | Noto Sans Malayalam + Inter |
| WhatsApp | wa.me Click-to-Chat |
| Calls | tel: links |
| Maps | Google Maps links (manual) |

---

## ⚙️ Environment Variables (.env)

```
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

For production:
- Set `DEBUG=False`
- Set a strong random `SECRET_KEY`
- Set `ALLOWED_HOSTS` to your domain

---

## 📞 Support

For blood donation emergencies, use the **Call Now** button in the donor directory.  
For platform issues: info@sanjeevani.kerala

---

*Sanjeevani — Built with ❤️ for the people of Kerala.*
