"""F5.1: Tests for recommendation version persistence and diff."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.services.recommendation_version_store import RecommendationVersionStore
from app.repositories.runtime_repository import SQLiteRuntimeRepository

TEST_DIR = Path(__file__).resolve().parents[2] / "data" / "recommendation_versions"


def _store() -> RecommendationVersionStore:
    return RecommendationVersionStore(TEST_DIR)


def test_sqlite_store_survives_reopen_and_is_idempotent(tmp_path):
    repository = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    store = RecommendationVersionStore(repository=repository)
    first = store.save_version(
        session_id="sqlite-session",
        request_id="request-1",
        idempotency_key="client-1",
        parse_summary={"intent": "credit_risk"},
        recommendations=[{"model_id": "OFFICIAL_001", "rank": 1, "total_score": 88}],
    )
    duplicate = store.save_version(
        session_id="sqlite-session",
        request_id="request-2",
        idempotency_key="client-1",
        parse_summary={"intent": "credit_risk"},
        recommendations=[{"model_id": "OFFICIAL_002", "rank": 1, "total_score": 99}],
    )
    reopened = RecommendationVersionStore(repository=SQLiteRuntimeRepository(tmp_path / "runtime.db"))

    assert duplicate["version_id"] == first["version_id"]
    assert reopened.list_versions("sqlite-session") == [first]


def _cleanup(session_id: str):
    path = TEST_DIR / f"{session_id}.jsonl"
    path.unlink(missing_ok=True)


def test_save_version_creates_version_record():
    store = _store()
    _cleanup("test-save")
    rec = store.save_version(
        session_id="test-save",
        request_id="req-001",
        parse_summary={"intent": "customer_marketing", "business_scenario": "县域新客"},
        recommendations=[
            {"model_id": "MKT_001", "model_name": "M1", "rank": 1, "total_score": 90},
            {"model_id": "MKT_002", "model_name": "M2", "rank": 2, "total_score": 85},
        ],
        raw_text="测试需求",
    )
    assert rec["version_id"].startswith("VER_")
    assert rec["version_number"] == 1
    assert len(rec["model_ranking"]) == 2
    assert rec["model_ranking"][0]["model_id"] == "MKT_001"
    assert rec["model_ranking"][0]["total_score"] == 90
    _cleanup("test-save")


def test_save_version_idempotent_same_request_id():
    """F5.1: Saving the same request_id twice should not duplicate."""
    store = _store()
    _cleanup("test-idem")
    rec1 = store.save_version(
        session_id="test-idem",
        request_id="req-stable",
        parse_summary={"intent": "credit_risk"},
        recommendations=[{"model_id": "MKT_001", "rank": 1}],
    )
    rec2 = store.save_version(
        session_id="test-idem",
        request_id="req-stable",
        parse_summary={"intent": "credit_risk"},
        recommendations=[{"model_id": "MKT_001", "rank": 1}],
    )
    assert rec1["version_id"] == rec2["version_id"]
    assert rec1["version_number"] == rec2["version_number"]
    versions = store.list_versions("test-idem")
    assert len(versions) == 1
    _cleanup("test-idem")


def test_list_versions_ordered_by_number():
    store = _store()
    _cleanup("test-list")
    for i in range(3):
        store.save_version(
            session_id="test-list",
            request_id=f"req-{i}",
            parse_summary={"intent": "test"},
            recommendations=[{"model_id": f"MKT_{i}", "rank": 1}],
        )
    versions = store.list_versions("test-list")
    assert len(versions) == 3
    assert versions[0]["version_number"] == 1
    assert versions[2]["version_number"] == 3
    _cleanup("test-list")


def test_diff_versions_detects_added_removed_rank_changes():
    store = _store()
    _cleanup("test-diff")
    va = store.save_version(
        session_id="test-diff",
        request_id="req-a",
        parse_summary={"intent": "marketing"},
        recommendations=[
            {"model_id": "MKT_001", "model_name": "M1", "rank": 1, "total_score": 90},
            {"model_id": "MKT_002", "model_name": "M2", "rank": 2, "total_score": 85},
        ],
    )
    vb = store.save_version(
        session_id="test-diff",
        request_id="req-b",
        parse_summary={"intent": "marketing"},
        recommendations=[
            {"model_id": "MKT_001", "model_name": "M1", "rank": 1, "total_score": 92},
            {"model_id": "MKT_003", "model_name": "M3", "rank": 2, "total_score": 88},
        ],
    )
    diff = store.diff_versions("test-diff", va["version_id"], vb["version_id"])
    assert "MKT_003" in diff["added_models"]
    assert "MKT_002" in diff["removed_models"]
    # MKT_001 has a score change (90 -> 92)
    m1_change = next(c for c in diff["rank_changes"] if c["model_id"] == "MKT_001")
    assert m1_change["score_delta"] == 2.0
    _cleanup("test-diff")


def test_version_survives_new_store_instance():
    """F5.1: Versions must persist across store instances (process restart simulation)."""
    store1 = _store()
    _cleanup("test-persist")
    store1.save_version(
        session_id="test-persist",
        request_id="req-p1",
        parse_summary={"intent": "test"},
        recommendations=[{"model_id": "MKT_001", "rank": 1}],
    )
    # Simulate process restart by creating a new store instance.
    store2 = _store()
    versions = store2.list_versions("test-persist")
    assert len(versions) == 1
    assert versions[0]["model_ranking"][0]["model_id"] == "MKT_001"
    _cleanup("test-persist")


def test_recommend_api_persists_version(client):
    """F5.1: The recommend API must save a version and return version_id."""
    from app.services.recommendation_version_store import get_recommendation_version_store
    store = get_recommendation_version_store()
    _cleanup("test-api-session")

    response = client.post("/api/v1/recommend-models", json={
        "parse_result": {
            "raw_text": "县域新客首贷营销",
            "intent": "customer_marketing",
            "business_scenario": "县域新客首贷营销",
            "session_id": "test-api-session",
        },
        "top_k": 3,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["version_id"].startswith("VER_")
    assert data["version_number"] == 1
    versions = store.list_versions("test-api-session")
    assert len(versions) == 1
    assert versions[0]["model_ranking"][0]["total_score"] > 0
    assert len(versions[0]["config_hash"]) == 64
    _cleanup("test-api-session")


def test_concurrent_same_idempotency_key_creates_one_version(tmp_path):
    store = RecommendationVersionStore(tmp_path)

    def save_once(index: int):
        return store.save_version(
            session_id="concurrent-session",
            request_id=f"req-{index}",
            idempotency_key="stable-client-request",
            parse_summary={"intent": "customer_marketing"},
            recommendations=[{"model_id": "MKT_001", "rank": 1, "total_score": 88.5}],
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(save_once, range(20)))

    assert len({record["version_id"] for record in records}) == 1
    assert len(store.list_versions("concurrent-session")) == 1


def test_version_api_diff_route_and_user_isolation(client):
    session_id = "version-access-session"
    payload = {
        "parse_result": {
            "raw_text": "县域新客首贷营销",
            "intent": "customer_marketing",
            "business_scenario": "县域新客首贷营销",
            "session_id": session_id,
        },
        "top_k": 3,
    }
    first = client.post(
        "/api/v1/recommend-models",
        json={**payload, "client_request_id": "browser-action-1"},
        headers={"X-User-Id": "business_user"},
    )
    second = client.post(
        "/api/v1/recommend-models",
        json={**payload, "client_request_id": "browser-action-2"},
        headers={"X-User-Id": "business_user"},
    )
    assert first.status_code == 200
    assert second.status_code == 200

    own = client.get(
        f"/api/v1/recommendation-versions/{session_id}",
        headers={"X-User-Id": "business_user"},
    )
    cross_user = client.get(
        f"/api/v1/recommendation-versions/{session_id}",
        headers={"X-User-Id": "risk_user"},
    )
    assert own.status_code == 200
    assert own.json()["count"] == 2
    assert cross_user.status_code == 200
    assert cross_user.json()["count"] == 0

    versions = own.json()["versions"]
    diff = client.get(
        f"/api/v1/recommendation-versions/{session_id}/diff",
        params={"version_a": versions[0]["version_id"], "version_b": versions[1]["version_id"]},
        headers={"X-User-Id": "business_user"},
    )
    assert diff.status_code == 200
    assert diff.json()["version_a"] == versions[0]["version_id"]
    assert "summary" in diff.json()
