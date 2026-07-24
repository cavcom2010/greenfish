"""
Operations-specific request hardening.
"""
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from .permissions import ROLE_MANAGER, get_operations_roles

# Paths a not-yet-enrolled manager may still reach: the MFA enrolment flow
# itself, sign-out, and static assets. Everything else redirects to enrolment.
_EXEMPT_PREFIXES = (
    "/accounts/2fa/",
    "/accounts/logout/",
    "/static/",
    "/media/",
    "/pwa/",
)


class OpsSecurityMiddleware:
    """Two per-request policies for staff accounts.

    1. Session cap — any account holding an operations role gets its session
       expiry clamped to OPS_SESSION_MAX_AGE (12h default) instead of the
       two-week customer default. Enforced per-request rather than at login so
       it is immune to allauth's own post-login session-expiry handling and
       also catches sessions that predate this policy.

    2. Manager MFA — managers can reach every staff surface, so a phished
       manager password is the worst-case credential. Until the manager has an
       MFA authenticator enrolled, every page redirects to the enrolment
       screen. Other roles are encouraged but not forced. Disable per
       deployment with OPS_MANAGER_MFA_REQUIRED=false.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return self.get_response(request)

        roles = get_operations_roles(user)
        if not roles:
            return self.get_response(request)

        max_age = getattr(settings, "OPS_SESSION_MAX_AGE", 12 * 60 * 60)
        if request.session.get_expiry_age() > max_age:
            request.session.set_expiry(max_age)

        if (
            getattr(settings, "OPS_MANAGER_MFA_REQUIRED", True)
            and ROLE_MANAGER in roles
            and not request.path.startswith(_EXEMPT_PREFIXES)
        ):
            from allauth.mfa.utils import is_mfa_enabled

            if not is_mfa_enabled(user):
                return redirect(reverse("mfa_index"))

        return self.get_response(request)
