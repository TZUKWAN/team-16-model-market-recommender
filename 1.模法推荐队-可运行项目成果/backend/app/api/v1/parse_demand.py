"""
Demand parsing endpoint - POST /api/v1/parse-demand
Uses DemandParser service for real NLU.

Supports true multi-turn clarification via ConversationStore: each request may
carry a session_id; clarification answers are recorded against the session so
the parser sees the full Q&A history when deciding what to ask next.
"""

from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.schemas.demand import ParseDemandRequest, ParseDemandResponse
from app.schemas.auth import UserContext
from app.core.logging import get_logger
from app.services.audit_service import get_audit_service
from app.services.conversation_store import (
    ConversationTurn,
    get_conversation_store,
)
from app.services.demand_parser import DemandParser

router = APIRouter()
logger = get_logger(__name__)

_parser = DemandParser()


def _enrich_text_with_clarification(text: str, context: dict) -> tuple[str, list[str]]:
    """Backward-compat text enrichment for the rule-parse fallback path.

    The LLM path now receives structured history directly; this keeps the rule
    path working when clarification_answers are supplied in the legacy shape.
    """
    answers = context.get("clarification_answers") or []
    answer_texts: list[str] = []
    if isinstance(answers, list):
        for item in answers:
            if isinstance(item, dict):
                question = str(item.get("question_text") or "").strip()
                answer = str(item.get("user_answer") or "").strip()
                if answer:
                    answer_texts.append(f"{question} {answer}".strip())
            elif isinstance(item, str) and item.strip():
                answer_texts.append(item.strip())
    if not answer_texts:
        return text, []
    return f"{text}\n补充信息：{'；'.join(answer_texts)}", answer_texts


@router.post("/parse-demand", response_model=ParseDemandResponse)
async def parse_demand(
    request: ParseDemandRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Parse natural language demand into structured intent and tags."""
    text = request.raw_text
    context = dict(request.context or {})
    store = get_conversation_store()

    # Resolve or create a conversation session for multi-turn clarification.
    session = store.get_session(request.session_id) if request.session_id else None
    is_new_session = session is None
    if is_new_session:
        session = store.new_session(original_demand=text)

    # Fold this turn's clarification answers (if any) into the session.
    new_answers = context.get("clarification_answers") or []
    answer_count = 0
    if isinstance(new_answers, list):
        answer_count = sum(
            1 for a in new_answers
            if isinstance(a, dict) and str(a.get("user_answer") or "").strip()
        )

    # Build the structured history the parser will consume: everything the
    # user has confirmed so far across prior turns.
    history = session.history_qa
    context["history"] = history

    # Keep the legacy text enrichment too, so the rule fallback path still
    # benefits from the concatenated answers.
    enriched_text, _legacy_texts = _enrich_text_with_clarification(text, context)

    logger.info(
        f"Parsing demand (session={session.session_id}, round={session.round_number}, "
        f"new_answers={answer_count}): {text[:80]}..."
    )

    try:
        result = _parser.parse(enriched_text, context)
        result.raw_text = text

        # Record this turn into the session.
        turn = ConversationTurn(
            turn_id=f"{session.session_id}_t{len(session.turns) + 1}",
            raw_text=text,
            asked_questions=[q.model_dump() for q in result.clarification_questions],
            answers=[
                a for a in new_answers
                if isinstance(a, dict) and str(a.get("user_answer") or "").strip()
            ] if isinstance(new_answers, list) else [],
            parse_source=result.parse_source,
        )
        session.add_turn(turn)

        # Convergence: stop asking once there are no missing slots or the
        # round cap is reached.
        if not result.need_clarification or session.converged:
            session.mark_converged()
            # When converged, drop remaining clarification questions so the
            # front-end proceeds to recommendation.
            result.clarification_questions = []
            result.need_clarification = False
        store.save(session)

        # Surface backend-authoritative conversation state to the front-end.
        result.session_id = session.session_id
        result.clarification_round = session.round_number
        result.conversation_converged = session.converged

        logger.info(
            f"Parsed intent={result.intent} confidence={result.intent_confidence} "
            f"round={result.clarification_round} converged={result.conversation_converged}"
        )
        get_audit_service().record(
            "parse_demand",
            current_user,
            status="success",
            payload_summary={
                "raw_text": text,
                "intent": result.intent,
                "domain": result.domain,
                "tag_count": len(result.tags),
                "parse_source": result.parse_source,
                "session_id": session.session_id,
                "clarification_round": result.clarification_round,
                "new_answer_count": answer_count,
            },
        )
        return result
    except Exception as e:
        logger.error(f"Parse failed: {e}", exc_info=True)
        get_audit_service().record(
            "parse_demand",
            current_user,
            status="fallback",
            payload_summary={
                "raw_text": text,
                "error": e.__class__.__name__,
            },
        )
        # Return a minimal fallback response
        return ParseDemandResponse(
            raw_text=text,
            normalized_query=text,
            parse_source="error_fallback",
            intent="customer_marketing",
            intent_confidence=0.3,
            domain="客户营销",
            user_confirmable_summary="抱歉，需求解析遇到问题，请重试或简化描述。",
            session_id=session.session_id,
            clarification_round=session.round_number,
        )
