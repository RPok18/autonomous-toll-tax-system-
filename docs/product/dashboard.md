# Operations dashboard

The FastAPI application serves the read-mostly operations dashboard at `/dashboard/`.
Open `http://localhost:8000/dashboard/` after starting the backend. Sign in with an
admin, operator, or auditor account; API role checks remain authoritative for all
data and actions.

The Transactions view supports plaza, payment status, exception, date, and transaction
filters, paging, and pass details. The Exceptions view supports status, plaza, type,
and linked transaction filters. Admins and operators can resolve exceptions. Plate-image
upload and viewing are not included in this dashboard iteration.

The dashboard refreshes its current view every 30 seconds and uses the existing API.
List endpoints provide pagination totals through the `X-Total-Count` response header.
