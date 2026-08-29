"""Tests for desensitized demo result sample library."""

from app.services.demo_result_service import DemoResultService


def test_demo_result_service_loads_all_result_types():
    service = DemoResultService()

    risk = service.rows("risk")
    marketing = service.rows("marketing")
    operation = service.rows("operation")

    assert risk and marketing and operation
    assert risk[0]["demo_data"] is True
    assert marketing[0]["demo_data"] is True
    assert operation[0]["demo_data"] is True
    assert risk[0]["desensitized_notice"]
    assert marketing[0]["desensitized_notice"]
    assert operation[0]["desensitized_notice"]


def test_demo_result_shapes_match_task_requirements():
    service = DemoResultService()

    risk = service.result_for_model("RISK_001")
    marketing = service.result_for_model("MKT_001")
    operation = service.result_for_model("OPS_001")

    assert risk["result_type"] == "risk"
    assert risk["compliance_notice"]
    assert risk["usage_boundary"]
    assert risk["compliance"]["sensitivity_level"] == "high"
    assert {"customer_id_masked", "risk_score", "risk_level", "reason_code", "suggested_action"}.issubset(
        risk["rows"][0]
    )
    assert marketing["result_type"] == "marketing"
    assert marketing["compliance"]["sensitivity_level"] == "medium"
    assert {"customer_id_masked", "product", "conversion_probability", "priority", "touch_channel"}.issubset(
        marketing["rows"][0]
    )
    assert operation["result_type"] == "operation"
    assert {"subject_masked", "warning_type", "probability", "suggested_action"}.issubset(
        operation["rows"][0]
    )


def test_demo_result_schema_uses_model_domain():
    service = DemoResultService()

    schema = service.result_schema_for_model("MKT_001")

    row_props = schema["properties"]["rows"]["items"]["properties"]
    assert "conversion_probability" in row_props
    assert "touch_channel" in row_props
    assert "compliance_notice" in schema["properties"]
    assert "usage_boundary" in schema["properties"]
