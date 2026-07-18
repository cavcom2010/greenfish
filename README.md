# Restaurant Online Ordering System 🍽️

A complete, production-ready food ordering platform built with Django. Features mobile-first design, real-time kitchen management, SMS notifications, loyalty programs, and seamless payment integration.

[![Django](https://img.shields.io/badge/Django-6.x-green.svg)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Commercial-blue.svg)]()

## 🎯 What You Get

### Customer-Facing Features
- **📱 Progressive Web App** - Install on phone, works offline
- **🛒 Easy Ordering** - Browse menu, customize items, checkout in seconds
- **⏰ Pickup Scheduling** - Choose convenient pickup times
- **💳 Multiple Payment Options** - Cards (Mollie), Apple Pay, or Pay in Store
- **🎁 Loyalty Program** - Earn points, get rewards, refer friends
- **📲 SMS Notifications** - Order confirmations and ready alerts
- **📜 Order History** - Reorder favorites with one click

### Kitchen & Staff Features
- **📊 Real-Time Order Board** - Live updating kanban display
- **⏱️ Order Timers** - Track prep time, prioritize urgent orders
- **🔔 Sound Notifications** - Alert on new orders
- **📝 Special Instructions** - Clear display of customer notes
- **📱 Mobile-Friendly** - Access from any device

### Admin Features
- **🎨 Customizable Branding** - Shop name, logo, colors, contact info
- **🍔 Menu Management** - Categories, items, modifiers, pricing
- **🏷️ Promotions** - Voucher codes, percentage discounts
- **📈 Order Analytics** - Track sales, popular items
- **👥 Customer Management** - View history, manage loyalty points

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL (recommended for production) or SQLite (development)
- Mollie account (for payments)
- Twilio account (for SMS)

### 1. Installation

```bash
# Clone the repository
cd /path/to/project

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Required Settings
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database (PostgreSQL recommended for production)
DATABASE_URL=postgres://user:password@localhost:5432/dbname

# Payment (Mollie)
MOLLIE_API_KEY=live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MOLLIE_WEBHOOK_SECRET=your-webhook-secret

# SMS (Twilio)
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=+1234567890

# Shop Settings
SHOP_NAME=Your Restaurant Name
SHOP_ADDRESS=123 Main Street, City
SHOP_PHONE=+44 123 456 7890
SHOP_EMAIL=orders@yourdomain.com
CURRENCY=GBP
```

### 3. Database Setup

```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Initialize site settings
python manage.py shell -c "from apps.core.models import SiteSettings; SiteSettings.get()"
```

### 4. Run Development Server

```bash
python manage.py runserver
```

Visit http://127.0.0.1:8000/

---

## 📋 Configuration Guide

### Shop Branding

1. **Admin Panel**: Go to `/admin/` → Core → Site Settings
2. Update:
   - Shop name
   - Address
   - Phone & email
   - Logo & favicon
   - Social media links
   - Opening hours

### Payment Setup (Mollie)

1. Create account at [mollie.com](https://www.mollie.com)
2. Get API key from dashboard
3. Add webhook URL: `https://yourdomain.com/payments/webhook/`
4. Configure payment methods (cards, Apple Pay, etc.)

### SMS Setup (Twilio)

1. Create account at [twilio.com](https://www.twilio.com)
2. Purchase a phone number
3. Add credentials to `.env`
4. Test SMS delivery

### Menu Management

1. **Categories**: Admin → Menu → Categories
   - Create categories (e.g., Starters, Mains, Drinks)
   - Set icons, sort order

2. **Menu Items**: Admin → Menu → Items
   - Add items with descriptions, prices
   - Upload photos
   - Assign categories

3. **Modifiers**: Admin → Menu → Modifiers
   - Create options (e.g., "Extra cheese", "Spicy")
   - Set price adjustments
   - Assign to items

---

## 🏗️ Production Deployment

### Option 1: Using Included Scripts

```bash
# Configure production settings
export DJANGO_SETTINGS_MODULE=config.settings.production

# Run deployment script
./deploy/production/deploy.sh
```

### Option 2: Manual Deployment

See [docs/deployment.md](docs/deployment.md) for detailed instructions.

### Post-Deployment Checklist

- [ ] Set `DEBUG=False`
- [ ] Configure SSL certificate
- [ ] Set up database backups
- [ ] Configure error tracking (Sentry)
- [ ] Test payment flow
- [ ] Test SMS notifications
- [ ] Verify PWA manifest
- [ ] Set up monitoring

---

## 💾 Backup Strategy

### Automated Daily Backups

```bash
# Add to crontab (crontab -e)
0 2 * * * /path/to/project/backup.sh
```

### Manual Backup

```bash
# Backup database
python manage.py dumpdata > backup_$(date +%Y%m%d).json

# Backup media files
tar -czf media_backup_$(date +%Y%m%d).tar.gz media/
```

---

## 🔧 Troubleshooting

### Common Issues

**Payments not working**
- Check Mollie API key is correct
- Verify webhook URL is accessible
- Check `MOLLIE_WEBHOOK_SECRET` matches

**SMS not sending**
- Verify Twilio credentials
- Check phone number format (E.164)
- Check Twilio account balance

**Orders not appearing in kitchen**
- Verify order status updates
- Check kitchen board URL: `/orders/kanban/`
- Ensure staff user has permissions

**Static files not loading**
- Run `python manage.py collectstatic`
- Check `STATIC_ROOT` and `STATIC_URL`
- Verify web server configuration

---

## 📂 Documentation

| Document | Description |
|----------|-------------|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | For restaurant staff using the system |
| [docs/admin-guide.md](docs/admin-guide.md) | For administrators configuring the platform |
| [docs/deployment.md](docs/deployment.md) | Production deployment instructions |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Codebase structure and architecture |
| [docs/MULTI_CLIENT_SETUP.md](docs/MULTI_CLIENT_SETUP.md) | **Using this for multiple clients** |

## 🏢 Multi-Client Setup

This codebase is designed to be deployed for multiple restaurants. Each client gets their own isolated instance with:
- Separate Git repository
- Separate database
- Separate deployment
- Custom branding via SiteSettings

See [docs/MULTI_CLIENT_SETUP.md](docs/MULTI_CLIENT_SETUP.md) for the complete workflow.

## 📞 Support

For technical support or customization:
- Email: support@yourdomain.com
- Documentation: See links above

---

## 📄 License

This is commercial software. All rights reserved.

---

## 🙏 Credits

Built with:
- Django - Web framework
- HTMX - Dynamic interactions
- Mollie - Payment processing
- Twilio - SMS notifications
- Phosphor Icons - Beautiful icons

---

**Ready to take orders!** 🚀
