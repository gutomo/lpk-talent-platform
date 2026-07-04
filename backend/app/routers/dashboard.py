"""経営者KPIダッシュボード（admin専用）。

集計定義は services/dashboard.py（BUILD_PLAN の KPI 表と同一）。
教師ビューのクラス一覧は /students、企業ビューは共有リンク側が担う。
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from app.models import User
from app.models.enums import UserRole
from app.routers.deps import DbSession, require_role
from app.schemas.dashboard import AdminKpiOut
from app.services.dashboard import admin_kpi

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

Admin = Annotated[User, Depends(require_role(UserRole.ADMIN))]


@router.get("/kpi")
def kpi(admin: Admin, db: DbSession) -> AdminKpiOut:
    """自組織の学生を対象にした経営者KPI。"""
    return AdminKpiOut(**admin_kpi(db, admin.org_id, datetime.now(UTC)))
