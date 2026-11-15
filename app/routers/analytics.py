from fastapi import APIRouter, HTTPException
from sqlalchemy import select, update

from app.database import DB, as_dict
from app.models import ChangeAlert
from app.schemas import Severity
from app.services.battlecards import overview

router = APIRouter()


@router.get("/analytics/overview")
def analytics(db: DB):
    return overview(db)


@router.get("/alerts")
def alerts(db: DB, severity: Severity | None = None, is_acknowledged: bool | None = None):
    query = select(ChangeAlert).order_by(ChangeAlert.created_at.desc(), ChangeAlert.id.desc())
    if severity is not None:
        query = query.where(ChangeAlert.severity == severity)
    if is_acknowledged is not None:
        query = query.where(ChangeAlert.is_acknowledged.is_(is_acknowledged))
    return [as_dict(alert) for alert in db.scalars(query)]


@router.patch("/alerts/{alert_id}/ack")
def acknowledge(alert_id: int, db: DB):
    alert = db.scalar(update(ChangeAlert).where(ChangeAlert.id == alert_id)
                      .values(is_acknowledged=True).returning(ChangeAlert))
    if alert is None:
        raise HTTPException(404, "Изменение не найдено")
    result = as_dict(alert)
    db.commit()
    return result
