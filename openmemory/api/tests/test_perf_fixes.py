"""Regression tests for the performance fixes:

  * get_categories must return distinct categories via a join (it used to load
    every memory row and lazy-load categories per memory — ~1 query/memory).
  * list_memories must filter to active state IN SQL so `total` matches the
    returned items (paused rows used to be counted, then dropped post-pagination).
"""

import os
import uuid

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import App, Category, Memory, MemoryState, User
from app.routers import memories as memories_router


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()

    def _get_test_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(memories_router.router)
    app.dependency_overrides[get_db] = _get_test_db

    client = TestClient(app, raise_server_exceptions=False)
    yield client, session
    session.close()


def _seed(session):
    user = User(id=uuid.uuid4(), user_id="default_user")
    app = App(id=uuid.uuid4(), name="test-app", owner=user)
    cat_a = Category(name="cat-a")
    cat_b = Category(name="cat-b")
    cat_archived_only = Category(name="cat-archived-only")

    active_1 = Memory(
        id=uuid.uuid4(), user_id=user.id, app_id=app.id,
        content="active one", state=MemoryState.active, categories=[cat_a, cat_b],
    )
    active_2 = Memory(
        id=uuid.uuid4(), user_id=user.id, app_id=app.id,
        content="active two", state=MemoryState.active, categories=[cat_a],
    )
    paused = Memory(
        id=uuid.uuid4(), user_id=user.id, app_id=app.id,
        content="paused one", state=MemoryState.paused, categories=[cat_a],
    )
    archived = Memory(
        id=uuid.uuid4(), user_id=user.id, app_id=app.id,
        content="archived one", state=MemoryState.archived,
        categories=[cat_archived_only],
    )
    session.add_all([user, app, active_1, active_2, paused, archived])
    session.commit()
    return user


def test_get_categories_distinct_and_excludes_archived(env):
    client, session = env
    _seed(session)

    resp = client.get("/api/v1/memories/categories", params={"user_id": "default_user"})
    assert resp.status_code == 200
    body = resp.json()

    names = sorted(c["name"] for c in body["categories"])
    # cat-a appears on three memories but must be returned once; the category
    # only attached to an archived memory must not appear at all.
    assert names == ["cat-a", "cat-b"]
    assert body["total"] == 2


def test_list_memories_total_matches_returned_items(env):
    client, session = env
    _seed(session)

    resp = client.get("/api/v1/memories/", params={"user_id": "default_user"})
    assert resp.status_code == 200
    body = resp.json()

    # Only the two active memories — the paused one must not be counted in
    # total and then silently dropped from items.
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert {item["content"] for item in body["items"]} == {"active one", "active two"}
