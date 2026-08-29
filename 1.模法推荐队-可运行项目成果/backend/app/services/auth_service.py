"""Local role and institution access-control service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.repositories.model_asset_repository import get_model_asset_repository
from app.schemas.auth import TaskAccessContext, UserContext


ALL_DOMAINS = ["credit_risk", "customer_marketing", "operation_management"]


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str = ""


class AuthConfigurationError(RuntimeError):
    pass


class AuthenticationError(ValueError):
    pass


class EnterpriseJWTAdapter:
    """Verify enterprise JWT/OIDC tokens and map claims to a user context."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def configured(self) -> bool:
        return bool(
            self.settings.AUTH_JWT_ISSUER
            and self.settings.AUTH_JWT_AUDIENCE
            and (self.settings.AUTH_JWT_PUBLIC_KEY or self.settings.AUTH_JWKS_URL)
            and self.settings.AUTH_ADAPTER in {"jwt", "oidc", "bank_sso"}
        )

    def authenticate(self, token: str) -> UserContext:
        if not self.configured():
            raise AuthConfigurationError("real authentication identity source is not configured")
        try:
            import jwt

            key: Any = self.settings.AUTH_JWT_PUBLIC_KEY
            if not key:
                key = jwt.PyJWKClient(self.settings.AUTH_JWKS_URL).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key=key,
                algorithms=self.settings.AUTH_JWT_ALGORITHMS,
                issuer=self.settings.AUTH_JWT_ISSUER,
                audience=self.settings.AUTH_JWT_AUDIENCE,
                options={"require": ["exp", "iat", "sub"]},
            )
        except ImportError as exc:
            raise AuthConfigurationError("PyJWT dependency is unavailable") from exc
        except Exception as exc:
            raise AuthenticationError(exc.__class__.__name__) from exc
        domains = claims.get("permitted_domains") or []
        if isinstance(domains, str):
            domains = [item.strip() for item in domains.split(",") if item.strip()]
        return UserContext(
            user_id=str(claims["sub"]),
            display_name=str(claims.get("name") or claims["sub"]),
            role=str(claims.get("role") or "unknown"),
            institution_id=str(claims.get("institution_id") or ""),
            legal_entity_id=str(claims.get("legal_entity_id") or ""),
            permitted_domains=[str(item) for item in domains],
            can_recommend=bool(claims.get("can_recommend", True)),
            can_invoke_models=bool(claims.get("can_invoke_models", False)),
            can_view_results=bool(claims.get("can_view_results", True)),
            can_view_audit=bool(claims.get("can_view_audit", False)),
        )


def authentication_status() -> dict[str, Any]:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.AUTH_MODE == "demo":
        return {
            "auth_mode": "demo",
            "auth_adapter": "demo_header",
            "auth_configured": True,
            "production_auth_ready": False,
        }
    adapter = EnterpriseJWTAdapter(settings)
    return {
        "auth_mode": "real",
        "auth_adapter": settings.AUTH_ADAPTER,
        "auth_configured": adapter.configured(),
        "production_auth_ready": adapter.configured(),
    }


class AuthService:
    """Small local permission service used before enterprise SSO exists."""

    def __init__(self) -> None:
        self.repository = get_model_asset_repository()
        self._tasks: dict[str, TaskAccessContext] = {}
        self._users: dict[str, UserContext] = {
            "admin": UserContext(
                user_id="admin",
                display_name="系统管理员",
                role="admin",
                institution_id="HEAD",
                legal_entity_id="JSRCU",
                permitted_domains=ALL_DOMAINS,
                can_view_audit=True,
            ),
            "risk_user": UserContext(
                user_id="risk_user",
                display_name="风控人员",
                role="risk_officer",
                institution_id="BR_RISK_001",
                legal_entity_id="JSRCU",
                permitted_domains=["credit_risk"],
            ),
            "business_user": UserContext(
                user_id="business_user",
                display_name="业务人员",
                role="business_user",
                institution_id="BR_MKT_001",
                legal_entity_id="JSRCU",
                permitted_domains=["customer_marketing", "operation_management"],
            ),
            "auditor": UserContext(
                user_id="auditor",
                display_name="审计人员",
                role="auditor",
                institution_id="AUDIT",
                legal_entity_id="JSRCU",
                permitted_domains=ALL_DOMAINS,
                can_invoke_models=False,
                can_view_audit=True,
            ),
        }

    def get_user(self, user_id: str | None) -> UserContext:
        """Return a local user; default admin preserves existing demo compatibility."""
        if not user_id:
            return self._users["admin"]
        if user_id in self._users:
            return self._users[user_id]
        return UserContext(
            user_id=user_id,
            display_name="未知用户",
            role="unknown",
            institution_id="UNKNOWN",
            legal_entity_id="UNKNOWN",
            permitted_domains=[],
            can_recommend=False,
            can_invoke_models=False,
            can_view_results=False,
            can_view_audit=False,
        )

    def list_users(self) -> list[UserContext]:
        return list(self._users.values())

    def can_access_model(
        self,
        user: UserContext,
        model_id: str,
        action: str,
    ) -> AccessDecision:
        """Check whether a user can recommend, invoke, or view a model."""
        model = self.repository.get_model(model_id)
        if model is None:
            return AccessDecision(False, f"模型 {model_id} 不存在")

        domain = model.get("domain", "")
        if domain not in user.permitted_domains:
            return AccessDecision(False, f"用户角色 {user.role} 无权访问 {domain} 模型")

        if action == "recommend" and not user.can_recommend:
            return AccessDecision(False, "当前用户无推荐权限")
        if action == "invoke" and not user.can_invoke_models:
            return AccessDecision(False, "当前用户无模型调用权限")
        if action == "view_result" and not user.can_view_results:
            return AccessDecision(False, "当前用户无结果查看权限")

        return AccessDecision(True)

    def filter_model_ids(
        self,
        user: UserContext,
        model_ids: list[str],
        action: str = "recommend",
    ) -> list[str]:
        return [
            model_id for model_id in model_ids
            if self.can_access_model(user, model_id, action).allowed
        ]

    def register_task(self, task_id: str, model_id: str, user: UserContext) -> None:
        self._tasks[task_id] = TaskAccessContext(
            task_id=task_id,
            model_id=model_id,
            user_id=user.user_id,
            institution_id=user.institution_id,
            legal_entity_id=user.legal_entity_id,
        )

    def can_view_task(self, user: UserContext, task_id: str) -> AccessDecision:
        task = self._tasks.get(task_id)
        if task is None:
            if user.role in {"admin", "auditor"}:
                return AccessDecision(True)
            return AccessDecision(False, "未找到任务访问上下文，无法确认结果查看权限")

        model_decision = self.can_access_model(user, task.model_id, "view_result")
        if not model_decision.allowed:
            return model_decision

        if user.role in {"admin", "auditor"}:
            return AccessDecision(True)
        if user.user_id == task.user_id:
            return AccessDecision(True)
        if user.institution_id == task.institution_id:
            return AccessDecision(True)
        return AccessDecision(False, "当前用户不可查看其他机构或其他用户发起的模型结果")


_auth_service = AuthService()


def get_auth_service() -> AuthService:
    return _auth_service
