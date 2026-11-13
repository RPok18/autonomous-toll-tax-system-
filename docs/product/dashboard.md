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

## Simulation demo data

Simulation runs remain offline by default. To explicitly write pass-level
simulation results to the dashboard's database, first seed the database and
rebuild/start the Compose services, then run from the repository root:

```powershell
docker compose up -d --build backend
docker compose exec backend python scripts/seed.py
docker compose exec backend python scripts/run_simulation.py --scenario S0,S3,S10 --passes 20 --seeds 42 --per-pass --persist-to-db --out-dir simulation_results/recording_demo
```

Refresh Transactions and Exceptions in the dashboard. Imported transactions
are marked with a `SIM-` lane and a `simulation_demo` applied rule; exception
details identify the scenario, seed, and pass. The import is idempotent for a
given plaza, scenario, seed, and pass number. These are synthetic simulation
records, not live sensor events or real toll charges. They use the simulator's
modeled amounts, are not linked to database vehicles or tariffs, and do not
change vehicle balances. When run inside Compose, report files are written in
the backend container at `/app/simulation_results/recording_demo`.
