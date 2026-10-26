"""Dashboard API filtering, pagination, authorization, and static asset coverage."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.enums import ExceptionType, IdentificationMethod, PaymentStatus
from app.models.exception import ExceptionRecord
from app.models.transaction import Transaction
from helpers import add_exception

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def tx(db, seed, *, days_ago=0, status=PaymentStatus.PAID, is_exception=False):
    row = Transaction(
        plaza_id=seed.plaza.plaza_id,
        lane_id="L1",
        plate_number="MH12AB1234",
        identification_method=IdentificationMethod.ANPR_ONLY,
        amount_charged=Decimal("65.00"),
        payment_status=status,
        is_exception=is_exception,
        transaction_time=NOW - timedelta(days=days_ago),
    )
    db.add(row)
    db.commit()
    return row


def test_plaza_list_returns_code_and_name(client, auth, seed):
    response = client.get("/plazas", headers=auth("auditor"))
    assert response.status_code == 200
    assert response.json() == [{
        "plaza_id": str(seed.plaza.plaza_id),
        "plaza_code": seed.plaza.plaza_code,
        "name": seed.plaza.name,
        "state_code": "MH",
        "num_lanes": 2,
        "is_active": True,
    }]


def test_plaza_list_requires_dashboard_role(client, auth):
    assert client.get("/plazas", headers=auth("viewer")).status_code == 403


def test_transaction_list_reports_total_and_pages(client, auth, db, seed):
    for i in range(5):
        tx(db, seed, days_ago=i)
    first = client.get("/transactions?limit=2", headers=auth("operator"))
    second = client.get("/transactions?limit=2&offset=2", headers=auth("operator"))
    last = client.get("/transactions?limit=2&offset=4", headers=auth("operator"))
    assert first.headers["x-total-count"] == "5"
    times = [r["transaction_time"] for r in first.json() + second.json() + last.json()]
    assert len(times) == 5 and times == sorted(times, reverse=True)
    assert len(last.json()) == 1


def test_transaction_filter_total_and_date_range(client, auth, db, seed):
    tx(db, seed, days_ago=3)
    tx(db, seed, days_ago=1, status=PaymentStatus.FAILED)
    tx(db, seed)
    response = client.get(
        "/transactions",
        params={
            "payment_status": "failed",
            "from": (NOW - timedelta(days=1)).isoformat(),
            "to": NOW.isoformat(),
        },
        headers=auth("operator"),
    )
    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert [r["payment_status"] for r in response.json()] == ["failed"]


@pytest.mark.parametrize("query", ["payment_status=nonsense", "offset=-1", "from=not-a-date"])
def test_transaction_list_rejects_bad_filters(client, auth, query):
    assert client.get("/transactions?" + query, headers=auth("operator")).status_code == 422


def test_transaction_list_can_filter_one_transaction(client, auth, db, seed):
    expected = tx(db, seed)
    tx(db, seed, days_ago=1)
    response = client.get(
        "/transactions",
        params={"transaction_id": str(expected.transaction_id)},
        headers=auth("operator"),
    )
    assert response.headers["x-total-count"] == "1"
    assert [row["transaction_id"] for row in response.json()] == [str(expected.transaction_id)]


def test_exception_list_filters_by_transaction_and_type(client, auth, db, seed):
    transaction = tx(db, seed, is_exception=True)
    linked = ExceptionRecord(
        plaza_id=seed.plaza.plaza_id,
        lane_id="L1",
        exception_type=ExceptionType.TAG_MISMATCH,
        transaction_id=transaction.transaction_id,
    )
    db.add(linked)
    db.commit()
    add_exception(db, seed, exception_type=ExceptionType.LOW_CONFIDENCE_PLATE)
    by_transaction = client.get(
        f"/exceptions?transaction_id={transaction.transaction_id}", headers=auth("auditor")
    )
    by_type = client.get(
        "/exceptions?exception_type=low_confidence_plate", headers=auth("auditor")
    )
    unknown = client.get(f"/exceptions?transaction_id={uuid.uuid4()}", headers=auth("auditor"))
    assert [r["exception_id"] for r in by_transaction.json()] == [str(linked.exception_id)]
    assert [r["exception_type"] for r in by_type.json()] == ["low_confidence_plate"]
    assert unknown.json() == [] and unknown.headers["x-total-count"] == "0"


def test_exception_list_reports_total_and_pages(client, auth, db, seed):
    for _ in range(3):
        add_exception(db, seed)
    add_exception(db, seed, resolved=True)
    response = client.get("/exceptions?resolved=false&limit=2", headers=auth("operator"))
    rest = client.get("/exceptions?resolved=false&limit=2&offset=2", headers=auth("operator"))
    assert response.headers["x-total-count"] == "3"
    assert len(response.json()) == 2 and len(rest.json()) == 1


def test_exception_list_rejects_unknown_type(client, auth):
    assert client.get(
        "/exceptions?exception_type=nonsense", headers=auth("operator")
    ).status_code == 422


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("/dashboard/", "text/html"),
        ("/dashboard/app.js", "javascript"),
        ("/dashboard/style.css", "text/css"),
    ],
)
def test_dashboard_files_are_served_without_a_token(client, path, kind):
    response = client.get(path)
    assert response.status_code == 200
    assert kind in response.headers["content-type"]


def test_dashboard_page_contains_no_inline_credentials(client):
    html = client.get("/dashboard/").text
    assert "Bearer" not in html and "password" not in html.lower()
