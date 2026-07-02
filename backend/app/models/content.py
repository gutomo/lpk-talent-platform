from typing import Any

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import CreatedAtMixin, UpdatedAtMixin, str_enum
from app.models.enums import ContentModule, QuizSection, Sector


class ContentItem(CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    module: Mapped[ContentModule] = mapped_column(
        str_enum(ContentModule, "content_module"), index=True
    )
    sector: Mapped[Sector] = mapped_column(str_enum(Sector, "sector"), index=True)
    text_ja: Mapped[str] = mapped_column(Text)
    furigana: Mapped[str | None] = mapped_column(Text)
    gloss_id: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(16))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class QuizItem(CreatedAtMixin, UpdatedAtMixin, Base):
    """完全オリジナル問題のみ。JLPT / JFT の過去問・公式問題は保存しない。"""

    __tablename__ = "quiz_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    section: Mapped[QuizSection] = mapped_column(str_enum(QuizSection, "quiz_section"), index=True)
    level: Mapped[str] = mapped_column(String(16))
    question: Mapped[str] = mapped_column(Text)
    choices: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    answer_index: Mapped[int] = mapped_column(Integer)
    explanation_id: Mapped[str | None] = mapped_column(Text)
    # True の間は人間レビュー前なので出題しない。
    review_flag: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
