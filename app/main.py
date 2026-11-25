from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload

from app.agent import ensure_knowledge
from app.database import Base, SessionLocal, engine, get_db
from app.lab_routes import router as lab_router
from app.models import Address, Cart, Item, Order, TradeAudit, User
from app.schemas import (
    AddressIn,
    AddressOut,
    CartIn,
    CartOut,
    CartUpdate,
    ItemOut,
    ItemPage,
    LoginIn,
    LoginOut,
    OrderCreate,
    OrderOut,
    AddressChangeIn,
    PayApplyIn,
    PayConfirmIn,
    PayOrderOut,
    RegisterIn,
    UserOut,
)
from app.security import create_token, get_current_user, hash_password, verify_password
from app.seed import seed
from app.trade import apply_pay_order, change_unpaid_address, create_order, pay_by_balance, refund_order

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed(db)
        ensure_knowledge(db)
    finally:
        db.close()
    yield


app = FastAPI(title="北巷商城", lifespan=lifespan)
app.include_router(lab_router)
app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.post("/api/auth/register", response_model=LoginOut)
def register(form: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter_by(username=form.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=form.username,
        password=hash_password(form.password),
        phone=form.phone,
        balance=100000,
    )
    db.add(user)
    db.flush()
    db.add(
        Address(
            user_id=user.id,
            province="上海市",
            city="徐汇区",
            town="衡山路",
            street="新地址待修改",
            contact=form.username,
            mobile=form.phone or "13900000000",
            is_default=1,
        )
    )
    db.commit()
    db.refresh(user)
    return LoginOut(token=create_token(user.id), user=UserOut.model_validate(user))


@app.post("/api/auth/login", response_model=LoginOut)
def login(form: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=form.username).one_or_none()
    if user is None or not verify_password(form.password, user.password):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    if user.status != 1:
        raise HTTPException(status_code=403, detail="用户被冻结")
    return LoginOut(token=create_token(user.id), user=UserOut.model_validate(user))


@app.get("/api/users/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@app.get("/api/items", response_model=ItemPage)
def list_items(
    keyword: str = "",
    category: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query = db.query(Item).filter(Item.status == 1)
    if keyword:
        query = query.filter(Item.name.contains(keyword))
    if category:
        query = query.filter(Item.category == category)
    total = query.count()
    rows = (
        query.order_by(Item.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ItemPage(total=total, list=rows)


@app.get("/api/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if item is None or item.status != 1:
        raise HTTPException(status_code=404, detail="商品不存在")
    return item


@app.get("/api/carts", response_model=list[CartOut])
def list_carts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Cart)
        .options(joinedload(Cart.item))
        .filter(Cart.user_id == user.id)
        .order_by(Cart.id.desc())
        .all()
    )
    return [
        CartOut(
            id=row.id,
            item_id=row.item_id,
            num=row.num,
            name=row.item.name,
            spec=row.item.spec,
            price=row.item.price,
            stock=row.item.stock,
            tone=row.item.tone,
            category=row.item.category,
        )
        for row in rows
    ]


@app.post("/api/carts", response_model=list[CartOut])
def add_cart(
    form: CartIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(Item, form.item_id)
    if item is None or item.status != 1:
        raise HTTPException(status_code=404, detail="商品不存在")
    row = db.query(Cart).filter_by(user_id=user.id, item_id=item.id).one_or_none()
    if row is None:
        row = Cart(user_id=user.id, item_id=item.id, num=0)
        db.add(row)
    if row.num + form.num > item.stock:
        raise HTTPException(status_code=400, detail="超过当前库存")
    row.num += form.num
    db.commit()
    return list_carts(user, db)


@app.put("/api/carts/{cart_id}", response_model=list[CartOut])
def update_cart(
    cart_id: int,
    form: CartUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(Cart, cart_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="购物车商品不存在")
    item = db.get(Item, row.item_id)
    if form.num > item.stock:
        raise HTTPException(status_code=400, detail="超过当前库存")
    row.num = form.num
    db.commit()
    return list_carts(user, db)


@app.delete("/api/carts/{cart_id}", response_model=list[CartOut])
def delete_cart(
    cart_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(Cart, cart_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="购物车商品不存在")
    db.delete(row)
    db.commit()
    return list_carts(user, db)


@app.get("/api/addresses", response_model=list[AddressOut])
def list_addresses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Address).filter_by(user_id=user.id).all()


@app.post("/api/addresses", response_model=AddressOut)
def create_address(
    form: AddressIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if form.is_default:
        db.query(Address).filter_by(user_id=user.id).update({"is_default": 0})
    address = Address(user_id=user.id, **form.model_dump())
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


@app.post("/api/orders", response_model=OrderOut)
def place_order(
    form: OrderCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = create_order(db, user, form)
    return _load_order(db, user, order.id)


@app.get("/api/orders", response_model=list[OrderOut])
def list_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Order)
        .options(joinedload(Order.details))
        .filter(Order.user_id == user.id)
        .order_by(Order.id.desc())
        .all()
    )
    return rows


@app.get("/api/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _load_order(db, user, order_id)


@app.post("/api/orders/{order_id}/address")
def update_order_address(
    order_id: int,
    form: AddressChangeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    change_unpaid_address(db, user, order_id, form.street)
    return {"ok": True}


@app.post("/api/orders/{order_id}/refund")
def refund_paid_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refund_order(db, user, order_id)
    db.refresh(user)
    return {"ok": True, "balance": user.balance}


@app.get("/api/trade-audits")
def list_trade_audits(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(TradeAudit)
        .filter(TradeAudit.user_id == user.id)
        .order_by(TradeAudit.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": row.id,
            "order_id": row.order_id,
            "action": row.action,
            "success": bool(row.success),
            "code": row.code,
            "message": row.message,
            "create_time": row.create_time.isoformat(sep=" ", timespec="seconds"),
        }
        for row in rows
    ]


@app.post("/api/pay-orders", response_model=PayOrderOut)
def create_pay_order(
    form: PayApplyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return apply_pay_order(db, user, form)


@app.post("/api/pay-orders/{pay_order_id}")
def confirm_pay(
    pay_order_id: int,
    form: PayConfirmIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pay_by_balance(db, user, pay_order_id, form.pw)
    db.refresh(user)
    return {"ok": True, "balance": user.balance}


def _load_order(db: Session, user: User, order_id: int) -> Order:
    order = (
        db.query(Order)
        .options(joinedload(Order.details))
        .filter(Order.id == order_id, Order.user_id == user.id)
        .one_or_none()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order
