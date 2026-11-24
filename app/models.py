from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[int] = mapped_column(default=1)
    balance: Mapped[int] = mapped_column(default=0)
    create_time: Mapped[datetime] = mapped_column(default=datetime.now)


class Address(Base):
    __tablename__ = "address"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    province: Mapped[str] = mapped_column(String(32))
    city: Mapped[str] = mapped_column(String(32))
    town: Mapped[str] = mapped_column(String(32))
    street: Mapped[str] = mapped_column(String(128))
    contact: Mapped[str] = mapped_column(String(32))
    mobile: Mapped[str] = mapped_column(String(20))
    is_default: Mapped[int] = mapped_column(default=0)


class Item(Base):
    __tablename__ = "item"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    price: Mapped[int]
    stock: Mapped[int] = mapped_column(default=0)
    category: Mapped[str] = mapped_column(String(32), default="")
    brand: Mapped[str] = mapped_column(String(32), default="")
    spec: Mapped[str] = mapped_column(String(128), default="")
    blurb: Mapped[str] = mapped_column(String(256), default="")
    sold: Mapped[int] = mapped_column(default=0)
    status: Mapped[int] = mapped_column(default=1)
    tone: Mapped[str] = mapped_column(String(16), default="#8c5a3c")


class Cart(Base):
    __tablename__ = "cart"
    __table_args__ = (UniqueConstraint("user_id", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    num: Mapped[int] = mapped_column(default=1)
    create_time: Mapped[datetime] = mapped_column(default=datetime.now)

    item: Mapped[Item] = relationship()


class Order(Base):
    """订单状态：1 未付款，2 已付款，5 已关闭，6 已退款。金额单位为分。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    total_fee: Mapped[int]
    payment_type: Mapped[int] = mapped_column(default=3)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[int] = mapped_column(default=1)
    contact: Mapped[str] = mapped_column(String(32), default="")
    mobile: Mapped[str] = mapped_column(String(20), default="")
    full_address: Mapped[str] = mapped_column(String(256), default="")
    create_time: Mapped[datetime] = mapped_column(default=datetime.now)
    pay_time: Mapped[datetime | None] = mapped_column(default=None)

    details: Mapped[list["OrderDetail"]] = relationship(back_populates="order")


class OrderDetail(Base):
    __tablename__ = "order_detail"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    name: Mapped[str] = mapped_column(String(128))
    spec: Mapped[str] = mapped_column(String(128), default="")
    price: Mapped[int]
    num: Mapped[int]
    tone: Mapped[str] = mapped_column(String(16), default="#8c5a3c")

    order: Mapped[Order] = relationship(back_populates="details")


class PayOrder(Base):
    """支付状态：0 待提交，1 待支付，2 已关闭，3 支付成功。"""

    __tablename__ = "pay_order"

    id: Mapped[int] = mapped_column(primary_key=True)
    biz_order_no: Mapped[int] = mapped_column(unique=True)
    pay_order_no: Mapped[int]
    biz_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    pay_channel_code: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int]
    pay_type: Mapped[int]
    status: Mapped[int] = mapped_column(default=1)
    pay_success_time: Mapped[datetime | None] = mapped_column(default=None)
    pay_over_time: Mapped[datetime | None] = mapped_column(default=None)
    create_time: Mapped[datetime] = mapped_column(default=datetime.now)


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_doc"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(String(1024))
    kind: Mapped[str] = mapped_column(String(16), default="policy")


class AgentState(Base):
    """每个用户一条会话：指代、待确认写操作、最近几轮对话。"""

    __tablename__ = "agent_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    last_order_id: Mapped[int | None] = mapped_column(default=None)
    last_item_name: Mapped[str] = mapped_column(String(128), default="")
    pending_json: Mapped[str] = mapped_column(String(1024), default="")
    history_json: Mapped[str] = mapped_column(String(8000), default="[]")


class MarketJob(Base):
    """按交易日幂等。同一天成功后再跑，直接返回已有日报。"""

    __tablename__ = "market_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    attempts: Mapped[int] = mapped_column(default=0)
    cost_units: Mapped[int] = mapped_column(default=0)
    used_fallback: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(String(256), default="")
    create_time: Mapped[datetime] = mapped_column(default=datetime.now)


class MarketQuote(Base):
    __tablename__ = "market_quote"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("market_job.id"))
    symbol: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(32))
    price_cent: Mapped[int]
    change_bp: Mapped[int]


class MarketNews(Base):
    __tablename__ = "market_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_hash: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(String(512))


class MarketReport(Base):
    __tablename__ = "market_report"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("market_job.id"), unique=True)
    content: Mapped[str] = mapped_column(String(2000))
    new_news: Mapped[int] = mapped_column(default=0)
