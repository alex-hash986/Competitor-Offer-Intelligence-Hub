from datetime import datetime, timezone

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database import Base


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def utc_now():
    return datetime.now(timezone.utc)


def choice(name, *values):
    return Enum(*values, name=name, native_enum=False, create_constraint=True)


class Competitor(Base):
    __tablename__ = "competitors"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(240))
    domain: Mapped[str] = mapped_column(String(253))
    segment: Mapped[str] = mapped_column(choice("segment", "direct", "indirect", "leader"))
    is_own_brand: Mapped[bool] = mapped_column(default=False)
    positioning_note: Mapped[str] = mapped_column(default="")
    target_audience: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    pages: Mapped[list["TrackedPage"]] = relationship(order_by="TrackedPage.id")
    battlecard: Mapped["BattlecardNote | None"] = relationship()


class TrackedPage(Base):
    __tablename__ = "tracked_pages"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), index=True)
    page_type: Mapped[str] = mapped_column(choice("page_type", "main", "pricing", "promo", "lead_magnet"))
    url: Mapped[str]
    title: Mapped[str] = mapped_column(default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    snapshots: Mapped[list["PageSnapshot"]] = relationship(
        order_by=lambda: (PageSnapshot.captured_at.desc(), PageSnapshot.id.desc())
    )


class PageSnapshot(Base):
    __tablename__ = "page_snapshots"
    __table_args__ = (
        CheckConstraint("cro_score BETWEEN 0 AND 100", name="cro_score_range"),
        Index("ix_snapshots_page_history", "page_id", "captured_at", "id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("tracked_pages.id", ondelete="CASCADE"))
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    source_mode: Mapped[str] = mapped_column(choice(
        "source_mode", "live_url", "raw_html", "json_snapshot", "manual_text"
    ))
    content_hash: Mapped[str] = mapped_column(String(64))
    h1_text: Mapped[str]
    subheadline: Mapped[str]
    extracted_prices: Mapped[list[float]] = mapped_column(JSON)
    min_price: Mapped[float | None]
    max_price: Mapped[float | None]
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    cta_buttons: Mapped[list[str]] = mapped_column(JSON)
    trust_signals: Mapped[list[str]] = mapped_column(JSON)
    lead_magnets: Mapped[list[str]] = mapped_column(JSON)
    offer_summary: Mapped[str]
    cro_score: Mapped[int]
    score_breakdown: Mapped[dict[str, int]] = mapped_column(JSON)


class ChangeAlert(Base):
    __tablename__ = "change_alerts"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("tracked_pages.id", ondelete="CASCADE"), index=True)
    old_snapshot_id: Mapped[int] = mapped_column(ForeignKey("page_snapshots.id", ondelete="CASCADE"))
    new_snapshot_id: Mapped[int] = mapped_column(ForeignKey("page_snapshots.id", ondelete="CASCADE"))
    change_type: Mapped[str] = mapped_column(choice(
        "change_type", "price_drop", "price_hike", "h1_change", "cta_change", "trust_update", "offer_pivot"
    ))
    severity: Mapped[str] = mapped_column(choice("severity", "high", "medium", "low"))
    summary: Mapped[str]
    diff_details: Mapped[dict] = mapped_column(JSON)
    is_acknowledged: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class BattlecardNote(Base):
    __tablename__ = "battlecard_notes"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), unique=True)
    competitor_strength: Mapped[str]
    our_counter_offer: Mapped[str]
    sales_objection_script: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class DemoState(Base):
    __tablename__ = "demo_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(String(32))
