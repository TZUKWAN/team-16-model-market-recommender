import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CircleCheck, ClipboardList, LogIn, Send, X } from 'lucide-react';
import { getSurveyDefinition, submitSurveyResponse } from '../api/client';
import type {
  SurveyAccess,
  SurveyAnswers,
  SurveyDefinitionResponse,
  SurveyOpenFeedback,
  SurveyRole,
  SurveyScenario,
} from '../types';

interface SurveyPanelProps {
  open: boolean;
  sampleId: string;
  scenarioId: SurveyScenario;
  access: SurveyAccess;
  onAccessChange: (access: SurveyAccess) => void;
  onClose: () => void;
}

const ROLE_OPTIONS: Array<{ value: SurveyRole; label: string }> = [
  { value: 'business', label: '业务' },
  { value: 'risk', label: '风控' },
  { value: 'product', label: '产品' },
  { value: 'operations', label: '运营' },
  { value: 'compliance', label: '合规' },
  { value: 'technology', label: '科技' },
];

const EMPTY_ANSWERS: SurveyAnswers = {
  q1: 0,
  q2: 0,
  q3: 0,
  q4: 0,
  q5: 0,
  q6: 0,
  q7: 0,
  q8: 0,
};

const SurveyPanel: React.FC<SurveyPanelProps> = ({
  open,
  sampleId,
  scenarioId,
  access,
  onAccessChange,
  onClose,
}) => {
  const [campaignId, setCampaignId] = useState(access.campaignId);
  const [invitationToken, setInvitationToken] = useState(access.invitationToken);
  const [definition, setDefinition] = useState<SurveyDefinitionResponse | null>(null);
  const [department, setDepartment] = useState<SurveyRole>('business');
  const [role, setRole] = useState<SurveyRole>('business');
  const [answers, setAnswers] = useState<SurveyAnswers>(EMPTY_ANSWERS);
  const [feedback, setFeedback] = useState<SurveyOpenFeedback>({});
  const [consent, setConsent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setCampaignId(access.campaignId);
    setInvitationToken(access.invitationToken);
  }, [access]);

  useEffect(() => {
    if (!open) {
      setDefinition(null);
      setError('');
      setSuccess('');
      setAnswers(EMPTY_ANSWERS);
      setFeedback({});
      setConsent(false);
    }
  }, [open]);

  useEffect(() => {
    const firstRole = definition?.campaign.required_roles[0];
    if (firstRole) {
      setRole(firstRole);
      setDepartment(firstRole);
    }
  }, [definition]);

  useEffect(() => {
    if (!open) return undefined;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const focusableSelector = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';
    const focusFirst = () => {
      const first = dialog?.querySelector<HTMLElement>(focusableSelector);
      (first ?? dialog)?.focus();
    };
    const frame = window.requestAnimationFrame(focusFirst);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;
      const controls = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector));
      if (controls.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('keydown', handleKeyDown);
      opener?.focus();
    };
  }, [open]);

  const allAnswered = useMemo(
    () => Object.values(answers).every((value) => value >= 1 && value <= 5),
    [answers]
  );

  if (!open) return null;

  const loadDefinition = async () => {
    const normalizedCampaign = campaignId.trim().toUpperCase();
    const normalizedToken = invitationToken.trim();
    if (!normalizedCampaign || !normalizedToken) {
      setError('请输入活动编号和邀请码。');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await getSurveyDefinition(normalizedCampaign);
      if (result.campaign.status !== 'active') {
        throw new Error('问卷活动已关闭。');
      }
      if (!result.campaign.required_scenarios.includes(scenarioId)) {
        throw new Error('当前推荐场景不在本次问卷范围内。');
      }
      setDefinition(result);
      onAccessChange({ campaignId: normalizedCampaign, invitationToken: normalizedToken });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '问卷加载失败。');
    } finally {
      setLoading(false);
    }
  };

  const submit = async () => {
    if (!definition || !allAnswered || !consent) {
      setError('请完成8项评分并确认匿名评估授权。');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const result = await submitSurveyResponse({
        campaign_id: definition.campaign.campaign_id,
        invitation_token: invitationToken.trim(),
        sample_id: sampleId,
        scenario_id: scenarioId,
        department,
        role,
        answers,
        open_feedback: feedback,
        consent_confirmed: true,
      });
      setSuccess(
        result.respondent_complete
          ? `已完成 ${result.accepted_samples}/${result.required_samples} 个样例。`
          : `已提交 ${result.accepted_samples}/${result.required_samples} 个样例。`
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '问卷提交失败。');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="survey-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        ref={dialogRef}
        className="survey-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="survey-title"
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="survey-modal-header">
          <div>
            <span className="survey-kicker">当前推荐样例</span>
            <h2 id="survey-title"><ClipboardList size={20} />解释理解度问卷</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} title="关闭问卷" aria-label="关闭问卷">
            <X size={20} />
          </button>
        </header>

        <div className="survey-modal-body">
          {!definition && (
            <div className="survey-access-grid">
              <label>
                <span>活动编号</span>
                <input value={campaignId} onChange={(event) => setCampaignId(event.target.value)} placeholder="SURV_..." />
              </label>
              <label>
                <span>匿名邀请码</span>
                <input
                  type="password"
                  value={invitationToken}
                  onChange={(event) => setInvitationToken(event.target.value)}
                  autoComplete="off"
                />
              </label>
              <button type="button" className="btn btn-primary survey-enter-button" onClick={loadDefinition} disabled={loading}>
                <LogIn size={17} />{loading ? '正在加载' : '进入问卷'}
              </button>
            </div>
          )}

          {definition && !success && (
            <>
              <div className="survey-context-row">
                <label>
                  <span>部门类别</span>
                  <select value={department} onChange={(event) => setDepartment(event.target.value as SurveyRole)}>
                    {ROLE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <label>
                  <span>岗位角色</span>
                  <select value={role} onChange={(event) => setRole(event.target.value as SurveyRole)}>
                    {ROLE_OPTIONS.filter((option) => definition.campaign.required_roles.includes(option.value)).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
              </div>

              <div className="survey-question-list">
                {definition.questions.map((question, index) => {
                  const key = question.question_id as keyof SurveyAnswers;
                  return (
                    <fieldset key={question.question_id} className="survey-question">
                      <legend><span>{index + 1}</span>{question.text}</legend>
                      <div className="survey-scale" aria-label={question.dimension}>
                        {[1, 2, 3, 4, 5].map((score) => (
                          <label key={score} className={answers[key] === score ? 'selected' : ''}>
                            <input
                              type="radio"
                              name={question.question_id}
                              value={score}
                              checked={answers[key] === score}
                              onChange={() => setAnswers((current) => ({ ...current, [key]: score }))}
                            />
                            <span>{score}</span>
                          </label>
                        ))}
                      </div>
                    </fieldset>
                  );
                })}
              </div>

              <div className="survey-feedback-grid">
                <label><span>最有帮助的部分</span><textarea value={feedback.most_helpful || ''} onChange={(event) => setFeedback((current) => ({ ...current, most_helpful: event.target.value }))} /></label>
                <label><span>仍不清楚的部分</span><textarea value={feedback.still_unclear || ''} onChange={(event) => setFeedback((current) => ({ ...current, still_unclear: event.target.value }))} /></label>
                <label><span>最担心的风险</span><textarea value={feedback.main_risk || ''} onChange={(event) => setFeedback((current) => ({ ...current, main_risk: event.target.value }))} /></label>
                <label><span>希望增加的能力</span><textarea value={feedback.desired_improvements || ''} onChange={(event) => setFeedback((current) => ({ ...current, desired_improvements: event.target.value }))} /></label>
              </div>

              <label className="survey-consent">
                <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
                <span>同意将匿名答卷用于系统评估，不填写个人或银行敏感信息。</span>
              </label>
            </>
          )}

          {success && (
            <div className="survey-success" role="status">
              <CircleCheck size={30} />
              <strong>{success}</strong>
            </div>
          )}

          {error && <div className="survey-error" role="alert">{error}</div>}
        </div>

        <footer className="survey-modal-footer">
          <span className="survey-sample-id">样例 {sampleId}</span>
          {definition && !success && (
            <button type="button" className="btn btn-primary" onClick={submit} disabled={submitting || !allAnswered || !consent}>
              <Send size={17} />{submitting ? '正在提交' : '提交答卷'}
            </button>
          )}
          {success && <button type="button" className="btn btn-primary" onClick={onClose}>完成</button>}
        </footer>
      </section>
    </div>
  );
};

export default SurveyPanel;
