# Tinashe Takeaway - Documentation

Welcome to Tinashe Takeaway - A Premium Mobile-First Food Ordering PWA.

## Quick Links

- [Getting Started](getting-started.md) - Set up the project locally
- [Deployment Guide](deployment.md) - Deploy to DigitalOcean
- [Configuration](configuration.md) - Environment variables and settings
- [User Guide](user-guide.md) - How to use the app
- [Admin Guide](admin-guide.md) - Manage your takeaway
- [Operations Order Board](operations-order-board.md) - Staff workflow architecture, roles, statuses, and action model
- [Operations Runbook](operations-runbook.md) - Daily staff usage, setup, and troubleshooting for kitchen and collection boards
- [API Reference](api-reference.md) - API endpoints
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

## Project Overview

Tinashe Takeaway is a production-ready Django web application designed for takeaway businesses. It features:

- **Mobile-First Design** - Native app experience on smartphones
- **PWA Capabilities** - Installable on home screens, works offline
- **Operations Boards** - Separate kitchen and collection boards for live staff order handling
- **Mollie Payments** - Secure European payment processing
- **Promotions System** - Voucher codes and automatic discounts

## Architecture

```
greenfish/
├── apps/
│   ├── core/          # Site settings, utilities
│   ├── accounts/      # User authentication (django-allauth)
│   ├── menu/          # Menu categories and items
│   ├── orders/        # Order management, cart, checkout
│   ├── operations/    # Staff boards, workflows, permissions
│   ├── offers/        # Promotions and voucher codes
│   ├── payments/      # Mollie payment integration
│   └── pwa/           # Service worker, manifest
├── config/            # Django settings
├── templates/         # HTML templates
├── static/            # CSS, JS, icons
├── deploy/            # Deployment scripts
└── docs/              # Documentation
```

## Default Credentials

- **Admin Panel**: http://localhost:8006/admin/
  - Email: `admin@tinashe.com`
  - Password: `adminpass123`

## Support

For issues or questions, refer to the [Troubleshooting](troubleshooting.md) guide or check the deployment logs.
