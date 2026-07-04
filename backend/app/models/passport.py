from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import CreatedAtMixin, PortableJSON


class Passport(CreatedAtMixin, Base):
    __tablename__ = "passports"
    __table_args__ = (UniqueConstraint("user_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    pdf_ref: Mapped[str | None] = mapped_column(String(255))

    share_links: Mapped[list["ShareLink"]] = relationship(back_populates="passport")


class ShareLink(CreatedAtMixin, Base):
    __tablename__ = "share_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    passport_id: Mapped[int] = mapped_column(ForeignKey("passports.id"), index=True)
    # ランダム32byteのhex表現（64文字）。
    token: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    view_log: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)

    passport: Mapped[Passport] = relationship(back_populates="share_links")


class CompanyShareLink(CreatedAtMixin, Base):
    """企業向けの組織単位共有リンク。

    トークン1本で、その組織の Passport 発行済み学生全員の比較テーブルと
    各 Passport 詳細・PDF の閲覧を許可する。トークン形式・期限・失効・閲覧ログの
    semantics は ShareLink と同一。
    """

    __tablename__ = "company_share_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    view_log: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
