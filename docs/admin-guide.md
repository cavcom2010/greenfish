# Admin Guide

Complete guide for managing your Tinashe Takeaway system.

## Table of Contents

1. [Getting Started with Admin](#getting-started)
2. [Managing Menu](#managing-menu)
3. [Creating Offers](#creating-offers)
4. [Managing Orders](#managing-orders)
5. [Customer Management](#customer-management)
6. [Reports and Analytics](#reports-and-analytics)

## Getting Started

### Accessing the Admin Panel

Navigate to: `https://yourdomain.com/admin/`

Login with your superuser credentials created during setup.

### Admin Dashboard Overview

The Django Admin interface is organized by apps:

- **ACCOUNTS** - User and customer management
- **CORE** - Site settings
- **MENU** - Categories, items, modifiers
- **OFFERS** - Promotions and voucher codes
- **ORDERS** - Order management
- **PAYMENTS** - Payment records and logs
- **SITES** - Django sites framework
- **SOCIAL ACCOUNTS** - Social authentication (if configured)

## Managing Menu

### Menu Categories

Categories organize your menu (e.g., Mains, Sides, Drinks).

**Creating a Category:**

1. Go to Menu → Menu Categories → Add
2. Fill in:
   - **Name**: Category name (e.g., "Burgers")
   - **Description**: Optional description
   - **Sort Order**: Number for ordering (lower = first)
   - **Is Active**: Uncheck to hide temporarily
   - **Icon**: Emoji or text (e.g., 🍔)
   - **Image**: Optional category image

**Best Practices:**
- Use consistent sort orders (10, 20, 30...)
- Choose recognizable emojis for icons
- Keep categories broad (5-8 categories maximum)

### Menu Items

Items are individual products customers can order.

**Creating an Item:**

1. Go to Menu → Menu Items → Add
2. Fill in required fields:
   - **Category**: Select parent category
   - **Name**: Item name
   - **Price**: Base price

3. Optional fields:
   - **Description**: Ingredients, details
   - **Image**: Product photo (400x300px recommended)
   - **Is Available**: Uncheck to temporarily hide
   - **Is Popular**: Highlights on homepage
   - **Preparation Time**: Estimated kitchen minutes; the slowest ordered item drives the order ready-time estimate
   - **Dietary Tags**: Format as JSON list: `["vegetarian", "spicy"]`
   - **Modifiers**: Select applicable add-ons
   - **Sort Order**: Ordering within category

**Image Guidelines:**
- Format: JPG or PNG
- Size: 400x300 pixels (4:3 ratio)
- Max file size: 2MB
- Well-lit, appetizing photos

### Menu Modifiers

Modifiers are add-ons customers can select (e.g., "Extra Cheese").

**Creating a Modifier:**

1. Go to Menu → Menu Modifiers → Add
2. Set:
   - **Name**: Modifier name
   - **Price Adjustment**: Additional cost (0 for free)
   - **Is Active**: Enable/disable

**Linking Modifiers to Items:**

When editing a menu item:
1. Find "Modifiers" field
2. Select applicable modifiers
3. Save

**Examples:**

| Modifier | Price | Use Case |
|----------|-------|----------|
| Extra Cheese | £0.50 | Burgers, pizzas |
| Large Size | £1.00 | Drinks |
| Add Bacon | £0.75 | Burgers, salads |
| Gluten-Free Bun | £0.50 | Burgers |

## Creating Offers

### Types of Offers

1. **Percentage Off**: e.g., "20% off your order"
2. **Fixed Amount Off**: e.g., "£5 off orders over £20"
3. **Free Item**: e.g., "Free chips with any main"
4. **Bundle Deal**: e.g., "Meal deal for £10"

### Creating an Offer

1. Go to Offers → Offers → Add
2. Fill in details:

**Basic Information:**
- **Name**: Internal name (e.g., "Summer Sale 2024")
- **Description**: Customer-facing description
- **Offer Type**: Select type from dropdown
- **Value**: Percentage or amount

**Conditions:**
- **Minimum Order Amount**: Threshold to qualify (0 for no minimum)
- **Applicable Items**: Specific items (leave empty for all)
- **Applicable Categories**: Specific categories (leave empty for all)

**Validity:**
- **Start Date**: When offer becomes active
- **End Date**: When offer expires
- **Is Active**: Enable/disable

**Display:**
- **Hero Title**: Short headline (e.g., "Summer Sale!")
- **Hero Subtitle**: Longer description
- **Hero Image**: Banner image
- **Display on Hero**: Show on homepage carousel
- **Display Order**: Priority in carousel

**Limits:**
- **Max Usage Count**: Total uses allowed (0 = unlimited)

### Creating Voucher Codes

Voucher codes allow customers to apply offers.

1. Go to Offers → Voucher Codes → Add
2. Fill in:
   - **Code**: Unique code (e.g., "WELCOME20", "CHIPS20")
   - **Offer**: Select the linked offer
   - **Max Uses**: Total allowed uses (0 = unlimited)
   - **Max Uses Per Customer**: Limit per account (1 typical)
   - **Valid From/Until**: Date range
   - **Is Active**: Enable/disable

**Promotion Ideas:**

| Code | Offer | Purpose |
|------|-------|---------|
| WELCOME20 | 20% off | New customers |
| FREEFRIDAY | Free chips | Friday promotion |
| FAMILY25 | £25 family meal | Weekend special |
| STUDENT10 | 10% off | Student discount |

## Managing Orders

### Order Status Workflow

```
Pending Payment → Confirmed → Preparing → Ready → Completed
       ↓
   Cancelled
```

**Status Definitions:**

| Status | Description | Action |
|--------|-------------|--------|
| Pending Payment | Awaiting payment | System auto-updates |
| Confirmed | Paid, awaiting preparation | Start cooking |
| Preparing | Being cooked | Continue cooking |
| Ready | Ready for pickup | Notify customer |
| Completed | Customer collected | Archive |
| Cancelled | Order cancelled | Refund if paid |

### Viewing Orders

Go to Orders → Orders to see all orders.

**Filtering:**
- Use sidebar filters (Status, Payment Status)
- Use date filters
- Search by order number or customer name

### Processing Orders

**Bulk Actions:**
1. Select orders using checkboxes
2. Choose action from dropdown:
   - Mark as Confirmed
   - Mark as Preparing
   - Mark as Ready
   - Mark as Completed

**Individual Order:**
1. Click order number
2. View details:
   - Customer info
   - Items ordered
   - Payment status
   - Special instructions
3. Update status if needed
4. Add internal notes

### Refunds

To process a refund:

1. Go to Payments → Payments
2. Find the payment
3. Click "Refresh payment status" to verify
4. Contact customer for refund method
5. Process refund via Mollie Dashboard
6. Update order status to "Refunded"

## Customer Management

### Viewing Customers

Go to Accounts → Users to see registered customers.

**Customer Profile includes:**
- Contact information
- Order history
- Favorite items
- Marketing preferences

### Customer Actions

**View Orders:**
1. Click customer email
2. Scroll to "Orders" section
3. See all past orders

**Update Information:**
1. Edit fields as needed
2. Save changes

**Export Data:**
1. Select customers
2. Choose "Export selected" action
3. Select format (CSV, Excel)

## Reports and Analytics

### Order Reports

**Daily Summary:**
```bash
# View via shell
python manage.py shell

from apps.orders.models import Order
from django.utils import timezone
from datetime import timedelta

today = timezone.now().date()
orders_today = Order.objects.filter(
    created_at__date=today,
    payment_status='paid'
)

total_revenue = sum(o.total_amount for o in orders_today)
order_count = orders_today.count()
print(f"Today's Orders: {order_count}")
print(f"Today's Revenue: £{total_revenue}")
```

**Popular Items:**
```python
from apps.orders.models import OrderItem
from django.db.models import Sum

popular = OrderItem.objects.values('item_name').annotate(
    total_quantity=Sum('quantity')
).order_by('-total_quantity')[:10]

for item in popular:
    print(f"{item['item_name']}: {item['total_quantity']}")
```

### Exporting Data

**Orders Export:**
1. Go to Orders → Orders
2. Filter by date range if needed
3. Select all or specific orders
4. Action: Export to CSV

**Payment Report:**
1. Go to Payments → Payments
2. Filter by date/status
3. Export for accounting

## Best Practices

### Menu Management

1. **Keep it Simple**: 5-8 categories, 15-30 items
2. **Use Great Photos**: Professional food photography
3. **Clear Descriptions**: List main ingredients
4. **Regular Updates**: Seasonal items, remove unavailable

### Offer Strategy

1. **Limited Time**: Create urgency
2. **Clear Terms**: Minimum spends, exclusions
3. **Track Performance**: Monitor usage rates
4. **Rotate Promotions**: Keep customers engaged

### Order Management

1. **Update Status Promptly**: Keep customers informed
2. **Check Special Instructions**: Avoid mistakes
3. **Track Prep Times**: Improve estimates
4. **Follow Up**: Contact for cancelled orders

## Maintenance Tasks

### Daily
- Check Order Board for new orders
- Update menu availability
- Review cancelled orders

### Weekly
- Check low-stock items
- Review popular items report
- Update offers/promotions

### Monthly
- Export sales reports
- Review customer feedback
- Update menu photos
- Check payment reconciliation

## Getting Help

- [Troubleshooting Guide](troubleshooting.md)
- [Configuration Reference](configuration.md)
- Django Admin documentation: https://docs.djangoproject.com/en/stable/ref/contrib/admin/
