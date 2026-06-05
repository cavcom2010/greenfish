"""
Custom allauth adapter — routes auth pages to desktop templates on desktop.
"""
from django.template import loader

from allauth.account.adapter import DefaultAccountAdapter

from apps.core.request_meta import client_ip_from_request


class DesktopAwareAccountAdapter(DefaultAccountAdapter):
    """Render desktop auth templates when request.is_desktop is True."""

    def get_client_ip(self, request):
        """Return the client IP in socket/proxy deployments."""
        ip = client_ip_from_request(request)
        if ip:
            return ip
        return super().get_client_ip(request)

    def render_template(self, request, template_name, context):
        """Override to swap in desktop templates."""
        if getattr(request, 'is_desktop', True):
            desktop_map = {
                'account/login.html': 'desktop/account/login.html',
                'account/signup.html': 'desktop/account/signup.html',
                'account/password_reset.html': 'desktop/account/password_reset.html',
                'account/password_reset_done.html': 'desktop/account/password_reset_done.html',
                'account/password_reset_from_key.html': 'desktop/account/password_reset_from_key.html',
                'account/password_reset_from_key_done.html': 'desktop/account/password_reset_from_key_done.html',
                'account/logout.html': 'desktop/account/logout.html',
                'account/email_confirm.html': 'desktop/account/email_confirm.html',
                'account/verification_sent.html': 'desktop/account/verification_sent.html',
            }
            template_name = desktop_map.get(template_name, template_name)
        template = loader.get_template(template_name)
        return template.render(context, request)
