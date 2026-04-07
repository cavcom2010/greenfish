"""
Payments app - Payment processing integration.

This app contains:
- Payment: Payment records and status
- PaymentLog: Audit trail of payment events
- MolliePaymentService: Mollie API integration
- Demo checkout: For testing without real payments

Purpose: Handle all payment processing.
Reusable: Can integrate with different payment providers.
Current: Mollie (cards, Apple Pay, iDEAL)
"""
