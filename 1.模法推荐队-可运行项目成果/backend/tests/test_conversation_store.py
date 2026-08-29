"""Tests for the multi-turn conversation session store and clarification flow."""

from app.repositories.runtime_repository import SQLiteRuntimeRepository
from app.services.conversation_store import (
    ConversationSession,
    ConversationTurn,
    ConversationStore,
)


def test_session_round_counter_and_convergence():
    """round_number is 1-based and converges after MAX_TURNS."""
    session = ConversationSession(session_id="s1", original_demand="我想做风控")
    assert session.round_number == 1
    assert not session.converged

    session.add_turn(ConversationTurn(turn_id="t1", raw_text="我想做风控"))
    assert session.round_number == 2
    assert not session.converged

    session.add_turn(ConversationTurn(turn_id="t2", raw_text="我想做风控"))
    assert session.round_number == 3
    assert not session.converged

    session.add_turn(ConversationTurn(turn_id="t3", raw_text="我想做风控"))
    assert session.round_number == 3  # capped at MAX_TURNS
    assert session.converged  # hit the MAX_TURNS cap


def test_session_history_qa_flattens_answers():
    """history_qa accumulates answered questions across turns."""
    session = ConversationSession(session_id="s1")
    session.add_turn(ConversationTurn(
        turn_id="t1", raw_text="需求",
        answers=[{"question_text": "目标客群？", "user_answer": "小微企业", "slot": "customer_segment"}],
    ))
    session.add_turn(ConversationTurn(
        turn_id="t2", raw_text="需求",
        answers=[{"question_text": "期望输出？", "user_answer": "评分", "slot": "expected_outputs"}],
    ))
    qa = session.history_qa
    assert len(qa) == 2
    assert qa[0]["answer"] == "小微企业"
    assert qa[1]["slot"] == "expected_outputs"


def test_store_persists_and_reloads_session(tmp_path):
    """A session saved to disk can be reloaded by id (durability)."""
    store = ConversationStore(conversations_dir=tmp_path)
    session = store.new_session(original_demand="农户贷款风控")
    sid = session.session_id

    session.add_turn(ConversationTurn(turn_id="t1", raw_text="农户贷款风控"))
    store.save(session)

    # Drop the in-memory copy to force a disk reload.
    store._sessions.pop(sid)
    reloaded = store.get_session(sid)
    assert reloaded is not None
    assert reloaded.original_demand == "农户贷款风控"
    assert len(reloaded.turns) == 1


def test_store_get_unknown_session_returns_none(tmp_path):
    store = ConversationStore(conversations_dir=tmp_path)
    assert store.get_session("does-not-exist") is None


def test_mark_converged_drops_remaining_questions():
    """A manually-converged session reports converged even before the cap."""
    session = ConversationSession(session_id="s1")
    session.add_turn(ConversationTurn(turn_id="t1", raw_text="x"))
    session.mark_converged()
    assert session.converged is True


def test_sqlite_store_survives_new_store_instance(tmp_path):
    db_path = tmp_path / "runtime.db"
    store = ConversationStore(repository=SQLiteRuntimeRepository(db_path))
    session = store.new_session(original_demand="loan risk control")
    session.add_turn(ConversationTurn(turn_id="t1", raw_text="first turn"))
    store.save(session)

    reopened = ConversationStore(repository=SQLiteRuntimeRepository(db_path))
    reloaded = reopened.get_session(session.session_id)
    assert reloaded is not None
    assert reloaded.original_demand == "loan risk control"
    assert [turn.turn_id for turn in reloaded.turns] == ["t1"]
    assert reopened.get_session("unknown") is None
