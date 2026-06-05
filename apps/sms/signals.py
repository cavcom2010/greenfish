"""SMS signals module.

Customer order SMS is intentionally queued from explicit payment/status
transition helpers, not from raw Order post_save, so unpaid orders cannot send
customer-confirmed messages.
"""
