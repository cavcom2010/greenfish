"""Shared helpers for customer-facing order access."""
from urllib.parse import urlencode

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse

from .models import Order

ORDER_ACCESS_TOKEN_PARAM = "t"


def user_can_access_order(user, order):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False):
        return True
    return bool(order.user_id and order.user_id == user.id)


def request_has_order_token(request, order):
    supplied_token = request.GET.get(ORDER_ACCESS_TOKEN_PARAM, "")
    return bool(supplied_token and supplied_token == order.public_access_token)


def request_can_access_order(request, order):
    return user_can_access_order(request.user, order) or request_has_order_token(request, order)


def get_accessible_order_or_404(request, order_number, queryset=None):
    queryset = queryset or Order.objects.all()
    order = get_object_or_404(queryset, order_number=order_number)
    if not request_can_access_order(request, order):
        raise Http404("Order not found")
    return order


def order_access_query(order, extra=None):
    query = {ORDER_ACCESS_TOKEN_PARAM: order.public_access_token}
    if extra:
        query.update(extra)
    return urlencode(query)


def order_customer_url(route_name, order, *, extra=None):
    return f"{reverse(route_name, args=[order.order_number])}?{order_access_query(order, extra=extra)}"


def absolute_order_customer_url(request, route_name, order, *, extra=None):
    return request.build_absolute_uri(order_customer_url(route_name, order, extra=extra))
