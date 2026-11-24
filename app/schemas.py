from datetime import datetime

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=32)
    phone: str = ""


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    phone: str
    balance: int

    model_config = {"from_attributes": True}


class LoginOut(BaseModel):
    token: str
    user: UserOut


class ItemOut(BaseModel):
    id: int
    name: str
    price: int
    stock: int
    category: str
    brand: str
    spec: str
    blurb: str
    sold: int
    tone: str

    model_config = {"from_attributes": True}


class ItemPage(BaseModel):
    total: int
    list: list[ItemOut]


class CartIn(BaseModel):
    item_id: int
    num: int = Field(ge=1, le=99)


class CartUpdate(BaseModel):
    num: int = Field(ge=1, le=99)


class CartOut(BaseModel):
    id: int
    item_id: int
    num: int
    name: str
    spec: str
    price: int
    stock: int
    tone: str
    category: str


class AddressIn(BaseModel):
    province: str
    city: str
    town: str
    street: str
    contact: str
    mobile: str
    is_default: int = 0


class AddressOut(AddressIn):
    id: int

    model_config = {"from_attributes": True}


class OrderLineIn(BaseModel):
    item_id: int
    num: int = Field(ge=1, le=99)


class OrderCreate(BaseModel):
    address_id: int
    payment_type: int = 3
    details: list[OrderLineIn] = Field(min_length=1)


class OrderDetailOut(BaseModel):
    item_id: int
    name: str
    spec: str
    price: int
    num: int
    tone: str

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    id: int
    total_fee: int
    payment_type: int
    status: int
    contact: str
    mobile: str
    full_address: str
    create_time: datetime
    pay_time: datetime | None
    details: list[OrderDetailOut]


class PayApplyIn(BaseModel):
    biz_order_no: int
    amount: int = Field(ge=1)
    pay_channel_code: str = "balance"
    pay_type: int = 5
    order_info: str = ""


class PayOrderOut(BaseModel):
    id: int
    biz_order_no: int
    amount: int
    status: int
    pay_channel_code: str

    model_config = {"from_attributes": True}


class PayConfirmIn(BaseModel):
    pw: str


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class ReviewIn(BaseModel):
    code: str = Field(min_length=1, max_length=8000)


class MindIn(BaseModel):
    prompt: str = ""
    n: int = Field(default=40, ge=1, le=80)
    steps: int = Field(default=400, ge=50, le=800)


class MarketRunIn(BaseModel):
    trade_date: str = ""
    fail_primary: bool = False
