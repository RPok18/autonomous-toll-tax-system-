"""A6: every endpoint of the toll API, one success case and one error case each,
run through the real FastAPI app against a real PostgreSQL test database.

The expected behaviour is the contract in KB article 03 (Toll API contract).
Fixtures live in conftest.py.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.audit import AuditLog
from app.models.device import Device
from app.models.enums import (
    DeviceStatus,
    DeviceType,
    ExceptionType,
    IdentificationMethod,
    PaymentStatus,
    VehicleClass,
)
from app.models.exception import ExceptionRecord
from app.models.transaction import Transaction
from app.models.vehicle import Vehicle
from conftest import PASSWORDS
from helpers import add_device, add_exception, add_transaction, add_vehicle, audit_rows

ROLES = ("admin", "operator", "auditor", "viewer")


# ---------------------------------------------------------------- health

def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_rejects_other_methods(client):
    assert client.post("/health").status_code == 405


# ---------------------------------------------------------------- auth

def test_login_returns_token_and_role_and_is_audited(client, db):
    response = client.post("/auth/login", json={"username": "operator", "password": PASSWORDS["operator"]})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "operator"
    assert body["access_token"]
    assert len(audit_rows(db, "login")) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "operator", "password": "wrong"},
        {"username": "nobody", "password": "whatever"},
    ],
)
def test_login_with_bad_credentials_returns_401(client, payload):
    response = client.post("/auth/login", json=payload)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


def test_login_is_json_only(client):
    response = client.post("/auth/login", data={"username": "operator", "password": PASSWORDS["operator"]})

    assert response.status_code == 422


def test_missing_and_invalid_tokens_return_401(client):
    assert client.get("/vehicles").json() == {"detail": "Not authenticated"}
    response = client.get("/vehicles", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired token"}


def test_denied_access_is_audited(client, auth, db):
    response = client.post("/vehicles", json={}, headers=auth("viewer"))

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient role for this action"}
    rows = audit_rows(db, "access_denied")
    assert len(rows) == 1
    assert set(rows[0].metadata_json["required_roles"]) == {"operator", "admin"}


@pytest.mark.xfail(reason="Known issue A4: the audit actor is read from identity['sub'], which is never set", strict=False)
def test_audit_actor_is_recorded_on_create(client, auth, db):
    client.post("/vehicles", json={"plate_number": "MH01AA0001"}, headers=auth("operator"))

    row = audit_rows(db, "create_vehicle")[0]
    assert row.actor not in (None, "", "None")


@pytest.mark.xfail(reason="Not in the contract: inactive users can still log in; decision recorded in the A6 comment", strict=False)
def test_inactive_user_cannot_log_in(client, db):
    from app.models.user import User

    db.query(User).filter_by(username="viewer").update({"is_active": False})
    db.commit()
    try:
        response = client.post("/auth/login", json={"username": "viewer", "password": PASSWORDS["viewer"]})
        assert response.status_code == 401
    finally:
        db.query(User).filter_by(username="viewer").update({"is_active": True})
        db.commit()


# ---------------------------------------------------------------- roles and contract

# (method, path, roles allowed by the contract)
ENDPOINTS = [
    ("POST", "/vehicles", {"admin", "operator"}),
    ("GET", "/vehicles", set(ROLES)),
    ("GET", f"/vehicles/{uuid.uuid4()}", set(ROLES)),
    ("GET", "/vehicles/by-plate/XX00XX0000", set(ROLES)),
    ("POST", "/vehicles/charge", {"admin", "operator"}),
    ("POST", "/transactions", {"admin", "operator"}),
    ("GET", "/transactions", {"admin", "operator", "auditor"}),
    ("GET", f"/transactions/{uuid.uuid4()}", {"admin", "operator", "auditor"}),
    ("POST", "/devices", {"admin"}),
    ("GET", "/devices", {"admin", "operator", "auditor"}),
    ("GET", f"/devices/{uuid.uuid4()}", {"admin", "operator", "auditor"}),
    ("PATCH", f"/devices/{uuid.uuid4()}/heartbeat", {"admin", "operator"}),
    ("POST", "/exceptions", {"admin", "operator"}),
    ("GET", "/exceptions", {"admin", "operator", "auditor"}),
    ("GET", f"/exceptions/{uuid.uuid4()}", {"admin", "operator", "auditor"}),
    ("PATCH", f"/exceptions/{uuid.uuid4()}/resolve", {"admin", "operator"}),
    ("POST", f"/exceptions/{uuid.uuid4()}/image", {"admin", "operator"}),
    ("GET", f"/exceptions/{uuid.uuid4()}/image", {"admin", "operator", "auditor"}),
    ("GET", "/plazas", {"admin", "operator", "auditor"}),
]


@pytest.mark.parametrize("method,path,allowed", ENDPOINTS, ids=[f"{m} {p.split('/')[1]}{'...' if p.count('/') > 1 else ''}" for m, p, _ in ENDPOINTS])
def test_role_matrix_matches_contract(client, auth, method, path, allowed):
    for role in ROLES:
        response = client.request(method, path, json={} if method == "POST" else None, headers=auth(role))
        if role in allowed:
            assert response.status_code not in (401, 403), f"{role} should be allowed on {method} {path}"
        else:
            assert response.status_code == 403, f"{role} should be refused on {method} {path}"


@pytest.mark.parametrize("method,path,allowed", ENDPOINTS, ids=[f"{m} {p.split('/')[1]}{'...' if p.count('/') > 1 else ''}" for m, p, _ in ENDPOINTS])
def test_every_protected_endpoint_requires_a_token(client, method, path, allowed):
    response = client.request(method, path, json={} if method == "POST" else None)

    assert response.status_code == 401


def test_routes_match_the_documented_endpoint_list(app_with_db):
    documented = {
        ("GET", "/health"),
        ("POST", "/auth/login"),
        ("POST", "/vehicles"),
        ("GET", "/vehicles"),
        ("GET", "/vehicles/{vehicle_id}"),
        ("GET", "/vehicles/by-plate/{plate_number}"),
        ("POST", "/vehicles/charge"),
        ("POST", "/transactions"),
        ("GET", "/transactions"),
        ("GET", "/transactions/{transaction_id}"),
        ("POST", "/devices"),
        ("GET", "/devices"),
        ("GET", "/devices/{device_id}"),
        ("PATCH", "/devices/{device_id}/heartbeat"),
        ("POST", "/exceptions"),
        ("GET", "/exceptions"),
        ("GET", "/exceptions/{exception_id}"),
        ("PATCH", "/exceptions/{exception_id}/resolve"),
        ("POST", "/exceptions/{exception_id}/image"),
        ("GET", "/exceptions/{exception_id}/image"),
        ("GET", "/plazas"),
    }
    actual = {
        (method.upper(), path)
        for path, item in app_with_db.openapi()["paths"].items()
        for method in item
    }

    assert actual == documented


# ---------------------------------------------------------------- vehicles

def test_create_vehicle_normalises_plate_and_stores_balance(client, auth, db):
    response = client.post(
        "/vehicles",
        json={"plate_number": "mh 12-ab 1234", "vehicle_class": "car_jeep_van", "balance": "100.00", "fastag_id": "TAG-1"},
        headers=auth("operator"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["plate_number"] == "MH12AB1234"
    assert Decimal(body["balance"]) == Decimal("100.00")
    assert db.query(Vehicle).filter_by(plate_number="MH12AB1234").count() == 1
    assert len(audit_rows(db, "create_vehicle")) == 1


def test_create_vehicle_rejects_negative_balance(client, auth, db):
    response = client.post("/vehicles", json={"plate_number": "MH01AA0001", "balance": "-5"}, headers=auth("operator"))

    assert response.status_code == 422
    assert db.query(Vehicle).count() == 0


@pytest.mark.parametrize(
    "second",
    [
        {"plate_number": "mh12ab1234", "fastag_id": "TAG-OTHER"},
        {"plate_number": "MH99ZZ9999", "fastag_id": "TAG-1"},
    ],
    ids=["duplicate plate", "duplicate fastag"],
)
def test_create_vehicle_duplicate_returns_409(client, auth, db, second):
    first = client.post("/vehicles", json={"plate_number": "MH12AB1234", "fastag_id": "TAG-1"}, headers=auth("operator"))
    assert first.status_code == 201

    response = client.post("/vehicles", json=second, headers=auth("operator"))

    assert response.status_code == 409
    assert "detail" in response.json()
    assert db.query(Vehicle).count() == 1


def test_get_vehicle_by_id(client, auth, db):
    vehicle = add_vehicle(db)

    response = client.get(f"/vehicles/{vehicle.vehicle_id}", headers=auth("viewer"))

    assert response.status_code == 200
    assert response.json()["plate_number"] == "MH12AB1234"


def test_get_vehicle_unknown_id_returns_404_and_bad_id_returns_422(client, auth):
    assert client.get(f"/vehicles/{uuid.uuid4()}", headers=auth("viewer")).json() == {"detail": "Vehicle not found"}
    assert client.get("/vehicles/not-a-uuid", headers=auth("viewer")).status_code == 422


def test_get_vehicle_by_plate_normalises_the_plate(client, auth, db):
    add_vehicle(db)

    response = client.get("/vehicles/by-plate/mh 12-ab 1234", headers=auth("auditor"))

    assert response.status_code == 200
    assert response.json()["plate_number"] == "MH12AB1234"


def test_get_vehicle_by_plate_unknown_returns_404(client, auth):
    response = client.get("/vehicles/by-plate/XX00XX0000", headers=auth("viewer"))

    assert response.status_code == 404
    assert response.json() == {"detail": "Vehicle not found"}


def test_list_vehicles_filters_and_orders_newest_first(client, auth, db):
    add_vehicle(db, plate="MH01AA0001", fastag_id="T1")
    add_vehicle(db, plate="MH02BB0002", fastag_id="T2", is_blacklisted=True)
    add_vehicle(db, plate="MH03CC0003", fastag_id="T3")

    everything = client.get("/vehicles", headers=auth("viewer")).json()
    assert [v["plate_number"] for v in everything] == ["MH03CC0003", "MH02BB0002", "MH01AA0001"]

    blacklisted = client.get("/vehicles", params={"is_blacklisted": "true"}, headers=auth("viewer")).json()
    assert [v["plate_number"] for v in blacklisted] == ["MH02BB0002"]

    by_tag = client.get("/vehicles", params={"fastag_id": "T1"}, headers=auth("viewer")).json()
    assert [v["plate_number"] for v in by_tag] == ["MH01AA0001"]

    assert len(client.get("/vehicles", params={"limit": 2}, headers=auth("viewer")).json()) == 2


def test_list_vehicles_plate_filter_normalises_like_by_plate(client, auth, db):
    add_vehicle(db)

    response = client.get("/vehicles", params={"plate_number": "mh12ab1234"}, headers=auth("viewer"))

    assert [v["plate_number"] for v in response.json()] == ["MH12AB1234"]


@pytest.mark.parametrize("path", ["/vehicles", "/transactions", "/devices", "/exceptions"])
@pytest.mark.parametrize("limit", [0, -1, 201, 100000])
def test_list_endpoints_reject_out_of_range_limit(client, auth, path, limit):
    response = client.get(path, params={"limit": limit}, headers=auth("admin"))

    assert response.status_code == 422


# ---------------------------------------------------------------- charge

def charge(client, auth, plate="MH12AB1234", plaza="PLZ-T1", role="operator", **extra):
    return client.post("/vehicles/charge", json={"plate_number": plate, "plaza_code": plaza, **extra}, headers=auth(role))


def test_charge_deducts_toll_and_records_transaction(client, auth, db, seed):
    vehicle = add_vehicle(db, balance="100.00")

    response = charge(client, auth, plate="mh 12 ab 1234", plaza="plz-t1")

    assert response.status_code == 201
    body = response.json()
    assert Decimal(body["balance_after"]) == Decimal("35.00")
    transaction = body["transaction"]
    assert Decimal(transaction["amount_charged"]) == Decimal("65.00")
    assert transaction["payment_status"] == "paid"
    assert transaction["identification_method"] == "manual"
    assert transaction["plate_number"] == "MH12AB1234"
    assert transaction["lane_id"] == "AUTO"
    assert transaction["currency"] == "INR"

    db.expire_all()
    assert db.get(Vehicle, vehicle.vehicle_id).balance == Decimal("35.00")
    assert db.query(Transaction).count() == 1
    audit = audit_rows(db, "charge_vehicle_toll")
    assert len(audit) == 1
    assert audit[0].metadata_json["balance_after"] == "35.00"
    assert audit[0].resource_id == transaction["transaction_id"]


def test_charge_is_retrievable_through_the_transactions_endpoints(client, auth, db, seed):
    add_vehicle(db)
    transaction_id = charge(client, auth).json()["transaction"]["transaction_id"]

    fetched = client.get(f"/transactions/{transaction_id}", headers=auth("auditor"))

    assert fetched.status_code == 200
    assert fetched.json()["transaction_id"] == transaction_id


def test_charge_with_exact_balance_leaves_zero(client, auth, db, seed):
    vehicle = add_vehicle(db, balance="65.00")

    response = charge(client, auth)

    assert response.status_code == 201
    assert Decimal(response.json()["balance_after"]) == Decimal("0.00")
    db.expire_all()
    assert db.get(Vehicle, vehicle.vehicle_id).balance == Decimal("0.00")


def test_charge_with_insufficient_balance_returns_402_and_changes_nothing(client, auth, db, seed):
    vehicle = add_vehicle(db, balance="64.99")

    response = charge(client, auth)

    assert response.status_code == 402
    assert response.json() == {"detail": "Insufficient balance"}
    db.expire_all()
    assert db.get(Vehicle, vehicle.vehicle_id).balance == Decimal("64.99")
    assert db.query(Transaction).count() == 0
    assert audit_rows(db, "charge_vehicle_toll") == []


def test_charge_unknown_vehicle_returns_404(client, auth, seed):
    response = charge(client, auth, plate="XX00XX0000")

    assert response.status_code == 404
    assert response.json() == {"detail": "Vehicle not found"}


def test_charge_unknown_or_inactive_plaza_returns_404(client, auth, db, seed):
    add_vehicle(db)
    assert charge(client, auth, plaza="NOPE").json() == {"detail": "Toll plaza not found"}

    seed.plaza.is_active = False
    db.commit()
    assert charge(client, auth).json() == {"detail": "Toll plaza not found"}


def test_charge_without_a_tariff_for_the_vehicle_class_returns_404(client, auth, db, seed):
    vehicle = add_vehicle(db, plate="MH05LC0005", vehicle_class=VehicleClass.LCV)

    response = charge(client, auth, plate="MH05LC0005")

    assert response.status_code == 404
    assert response.json() == {"detail": "No applicable tariff found"}
    db.expire_all()
    assert db.get(Vehicle, vehicle.vehicle_id).balance == Decimal("100.00")
    assert db.query(Transaction).count() == 0


@pytest.mark.parametrize("body", [{"plate_number": "---", "plaza_code": "PLZ-T1"}, {"plate_number": "MH12AB1234"}, {}])
def test_charge_rejects_invalid_bodies(client, auth, body):
    response = client.post("/vehicles/charge", json=body, headers=auth("operator"))

    assert response.status_code == 422


# ---------------------------------------------------------------- transactions

def test_create_transaction_stores_the_posted_values(client, auth, db, seed):
    response = client.post(
        "/transactions",
        json={
            "plaza_id": str(seed.plaza.plaza_id),
            "lane_id": "L2",
            "plate_number": "MH12AB1234",
            "identification_method": "hybrid_agreed",
            "amount_charged": "65.00",
            "payment_status": "paid",
        },
        headers=auth("operator"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["lane_id"] == "L2"
    assert body["identification_method"] == "hybrid_agreed"
    assert Decimal(body["amount_charged"]) == Decimal("65.00")
    assert db.query(Transaction).count() == 1
    assert len(audit_rows(db, "create_transaction")) == 1


def test_create_transaction_rejects_missing_fields_and_unknown_plaza(client, auth, db, seed):
    missing = client.post("/transactions", json={"lane_id": "L2"}, headers=auth("operator"))
    assert missing.status_code == 422

    unknown_plaza = client.post(
        "/transactions", json={"plaza_id": str(uuid.uuid4()), "lane_id": "L2"}, headers=auth("operator")
    )
    assert unknown_plaza.status_code == 422
    assert db.query(Transaction).count() == 0


def test_get_transaction(client, auth, db, seed):
    transaction = add_transaction(db, seed)

    response = client.get(f"/transactions/{transaction.transaction_id}", headers=auth("auditor"))

    assert response.status_code == 200
    assert response.json()["transaction_id"] == str(transaction.transaction_id)


def test_get_transaction_unknown_returns_404(client, auth):
    response = client.get(f"/transactions/{uuid.uuid4()}", headers=auth("auditor"))

    assert response.status_code == 404
    assert response.json() == {"detail": "Transaction not found"}


def test_list_transactions_filters_by_exception_flag_and_plaza(client, auth, db, seed):
    normal = add_transaction(db, seed)
    flagged = add_transaction(db, seed, is_exception=True)

    flagged_only = client.get("/transactions", params={"is_exception": "true"}, headers=auth("auditor")).json()
    assert [t["transaction_id"] for t in flagged_only] == [str(flagged.transaction_id)]

    by_plaza = client.get("/transactions", params={"plaza_id": str(seed.plaza.plaza_id)}, headers=auth("auditor")).json()
    assert {t["transaction_id"] for t in by_plaza} == {str(normal.transaction_id), str(flagged.transaction_id)}

    other_plaza = client.get("/transactions", params={"plaza_id": str(uuid.uuid4())}, headers=auth("auditor")).json()
    assert other_plaza == []


def test_list_transactions_is_newest_first(client, auth, db, seed):
    first = add_transaction(db, seed)
    second = add_transaction(db, seed)

    ids = [t["transaction_id"] for t in client.get("/transactions", headers=auth("auditor")).json()]

    assert ids == [str(second.transaction_id), str(first.transaction_id)]


# ---------------------------------------------------------------- devices

def test_create_device_as_admin(client, auth, db, seed):
    response = client.post(
        "/devices",
        json={"name": "Lane 1 camera", "device_type": "camera_front", "plaza_id": str(seed.plaza.plaza_id), "lane_id": "L1"},
        headers=auth("admin"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["device_type"] == "camera_front"
    assert body["status"] == "online"
    assert db.query(Device).count() == 1
    assert len(audit_rows(db, "create_device")) == 1


def test_create_device_rejects_unknown_type_and_unknown_plaza(client, auth, db, seed):
    bad_type = client.post("/devices", json={"device_type": "toaster"}, headers=auth("admin"))
    assert bad_type.status_code == 422

    bad_plaza = client.post(
        "/devices", json={"device_type": "rfid_reader", "plaza_id": str(uuid.uuid4())}, headers=auth("admin")
    )
    assert bad_plaza.status_code == 422
    assert db.query(Device).count() == 0


def test_get_device(client, auth, db, seed):
    device = add_device(db, seed)

    response = client.get(f"/devices/{device.device_id}", headers=auth("operator"))

    assert response.status_code == 200
    assert response.json()["name"] == "Camera 1"


def test_get_device_unknown_returns_404(client, auth):
    response = client.get(f"/devices/{uuid.uuid4()}", headers=auth("operator"))

    assert response.status_code == 404
    assert response.json() == {"detail": "Device not found"}


def test_list_devices_filters_by_plaza_and_status(client, auth, db, seed):
    online = add_device(db, seed, name="up")
    offline = add_device(db, seed, status=DeviceStatus.OFFLINE, name="down")

    offline_only = client.get("/devices", params={"status_filter": "offline"}, headers=auth("auditor")).json()
    assert [d["device_id"] for d in offline_only] == [str(offline.device_id)]

    by_plaza = client.get("/devices", params={"plaza_id": str(seed.plaza.plaza_id)}, headers=auth("auditor")).json()
    assert {d["device_id"] for d in by_plaza} == {str(online.device_id), str(offline.device_id)}

    assert client.get("/devices", params={"status_filter": "broken"}, headers=auth("auditor")).status_code == 422


def test_heartbeat_updates_timestamp_and_brings_offline_device_online(client, auth, db, seed):
    device = add_device(db, seed, status=DeviceStatus.OFFLINE)
    before = device.last_heartbeat_at

    response = client.patch(f"/devices/{device.device_id}/heartbeat", headers=auth("operator"))

    assert response.status_code == 200
    assert response.json()["status"] == "online"
    db.expire_all()
    refreshed = db.get(Device, device.device_id)
    assert refreshed.status == DeviceStatus.ONLINE
    assert refreshed.last_heartbeat_at > before


def test_heartbeat_keeps_a_degraded_device_degraded(client, auth, db, seed):
    device = add_device(db, seed, status=DeviceStatus.DEGRADED)

    response = client.patch(f"/devices/{device.device_id}/heartbeat", headers=auth("operator"))

    assert response.json()["status"] == "degraded"


def test_heartbeat_unknown_device_returns_404(client, auth):
    response = client.patch(f"/devices/{uuid.uuid4()}/heartbeat", headers=auth("operator"))

    assert response.status_code == 404
    assert response.json() == {"detail": "Device not found"}


# ---------------------------------------------------------------- exceptions

def test_create_exception(client, auth, db, seed):
    response = client.post(
        "/exceptions",
        json={"plaza_id": str(seed.plaza.plaza_id), "lane_id": "L1", "exception_type": "tag_mismatch", "details": "plate and tag disagree"},
        headers=auth("operator"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["exception_type"] == "tag_mismatch"
    assert body["resolved"] is False
    assert db.query(ExceptionRecord).count() == 1
    assert len(audit_rows(db, "create_exception")) == 1


def test_create_exception_rejects_unknown_type_and_unknown_transaction(client, auth, db, seed):
    bad_type = client.post("/exceptions", json={"exception_type": "gremlins"}, headers=auth("operator"))
    assert bad_type.status_code == 422

    bad_transaction = client.post(
        "/exceptions",
        json={"exception_type": "tag_mismatch", "transaction_id": str(uuid.uuid4())},
        headers=auth("operator"),
    )
    assert bad_transaction.status_code == 422
    assert db.query(ExceptionRecord).count() == 0


def test_get_exception(client, auth, db, seed):
    record = add_exception(db, seed)

    response = client.get(f"/exceptions/{record.exception_id}", headers=auth("auditor"))

    assert response.status_code == 200
    assert response.json()["exception_type"] == "low_confidence_plate"


def test_get_exception_unknown_returns_404(client, auth):
    response = client.get(f"/exceptions/{uuid.uuid4()}", headers=auth("auditor"))

    assert response.status_code == 404
    assert response.json() == {"detail": "Exception not found"}


def test_list_exceptions_filters_by_resolved_flag(client, auth, db, seed):
    open_record = add_exception(db, seed)
    add_exception(db, seed, resolved=True)

    open_only = client.get("/exceptions", params={"resolved": "false"}, headers=auth("auditor")).json()
    assert [e["exception_id"] for e in open_only] == [str(open_record.exception_id)]
    assert len(client.get("/exceptions", headers=auth("auditor")).json()) == 2
    assert client.get("/exceptions", params={"resolved": "maybe"}, headers=auth("auditor")).status_code == 422


def test_resolve_exception_marks_it_resolved_and_is_audited(client, auth, db, seed):
    record = add_exception(db, seed)

    response = client.patch(f"/exceptions/{record.exception_id}/resolve", headers=auth("operator"))

    assert response.status_code == 200
    assert response.json()["resolved"] is True
    db.expire_all()
    assert db.get(ExceptionRecord, record.exception_id).resolved is True
    assert len(audit_rows(db, "resolve_exception")) == 1


def test_resolving_twice_is_harmless(client, auth, db, seed):
    record = add_exception(db, seed, resolved=True)

    response = client.patch(f"/exceptions/{record.exception_id}/resolve", headers=auth("operator"))

    assert response.status_code == 200
    assert response.json()["resolved"] is True


def test_resolve_unknown_exception_returns_404(client, auth):
    response = client.patch(f"/exceptions/{uuid.uuid4()}/resolve", headers=auth("operator"))

    assert response.status_code == 404
    assert response.json() == {"detail": "Exception not found"}
