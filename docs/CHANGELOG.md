# Changelog

All notable changes to Tinashe Takeaway will be documented in this file.

## [1.0.0] - 2026-04-05

### Added

#### Core Features
- Mobile-first responsive design with PWA support
- Bottom navigation (Home, Order, Offers, Account)
- Location picker with shop address
- Service type toggle (Pickup/Delivery placeholder)
- Hero banner for promotions
- Category pills for menu filtering

#### Menu System
- Menu categories with icons and sorting
- Menu items with images, descriptions, prices
- Dietary tags support (vegetarian, spicy, etc.)
- Menu modifiers with price adjustments
- "Popular" item highlighting
- Preparation time estimates

#### Cart & Orders
- Session-based shopping cart
- Add/remove/update cart items
- Quantity controls
- Modifier selection in item modal
- Floating basket bar
- Guest checkout (no account required)
- Order confirmation page

#### Payments
- Mollie payment integration
- Payment Intents API support
- Webhook handling for status updates
- Secure checkout flow
- Payment status tracking

#### Offers & Promotions
- Percentage off offers
- Fixed amount off offers
- Free item offers
- Bundle deals
- Voucher code system
- Hero banner display for offers
- Usage limits (total and per customer)

#### Real-Time Order Board
- Live updating order list (HTMX polling)
- Status workflow: Pending → Confirmed → Preparing → Ready → Completed
- Sound notifications for new orders
- Order filtering by status
- Status action buttons
- Special instructions display

#### User Accounts
- Custom user model (email-based login)
- Django allauth integration
- Registration and login
- User profiles with order history
- Favorite items
- Phone number field

#### Admin Panel
- Full Django admin interface
- Menu management
- Order management with bulk actions
- Offer and voucher management
- Site settings configuration
- Payment log viewing

#### PWA Features
- Web App Manifest
- Service Worker with caching
- Offline fallback page
- Add to Home Screen support
- Theme color and icons

#### Deployment
- Home deployment scripts (start.sh, stop.sh)
- Nginx + Gunicorn configuration
- Port 8026 for Gunicorn
- Port 8006 for Nginx
- Systemd service template
- DigitalOcean deployment guide

### Technical Stack
- Django 6.x
- PostgreSQL (with SQLite fallback)
- python-decouple for environment variables
- dj-database-url for database configuration
- HTMX for dynamic updates
- Alpine.js for reactive components
- Mollie API for payments
- Phosphor Icons for UI icons

### Security
- CSRF protection
- Secure cookie settings for production
- HSTS headers
- SSL redirect
- Environment-based configuration

### Documentation
- Getting Started guide
- Deployment guide
- Configuration reference
- User guide
- Admin guide
- API reference
- Troubleshooting guide
- Deployment checklist

---

## Future Releases

### [1.1.0] - Planned

#### Features
- [ ] Delivery radius and postcode validation
- [ ] Real-time order tracking for customers
- [ ] Push notifications via web push
- [ ] SMS notifications via Twilio
- [ ] Inventory management
- [ ] Multi-location support
- [ ] Advanced analytics dashboard
- [ ] Customer loyalty program
- [ ] Review and rating system
- [ ] Table reservations

#### Improvements
- [ ] Enhanced PWA offline capabilities
- [ ] Image optimization (WebP support)
- [ ] Caching layer (Redis)
- [ ] Background task processing (Celery)
- [ ] API rate limiting
- [ ] Enhanced search functionality
- [ ] Bulk menu import/export
- [ ] Automated testing suite

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Incompatible API changes
- **MINOR**: Added functionality (backwards compatible)
- **PATCH**: Bug fixes (backwards compatible)

---

## Contributing

When adding changes:

1. Add entry to [Unreleased] section
2. Use categories: Added, Changed, Deprecated, Removed, Fixed, Security
3. Reference issue numbers where applicable
4. Keep entries concise but descriptive

---

**Note:** This changelog documents the initial release. For updates, check the repository or documentation folder.
