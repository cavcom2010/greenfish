"""
Analytics views - Business intelligence dashboards.
"""
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour
from django.shortcuts import render
from django.utils import timezone

from apps.menu.models import MenuItem
from apps.orders.models import Order

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

    total_revenue = orders.aggregate(total=Sum("total_amount"))["total"] or 0
    total_orders = orders.count()
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    daily_average = total_revenue / days if days > 0 else 0

    status_counts = orders.values("status").annotate(count=Count("id")).order_by("-count")

    popular_items = (
        MenuItem.objects.filter(order_items__order__created_at__gte=start_date)
        .annotate(
            order_count=Count("order_items"),
            total_revenue=Sum("order_items__item_price"),
        )
        .order_by("-order_count")[:10]
    )

    peak_hours = (
        orders.annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("hour")
    )

    last_7_days = timezone.now() - timedelta(days=7)
    daily_sales = []
    max_daily_revenue = 0
    for offset in range(7):
        day = last_7_days + timedelta(days=offset)
        day_orders = Order.objects.filter(created_at__date=day.date())
        day_revenue = day_orders.aggregate(total=Sum("total_amount"))["total"] or 0
        max_daily_revenue = max(max_daily_revenue, day_revenue)
        daily_sales.append(
            {
                "date": day.strftime("%a"),
                "revenue": day_revenue,
                "orders": day_orders.count(),
            }
        )

    for day in daily_sales:
        if max_daily_revenue:
            day["bar_percent"] = max(4, int((day["revenue"] / max_daily_revenue) * 100))
        else:
            day["bar_percent"] = 4

    payment_methods = (
        orders.values("payment_status")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("-count")
    )

    context = {
        "days": days,
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "avg_order_value": avg_order_value,
        "daily_average": daily_average,
        "status_counts": list(status_counts),
        "popular_items": popular_items,
        "peak_hours": list(peak_hours),
        "daily_sales": daily_sales,
        "payment_methods": list(payment_methods),
    }
    return render(request, "analytics/dashboard.html", context)


@staff_member_required
def sales_report(request):
    """Detailed sales report."""
    return dashboard(request)
