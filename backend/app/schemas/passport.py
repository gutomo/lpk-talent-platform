from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PassportOut(BaseModel):
    passport_id: int
    user_id: int
    version: int
    created_at: datetime
    # 集計サービスが確定した snapshot をそのまま返す（PDF・共有ビューが参照する）。
    snapshot: dict[str, Any]
