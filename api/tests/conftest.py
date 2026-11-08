import os
from pathlib import Path

# Must be set BEFORE the app is imported: tests run against their own database.
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["ENV"] = "dev"
_base_url = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://payforge:payforge@localhost:5432/payforge"
)
TEST_DB = "payforge_test"
os.environ["DATABASE_URL"] = _base_url.rsplit("/", 1)[0] + f"/{TEST_DB}"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

ADMIN = {"X-Admin-Token": get_settings().admin_token}


def _ensure_database() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": TEST_DB})
        if exists.first() is None:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_database():
    _ensure_database()
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    command.downgrade(cfg, "base")  # always test the real migrations from scratch
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean_tables(_migrated_database):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with SessionLocal() as s:
        s.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
        s.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def make_merchant(client: TestClient, name: str = "Acme") -> dict:
    r = client.post("/admin/merchants", json={"name": name, "email": f"{name}@example.com"}, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def merchant(client):
    return make_merchant(client)


@pytest.fixture
def headers(merchant):
    return {"Authorization": f"Bearer {merchant['api_key']}"}


def pay(client, headers, amount=10_000, method="pm_card_visa", **extra):
    body = {"amount": amount, "currency": "usd", "payment_method": method, **extra}
    return client.post("/v1/payments", json=body, headers=headers)
