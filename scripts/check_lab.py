"""离线检查实验室四条链路。直接跑：.venv\\Scripts\\python.exe scripts\\check_lab.py"""

import app.models  # noqa: F401
from app.agent import chat, ensure_knowledge
from app.database import Base, SessionLocal, engine
from app.market import run_market
from app.models import KnowledgeDoc, MarketJob, MarketNews, MarketQuote, MarketReport, User
from app.review import review_source
from app.retrieve import hybrid_search
from app import tinymind

SAMPLE = """
def find_user(name):
    sql = f"SELECT * FROM users WHERE name = '{name}'"
    cursor.execute(sql)
    password = "admin123"
    try:
        return eval(name)
    except:
        os.system(name)
"""


def main() -> None:
    Base.metadata.create_all(engine)
    reviewed = review_source(SAMPLE)
    rules = {row["rule"] for row in reviewed["comments"]}
    assert {"SQL_CONCAT", "EVAL", "BARE_EXCEPT", "SECRET", "SHELL"} <= rules, rules

    docs = [
        {"id": 1, "title": "退货政策", "body": "已付款订单可以申请退款。退款退回余额。", "kind": "policy"},
        {"id": 2, "title": "黄铜书桌灯", "body": "灯罩是磨砂玻璃。", "kind": "item"},
    ]
    hits = hybrid_search(docs, "能退吗")
    assert hits[0]["title"] == "退货政策", hits

    db = SessionLocal()
    try:
        ensure_knowledge(db)
        user = db.query(User).filter_by(username="demo").one()
        balance = chat(db, user, "余额还有多少")
        assert balance["route"] == "tool", balance
        stock = chat(db, user, "耳机还有吗")
        assert stock["route"] == "tool" and "头戴降噪耳机" in stock["reply"], stock
        missing = chat(db, user, "有没有手机")
        assert missing["route"] == "refuse" and missing["reply"].startswith("手机暂时没有"), missing
        assert "我们登记，后续可以持续关注哦" in missing["reply"]
        policy = chat(db, user, "那它能退吗")
        assert policy["route"] == "rag" and "退货政策" in policy["reply"], policy

        text = "".join(row.body for row in db.query(KnowledgeDoc).all())
        trained = tinymind.train(text, steps=80)
        assert trained["loss_end"] < trained["loss_start"], trained
        assert tinymind.generate("退款", 12)

        from app.review import review_source as scan
        from pathlib import Path

        app_dir = Path(__file__).resolve().parent.parent / "app"
        own = []
        for path in app_dir.glob("*.py"):
            own.extend(scan(path.read_text(encoding="utf-8"))["comments"])
        assert [row["rule"] for row in own] == ["SECRET"], own

        day = "2099-01-02"
        _wipe(db, day)
        first = run_market(db, day, fail_primary=True)
        assert first["used_fallback"] and first["attempts"] == 2, first
        assert first["new_news"] >= 1
        second = run_market(db, day, fail_primary=True)
        assert second["idempotent_hit"] and second["new_news"] == first["new_news"]
        _wipe(db, day)
    finally:
        db.close()
    print("ok")


def _wipe(db, day: str) -> None:
    job = db.query(MarketJob).filter_by(trade_date=day).one_or_none()
    if job is not None:
        db.query(MarketQuote).filter_by(job_id=job.id).delete()
        db.query(MarketReport).filter_by(job_id=job.id).delete()
        db.delete(job)
    db.query(MarketNews).delete()
    db.commit()


if __name__ == "__main__":
    main()
