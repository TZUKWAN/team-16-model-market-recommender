"""Shared test fixtures."""

import os

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("LLM_BASE_URL", "")
os.environ.setdefault("LLM_MODEL", "")
os.environ.setdefault("ENABLE_MOCK", "true")
os.environ.setdefault("MODEL_MARKET_ADAPTER", "demo")
os.environ.setdefault("HYBRID_DENSE_ENABLED", "false")
os.environ.setdefault("HYBRID_DENSE_WEIGHT", "0")

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Provide a FastAPI TestClient instance."""
    return TestClient(app)


@pytest.fixture
def marketing_demand():
    """Sample marketing demand input."""
    return {
        "raw_text": "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。"
    }


@pytest.fixture
def risk_pre_demand():
    """Sample pre-loan risk control demand input."""
    return {
        "raw_text": "帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。"
    }


@pytest.fixture
def post_loan_demand():
    """Sample post-loan early warning demand input."""
    return {
        "raw_text": "我想提前发现对公贷款可能逾期的客户，并给客户经理一个预警名单。"
    }


@pytest.fixture(autouse=True)
def _reset_model_market_client():
    """Ensure each test uses a fresh demo model-market client, isolated from .env."""
    from app.core.config import get_settings
    from app.integrations import model_market_client as mmc
    get_settings.cache_clear()
    mmc.reset_model_market_client_for_tests()
    yield
    mmc.reset_model_market_client_for_tests()


@pytest.fixture(autouse=True)
def _isolate_feedback_log(tmp_path):
    """Redirect feedback event log to per-test tmp dir to avoid polluting data/feedback."""
    from app.services.feedback_service import get_feedback_service
    svc = get_feedback_service()
    original = svc.log_path
    svc.log_path = tmp_path / "feedback_events.jsonl"
    svc.log_path.parent.mkdir(parents=True, exist_ok=True)
    yield
    svc.log_path = original


@pytest.fixture(autouse=True)
def _isolate_survey_store(tmp_path):
    """Keep campaign tokens and survey responses out of the workspace during tests."""
    from app.services.survey_service import get_survey_service
    svc = get_survey_service()
    original_campaign_dir = svc.campaign_dir
    original_response_log = svc.response_log_path
    svc.campaign_dir = tmp_path / "survey_campaigns"
    svc.response_log_path = tmp_path / "survey_responses.jsonl"
    svc.campaign_dir.mkdir(parents=True, exist_ok=True)
    svc.response_log_path.parent.mkdir(parents=True, exist_ok=True)
    yield
    svc.campaign_dir = original_campaign_dir
    svc.response_log_path = original_response_log


@pytest.fixture(autouse=True)
def _isolate_recommendation_version_store(tmp_path):
    """Keep recommendation versions out of the workspace during tests."""
    from app.services.recommendation_version_store import get_recommendation_version_store
    store = get_recommendation_version_store()
    original = store.storage_dir
    store.storage_dir = tmp_path / "recommendation_versions"
    store.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    store.storage_dir = original
