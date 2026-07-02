from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import CreatedAtMixin, UpdatedAtMixin, str_enum
from app.models.enums import Locale, OrgType, Sector, UserRole


class Organization(CreatedAtMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[OrgType] = mapped_column(str_enum(OrgType, "org_type"))

    users: Mapped[list["User"]] = relationship(back_populates="org")


class User(CreatedAtMixin, UpdatedAtMixin, Base):
    """PII 最小化：氏名とメールのみ保持。パスポート番号・住所は扱わない。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "user_role"))
    locale: Mapped[Locale] = mapped_column(str_enum(Locale, "locale"), default=Locale.ID)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    org: Mapped[Organization] = relationship(back_populates="users")


class Cohort(CreatedAtMixin, Base):
    __tablename__ = "cohorts"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    sector: Mapped[Sector] = mapped_column(str_enum(Sector, "sector"))
    start_date: Mapped[date] = mapped_column(Date)


class Enrollment(CreatedAtMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("cohort_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cohort_id: Mapped[int] = mapped_column(ForeignKey("cohorts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
