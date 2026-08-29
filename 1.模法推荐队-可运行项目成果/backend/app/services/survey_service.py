"""Anonymous, append-only survey collection with honest evidence boundaries."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import threading
import uuid
from typing import Any

from app.repositories.runtime_repository import SQLiteRuntimeRepository, get_runtime_repository
from app.schemas.survey import (
    SurveyCampaignCreateRequest,
    SurveyCampaignInfo,
    SurveyMetricBucket,
    SurveyQuestionDefinition,
    SurveySubmissionRequest,
    SurveySubmissionResponse,
    SurveySummaryResponse,
)


QUESTIONS = [
    SurveyQuestionDefinition(question_id="q1", text="我能理解系统为什么推荐这些模型。", dimension="推荐理由清晰度"),
    SurveyQuestionDefinition(question_id="q2", text="推荐解释能够对应我的业务需求，而不是泛泛而谈。", dimension="需求相关性"),
    SurveyQuestionDefinition(question_id="q3", text="解释中的证据、标签和排序依据能帮助我追溯推荐结论。", dimension="可追溯性"),
    SurveyQuestionDefinition(question_id="q4", text="我能理解推荐模型的适用边界和不适用条件。", dimension="边界理解"),
    SurveyQuestionDefinition(question_id="q5", text="我能理解使用这些模型所需的数据条件和数据缺口。", dimension="数据要求理解"),
    SurveyQuestionDefinition(question_id="q6", text="合规提示、人工复核提示和风险边界表达清楚。", dimension="合规可理解性"),
    SurveyQuestionDefinition(question_id="q7", text="多模型组合的输入输出关系和执行顺序清楚。", dimension="组合方案理解"),
    SurveyQuestionDefinition(question_id="q8", text="报告摘要足以支持我向同事或管理者说明推荐结论。", dimension="汇报可用性"),
]

SENSITIVE_PATTERNS = {
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "national_id": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "bank_card": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    "api_secret": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|(?:api[_-]?key|password|token)\s*[:=]\s*\S+)", re.I),
}


class SurveyError(ValueError):
    """Safe, user-facing survey validation failure."""


class SurveyService:
    def __init__(
        self,
        campaign_dir: Path | None = None,
        response_log_path: Path | None = None,
        repository: SQLiteRuntimeRepository | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        self._default_campaign_dir = root / "data" / "surveys" / "campaigns"
        self._default_response_log_path = root / "data" / "surveys" / "responses.jsonl"
        self.campaign_dir = campaign_dir or self._default_campaign_dir
        self.response_log_path = response_log_path or self._default_response_log_path
        self.campaign_dir.mkdir(parents=True, exist_ok=True)
        self.response_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.repository = repository if repository is not None else (
            get_runtime_repository()
            if campaign_dir is None and response_log_path is None
            else None
        )
        self._lock = threading.Lock()

    def _use_sqlite(self) -> bool:
        return (
            self.repository is not None
            and self.campaign_dir == self._default_campaign_dir
            and self.response_log_path == self._default_response_log_path
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_campaign(self, request: SurveyCampaignCreateRequest) -> tuple[SurveyCampaignInfo, list[str]]:
        if len(set(request.required_roles)) != len(request.required_roles):
            raise SurveyError("必需角色不能重复")
        if len(set(request.required_scenarios)) != len(request.required_scenarios):
            raise SurveyError("必需场景不能重复")
        if request.invite_count < request.minimum_respondents:
            raise SurveyError("邀请码数量不能少于最低受访者数量")

        campaign_id = f"SURV_{uuid.uuid4().hex[:12].upper()}"
        raw_tokens = [secrets.token_urlsafe(24) for _ in range(request.invite_count)]
        campaign = {
            "campaign_id": campaign_id,
            "name": request.name,
            "status": "active",
            "created_at": self._now(),
            "samples_per_respondent": request.samples_per_respondent,
            "minimum_respondents": request.minimum_respondents,
            "evidence_mode": request.evidence_mode,
            "required_roles": list(request.required_roles),
            "required_scenarios": list(request.required_scenarios),
            "invitation_hashes": [self._token_hash(token) for token in raw_tokens],
            "questionnaire_version": "explanation-v1",
        }
        with self._lock:
            self._write_campaign(campaign)
        return self._campaign_info(campaign), raw_tokens

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        if self._use_sqlite():
            assert self.repository is not None
            campaign = self.repository.get("survey_campaigns", campaign_id)
            if campaign is None:
                raise SurveyError("survey campaign does not exist")
            return campaign
        path = self.campaign_dir / f"{campaign_id}.json"
        if not path.exists():
            raise SurveyError("问卷活动不存在")
        try:
            campaign = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SurveyError("问卷活动文件无法读取") from exc
        if not isinstance(campaign, dict) or campaign.get("campaign_id") != campaign_id:
            raise SurveyError("问卷活动文件无效")
        return campaign

    def campaign_info(self, campaign_id: str) -> SurveyCampaignInfo:
        return self._campaign_info(self.get_campaign(campaign_id))

    @staticmethod
    def _campaign_info(campaign: dict[str, Any]) -> SurveyCampaignInfo:
        return SurveyCampaignInfo(
            campaign_id=str(campaign["campaign_id"]),
            name=str(campaign["name"]),
            status=str(campaign.get("status") or "active"),
            created_at=str(campaign["created_at"]),
            samples_per_respondent=int(campaign["samples_per_respondent"]),
            minimum_respondents=int(campaign["minimum_respondents"]),
            required_roles=list(campaign["required_roles"]),
            required_scenarios=list(campaign["required_scenarios"]),
            invitation_count=len(campaign.get("invitation_hashes") or []),
            questionnaire_version=str(campaign.get("questionnaire_version") or "explanation-v1"),
            evidence_mode=str(campaign.get("evidence_mode") or "human_survey"),
        )

    def _write_campaign(self, campaign: dict[str, Any]) -> None:
        if self._use_sqlite():
            assert self.repository is not None
            self.repository.upsert(
                "survey_campaigns",
                str(campaign["campaign_id"]),
                campaign,
                partition_key=str(campaign["campaign_id"]),
                created_at=str(campaign.get("created_at") or ""),
            )
            return
        path = self.campaign_dir / f"{campaign['campaign_id']}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(campaign, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def submit(self, request: SurveySubmissionRequest) -> SurveySubmissionResponse:
        if not request.consent_confirmed:
            raise SurveyError("必须确认匿名评估授权")
        self._reject_sensitive_text(request)

        with self._lock:
            campaign = self.get_campaign(request.campaign_id)
            if campaign.get("status") != "active":
                raise SurveyError("问卷活动已关闭")
            token_hash = self._token_hash(request.invitation_token)
            if not any(secrets.compare_digest(token_hash, value) for value in campaign.get("invitation_hashes") or []):
                raise SurveyError("邀请码无效")
            if request.role not in campaign["required_roles"]:
                raise SurveyError("岗位角色不在本次问卷范围内")
            if request.scenario_id not in campaign["required_scenarios"]:
                raise SurveyError("业务场景不在本次问卷范围内")

            respondent_key = token_hash[:16]
            existing = [row for row in self._read_responses() if row.get("campaign_id") == request.campaign_id and row.get("respondent_key") == respondent_key]
            if any(row.get("sample_id") == request.sample_id for row in existing):
                raise SurveyError("同一受访者不能重复评价同一样例")
            if len(existing) >= int(campaign["samples_per_respondent"]):
                raise SurveyError("该邀请码已完成规定样例数")
            if existing and any(row.get("role") != request.role or row.get("department") != request.department for row in existing):
                raise SurveyError("同一邀请码的部门和岗位必须保持一致")

            response_id = f"SRESP_{uuid.uuid4().hex[:12].upper()}"
            source_type = (
                "human_submitted_identity_unverified"
                if campaign.get("evidence_mode", "human_survey") == "human_survey"
                else "automated_acceptance_test_non_evidence"
            )
            row = {
                "response_id": response_id,
                "submitted_at": self._now(),
                "campaign_id": request.campaign_id,
                "respondent_key": respondent_key,
                "sample_id": request.sample_id,
                "scenario_id": request.scenario_id,
                "department": request.department,
                "role": request.role,
                "answers": request.answers.model_dump(),
                "open_feedback": request.open_feedback.model_dump(),
                "consent_confirmed": True,
                "source_type": source_type,
            }
            required = int(campaign["samples_per_respondent"])
            if self._use_sqlite():
                assert self.repository is not None
                partition_key = f"{request.campaign_id}:{respondent_key}"
                _, created, accepted, status = self.repository.insert_with_partition_limit(
                    "survey_responses",
                    response_id,
                    row,
                    partition_key=partition_key,
                    idempotency_key=f"{partition_key}:{request.sample_id}",
                    max_records=required,
                    consistent_fields=("role", "department"),
                    created_at=row["submitted_at"],
                )
                if not created:
                    if status == "duplicate":
                        raise SurveyError("same respondent cannot evaluate the same sample twice")
                    if status == "limit":
                        raise SurveyError("invitation has completed the required number of samples")
                    raise SurveyError("department and role must remain consistent for one invitation")
            else:
                with self.response_log_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                accepted = len(existing) + 1
            return SurveySubmissionResponse(
                response_id=response_id,
                accepted_samples=accepted,
                required_samples=required,
                respondent_complete=accepted >= required,
            )

    def _reject_sensitive_text(self, request: SurveySubmissionRequest) -> None:
        feedback = request.open_feedback.model_dump()
        for field, value in feedback.items():
            for kind, pattern in SENSITIVE_PATTERNS.items():
                if pattern.search(value):
                    raise SurveyError(f"开放反馈疑似包含敏感信息（{field}/{kind}），请删除后提交")

    def _read_responses(self) -> list[dict[str, Any]]:
        if self._use_sqlite():
            assert self.repository is not None
            return self.repository.list("survey_responses")
        if not self.response_log_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.response_log_path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
        return rows

    @staticmethod
    def _bucket(values: list[int]) -> SurveyMetricBucket:
        if not values:
            return SurveyMetricBucket()
        return SurveyMetricBucket(
            count=len(values),
            average_score=round(sum(values) / len(values), 2),
            understandable_rate_pct=round(sum(int(value >= 4) for value in values) / len(values) * 100, 2),
        )

    def summary(self, campaign_id: str) -> SurveySummaryResponse:
        campaign = self.get_campaign(campaign_id)
        rows = [row for row in self._read_responses() if row.get("campaign_id") == campaign_id]
        by_respondent: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_respondent.setdefault(str(row.get("respondent_key") or ""), []).append(row)
        required_samples = int(campaign["samples_per_respondent"])
        complete_keys = {key for key, values in by_respondent.items() if len(values) >= required_samples}
        scored = [row for row in rows if row.get("respondent_key") in complete_keys]

        question_values = {question.question_id: [] for question in QUESTIONS}
        role_values: dict[str, list[int]] = {}
        scenario_values: dict[str, list[int]] = {}
        all_values: list[int] = []
        for row in scored:
            answers = row.get("answers") or {}
            values = [int(answers.get(question.question_id, 0)) for question in QUESTIONS]
            for question, value in zip(QUESTIONS, values):
                question_values[question.question_id].append(value)
            role_values.setdefault(str(row.get("role") or "unknown"), []).extend(values)
            scenario_values.setdefault(str(row.get("scenario_id") or "unknown"), []).extend(values)
            all_values.extend(values)

        per_question = {key: self._bucket(values) for key, values in question_values.items()}
        per_role = {key: self._bucket(values) for key, values in sorted(role_values.items())}
        per_scenario = {key: self._bucket(values) for key, values in sorted(scenario_values.items())}
        represented_roles = {row.get("role") for row in scored}
        represented_scenarios = {row.get("scenario_id") for row in scored}
        missing_roles = sorted(set(campaign["required_roles"]) - represented_roles)
        missing_scenarios = sorted(set(campaign["required_scenarios"]) - represented_scenarios)
        low_dimensions = sorted(
            question_id for question_id, bucket in per_question.items()
            if bucket.count and bucket.understandable_rate_pct < 85.0
        )
        comprehensibility = self._bucket(all_values).understandable_rate_pct
        enough_people = len(complete_keys) >= int(campaign["minimum_respondents"])
        is_human_campaign = campaign.get("evidence_mode", "human_survey") == "human_survey"
        threshold_met = bool(
            is_human_campaign
            and
            enough_people
            and not missing_roles
            and not missing_scenarios
            and not low_dimensions
            and comprehensibility >= 90.0
        )
        if not is_human_campaign:
            status = "acceptance_test_non_evidence"
        elif not enough_people or missing_roles or missing_scenarios:
            status = "collecting"
        elif not threshold_met:
            status = "metric_below_target"
        else:
            status = "eligible_for_external_identity_verification"
        return SurveySummaryResponse(
            campaign_id=campaign_id,
            total_submissions=len(rows),
            unique_invited_respondents=len(by_respondent),
            complete_respondents=len(complete_keys),
            scored_responses=len(scored),
            core_answer_count=len(all_values),
            understandable_count=sum(int(value >= 4) for value in all_values),
            comprehensibility_pct=comprehensibility,
            per_question=per_question,
            per_role=per_role,
            per_scenario=per_scenario,
            missing_required_roles=missing_roles,
            missing_required_scenarios=missing_scenarios,
            low_dimensions=low_dimensions,
            metric_threshold_met=threshold_met,
            formal_evidence_verified=False,
            evidence_status=status,
            source_type=(
                "human_submitted_identity_unverified"
                if is_human_campaign
                else "automated_acceptance_test_non_evidence"
            ),
        )

    def export_csv(self, campaign_id: str) -> str:
        self.get_campaign(campaign_id)
        rows = [row for row in self._read_responses() if row.get("campaign_id") == campaign_id]
        output = io.StringIO(newline="")
        fields = [
            "response_id", "submitted_at", "respondent_key", "sample_id", "scenario_id",
            "department", "role", "q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8",
            "most_helpful", "still_unclear", "main_risk", "desired_improvements", "source_type",
        ]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat = {key: row.get(key, "") for key in fields}
            flat.update(row.get("answers") or {})
            flat.update(row.get("open_feedback") or {})
            writer.writerow({key: self._csv_safe_cell(value) for key, value in flat.items()})
        return "\ufeff" + output.getvalue()

    @staticmethod
    def _csv_safe_cell(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value


_survey_service = SurveyService()


def get_survey_service() -> SurveyService:
    return _survey_service
