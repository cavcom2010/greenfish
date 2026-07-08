import json
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

META_API_VERSION = "v22.0"
META_MESSAGES_URL = (
    "https://graph.facebook.com/{version}/{phone_number_id}/messages"
)
DEFAULT_TIMEOUT = 10


class WhatsAppError(Exception):
    pass


class WhatsAppClient:
    def __init__(
        self,
        phone_number_id=None,
        cloud_api_token=None,
        *,
        api_version=META_API_VERSION,
        default_from=None,
    ):
        self.phone_number_id = phone_number_id
        self.cloud_api_token = cloud_api_token
        self.api_version = api_version
        self.default_from = default_from or phone_number_id

    def _from_django_settings(self):
        from django.conf import settings

        if not self.phone_number_id:
            self.phone_number_id = getattr(
                settings, "WHATSAPP_PHONE_NUMBER_ID", ""
            )
        if not self.cloud_api_token:
            self.cloud_api_token = getattr(
                settings, "WHATSAPP_CLOUD_API_TOKEN", ""
            )
        if not self.default_from:
            self.default_from = self.phone_number_id

    @property
    def is_configured(self):
        if not self.phone_number_id or not self.cloud_api_token:
            self._from_django_settings()
        return bool(self.phone_number_id and self.cloud_api_token)

    def _build_url(self):
        phone_number_id = self.phone_number_id or self.default_from
        return META_MESSAGES_URL.format(
            version=self.api_version,
            phone_number_id=phone_number_id,
        )

    def _send(self, *, to, payload_type, payload_data, timeout=DEFAULT_TIMEOUT):
        if not self.is_configured:
            raise WhatsAppError(
                "WhatsAppClient not configured: "
                "set WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_CLOUD_API_TOKEN"
            )

        body = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": payload_type,
            payload_type: payload_data,
        }

        try:
            req = Request(
                self._build_url(),
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.cloud_api_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            response = urlopen(req, timeout=timeout)
            response_data = json.loads(response.read().decode("utf-8"))

            if "error" in response_data:
                error_info = response_data["error"]
                raise WhatsAppError(
                    f"{error_info.get('message', 'unknown')} "
                    f"(code {error_info.get('code', 'unknown')})"
                )

            message_id = None
            if response_data.get("messages"):
                message_id = response_data["messages"][0].get("id")

            logger.info(
                "WhatsApp %s sent to %s (wa_id=%s)",
                payload_type,
                to,
                message_id or "unknown",
            )
            return {"success": True, "message_id": message_id}

        except URLError as exc:
            raise WhatsAppError(f"HTTP error sending WhatsApp: {exc}") from exc

    def send_text(self, to, body, *, timeout=DEFAULT_TIMEOUT):
        return self._send(
            to=to,
            payload_type="text",
            payload_data={"body": body},
            timeout=timeout,
        )

    def send_template(
        self,
        to,
        template_name,
        *,
        language_code="en",
        header_params=None,
        body_params=None,
        timeout=DEFAULT_TIMEOUT,
    ):
        template_data = {
            "name": template_name,
            "language": {"code": language_code},
        }

        components = []
        if header_params:
            components.append({
                "type": "header",
                "parameters": [
                    {"type": "text", "text": p} for p in header_params
                ],
            })
        if body_params:
            components.append({
                "type": "body",
                "parameters": [
                    {"type": "text", "text": p} for p in body_params
                ],
            })
        if components:
            template_data["components"] = components

        return self._send(
            to=to,
            payload_type="template",
            payload_data=template_data,
            timeout=timeout,
        )
