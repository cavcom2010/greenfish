# Application Architecture

## Overview

This Django project follows a **modular app architecture** where each app has a single responsibility and can potentially be reused in other projects.

## App Structure

### Layer 1: Infrastructure (Foundation)

| App | Purpose | Reusable | Dependencies |
|-----|---------|----------|--------------|
| `core` | Shared utilities, base models, common template tags | ✅ Yes | None |
| `config` | Site-wide configuration (SiteSettings) | ✅ Yes | None |

**core**: Contains `TimeStampedModel`, context processors, and shared utilities.

**config**: Business configuration (shop name, address, hours). 
*Note: Currently SiteSettings is in core for backward compatibility.*

---

### Layer 2: Identity (User Management)

| App | Purpose | Reusable | Dependencies |
|-----|---------|----------|--------------|
| `accounts` | User authentication + Customer profiles | ⚠️ Partial | None |

**accounts**: Combines authentication (User model) with business logic (CustomerProfile).

*Note: In a clean architecture, these would be separate:*
- `authentication`: User, login, registration
- `customers`: CustomerProfile, Address, preferences

*Kept combined for database compatibility.*

---

### Layer 3: Commerce (E-commerce Engine)

| App | Purpose | Reusable | Dependencies |
|-----|---------|----------|--------------|
| `menu` | Product catalog (categories, items, modifiers) | ✅ Yes | None |
| `cart` | Shopping cart (session-based) | ✅ Yes | None |
| `orders` | Order management, checkout, kitchen display | ⚠️ Partial | accounts, menu |
| `payments` | Payment processing (Mollie) | ✅ Yes | orders |

**menu**: Generic product catalog. Can be used for any restaurant/shop.

**cart**: Session-based cart. No database models. Works with any product catalog.

**orders**: Order lifecycle management. Depends on specific business flow.

**payments**: Payment gateway abstraction. Currently Mollie. Can add Stripe, etc.

---

### Layer 4: Marketing & Engagement

| App | Purpose | Reusable | Dependencies |
|-----|---------|----------|--------------|
| `offers` | Vouchers, promotions, discounts | ✅ Yes | orders |
| `loyalty` | Points program, referrals | ✅ Yes | accounts |
| `sms` | SMS notifications (Twilio) | ✅ Yes | None |
| `mealdeals` | Combo meals, bundles | ✅ Yes | menu |

**offers**: Discount codes and automatic promotions.

**loyalty**: Points-based rewards system.

**sms**: SMS notification service. Currently Twilio.

**mealdeals**: Bundle/combo management.

---

### Layer 5: Features

| App | Purpose | Reusable | Dependencies |
|-----|---------|----------|--------------|
| `pwa` | Progressive Web App support | ✅ Yes | None |

**pwa**: Service worker, manifest, offline support.

---

## App Dependencies Graph

```
config, core          (infrastructure)
    ↓
accounts              (identity)
    ↓
menu                  (catalog)
    ↓ ↓ ↓
    cart              (shopping)
    orders            (checkout)
    mealdeals         (bundles)
        ↓
        payments      (processing)
        offers        (discounts)
        loyalty       (rewards)
sms                   (notifications)
pwa                   (web app)
```

## Key Design Principles

### 1. Separation of Concerns
Each app handles one domain:
- `menu` = products only, no orders
- `orders` = orders only, no payments
- `payments` = payments only, generic gateway

### 2. Reusability
Apps like `cart`, `menu`, `payments` can be copied to other projects with minimal changes.

### 3. Clear Dependencies
Lower layers don't depend on upper layers:
- ✅ `cart` doesn't import from `orders`
- ✅ `menu` doesn't import from `orders`
- ❌ Would be wrong: `menu` importing `orders.Order`

### 4. Session-Based Cart
The cart app uses sessions (no database) making it:
- Fast (no DB queries for cart operations)
- Simple (no migrations needed)
- Reusable (works with any product model)

## Using Apps in Other Projects

### Example: Reusing the Cart App

```python
# In another project's settings.py
INSTALLED_APPS = [
    # ...
    'apps.cart',
]

# In views
from apps.cart.services import CartService

def add_to_cart(request):
    cart = CartService(request)
    cart.add_item(
        item_id=product.id,
        name=product.name,
        price=product.price,
        quantity=1
    )
```

### Example: Reusing the Menu App

```python
# In another project's settings.py
INSTALLED_APPS = [
    # ...
    'apps.menu',
]

# In templates
{% for category in categories %}
    <h2>{{ category.name }}</h2>
    {% for item in category.items.all %}
        <p>{{ item.name }} - ${{ item.price }}</p>
    {% endfor %}
{% endfor %}
```

## Future Improvements

### Short Term
1. ✅ Add docstrings to all apps (Done)
2. ✅ Create cart service (Done)
3. ⬜ Move SiteSettings to config app (Requires migration)
4. ⬜ Split accounts into authentication + customers (Requires migration)

### Long Term
1. ⬜ Convert cart to use database (for persistent carts)
2. ⬜ Add more payment providers to payments app
3. ⬜ Make orders app more generic (configurable statuses)
4. ⬜ Extract notifications base class (SMS, Email, Push)

## Testing Individual Apps

Each app should be testable independently:

```bash
# Test only the cart app
python manage.py test apps.cart

# Test only the menu app
python manage.py test apps.menu
```

## Adding a New App

When adding a new app:

1. Create directory in `apps/`
2. Add `__init__.py` with docstring
3. Add to `settings.INSTALLED_APPS`
4. Document purpose in this file
5. List dependencies
6. Mark as reusable or project-specific

## Questions?

For architecture decisions, refer to:
- Django docs: https://docs.djangoproject.com/
- Django best practices: https://django-best-practices.readthedocs.io/
