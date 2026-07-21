# Desktop category navigation — implementation plan

Branch: `ui/desktop-category-nav`. All work lands in the **base** token/style/JS
layer so every client inherits it. The theme overlay
(`static/css/theme-evergreen.css`) and no other client override files are touched.

## Context / problem

On desktop the menu category filters render as a single wrapping cloud of ~22
pill buttons across four ragged rows — the mobile chip strip stretched to full
width. There is no scan order and the layout wastes the horizontal space desktop
affords. The target (mocked in `~/Downloads/greenfish-desktop-categories.html`)
is the industry-standard restaurant-ordering layout (Deliveroo / Uber Eats /
Just Eat): a **sticky left category rail with scrollspy**, beside a single
long-scrolling menu, read the way you'd read a paper takeaway menu.

Scope decisions (confirmed):
- Full rail is built on **`/menu` only**. The homepage keeps a light chip strip.
- Homepage chips **drop their emoji** and **deep-link to `/menu#cat-<id>`**.

All colours/radii/spacing come from existing base tokens (`--brand`, `--bg`,
`--surface`, `--border`, `--text*`, `--space-*`, `--radius-*`), never the mock's
literal hex — so the green Evergreen overlay (and any future client theme) keeps
working for free.

## Inspection findings (Phase 1)

- **Model** `apps/menu/models.py` → `MenuCategory`: has `sort_order`, `is_active`,
  `icon` (emoji). **No slug.** Items: `MenuItem.category` FK, `related_name="items"`,
  `is_available` boolean, `sort_order`. Anchors will use `category.id` (`cat-<id>`).
- **View** `apps/menu/views.py:menu_list` builds a flat `all_items` queryset and a
  flat `categories` queryset. **No per-category count, no grouping, no `Count()`.**
- **Template** `templates/menu/menu_list.html` renders **one flat `#menuGrid`** of
  `.menu-card`s (partial `templates/partials/item_card.html`). No per-category
  sections or anchors exist today.
- **Filtering** (`static/js/menu.js`) is **pure client-side hide/show**: category
  pills toggle `search-hidden` on cards; URL synced via pushState; no scrolling.
  Search (`#menuSearchInput`, ⌘K, 150 ms debounce) feeds the same pass.
- **Emoji**: the menu *category* pills already show **name only** (no emoji). The
  emoji live on the *homepage* chips (`templates/core/home.html`, `category.icon`)
  and on the menu *dietary* pills. So "remove emoji from category labels" = strip
  the homepage chips; the menu rail simply never adds them.
- **CSS**: `--header-height` (72px desktop / 60px mobile) is the single sticky
  offset token, already used by the header and the sticky pill-row and read at
  runtime by menu.js. Container `--content-width` 1180px, side pad `--space-8`.
  Menu grid `.menu-grid-desktop` = 4→3(≤1180)→2(≤920)→1(≤640) cols. Canonical
  desktop/mobile line is **768px**. Existing IntersectionObserver patterns to
  mirror: menu.js sticky-shadow observer (reads `--header-height`) and home.js
  reveal observer. JS is per-page `defer`, plain ES5-style `var`/functions.

## The one conflict to flag (as requested)

The mock changes categories from a **filter that replaces the list** into
**anchor links that scroll one long page**. That is a genuine interaction change,
and it forces the flat `#menuGrid` to be regrouped into per-category `<section>`s.

**Resolution — behaviour branches by breakpoint, one section-based DOM:**

| | Category nav | On activate | Active state |
|---|---|---|---|
| **Desktop ≥768** | vertical rail | smooth-scroll to that `<section>` | scrollspy (IntersectionObserver) |
| **Mobile ≤767** | existing horizontal chip strip | filter (show only that section) | clicked state |

Search stays a filter at both breakpoints (hides cards, auto-hides emptied
sections). This satisfies "desktop scrolls the whole menu" **and** keeps the
mobile *outcome* (tap a category → see only that category) identical. Honest
caveat: because the DOM moves from one flat grid to sections, the mobile filter
JS is **updated** (operates on sections instead of a flat grid) — it is not left
byte-for-byte identical, but the mobile UX/visual result is preserved and is
verified at 390px against the pre-branch build.

## Implementation (small, separate commits)

### 1. View — counts + grouping (`apps/menu/views.py`)
Annotate categories with an available-item count in **one query** and prefetch
their available items (no query-per-category):

```python
from django.db.models import Count, Q, Prefetch

available_items = MenuItem.objects.filter(is_available=True).order_by("sort_order", "name")
categories = (
    MenuCategory.objects.filter(is_active=True)
    .annotate(item_count=Count("items", filter=Q(items__is_available=True)))
    .filter(item_count__gt=0)                       # empty categories don't get a rail row/section
    .order_by("sort_order", "name")
    .prefetch_related(Prefetch("items", queryset=available_items, to_attr="available_items"))
)
```
Keep `all_items` (flat) for the dietary-tag derivation and the `>4` search gate.
Rail counts come from `category.item_count`; sections iterate
`category.available_items`.

### 2. Template — rail + sections (`templates/menu/menu_list.html`)
- Wrap rail + content in `<div class="menu-layout">` (CSS grid, two columns ≥768).
- **Rail** `<nav class="menu-rail" aria-label="Menu categories">`: the existing
  search bar moves in at the top, then `.menu-rail-list` of
  `<a href="#cat-{{ c.id }}" data-category-id="{{ c.id }}">{{ c.name }}
  <span class="menu-rail-count">{{ c.item_count }}</span></a>`. Optional
  `.menu-rail-foot` link to meal deals if a URL exists.
- **Content**: replace the single `#menuGrid` with a loop of
  `<section class="menu-section" id="cat-{{ c.id }}"><h2>{{ c.name }}</h2>
  <div class="menu-grid-desktop">{% for item in c.available_items %}…{% endfor %}</div></section>`,
  reusing `partials/item_card.html` unchanged (cards keep `data-category-id`).
- Keep the existing `.pill-row` (mobile chip strip) and `.dietary-filter-row` as-is
  in the markup; CSS hides the pill-row ≥768 and the rail ≤767.

### 3. CSS — new `static/css/pages/menu.css` (base layer, loaded via `extra_css`)
Add `{% block extra_css %}<link rel="stylesheet" href="{% static 'css/pages/menu.css' %}">{% endblock %}`
to `menu_list.html`. All rules token-driven; wrap desktop layout in
`@media (min-width: 768px)` so mobile is untouched:
- `.menu-layout { display:grid; grid-template-columns: 236px 1fr; gap: var(--space-8); align-items:start }`.
- `.menu-rail { position:sticky; top: calc(var(--header-height) + var(--space-4));
  max-height: calc(100vh - var(--header-height) - var(--space-8)); display:flex; flex-direction:column }`
  with `.menu-rail-list { overflow-y:auto }` so a long list **scrolls
  independently** inside the sticky rail (many-category case).
- Rail link states from tokens: rest `--text-secondary`; hover `--surface-hover`;
  active `--brand-light` bg + `--brand` left border + `--brand` text; count in
  `--text-muted` / tabular-nums.
- `.menu-section { scroll-margin-top: calc(var(--header-height) + var(--space-8)) }`
  so anchor jumps (incl. homepage deep-links on load) clear the sticky header —
  **all offsets derive from the single `--header-height` token**.
- `≤767`: `.menu-layout` collapses to one column, `.menu-rail` hidden
  (`display:none`), `.pill-row` shown — mobile is the current strip verbatim.
- `@media (prefers-reduced-motion: reduce)`: no transitions (mirror existing block).

### 4. JS — scrollspy + desktop scroll branch (`static/js/menu.js`)
Follow the existing observer style (feature-detect, read `--header-height` at
runtime, `var`/functions):
- **Scrollspy** (desktop only, guard `matchMedia('(min-width:768px)')`):
  IntersectionObserver over `.menu-section` with
  `rootMargin: '-<headerHeight+pad>px 0px -70% 0px'`; on intersect set
  `aria-current="location"` + `.is-active` on the matching rail link, clear others.
- **Rail click** (desktop): `preventDefault`, `scrollIntoView({behavior: reduced ? 'auto':'smooth', block:'start'})`.
- **Mobile chip filter**: update `applyMenuFilters` so category filtering toggles a
  `section-hidden` class on non-matching `.menu-section` (equivalent to the old
  per-card hide); search keeps toggling `search-hidden` on cards and now also hides
  a section whose visible-card count is 0.
- Preserve the sticky-shadow observer and the ⌘K / reset-timer behaviour.

### 5. Homepage chips (`templates/core/home.html` + `static/css/pages/home.css`)
- Remove the `{{ category.icon }}` emoji span from `.category-chip`.
- Change link to `href="{% url 'menu:menu' %}#cat-{{ category.id }}"` (Full-menu
  chip stays `{% url 'menu:menu' %}`). The desktop-wrap fix already shipped stays.

## Separate report — Evergreen client-data leak (no change made)

Reporting only, per request. Client-specific naming has leaked into greenfish:
- **`apps/menu/fixtures/evergreen_menu.json`** — client-named filename; contains
  categories **"Evergreen Fish"** (pk 10) and **"Evergreen Special Roll"** (pk 22).
  The other 22 categories read generic.
- **`apps/mealdeals/fixtures/evergreen_mealdeals.json`** — client-named filename
  only; contents generic.
- **`static/css/theme-evergreen.css`** — client-named theme overlay (expected;
  this is the per-client overlay, not base data).

These fixtures are **manual `loaddata` only** — nothing auto-loads them. The
template's actual auto-seeded menu is the unrelated generic Zimbabwean data
migration `apps/menu/migrations/0002_zimbabwean_menu.py`. So the Evergreen
fixtures are a hand-loaded client overlay, not base seed data. Recommendation
(deferred): rename to a generic demo fixture and neutralise the two category
names, but **not touched now** as instructed.

## Verification

- **Desktop 1280 & 1440px**: rail sticky under header; counts correct; clicking a
  rail item scrolls to its section with the heading clear of the header;
  scrollspy highlights the section in view; search filters and empties hide;
  keyboard Tab shows focus rings; `aria-current` tracks the active category.
- **Mobile 390px**: visually and behaviourally unchanged vs `main` — sticky
  horizontal chip strip, tap-to-filter, search, ⌘K. Screenshot-compare to pre-branch.
- **Theme**: load with `theme-evergreen.css` active — rail/sections pick up green
  from tokens; then remove the overlay `<link>` and confirm the default orange
  base renders identically in structure.
- **Few categories** (e.g. 3): rail short, layout intact. **Many** (24): rail list
  scrolls independently inside the sticky container; page scroll unaffected.
- **Counts query**: `assertNumQueries`-style check that category counts add no
  per-category queries (single annotated queryset).
- **Deep-link**: hit `/menu#cat-<id>` directly and from a homepage chip — lands
  on the right section with the heading below the header.
