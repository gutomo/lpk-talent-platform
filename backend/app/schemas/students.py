from datetime import datetime

from pydantic import BaseModel


class StudentListItem(BaseModel):
    id: int
    name: str
    email: str
    cohort_name: str | None
    last_active_at: datetime | None
