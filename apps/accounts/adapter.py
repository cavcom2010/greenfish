"""
Custom allauth adapter.
"""
from allauth.account.adapter import DefaultAccountAdapter

from apps.core.request_meta import client_ip_from_request


class DesktopAwareAccountAdapter(DefaultAccountAdapter):
    """Account adapter with proxy-aware client IP resolution."""

    def get_client_ip(self, request):
        """Return the client IP in socket/proxy deployments."""
        ip = client_ip_from_request(request)
        if ip:
            return ip
        return super().get_client_ip(request)
