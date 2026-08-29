"""Tests for feedback service and adoption personalization."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.repositories.runtime_repository import SQLiteRuntimeRepository
from app.schemas.auth import UserContext
from app.services import feedback_service as feedback_module
from app.services.feedback_service import FeedbackService
from app.services.recommender import ModelRecommendationService


TEST_FEEDBACK_DIR = Path(__file__).resolve().parents[2] / "data" / "feedback"


def _user() -> UserContext:
    return UserContext(
        user_id="u1",
        display_name="测试用户",
        role="business_user",
        institution_id="BR_TEST",
        legal_entity_id="JSRCU",
        permitted_domains=["customer_marketing", "credit_risk", "operation_management"],
    )


def _service(name: str) -> FeedbackService:
    TEST_FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    path = TEST_FEEDBACK_DIR / name
    if path.exists():
        path.unlink()
    return FeedbackService(path)


def test_feedback_stats_and_recommender_adoption_boost(monkeypatch):
    service = _service("test_feedback_events_boost.jsonl")
    monkeypatch.setattr(feedback_module, "_feedback_service", service)
    user = _user()
    parse_result = {"business_scenario": "县域新客首贷营销"}
    recommendation = {"model_id": "MKT_001", "model_name": "县域新客首贷转化预测模型", "rank": 1}

    for idx in range(5):
        service.record_recommendation_impressions(
            user,
            request_id=f"rec-{idx}",
            parse_result=parse_result,
            recommendations=[recommendation],
        )
    for idx in range(3):
        service.record_feedback(
            user,
            request_id=f"rec-{idx}",
            model_id="MKT_001",
            model_name="县域新客首贷转化预测模型",
            action="adopt",
            scenario="县域新客首贷营销",
        )

    stats, mode_counts = service.stats(role="business_user")
    assert stats[0].recommended_count == 5
    assert stats[0].adopt_count == 3
    assert stats[0].adoption_rate == 0.6
    assert mode_counts["human"] > 0
    batch = service.adoption_rates(
        role="business_user", scenario=parse_result["business_scenario"]
    )
    assert batch["MKT_001"] == service.model_adoption_rate(
        model_id="MKT_001",
        role="business_user",
        scenario=parse_result["business_scenario"],
    )

    recommender = ModelRecommendationService()
    boost = recommender._adoption_boost(
        {"model_id": "MKT_001"},
        {"user_role": "business_user", "business_scenario": "县域新客首贷营销"},
    )
    assert boost == 3.0
    service.log_path.unlink(missing_ok=True)


def test_adoption_boost_has_cold_start_protection(monkeypatch):
    service = _service("test_feedback_events_cold_start.jsonl")
    monkeypatch.setattr(feedback_module, "_feedback_service", service)
    user = _user()
    parse_result = {"business_scenario": "县域新客首贷营销"}
    recommendation = {"model_id": "MKT_005", "model_name": "客户响应率预测模型", "rank": 1}

    for idx in range(4):
        service.record_recommendation_impressions(
            user,
            request_id=f"rec-cold-{idx}",
            parse_result=parse_result,
            recommendations=[recommendation],
        )
        service.record_feedback(
            user,
            request_id=f"rec-cold-{idx}",
            model_id="MKT_005",
            model_name="客户响应率预测模型",
            action="adopt",
            scenario="县域新客首贷营销",
        )

    recommender = ModelRecommendationService()
    boost = recommender._adoption_boost(
        {"model_id": "MKT_005"},
        {"user_role": "business_user", "business_scenario": "县域新客首贷营销"},
    )
    assert boost == 0.0
    service.log_path.unlink(missing_ok=True)


def test_impression_idempotency_repeated_requests_do_not_inflate(monkeypatch):
    """F2.1: Repeated impression recording for the same request_id must not inflate counts."""
    service = _service("test_feedback_idempotent.jsonl")
    monkeypatch.setattr(feedback_module, "_feedback_service", service)
    user = _user()
    parse_result = {"business_scenario": "县域新客首贷营销"}
    recommendation = {"model_id": "MKT_001", "model_name": "县域新客首贷转化预测模型", "rank": 1}

    # Simulate 10 page refreshes / retries with the same request_id.
    for _ in range(10):
        service.record_recommendation_impressions(
            user,
            request_id="req-stable-001",
            parse_result=parse_result,
            recommendations=[recommendation],
        )

    stats, _ = service.stats()
    assert stats[0].recommended_count == 1, "Repeated impressions for same request should count as 1"
    service.log_path.unlink(missing_ok=True)


def test_feedback_state_transition_final_action_wins(monkeypatch):
    """F2.1: If user changes from reject to adopt, only the final 'adopt' counts."""
    service = _service("test_feedback_transition.jsonl")
    monkeypatch.setattr(feedback_module, "_feedback_service", service)
    user = _user()

    service.record_recommendation_impressions(
        user,
        request_id="req-001",
        parse_result={"business_scenario": "县域新客首贷营销"},
        recommendations=[{"model_id": "MKT_001", "model_name": "M", "rank": 1}],
    )
    # User first rejects, then adopts.
    service.record_feedback(user, request_id="req-001", model_id="MKT_001", action="reject", scenario="县域新客首贷营销")
    service.record_feedback(user, request_id="req-001", model_id="MKT_001", action="adopt", scenario="县域新客首贷营销")

    stats, _ = service.stats()
    assert stats[0].recommended_count == 1
    assert stats[0].adopt_count == 1
    assert stats[0].reject_count == 0, "Final action (adopt) should override earlier reject"
    service.log_path.unlink(missing_ok=True)


def test_demo_test_feedback_does_not_affect_adoption_rate(monkeypatch):
    """F2.2: Demo/test feedback must not inflate production adoption rate or boost."""
    service = _service("test_feedback_isolation.jsonl")
    monkeypatch.setattr(feedback_module, "_feedback_service", service)
    user = _user()
    parse_result = {"business_scenario": "县域新客首贷营销"}

    # Record 100 test-mode impressions and adoptions.
    for idx in range(100):
        service.record_recommendation_impressions(
            user,
            request_id=f"test-req-{idx}",
            parse_result=parse_result,
            recommendations=[{"model_id": "MKT_006", "model_name": "M", "rank": 1}],
            evidence_mode="test",
        )
        service.record_feedback(
            user,
            request_id=f"test-req-{idx}",
            model_id="MKT_006",
            action="adopt",
            scenario="县域新客首贷营销",
            evidence_mode="test",
        )

    # Adoption rate for production ranking must be 0 because no human feedback.
    rate = service.model_adoption_rate(
        model_id="MKT_006", role="business_user", scenario="县域新客首贷营销"
    )
    assert rate["boost_eligible"] is False
    assert rate["adoption_rate"] == 0.0

    # Mode counts should show 200 test events, 0 human.
    counts = service.mode_counts()
    assert counts["test"] == 200
    assert counts["human"] == 0

    recommender = ModelRecommendationService()
    boost = recommender._adoption_boost(
        {"model_id": "MKT_006"},
        {"user_role": "business_user", "business_scenario": "县域新客首贷营销"},
    )
    assert boost == 0.0, "Test feedback must not produce a ranking boost"
    service.log_path.unlink(missing_ok=True)


def test_sqlite_feedback_survives_restart_and_deduplicates_concurrent_impressions(tmp_path):
    db_path = tmp_path / "runtime.db"
    repository = SQLiteRuntimeRepository(db_path)
    service = FeedbackService(repository=repository)
    user = _user()
    recommendation = {"model_id": "MKT_001", "model_name": "Model A", "rank": 1}

    def record_impression(_: int) -> None:
        service.record_recommendation_impressions(
            user,
            request_id="req-concurrent-001",
            parse_result={"business_scenario": "customer_marketing"},
            recommendations=[recommendation],
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(record_impression, range(30)))

    service.record_feedback(
        user,
        request_id="req-concurrent-001",
        model_id="MKT_001",
        model_name="Model A",
        action="adopt",
        scenario="customer_marketing",
    )

    reopened = FeedbackService(repository=SQLiteRuntimeRepository(db_path))
    stats, mode_counts = reopened.stats()
    assert reopened.total_events() == 2
    assert stats[0].recommended_count == 1
    assert stats[0].adopt_count == 1
    assert stats[0].adoption_rate == 1.0
    assert mode_counts["human"] == 2
