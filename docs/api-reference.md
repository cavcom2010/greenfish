# API Reference

This document describes the available API endpoints and their usage.

## Base URL

- **Local**: `http://127.0.0.1:8006/`
- **Production**: `https://yourdomain.com/`

## Authentication

Most API endpoints use Django session authentication. Some endpoints are public.

For admin endpoints, login via `/admin/` first.

## Public Endpoints

### Menu

#### List Categories

```http
GET /menu/
```

Returns menu page with all categories and items.

**Response:** HTML page

#### Get Item Detail

```http
GET /menu/item/{id}/
```

Returns item details for modal display.

**Response:** HTML partial (if HTMX request) or JSON

**Example JSON Response:**
```json
{
  "id": 1,
  "name": "Fish & Chips",
  "description": "Fresh cod with crispy chips",
  "price": "8.99",
  "image": "/media/menu/items/fish_chips.jpg",
  "preparation_time": 15,
  "dietary_tags": ["gluten-free-option"],
  "modifiers": [
    {
      "id": 1,
      "name": "Extra Chips",
      "price": "1.50"
    }
  ]
}
```

### PWA

#### Manifest

```http
GET /pwa/manifest.json
```

Returns PWA manifest file.

**Response:** JSON

#### Service Worker

```http
GET /pwa/service-worker.js
```

Returns service worker JavaScript.

**Response:** JavaScript

### Offers

#### List Offers

```http
GET /offers/
```

Returns active offers page.

**Response:** HTML page

## Cart & Order Endpoints

### Cart Operations

#### Add to Cart

```http
POST /orders/cart/add/
Content-Type: application/x-www-form-urlencoded
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| menu_item_id | integer | Yes | ID of menu item |
| quantity | integer | No | Quantity (default: 1) |
| modifiers | JSON | No | Array of modifier objects |

**Example:**
```bash
curl -X POST http://127.0.0.1:8006/orders/cart/add/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "menu_item_id=1&quantity=2&modifiers=[{\"id\":1,\"name\":\"Extra Cheese\",\"price\":0.50}]"
```

**Response:**
```json
{
  "success": true,
  "cart_count": 3
}
```

#### Update Cart Item

```http
POST /orders/cart/update/{item_id}/
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| quantity | integer | Yes | New quantity |

#### Remove from Cart

```http
POST /orders/cart/remove/{item_id}/
```

#### View Cart

```http
GET /orders/cart/
```

**Response:** HTML page with cart contents

### Checkout

#### Checkout Page

```http
GET /orders/checkout/
```

**Response:** HTML checkout form

#### Apply Voucher

```http
POST /orders/checkout/voucher/
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| code | string | Yes | Voucher code |

### Order Management

#### Create Order (Payment)

```http
POST /payments/create/
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| customer_name | string | Yes | Customer full name |
| customer_phone | string | Yes | Phone number |
| customer_email | string | No | Email address |
| special_instructions | string | No | Order notes |

**Response:** Redirects to Stripe Checkout

#### Check Payment Status

```http
GET /payments/status/{order_number}/
```

**Response:**
```json
{
  "order_number": "TN-12345",
  "status": "confirmed",
  "payment_status": "paid",
  "paid": true
}
```

## Dashboard Endpoints (Staff Only)

### Order Board

#### View Order Board

```http
GET /orders/dashboard/
```

Requires staff login.

**Response:** HTML order board interface

#### Get Order List Fragment

```http
GET /orders/dashboard/orders/fragment/
```

Returns HTMX-updatable order list.

**Query Parameters:**
| Name | Type | Description |
|------|------|-------------|
| status | string | Filter by status (confirmed, preparing, ready) |

**Response:** HTML partial

#### Update Order Status

```http
POST /orders/dashboard/orders/{order_id}/update/
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| status | string | Yes | New status |

**Valid Status Values:**
- `confirmed`
- `preparing`
- `ready`
- `completed`
- `cancelled`

### Order Detail

```http
GET /orders/dashboard/orders/{order_id}/detail/
```

**Response:** HTML modal content

## Webhooks

### Stripe Webhook

```http
POST /payments/webhook/
```

**Description:** Receives payment status updates from Stripe

**Note:** This endpoint is called by Stripe servers, not by your application. The request is verified using the `Stripe-Signature` header.

**Response:** Always return 200 OK

## Authentication Endpoints (Django AllAuth)

### Login

```http
GET /accounts/login/
POST /accounts/login/
```

### Register

```http
GET /accounts/signup/
POST /accounts/signup/
```

### Logout

```http
POST /accounts/logout/
```

### Password Reset

```http
GET /accounts/password/reset/
POST /accounts/password/reset/
```

See [Django AllAuth documentation](https://django-allauth.readthedocs.io/) for complete authentication endpoints.

## Error Responses

### 400 Bad Request

```json
{
  "error": "Invalid request parameters"
}
```

### 403 Forbidden

```html
<!-- Login required page -->
```

### 404 Not Found

```json
{
  "error": "Item not found"
}
```

### 500 Internal Server Error

```json
{
  "error": "Internal server error"
}
```

## Rate Limiting

Currently no rate limiting is implemented. Consider adding for production use.

## CSRF Tokens

For POST requests from JavaScript, include CSRF token:

```javascript
// Get token from cookie
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Use in fetch
fetch('/orders/cart/add/', {
  method: 'POST',
  headers: {
    'X-CSRFToken': getCookie('csrftoken'),
    'Content-Type': 'application/x-www-form-urlencoded'
  },
  body: 'menu_item_id=1'
});
```

## HTMX Headers

When using HTMX, these headers are sent:

| Header | Description |
|--------|-------------|
| `HX-Request` | Set to "true" for HTMX requests |
| `HX-Trigger` | Element that triggered request |
| `HX-Target` | Target element for swap |

Server responds with partial HTML for HTMX requests.

## Testing API

### Using curl

```bash
# Add item to cart
curl -X POST http://127.0.0.1:8006/orders/cart/add/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "X-CSRFToken: YOUR_CSRF_TOKEN" \
  -b "csrftoken=YOUR_CSRF_TOKEN" \
  -d "menu_item_id=1&quantity=1"

# Check order status
curl http://127.0.0.1:8006/payments/status/TN-12345/
```

### Using Python requests

```python
import requests

session = requests.Session()

# Get CSRF token
response = session.get('http://127.0.0.1:8006/')
csrf_token = session.cookies['csrftoken']

# Add to cart
response = session.post(
    'http://127.0.0.1:8006/orders/cart/add/',
    data={'menu_item_id': 1, 'quantity': 1},
    headers={'X-CSRFToken': csrf_token}
)
print(response.json())
```
