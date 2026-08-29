"""API tests for clarification-based demand parsing."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_parse_demand_accepts_clarification_answers_and_reparses():
    first = client.post("/api/v1/parse-demand", json={
        "raw_text": "帮我看看有什么模型可以用。",
    })
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["need_clarification"] is True
    assert first_data["clarification_questions"]

    answers = [
        {
            **first_data["clarification_questions"][0],
            "user_answer": "客户营销，县域新客，输出名单排序和转化概率。",
        }
    ]
    second = client.post("/api/v1/parse-demand", json={
        "raw_text": "帮我看看有什么模型可以用。",
        "context": {"clarification_answers": answers},
    })

    assert second.status_code == 200
    second_data = second.json()
    assert second_data["intent"] == "customer_marketing"
    assert "名单" in "".join(second_data["expected_outputs"]) or "conversion_prediction" in second_data["tags"]
    assert len(second_data["clarification_questions"]) <= len(first_data["clarification_questions"])
