"""下单与余额支付。

单体阶段这两组写操作放在同一个数据库事务里。
拆成 user / catalog / trade 三个服务后，库存预留、扣余额、改订单状态
要改成各自的本地事务，再用业务单号和状态条件更新保证幂等。
"""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload

from app.models import Address, Cart, Item, Order, OrderDetail, PayOrder, User
from app.schemas import OrderCreate, PayApplyIn
from app.security import verify_password

PAY_WAIT = 1
PAY_CLOSED = 2
PAY_SUCCESS = 3
ORDER_UNPAID = 1
ORDER_PAID = 2
ORDER_REFUNDED = 6
BALANCE_PAY = 5


def create_order(db: Session, user: User, form: OrderCreate) -> Order:
    address = db.get(Address, form.address_id)
    if address is None or address.user_id != user.id:
        raise HTTPException(status_code=400, detail="收货地址不存在")

    item_num = {line.item_id: line.num for line in form.details}
    items = db.query(Item).filter(Item.id.in_(item_num), Item.status == 1).all()
    if len(items) < len(item_num):
        raise HTTPException(status_code=400, detail="商品不存在或已下架")

    total = 0
    for item in items:
        total += item.price * item_num[item.id]

    order = Order(
        total_fee=total,
        payment_type=form.payment_type,
        user_id=user.id,
        status=ORDER_UNPAID,
        contact=address.contact,
        mobile=address.mobile,
        full_address=f"{address.province}{address.city}{address.town}{address.street}",
    )
    db.add(order)
    db.flush()

    for item in items:
        db.add(
            OrderDetail(
                order_id=order.id,
                item_id=item.id,
                name=item.name,
                spec=item.spec,
                price=item.price,
                num=item_num[item.id],
                tone=item.tone,
            )
        )

    db.query(Cart).filter(
        Cart.user_id == user.id, Cart.item_id.in_(item_num)
    ).delete(synchronize_session=False)

    for item in items:
        num = item_num[item.id]
        result = db.execute(
            update(Item)
            .where(Item.id == item.id, Item.stock >= num)
            .values(stock=Item.stock - num, sold=Item.sold + num)
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=400, detail=f"{item.name} 库存不足")

    db.commit()
    db.refresh(order)
    return order


def apply_pay_order(db: Session, user: User, form: PayApplyIn) -> PayOrder:
    if form.pay_type != BALANCE_PAY:
        raise HTTPException(status_code=400, detail="目前只支持余额支付")

    order = db.get(Order, form.biz_order_no)
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != ORDER_UNPAID:
        raise HTTPException(status_code=400, detail="订单不是待支付状态")
    if form.amount != order.total_fee:
        raise HTTPException(status_code=400, detail="支付金额与订单不一致")

    existing = db.query(PayOrder).filter_by(biz_order_no=order.id).one_or_none()
    if existing is None:
        pay_order = PayOrder(
            biz_order_no=order.id,
            pay_order_no=int(datetime.now().strftime("%Y%m%d%H%M%S%f")[:18]),
            biz_user_id=user.id,
            pay_channel_code=form.pay_channel_code,
            amount=order.total_fee,
            pay_type=form.pay_type,
            status=PAY_WAIT,
            pay_over_time=datetime.now() + timedelta(minutes=120),
        )
        db.add(pay_order)
        db.commit()
        db.refresh(pay_order)
        return pay_order

    if existing.status == PAY_SUCCESS:
        raise HTTPException(status_code=400, detail="订单已经支付")
    if existing.status == PAY_CLOSED:
        raise HTTPException(status_code=400, detail="订单已关闭")
    if existing.pay_channel_code != form.pay_channel_code:
        existing.pay_channel_code = form.pay_channel_code
        existing.pay_type = form.pay_type
        existing.amount = order.total_fee
        existing.status = PAY_WAIT
        db.commit()
        db.refresh(existing)
    return existing


def pay_by_balance(db: Session, user: User, pay_order_id: int, password: str) -> None:
    pay_order = db.get(PayOrder, pay_order_id)
    if pay_order is None or pay_order.biz_user_id != user.id:
        raise HTTPException(status_code=404, detail="支付单不存在")
    if pay_order.status != PAY_WAIT:
        raise HTTPException(status_code=400, detail="交易已支付或关闭")
    if not verify_password(password, user.password):
        raise HTTPException(status_code=400, detail="支付密码错误")

    deducted = db.execute(
        update(User)
        .where(User.id == user.id, User.balance >= pay_order.amount)
        .values(balance=User.balance - pay_order.amount)
    )
    if deducted.rowcount != 1:
        raise HTTPException(status_code=400, detail="余额不足")

    now = datetime.now()
    marked = db.execute(
        update(PayOrder)
        .where(PayOrder.id == pay_order.id, PayOrder.status == PAY_WAIT)
        .values(status=PAY_SUCCESS, pay_success_time=now)
    )
    if marked.rowcount != 1:
        raise HTTPException(status_code=400, detail="交易已支付或关闭")

    db.execute(
        update(Order)
        .where(Order.id == pay_order.biz_order_no, Order.status == ORDER_UNPAID)
        .values(status=ORDER_PAID, pay_time=now)
    )
    db.commit()


def refund_order(db: Session, user: User, order_id: int) -> Order:
    """已付款订单退款：状态条件更新成功后才回补库存和余额。"""
    order = (
        db.query(Order)
        .options(joinedload(Order.details))
        .filter(Order.id == order_id, Order.user_id == user.id)
        .one_or_none()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != ORDER_PAID:
        raise HTTPException(status_code=400, detail="只有已付款订单可以退款")

    marked = db.execute(
        update(Order)
        .where(Order.id == order.id, Order.status == ORDER_PAID)
        .values(status=ORDER_REFUNDED)
    )
    if marked.rowcount != 1:
        raise HTTPException(status_code=400, detail="订单状态已变化")

    for line in order.details:
        item = db.get(Item, line.item_id)
        if item is None:
            continue
        item.stock += line.num
        item.sold = max(0, item.sold - line.num)
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(balance=User.balance + order.total_fee)
    )
    db.commit()
    db.refresh(order)
    return order


def change_unpaid_address(db: Session, user: User, order_id: int, street: str) -> None:
    street = street.strip()
    if len(street) < 4:
        raise HTTPException(status_code=400, detail="地址太短")
    result = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.user_id == user.id, Order.status == ORDER_UNPAID)
        .values(full_address=street[:256])
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=400, detail="只能修改未付款订单的地址")
    db.commit()
