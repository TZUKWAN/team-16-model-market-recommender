from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]


def _module():
    spec = spec_from_file_location("load_test_api", ROOT / "scripts" / "load_test_api.py")
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_percentile_uses_nearest_rank():
    module = _module()
    values = list(range(1, 101))
    assert module.percentile(values, 0.50) == 50
    assert module.percentile(values, 0.95) == 95
    assert module.percentile(values, 0.99) == 99


def test_run_case_reports_status_and_errors():
    module = _module()
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200 if calls < 3 else 503, json={}, request=request)

    with httpx.Client(base_url="https://test", transport=httpx.MockTransport(handler)) as client:
        result = module.run_case(
            client, "health", "GET", "/health", lambda _: None,
            samples=3, concurrency=1,
        )
    assert result["success_count"] == 2
    assert result["status_codes"] == {"200": 2, "503": 1}
    assert result["errors"] == {"HTTP_503": 1}


def test_survey_setup_respects_campaign_schema():
    module = _module()

    def handler(request):
        payload = __import__("json").loads(request.content)
        assert payload["samples_per_respondent"] >= 2
        return httpx.Response(
            200,
            json={"campaign": {"campaign_id": "SURV_123456789ABC"}},
            request=request,
        )

    with httpx.Client(base_url="https://test", transport=httpx.MockTransport(handler)) as client:
        assert module.setup_survey(client) == "SURV_123456789ABC"
