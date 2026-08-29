from concurrent.futures import ThreadPoolExecutor
import threading
import time

from app.schemas.recommendation import RecommendModelsResponse
from app.services.recommender import ModelRecommendationService


def test_identical_recommendations_singleflight_with_unique_request_ids(monkeypatch):
    service = ModelRecommendationService()
    calls = 0
    calls_lock = threading.Lock()

    def compute(**kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return RecommendModelsResponse(request_id="computed", summary=str(kwargs["parse_result"]["intent"]))

    monkeypatch.setattr(service, "_recommend_uncached", compute)
    demand = {"intent": "customer_marketing", "business_scenario": "marketing"}
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: service.recommend(demand), range(30)))

    assert calls == 1
    assert len({result.request_id for result in results}) == 30
    assert {result.summary for result in results} == {"customer_marketing"}


def test_different_demands_do_not_share_singleflight_cache(monkeypatch):
    service = ModelRecommendationService()
    calls = 0

    def compute(**kwargs):
        nonlocal calls
        calls += 1
        intent = kwargs["parse_result"]["intent"]
        return RecommendModelsResponse(request_id=f"computed-{intent}", summary=intent)

    monkeypatch.setattr(service, "_recommend_uncached", compute)
    first = service.recommend({"intent": "customer_marketing"})
    second = service.recommend({"intent": "credit_risk"})
    assert calls == 2
    assert first.summary != second.summary
