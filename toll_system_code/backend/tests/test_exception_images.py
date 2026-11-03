"""Plate images of exceptions (decision record 07): who may upload and view them, and what is stored.

Needs the PostgreSQL test database from conftest.py. Images go to a temporary folder.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.models.audit import AuditLog
from app.models.exception import ExceptionRecord
from app.models.enums import ExceptionType
from app.models.user import User
from helpers import add_exception, audit_rows

JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-body"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"


@pytest.fixture()
def image_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "plate_image_dir", str(tmp_path))
    return tmp_path


def upload(client, auth, exception_id, data=JPEG, role="operator", name="plate.jpg", content_type="image/jpeg"):
    return client.post(
        f"/exceptions/{exception_id}/image",
        files={"file": (name, data, content_type)},
        headers=auth(role),
    )


def user_id(db, username) -> str:
    return str(db.query(User).filter_by(username=username).one().user_id)


def stored_files(image_dir):
    return sorted(p.name for p in image_dir.iterdir())


# ---------------------------------------------------------------- upload

def test_upload_stores_the_image_and_is_audited(client, auth, db, seed, image_dir):
    record = add_exception(db, seed)

    response = upload(client, auth, record.exception_id)

    assert response.status_code == 201
    body = response.json()
    assert body["has_image"] is True
    assert "image_path" not in body  # the server-side file name is never exposed
    files = stored_files(image_dir)
    assert len(files) == 1 and files[0].endswith(".jpg")
    assert (image_dir / files[0]).read_bytes() == JPEG
    rows = audit_rows(db, "upload_plate_image")
    assert len(rows) == 1
    assert rows[0].actor == user_id(db, "operator")
    assert rows[0].resource_id == str(record.exception_id)


def test_png_is_accepted_and_the_type_comes_from_the_bytes(client, auth, db, seed, image_dir):
    record = add_exception(db, seed)

    response = upload(client, auth, record.exception_id, data=PNG, name="x.jpg", content_type="image/jpeg")

    assert response.status_code == 201
    assert stored_files(image_dir)[0].endswith(".png")


def test_a_file_that_is_not_an_image_is_refused_whatever_the_client_says(client, auth, db, seed, image_dir):
    record = add_exception(db, seed)

    response = upload(client, auth, record.exception_id, data=b"<?php echo 1; ?>", name="plate.jpg", content_type="image/jpeg")

    assert response.status_code == 415
    assert stored_files(image_dir) == []
    db.expire_all()
    assert db.get(ExceptionRecord, record.exception_id).image_path is None


def test_a_too_large_image_is_refused(client, auth, db, seed, image_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_plate_image_bytes", 10)
    record = add_exception(db, seed)

    response = upload(client, auth, record.exception_id)

    assert response.status_code == 413
    assert stored_files(image_dir) == []


def test_only_open_exceptions_get_images(client, auth, db, seed, image_dir):
    resolved = add_exception(db, seed, resolved=True)

    response = upload(client, auth, resolved.exception_id)

    assert response.status_code == 409
    assert stored_files(image_dir) == []


def test_upload_to_unknown_exception_returns_404(client, auth, image_dir):
    assert upload(client, auth, uuid.uuid4()).status_code == 404


def test_a_new_upload_replaces_and_deletes_the_old_file(client, auth, db, seed, image_dir):
    record = add_exception(db, seed)
    upload(client, auth, record.exception_id)
    first = stored_files(image_dir)

    upload(client, auth, record.exception_id, data=PNG)

    second = stored_files(image_dir)
    assert len(second) == 1 and second != first


@pytest.mark.parametrize("role", ["auditor", "viewer"])
def test_roles_that_may_not_upload_get_403(client, auth, db, seed, image_dir, role):
    record = add_exception(db, seed)

    response = upload(client, auth, record.exception_id, role=role)

    assert response.status_code == 403
    assert stored_files(image_dir) == []


# ---------------------------------------------------------------- view

@pytest.mark.parametrize("role", ["admin", "operator", "auditor"])
def test_allowed_roles_see_the_image_and_each_view_is_audited(client, auth, db, seed, image_dir, role):
    record = add_exception(db, seed)
    upload(client, auth, record.exception_id, data=PNG)

    response = client.get(f"/exceptions/{record.exception_id}/image", headers=auth(role))

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    rows = audit_rows(db, "view_plate_image")
    assert len(rows) == 1
    assert rows[0].actor == user_id(db, role)
    assert rows[0].resource_id == str(record.exception_id)


def test_the_viewer_role_cannot_see_images_and_the_refusal_is_audited(client, auth, db, seed, image_dir):
    record = add_exception(db, seed)
    upload(client, auth, record.exception_id)

    response = client.get(f"/exceptions/{record.exception_id}/image", headers=auth("viewer"))

    assert response.status_code == 403
    assert response.content != JPEG
    assert audit_rows(db, "view_plate_image") == []
    assert len(audit_rows(db, "access_denied")) == 1


def test_no_token_means_no_image(client, db, seed, image_dir):
    record = add_exception(db, seed)

    assert client.get(f"/exceptions/{record.exception_id}/image").status_code == 401


def test_exception_without_an_image_returns_404_and_is_not_audited(client, auth, db, seed, image_dir):
    record = add_exception(db, seed)

    response = client.get(f"/exceptions/{record.exception_id}/image", headers=auth("operator"))

    assert response.status_code == 404
    assert response.json() == {"detail": "Image not found"}
    assert audit_rows(db, "view_plate_image") == []


def test_unknown_exception_returns_404(client, auth, image_dir):
    response = client.get(f"/exceptions/{uuid.uuid4()}/image", headers=auth("operator"))

    assert response.status_code == 404
    assert response.json() == {"detail": "Exception not found"}


def test_a_missing_file_returns_404(client, auth, db, seed, image_dir):
    record = add_exception(db, seed)
    upload(client, auth, record.exception_id)
    for path in image_dir.iterdir():
        path.unlink()

    assert client.get(f"/exceptions/{record.exception_id}/image", headers=auth("operator")).status_code == 404


@pytest.mark.parametrize("bad_name", ["../secret.jpg", "/etc/passwd", "plate.jpg", "A" * 32 + ".jpg"])
def test_a_stored_name_that_is_not_server_generated_is_never_served(client, auth, db, seed, image_dir, bad_name):
    (image_dir / "plate.jpg").write_bytes(JPEG)
    record = add_exception(db, seed)
    record.image_path = bad_name
    db.commit()

    assert client.get(f"/exceptions/{record.exception_id}/image", headers=auth("admin")).status_code == 404


# ---------------------------------------------------------------- resolved_at

def test_resolving_sets_resolved_at_once(client, auth, db, seed):
    record = add_exception(db, seed)

    first = client.patch(f"/exceptions/{record.exception_id}/resolve", headers=auth("operator")).json()
    second = client.patch(f"/exceptions/{record.exception_id}/resolve", headers=auth("operator")).json()

    assert first["resolved_at"] is not None
    assert second["resolved_at"] == first["resolved_at"]  # resolving again must not restart the retention clock


def test_an_exception_created_as_resolved_gets_resolved_at(client, auth, seed):
    response = client.post(
        "/exceptions",
        json={"plaza_id": str(seed.plaza.plaza_id), "exception_type": "device_fault", "resolved": True},
        headers=auth("operator"),
    )

    assert response.status_code == 201
    assert response.json()["resolved_at"] is not None
