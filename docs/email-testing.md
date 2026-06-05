# Email Testing Guide

Use this guide to test GreenFish email safely before using a real provider.

## 1. Console Email

Console email is the safest default. It prints the full email to the Django server terminal and does not send anything to a real inbox.

In `.env`:

```bash
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=GreenFish <orders@greenfish.local>
```

Run:

```bash
venv/bin/python manage.py send_test_email you@example.com
```

Expected result:

- The command prints `Sent 1 test email(s) to you@example.com`.
- The email content appears in the terminal running Django or the command.
- No real email is delivered.

## 2. Mailpit Local Inbox

Mailpit gives you a real-looking local inbox UI. Emails are captured locally and are not sent to real recipients.

Start Mailpit:

```bash
docker run --rm -p 1025:1025 -p 8025:8025 axllent/mailpit
```

In `.env`:

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=127.0.0.1
EMAIL_PORT=1025
EMAIL_USE_TLS=False
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=GreenFish <orders@greenfish.local>
```

Send a test email:

```bash
venv/bin/python manage.py send_test_email you@example.com
```

Open:

```text
http://127.0.0.1:8025
```

Expected result:

- Mailpit shows the email in its inbox.
- You can inspect subject, plain text, HTML preview, and headers.
- No real email is delivered.

## 3. HTML Email Preview

Use the `--html` option to test rendered HTML:

```bash
venv/bin/python manage.py send_test_email you@example.com \
  --subject "GreenFish HTML preview" \
  --message "Plain text fallback" \
  --html "<h1>GreenFish</h1><p>Your test email works.</p>"
```

In Mailpit, check both:

- HTML preview
- Plain text fallback

## 4. Production SMTP Smoke Test

Only do this after your SMTP provider is configured.

Example `.env` for SMTP:

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=orders@example.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=GreenFish <orders@example.com>
```

Run:

```bash
venv/bin/python manage.py send_test_email your-real-address@example.com
```

Expected result:

- The command succeeds.
- The real inbox receives the email.
- SPF/DKIM/DMARC should be configured for the sending domain before relying on production email.

## 5. Notification Outbox Test

Email notification events are sent by the notification dispatcher.

Run pending notifications:

```bash
venv/bin/python manage.py dispatch_notifications
```

Expected result:

- Pending email notification events move to `sent`.
- Failed sends remain retryable until their max attempts are reached.

## Troubleshooting

If Mailpit shows nothing:

- Confirm Mailpit is running.
- Confirm `.env` has `EMAIL_HOST=127.0.0.1` and `EMAIL_PORT=1025`.
- Restart Django after changing `.env`.
- Run `venv/bin/python manage.py check`.

If production SMTP fails:

- Check username/password or app password.
- Check the SMTP port and TLS setting.
- Confirm the provider allows SMTP access.
- Check spam/quarantine folders.
- Confirm `DEFAULT_FROM_EMAIL` uses a verified sender/domain.
