"""
Shared test helpers for app-level regression coverage.
"""
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import SiteSettings
from apps.mealdeals.models import MealDeal, MealDealItem, MealDealOption
from apps.menu.models import MenuCategory, MenuItem, MenuModifier
from apps.offers.models import Offer, VoucherCode
from apps.orders.models import Order, OrderItem


def ensure_site_settings(**overrides):
    settings = SiteSettings.get()
    defaults = {
        "shop_name": "Two Fish Kitchen",
        "address": "12 Test Street",
        "phone": "02000000000",
        "email": "hello@example.com",
        "theme_color": "#FF6B35",
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(settings, key, value)
    settings.save()
    return settings


def create_user(email="user@example.com", password="password123", **extra_fields):
    defaults = {
        "first_name": "Test",
        "last_name": "User",
        "phone_number": "07747055935",
    }
    defaults.update(extra_fields)
    return User.objects.create_user(email=email, password=password, **defaults)


def create_menu_item(name="Sadza Special", price=Decimal("12.50"), **overrides):
    category = overrides.pop(
        "category",
        MenuCategory.objects.create(name="Mains", sort_order=1, is_active=True, icon="🍲"),
    )
    defaults = {
        "description": "Freshly made",
        "is_available": True,
        "is_popular": True,
        "preparation_time": 15,
        "dietary_tags": ["halal"],
    }
    defaults.update(overrides)
    item = MenuItem.objects.create(
        category=category,
        name=name,
        price=price,
        **defaults,
    )
    modifier = MenuModifier.objects.create(name="Extra Sauce", price_adjustment=Decimal("1.50"))
    item.modifiers.add(modifier)
    return item


def create_offer(name="Weekend Deal", value=Decimal("10.00"), offer_type=Offer.OfferType.PERCENTAGE):
    now = timezone.now()
    return Offer.objects.create(
        name=name,
        description="Save on your next order",
        offer_type=offer_type,
        value=value,
        start_date=now - timezone.timedelta(days=1),
        end_date=now + timezone.timedelta(days=7),
        is_active=True,
        display_on_hero=True,
    )


def create_voucher(code="SAVE10", offer=None):
    now = timezone.now()
    offer = offer or create_offer()
    return VoucherCode.objects.create(
        code=code,
        offer=offer,
        valid_from=now - timezone.timedelta(days=1),
        valid_until=now + timezone.timedelta(days=7),
        is_active=True,
        max_uses=10,
        max_uses_per_customer=5,
    )


def create_meal_deal(menu_item=None):
    menu_item = menu_item or create_menu_item(name="Meal Deal Main", price=Decimal("8.00"))
    deal = MealDeal.objects.create(
        name="Family Feast",
        description="A complete meal deal",
        original_price=Decimal("22.00"),
        deal_price=Decimal("18.00"),
        is_active=True,
    )
    deal_item = MealDealItem.objects.create(
        deal=deal,
        name="Choose your main",
        min_quantity=1,
        max_quantity=1,
    )
    MealDealOption.objects.create(
        deal_item=deal_item,
        menu_item=menu_item,
        upgrade_price=Decimal("0.00"),
        is_available=True,
    )
    return deal


def create_order(user=None, status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PENDING, **overrides):
    item = create_menu_item()
    defaults = {
        "customer_name": "Order Customer",
        "customer_phone": "07747055935",
        "customer_email": "order@example.com",
        "user": user,
        "subtotal": Decimal("12.50"),
        "total_amount": Decimal("12.50"),
        "status": status,
        "payment_status": payment_status,
        "requested_pickup_time": timezone.now() + timezone.timedelta(minutes=15),
    }
    defaults.update(overrides)
    order = Order.objects.create(**defaults)
    OrderItem.objects.create(
        order=order,
        menu_item=item,
        item_name=item.name,
        item_price=item.price,
        quantity=1,
        modifiers=[],
    )
    return order
