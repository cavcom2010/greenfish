# Administrator Guide

## Getting Started

### Accessing the Admin Panel

1. Go to: `https://yourdomain.com/admin/`
2. Login with your superuser credentials
3. You'll see the main dashboard

## Daily Operations

### Managing Orders

**View Orders:**
- Go to Orders → Orders
- Filter by status: Pending, Confirmed, Preparing, Ready, Completed
- Search by order number or customer name

**Update Order Status:**
1. Open order detail page
2. Change status dropdown
3. Save

**Kitchen Display:**
- Visit: `https://yourdomain.com/orders/kanban/`
- Real-time order updates
- Click buttons to change status
- Sound notifications for new orders

### Menu Management

**Add New Category:**
1. Menu → Categories → Add
2. Enter name (e.g., "Burgers")
3. Choose icon emoji
4. Set sort order
5. Save

**Add Menu Item:**
1. Menu → Items → Add
2. Fill in:
   - Name
   - Description
   - Price
   - Category
   - Upload image
3. Save

**Add Modifiers (Options):**
1. Menu → Modifiers → Add
2. Create modifier (e.g., "Extra Cheese")
3. Set price adjustment
4. Assign to menu items

### Promotions & Vouchers

**Create Voucher Code:**
1. Offers → Voucher Codes → Add
2. Set:
   - Code (e.g., "WELCOME10")
   - Discount type (percentage or fixed)
   - Discount value
   - Valid dates
   - Usage limit
3. Save

**Create Automatic Offer:**
1. Offers → Offers → Add
2. Configure conditions (e.g., "Order over £30")
3. Set reward (discount or free item)
4. Save

### Customer Management

**View Customers:**
- Accounts → Users
- See order history per customer
- Manage loyalty points

**Award Loyalty Points:**
1. Find customer
2. Edit profile
3. Adjust points
4. Save

### Site Settings

**Update Shop Information:**
1. Core → Site Settings
2. Update:
   - Shop name
   - Address
   - Phone
   - Email
   - Opening hours
3. Upload logo
4. Save

## Reports & Analytics

**Popular Items:**
- Orders → Order Items
- Group by item
- Sort by quantity

**Sales Summary:**
- Orders → Orders
- Filter by date range
- Export to CSV if needed

**Customer Analytics:**
- Accounts → Users
- View total orders per customer
- See loyalty point balances

## Troubleshooting

### Order Not Appearing in Kitchen

1. Check order status is "Confirmed"
2. Verify customer completed checkout
3. Refresh kitchen board

### Payment Issues

1. Check Stripe dashboard for failed payments
2. Verify webhook URL is correct
3. Check logs in Admin

### Menu Item Not Showing

1. Verify item is marked "Available"
2. Check category is active
3. Ensure item has price > 0

## Best Practices

1. **Regular Backups** - Verify backups run daily
2. **Monitor Orders** - Check kitchen board regularly
3. **Update Menu** - Keep prices and availability current
4. **Test Payments** - Run test orders weekly
5. **Review Analytics** - Check popular items monthly

## Support

For technical issues:
- Check logs in server
- Review error tracking (if configured)
- Contact your developer

For feature requests:
- Document requirements
- Contact your developer for quote
