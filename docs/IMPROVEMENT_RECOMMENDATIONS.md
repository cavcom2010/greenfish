# Future Improvements Review

Date: 2026-04-11
Project: Two Fish / Tinashe takeaway platform

## Scope

This document is a broad repo-wide review of the current Django app and the
improvements I recommend for future work. It is based on the current settings,
URLs, representative models, views, services, templates, tests, docs, and the
main commerce flows.

Quick repo signals from this review:

- 12 model-backed apps
- 74 HTML templates
- 24 desktop-specific templates under `templates/desktop/`
- 17 templates with inline `<script>` blocks
- 6 app-level `tests.py` modules
- 8 model-backed apps without test modules
- no CI workflow or container-based local/prod bootstrap in the repo

## Recommended Priorities

### Priority 0: security and correctness

1. Protect public order and payment endpoints.
   - `orders:confirmation`
   - `orders:confirmation_instore`
   - `orders:tracking`
   - `payments:payment_status_api`
   - `payments:demo_checkout`
   These should use either authenticated ownership checks or signed public
   tokens. Right now they are too easy to enumerate from `order_number`.

2. Fix the desktop login wrapper.
   In `apps/accounts/views.py`, the desktop POST branch still builds
   `LoginForm(request)` instead of binding POST data. That should be corrected
   before any further auth hardening work.

3. Tighten server-side request validation.
   Most non-account POST handlers still read raw `request.POST` directly. Add
   Django forms or serializers for checkout, voucher apply, cart quantity
   updates, profile updates, and meal deal selection.

4. Cap cart quantities and similar user-controlled inputs.
   The cart update path still accepts arbitrary integers. Clamp quantity and
   reject abusive values server-side.

5. Remove silent failure paths around operational side effects.
   SMS and push follow-ups should not fail with `except Exception: pass`.
   Capture failures in logs, queue retries, and make them observable.

6. Fix overly broad operations fallback permissions.
   `apps/operations/permissions.py` currently grants manager-level access to
   staff users with no explicit operations group. That should be inverted so
   "no group" means "no board access".

### Priority 1: architecture simplification

1. Reduce the desktop/mobile template split.
   There are 24 desktop-only templates plus repeated per-view template
   switching across the codebase. Move toward one responsive template system,
   or at least centralize template resolution in a shared helper.

2. Remove compatibility passthrough views from `apps.orders`.
   Several orders routes just forward to `apps.operations.views`. Point URLs to
   the real operations views directly and trim the alias layer.

5. Standardize JSON response shapes.
   Cart, checkout, voucher, and operations endpoints still return different
   response envelopes. Standardizing these will simplify HTMX/fetch code and
   future API work.

### Priority 2: scale and maintainability

1. Add database constraints and missing indexes.
   This codebase still relies heavily on application logic for data integrity.
   Add `CheckConstraint`, `UniqueConstraint`, and targeted indexes for the
   high-traffic commerce and loyalty tables.

2. Move signal-heavy business flows into explicit services and async jobs.
   Loyalty, SMS, and customer profile creation all rely on `post_save`
   signals. Keep signals minimal, add `dispatch_uid`, and move meaningful work
   into explicit services or a job queue.

3. Improve analytics query design.
   The dashboard currently does repeated day-by-day Python loops and uses
   `payment_status` where the UI label suggests payment-method reporting.
   Replace those loops with database aggregation and fix the reporting model.

4. Expand the test surface substantially.
   Model-backed apps without test modules today:
   - `accounts`
   - `config`
   - `customers`
   - `mealdeals`
   - `menu`
   - `offers`
   - `payments`
   - `sms`

5. Add release automation.
   The repo has no visible CI pipeline. Add a baseline workflow for:
   - `manage.py check`
   - migrations validation
   - test suite
   - linting/formatting

## Detailed Recommendations

### 1. Security and abuse prevention

- Make public guest order access token-based rather than order-number based.
- Add rate limits for login, signup, password reset, order tracking, and
  payment status checks.
- Move voucher attempt limits into settings so they can vary by environment.
- Add a content security policy and tighten frontend script loading over time.
- Review whether optional email verification is still the right default once
  loyalty, referrals, and saved customer data are relied on more heavily.

### 2. Commerce and product

- Finish online checkout support for non-discount offer types such as
  `free_item` and `bundle`.
- Add explicit promotion stacking rules so voucher vs offer precedence is not
  implicit.
- Add admin preview tooling for promotions:
  - eligible basket examples
  - minimum spend checks
  - active date windows
  - per-customer limit visibility
- Add campaign analytics for vouchers and offers:
  - activation rate
  - redemption rate
  - revenue lift
  - most-used promo codes
- Add reorder from order history and favorite-item shortcuts.
- Add a proper guest-to-account merge path so loyalty and order history can be
  linked after checkout.

### 3. Accounts, customer data, and permissions

- Replace the hand-written desktop allauth wrappers with cleaner class-based
  wrappers or a shared adapter layer.
- Add forms for profile and address editing instead of direct POST parsing.
- Add uniqueness rules around customer addresses and clearer default-address
  behavior.
- Tighten operations role assignment so roles are explicit, auditable, and not
  derived from broad `is_staff` fallback behavior.

### 4. Architecture and code health

- Introduce a shared `resolve_template(request, "app/view.html")` helper if the
  desktop/mobile split remains for now.
- Move the 17 inline script blocks into static JS files or page-specific
  modules.
- Decide whether the app wants a small modern frontend build step; right now
  nearly all frontend behavior is spread between inline script blocks and one
  `static/js/desktop.js` file.
- Add queryset helpers/managers for common business filters such as:
  - active offers
  - visible hero offers
  - available menu items
  - recent orders for operations
- Continue removing underused app boundaries where the split no longer helps.

### 5. Data model and persistence

- Add constraints for obvious business rules, for example:
  - offer end date after start date
  - voucher validity end after start
  - meal deal price not above original price
  - unique address labels per user when appropriate
- Review indexing on the highest-traffic lookup fields in orders, payments,
  loyalty, and SMS models.
- Consider a shared singleton base model for settings-style tables instead of
  repeating the same `get()` pattern.

### 6. Performance and scalability

- Add pagination to order history, loyalty history, and any staff-facing lists
  that can grow unbounded.
- Cache expensive but slow-changing content:
  - site settings
  - hero/menu fragments
  - analytics snapshots
- Push analytics aggregation closer to the database and add caching around the
  dashboard.
- Audit `select_related` / `prefetch_related` coverage for staff boards and
  account history pages as data volume grows.
- Extend the health endpoint to check more than the database when running in
  production, especially cache and optional provider connectivity.

### 7. Testing and developer workflow

- Add missing test modules for the untested apps listed above.
- Add regression tests for:
  - desktop auth views
  - public order access rules
  - payment webhooks and return flows
  - offer activation and stacking rules
  - SMS side effects
- Add linting and formatting tools such as Ruff and Djlint.
- Add at least one end-to-end smoke test for:
  - guest checkout
  - logged-in checkout
  - staff order board status flow

### 8. Operations and observability

- Add Sentry or equivalent error aggregation.
- Emit structured logs for payment lifecycle, order lifecycle, and promo usage.
- Move SMS, push, and other slow side effects to a background worker instead of
  running them inline in request/response flows.
- Add a repeatable deployment path in-repo:
  - CI pipeline
  - container or service definitions
  - environment validation
  - release checklist automation

### 9. Frontend and UX

- Reduce duplicated mobile/desktop markup and let CSS do more of the work.
- Create a consistent pattern for inline form feedback, loading states, and
  async errors across checkout, cart, loyalty, and operations.
- Run a basic accessibility pass:
  - keyboard navigation
  - label/input associations
  - color contrast
  - focus states
  - screen-reader wording
- Normalize responsive spacing, component states, and button styling so the app
  feels like one system rather than multiple page-specific implementations.

### 10. Documentation

- Consolidate duplicate docs with case-only naming differences, for example:
  - `docs/ADMIN_GUIDE.md` and `docs/admin-guide.md`
  - `docs/DEPLOYMENT.md` and `docs/deployment.md`
- Refresh the root `README.md` so it matches the current stack and current app
  behavior.
- Add one short "system map" document covering app boundaries, data ownership,
  and key request flows.
- Keep this file updated as work lands so it stays a roadmap, not a forgotten
  audit artifact.

## Suggested Roadmap

### Next 2 weeks

- Lock down public order/payment endpoints
- Fix desktop login POST handling
- Clamp cart quantities and tighten request validation
- Remove operations fallback-manager permissions
- Log and retry notification failures instead of swallowing them

### Next 1 to 2 months

- Consolidate duplicate customer/cart implementations
- Add constraints and indexes
- Expand tests to offers, payments, menu, and accounts
- Add CI for checks, tests, and linting
- Start shrinking the desktop/mobile template split

### Next quarter

- Move side effects to background jobs
- Improve analytics correctness and performance
- Add richer promotion tooling and campaign reporting
- Introduce better frontend structure and reduce inline scripts
- Simplify docs and deployment workflow

## Recommended Principle

The most valuable future work here is not a rewrite. It is tightening the app
around a few clear seams:

- one customer profile model
- one cart abstraction
- one responsive UI strategy
- one explicit permission model
- one repeatable validation and release pipeline

If those are done well, the rest of the roadmap becomes much easier.
