# Systemd units for GreenFish

Version-controlled templates for the production services.

## Quick install (recommended)

On the server, from the repo checkout:

```bash
sudo bash deploy/production/systemd/install.sh
```

This templates the unit files to the real repo path/user, installs the
celery worker + beat units, and enables them. Add `--with-gunicorn` to also
install the gunicorn units, or `--dry-run` to preview.

## Manual install

Copy, adjust paths/users, then enable:

```bash
sudo cp deploy/production/systemd/*.socket deploy/production/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now greenfish-gunicorn.socket greenfish-gunicorn.service
sudo systemctl enable --now greenfish-celery.service greenfish-celerybeat.service
```

| Unit | Purpose |
|------|---------|
| `greenfish-gunicorn.socket` / `.service` | WSGI app server behind nginx |
| `greenfish-celery.service` | Async worker (notification outbox, cleanup) |
| `greenfish-celerybeat.service` | Scheduler for periodic jobs (see `config/celery.py`) |

Without `greenfish-celerybeat`, order confirmation emails/SMS are never
dispatched from the outbox and unpaid fallback orders are never expired.

## Cron alternative

If you prefer cron over celery beat, run these instead:

```cron
* * * * *  cd /home/deploy/greenfish && venv/bin/python manage.py dispatch_notifications >> logs/cron.log 2>&1
*/5 * * * * cd /home/deploy/greenfish && venv/bin/python manage.py expire_unpaid_orders >> logs/cron.log 2>&1
*/15 * * * * cd /home/deploy/greenfish && venv/bin/python manage.py process_customer_data_requests >> logs/cron.log 2>&1
15 4 * * *  cd /home/deploy/greenfish && venv/bin/python manage.py clearsessions >> logs/cron.log 2>&1
30 3 * * 1  cd /home/deploy/greenfish && venv/bin/python manage.py anonymise_old_order_personal_data >> logs/cron.log 2>&1
20 2 * * *  /home/deploy/greenfish/backup.sh >> logs/backup.log 2>&1
```
