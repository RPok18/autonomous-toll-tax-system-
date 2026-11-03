# A1 API verification evidence

## Result

Added request-level tests in `backend/tests/test_api_contract.py` for all 19
registered route operations: one success case and one error case per operation.
The tests exercise the FastAPI request parsing, dependency wiring, response
serialization, and status codes.

The suite also sends two concurrent toll-charge requests for a vehicle with
exactly one toll's balance. It verifies that one request succeeds, the other
returns insufficient balance, the balance ends at zero, and both requests go
through the endpoint's row-lock path.

## Evidence and test scope

Run from the repository root:

```text
python -m pytest backend\tests\test_api_contract.py backend\tests\test_transaction_history_endpoints.py backend\tests\test_vehicle_toll_endpoints.py -q --tb=short
```

Result: **48 passed** (39 new contract cases and 9 existing API tests).

The endpoint tests use a request-level `TestClient` with a fake database
session. The concurrent charge case verifies that both requests use the
endpoint's `with_for_update()` path and models the serialization provided by a
database row lock. It does not validate PostgreSQL's actual transaction and
locking behavior. A PostgreSQL-backed integration test remains necessary to
establish that guarantee against the configured production database.

The health route has no request input that can produce an application error;
its error case is a `405 Method Not Allowed` request using `POST` on the same
path.

## A1 specification status and decision

No A1 specification document was found in the repository, and the linked
GitHub repository currently has no issues containing that specification.
Therefore these tests verify the currently implemented FastAPI routes and
schemas, but cannot establish conformance to an unavailable external A1
contract.

**Decision:** use the implementation's OpenAPI-visible routes, request and
response schemas, and HTTP status behavior as the provisional test baseline.
Do not invent or silently change requirements. Keep A1 conformance unresolved
until the normative A1 specification is linked or added; when available,
compare it against this test suite and record any remaining deviations with a
specific decision.

The full backend suite was also run: **71 passed, 3 failed**. The failures are
in existing fusion-settings tests (`Settings` lacks `rfid_min_confidence`, and
the tested `fusion_mode` setting is not applied by `FusionEngine`); neither
failure is in the API files changed for this task.
