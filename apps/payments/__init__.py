"""
Payments app - Payment processing integration.

This app contains:
- Payment: Payment records and status
- PaymentLog: Audit trail of payment events
- StripePaymentService: Stripe Checkout integration
- Offline fallback: Customer-approved unpaid hold when the provider is down
- Demo checkout: For testing without real payments

Purpose: Handle all payment processing.
Current: Stripe (cards, Apple Pay, Google Pay via Stripe Checkout)
"""
