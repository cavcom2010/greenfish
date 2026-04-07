"""
Mollie payment service for Tinashe Takeaway.
"""
import logging

from django.conf import settings
from django.urls import reverse
from mollie.api.client import Client
from mollie.api.error import Error as MollieError

from apps.orders.models import Order

from .models import Payment, PaymentLog

logger = logging.getLogger(__name__)


class MolliePaymentService:
    """Service for handling Mollie payments."""
    
    def __init__(self):
        self.client = Client()
        api_key = getattr(settings, "MOLLIE_API_KEY", "")
        if api_key:
            self.client.set_api_key(api_key)
    
    def create_payment(self, order, request):
        """Create a new Mollie payment for an order."""
        try:
            # Build URLs
            base_url = f"{request.scheme}://{request.get_host()}"
            redirect_url = f"{base_url}{reverse('payments:return', args=[order.order_number])}"
            webhook_url = f"{base_url}{reverse('payments:webhook')}"
            
            # Create payment with Mollie
            payment_data = {
                "amount": {
                    "currency": getattr(settings, "CURRENCY", "GBP"),
                    "value": f"{order.total_amount:.2f}"
                },
                "description": f"Order {order.order_number} - {order.customer_name}",
                "redirectUrl": redirect_url,
                "webhookUrl": webhook_url,
                "metadata": {
                    "order_number": order.order_number,
                    "order_id": order.id,
                    "customer_name": order.customer_name,
                    "customer_email": order.customer_email,
                }
            }
            
            mollie_payment = self.client.payments.create(payment_data)
            
            # Create payment record
            payment = Payment.objects.create(
                order=order,
                mollie_payment_id=mollie_payment["id"],
                amount=order.total_amount,
                currency=getattr(settings, "CURRENCY", "GBP"),
                status=Payment.Status.PENDING,
                checkout_url=mollie_payment["checkoutUrl"],
                metadata=mollie_payment
            )
            
            # Log the event
            PaymentLog.objects.create(
                payment=payment,
                event_type="payment_created",
                event_data=mollie_payment
            )
            
            return payment
            
        except MollieError as e:
            logger.error(f"Mollie error creating payment: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            raise
    
    def get_payment(self, mollie_payment_id):
        """Get payment details from Mollie."""
        try:
            return self.client.payments.get(mollie_payment_id)
        except MollieError as e:
            logger.error(f"Mollie error getting payment: {e}")
            return None
    
    def update_payment_status(self, mollie_payment_id):
        """Update local payment status from Mollie."""
        try:
            payment = Payment.objects.get(mollie_payment_id=mollie_payment_id)
            mollie_payment = self.get_payment(mollie_payment_id)
            
            if not mollie_payment:
                return None
            
            old_status = payment.status
            new_status = mollie_payment["status"]
            
            # Map Mollie status to our status
            status_map = {
                "pending": Payment.Status.PENDING,
                "authorized": Payment.Status.AUTHORIZED,
                "paid": Payment.Status.PAID,
                "failed": Payment.Status.FAILED,
                "expired": Payment.Status.EXPIRED,
                "canceled": Payment.Status.CANCELLED,
            }
            
            payment.status = status_map.get(new_status, Payment.Status.PENDING)
            payment.mollie_payment_method = mollie_payment.get("method", "")
            payment.metadata = mollie_payment
            
            if payment.status == Payment.Status.PAID:
                payment.paid_at = mollie_payment.get("paidAt")
                payment.order.mark_as_paid()
            
            payment.save()
            
            # Log status change
            if old_status != payment.status:
                PaymentLog.objects.create(
                    payment=payment,
                    event_type="status_changed",
                    event_data={
                        "old_status": old_status,
                        "new_status": payment.status,
                        "mollie_status": new_status
                    }
                )
            
            return payment
            
        except Payment.DoesNotExist:
            logger.warning(f"Payment not found: {mollie_payment_id}")
            return None
        except Exception as e:
            logger.error(f"Error updating payment status: {e}")
            return None
    
    def refund_payment(self, payment, amount=None):
        """Refund a payment."""
        try:
            refund_data = {}
            if amount:
                refund_data["amount"] = {
                    "currency": payment.currency,
                    "value": f"{amount:.2f}"
                }
            
            self.client.payment_refunds.with_parent_id(
                payment.mollie_payment_id
            ).create(refund_data)
            
            payment.status = Payment.Status.REFUNDED
            payment.save()
            
            PaymentLog.objects.create(
                payment=payment,
                event_type="refunded",
                event_data={"amount": str(amount) if amount else "full"}
            )
            
            return True
            
        except MollieError as e:
            logger.error(f"Mollie error refunding payment: {e}")
            return False
