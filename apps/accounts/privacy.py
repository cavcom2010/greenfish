from django.utils import timezone

from apps.orders.models import Order

from .models import CustomerDataRequest, User


def _stringify(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if value is not None else ""


def _user_export_payload(user, email):
    orders = Order.objects.filter(user=user) if user else Order.objects.filter(customer_email__iexact=email)
    return {
        "user": {
            "id": user.pk if user else None,
            "email": user.email if user else email,
            "first_name": getattr(user, "first_name", ""),
            "last_name": getattr(user, "last_name", ""),
            "phone_number": getattr(user, "phone_number", ""),
        },
        "addresses": [],
        "orders": [
            {
                key: _stringify(value)
                for key, value in row.items()
            }
            for row in orders.values(
                "order_number",
                "customer_name",
                "customer_phone",
                "customer_email",
                "service_type",
                "delivery_address_line1",
                "delivery_address_line2",
                "delivery_city",
                "delivery_postcode",
                "subtotal",
                "discount_amount",
                "delivery_fee",
                "total_amount",
                "status",
                "payment_status",
                "created_at",
            )
        ],
    }


def _anonymise_customer(user, email):
    anonymised_email = f"anonymised-{timezone.now().timestamp():.0f}@example.invalid"
    orders = Order.objects.filter(user=user) if user else Order.objects.filter(customer_email__iexact=email)
    anonymise_order_personal_data(orders, anonymised_email=anonymised_email)
    if user:
        user.email = anonymised_email
        user.first_name = "Anonymised"
        user.last_name = "Customer"
        user.phone_number = ""
        user.is_active = False
        user.save(update_fields=["email", "first_name", "last_name", "phone_number", "is_active"])


def anonymise_order_personal_data(orders, *, anonymised_email="anonymised@example.invalid"):
    """Remove customer-identifying fields while retaining order/accounting records."""
    return orders.update(
        customer_name="Anonymised Customer",
        customer_phone="",
        customer_email=anonymised_email,
        delivery_address_line1="",
        delivery_address_line2="",
        delivery_city="",
        delivery_postcode="",
        delivery_formatted_address="",
        delivery_place_id="",
        delivery_latitude=None,
        delivery_longitude=None,
        special_instructions="",
        user=None,
        personal_data_anonymised_at=timezone.now(),
    )


def process_customer_data_request(data_request):
    data_request = CustomerDataRequest.objects.select_related("user").get(pk=data_request.pk)
    if data_request.status not in {CustomerDataRequest.Status.REQUESTED, CustomerDataRequest.Status.FAILED}:
        return data_request

    data_request.status = CustomerDataRequest.Status.PROCESSING
    data_request.save(update_fields=["status"])

    try:
        user = data_request.user or User.objects.filter(email__iexact=data_request.email).first()
        data_request.export_payload = _user_export_payload(user, data_request.email)
        if data_request.request_type == CustomerDataRequest.RequestType.ANONYMISATION:
            _anonymise_customer(user, data_request.email)
        data_request.status = CustomerDataRequest.Status.COMPLETED
        data_request.completed_at = timezone.now()
        data_request.notes = (data_request.notes + "\nProcessed successfully.").strip()
    except Exception as exc:
        data_request.status = CustomerDataRequest.Status.FAILED
        data_request.notes = (data_request.notes + f"\nFailed: {exc}").strip()

    data_request.save(update_fields=["status", "export_payload", "notes", "completed_at"])
    return data_request
