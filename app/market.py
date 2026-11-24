"""行情日报流水线：主源失败重试、新闻按标题去重、同一天成功任务幂等、摘要有成本上限。"""

import hashlib
from datetime import date

from sqlalchemy.orm import Session

from app.models import MarketJob, MarketNews, MarketQuote, MarketReport

COST_CAP = 3

PRIMARY = [
    ("000001.SH", "上证指数", 328012, 42),
    ("000300.SH", "沪深300", 398855, -18),
    ("BX.RETAIL", "北巷零售指数", 12640, 75),
]

FALLBACK = [
    ("000001.SH", "上证指数", 327500, 0),
    ("000300.SH", "沪深300", 398000, 0),
    ("BX.RETAIL", "北巷零售指数", 12500, 0),
]

NEWS = [
    ("北巷零售指数纳入围巾与咖啡", "北巷研究", "样本里围巾库存偏低，咖啡豆成交上升。"),
    ("北巷零售指数纳入围巾与咖啡", "转载", "与北巷研究同题，应按标题哈希跳过。"),
    ("余额支付单按业务单号幂等", "交易组", "重复支付会被状态条件更新拒绝。"),
    ("未付款订单允许修改收货地址", "履约组", "已付款订单改地址要走退款，不直接改。"),
]


class SourceDown(Exception):
    pass


def run_market(db: Session, trade_date: str | None = None, fail_primary: bool = False) -> dict:
    trade_date = trade_date or date.today().isoformat()
    done = db.query(MarketJob).filter_by(trade_date=trade_date, status="ok").one_or_none()
    if done is not None:
        return _payload(db, done, idempotent_hit=True)

    job = db.query(MarketJob).filter_by(trade_date=trade_date).one_or_none()
    if job is None:
        job = MarketJob(trade_date=trade_date, status="running")
        db.add(job)
        db.flush()

    job.attempts += 1
    try:
        quotes = _fetch(fail_primary)
    except SourceDown as exc:
        job.last_error = str(exc)
        job.attempts += 1
        quotes = FALLBACK
        job.used_fallback = 1

    db.query(MarketQuote).filter_by(job_id=job.id).delete()
    for symbol, name, price_cent, change_bp in quotes:
        db.add(
            MarketQuote(
                job_id=job.id,
                symbol=symbol,
                name=name,
                price_cent=price_cent,
                change_bp=change_bp,
            )
        )
    new_news = _ingest_news(db)
    content, spent = _summarize(quotes, new_news, job.cost_units)
    job.cost_units += spent
    job.status = "ok"
    report = db.query(MarketReport).filter_by(job_id=job.id).one_or_none()
    if report is None:
        report = MarketReport(job_id=job.id, content=content, new_news=new_news)
        db.add(report)
    else:
        report.content = content
        report.new_news = new_news
    db.commit()
    db.refresh(job)
    return _payload(db, job, idempotent_hit=False)


def latest(db: Session) -> dict | None:
    job = db.query(MarketJob).filter_by(status="ok").order_by(MarketJob.id.desc()).first()
    if job is None:
        return None
    return _payload(db, job, idempotent_hit=False)


def _fetch(fail: bool) -> list[tuple]:
    if fail:
        raise SourceDown("主行情源超时")
    return PRIMARY


def _ingest_news(db: Session) -> int:
    seen = {row[0] for row in db.query(MarketNews.title_hash).all()}
    added = 0
    for title, source, body in NEWS:
        digest = hashlib.sha256(title.encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        db.add(MarketNews(title_hash=digest, title=title, source=source, body=body))
        added += 1
    return added


def _summarize(quotes: list[tuple], new_news: int, spent: int) -> tuple[str, int]:
    if spent >= COST_CAP:
        return "已达到单日摘要成本上限，这次只保留行情，不再生成摘要。", 0
    lines = []
    for _symbol, name, price_cent, change_bp in quotes:
        lines.append(f"{name} {price_cent / 100:.2f}（{change_bp / 100:+.2f}%）")
    text = "今日行情\n" + "\n".join(lines)
    text += f"\n新入库新闻 {new_news} 条。标题相同的来源已按哈希跳过。"
    return text, 1


def _payload(db: Session, job: MarketJob, idempotent_hit: bool) -> dict:
    quotes = db.query(MarketQuote).filter_by(job_id=job.id).all()
    report = db.query(MarketReport).filter_by(job_id=job.id).one_or_none()
    return {
        "trade_date": job.trade_date,
        "idempotent_hit": idempotent_hit,
        "attempts": job.attempts,
        "used_fallback": bool(job.used_fallback),
        "last_error": job.last_error,
        "cost_units": job.cost_units,
        "cost_cap": COST_CAP,
        "new_news": report.new_news if report else 0,
        "report": report.content if report else "",
        "quotes": [
            {
                "symbol": row.symbol,
                "name": row.name,
                "price_cent": row.price_cent,
                "change_bp": row.change_bp,
            }
            for row in quotes
        ],
    }
