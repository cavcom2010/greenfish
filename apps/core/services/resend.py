"""
Resend API integration for marketing emails.

Usage:
    from apps.core.services.resend import get_resend_service

    service = get_resend_service()
    if service:
        service.add_contact("user@example.com", "John Doe")
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ResendService:
    """
    Resend API client for marketing emails.

    This service handles high-volume, trackable marketing emails
    (offers, promotions, newsletters). Transactional emails continue
    to use Django's built-in SMTP system via Google Workspace.

    Docs: https://resend.com/docs/send-with-python
    """

    def __init__(self, api_key: str, from_email: str = "", from_name: str = ""):
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name

        import resend

        resend.api_key = api_key
        self._client = resend

    def send_campaign(
        self,
        recipients: list[dict],
        subject: str,
        html_content: str,
        from_email: str = "",
        from_name: str = "",
    ) -> dict:
        """
        Send a marketing email to multiple recipients.

        Args:
            recipients: List of dicts with 'email' and optionally 'name'.
            subject: Email subject line.
            html_content: HTML email body.
            from_email: Override default sender email.
            from_name: Override default sender name.

        Returns:
            Dict with 'success' (bool) and 'data' or 'error'.
        """
        sender = f"{from_name or self.from_name} <{from_email or self.from_email}>"
        to_addresses = [r.get("email", "") for r in recipients]

        try:
            params = {
                "from": sender,
                "to": to_addresses,
                "subject": subject,
                "html": html_content,
            }
            data = self._client.Emails.send(params)
            logger.info(
                "Resend campaign sent to %d recipients: %s",
                len(recipients),
                subject,
            )
            return {"success": True, "data": data}
        except Exception as exc:
            logger.error("Resend campaign send failed: %s", exc)
            return {"success": False, "error": str(exc)}

    def add_contact(
        self,
        email: str,
        name: str = "",
        audience_id: str = "",
    ) -> dict:
        """
        Add or update a contact in Resend audiences.

        Resend creates a contact via its API. Contacts are associated
        with an audience; if no audience_id is given, the default
        audience is used.

        Returns:
            Dict with 'success' (bool) and 'data' or 'error'.
        """
        try:
            params = {"email": email}
            if name:
                params["first_name"] = name.split(" ")[0] if " " in name else name
                params["last_name"] = name.split(" ", 1)[1] if " " in name else ""
            if audience_id:
                params["audience_id"] = audience_id

            contact = self._client.Contacts.create(params)
            logger.info("Added contact to Resend: %s", email)
            return {"success": True, "data": contact}
        except Exception as exc:
            logger.error("Resend add_contact failed for %s: %s", email, exc)
            return {"success": False, "error": str(exc)}

    def remove_contact(self, email: str) -> dict:
        """Remove a contact from Resend."""
        try:
            result = self._client.Contacts.remove(email=email)
            logger.info("Removed contact from Resend: %s", email)
            return {"success": True, "data": result}
        except Exception as exc:
            logger.error("Resend remove_contact failed for %s: %s", email, exc)
            return {"success": False, "error": str(exc)}

    def get_audiences(self) -> dict:
        """List all audiences in Resend."""
        try:
            audiences = self._client.Audiences.list()
            return {"success": True, "data": audiences}
        except Exception as exc:
            logger.error("Resend get_audiences failed: %s", exc)
            return {"success": False, "error": str(exc)}



_resend_service: Optional[ResendService] = None


def get_resend_service() -> Optional[ResendService]:
    """
    Get the Resend service instance.

    Returns None if the API key is not configured (e.g., in development).
    """
    global _resend_service

    if _resend_service is not None:
        return _resend_service

    from django.conf import settings

    api_key = getattr(settings, "RESEND_API_KEY", "")
    if not api_key:
        logger.info("Resend API key not configured — marketing emails will not be sent")
        return None

    _resend_service = ResendService(
        api_key=api_key,
        from_email=getattr(settings, "RESEND_FROM_EMAIL", ""),
        from_name=getattr(settings, "RESEND_FROM_NAME", ""),
    )
    return _resend_service
