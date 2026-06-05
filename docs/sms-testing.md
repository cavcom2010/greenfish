# SMS Testing Guide

Use this guide to test GreenFish SMS without wasting Twilio credit or texting real customers by accident.

The app supports three SMS backends:

| Backend | Sends real SMS? | Cost | Use case |
|---------|------------------|------|----------|
| `console` | No | Free | Local development and safe smoke tests |
| `twilio_test` | No | Free | Twilio API integration test with test credentials |
| `twilio` | Yes | Paid | One controlled live test and production |

## 1. Console SMS

Console SMS is the safest default. It creates an `SMSMessage` record and logs the message without calling Twilio.

In `.env`:

```bash
SMS_BACKEND=console
```

Run:

```bash
venv/bin/python manage.py send_test_sms +447700900123
```

Expected result:

- The command prints `Test SMS sent via console`.
- An `SMSMessage` row is created with status `sent`.
- `twilio_sid` is set to `console`.
- No real text is sent.

## 2. Twilio Test Credentials

Twilio test mode calls Twilio's API using test credentials and the magic successful sender number. It does not send a real SMS and should not charge credit.

In `.env`:

```bash
SMS_BACKEND=twilio_test
TWILIO_TEST_ACCOUNT_SID=your_twilio_test_sid
TWILIO_TEST_AUTH_TOKEN=your_twilio_test_token
TWILIO_TEST_PHONE_NUMBER=+15005550006
```

Run:

```bash
venv/bin/python manage.py send_test_sms +447700900123
```

Expected result:

- The command succeeds.
- An `SMSMessage` row is created with status `sent`.
- The returned Twilio SID is saved on the row.
- No real text is delivered.

## 3. Live Twilio Test

Live Twilio mode sends a real paid SMS. Use a shop-owned phone number only.

In `.env`:

```bash
SMS_BACKEND=twilio
TWILIO_ACCOUNT_SID=your_live_twilio_sid
TWILIO_AUTH_TOKEN=your_live_twilio_token
TWILIO_PHONE_NUMBER=+1234567890
```

The command is deliberately blocked unless you add `--live`:

```bash
venv/bin/python manage.py send_test_sms +447700900123
```

Expected result:

- The command refuses to send and tells you to use `--live`.

To send one real test:

```bash
venv/bin/python manage.py send_test_sms +447700900123 --live
```

Expected result:

- The phone receives the SMS.
- An `SMSMessage` row is created with status `sent`.
- Twilio deducts credit for the real message.

## 4. Order Notification Flow

Manual test commands prove the backend. Order-flow SMS also needs the admin switch enabled.

In Django admin:

1. Go to `SMS Notifications -> SMS Settings`.
2. Set `enabled=True`.
3. Keep `send_order_confirmed=True` and `send_order_ready=True`.
4. Enable `send_order_delivered` only if you want a completion SMS for delivery orders.

Then test the order flow:

1. Place an order with a valid customer phone number.
2. Confirm/pay the order as normal.
3. Update the order status on the operations board.
4. Run the dispatcher if it is not running automatically:

```bash
venv/bin/python manage.py dispatch_notifications
```

Expected result:

- Order confirmation creates an SMS notification event.
- Ready for pickup creates a ready SMS event.
- Out for delivery creates a dispatch SMS event.
- Delivered creates a delivered SMS event only when enabled.

## 5. Where To Check Results

In Django admin:

- `SMS Notifications -> SMS Messages`
- `Core -> Notification Events`

Useful fields:

- `SMSMessage.status`
- `SMSMessage.twilio_sid`
- `SMSMessage.error_message`
- `NotificationEvent.status`
- `NotificationEvent.last_error`
- `NotificationEvent.attempts`

## Troubleshooting

If console mode does not create an SMS row:

- Confirm `SMS_BACKEND=console`.
- Run `venv/bin/python manage.py check`.
- Confirm the command uses a non-empty phone number.

If Twilio test mode fails:

- Confirm `twilio` is installed from `requirements.txt`.
- Confirm `TWILIO_TEST_ACCOUNT_SID` and `TWILIO_TEST_AUTH_TOKEN` are set.
- Confirm `TWILIO_TEST_PHONE_NUMBER=+15005550006`.
- Restart Django after changing `.env`.

If live Twilio fails:

- Confirm `SMS_BACKEND=twilio`.
- Confirm live Twilio SID/token are correct.
- Confirm `TWILIO_PHONE_NUMBER` is an active Twilio sender.
- Confirm the destination number is in E.164 format, for example `+447700900123`.
- Check the SMS row's `error_message`.
