# Pre-Deployment Checklist

Use this checklist before deploying to production.

## Security

- [ ] Changed Django SECRET_KEY to a secure random string
- [ ] Set DEBUG=False in production
- [ ] Configured ALLOWED_HOSTS with domain name
- [ ] Added HTTPS to CSRF_TRUSTED_ORIGINS
- [ ] Enabled SSL redirect (SECURE_SSL_REDIRECT=True)
- [ ] Enabled secure cookies (SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE)
- [ ] Enabled HSTS headers
- [ ] Removed default admin credentials, created strong password
- [ ] Changed default superuser email/password
- [ ] Server firewall configured (UFW)
- [ ] SSH key authentication only (disabled password login)

## Database

- [ ] Using PostgreSQL (not SQLite)
- [ ] Database user has strong password
- [ ] Database backups configured
- [ ] Database migrations applied
- [ ] Connection pooling enabled (optional)

## Payments

- [ ] Using Mollie LIVE API key (not test)
- [ ] Mollie account fully verified
- [ ] Website profile complete in Mollie dashboard
- [ ] Webhook URL configured in Mollie
- [ ] Webhook secret set and matches
- [ ] Tested payment flow end-to-end
- [ ] Tested webhook reception

## Email

- [ ] SMTP server configured
- [ ] Email credentials working
- [ ] Test email sent successfully
- [ ] DEFAULT_FROM_EMAIL set correctly
- [ ] SPF/DKIM records configured (if using custom domain)

## Static & Media Files

- [ ] Collected static files (`collectstatic`)
- [ ] Static files served via Nginx (not Django)
- [ ] Media directory created with correct permissions
- [ ] Media uploads working
- [ ] CDN configured (optional but recommended)

## Domain & SSL

- [ ] Domain DNS pointing to server IP
- [ ] SSL certificate installed (Let's Encrypt)
- [ ] HTTPS redirect working
- [ ] www redirect configured (if using www)
- [ ] SSL auto-renewal tested

## Application

- [ ] Site Settings configured (name, address, phone)
- [ ] Menu items added with images
- [ ] Categories created and ordered
- [ ] Modifiers created and linked
- [ ] Opening hours configured
- [ ] At least one staff account created
- [ ] Order board accessible to staff

## Performance

- [ ] Gunicorn workers configured (typically 2-4)
- [ ] Nginx gzip compression enabled
- [ ] Static files cached (browser cache headers)
- [ ] Database queries optimized (check for N+1)
- [ ] Error monitoring enabled (e.g., Sentry)

## Monitoring

- [ ] Server monitoring configured (e.g., DigitalOcean monitoring)
- [ ] Log rotation configured
- [ ] Disk space monitoring
- [ ] SSL expiry monitoring
- [ ] Uptime monitoring (e.g., UptimeRobot)

## Testing

- [ ] Place test order successfully
- [ ] Payment processed correctly
- [ ] Order appears on order board
- [ ] Order status updates work
- [ ] Email notifications received
- [ ] Admin panel accessible
- [ ] Mobile responsive test passed
- [ ] PWA install test passed

## Documentation

- [ ] Staff trained on order board
- [ ] Staff know how to update menu
- [ ] Staff know how to process refunds
- [ ] Contact information documented
- [ ] Emergency procedures documented

## Final Checks

- [ ] `.env` file permissions set (readable only by app user)
- [ ] Debug mode off: `DJANGO_DEBUG=False`
- [ ] All sensitive data removed from code
- [ ] Git repository has no secrets committed
- [ ] Server timezone correct
- [ ] Server time synchronized (NTP)

## Post-Deployment

- [ ] Test order from customer perspective
- [ ] Verify order notification received
- [ ] Confirm staff can access order board
- [ ] Test mobile experience
- [ ] Verify PWA install works
- [ ] Monitor error logs for 24 hours
- [ ] Set up regular backup schedule

## Rollback Plan

Document your rollback procedure:

1. How to restore database backup
2. How to revert to previous code version
3. How to switch back to old server (if migrating)
4. Contact information for emergencies

---

**Sign-off:**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| Business Owner | | | |
| QA Tester | | | |
