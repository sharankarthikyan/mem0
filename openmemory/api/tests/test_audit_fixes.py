"""Regression tests for the audit fixes:

  * create_memory must NOT return HTTP 200 on a failed/empty write
    (memory store unavailable -> 503, store error -> 502, no-op -> explicit body).
  * PUT /api/v1/config/ must persist, re-init the client, and return the config
    (it used to fall off the end and return HTTP 200 `null`).
  * import_backup must be atomic (rollback on any DB error) and report vector
    failures honestly (207 Multi-Status) instead of always claiming success.
"""

import io
import json
import os
import uuid
import zipfile

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import App, Config, Memory, MemoryState, User
from app.routers import backup as backup_router
from app.routers import config as config_router
from app.routers import memories as memories_router


@pytest.fixture
def env():
    """A FastAPI app wired to a shared in-memory SQLite DB plus a live session."""
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
    app.include_router(config_router.router)
    app.include_router(backup_router.router)
    app.dependency_overrides[get_db] = _get_test_db

    client = TestClient(app, raise_server_exceptions=False)
    yield client, session
    session.close()


def _make_user(session, user_id="default_user"):
    user = User(id=uuid.uuid4(), user_id=user_id)
    session.add(user)
    session.commit()
    return user


# ---------------------------------------------------------------------------
# create_memory: never HTTP 200 on failure, never null
# ---------------------------------------------------------------------------

class _FakeEmbedder:
    def __init__(self, dims=8):
        self.dims = dims

    def embed(self, text, kind="add"):
        return [0.1] * self.dims


def test_create_memory_503_when_client_unavailable(env, monkeypatch):
    client, session = env
    _make_user(session)
    monkeypatch.setattr(memories_router, "get_memory_client", lambda: None)

    resp = client.post("/api/v1/memories/", json={"user_id": "default_user", "text": "hi"})

    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()


def test_create_memory_502_when_store_add_fails(env, monkeypatch):
    client, session = env
    _make_user(session)

    class _BoomClient:
        def add(self, *a, **k):
            raise RuntimeError("qdrant down")

    monkeypatch.setattr(memories_router, "get_memory_client", lambda: _BoomClient())

    resp = client.post("/api/v1/memories/", json={"user_id": "default_user", "text": "hi"})

    assert resp.status_code == 502


def test_create_memory_noop_returns_explicit_body_not_null(env, monkeypatch):
    client, session = env
    _make_user(session)

    class _NoAddClient:
        def add(self, *a, **k):
            return {"results": []}  # mem0 extracted nothing

    monkeypatch.setattr(memories_router, "get_memory_client", lambda: _NoAddClient())

    resp = client.post("/api/v1/memories/", json={"user_id": "default_user", "text": "hi"})

    assert resp.status_code == 200
    body = resp.json()
    assert body is not None  # the bug: this used to be HTTP 200 `null`
    assert body["message"]
    assert body["results"] == []


def test_create_memory_success_persists_and_returns_row(env, monkeypatch):
    client, session = env
    _make_user(session)
    mem_id = str(uuid.uuid4())

    class _OkClient:
        def add(self, *a, **k):
            return {"results": [{"event": "ADD", "id": mem_id, "memory": "remembered"}]}

    monkeypatch.setattr(memories_router, "get_memory_client", lambda: _OkClient())
    monkeypatch.setattr(memories_router, "schedule_categorization", lambda *a, **k: None)
    monkeypatch.setattr(memories_router, "get_search_cache", lambda: None)

    resp = client.post("/api/v1/memories/", json={"user_id": "default_user", "text": "remember this"})

    assert resp.status_code == 200
    assert session.query(Memory).filter(Memory.id == uuid.UUID(mem_id)).count() == 1


# ---------------------------------------------------------------------------
# PUT /api/v1/config/: persists, returns the config (not null)
# ---------------------------------------------------------------------------

def test_put_config_persists_and_returns(env, monkeypatch):
    client, session = env
    reset_calls = {"n": 0}
    monkeypatch.setattr(config_router, "reset_memory_client", lambda *a, **k: reset_calls.__setitem__("n", reset_calls["n"] + 1))

    payload = {
        "openmemory": {"custom_instructions": "be terse"},
        "mem0": {"llm": None, "embedder": None, "vector_store": None},
    }
    resp = client.put("/api/v1/config/", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body is not None  # the bug: PUT used to return HTTP 200 `null`
    assert body["openmemory"]["custom_instructions"] == "be terse"
    assert reset_calls["n"] == 1  # client was re-initialized

    # And it was actually written to the DB.
    stored = session.query(Config).filter(Config.key == "main").first()
    assert stored is not None
    assert stored.value["openmemory"]["custom_instructions"] == "be terse"

    # A subsequent GET reflects the saved value.
    got = client.get("/api/v1/config/")
    assert got.json()["openmemory"]["custom_instructions"] == "be terse"


# ---------------------------------------------------------------------------
# import_backup: atomic rollback + honest vector reporting
# ---------------------------------------------------------------------------

def _zip_backup(memories):
    payload = {"categories": [], "memories": memories, "memory_categories": [], "status_history": []}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("memories.json", json.dumps(payload))
    buf.seek(0)
    return buf


def _post_import(client, zip_buf, user_id="default_user", mode="overwrite"):
    return client.post(
        f"/api/v1/backup/import?mode={mode}",
        files={"file": ("backup.zip", zip_buf, "application/zip")},
        data={"user_id": user_id},
    )


def test_import_rolls_back_whole_batch_on_error(env, monkeypatch):
    client, session = env
    _make_user(session)
    monkeypatch.setattr(backup_router, "get_memory_client", lambda: None)  # skip vector phase

    good_id = str(uuid.uuid4())
    # Second record has an invalid UUID -> raises inside the transaction -> rollback.
    zip_buf = _zip_backup([
        {"id": good_id, "content": "keep me", "state": "active"},
        {"id": "not-a-uuid", "content": "boom", "state": "active"},
    ])

    resp = _post_import(client, zip_buf)

    assert resp.status_code == 500
    # Atomicity: the VALID first memory must NOT have been committed.
    assert session.query(Memory).count() == 0


def test_import_reports_vector_failures_as_207(env, monkeypatch):
    client, session = env
    _make_user(session)

    class _FailingVectorStore:
        # No embedding_model_dims attribute -> dimension pre-check is skipped.
        def insert(self, *a, **k):
            raise RuntimeError("vector store rejected insert")

    class _Client:
        def __init__(self):
            self.vector_store = _FailingVectorStore()
            self.embedding_model = _FakeEmbedder()

    monkeypatch.setattr(backup_router, "get_memory_client", lambda: _Client())

    mem_id = str(uuid.uuid4())
    zip_buf = _zip_backup([{"id": mem_id, "content": "searchable text", "state": "active"}])

    resp = _post_import(client, zip_buf)

    assert resp.status_code == 207  # Multi-Status: DB ok, vectors failed
    body = resp.json()
    assert body["status"] == "partial"
    assert body["vectors_failed"] == 1
    assert body["vectors_written"] == 0
    # The DB row IS committed (it just is not searchable yet).
    assert session.query(Memory).filter(Memory.id == uuid.UUID(mem_id)).count() == 1


def test_import_rejects_embedding_dimension_mismatch_without_writing(env, monkeypatch):
    client, session = env
    _make_user(session)

    class _MismatchStore:
        embedding_model_dims = 1536  # store expects 1536

    class _Client:
        def __init__(self):
            self.vector_store = _MismatchStore()
            self.embedding_model = _FakeEmbedder(dims=8)  # backup embeds to 8

    monkeypatch.setattr(backup_router, "get_memory_client", lambda: _Client())

    zip_buf = _zip_backup([{"id": str(uuid.uuid4()), "content": "text", "state": "active"}])

    resp = _post_import(client, zip_buf)

    assert resp.status_code == 400
    assert "dimension" in resp.json()["detail"].lower()
    # Pre-check runs BEFORE the DB phase: nothing imported.
    assert session.query(Memory).count() == 0
