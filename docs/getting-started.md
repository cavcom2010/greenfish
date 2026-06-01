# Getting Started

This guide will help you set up Tinashe Takeaway on your local machine for development.

## Prerequisites

- Python 3.12+
- PostgreSQL (optional - SQLite works for local dev)
- Node.js (optional - for frontend development)

## Installation

### 1. Clone the Repository

```bash
cd /home/cmazh/django/greenfish
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database (SQLite for local development)
DATABASE_URL=

# Payments
PAYMENT_PROVIDER=stripe

# Stripe Payments (test key for development)
STRIPE_SECRET_KEY=sk_test_your_stripe_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_local_webhook_secret

# Mollie Payments (optional alternate provider)
MOLLIE_API_KEY=
MOLLIE_WEBHOOK_SECRET=

# Shop Settings
SHOP_NAME=Tinashe Takeaway
SHOP_ADDRESS=45 High Street, Your Town
SHOP_PHONE=+44 123 456 7890
SHOP_EMAIL=orders@tinashe.local
```

Customer checkout is online-payment-only. In local development, the demo payment flow is available when provider keys are not configured.

### 5. Run Migrations

```bash
python manage.py migrate --settings=config.settings.local
```

### 6. Create Superuser

```bash
python manage.py createsuperuser --settings=config.settings.local
```

### 7. Load Sample Data (Optional)

```bash
python manage.py shell --settings=config.settings.local
```

Then run:
```python
from apps.core.models import SiteSettings
from apps.menu.models import MenuCategory, MenuItem

# Create categories
cat1 = MenuCategory.objects.create(name="Mains", sort_order=1)
cat2 = MenuCategory.objects.create(name="Sides", sort_order=2)

# Create items
MenuItem.objects.create(category=cat1, name="Fish & Chips", price=8.99, is_popular=True)
MenuItem.objects.create(category=cat1, name="Burger Meal", price=7.49, is_popular=True)
MenuItem.objects.create(category=cat2, name="Chips", price=2.49)
```

### 8. Collect Static Files

```bash
python manage.py collectstatic --noinput --settings=config.settings.local
```

### 9. Start the Development Server

```bash
./deploy/home/start.sh
```

The app will be available at:
- **Customer App**: http://127.0.0.1:8006/
- **Admin Panel**: http://127.0.0.1:8006/admin/

## Development Workflow

### Making Changes

1. Edit code in `apps/` directory
2. Run migrations if models changed:
   ```bash
   python manage.py makemigrations --settings=config.settings.local
   python manage.py migrate --settings=config.settings.local
   ```
3. Collect static files if CSS/JS changed:
   ```bash
   python manage.py collectstatic --noinput --settings=config.settings.local
   ```
4. Restart the server:
   ```bash
   ./deploy/home/stop.sh
   ./deploy/home/start.sh
   ```

### Running Tests

```bash
python manage.py test --settings=config.settings.local
```

### Accessing the Database

```bash
python manage.py dbshell --settings=config.settings.local
```

## Next Steps

- [Configure Payments](configuration.md#payments)
- [Customize the menu](admin-guide.md#managing-menu)
- [Set up promotions](admin-guide.md#creating-offers)
- [Deploy to production](deployment.md)
