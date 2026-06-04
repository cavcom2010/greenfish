from django import forms

from .models import LargeOrderRequest


class LargeOrderRequestForm(forms.ModelForm):
    class Meta:
        model = LargeOrderRequest
        fields = [
            "name",
            "company_name",
            "phone",
            "email",
            "event_datetime",
            "service_type",
            "delivery_address",
            "postcode",
            "guest_count",
            "requested_items",
        ]
        widgets = {
            "event_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "requested_items": forms.Textarea(attrs={"rows": 5}),
            "delivery_address": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        service_type = cleaned_data.get("service_type")
        delivery_address = (cleaned_data.get("delivery_address") or "").strip()
        postcode = (cleaned_data.get("postcode") or "").strip()

        if service_type == LargeOrderRequest.ServiceType.DELIVERY and not (delivery_address or postcode):
            raise forms.ValidationError("Please add a delivery address or postcode for large delivery requests.")

        return cleaned_data
