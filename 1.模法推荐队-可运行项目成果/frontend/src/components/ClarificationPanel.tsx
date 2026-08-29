import React, { useEffect, useState } from 'react';
import type { ClarificationQuestion } from '../types';

interface ClarificationPanelProps {
  questions: ClarificationQuestion[];
  onResolve: (answers: ClarificationQuestion[]) => void;
  disabled: boolean;
}

const ClarificationPanel: React.FC<ClarificationPanelProps> = ({
  questions,
  onResolve,
  disabled,
}) => {
  const [answers, setAnswers] = useState<ClarificationQuestion[]>(
    questions.map((q) => ({ ...q, user_answer: '' }))
  );

  useEffect(() => {
    setAnswers(questions.map((q) => ({ ...q, user_answer: '' })));
  }, [questions]);

  if (!questions || questions.length === 0) {
    return (
      <div className="card clarification-panel no-clarification">
        <h3 className="card-title">需求确认</h3>
        <p className="no-clarification-text">需求信息较完整，无需额外追问。</p>
      </div>
    );
  }

  const handleSelect = (questionId: string, option: string) => {
    setAnswers((prev) =>
      prev.map((a) =>
        a.question_id === questionId ? { ...a, user_answer: option } : a
      )
    );
  };

  const handleTextInput = (questionId: string, value: string) => {
    setAnswers((prev) =>
      prev.map((a) =>
        a.question_id === questionId ? { ...a, user_answer: value } : a
      )
    );
  };

  const canSubmit = answers.every((a) => a.user_answer && a.user_answer.trim() !== '');
  const hasInteraction = questions.length > 0;

  return (
    <div className="card clarification-panel">
      <h3 className="card-title">
        智能追问
      </h3>
      <p className="clarification-hint">
        系统需要补充以下信息以提供更精准的推荐：
      </p>

      {questions.map((q, idx) => {
        const answer = answers.find((a) => a.question_id === q.question_id);

        return (
          <div key={q.question_id} className="clarification-item">
            <div className="clarification-question">
              <span className="question-number">Q{idx + 1}</span>
              {q.question_text}
            </div>

            {q.options && q.options.length > 0 ? (
              <div className="clarification-options">
                {q.options.map((opt) => (
                  <button
                    key={opt}
                    className={`btn btn-option ${answer?.user_answer === opt ? 'selected' : ''}`}
                    onClick={() => handleSelect(q.question_id, opt)}
                    disabled={disabled}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            ) : (
              <input
                type="text"
                className="clarification-input"
                placeholder="请输入您的补充信息..."
                value={answer?.user_answer || ''}
                onChange={(e) => handleTextInput(q.question_id, e.target.value)}
                disabled={disabled}
              />
            )}
          </div>
        );
      })}

      {hasInteraction && (
        <button
          className="btn btn-primary"
          onClick={() => onResolve(answers)}
          disabled={!canSubmit || disabled}
        >
          {disabled ? '重新解析中...' : '提交补充信息'}
        </button>
      )}
    </div>
  );
};

export default ClarificationPanel;
