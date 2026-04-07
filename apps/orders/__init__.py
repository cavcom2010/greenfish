"""
Orders app - Order management and lifecycle.

This app contains:
- Order: Customer orders with status tracking
- OrderItem: Individual items within an order
- OrderStatusHistory: Audit log of status changes
- Cart views: Add to cart, view cart (uses session)
- Checkout views: Process orders
- Kitchen views: Kanban board for staff

Purpose: Complete order lifecycle from cart to completion.
Depends on: accounts (User), menu (MenuItem)
"""
