# Staff & driver onboarding / offboarding runbook

All staff access to `/ops/` is controlled by three things on the user account:
`is_staff`, membership of an **Operations group**, and (for drivers) the link
from a **Delivery driver** record. Manage all of it in Django admin.

## Onboarding

### Any staff role (manager / kitchen / cashier)
1. Admin → Users → Add: create the account (email + strong password), tick **Staff status**.
2. Assign exactly one group: `Operations Manager`, `Operations Kitchen`, or `Operations Cashier`.
3. Managers are forced to enrol in **two-factor authentication** on first login
   (authenticator app + recovery codes). Other roles can enrol from
   Account → Profile → Manage 2FA — encourage it.

### Drivers
1. Create the user as above, but assign only the `Operations Driver` group.
   This role can see **only** the driver board — no kitchen/collection boards,
   no other orders, no customer lists.
2. Admin → Delivery drivers → create (or edit) the driver record and set its
   **User** field to the new account. Assignment requires `Is active` ticked.
3. Driver bookmarks `/ops/driver/` on their phone (or installs the PWA).

## Offboarding (do all steps — same day the person leaves)

1. **Remove the Operations group(s)** from the user (Admin → Users). This
   instantly revokes every `/ops/` surface on their next request.
2. **Untick Staff status** unless they still need admin access for another reason.
3. Drivers: on the **Delivery driver** record, untick **Is active** (blocks new
   assignments) and clear the **User** link.
4. **Untick Active** on the user account to block login entirely, or set an
   unusable password if you may rehire.
5. Sessions: staff/driver sessions self-expire within 12 hours
   (`OPS_SESSION_MAX_AGE`). To revoke immediately, also run
   `python manage.py clearsessions` after deactivating, or change the account
   password (invalidates existing sessions).

## Notes

- One person, one role. Only managers should hold `Operations Manager`.
- Lost driver phone: do offboarding steps 1–4 for that account immediately;
  the session dies with the group removal for `/ops/` purposes.
- Repeated 403s on `/ops/` routes trigger the admin failure-alert emails —
  treat alerts referencing an offboarded account as an attempted misuse signal.
