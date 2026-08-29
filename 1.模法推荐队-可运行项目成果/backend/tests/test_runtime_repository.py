from concurrent.futures import ThreadPoolExecutor

from app.repositories.runtime_repository import SQLiteRuntimeRepository


def test_repository_persists_and_filters_partitions(tmp_path):
    path = tmp_path / "runtime.db"
    repo = SQLiteRuntimeRepository(path)
    repo.insert("events", "e1", {"created_at": "1", "value": 1}, partition_key="a")
    repo.insert("events", "e2", {"created_at": "2", "value": 2}, partition_key="b")

    reopened = SQLiteRuntimeRepository(path)
    assert reopened.get("events", "e1")["value"] == 1
    assert [row["value"] for row in reopened.list("events", partition_key="b")] == [2]


def test_concurrent_idempotent_insert_creates_one_record(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")

    def insert(index):
        return repo.insert(
            "versions",
            f"v{index}",
            {"created_at": str(index), "winner": index},
            partition_key="session",
            idempotency_key="same-request",
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(insert, range(30)))

    assert repo.count("versions", partition_key="session") == 1
    assert sum(int(created) for _, created in results) == 1
    assert len({payload["winner"] for payload, _ in results}) == 1


def test_upsert_and_delete_partition_are_transactional(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    repo.upsert("sessions", "s1", {"created_at": "1", "turns": 1}, partition_key="s1")
    repo.upsert("sessions", "s1", {"created_at": "1", "turns": 2}, partition_key="s1")
    assert repo.get("sessions", "s1")["turns"] == 2
    assert repo.delete_partition("sessions", "s1") == 1
    assert repo.get("sessions", "s1") is None


def test_concurrent_partition_sequences_are_unique(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")

    def insert(index):
        return repo.insert_with_sequence(
            "versions",
            f"v{index}",
            {"created_at": f"{index:02d}"},
            partition_key="session",
            sequence_field="version_number",
            idempotency_key=f"request-{index}",
        )[0]

    with ThreadPoolExecutor(max_workers=12) as pool:
        records = list(pool.map(insert, range(30)))

    assert sorted(record["version_number"] for record in records) == list(range(1, 31))


def test_partition_limit_is_atomic_and_enforces_identity(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    base = {"submitted_at": "1", "role": "business", "department": "branch"}

    _, created, count, status = repo.insert_with_partition_limit(
        "responses", "r1", {**base, "sample": "a"},
        partition_key="campaign:user", idempotency_key="campaign:user:a",
        max_records=2, consistent_fields=("role", "department"),
    )
    assert (created, count, status) == (True, 1, "created")

    _, created, count, status = repo.insert_with_partition_limit(
        "responses", "r2", {**base, "sample": "a"},
        partition_key="campaign:user", idempotency_key="campaign:user:a",
        max_records=2, consistent_fields=("role", "department"),
    )
    assert (created, count, status) == (False, 1, "duplicate")

    _, created, count, status = repo.insert_with_partition_limit(
        "responses", "r3", {**base, "department": "other", "sample": "b"},
        partition_key="campaign:user", idempotency_key="campaign:user:b",
        max_records=2, consistent_fields=("role", "department"),
    )
    assert (created, count, status) == (False, 1, "inconsistent")

    repo.insert_with_partition_limit(
        "responses", "r4", {**base, "sample": "b"},
        partition_key="campaign:user", idempotency_key="campaign:user:b",
        max_records=2, consistent_fields=("role", "department"),
    )
    _, created, count, status = repo.insert_with_partition_limit(
        "responses", "r5", {**base, "sample": "c"},
        partition_key="campaign:user", idempotency_key="campaign:user:c",
        max_records=2, consistent_fields=("role", "department"),
    )
    assert (created, count, status) == (False, 2, "limit")


def test_batch_insert_is_idempotent_and_json_fields_are_filterable(tmp_path):
    repo = SQLiteRuntimeRepository(tmp_path / "runtime.db")
    records = [
        {
            "record_id": f"e{index}",
            "partition_key": "request",
            "idempotency_key": f"key-{index}",
            "created_at": str(index),
            "payload": {
                "role": "business" if index < 2 else "risk",
                "scenario": "marketing",
                "evidence_mode": "human",
                "index": index,
            },
        }
        for index in range(3)
    ]
    assert repo.insert_many("feedback_events", records) == 3
    assert repo.insert_many("feedback_events", records) == 0
    filtered = repo.list_by_json_fields(
        "feedback_events",
        {"role": "business", "scenario": "marketing", "evidence_mode": "human"},
    )
    assert [row["index"] for row in filtered] == [0, 1]
