# Autonomous Toll Tax System

A toll system that identifies a vehicle by its number plate (ANPR) and RFID tag, works out the toll
for the plaza and vehicle class, and deducts it from the vehicle's balance. The backend is a FastAPI
service on PostgreSQL. The accuracy of the identification and the correctness of the charges are
measured with a simulation harness.

## Repository layout

| Path | What it holds |
| --- | --- |
| `backend/app/api/` | REST endpoints: auth, vehicles (including the toll charge), transactions, devices, exceptions, plazas |
| `backend/app/anpr/`, `rfid/`, `fusion/` | Plate recognition, RFID reading and the engine that combines both signals |
| `backend/app/policy/`, `toll/` | Vehicle class rules and the toll calculator |
| `backend/app/models/`, `schemas/` | SQLAlchemy tables and Pydantic request and response models |
| `backend/app/simulation/`, `backend/scripts/run_simulation.py` | Simulation scenarios, metrics and CSV export |
| `backend/alembic/` | Database migrations (the schema is changed only through these) |
| `backend/dashboard/` | Dashboard web pages (HTML, CSS, JavaScript) |
| `backend/tests/` | Automated tests |
| `docker-compose.yml` | PostgreSQL 16 for local development |

## Run it locally

You need Python 3.13 or newer (tested on 3.13 and 3.14) and Docker.

1. Create a `.env` file in the repository root with `POSTGRES_USER`, `POSTGRES_PASSWORD` and
   `POSTGRES_DB`, and a `DATABASE_URL` that matches them. **Never commit `.env`.**
2. Start the database: `docker compose up -d`
3. From the `backend` folder, install the dependencies: `pip install -r requirements.txt`
4. Create the tables: `alembic upgrade head`
5. Optional demo data: `python scripts/seed.py`
6. Start the API: `uvicorn main:app --reload` and open `http://localhost:8000/docs`

## Run the tests

From the `backend` folder:

```
python -m pytest tests
```

The API tests use a real PostgreSQL database named after the development one plus `_test`
(for example `toll_system_test`). They create it if it is missing, rebuild it from the migrations
and empty it before every test, so they never touch the development data. They refuse to run
against a database whose name does not end in `_test`. Without a reachable PostgreSQL server they
are skipped. Set `TEST_DATABASE_URL` to use a different test database.

## Git workflow

The project follows the course "PM and Git student guide". Work is organised in three kinds of branch.

| Branch | Purpose | Rules |
| --- | --- | --- |
| `main` | The checked release | Receives changes only from `develop`, after the checks pass. Never commit to it directly. |
| `develop` | The next release | Receives finished feature branches. Never commit to it directly. |
| `feature/<TASK-ID>-short-name` | One task | Cut from `develop`, one branch per PM task, deleted after the merge. |

The task ID is the Kreo PM card number, so a branch name always leads back to its task. Example for
task RISHA-21: `feature/RISHA-21-api-endpoint-tests`. Use your own task ID and write the name
without angle brackets.

### One-time setup

Create `develop` from `main` if it does not exist yet:

```
git checkout main
git pull
git checkout -b develop
git push -u origin develop
```

### Working on a task

1. Start from an up-to-date `develop` and create the feature branch:

   ```
   git checkout develop
   git pull
   git checkout -b feature/RISHA-21-api-endpoint-tests
   ```

2. Commit in small steps (format below). Unrelated changes go into separate commits.

   ```
   git add backend/tests/test_api_endpoints.py
   git commit
   ```

3. Push the branch:

   ```
   git push -u origin feature/RISHA-21-api-endpoint-tests
   ```

4. Merge into `develop` and test there:

   ```
   git checkout develop
   git pull
   git merge feature/RISHA-21-api-endpoint-tests
   cd backend
   python -m pytest tests
   cd ..
   git push
   ```

5. When `develop` is green, promote it to `main`:

   ```
   git checkout main
   git pull
   git merge develop
   git push
   ```

6. Delete the finished branch and add the commit links to the PM task:

   ```
   git branch -d feature/RISHA-21-api-endpoint-tests
   git push origin --delete feature/RISHA-21-api-endpoint-tests
   ```

Pull requests are not required in this course. If the merge into `develop` or the tests fail, fix the
problem on the feature branch (or a new one), not on `develop` or `main`.

### Commit messages

A commit message has a title line, a blank line and a body.

```
RISHA-21 Add API tests for every endpoint

The toll API had unit tests with a fake session only, so nothing proved
the endpoints work against PostgreSQL. These tests run the real app
against a real test database and cover the contract in article 03.

- Add a success and an error test for each of the 20 routes
- Add a role matrix test that checks the allowed roles of every endpoint
- Add concurrent charge tests that check a balance never goes below zero

Task: RISHA-21
```

* **Title:** the task ID, then an action-based summary written as a command ("Add", "Remove",
  "Change", "Move"). Keep it short. Avoid vague words such as "fix", "update", "final" or "stuff"
  on their own.
* **Body:** first a paragraph on why the change was needed, then a bullet list of what changed,
  then the task reference.
* **Split commits:** one logical change per commit. Do not put a refactor, a feature and a
  documentation change into the same commit just because they belong to one task.
* **In PowerShell** a multi-line message is easiest in the editor (`git commit` without `-m`) or
  from a file: `git commit -F message.txt` (do not add that file to the commit).

### Rules that apply to every commit

* Never commit `.env`, passwords, tokens or personal data. If a secret is committed by mistake,
  change it first, then remove it from the history.
* Do not commit generated files: `__pycache__`, `.pytest_cache`, per-pass simulation CSVs.
* Run the tests before every merge into `develop`.
* Paste the commit links into the comment of the PM task, together with what the commit proves.

## Simulation results for the report

The simulation harness (scenarios and metrics: knowledge base article 04) runs from the `backend`
folder and writes CSV files:

```
python scripts/run_simulation.py --scenario all --passes 10000 --seeds 1-5 --out-dir simulation_results
```

| File | Content |
| --- | --- |
| `metrics_summary.csv` | One row per scenario with the four metrics: correct identification rate, toll-deduction correctness, latency (p50 and p95) and exception rate |
| `summary_by_scenario.csv`, `summary.csv` | All metrics, averaged over seeds and per seed |
| `passes_<scenario>_seed<n>.csv` | One row per vehicle pass (written when the run has at most 100000 passes; force with `--per-pass`, skip with `--no-per-pass`) |

A run with `--passes 0` is not an error: it writes the headers and a summary of zeros.

## Dashboard

A read-mostly web dashboard with a Transactions view and an Exceptions view (design: knowledge base
article 08). It is plain HTML, CSS and JavaScript in `backend/dashboard/` (no build step) and is served
by the API itself:

1. Start the API as above and open `http://localhost:8000/dashboard/`
2. Sign in with an admin, operator or auditor user. The viewer role is shown a "no access" page.

The dashboard only calls the public API: `GET /plazas`, `GET /transactions`, `GET /exceptions`,
`PATCH /exceptions/{id}/resolve` and the plate image endpoints. The list endpoints take `limit`,
`offset` and filters, and return the number of matching rows in the `X-Total-Count` header. Resolve
and image upload are shown to admin and operator only. The page refreshes every 30 seconds.

## Data retention and plate images

Decision record 07 in the knowledge base sets how long data is kept and who can see plate images.

| Data | Kept | Then |
| --- | --- | --- |
| Plate image of an exception | 7 days after the exception is resolved | File deleted |
| Transactions | 12 months | Plate number, tag ID, vehicle and trip link removed; amount, plaza and time stay |
| Resolved exceptions | 12 months | Transaction link and free text removed |
| Audit log | 12 months | Entries deleted |

Images exist only for exceptions (`POST /exceptions/{id}/image`, roles admin and operator). They can be
read with `GET /exceptions/{id}/image` by admin, operator and auditor; the viewer role gets 403. Every
view is written to the audit log. Files are stored under `media/plate_captures` (not committed); change
the folder with `PLATE_IMAGE_DIR`. The periods are the settings `anpr_image_retention_days` (7) and
`record_retention_days` (365).

Run the clean-up from the `backend` folder, first as a dry run, and schedule it once a day
(Task Scheduler on Windows, cron on Linux):

```
python scripts/run_retention.py --dry-run
python scripts/run_retention.py
```

## Documentation

The knowledge base holds the detailed articles: database schema, Toll API contract, simulation
scenarios and metrics, and the component diagram. This README only covers how to run the project
and how to work with Git.
