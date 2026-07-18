"""
Analytics views - Business intelligence dashboards.
"""
import csv
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.menu.models import MenuItem
from apps.orders.models import Order
from apps.payments.models import Payment, RefundRequest

VALID_DAY_RANGES = {7, 30, 90}


def _parse_days(raw_days):
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        return 30
    return days if days in VALID_DAY_RANGES else 30


@staff_member_required
def dashboard(request):
    """Main analytics dashboard."""
    days = _parse_days(request.GET.get("days", 30))
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    orders = Order.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
    paid_orders = orders.filter(payment_status=Order.PaymentStatus.PAID)
    refunded_orders = orders.filter(payment_status=Order.PaymentStatus.REFUNDED)

    total_revenue = paid_orders.aggregate(total=Sum("total_amount"))["total"] or 0
    refunded_total = refunded_orders.aggregate(total=Sum("total_amount"))["total"] or 0
    delivery_fees = paid_orders.aggregate(total=Sum("delivery_fee"))["total"] or 0
    total_orders = paid_orders.count()
    placed_orders = orders.count()
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    daily_average = total_revenue / days if days > 0 else 0

    status_counts = orders.values("status").annotate(count=Count("id")).order_by("-count")

    popular_items = (
        MenuItem.objects.filter(
            order_items__order__created_at__gte=start_date,
            order_items__order__payment_status=Order.PaymentStatus.PAID,
        )
        .annotate(
            order_count=Count("order_items"),
            total_revenue=Sum("order_items__item_price"),
        )
        .order_by("-order_count")[:10]
    )

    peak_hours = (
        paid_orders.annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("hour")
    )

    last_7_days = timezone.now() - timedelta(days=7)
    daily_rows = {
        row["day"]: row
        for row in Order.objects.filter(
            created_at__gte=last_7_days,
            payment_status=Order.PaymentStatus.PAID,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(revenue=Sum("total_amount"), orders=Count("id"))
    }
    daily_sales = []
    max_daily_revenue = 0
    for offset in range(7):
        day = (last_7_days + timedelta(days=offset)).date()
        row = daily_rows.get(day, {})
        day_revenue = row.get("revenue") or 0
        max_daily_revenue = max(max_daily_revenue, day_revenue)
        daily_sales.append(
            {
                "date": day.strftime("%a"),
                "revenue": day_revenue,
                "orders": row.get("orders") or 0,
            }
        )

    for day in daily_sales:
        if max_daily_revenue:
            day["bar_percent"] = max(4, int((day["revenue"] / max_daily_revenue) * 100))
        else:
            day["bar_percent"] = 4

    payment_methods = (
        Payment.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
        .values("provider", "status")
        .annotate(count=Count("id"), revenue=Sum("amount"))
        .order_by("provider", "-count")
    )
    service_mix = (
        paid_orders.values("service_type")
        .annotate(count=Count("id"), revenue=Sum("total_amount"), delivery_fees=Sum("delivery_fee"))
        .order_by("service_type")
    )
    refunds = RefundRequest.objects.filter(
        requested_at__gte=start_date,
        requested_at__lte=end_date,
    ).values("status").annotate(count=Count("id"), amount=Sum("amount")).order_by("status")

    context = {
        "days": days,
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "placed_orders": placed_orders,
        "refunded_total": refunded_total,
        "delivery_fees": delivery_fees,
        "avg_order_value": avg_order_value,
        "daily_average": daily_average,
        "status_counts": list(status_counts),
        "popular_items": popular_items,
        "peak_hours": list(peak_hours),
        "daily_sales": daily_sales,
        "payment_methods": list(payment_methods),
        "service_mix": list(service_mix),
        "refunds": list(refunds),
    }
    return render(request, "analytics/dashboard.html", context)


@staff_member_required
def sales_report(request):
    """Detailed sales report."""
    return dashboard(request)


@staff_member_required
def sales_export(request):
    """CSV export for paid/refunded order reconciliation."""
    days = _parse_days(request.GET.get("days", 30))
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    orders = (
        Order.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
        .select_related("payment")
        .order_by("created_at")
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="sales-{days}-days.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "created_at",
            "order_number",
            "service_type",
            "status",
            "payment_status",
            "payment_provider",
            "subtotal",
            "discount",
            "delivery_fee",
            "total",
            "voucher_code",
        ]
    )
    for order in orders:
        payment = getattr(order, "payment", None)
        writer.writerow(
            [
                order.created_at.isoformat(),
                order.order_number,
                order.service_type,
                order.status,
                order.payment_status,
                payment.provider if payment else "",
                order.subtotal,
                order.discount_amount,
                order.delivery_fee,
                order.total_amount,
                order.voucher_code,
            ]
        )
    return response
