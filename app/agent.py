"""客服路由：精确事实走工具，政策走混合检索，退款和改地址先挂起再确认。"""

import json
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models import AgentState, Item, KnowledgeDoc, Order, User
from app.retrieve import hybrid_search
from app.trade import change_unpaid_address, refund_order

POLICIES = [
    (
        "退货政策",
        "已付款订单七日内可以申请退款。退款退回余额，并按订单明细回补库存。食品拆封后不支持退货。退款是写操作，必须先给出订单号并等人确认，不能在检索命中后直接改库。",
    ),
    (
        "配送与改地址",
        "北京和上海的订单默认次日达，其他地区三到五日。未付款订单可以修改收货地址。已付款订单不能直接改地址，需要先退款再重新下单。",
    ),
    (
        "支付说明",
        "目前只支持余额支付。支付单按业务订单号幂等，重复支付会被状态条件更新拒绝。支付密码与登录密码相同只出现在演示账号上。",
    ),
]

REFUND_ASK = ("我要退", "申请退款", "帮我退", "退掉", "不想要了")
POLICY_ASK = ("能退", "可以退", "退货政策", "怎么退", "地址还能改", "可以改地址", "几天到", "运费", "怎么支付")
CONFIRM = ("确认", "同意", "确定执行", "好的执行")
CANCEL = ("取消", "算了", "先不要")
GOODS_CUES = (
    "有没有",
    "有吗",
    "卖吗",
    "卖不卖",
    "想买",
    "多少钱",
    "什么价",
    "价格",
    "介绍",
    "库存",
    "有货",
    "还有吗",
    "还有几",
    "推荐",
    "有什么好",
    "买点什么",
    "帮我挑",
)
GOODS_STOP = GOODS_CUES + ("吗", "呢", "啊", "呀", "的", "了", "一下", "请问", "我想", "想要", "这个", "那个", "怎么", "什么", "可以", "商品")


def ensure_knowledge(db: Session) -> None:
    if db.query(KnowledgeDoc).first():
        return
    for title, body in POLICIES:
        db.add(KnowledgeDoc(title=title, body=body, kind="policy"))
    for item in db.query(Item).all():
        db.add(
            KnowledgeDoc(
                title=item.name,
                body=f"{item.brand} {item.spec}。{item.blurb} 分类是{item.category}。",
                kind="item",
            )
        )
    db.commit()


def history_of(db: Session, user: User) -> dict:
    state = _state(db, user)
    return {"messages": _history(state), "pending": _pending(state)}


def chat(db: Session, user: User, message: str) -> dict:
    message = message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="请输入问题")
    state = _state(db, user)
    pending = _pending(state)
    trace: list[str] = []
    citations: list[dict] = []
    cards: list[dict] = []
    route = "refuse"

    if pending and any(word in message for word in CANCEL):
        state.pending_json = ""
        reply = "已取消刚才的写操作，库没有改动。"
        route = "cancel"
        trace.append("待确认动作已清除")
    elif pending and pending.get("action") == "address" and not pending.get("street") and not any(
        word in message for word in CONFIRM
    ):
        street = message.strip()[:256]
        state.pending_json = json.dumps(
            {"action": "address", "order_id": pending["order_id"], "street": street},
            ensure_ascii=False,
        )
        reply = f"准备把订单 {pending['order_id']} 的地址改成「{street}」。回复「确认」后才会更新。"
        route = "hitl"
        trace.append("补全地址，仍未写库")
    elif pending and any(word in message for word in CONFIRM):
        reply, route = _commit_pending(db, user, pending, trace)
        if route == "confirm":
            state.pending_json = ""
    elif any(word in message for word in POLICY_ASK):
        reply, route, citations = _answer_from_docs(db, state, message, trace)
    elif any(word in message for word in ("余额", "还剩多少", "还有多少钱")):
        reply = f"账户余额 {user.balance / 100:.2f} 元。余额是精确查询，走账户工具，不查知识库。"
        route = "tool"
        trace.append("tool=get_balance")
    elif any(word in message for word in REFUND_ASK):
        reply = _propose_refund(db, user, state, message, trace)
        route = "hitl"
    elif any(word in message for word in ("改地址", "换地址", "修改地址", "改到", "改成")):
        reply = _propose_address(db, user, state, message, trace)
        route = "hitl"
    elif any(word in message for word in ("我的订单", "订单列表", "买过", "查订单")) or re.search(r"订单\s*\d+", message):
        reply = _orders_reply(db, user, state, message, trace)
        route = "tool"
    elif _asks_for_goods(message):
        reply, route, cards = _goods_reply(db, state, message, trace)
    else:
        reply, route, citations = _answer_from_docs(db, state, message, trace)
        if route == "rag":
            cards = _cards_for_titles(db, [row["title"] for row in citations])

    _remember(state, message, reply, cards)
    db.commit()
    return {
        "reply": reply,
        "route": route,
        "citations": citations,
        "pending": _pending(state),
        "trace": trace,
        "messages": _history(state),
    }


def _orders_reply(db: Session, user: User, state: AgentState, message: str, trace: list[str]) -> str:
    trace.append("tool=list_orders")
    match = re.search(r"订单\s*(\d+)", message)
    query = db.query(Order).options(joinedload(Order.details)).filter(Order.user_id == user.id)
    if match:
        query = query.filter(Order.id == int(match.group(1)))
    rows = query.order_by(Order.id.desc()).limit(5).all()
    if not rows:
        return "没有查到你的订单。"
    state.last_order_id = rows[0].id
    if rows[0].details:
        state.last_item_name = rows[0].details[0].name
    labels = {1: "待付款", 2: "已付款", 5: "已关闭", 6: "已退款"}
    lines = []
    for order in rows:
        names = "、".join(f"{line.name}×{line.num}" for line in order.details) or "无明细"
        lines.append(f"订单 {order.id} {labels.get(order.status, order.status)} {order.total_fee / 100:.2f} 元：{names}")
    return "订单走的是订单工具，不是向量检索。\n" + "\n".join(lines)


def _asks_for_goods(message: str) -> bool:
    return any(word in message for word in GOODS_CUES)


def _goods_focus(message: str) -> str:
    text = message
    for word in sorted(GOODS_STOP, key=len, reverse=True):
        text = text.replace(word, " ")
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", text)
    parts = [part for part in text.split() if len(part) >= 1]
    return "".join(parts)


def _missing_goods(focus: str) -> str:
    name = focus or "这件"
    return f"{name}暂时没有。需要的话，我们登记，后续可以持续关注哦。"


def _goods_reply(db: Session, state: AgentState, message: str, trace: list[str]) -> tuple[str, str, list[dict]]:
    name = _item_name(db, state, message)
    focus = _goods_focus(message)
    if not name and len(focus) >= 1 and not any(word in message for word in ("它", "这个", "那个", "这款", "那款")):
        trace.append("目录里没有这件商品")
        return _missing_goods(focus), "refuse", []
    if any(word in message for word in ("推荐", "有什么好", "买点什么", "帮我挑")) and not name:
        reply, cards = _recommend(db, state, message, trace)
        return reply, "tool", cards
    if not name:
        return "要查哪一件？可以说商品名。", "tool", []
    reply, cards = _stock_reply(db, state, message, trace)
    return reply, "tool", cards


def _stock_reply(db: Session, state: AgentState, message: str, trace: list[str]) -> tuple[str, list[dict]]:
    trace.append("tool=get_stock")
    name = _item_name(db, state, message)
    if not name:
        return "要查哪一件的库存？可以说商品名。", []
    item = db.query(Item).filter(Item.name == name, Item.status == 1).one_or_none()
    if item is None:
        return f"没有找到 {name}。", []
    state.last_item_name = item.name
    reply = f"{item.name} 当前库存 {item.stock} 件，已售 {item.sold}。点下面的卡片可以看详情并下单。"
    return reply, _cards([item])


def _recommend(db: Session, state: AgentState, message: str, trace: list[str]) -> tuple[str, list[dict]]:
    trace.append("tool=recommend")
    items = db.query(Item).filter(Item.status == 1, Item.stock > 0).order_by(Item.id).all()
    named = _item_name(db, state, message)
    picked = [item for item in items if item.name == named] if named else []
    if not picked:
        picked = [
            item for item in items
            if item.category in message or item.brand in message
        ]
    if not picked:
        picked = items[:3]
    if not picked:
        return "现在没有可推荐的在售商品。", []
    state.last_item_name = picked[0].name
    return "给你挑了这几件，点卡片进详情就能下单。", _cards(picked)


def _propose_refund(db: Session, user: User, state: AgentState, message: str, trace: list[str]) -> str:
    trace.append("hitl=refund 尚未写库")
    order = _pick_order(db, user, state, message)
    if order is None:
        return "没有找到可退的订单。可以先说「查订单」。"
    state.last_order_id = order.id
    if order.status != 2:
        return f"订单 {order.id} 不是已付款状态，不能退款。"
    state.pending_json = json.dumps({"action": "refund", "order_id": order.id}, ensure_ascii=False)
    return (
        f"准备退款：订单 {order.id}，{order.total_fee / 100:.2f} 元将退回余额，库存按明细回补。"
        "回复「确认」才会写库，回复「取消」则放弃。"
    )


def _propose_address(db: Session, user: User, state: AgentState, message: str, trace: list[str]) -> str:
    trace.append("hitl=address 尚未写库")
    order = _pick_order(db, user, state, message)
    if order is None:
        return "没有找到订单。未付款订单才能改地址。"
    state.last_order_id = order.id
    if order.status != 1:
        return f"订单 {order.id} 已付款或已结束，不能直接改地址。已付款的需要先退款。"
    found = re.search(r"(?:改成|改为|换成|改到)(.+)$", message)
    street = found.group(1).strip() if found else ""
    if len(street) < 4:
        state.pending_json = json.dumps({"action": "address", "order_id": order.id, "street": ""}, ensure_ascii=False)
        return f"订单 {order.id} 还是待付款。把新地址接在「改成」后面，例如：把订单改成上海市徐汇区衡山路 1 号。"
    state.pending_json = json.dumps(
        {"action": "address", "order_id": order.id, "street": street[:256]},
        ensure_ascii=False,
    )
    return f"准备把订单 {order.id} 的地址改成「{street}」。回复「确认」后才会更新。"


def _commit_pending(db: Session, user: User, pending: dict, trace: list[str]) -> tuple[str, str]:
    action = pending.get("action")
    order_id = int(pending.get("order_id") or 0)
    try:
        if action == "refund":
            trace.append("confirm refund")
            refund_order(db, user, order_id)
            db.refresh(user)
            return f"订单 {order_id} 已退款，余额现在是 {user.balance / 100:.2f} 元。", "confirm"
        if action == "address":
            street = pending.get("street") or ""
            if len(street) < 4:
                return "还没有新地址。请说「把订单改成」加上完整地址。", "hitl"
            trace.append("confirm address")
            change_unpaid_address(db, user, order_id, street)
            return f"订单 {order_id} 的地址已改为 {street}。", "confirm"
    except HTTPException as exc:
        return str(exc.detail), "refuse"
    return "没有待确认的操作。", "refuse"


def _answer_from_docs(db: Session, state: AgentState, message: str, trace: list[str]) -> tuple[str, str, list[dict]]:
    query = message
    policy = any(word in message for word in POLICY_ASK)
    if any(word in message for word in ("它", "这个", "那个", "这款", "那款")) and state.last_item_name:
        trace.append(f"指代补全={state.last_item_name}")
        if not policy:
            query = f"{message} {state.last_item_name}"
    docs = [
        {"id": row.id, "title": row.title, "body": row.body, "kind": row.kind}
        for row in db.query(KnowledgeDoc).all()
        if not policy or row.kind == "policy"
    ]
    hits = hybrid_search(docs, query, limit=3)
    if hits:
        top = hits[0]
        trace.append(f"bm25={top['bm25']} dense={top['dense']} rrf={top['rrf']} rerank={top['rerank']} 《{top['title']}》")
    if not hits or hits[0]["rerank"] < 0.12:
        trace.append("证据不足，拒答")
        focus = _goods_focus(message)
        if focus and not _item_name(db, state, message):
            trace.append("问到的商品不在目录里")
            return _missing_goods(focus), "refuse", []
        return "知识库里没有足够依据，这个问题先转人工，我不会编一条政策。", "refuse", []
    top = hits[0]
    if top.get("kind") == "item" and not _item_name(db, state, message):
        trace.append("问到的商品不在目录里")
        return _missing_goods(_goods_focus(message)), "refuse", []
    if top.get("kind") == "item":
        state.last_item_name = top["title"]
    prefix = f"你说的是{state.last_item_name}。" if state.last_item_name and state.last_item_name in query else ""
    reply = f"{prefix}依据《{top['title']}》：{top['body']}"
    citations = [
        {"title": row["title"], "rerank": row["rerank"], "kind": row.get("kind", "")}
        for row in hits
        if row["rerank"] > 0
    ]
    return reply, "rag", citations


def _pick_order(db: Session, user: User, state: AgentState, message: str) -> Order | None:
    match = re.search(r"订单\s*(\d+)", message)
    if match:
        return (
            db.query(Order)
            .filter(Order.id == int(match.group(1)), Order.user_id == user.id)
            .one_or_none()
        )
    if state.last_order_id:
        found = (
            db.query(Order)
            .filter(Order.id == state.last_order_id, Order.user_id == user.id)
            .one_or_none()
        )
        if found:
            return found
    return db.query(Order).filter(Order.user_id == user.id).order_by(Order.id.desc()).first()


def _item_name(db: Session, state: AgentState, message: str) -> str:
    items = db.query(Item).all()
    for item in items:
        if item.name in message:
            return item.name
    found = ""
    found_len = 1
    for item in items:
        blob = f"{item.name}{item.spec}{item.brand}{item.category}"
        for size in range(len(blob), 1, -1):
            if size <= found_len:
                break
            if any(blob[i : i + size] in message for i in range(len(blob) - size + 1)):
                found = item.name
                found_len = size
                break
    if not found and len(message) <= 8:
        singles = [item for item in items if any(char in item.name for char in message if "\u4e00" <= char <= "\u9fff")]
        unique = {item.name for item in singles}
        if len(unique) == 1:
            found = singles[0].name
    if found:
        return found
    if any(word in message for word in ("它", "这个", "那个", "这款", "那款")):
        return state.last_item_name
    return ""


def _state(db: Session, user: User) -> AgentState:
    row = db.query(AgentState).filter_by(user_id=user.id).one_or_none()
    if row is None:
        row = AgentState(user_id=user.id)
        db.add(row)
        db.flush()
    return row


def _pending(state: AgentState) -> dict | None:
    if not state.pending_json:
        return None
    return json.loads(state.pending_json)


def _history(state: AgentState) -> list[dict]:
    try:
        return json.loads(state.history_json or "[]")
    except json.JSONDecodeError:
        return []


def _cards(items: list[Item]) -> list[dict]:
    return [
        {"id": item.id, "name": item.name, "price": item.price, "spec": item.spec, "stock": item.stock}
        for item in items[:3]
    ]


def _cards_for_titles(db: Session, titles: list[str]) -> list[dict]:
    names = [title for title in titles if title]
    if not names:
        return []
    rows = db.query(Item).filter(Item.name.in_(names), Item.status == 1).all()
    order = {name: index for index, name in enumerate(names)}
    rows.sort(key=lambda item: order.get(item.name, 99))
    return _cards(rows)


def _remember(state: AgentState, message: str, reply: str, cards: list[dict] | None = None) -> None:
    rows = _history(state)
    rows.append({"role": "user", "content": message})
    assistant: dict = {"role": "assistant", "content": reply}
    if cards:
        assistant["cards"] = cards
    rows.append(assistant)
    state.history_json = json.dumps(rows[-12:], ensure_ascii=False)
