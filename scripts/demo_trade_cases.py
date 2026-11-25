"""交易失败路径演示。不碰 data/mall.db，跑完即删临时库。

    .venv\\Scripts\\python.exe scripts\\demo_trade_cases.py
"""

import tempfile
import threading
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.database import Base
from app.errors import TradeError
from app.models import Address, Item, Order, TradeAudit, User
from app.schemas import OrderCreate, OrderLineIn, PayApplyIn
from app.security import hash_password
from app.trade import (
    ORDER_PAID,
    ORDER_REFUNDED,
    ORDER_UNPAID,
    apply_pay_order,
    change_unpaid_address,
    create_order,
    pay_by_balance,
    refund_order,
)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="mall-trade-")) / "cases.db"
    engine = create_engine(
        f"sqlite:///{tmp}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        user = User(username="case", password=hash_password("123456"), balance=100_000)
        db.add(user)
        db.flush()
        address = Address(
            user_id=user.id,
            province="上海市",
            city="徐汇区",
            town="衡山路",
            street="北巷 1 号",
            contact="用例",
            mobile="13800000000",
            is_default=1,
        )
        scarce = Item(name="限量围巾", price=1000, stock=1, status=1)
        goods = Item(name="手帐", price=500, stock=10, status=1)
        last_one = Item(name="最后一件台灯", price=800, stock=1, status=1)
        db.add_all([address, scarce, goods, last_one])
        db.commit()
        user_id, address_id = user.id, address.id
        scarce_id, goods_id, last_id = scarce.id, goods.id, last_one.id

        expect(
            "库存不足不会超卖",
            lambda: create_order(db, _user(db, user_id), _form(address_id, scarce_id, 2)),
            "STOCK_NOT_ENOUGH",
        )
        assert _stock(db, scarce_id) == 1
        assert db.query(Order).count() == 0

        order = create_order(db, _user(db, user_id), _form(address_id, scarce_id, 1))
        assert _stock(db, scarce_id) == 0
        ok("买走最后 1 件后库存为 0")
        expect(
            "库存为 0 时再下单仍失败",
            lambda: create_order(db, _user(db, user_id), _form(address_id, scarce_id, 1)),
            "STOCK_NOT_ENOUGH",
        )
        assert _stock(db, scarce_id) == 0

        race = _race_last_item(Session, user_id, address_id, last_id)
        success = [item for item in race if item == "OK"]
        denied = [item for item in race if item == "STOCK_NOT_ENOUGH"]
        assert len(success) == 1 and len(denied) == 1, race
        assert _stock(db, last_id) == 0
        ok("两笔同时抢最后 1 件，只有 1 笔成功")

        payable = create_order(db, _user(db, user_id), _form(address_id, goods_id, 1))
        pay = apply_pay_order(
            db,
            _user(db, user_id),
            PayApplyIn(biz_order_no=payable.id, amount=payable.total_fee),
        )
        before = _balance(db, user_id)
        pay_by_balance(db, _user(db, user_id), pay.id, "123456")
        after = _balance(db, user_id)
        assert after == before - payable.total_fee
        expect(
            "同一订单重复支付被拒绝",
            lambda: pay_by_balance(db, _user(db, user_id), pay.id, "123456"),
            "PAY_ALREADY_SUCCESS",
        )
        assert _balance(db, user_id) == after
        assert db.get(Order, payable.id).status == ORDER_PAID
        ok("重复支付没有第二次扣余额")

        old_address = db.get(Order, payable.id).full_address
        expect(
            "已支付订单不能改地址",
            lambda: change_unpaid_address(db, _user(db, user_id), payable.id, "北京市朝阳区酒仙桥 8 号"),
            "ADDRESS_CHANGE_FORBIDDEN",
        )
        assert db.get(Order, payable.id).full_address == old_address

        unpaid = create_order(db, _user(db, user_id), _form(address_id, goods_id, 1))
        stock_before_refund = _stock(db, goods_id)
        expect(
            "未支付订单不能退款",
            lambda: refund_order(db, _user(db, user_id), unpaid.id),
            "REFUND_NOT_PAID",
        )
        assert db.get(Order, unpaid.id).status == ORDER_UNPAID
        assert _stock(db, goods_id) == stock_before_refund

        unpaid_pay = apply_pay_order(
            db,
            _user(db, user_id),
            PayApplyIn(biz_order_no=unpaid.id, amount=unpaid.total_fee),
        )
        pay_by_balance(db, _user(db, user_id), unpaid_pay.id, "123456")
        balance_before = _balance(db, user_id)
        stock_before = _stock(db, goods_id)
        refund_order(db, _user(db, user_id), unpaid.id)
        assert db.get(Order, unpaid.id).status == ORDER_REFUNDED
        assert _stock(db, goods_id) == stock_before + 1
        assert _balance(db, user_id) == balance_before + unpaid.total_fee
        ok("已支付订单退款后库存和余额回补")
        balance_after = _balance(db, user_id)
        stock_after = _stock(db, goods_id)
        expect(
            "重复退款不能成功",
            lambda: refund_order(db, _user(db, user_id), unpaid.id),
            "REFUND_ALREADY_DONE",
        )
        assert _balance(db, user_id) == balance_after
        assert _stock(db, goods_id) == stock_after

        print("\n审计（谁、订单、动作、结果）：")
        for row in db.query(TradeAudit).order_by(TradeAudit.id).all():
            flag = "成功" if row.success else "失败"
            print(f"  {row.username} 订单{row.order_id} {row.action} {flag} {row.code} {row.message}")
        print("\n全部用例通过")
    finally:
        db.close()
        engine.dispose()


def _race_last_item(Session, user_id: int, address_id: int, item_id: int) -> list[str]:
    barrier = threading.Barrier(2)
    codes: list[str] = []
    lock = threading.Lock()

    def once() -> None:
        session = Session()
        try:
            barrier.wait(timeout=5)
            create_order(session, _user(session, user_id), _form(address_id, item_id, 1))
            code = "OK"
        except TradeError as exc:
            code = exc.code
        finally:
            session.close()
        with lock:
            codes.append(code)

    threads = [threading.Thread(target=once), threading.Thread(target=once)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return codes


def _form(address_id: int, item_id: int, num: int) -> OrderCreate:
    return OrderCreate(address_id=address_id, details=[OrderLineIn(item_id=item_id, num=num)])


def _user(db, user_id: int) -> User:
    return db.get(User, user_id)


def _stock(db, item_id: int) -> int:
    db.expire_all()
    return db.get(Item, item_id).stock


def _balance(db, user_id: int) -> int:
    db.expire_all()
    return db.get(User, user_id).balance


def expect(title: str, fn, code: str) -> None:
    try:
        fn()
    except TradeError as exc:
        assert exc.code == code, (title, exc.code, exc.detail)
        ok(f"{title} -> {code}：{exc.detail['message']}")
        return
    raise AssertionError(f"{title} 应当失败 {code}")


def ok(title: str) -> None:
    print(f"通过  {title}")


if __name__ == "__main__":
    main()
