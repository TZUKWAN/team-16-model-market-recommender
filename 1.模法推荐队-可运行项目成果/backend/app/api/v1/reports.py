"""
Report generation endpoint - POST /api/v1/reports/recommendation
Uses ReportGenerationService for real report content.
"""

from datetime import datetime, timezone
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.core.security import get_current_user
from app.schemas.auth import UserContext
from app.schemas.report import ReportRequest, ReportResponse
from app.services.audit_service import get_audit_service
from app.services.report_exporter import get_report_exporter
from app.services.report_service import ReportGenerationService

router = APIRouter()
_service = ReportGenerationService()
logger = logging.getLogger(__name__)


@router.post("/reports/recommendation", response_model=ReportResponse)
async def generate_report(
    request: ReportRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Generate a recommendation report."""
    try:
        parse_result = request.parse_result or {}
        if request.demand_raw and not parse_result.get("raw_text"):
            parse_result = {**parse_result, "raw_text": request.demand_raw}

        recommend_result = request.recommend_result or {}
        if not recommend_result and request.recommendations:
            recommend_result = {"recommendations": request.recommendations}

        composition_result = request.composition_result or request.composition or {}

        report = _service.generate(
            request_id=request.request_id,
            parse_result=parse_result,
            recommend_result=recommend_result,
            composition_result=composition_result,
            model_result=request.model_result,
            include_details=request.include_details,
        )
        get_audit_service().record(
            "report_generate",
            current_user,
            request_id=report.request_id,
            status="success",
            payload_summary={
                "report_id": report.report_id,
                "generation_source": report.generation_source,
                "include_details": request.include_details,
                "recommendation_count": len(recommend_result.get("recommendations", [])),
                "has_model_result": bool(request.model_result),
            },
        )
        return report
    except Exception as e:
        logger.exception("Failed to generate recommendation report")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        fallback = ReportResponse(
            report_id="rpt-fallback",
            request_id=request.request_id,
            generated_at=now,
            format=request.format,
            title="推荐报告",
            summary="报告生成失败，系统已返回可追踪的兜底响应，请检查后端日志。",
            generation_source="fallback",
            sections=[
                {
                    "title": "报告生成失败",
                    "content": f"后端报告服务异常：{e.__class__.__name__}。请检查服务日志后重试。",
                }
            ],
            raw_content="# 推荐报告\n\n报告生成失败，请检查后端日志后重试。",
        )
        get_audit_service().record(
            "report_generate",
            current_user,
            request_id=request.request_id,
            status="fallback",
            payload_summary={"error": e.__class__.__name__},
        )
        return fallback


@router.post("/reports/recommendation/export")
async def export_report(
    request: ReportRequest,
    format: str = Query("docx", description="导出格式: docx 或 pdf"),
    current_user: UserContext = Depends(get_current_user),
):
    """Export recommendation report as a downloadable DOCX or PDF file."""
    try:
        parse_result = request.parse_result or {}
        if request.demand_raw and not parse_result.get("raw_text"):
            parse_result = {**parse_result, "raw_text": request.demand_raw}

        recommend_result = request.recommend_result or {}
        if not recommend_result and request.recommendations:
            recommend_result = {"recommendations": request.recommendations}

        composition_result = request.composition_result or request.composition or {}

        report = _service.generate(
            request_id=request.request_id,
            parse_result=parse_result,
            recommend_result=recommend_result,
            composition_result=composition_result,
            model_result=request.model_result,
            include_details=request.include_details,
        )

        exporter = get_report_exporter()
        fmt = (format or "").lower().strip()
        if fmt == "docx":
            content = exporter.to_docx(report)
            media_type = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            ext = "docx"
        elif fmt == "pdf":
            content = exporter.to_pdf(report)
            media_type = "application/pdf"
            ext = "pdf"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的导出格式: {format}，仅支持 docx 或 pdf",
            )

        get_audit_service().record(
            "report_export",
            current_user,
            request_id=report.report_id,
            status="success",
            payload_summary={"format": fmt, "report_id": report.report_id},
        )

        return StreamingResponse(
            io.BytesIO(content),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename=recommendation-report.{ext}"
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to export recommendation report")
        raise HTTPException(
            status_code=500,
            detail=f"报告导出失败：{e.__class__.__name__}",
        )
