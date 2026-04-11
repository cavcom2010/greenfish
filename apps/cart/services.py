"""
Cart services - Shopping cart business logic.

This module contains cart operations that work with the session.
No database models needed - cart is session-based.
"""
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation


class CartService:
    """
    Session-based shopping cart service.
    
    This service manages cart operations without database models.
    Cart data is stored in the user's session.
    """
    
    CART_SESSION_KEY = 'cart'
    
    def __init__(self, request):
        """Initialize cart service with request object."""
        self.request = request
        self.session = request.session
        self.cart = self.session.get(self.CART_SESSION_KEY, {})
    
    def add_item(self, item_id, name, price, quantity=1, options=None, image_url=None):
        """
        Add an item to the cart.
        
        Args:
            item_id: Product/item ID
            name: Item name
            price: Item price
            quantity: Quantity to add
            options: List of option dicts [{'name': 'Extra Cheese', 'price': 0.50}]
            image_url: URL to item image
        """
        # Generate unique cart item ID if not exists
        cart_key = self._build_cart_key(item_id, options or [])

        if cart_key not in self.cart:
            self.cart[cart_key] = {
                'cart_id': str(uuid.uuid4())[:8],
                'item_id': item_id,
                'menu_item_id': item_id,
                'name': name,
                'price': str(price),
                'quantity': 0,
                'options': self._normalize_options(options or []),
                'modifiers': self._normalize_options(options or []),
                'image_url': image_url,
            }

        self.cart[cart_key]['quantity'] += max(1, int(quantity))
        self.save()
    
    def update_quantity(self, item_id, quantity):
        """Update item quantity."""
        if item_id in self.cart:
            if quantity > 0:
                self.cart[item_id]['quantity'] = quantity
            else:
                del self.cart[item_id]
            self.save()
    
    def remove_item(self, item_id):
        """Remove item from cart."""
        if item_id in self.cart:
            del self.cart[item_id]
            self.save()
    
    def clear(self):
        """Clear entire cart."""
        self.cart = {}
        self.save()
    
    def get_items(self):
        """Get all cart items as list."""
        items = []
        for key, item_data in self.cart.items():
            try:
                price = Decimal(str(item_data.get('price', 0)))
                quantity = int(item_data.get('quantity', 1))
                options = self._normalize_options(
                    item_data.get('modifiers', item_data.get('options', []))
                )
                options_total = sum(
                    Decimal(str(opt.get('price', 0))) for opt in options
                )

                items.append({
                    'id': key,
                    'cart_id': item_data.get('cart_id'),
                    'item_id': item_data.get('item_id') or item_data.get('menu_item_id'),
                    'menu_item_id': item_data.get('menu_item_id') or item_data.get('item_id'),
                    'name': item_data.get('name'),
                    'quantity': quantity,
                    'price': price,
                    'options': options,
                    'modifiers': options,
                    'options_total': options_total,
                    'modifiers_total': options_total,
                    'line_total': (price + options_total) * quantity,
                    'image_url': item_data.get('image_url'),
                })
            except (ValueError, TypeError, InvalidOperation):
                continue
        return items
    
    def get_total(self):
        """Calculate cart total."""
        total = Decimal('0.00')
        for item in self.get_items():
            total += item['line_total']
        return total
    
    def get_count(self):
        """Get total item count."""
        count = 0
        for item in self.cart.values():
            try:
                quantity = int(item.get('quantity', 1))
            except (TypeError, ValueError):
                continue
            if quantity > 0:
                count += quantity
        return count
    
    def save(self):
        """Save cart to session."""
        self.session[self.CART_SESSION_KEY] = self.cart
        self.session.modified = True

    def _normalize_options(self, options):
        """Return a cleaned list of options/modifiers."""
        cleaned = []
        if not isinstance(options, list):
            return cleaned

        for option in options:
            if not isinstance(option, dict):
                continue
            try:
                price = Decimal(str(option.get('price', 0))).quantize(Decimal('0.01'))
            except (InvalidOperation, TypeError, ValueError):
                price = Decimal('0.00')

            name = str(option.get('name', '')).strip()
            if not name:
                continue

            cleaned.append({
                'id': option.get('id'),
                'name': name,
                'price': str(max(price, Decimal('0.00'))),
            })

        return cleaned

    def _build_cart_key(self, item_id, options):
        """Create a stable key for an item and its selected options."""
        payload = json.dumps(self._normalize_options(options), sort_keys=True)
        digest = hashlib.md5(payload.encode('utf-8'), usedforsecurity=False).hexdigest()[:10]
        return f'{item_id}_{digest}'
    
    def __iter__(self):
        """Allow iteration over cart items."""
        return iter(self.get_items())
    
    def __len__(self):
        """Return item count."""
        return self.get_count()
