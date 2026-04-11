"""
Sender.net API integration for marketing emails.

Usage:
    from apps.core.services.sender_net import sender_service

    # Send a marketing campaign
    sender_service.send_campaign(
        recipients=[{"email": "user@example.com", "name": "John"}],
        subject="Special Offer!",
        html_content="<p>20% off this weekend!</p>",
    )

    # Add a contact to your Sender.net audience
    sender_service.add_contact("user@example.com", "John Doe")
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class SenderNetResponse:
    """Wrapper for Sender.net API responses."""
    success: bool
    status_code: int
    data: Optional[dict] = None
    error: Optional[str] = None


class SenderNetService:
    """
    Sender.net API client for marketing emails.

    This service is designed for high-volume, trackable marketing emails
    (offers, promotions, newsletters). Transactional emails should continue
    to use Django's built-in email system via Google Workspace SMTP.

    API Reference: https://sender.net/developers/api
    """

    BASE_URL = "https://api.sender.net/api/v3"

    def __init__(self, api_key: str, from_email: str = "", from_name: str = ""):
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, endpoint: str, json: dict = None) -> SenderNetResponse:
        """Make an authenticated request to the Sender.net API."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers,
                json=json,
                timeout=30,
            )
            response.raise_for_status()
            return SenderNetResponse(
                success=True,
                status_code=response.status_code,
                data=response.json(),
            )
        except requests.exceptions.HTTPError as exc:
            error_msg = f"Sender.net HTTP error {exc.response.status_code}: {exc.response.text}"
            logger.error(error_msg)
            return SenderNetResponse(
                success=False,
                status_code=exc.response.status_code,
                error=error_msg,
            )
        except requests.exceptions.RequestException as exc:
            error_msg = f"Sender.net request failed: {exc}"
            logger.error(error_msg)
            return SenderNetResponse(
                success=False,
                status_code=0,
                error=error_msg,
            )

    def send_campaign(
        self,
        recipients: list[dict],
        subject: str,
        html_content: str,
        from_email: str = "",
        from_name: str = "",
    ) -> SenderNetResponse:
        """
        Send a marketing campaign to a list of recipients.

        Args:
            recipients: List of dicts with 'email' and optionally 'name'.
            subject: Email subject line.
            html_content: HTML email body.
            from_email: Override default sender email.
            from_name: Override default sender name.

        Returns:
            SenderNetResponse with campaign ID or error details.
        """
        payload = {
            "recipients": recipients,
            "subject": subject,
            "html_content": html_content,
            "from_email": from_email or self.from_email,
            "from_name": from_name or self.from_name,
        }

        logger.info(
            "Sending Sender.net campaign to %d recipients: %s",
            len(recipients),
            subject,
        )
        return self._request("POST", "campaigns/send", json=payload)

    def send_transactional(
        self,
        to: str,
        subject: str,
        html_content: str,
        from_email: str = "",
        from_name: str = "",
    ) -> SenderNetResponse:
        """
        Send a single transactional-style email via Sender.net.

        Use this when you want Sender.net tracking (opens, clicks) on
        individual emails like order confirmations.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            html_content: HTML email body.
            from_email: Override default sender email.
            from_name: Override default sender name.

        Returns:
            SenderNetResponse with send status or error details.
        """
        payload = {
            "to": to,
            "subject": subject,
            "html_content": html_content,
            "from_email": from_email or self.from_email,
            "from_name": from_name or self.from_name,
        }

        logger.info("Sending Sender.net transactional email to %s: %s", to, subject)
        return self._request("POST", "transactional/send", json=payload)

    def add_contact(
        self,
        email: str,
        name: str = "",
        fields: dict = None,
        audience_id: str = "",
    ) -> SenderNetResponse:
        """
        Add or update a contact in Sender.net.

        Args:
            email: Contact email address.
            name: Contact display name.
            fields: Custom fields (e.g., {"phone": "+44123456789"}).
            audience_id: Target audience/list ID (uses default if empty).

        Returns:
            SenderNetResponse with contact details or error.
        """
        payload = {
            "email": email,
            "name": name,
            "fields": fields or {},
        }
        if audience_id:
            payload["audience_id"] = audience_id

        logger.info("Adding contact to Sender.net: %s", email)
        return self._request("POST", "contacts", json=payload)

    def remove_contact(self, email: str) -> SenderNetResponse:
        """Remove a contact from Sender.net."""
        logger.info("Removing contact from Sender.net: %s", email)
        return self._request("DELETE", f"contacts/{email}")

    def get_contact(self, email: str) -> SenderNetResponse:
        """Get contact details from Sender.net."""
        return self._request("GET", f"contacts/{email}")

    def get_audiences(self) -> SenderNetResponse:
        """List all audiences/lists in Sender.net."""
        return self._request("GET", "audiences")


# Singleton instance — lazy-initialised from Django settings
_sender_service: Optional[SenderNetService] = None


def get_sender_service() -> Optional[SenderNetService]:
    """
    Get the Sender.net service instance.

    Returns None if the API key is not configured (e.g., in development).
    """
    global _sender_service

    if _sender_service is not None:
        return _sender_service

    from django.conf import settings

    api_key = getattr(settings, "SENDER_NET_API_KEY", "")
    if not api_key:
        logger.warning("Sender.net API key not configured — marketing emails will not be sent")
        return None

    _sender_service = SenderNetService(
        api_key=api_key,
        from_email=getattr(settings, "SENDER_NET_FROM_EMAIL", ""),
        from_name=getattr(settings, "SENDER_NET_FROM_NAME", ""),
    )
    return _sender_service


# Convenience alias for direct imports
sender_service = None  # Will be set at import time if settings are available
