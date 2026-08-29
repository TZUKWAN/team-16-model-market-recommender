"""Auditable hybrid retrieval over factual model knowledge cards.

The default path uses character n-gram TF-IDF because it is deterministic,
fast for the small model catalog, and handles Chinese text without requiring a
segmenter. An optional SentenceTransformer-compatible dense encoder can be
enabled for BGE-M3 (or another locally deployed embedding model). Dense model
loading is lazy and a missing optional dependency never fabricates a score.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import threading
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


logger = logging.getLogger(__name__)


class DenseRetrievalUnavailableError(RuntimeError):
    """Raised when competition mode requires dense retrieval but it is unavailable."""

    def __init__(self, status: dict[str, Any]):
        self.status = dict(status)
        super().__init__(
            "required dense retrieval is unavailable "
            f"({self.status.get('dense_error_code') or 'unknown'})"
        )


@dataclass(frozen=True)
class HybridRetrievalScore:
    """Inspectable retrieval scores for one model candidate."""

    sparse_full: float = 0.0
    sparse_title: float = 0.0
    sparse_score: float = 0.0
    dense_score: float = 0.0
    retrieval_score: float = 0.0


class HybridModelRetriever:
    """Build model knowledge cards and score them against a business demand."""

    def __init__(
        self,
        *,
        full_text_weight: float = 0.72,
        title_text_weight: float = 0.28,
        dense_enabled: bool = False,
        dense_weight: float = 0.0,
        dense_model: str = "BAAI/bge-m3",
        dense_encoder: Any | None = None,
        dense_cache_enabled: bool = True,
        dense_cache_dir: str | Path | None = None,
        runtime_mode: str = "light",
        dense_required: bool = False,
        dense_offline: bool = False,
        dense_expected_dimension: int = 0,
        dense_expected_revision: str = "",
        dense_manifest_path: str | Path | None = None,
        dense_verify_manifest: bool = False,
        dense_config_error: str = "",
    ) -> None:
        self.full_text_weight = float(full_text_weight)
        self.title_text_weight = float(title_text_weight)
        self.dense_enabled = bool(dense_enabled)
        self.dense_weight = max(0.0, min(1.0, float(dense_weight)))
        self.dense_model = str(dense_model or "BAAI/bge-m3")
        self._dense_encoder = dense_encoder
        self._dense_load_attempted = dense_encoder is not None
        self.dense_cache_enabled = bool(dense_cache_enabled)
        self.dense_cache_dir = Path(dense_cache_dir).resolve() if dense_cache_dir else None
        self.runtime_mode = str(runtime_mode or "light").strip().lower()
        self.dense_required = bool(dense_required)
        self.dense_offline = bool(dense_offline)
        self.dense_expected_dimension = max(0, int(dense_expected_dimension))
        self.dense_expected_revision = str(dense_expected_revision or "").strip().lower()
        self.dense_manifest_path = (
            Path(dense_manifest_path).resolve() if dense_manifest_path else None
        )
        self.dense_verify_manifest = bool(dense_verify_manifest)
        self.dense_config_error = str(dense_config_error or "")
        self._dense_cache_hit = False
        self._dense_available = False
        self._dense_dimension = 0
        self._dense_error_code = ""
        self._dense_manifest_verified = False
        self._dense_checked_at = ""
        self._dense_load_lock = threading.Lock()

        self._signature = ""
        self._model_ids: list[str] = []
        self._full_vectorizer: TfidfVectorizer | None = None
        self._title_vectorizer: TfidfVectorizer | None = None
        self._full_matrix: Any | None = None
        self._title_matrix: Any | None = None
        self._dense_matrix: np.ndarray | None = None
        self.last_audit: dict[str, Any] = {}

    def runtime_status(self) -> dict[str, Any]:
        """Return non-sensitive dense runtime readiness for health and diagnostics."""
        return {
            "retrieval_runtime_mode": self.runtime_mode,
            "dense_requested": bool(self.dense_enabled and self.dense_weight > 0),
            "dense_required": self.dense_required,
            "dense_initialized": self._dense_load_attempted,
            "dense_available": self._dense_available,
            "dense_model": self.dense_model if self.dense_enabled else "",
            "dense_weight": self.dense_weight if self.dense_enabled else 0.0,
            "dense_embedding_dimension": self._dense_dimension,
            "dense_expected_dimension": self.dense_expected_dimension,
            "dense_expected_revision": self.dense_expected_revision,
            "dense_offline": self.dense_offline,
            "dense_manifest_required": self.dense_verify_manifest,
            "dense_manifest_verified": self._dense_manifest_verified,
            "dense_cache_enabled": self.dense_cache_enabled,
            "dense_cache_ready": bool(
                self.dense_cache_enabled
                and self.dense_cache_dir is not None
                and self.dense_cache_dir.exists()
            ),
            "dense_cache_hit": self._dense_cache_hit,
            "dense_error_code": self._dense_error_code,
            "dense_config_error": self.dense_config_error,
            "dense_checked_at": self._dense_checked_at,
        }

    def warmup(self, models: list[dict[str, Any]]) -> dict[str, Any]:
        """Load and verify the configured dense runtime using factual model cards."""
        if not models:
            self._set_dense_error("MODEL_CATALOG_EMPTY")
            if self.dense_required:
                raise DenseRetrievalUnavailableError(self.runtime_status())
            return self.runtime_status()
        if self.dense_config_error:
            self._set_dense_error(self.dense_config_error)
            if self.dense_required:
                raise DenseRetrievalUnavailableError(self.runtime_status())
            return self.runtime_status()
        self.score("模型市场语义检索运行状态探针", models)
        return self.runtime_status()

    @staticmethod
    def _list_text(value: Any) -> str:
        if isinstance(value, list | tuple | set):
            return " ".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip()

    @classmethod
    def title_text(cls, model: dict[str, Any]) -> str:
        """Return high-precision identity text without synthetic performance data."""
        return " ".join(
            part
            for part in (
                str(model.get("model_name") or "").strip(),
                str(model.get("canonical_name") or "").strip(),
                cls._list_text(model.get("aliases")),
            )
            if part
        )

    @classmethod
    def knowledge_card_text(cls, model: dict[str, Any]) -> str:
        """Build searchable text only from factual model catalog fields."""
        fields = (
            cls.title_text(model),
            str(model.get("description") or "").strip(),
            cls._list_text(model.get("business_scenario")),
            cls._list_text(model.get("business_stage")),
            cls._list_text(model.get("customer_segment")),
            cls._list_text(model.get("tags")),
            cls._list_text(model.get("model_capability")),
            cls._list_text(model.get("input_fields_required")),
            cls._list_text(model.get("output_fields")),
            str(model.get("applicable_conditions") or model.get("applicable_boundary") or "").strip(),
            str(model.get("unsuitable_conditions") or "").strip(),
            str(model.get("compliance_boundary") or model.get("legal_boundary") or "").strip(),
        )
        return " ".join(part for part in fields if part)

    def score(self, query_text: str, models: list[dict[str, Any]]) -> dict[str, HybridRetrievalScore]:
        """Return per-model sparse/dense scores in the 0-1 range."""
        query = str(query_text or "").strip()
        if not query or not models:
            if self.dense_required:
                self._set_dense_error("EMPTY_DENSE_PROBE")
                raise DenseRetrievalUnavailableError(self.runtime_status())
            self.last_audit = {
                "enabled": True,
                "candidate_count": len(models),
                "query_nonempty": bool(query),
                "dense_requested": self.dense_enabled,
                "dense_available": False,
                "mode": "empty",
            }
            return {
                str(model.get("model_id") or ""): HybridRetrievalScore()
                for model in models
                if model.get("model_id")
            }

        self._ensure_index(models)
        assert self._full_vectorizer is not None and self._title_vectorizer is not None
        assert self._full_matrix is not None and self._title_matrix is not None

        sparse_full = cosine_similarity(
            self._full_vectorizer.transform([query]), self._full_matrix
        )[0]
        sparse_title = cosine_similarity(
            self._title_vectorizer.transform([query]), self._title_matrix
        )[0]
        sparse = self.full_text_weight * sparse_full + self.title_text_weight * sparse_title

        dense_available = False
        dense = np.zeros(len(models), dtype=float)
        if self.dense_required and (not self.dense_enabled or self.dense_weight <= 0):
            self._set_dense_error("DENSE_DISABLED_OR_ZERO_WEIGHT")
            raise DenseRetrievalUnavailableError(self.runtime_status())
        if self.dense_enabled and self.dense_weight > 0:
            encoder = self._get_dense_encoder()
            if encoder is not None and self._dense_matrix is not None:
                query_vector = self._encode_dense(encoder, [query])
                if query_vector is not None:
                    dense = cosine_similarity(query_vector, self._dense_matrix)[0]
                    dense = np.clip(dense, 0.0, 1.0)
                    dense_available = True

        if dense_available:
            self._dense_available = True
            self._dense_error_code = ""
            self._dense_checked_at = self._utc_now()
        elif self.dense_enabled and self.dense_weight > 0 and not self._dense_error_code:
            self._set_dense_error("DENSE_RUNTIME_UNAVAILABLE")

        if self.dense_required and not dense_available:
            raise DenseRetrievalUnavailableError(self.runtime_status())

        effective_dense_weight = self.dense_weight if dense_available else 0.0
        retrieval = sparse * (1.0 - effective_dense_weight) + dense * effective_dense_weight
        scores = {
            model_id: HybridRetrievalScore(
                sparse_full=round(float(sparse_full[index]), 6),
                sparse_title=round(float(sparse_title[index]), 6),
                sparse_score=round(float(sparse[index]), 6),
                dense_score=round(float(dense[index]), 6),
                retrieval_score=round(float(retrieval[index]), 6),
            )
            for index, model_id in enumerate(self._model_ids)
        }
        self.last_audit = {
            "enabled": True,
            "candidate_count": len(models),
            "query_nonempty": True,
            "dense_requested": self.dense_enabled,
            "dense_available": dense_available,
            "dense_model": self.dense_model if self.dense_enabled else "",
            "dense_weight": effective_dense_weight,
            "dense_index_cache_enabled": self.dense_cache_enabled,
            "dense_index_cache_hit": self._dense_cache_hit,
            "dense_embedding_dimension": self._dense_dimension,
            "dense_manifest_verified": self._dense_manifest_verified,
            "dense_error_code": self._dense_error_code,
            "retrieval_runtime_mode": self.runtime_mode,
            "full_text_weight": self.full_text_weight,
            "title_text_weight": self.title_text_weight,
            "mode": "sparse+dense" if dense_available else "sparse",
        }
        return scores

    def _ensure_index(self, models: list[dict[str, Any]]) -> None:
        model_ids = [str(model.get("model_id") or "") for model in models]
        full_docs = [self.knowledge_card_text(model) or model_ids[index] for index, model in enumerate(models)]
        title_docs = [self.title_text(model) or model_ids[index] for index, model in enumerate(models)]
        digest = hashlib.sha256()
        for model_id, title, full in zip(model_ids, title_docs, full_docs):
            digest.update(model_id.encode("utf-8"))
            digest.update(b"\0")
            digest.update(title.encode("utf-8"))
            digest.update(b"\0")
            digest.update(full.encode("utf-8"))
            digest.update(b"\0")
        signature = digest.hexdigest()
        if signature == self._signature:
            return

        self._model_ids = model_ids
        self._full_vectorizer = TfidfVectorizer(
            analyzer="char", ngram_range=(2, 5), sublinear_tf=True, norm="l2"
        )
        self._title_vectorizer = TfidfVectorizer(
            analyzer="char", ngram_range=(2, 6), sublinear_tf=True, norm="l2"
        )
        self._full_matrix = self._full_vectorizer.fit_transform(full_docs)
        self._title_matrix = self._title_vectorizer.fit_transform(title_docs)
        self._dense_matrix = None
        self._dense_cache_hit = False

        if self.dense_enabled and self.dense_weight > 0:
            encoder = self._get_dense_encoder()
            if encoder is not None:
                self._dense_matrix = self._load_dense_cache(signature, len(full_docs))
                if self._dense_matrix is not None:
                    self._dense_cache_hit = True
                else:
                    self._dense_matrix = self._encode_dense(encoder, full_docs)
                    if self._dense_matrix is not None:
                        self._save_dense_cache(signature, self._dense_matrix)
        self._signature = signature

    def _dense_cache_path(self, signature: str) -> Path | None:
        if not self.dense_cache_enabled or self.dense_cache_dir is None:
            return None
        cache_key = hashlib.sha256(
            f"knowledge-card-v1\0{self.dense_model}\0{signature}".encode("utf-8")
        ).hexdigest()
        return self.dense_cache_dir / f"{cache_key}.npz"

    def _load_dense_cache(self, signature: str, expected_rows: int) -> np.ndarray | None:
        path = self._dense_cache_path(signature)
        if path is None or not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as payload:
                matrix = np.asarray(payload["matrix"], dtype=float)
            if matrix.ndim != 2 or matrix.shape[0] != expected_rows or not np.isfinite(matrix).all():
                raise ValueError("invalid dense cache shape or values")
            if self.dense_expected_dimension and matrix.shape[1] != self.dense_expected_dimension:
                raise ValueError("dense cache dimension mismatch")
            self._dense_dimension = int(matrix.shape[1])
            return matrix
        except Exception as exc:
            logger.warning("Dense index cache ignored (%s)", exc.__class__.__name__)
            return None

    def _save_dense_cache(self, signature: str, matrix: np.ndarray) -> None:
        path = self._dense_cache_path(signature)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            with temporary.open("wb") as handle:
                np.savez_compressed(handle, matrix=np.asarray(matrix, dtype=np.float32))
            temporary.replace(path)
        except Exception as exc:
            logger.warning("Dense index cache write failed (%s)", exc.__class__.__name__)

    def _get_dense_encoder(self) -> Any | None:
        if self._dense_encoder is not None:
            return self._dense_encoder
        if self._dense_load_attempted:
            return None
        with self._dense_load_lock:
            if self._dense_encoder is not None:
                return self._dense_encoder
            if self._dense_load_attempted:
                return None
            self._dense_load_attempted = True
            try:
                if self.dense_verify_manifest and not self._verify_dense_manifest():
                    return None
                from sentence_transformers import SentenceTransformer

                self._dense_encoder = SentenceTransformer(
                    self.dense_model,
                    local_files_only=self.dense_offline,
                )
            except Exception as exc:  # optional dependency/model cache/network boundary
                self._set_dense_error(exc.__class__.__name__.upper())
                logger.warning(
                    "Dense retriever unavailable (%s); using sparse retrieval",
                    exc.__class__.__name__,
                )
                self._dense_encoder = None
        return self._dense_encoder

    def _encode_dense(self, encoder: Any, texts: list[str]) -> np.ndarray | None:
        try:
            vectors = encoder.encode(texts, normalize_embeddings=True)
            array = np.asarray(vectors, dtype=float)
            if array.ndim != 2 or array.shape[0] != len(texts) or not np.isfinite(array).all():
                raise ValueError("invalid dense embedding shape or values")
            if self.dense_expected_dimension and array.shape[1] != self.dense_expected_dimension:
                raise ValueError(
                    f"dense embedding dimension {array.shape[1]} does not match "
                    f"expected {self.dense_expected_dimension}"
                )
            self._dense_dimension = int(array.shape[1])
            return array
        except Exception as exc:
            self._set_dense_error(exc.__class__.__name__.upper())
            logger.warning("Dense encoding failed (%s); using sparse retrieval", exc.__class__.__name__)
            return None

    def _verify_dense_manifest(self) -> bool:
        """Verify every declared local model artifact before offline loading."""
        if self.dense_manifest_path is None:
            self._set_dense_error("DENSE_MANIFEST_NOT_CONFIGURED")
            return False
        model_root = Path(self.dense_model).resolve()
        if not model_root.is_dir() or not self.dense_manifest_path.is_file():
            self._set_dense_error("DENSE_ARTIFACT_MISSING")
            return False
        try:
            manifest = json.loads(self.dense_manifest_path.read_text(encoding="utf-8"))
            if int(manifest.get("schema_version", 0)) != 1:
                raise ValueError("unsupported manifest schema")
            resolved_revision = str(manifest.get("resolved_revision") or "").strip().lower()
            if self.dense_expected_revision and resolved_revision != self.dense_expected_revision:
                raise ValueError("manifest revision mismatch")
            manifest_dimension = int(manifest.get("embedding_dimension", 0))
            if self.dense_expected_dimension and manifest_dimension != self.dense_expected_dimension:
                raise ValueError("manifest embedding dimension mismatch")
            files = manifest.get("files")
            if not isinstance(files, list) or not files:
                raise ValueError("manifest has no files")
            for item in files:
                relative = Path(str(item.get("path") or ""))
                if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe manifest path")
                path = (model_root / relative).resolve()
                if not path.is_relative_to(model_root) or not path.is_file():
                    raise FileNotFoundError(relative.as_posix())
                expected_size = int(item.get("size", -1))
                if path.stat().st_size != expected_size:
                    raise ValueError("artifact size mismatch")
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != str(item.get("sha256") or ""):
                    raise ValueError("artifact checksum mismatch")
            self._dense_manifest_verified = True
            self._dense_checked_at = self._utc_now()
            return True
        except Exception as exc:
            self._dense_manifest_verified = False
            self._set_dense_error(f"MANIFEST_{exc.__class__.__name__.upper()}")
            logger.warning("Dense model manifest verification failed (%s)", exc.__class__.__name__)
            return False

    def _set_dense_error(self, code: str) -> None:
        self._dense_available = False
        self._dense_error_code = str(code or "DENSE_RUNTIME_UNAVAILABLE")
        self._dense_checked_at = self._utc_now()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
