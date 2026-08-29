"""Tests for compliance masking and usage boundaries."""

from app.services.compliance_service import ComplianceService


def test_compliance_service_masks_sensitive_identifiers():
    service = ComplianceService()

    payload = service.apply_to_result_payload({
        "result_type": "risk",
        "rows": [
            {
                "customer_id": "CUST123456789",
                "customer_id_masked": "CUST_0001",
                "risk_score": 0.82,
            }
        ],
    })

    row = payload["rows"][0]
    assert row["customer_id"] != "CUST123456789"
    assert row["customer_id_masked"] == "CUST_0001"
    assert payload["compliance"]["sensitivity_level"] == "high"
    assert "customer_id" in payload["compliance"]["sensitive_fields_masked"]
    assert payload["usage_boundary"]


def test_field_registry_contains_sensitivity_levels():
    service = ComplianceService()

    assert service.field_sensitivity("credit_report") == "high"
    assert service.field_sensitivity("campaign_response") == "low"
