"""Schema for natural language demand parsing."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class ParseDemandRequest(BaseModel):
    """Request: parse a natural language demand/query."""
    raw_text: str = Field(..., description="原始用户输入文本", min_length=1, max_length=10000)
    context: dict[str, Any] = Field(default_factory=dict, description="可选的调用上下文")
    session_id: str = Field(default="", max_length=128, description="多轮澄清会话 id；首次提问可留空，由后端创建")


class ClarificationQuestion(BaseModel):
    """A follow-up question for missing demand slots."""
    question_id: str = ""
    question_text: str = ""
    slot: str = ""
    options: list[str] = Field(default_factory=list)
    user_answer: str = ""


class ParseDemandResponse(BaseModel):
    """Response: structured output from demand parsing."""
    raw_text: str = ""
    normalized_query: str = ""
    parse_source: str = Field(default="rule", description="解析来源：rule / llm / hybrid_fallback / error_fallback")
    llm_enabled: bool = Field(default=False, description="本次解析时 LLM 是否可用")
    llm_trace_id: str = Field(default="", description="LLM 调用审计 trace id；未调用时为空")
    llm_fallback_reason: str = Field(default="", description="Non-sensitive LLM fallback reason")
    intent: str = ""
    intent_confidence: float = 0.0
    domain: str = ""
    business_scenario: str = ""
    business_stage: str = ""
    customer_segment: list[str] = Field(default_factory=list)
    product_type: list[str] = Field(default_factory=list)
    risk_type: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    data_conditions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    tag_names: list[str] = Field(default_factory=list)
    tag_confidence: dict[str, float] = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    need_clarification: bool = False
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    structured_filters: dict[str, Any] = Field(default_factory=dict)
    business_to_model_translation: str = ""
    user_confirmable_summary: str = ""
    # Multi-turn conversation fields. session_id lets the front-end thread
    # subsequent clarification answers back to the same conversation;
    # clarification_round is the backend-authoritative round counter (1-based);
    # conversation_converged signals that no more questions should be asked.
    session_id: str = Field(default="", description="多轮澄清会话 id")
    clarification_round: int = Field(default=1, description="当前澄清轮次（1-based）")
    conversation_converged: bool = Field(default=False, description="会话是否已收敛，无需再追问")
