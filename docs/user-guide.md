# User Guide

How to use Tinashe Takeaway for customers and staff.

## For Customers

### Placing an Order

1. **Browse the Menu**
   - Visit the website on your phone
   - Scroll through categories (Mains, Sides, Drinks)
   - Tap on items to see details and add-ons

2. **Add Items to Cart**
   - Tap the "+" button on items
   - Select modifiers (e.g., extra cheese)
   - Choose quantity
   - Tap "Add to Basket"

3. **Review Cart**
   - Tap the basket icon at the bottom
   - Adjust quantities or remove items
   - Apply voucher code if you have one

4. **Checkout**
   - Enter your name and phone number
   - Add any special instructions
   - Tap "Pay" to proceed to secure payment

5. **Payment**
   - Complete payment via Stripe (cards, Apple Pay, etc.)
   - Wait for confirmation page

6. **Pickup**
   - Wait for SMS/email notification
   - Collect your order at the specified time

### Creating an Account (Optional)

1. Tap "Account" at the bottom
2. Tap "Create Account"
3. Enter your details
4. Verify your email

Benefits:
- Order history
- Faster checkout
- Exclusive offers

### Using Voucher Codes

1. Add items to cart
2. Go to checkout
3. Enter code in "Voucher Code" field
4. Tap "Apply"
5. Discount is applied automatically

## For Staff

### Order Board

The Order Board is the main interface for kitchen staff.

**Access:**
- Go to `/orders/dashboard/`
- Login with staff credentials

**Understanding the Board:**

| Status | Color | Action Needed |
|--------|-------|---------------|
| Confirmed | Yellow/Orange | Start preparing |
| Preparing | Blue | Continue cooking |
| Ready | Green | Notify customer |

**Managing Orders:**

1. **New Orders** appear automatically (page refreshes every 5 seconds)
2. **Sound notifications** play when new orders arrive
3. **Click status buttons** to update order progress:
   - "Start Preparing" → Moves to Preparing
   - "Ready" → Moves to Ready
   - "Complete" → Finishes order

**Order Card Information:**
- Order number
- Customer name and phone
- Items with quantities
- Special instructions (highlighted in red)
- Total amount

**Filtering Orders:**
- Use tabs at top to filter by status
- "All Active" shows confirmed, preparing, and ready

### Admin Panel

**Access:** `/admin/`

**Managing Menu:**

1. **Categories**
   - Go to Menu → Menu Categories
   - Add, edit, or reorder categories
   - Set icons (emojis work well)

2. **Items**
   - Go to Menu → Menu Items
   - Create new items with:
     - Name and description
     - Price
     - Category
     - Image (recommended size: 400x300px)
     - Preparation time
     - Dietary tags (vegetarian, spicy, etc.)
     - Modifiers (add-ons)

3. **Modifiers**
   - Go to Menu → Menu Modifiers
   - Create reusable modifiers
   - Set price adjustments
   - Assign to items

**Managing Orders:**

- View all orders with filters
- Update order status manually
- Process refunds
- Export order data

**Managing Offers:**

1. Go to Offers → Offers
2. Create new offer:
   - **Percentage Off**: e.g., 20% off
   - **Fixed Amount**: e.g., £5 off
   - **Free Item**: Add free item
   - **Bundle Deal**: Special combination price

3. Set conditions:
   - Minimum order amount
   - Applicable items/categories
   - Start and end dates
   - Usage limits

4. **Voucher Codes**
   - Create unique codes (e.g., "WELCOME20")
   - Link to an offer
   - Set usage limits per customer
   - Set total usage limits

**Site Settings:**

Go to Core → Site Settings to customize:
- Shop name and logo
- Address and contact info
- Opening hours (JSON format)
- Social media links

### Sample Opening Hours Format

```json
{
  "0": {"open": "09:00", "close": "22:00"},
  "1": {"open": "09:00", "close": "22:00"},
  "2": {"open": "09:00", "close": "22:00"},
  "3": {"open": "09:00", "close": "22:00"},
  "4": {"open": "09:00", "close": "23:00"},
  "5": {"open": "10:00", "close": "23:00"},
  "6": {"open": "10:00", "close": "21:00"}
}
```

(0=Monday, 6=Sunday)

## Tips

### For Customers

- Save the website to your home screen for app-like experience
- Create an account to save time on future orders
- Check the Offers page for current promotions
- Order ahead during peak times

### For Staff

- Keep the Order Board open on a tablet in the kitchen
- Enable sound for new order notifications
- Check special instructions carefully
- Update status promptly so customers know progress
- Use the Admin Panel on desktop for easier management

## Mobile App Experience

Customers can "install" the website as an app:

**iPhone/iPad:**
1. Open Safari
2. Tap Share button
3. Tap "Add to Home Screen"

**Android:**
1. Open Chrome
2. Tap Menu (three dots)
3. Tap "Add to Home Screen"

This creates an app icon that opens the PWA in full-screen mode without browser chrome.
