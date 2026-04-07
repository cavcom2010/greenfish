"""
Cart app - Shopping cart management (session-based).

This app contains:
- CartService: Session-based cart operations
- Views: Add item, update quantity, remove item, view cart

Purpose: Manage shopping cart before checkout.
Design: Session-based (no database models)
Reusable: Works with any product catalog

Note: This is separate from orders to allow reuse.
Cart -> Checkout -> Order creation
"""
