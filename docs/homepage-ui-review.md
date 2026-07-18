# Homepage UI Review & Proposal

Status: **awaiting approval** — nothing below is implemented yet. Approve, amend, or strike items and implementation will follow in small, separately reviewable commits (bugs first, then structure).

Scope: mobile-first (the bottom nav and cart-bar overlap only exist below 768px; desktop keeps its current layout unless noted).

---

## Part 1 — Findings

### 1.1 Homepage view and template

`apps/core/views.py:26 home()` renders `templates/core/home.html` (475 lines). The template extends `base.html` and contains **no `{% include %}` partials — every section is inline markup**. Render order:

| # | Section | Lines | Shown |
|---|---------|-------|-------|
| 1 | Marketing hero (headline, Order Now / View Full Menu, stats, rotating plate) | 13–86 | always |
| 2 | Pickup/Delivery service toggle bar | 89–113 | always |
| 3 | Order Again (reorder cards) | 115–161 | signed-in with orders |
| 4 | Your Favourites (+ dismissible hint variant) | 163–222 | signed-in |
| 5 | Popular Right Now (`menu-card` grid; mobile swipe strip as of `5905bb9`) | 224–267 | always |
| 6 | Meal Deals (`deal-spotlight-card`) | 269–308 | active deals |
| 7 | House Signatures (`signature-card` strip) | 310–350 | "special" category exists |
| 8 | Today's Offers | 352–381 | >1 hero offer |
| 9 | Browse the Menu (category chips + big button) | 384–414 | always |
| 10 | Rewards teaser | 417–432 | always |
| 11 | Opening Hours / Find Us info-strip | 434–467 | hours or address set |

Page JS: `static/js/home.js` (section reveal animation, hero image rotation, favourites-hint dismiss).

### 1.2 Base layout and the fixed bottom elements

All three fixed elements are defined once in `templates/base.html`, as fixed-position siblings **outside** `<main id="main-content">` (line 190):

- **Bottom nav** — base.html:195–213; CSS `static/css/shell.css:377–397`. Fixed to bottom, phones only (hidden ≥768px).
- **Sticky cart bar** — base.html:248–261 (`{% block basket_bar %}`); CSS shell.css:428–464. Fixed pill; on mobile sits at `bottom: nav + safe-area + 12px`. Rendered on every page except checkout/cart paths; visible only when `cart_count > 0` (server-rendered class + live toggle in `app.js`).
- **Scroll-to-top button** — base.html:263–265; CSS shell.css:513–550. Fixed right; on mobile at `bottom: nav + safe-area + 84px`.

**The layout reserves space for only one of them.** `static/css/base.css:76–80` gives `body` a `padding-bottom` of nav height + safe area on phones — but nothing ever reserves the cart bar's ~66px pill, so with a non-empty basket it covers the last row of content on every page. The scroll-to-top button (bottom = nav + 84px) sits directly on top of the cart pill (which spans roughly nav + 12px to nav + 78px) and floats over content "add" buttons.

### 1.3 Design tokens

`static/css/tokens.css` is the single token source; cascade layers `reset, base, components, shell, pages, utilities` are declared at line 8 (pages CSS wins over components/shell). Relevant tokens:

- Spacing: 4px-base scale `--space-1…16`.
- Shell: `--header-height`, `--bottom-nav-height: 62px`, `--safe-bottom: env(safe-area-inset-bottom, 0px)`. **There is no custom property for the cart bar's height** — hence the bug above.
- Section rhythm: `.section { padding-block: clamp(2.5rem, 5vw, 4.5rem) }` (`components.css:627`), so two adjacent sections stack up to ~144px of empty space; `.section-header` adds another `margin-bottom: 2rem` (`components.css:636`).
- Theme: `static/css/theme-evergreen.css` overrides **colour tokens only**; deleting its `<link>` (base.html:33) reverts the whole site to the default orange. Any change here must preserve that.

### 1.4 Full-menu CTAs on the homepage

Content-area links to `menu:menu` (the shell adds header-nav Menu, bottom-nav Menu tab, and footer "Full Menu" on top of these):

| Line (home.html) | CTA |
|---|---|
| 41 | Hero "Order Now" → `#menu-section` anchor (the Browse section) |
| 45 | Hero "View Full Menu" |
| 171 | Favourites section link "Browse Menu" (signed-in) |
| 215 | Favourites-hint "Browse Menu" button (signed-in, empty state) |
| 232 | Popular Right Now section link "View Full Menu" |
| 318 | House Signatures "See Them All" (category-scoped) |
| 391 | Browse the Menu section link "Full Menu" |
| 399 | Category chips (category-scoped) |
| 408 | "View the Full Menu" primary button |

That is ~5 unscoped duplicates in the content alone, plus the Menu tab always visible in the bottom nav.

### 1.5 Item-card patterns

Three distinct dish-card patterns, plus two promo patterns — all duplicated inline markup, no shared partial:

1. **`menu-card`** (vertical photo card; compact horizontal variant ≤640px) — Popular (home.html:239–262), Favourites (178–201), and near-identical copies in `templates/menu/menu_list.html` and `templates/mealdeals/list.html`. Add affordance: round `menu-card-add` "+" button → `quickAddToCart()`.
2. **`signature-card`** (carousel card, gradient body, numbered title) — home.html:325–345 only. Borrows `menu-card-add` but has its own title/desc/price/footer classes (`static/css/pages/home.css:593–674`).
3. **`deal-spotlight-card`** — home.html:284–303 only. The whole card is an `<a>` to the deal builder; CTA is the text "Build Yours" (no add button — legitimately different, deals require the builder flow).

Also: `reorder-card` (a `<form>` with a Reorder submit) and `offer-card-desktop`. The CSS comment at `components.css:6` confirms shared class names are load-bearing for `app.js`.

### 1.6 Shared vs homepage-only blocks

`rewards-teaser`, the `info-strip` (Opening Hours / Find Us), and all `deal-spotlight-*` markup/styles appear **only** in `home.html` + `home.css`. They are safe to move or delete without affecting other pages. A full rewards page already exists at `loyalty:dashboard` (the bottom-nav Rewards tab).

### 1.7 Checkout authentication

**Guest checkout is supported.** `apps/orders/views.py:452 checkout()` has no auth requirement; the cart lives in the session; order creation stores `user=None` for anonymous customers (views.py:784). Signed-in users only get their contact fields prefilled. The homepage does not need to funnel visitors through sign-up (the header's "Order Now → signup" button for anonymous users at base.html:89 is arguably mislabelled, but out of scope here).

### 1.8 Meal-deal images

Both active `MealDeal` rows (Kids Box, Chinese Box A) have `image=None`. The identical "bento box" graphic on the cards is the **🍱 emoji fallback** rendered large — decided in the template at home.html:286–290 (`deal-spotlight-icon`) and again in `mealdeals/list.html:23–26` (🍽️). Menu items *do* have real photography (127 items populated), so a real image is derivable for every deal from the items it contains.

### 1.9 Bonus finding

`SiteSettings` (`apps/core/models.py:26`) has **no** `hero_image`, `tagline`, `shop_description`, or `about_page_enabled` fields, although `base.html` and `home.html` reference all four — Django templates resolve them silently to empty, so those branches are dead and the hero always renders fallback copy. Precedent exists for admin-editable flags (`delivery_enabled`, `delivery_map_enabled`), which the hero toggle below builds on.

---

## Part 2 — Bug fixes (proposed regardless of redesign)

### B1. Fixed bars overlap page content

One base-layout fix, applied once, no per-template padding hacks:

- **`static/css/tokens.css`** — add `--cart-bar-clearance: 0px` next to the existing shell tokens.
- **`static/css/base.css`** — replace the phone-only body padding (lines 76–80) with a single rule:
  `body { padding-bottom: calc(var(--nav-clearance, 0px) + var(--cart-bar-clearance) + var(--safe-bottom)); }`
  where `--nav-clearance` is `62px` below 768px and `0px` above (bottom nav is phones-only), preserving today's behaviour when the basket is empty.
- **Cart-bar conditionality** (the bar only renders when the basket is non-empty and not on checkout/cart):
  - Server: `templates/base.html` body tag gains a `has-cart-bar` class under the same condition that renders the visible bar (base.html:249–250).
  - Client: `static/js/app.js` already toggles `#stickyCartBar.visible` when the cart changes; add one line toggling `body.classList` in the same place.
  - CSS: `body.has-cart-bar { --cart-bar-clearance: 78px; }` (66px pill + 12px gap). No `:has()` dependency; works in every browser.
- Bump the service-worker cache (maintenance rule).

Files: `tokens.css`, `base.css`, `shell.css`, `base.html`, `app.js`, `templates/pwa/service-worker.js`, `apps/pwa/tests.py`.

### B2. Scroll-to-top button

**Recommendation: remove it entirely** — button (base.html:263–265), CSS (shell.css:513–550), and the JS handler (app.js ~270–280). Rationale: on mobile the bottom nav already provides one-tap navigation and the restructured page is short; on desktop the sticky header makes the top reachable. It currently collides with the cart pill and floats over item add-buttons for no benefit.

Fallback option if you'd rather keep it: desktop-only (`display:none` below 768px) — but removal is the cleaner call given the nav.

### B3. Meal-deal placeholder images

Add a `display_image` property to `MealDeal` (`apps/mealdeals/models.py`) with the fallback chain: `self.image` → first available option's `menu_item.image` (first slot by sort order) → `None`. Templates (`home.html` deal cards, `mealdeals/list.html`) render `deal.display_image` and only fall back to the emoji when there is genuinely no photo anywhere in the deal. Result: Kids Box and Chinese Box A show real photos of what's in the box, with zero data entry; an admin-uploaded `image` still wins when present.

Files: `apps/mealdeals/models.py`, `templates/core/home.html`, `templates/mealdeals/list.html`.

---

## Part 3 — Homepage restructure

Target render order (mobile-first; desktop shares the same structure with wider layouts):

1. **Compact status band** — replaces the hero as the default top of page:
   - Open/closed now + today's hours, from a new helper `apps/core/services/opening_hours.py` reading the existing `SiteSettings.opening_hours` JSON (the parsing logic in `home()` views.py:67–81 moves there).
   - Delivery minimum (`SiteSettings.delivery_minimum_order_amount`, exists) and delivery ETA — needs a new optional `SiteSettings.delivery_eta_text` CharField (blank ⇒ hidden), since no ETA field exists today.
   - The existing Pickup/Delivery toggle (home.html:89–113) moves up into this band unchanged — markup, `data-desktop-service` hooks, and `app.js` behaviour are reused as-is. This also fixes it being buried below the fold behind the cart bar.
2. **Slim offer banner** — when active hero offers exist, one compact dismissible strip (name + short line + link to the offer), replacing both the hero-offer headline and the "Today's Offers" section. The full offer list stays on the Rewards tab. Dismissal follows the existing `data-dismiss-hint` localStorage pattern in `home.js`.
3. **Category chips** — the existing `.category-strip` (home.html:397–404) moves up here; a trailing chip "Full menu →" becomes the page's **single** unscoped full-menu CTA.
4. **Order Again**, then **Your Favourites** (signed-in only) — content unchanged, headers retitled per Part 4.
5. **Popular Right Now** — absorbs House Signatures: `home()` merges `signature_items` after `popular_items` (deduplicated); signature dishes get a "Signature" badge variant instead of "Popular". The mobile swipe strip from commit `5905bb9` is kept; the separate signatures section and its one-off `signature-card` CSS are deleted.
6. **Meal Deals** — unchanged position, with B3 images.
7. **Footer** — gains an Opening Hours column (data via a small addition to `apps/config/context_processors.py`, reusing the moved hours helper, so it renders site-wide). The homepage info-strip section is deleted; the footer already carries address/phone.

**Removed from the homepage:** marketing hero (→ optional, below), rewards teaser (the Rewards tab and footer link cover it; `loyalty:dashboard` is already the promo surface), "Browse the Menu" section incl. the standalone "View the Full Menu" button (chips + Menu tab cover it), "Today's Offers" section (→ banner), hours/Find Us info-strip (→ footer).

### The hero becomes an optional, config-driven block

Per the multi-client constraint, the hero is **not deleted**:

- New `SiteSettings.homepage_hero_enabled = BooleanField(default=False)` + migration + exposure in `apps/core/admin.py` (same pattern as `delivery_enabled`).
- `home.html` wraps the hero section in `{% if site_settings.homepage_hero_enabled %}`; when on, it renders **above** the status band, and the band drops its duplicate shop-name line.
- Off by default ⇒ the ordering path is the first thing on the page; brochure-style clients flip one admin switch. Hero CSS/JS (rotation) stays; `home.js` already guards on element existence.

---

## Part 4 — Consistency cleanups

- **CTA consolidation:** exactly one unscoped "Full menu" CTA (the trailing chip). Category-scoped links (chips) stay. Section arrow-links point only at genuinely different destinations (Order History, All Deals, Rewards).
- **Section heading formula:** retire the repeated two-tone `h2 span` + marketing subtitle + arrow-link trio. New compact `.section-title` row: single-colour heading, no subtitle (they are filler: "What customers are ordering most right now", etc.), optional inline link. Two-tone treatment survives only inside the optional hero.
- **Vertical rhythm:** `home.html` sets `{% block body_class %}home-page{% endblock %}`; `home.css` scopes `.home-page .section { padding-block: clamp(1.25rem, 2.5vw, 2rem) }` and trims `.section-header` margin — roughly halving inter-section whitespace on the homepage without touching other pages.
- **One shared item card:** new `templates/partials/item_card.html` (params: item, badge label/variant, numbered-title flag) replaces the duplicated `menu-card` markup in Popular, Favourites, the signatures fold-in, `menu/menu_list.html`, and `mealdeals/list.html`. One add affordance everywhere: the `menu-card-add` "+" → `quickAddToCart()`. `deal-spotlight-card` remains a distinct component (builder flow) but is restyled to the same visual family. Class names used by `app.js` (`menu-card-*`, `data-quick-add`) are preserved.

---

## Part 5 — Constraints honoured

- **Theme overlay stays reversible:** all changes use semantic tokens; `theme-evergreen.css` remains a colour-only overlay whose removal reverts to orange.
- **Reusable template:** hero is admin-toggleable per client; new fields (`homepage_hero_enabled`, `delivery_eta_text`) default to off/blank so existing deployments render sensibly without data changes.

---

## Part 6 — Proposed commit sequence

Each commit independently reviewable and shippable; SW cache bumped once per commit that changes precached pages.

1. **B1** — bottom-bar clearance via custom properties (base layout only).
2. **B2** — remove scroll-to-top button.
3. **B3** — `MealDeal.display_image` fallback chain.
4. **S1** — `homepage_hero_enabled` flag + migration; hero wrapped (still on-top when enabled); no visual change with flag off yet… flag ships defaulted **on** in this commit to stay no-op, flipped to off in S2. *(Alternative: default off immediately — call it out in review.)*
5. **S2** — status band + service toggle relocation + category chips move + section removals (hero off, rewards teaser, Browse the Menu, info-strip → footer hours column, Today's Offers → offer banner).
6. **S3** — Popular/Signatures merge + shared `item_card.html` partial adopted across templates.
7. **S4** — heading formula + homepage spacing scale.

Verification per commit: full `manage.py test`; manifest collectstatic against a scratch root; headless Chrome at 390×844 and 1280×900 — with items in the basket, confirm the last content row and footer clear the cart bar on home/menu/offers; meal-deal cards show real photos; hero absent by default and correct with the flag on; evergreen link removed locally → orange theme still renders.
