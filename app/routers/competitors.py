from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.database import DB, as_dict
from app.models import BattlecardNote, ChangeAlert, Competitor, TrackedPage
from app.schemas import BattlecardWrite, CompetitorCreate, PageCreate
from app.services.battlecards import market_rows

router = APIRouter()


@router.get("/competitors")
def competitors(db: DB):
    counts = dict(db.execute(
        select(TrackedPage.competitor_id, func.count(ChangeAlert.id))
        .join(ChangeAlert, ChangeAlert.page_id == TrackedPage.id)
        .where(ChangeAlert.is_acknowledged.is_(False)).group_by(TrackedPage.competitor_id)
    ).all())
    cards = {card.competitor_id: as_dict(card) for card in db.scalars(select(BattlecardNote))}
    return [
        dict(**as_dict(brand), cro_score=snap.cro_score if snap else None,
             min_price=snap.min_price if snap else None, currency=snap.currency if snap else None,
             unread_alert_count=counts.get(brand.id, 0), battlecard=cards.get(brand.id))
        for brand, snap in market_rows(db)
    ]


@router.post("/competitors", status_code=201)
def create_competitor(data: CompetitorCreate, db: DB):
    competitor = Competitor(**data.model_dump())
    db.add(competitor)
    db.flush()
    result = as_dict(competitor)
    db.commit()
    return result


@router.get("/competitors/{competitor_id}")
def competitor_detail(competitor_id: int, db: DB):
    brand = db.get(Competitor, competitor_id, options=[
        selectinload(Competitor.pages).selectinload(TrackedPage.snapshots),
        selectinload(Competitor.battlecard),
    ])
    if brand is None:
        raise HTTPException(404, "Игрок рынка не найден")
    pages = [dict(**as_dict(page), snapshots=[as_dict(snap) for snap in page.snapshots])
             for page in brand.pages]
    return dict(**as_dict(brand), pages=pages, battlecard=as_dict(brand.battlecard) if brand.battlecard else None)


@router.put("/competitors/{competitor_id}/battlecard")
def write_battlecard(competitor_id: int, data: BattlecardWrite, db: DB):
    locked = db.execute(update(Competitor).where(Competitor.id == competitor_id)
                        .values(name=Competitor.name).returning(Competitor.id)).scalar_one_or_none()
    if locked is None:
        raise HTTPException(404, "Игрок рынка не найден")
    card = db.scalar(select(BattlecardNote).where(BattlecardNote.competitor_id == competitor_id))
    if card is None:
        card = BattlecardNote(competitor_id=competitor_id)
        db.add(card)
    for field, value in data.model_dump().items():
        setattr(card, field, value)
    db.flush()
    result = as_dict(card)
    db.commit()
    return result


@router.post("/pages", status_code=201)
def create_page(data: PageCreate, db: DB):
    locked = db.execute(update(Competitor).where(Competitor.id == data.competitor_id)
                        .values(name=Competitor.name).returning(Competitor.id)).scalar_one_or_none()
    if locked is None:
        raise HTTPException(404, "Игрок рынка не найден")
    page = TrackedPage(**data.model_dump(mode="json"))
    db.add(page)
    db.flush()
    result = as_dict(page)
    db.commit()
    return result
