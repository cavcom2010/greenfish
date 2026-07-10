"""
PWA views - Manifest, service worker, and push notifications.
"""
import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.core.models import SiteSettings
from apps.core.rate_limits import rate_limit

from .models import PushSubscription

logger = logging.getLogger(__name__)


@require_GET
def manifest(request):
    """Generate PWA manifest.json dynamically."""
    db_settings = SiteSettings.get()
    
    manifest_data = {
        "name": db_settings.shop_name,
        "short_name": db_settings.shop_name[:12] if len(db_settings.shop_name) > 12 else db_settings.shop_name,
        "start_url": "/accounts/app/",
        "display": "standalone",
        "background_color": "#FFFFFF",
        "theme_color": db_settings.theme_color,
        "orientation": "portrait",
        "scope": "/",
        "icons": [
            {
                "src": "/static/icons/icon-72.png",
                "sizes": "72x72",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-96.png",
                "sizes": "96x96",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-128.png",
                "sizes": "128x128",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-144.png",
                "sizes": "144x144",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-152.png",
                "sizes": "152x152",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-384.png",
                "sizes": "384x384",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-512.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ],
        "shortcuts": [
            {
                "name": "Order now",
                "short_name": "Order",
                "url": "/menu/",
                "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"}],
            },
            {
                "name": "Rewards Hub",
                "short_name": "Rewards",
                "url": "/rewards/",
                "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"}],
            },
            {
                "name": "Offers",
                "short_name": "Offers",
                "url": "/offers/",
                "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"}],
            },
            {
                "name": "Account",
                "short_name": "Account",
                "url": "/accounts/app/",
                "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"}],
            },
        ],
        "gcm_sender_id": "103953800507"
    }
    
    return JsonResponse(manifest_data)


@require_GET
def service_worker(request):
    """Serve the service worker file."""
    return render(request, "pwa/service-worker.js", content_type="application/javascript")


@require_GET
def offline(request):
    """Offline page."""
    return render(request, "pwa/offline.html")


@require_POST
@rate_limit("push-subscribe", limit=10, window_seconds=600)
def subscribe_push(request):
    """Save push notification subscription."""
    try:
        data = json.loads(request.body)
        
        subscription_data = data.get("subscription", {})
        endpoint = subscription_data.get("endpoint")
        keys = subscription_data.get("keys", {})
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")
        
        if not all([endpoint, p256dh, auth]):
            return JsonResponse({"error": "Invalid subscription data"}, status=400)
        
        # Check if subscription already exists
        existing = PushSubscription.objects.filter(endpoint=endpoint).first()
        if existing:
            # Update existing
            existing.p256dh = p256dh
            existing.auth = auth
            existing.is_active = True
            if request.user.is_authenticated:
                existing.user = request.user
            existing.save()
            return JsonResponse({"success": True, "message": "Subscription updated"})
        
        # Create new subscription
        PushSubscription.objects.create(
            user=request.user if request.user.is_authenticated else None,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            device_name=data.get("device_name", ""),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500]
        )
        
        return JsonResponse({"success": True, "message": "Subscribed to notifications"})
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception:
        logger.exception("Failed to subscribe push endpoint")
        return JsonResponse({"error": "Could not save subscription"}, status=500)


@require_POST
@rate_limit("push-unsubscribe", limit=10, window_seconds=600)
def unsubscribe_push(request):
    """Unsubscribe from push notifications."""
    try:
        data = json.loads(request.body)
        endpoint = data.get("endpoint")
        
        if endpoint:
            PushSubscription.objects.filter(endpoint=endpoint).update(is_active=False)
        
        return JsonResponse({"success": True, "message": "Unsubscribed"})
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception:
        logger.exception("Failed to unsubscribe push endpoint")
        return JsonResponse({"error": "Could not update subscription"}, status=500)


@require_GET
def push_status(request):
    """Check if user is subscribed to push notifications."""
    # This would check if the current endpoint is in our database
    # Client-side checks subscription in service worker
    return JsonResponse({"supported": True})
