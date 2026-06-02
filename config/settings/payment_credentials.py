"""Payment credential validation helpers used by settings and runtime code."""


PLACEHOLDER_VALUES = {"", "...", "changeme", "change-me", "none", "null"}


def _clean(value):
    return (value or "").strip()


def _looks_placeholder(value):
    cleaned = _clean(value)
    lowered = cleaned.lower()
    return (
        lowered in PLACEHOLDER_VALUES
        or "xxxx" in lowered
        or "your-" in lowered
        or "<" in cleaned
        or ">" in cleaned
    )


def valid_stripe_secret_key(value):
    cleaned = _clean(value)
    return cleaned.startswith(("sk_test_", "sk_live_")) and not _looks_placeholder(cleaned)


def valid_stripe_webhook_secret(value):
    cleaned = _clean(value)
    return cleaned.startswith("whsec_") and not _looks_placeholder(cleaned)


def stripe_credentials_configured(secret_key, webhook_secret):
    return valid_stripe_secret_key(secret_key) and valid_stripe_webhook_secret(webhook_secret)


def valid_mollie_api_key(value):
    cleaned = _clean(value)
    return cleaned.startswith(("test_", "live_")) and not _looks_placeholder(cleaned)


def valid_shared_secret(value):
    cleaned = _clean(value)
    return bool(cleaned) and not _looks_placeholder(cleaned)


def mollie_credentials_configured(api_key, webhook_secret):
    return valid_mollie_api_key(api_key) and valid_shared_secret(webhook_secret)
