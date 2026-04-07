"""
Analytics views - Business intelligence dashboards.
"""
from datetime import datetime, timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.menu.models import MenuItem
from apps.orders.models import Order


@staff_member_required
def dashboard(request):
    """Main analytics dashboard."""
    # Date range (default: last 30 days)
    days = int(request.GET.get('days', 30))
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    # Sales Overview
    orders = Order.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date
    )
    
    total_revenue = orders.aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    total_orders = orders.count()
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    
    # Order Status Breakdown
    status_counts = orders.values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Popular Items
    popular_items = MenuItem.objects.filter(
        order_items__order__created_at__gte=start_date
    ).annotate(
        order_count=Count('order_items'),
        total_revenue=Sum('order_items__item_price')
    ).order_by('-order_count')[:10]
    
    # Peak Hours (orders by hour)
    peak_hours = orders.extra(
        select={'hour': 'EXTRACT(hour FROM created_at)'}
    ).values('hour').annotate(
        count=Count('id')
    ).order_by('hour')
    
    # Sales by Day (last 7 days)
    last_7_days = timezone.now() - timedelta(days=7)
    daily_sales = []
    for i in range(7):
        day = last_7_days + timedelta(days=i)
        day_orders = Order.objects.filter(
            created_at__date=day.date()
        )
        daily_sales.append({
            'date': day.strftime('%a'),
            'revenue': day_orders.aggregate(
                total=Sum('total_amount')
            )['total'] or 0,
            'orders': day_orders.count()
        })
    
    # Payment Method Breakdown
    payment_methods = orders.values('payment_status').annotate(
        count=Count('id'),
        revenue=Sum('total_amount')
    ).order_by('-count')
    
    context = {
        'days': days,
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'avg_order_value': avg_order_value,
        'status_counts': list(status_counts),
        'popular_items': popular_items,
        'peak_hours': list(peak_hours),
        'daily_sales': daily_sales,
        'payment_methods': list(payment_methods),
    }
    return render(request, 'analytics/dashboard.html', context)


@staff_member_required
def sales_report(request):
    """Detailed sales report."""
    # Similar to dashboard but with more detail
    return dashboard(request)
