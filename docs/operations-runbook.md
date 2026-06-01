# Operations Runbook

This runbook is for the people operating the order boards day to day.

Use it for:
- assigning staff access
- understanding which board to use
- handling pickup and delivery orders
- troubleshooting common operations-side problems

For implementation detail, see [operations-order-board.md](operations-order-board.md).

## 1. Boards at a Glance

### Kitchen board

URL:
- `/ops/orders/kitchen/`

Use this board to:
- accept paid orders
- start preparing
- mark orders ready

Primary users:
- kitchen staff
- operations managers

### Collection board

URL:
- `/ops/orders/collection/`

Use this board to:
- hand off pickup orders
- dispatch delivery orders
- complete pickup and delivery handovers

Primary users:
- cashier / front counter staff
- operations managers

## 2. Staff Group Setup

Assign staff users to one of these Django groups:

- `Operations Manager`
- `Operations Kitchen`
- `Operations Cashier`

### Where to assign them

Use Django admin:

1. open `/admin/`
2. open `Users`
3. open the staff user
4. add the correct operations group
5. save

### Explicit role behavior

Staff users must be in an operations group before they can access an operations board.

Existing ungrouped staff users are assigned to `Operations Manager` by migration during the hardening rollout. New staff users must be assigned deliberately.

## 3. Standard Pickup Flow

### Kitchen

1. open the kitchen board
2. find the paid order in `Confirmed`
3. click `Accept Order` if needed
4. click `Start Preparing`
5. when finished, click `Mark Ready`

### Cashier / front counter

1. open the collection board
2. find the order in `Ready`
3. confirm the order number with the customer
4. optionally add handover notes
5. click `Mark Collected`

Result:
- order becomes `Completed`
- `collected_at` and `completed_at` are recorded

## 4. Standard Delivery Flow

### Kitchen

1. open the kitchen board
2. accept the order
3. start preparing
4. mark it ready when packed

At this point the order is ready to leave the shop, but it is not yet marked as on the road.

### Cashier / front counter

1. open the collection board
2. find the delivery order in `Ready`
3. add dispatch handover notes if needed
4. click `Mark Dispatched`

Result:
- order becomes `Out for Delivery`
- `dispatched_at` is recorded
- customer dispatch notifications are sent

### Delivery completion

When the order is confirmed delivered:

1. open the collection board
2. find the order in `Out for Delivery`
3. click `Mark Delivered`

Result:
- order becomes `Completed`
- `delivered_at` and `completed_at` are recorded

## 5. Using Notes Properly

### Kitchen Notes

Use for preparation-only context:
- allergy handling
- item substitutions
- remake requirements
- cooking instructions

### Handover Notes

Use for dispatch or collection context:
- collected by someone else
- driver name or vehicle note
- bag count or missing item follow-up
- special handoff instruction

### Cancel Reason

If a manager cancels an order:
- the cancel reason must be filled in

Do not leave cancellation unexplained. That makes support and payment follow-up harder.

## 6. What Each Role Can Do

### Kitchen

Can:
- view kitchen board
- accept orders
- start preparing
- mark ready
- save notes

Cannot:
- access collection board
- dispatch delivery orders
- complete handovers
- cancel orders

### Cashier

Can:
- view collection board
- dispatch delivery orders
- mark pickup orders collected
- mark delivery orders delivered
- save notes

Cannot:
- access kitchen board
- accept orders
- start preparing
- mark ready
- cancel orders

### Manager

Can:
- access both boards
- perform all actions
- cancel orders
- save notes

## 7. Common Checks

### Order is on the kitchen board but cannot be accepted

Check:
- payment status is actually `Paid`
- order is not still awaiting payment

The current workflow only allows `Accept Order` for paid pending orders.

### Delivery order is ready but not yet on the way

That is expected.

Meaning:
- kitchen has finished the order
- front counter has not dispatched it yet

The next step is on the collection board:
- `Mark Dispatched`

### Cashier cannot see the collection board

Check:
- user is `is_staff=True`
- user belongs to `Operations Cashier` or `Operations Manager`

### Kitchen cannot see the kitchen board

Check:
- user is `is_staff=True`
- user belongs to `Operations Kitchen` or `Operations Manager`

### Board says refresh failed

Check:
- device network connection
- whether the staff session expired
- server logs for `403`, `500`, or database errors

Use the board's Refresh button after fixing the connection or login state.

### Action says order changed

Another staff member already changed the order. Refresh the board and continue from the latest status.

### Order was cancelled but there is no explanation

This should not happen through the current operations UI.

Check:
- whether the order was changed in admin or shell
- whether a legacy endpoint or manual update bypassed the action flow

## 8. Recommended Shift Handover Rules

Use these rules consistently:

1. kitchen owns production states up to `Ready`
2. cashier owns collection and dispatch handoff
3. delivery completion should be recorded the same day
4. every cancellation should include a reason
5. every handoff issue should be captured in notes

## 9. Admin / Manager Checklist

At opening:

1. confirm staff users are assigned to the correct groups
2. confirm one kitchen user can access `/ops/orders/kitchen/`
3. confirm one cashier user can access `/ops/orders/collection/`
4. confirm the boards are auto-refreshing

During service:

1. watch for orders stuck in `pending`
2. watch for orders stuck in `ready`
3. review any cancellation reasons
4. review handover notes for repeated issues

At close:

1. confirm no active orders remain unintentionally
2. review completed deliveries if any are still marked `out_for_delivery`
3. resolve any orders with missing operational notes after incidents

## 10. Debugging Commands

Use these commands from the project root:

```bash
./venv/bin/python manage.py check
./venv/bin/python manage.py test apps.operations.tests apps.orders.tests
./venv/bin/python manage.py shell
```

Useful shell checks:

```python
from apps.orders.models import Order
Order.objects.filter(status="out_for_delivery").values("order_number", "customer_name", "updated_at")
```

```python
from django.contrib.auth.models import User, Group
Group.objects.filter(name__startswith="Operations").values_list("name", flat=True)
```

## 11. Current Known Limits

This is still a takeaway and delivery operations system, not a full restaurant floor-management system.

It does not yet include:
- driver assignment
- table service
- course firing
- split bills
- waiter workflow
- printer routing
- note history audit trail

Those should be added into `apps.operations` as new action flows, not by bypassing the current action service.
