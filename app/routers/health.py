from fastapi import APIRouter
from sqlalchemy import func, select

from app.config import VERSION
from app.database import DB
from app.models import Competitor, DemoState, PageSnapshot
from app.schemas import DemoReset
from app.seed import DEMO_CASES, reset_demo_data

router = APIRouter()


@router.get("/health")
def health(db: DB):
    demo = db.get(DemoState, 1)
    return {
        "status": "ok",
        "version": VERSION,
        "active_demo_case": demo.case_id if demo else None,
        "competitor_count": db.scalar(select(func.count(Competitor.id))),
        "snapshot_count": db.scalar(select(func.count(PageSnapshot.id))),
    }


@router.get("/demo/cases")
def demo_cases():
    return [{"case_id": case_id, "title": title} for case_id, title in DEMO_CASES.items()]


@router.post("/demo/reset")
def reset(data: DemoReset, db: DB):
    reset_demo_data(db, data.case_id)
    db.commit()
    return health(db)
