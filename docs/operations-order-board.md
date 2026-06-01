# Operations Order Board

This document covers the staff-facing order operations subsystem in `two_fish`.

It documents:
- the `apps.operations` app
- board routes and templates
- role and permission model
- order status workflow
- action handling
- notification side effects
- migrations and test coverage

This is the authoritative guide for the current takeaway and delivery operations flow.

## 1. Purpose

The customer ordering flow and the staff operations flow are now separated.

- `apps.orders` owns:
  - order records
  - checkout
  - payment state
  - public tracking
  - customer-facing order lifecycle
- `apps.operations` owns:
  - kitchen board
  - collection board
  - role-aware staff actions
  - operational notes
  - staff detail modal and board fragments

This split is deliberate. The staff workflow has different requirements from customer checkout and should not be buried inside order placement views.

## 2. App Ownership

### Primary app

- `apps/operations/permissions.py`
- `apps/operations/services.py`
- `apps/operations/views.py`
- `apps/operations/urls.py`
- `apps/operations/tests.py`

### Supporting app/model dependencies

- `apps/orders/models.py`
- `apps/sms/services.py`
- `apps/sms/signals.py`
- `apps/pwa/services.py`
- `templates/operations/orders/*`
- `templates/orders/tracking.html`

## 3. Route Map

Mounted under `/ops/` from `config/urls.py`.

### Collection board

- `/ops/orders/collection/`
- `/ops/orders/collection/fragment/`

Purpose:
- pickup handover
- delivery dispatch handover
- dispatch completion for deliveries

### Kitchen board

- `/ops/orders/kitchen/`
- `/ops/orders/kanban/`
- `/ops/orders/kanban/column/<status>/`
- `/ops/orders/kanban/columns/`

Purpose:
- paid orders awaiting acceptance
- accepted orders awaiting preparation
- prepared orders awaiting handoff to front counter / driver

### Shared operations endpoints

- `/ops/orders/<order_id>/detail/`
- `/ops/orders/<order_id>/action/`

Purpose:
- order detail modal
- notes persistence
- named action execution

### Legacy compatibility routes

The older `orders:` routes still exist and delegate into `apps.operations`:

- `/orders/dashboard/`
- `/orders/dashboard/orders/<id>/detail/`
- `/orders/kanban/`
- legacy status update endpoints in `apps.orders.views` and `apps.orders.views_kanban`

These exist to avoid breaking older links and templates while the operations app becomes the canonical owner.

## 4. Permission Model

The subsystem uses Django groups, not a custom user-role field.

Seeded groups:

- `Operations Manager`
- `Operations Kitchen`
- `Operations Cashier`

Implementation lives in `apps.operations.permissions`.

### Role capabilities

#### Manager

Full access:
- kitchen board
- collection board
- all order actions
- cancel order
- save notes

#### Kitchen

Access:
- kitchen board only

Allowed actions:
- `accept_order`
- `start_preparing`
- `mark_ready`
- `save_notes`

Not allowed:
- dispatch
- collected
- delivered
- cancel

#### Cashier

Access:
- collection board only

Allowed actions:
- `mark_dispatched`
- `mark_collected`
- `mark_delivered`
- `save_notes`

Not allowed:
- accept
- start preparing
- mark ready
- cancel

### Explicit roles only

Operations access requires `is_staff=True` and membership in one of the operations groups.

Ungrouped staff users do not receive board access. A one-time migration assigns existing ungrouped staff users to `Operations Manager` so current accounts keep access while new staff must be assigned deliberately.

## 5. Order Status Model

The operational order states are:

- `pending`
- `confirmed`
- `preparing`
- `ready`
- `out_for_delivery`
- `completed`
- `cancelled`

### Meaning of each state

#### `pending`

Order exists but has not entered the production flow yet.

In practice:
- online payment may still be pending
- only paid pending orders can be accepted

#### `confirmed`

Order has been accepted into the kitchen workflow.

Side effects:
- `accepted_at`
- `accepted_by`
- `estimated_ready_time` if not already set

#### `preparing`

Kitchen is actively working on the order.

Side effects:
- `preparing_started_at`

#### `ready`

The kitchen has finished the order.

For pickup:
- ready for collection

For delivery:
- ready to dispatch to driver

Side effects:
- `actual_ready_time`
- `ready_at`

#### `out_for_delivery`

Delivery-only status. The order has left the shop and is with the driver.

Side effects:
- `dispatched_at`
- `ready_at` backfilled if not already present
- `actual_ready_time` backfilled if not already present

#### `completed`

The operational flow is finished.

For pickup:
- customer collected order

For delivery:
- order delivered

Side effects:
- `completed_at`
- `completed_by`
- `collected_at` for pickup
- `delivered_at` for delivery

#### `cancelled`

Order was cancelled.

Side effects:
- `cancelled_at`
- `cancelled_by`
- `cancel_reason`

## 6. Service Type and Status Display

Service type remains:

- `pickup`
- `delivery`

The user-facing display labels are intentionally different from raw internal statuses:

- pickup `ready` -> `Ready for Collection`
- delivery `ready` -> `Ready to Dispatch`
- delivery `out_for_delivery` -> `Out for Delivery`

This distinction matters because:
- the kitchen is done at `ready`
- the driver handoff happens after that

## 7. Operational Timestamps and Notes

The order model now captures these operational fields:

- `accepted_at`
- `preparing_started_at`
- `ready_at`
- `dispatched_at`
- `collected_at`
- `delivered_at`
- `completed_at`
- `cancelled_at`
- `accepted_by`
- `completed_by`
- `cancelled_by`
- `staff_notes`
- `handover_notes`
- `cancel_reason`

### Notes fields

#### `staff_notes`

Internal preparation notes.

Examples:
- allergy handling
- remake instructions
- plating note

#### `handover_notes`

Collection or dispatch note.

Examples:
- collected by spouse
- driver name or bag handoff note
- issue observed at pickup

#### `cancel_reason`

Required when cancelling an order through the operations action endpoint.

## 8. Action Model

The operations subsystem does not treat raw statuses as the main staff API.

The canonical contract is named actions:

- `accept_order`
- `start_preparing`
- `mark_ready`
- `mark_dispatched`
- `mark_collected`
- `mark_delivered`
- `cancel_order`
- `save_notes`

This matters because action names are stable, while the resulting status may differ by service type or future product model.

### Why actions are better than direct status posting

- clearer permission control
- clearer UI intent
- easier transition validation
- safer future extension for dine-in workflows

Legacy routes can still post raw statuses, but they are translated through `action_from_legacy_status`.

## 9. Board Design

### Kitchen board

Source queryset:
- `pending`
- `confirmed`
- `preparing`
- `ready`

Only paid orders are included. Unpaid `pending` orders from abandoned online checkout sessions stay out of the staff workflow.

Kanban columns:

- `confirmed`
  - includes `pending` and `confirmed`
- `preparing`
  - includes `preparing`
- `ready`
  - includes `ready`

Operational interpretation:
- this is the kitchen production queue
- delivery orders stay here until the kitchen finishes them
- they do not become `out_for_delivery` until front counter / cashier dispatches them

### Collection board

Source queryset:
- `ready`
- `out_for_delivery`

Only paid orders are included.

Operational interpretation:
- pickup orders are completed here
- delivery orders are dispatched here
- delivery orders can also be marked delivered here

The collection board is the handoff board, not the kitchen production board.

## 9.1 Stale Board Actions

Board cards and detail modals post the order status they were rendered with as `expected_status`.

If another staff member changes the order first, the action endpoint returns `409` and the board should be refreshed before trying again.

## 9.2 Refresh and Side-Effect Visibility

Both boards use 5-second HTMX polling and show a visible last-updated or refresh-failed state.

SMS and push notification failures are logged with stack traces but do not block the staff workflow action.

## 10. Detail Modal

The order detail modal is shared across the boards.

It provides:
- customer details
- service details
- item breakdown
- timestamp summary
- note editing
- cancel reason input
- action buttons

The modal saves notes through the same `order_action` endpoint using `save_notes`.

Notes are intentionally persisted without changing status.

## 11. Notifications

Notifications are centralized around the action service and supporting signals.

### SMS

Handled in:
- `apps/sms/services.py`
- `apps/sms/signals.py`

Messages currently supported:
- order confirmed
- order ready
- out for delivery
- delivered

Behavior:
- pickup ready SMS is sent when order becomes `ready`
- delivery dispatch SMS is sent when order becomes `out_for_delivery`
- delivery delivered SMS is optional and controlled by SMS settings

### Push

Handled in:
- `apps/pwa/services.py`

Push events currently supported:
- confirmed
- ready
- out for delivery
- delivered

## 12. Migration History

Relevant migrations for the operations subsystem:

### `operations.0001_create_operations_groups`

Creates the three Django groups:
- `Operations Manager`
- `Operations Kitchen`
- `Operations Cashier`

### `orders.0006_alter_order_status`

Adds `out_for_delivery` to the `Order.status` choices.

### `orders.0007_backfill_delivery_dispatch_status`

Moves legacy delivery orders from:
- `ready`

to:
- `out_for_delivery`

Reason:
- the older system overloaded `ready` for both kitchen completion and driver dispatch
- the new model separates those two stages

## 13. Test Coverage

Primary regression coverage lives in:
- `apps/operations/tests.py`
- `apps/orders/tests.py`

Covered cases include:
- route access by role
- kitchen-only actions
- cashier-only actions
- manager cancellation
- note saving without state changes
- delivery dispatch and completion flow
- pickup collection flow
- compatibility route behavior
- customer tracking rendering for `out_for_delivery`

Recommended validation commands:

```bash
./venv/bin/python manage.py check
./venv/bin/python manage.py test apps.operations.tests apps.orders.tests
./venv/bin/python manage.py test
```

## 14. Daily Operational Flow

### Pickup order

1. Customer places order
2. Paid order appears on kitchen board
3. Kitchen accepts order
4. Kitchen starts preparing
5. Kitchen marks ready
6. Order appears on collection board
7. Cashier marks collected
8. Order becomes completed

### Delivery order

1. Customer places order
2. Paid order appears on kitchen board
3. Kitchen accepts order
4. Kitchen starts preparing
5. Kitchen marks ready
6. Order appears on collection board as ready to dispatch
7. Cashier marks dispatched
8. Order becomes `out_for_delivery`
9. Cashier or manager marks delivered
10. Order becomes completed

## 15. Current Limitations

These are known and intentional for the current scope:

- no driver entity or driver assignment model
- no operational audit trail for note edits
- no per-role Django permission objects beyond group-name checks
- existing ungrouped staff users still inherit manager access
- no refund workflow in operations
- no split kitchen stations or station routing
- no printer or KDS integration
- no dine-in service model

## 16. Extension Guidance

If this system is extended for a larger restaurant model, keep these rules:

1. keep `apps.operations` as the owner of staff workflows
2. keep using named actions, not raw status strings, as the main UI contract
3. add new fulfilment states carefully and document each side effect
4. avoid pushing kitchen logic back into `apps.orders.views`
5. add role checks centrally in `apps.operations.permissions`

### Likely next extensions

- driver assignment model
- explicit refund and failed-handover actions
- operational timeline / audit log
- station-specific kitchen boards
- dine-in service actions such as `seat_order`, `fire_course`, `served`, `closed`

## 17. Setup Checklist

Before using this in a real environment:

1. run migrations
2. assign staff users to operations groups
3. verify board access by role
4. verify SMS and push settings
5. test one pickup order end-to-end
6. test one delivery order end-to-end
7. confirm no active staff users are missing an operations group
