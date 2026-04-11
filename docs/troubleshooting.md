# Troubleshooting Guide

Common issues and their solutions.

## Installation Issues

### pip install fails

**Problem:** Package installation errors

**Solutions:**
```bash
# Upgrade pip
pip install --upgrade pip

# Install system dependencies (Ubuntu/Debian)
sudo apt-get install python3-dev libpq-dev

# Try installing with --no-cache-dir
pip install --no-cache-dir -r requirements.txt
```

### Database connection fails

**Problem:** Cannot connect to PostgreSQL

**Solutions:**
1. Check PostgreSQL is running:
   ```bash
   sudo systemctl status postgresql
   ```

2. Verify database and user exist:
   ```bash
   sudo -u postgres psql -l
   ```

3. Check DATABASE_URL format:
   ```
   postgres://user:password@localhost:5432/dbname
   ```

4. For local development, leave DATABASE_URL empty to use SQLite

### Static files not found

**Problem:** 404 errors for CSS/JS files

**Solution:**
```bash
python manage.py collectstatic --noinput --settings=config.settings.local
```

Check `STATIC_ROOT` is set in settings and directory exists.

## Runtime Issues

### Server won't start

**Problem:** Port already in use

**Solutions:**
```bash
# Find process using port 8026
sudo lsof -i :8026

# Kill the process
sudo kill -9 <PID>

# Or use different port
export HOME_APP_PORT=9000
./deploy/home/start.sh
```

**Problem:** Permission denied

**Solution:**
```bash
# Fix permissions
chmod +x deploy/home/*.sh
chown -R $USER:$USER .
```

### 500 Internal Server Error

**Problem:** Application error

**Check logs:**
```bash
# Gunicorn logs
tail -f .home_nginx/logs/gunicorn-error.log

# Django logs
tail -f .home_nginx/logs/error.log
```

**Common causes:**
1. Missing environment variables
2. Database not migrated
3. Missing static files

**Solutions:**
```bash
# Check settings
python manage.py check --settings=config.settings.local

# Run migrations
python manage.py migrate --settings=config.settings.local

# Collect static
python manage.py collectstatic --noinput --settings=config.settings.local
```

### CSRF verification failed

**Problem:** Form submissions fail with CSRF error

**Solutions:**
1. Check CSRF_TRUSTED_ORIGINS includes your domain:
   ```bash
   DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com
   ```

2. For local development, ensure DEBUG=True

3. Clear browser cookies and cache

## Payment Issues

### Stripe payment fails

**Problem:** Payment creation fails

**Solutions:**
1. Verify `PAYMENT_PROVIDER=stripe` and `STRIPE_SECRET_KEY` are set:
   ```bash
   echo $PAYMENT_PROVIDER
   echo $STRIPE_SECRET_KEY
   ```

2. Check the Stripe dashboard API key and webhook endpoint status

3. Verify the webhook URL is accessible:
   ```bash
   curl -X POST https://yourdomain.com/payments/webhook/
   # Should return 400 or 403 without a Stripe signature, but the route must be reachable
   ```

4. Check `STRIPE_WEBHOOK_SECRET` matches the signing secret from the Stripe dashboard

### Webhook not receiving updates

**Problem:** Payment status not updating

**Solutions:**
1. Ensure webhook URL is publicly accessible
2. Check SSL certificate is valid
3. Verify `STRIPE_WEBHOOK_SECRET` in `.env` matches the Stripe webhook endpoint signing secret
4. Check logs for webhook errors:
   ```bash
   tail -f .home_nginx/logs/gunicorn-error.log | grep webhook
   ```

### Stripe live payments don't work

**Problem:** Live API key issues

**Solutions:**
1. Verify using an `sk_live_...` key, not a test key
2. Confirm the Stripe account is activated for live payments
3. Confirm the live webhook endpoint is configured for `/payments/webhook/`

## Email Issues

### Emails not sending

**Problem:** No emails received

**Solutions:**
1. Check EMAIL_BACKEND setting:
   ```bash
   # For testing (console output)
   EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
   
   # For production
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   ```

2. Verify SMTP credentials

3. For Gmail, use App Password (not regular password)

4. Check spam/junk folders

## Database Issues

### Migration errors

**Problem:** Migration fails

**Solutions:**
```bash
# Check for conflicts
python manage.py makemigrations --check --dry-run

# Reset migrations (WARNING: data loss)
# Only for development!
rm -f db.sqlite3
python manage.py migrate --settings=config.settings.local
```

### Data appears lost

**Problem:** Data not showing up

**Solutions:**
1. Check correct database is connected
2. Verify data exists:
   ```bash
   python manage.py shell --settings=config.settings.local
   >>> from apps.menu.models import MenuItem
   >>> MenuItem.objects.count()
   ```

3. Check database permissions

## Performance Issues

### Slow page loads

**Solutions:**
1. Enable DEBUG=False in production
2. Use PostgreSQL (not SQLite) for production
3. Enable caching:
   ```python
   # settings/production.py
   CACHES = {
       'default': {
           'BACKEND': 'django.core.cache.backends.redis.RedisCache',
           'LOCATION': 'redis://127.0.0.1:6379/1',
       }
   }
   ```

4. Use CDN for static/media files

### High memory usage

**Solutions:**
1. Reduce Gunicorn workers:
   ```bash
   export HOME_GUNICORN_WORKERS=2
   ```

2. Enable connection pooling

3. Restart services periodically

## Deployment Issues

### Nginx 502 Bad Gateway

**Problem:** Nginx can't connect to Gunicorn

**Solutions:**
```bash
# Check Gunicorn is running
sudo systemctl status tinashe

# Check socket file exists
ls -la /home/tinashe/tinashe-takeaway/app.sock

# Fix permissions
sudo chown tinashe:www-data /home/tinashe/tinashe-takeaway/app.sock

# Check Nginx error log
sudo tail -f /var/log/nginx/error.log
```

### SSL Certificate issues

**Problem:** HTTPS not working

**Solutions:**
```bash
# Test Nginx config
sudo nginx -t

# Renew certificates
sudo certbot renew --dry-run

# Check certificate status
sudo certbot certificates
```

### Static files 404 in production

**Problem:** Static files not served

**Solutions:**
```bash
# Collect static
python manage.py collectstatic --noinput

# Check Nginx config has static location
location /static/ {
    root /home/tinashe/tinashe-takeaway;
}

# Verify files exist
ls -la /home/tinashe/tinashe-takeaway/staticfiles/
```

## PWA Issues

### Can't install PWA

**Problem:** "Add to Home Screen" not appearing

**Solutions:**
1. Check manifest.json is valid:
   ```bash
   curl https://yourdomain.com/pwa/manifest.json
   ```

2. Verify service worker loads:
   ```bash
   curl https://yourdomain.com/pwa/service-worker.js
   ```

3. Check HTTPS is enabled (required for PWA)

4. Use Chrome DevTools → Application → Manifest to debug

### Offline mode not working

**Problem:** App doesn't work offline

**Solutions:**
1. Check service worker is registered:
   - Open DevTools → Application → Service Workers
   - Should show service worker active

2. Verify cache is populated:
   - Check Cache Storage in DevTools

3. Test in Incognito mode (clears old service workers)

## Order Board Issues

### Orders not appearing

**Problem:** New orders don't show on board

**Solutions:**
1. Check staff is logged in
2. Verify HTMX is loading (check DevTools console)
3. Check for JavaScript errors
4. Manually refresh: `location.reload()`

### Sound notifications not working

**Problem:** No audio alert for new orders

**Solutions:**
1. Check sound is enabled (toggle button)
2. Browser might block autoplay - click page first
3. Check volume settings
4. Try different browser

## Common Error Messages

### "Module not found"

```bash
# Reinstall dependencies
pip install -r requirements.txt
```

### "No module named 'config'"

```bash
# Ensure you're in project root
cd /home/cmazh/django/two_fish
python manage.py check
```

### "Migration xxx is applied before its dependency"

```bash
# Check migration order
python manage.py showmigrations

# If development, reset:
rm -f db.sqlite3
python manage.py migrate
```

### "Permission denied" on media uploads

```bash
# Fix media directory permissions
chmod 755 media/
chown -R www-data:www-data media/
```

## Getting More Help

### Enable Debug Logging

Add to `.env`:
```bash
DJANGO_DEBUG=True
```

### Check All Logs

```bash
# Application logs
tail -f .home_nginx/logs/gunicorn-error.log

# Nginx logs
tail -f .home_nginx/logs/error.log
tail -f .home_nginx/logs/access.log

# System logs (production)
sudo journalctl -u tinashe -f
```

### Django Shell Debugging

```bash
python manage.py shell --settings=config.settings.local

# Test database connection
from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT 1")

# Check settings
from django.conf import settings
print(settings.DATABASES)
print(settings.ALLOWED_HOSTS)
```

## Still Having Issues?

1. Check all environment variables are set
2. Verify database is running and accessible
3. Check all services are running (Gunicorn, Nginx)
4. Review complete logs for error traces
5. Try restarting all services

**Restart Everything:**
```bash
./deploy/home/stop.sh
./deploy/home/start.sh
```
