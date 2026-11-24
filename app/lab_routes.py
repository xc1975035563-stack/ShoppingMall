from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent import chat, ensure_knowledge, history_of
from app.database import get_db
from app.market import latest, run_market
from app.models import KnowledgeDoc, User
from app.review import review_source
from app.schemas import ChatIn, MarketRunIn, MindIn, ReviewIn
from app.security import get_current_user
from app import tinymind

router = APIRouter(prefix="/api/lab", tags=["lab"])
APP_DIR = Path(__file__).resolve().parent


@router.get("/agent")
def agent_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_knowledge(db)
    return history_of(db, user)


@router.post("/agent")
def agent_chat(form: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_knowledge(db)
    return chat(db, user, form.message)


@router.post("/review")
def review_code(form: ReviewIn):
    return review_source(form.code)


@router.get("/review/app")
def review_app():
    comments = []
    for path in sorted(APP_DIR.glob("*.py")):
        found = review_source(path.read_text(encoding="utf-8"))
        for row in found["comments"]:
            row["file"] = path.name
            comments.append(row)
    if comments:
        summary = f"规则引擎在 app 目录命中 {len(comments)} 处。"
    else:
        summary = "app 目录没有命中这些规则。"
    return {"comments": comments, "summary": summary}


@router.get("/mind")
def mind_status(db: Session = Depends(get_db)):
    ensure_knowledge(db)
    return tinymind.status()


@router.post("/mind/train")
def mind_train(form: MindIn, db: Session = Depends(get_db)):
    ensure_knowledge(db)
    text = "".join(row.body for row in db.query(KnowledgeDoc).all())
    try:
        return tinymind.train(text, steps=form.steps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mind/generate")
def mind_generate(form: MindIn):
    try:
        return {"text": tinymind.generate(form.prompt, form.n)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail="先训练再生成") from exc


@router.get("/market")
def market_latest(db: Session = Depends(get_db)):
    return latest(db) or {"report": ""}


@router.post("/market/run")
def market_run(form: MarketRunIn, db: Session = Depends(get_db)):
    if form.trade_date and len(form.trade_date) != 10:
        raise HTTPException(status_code=400, detail="日期用 YYYY-MM-DD")
    return run_market(db, form.trade_date or None, form.fail_primary)
