from sqlalchemy.orm import Session

from app.models import Address, Item, User
from app.security import hash_password

ITEMS = [
    ("橡木机械键盘", 39900, 18, "数码", "北巷", "87 键 / 红轴", "桌面上安静的一段木头。", "#8c4a32"),
    ("手冲陶瓷壶", 16800, 22, "家居", "窑口", "600ml", "壶嘴收得窄，水流比较稳。", "#c47b4a"),
    ("亚麻托特包", 25900, 9, "服饰", "巷口", "本色亚麻", "能放下一台 14 寸电脑。", "#a38b62"),
    ("头戴降噪耳机", 89900, 6, "数码", "听澜", "无线 / 30 小时", "地铁里把环境声压低一档。", "#3d4c5c"),
    ("黄铜书桌灯", 12900, 30, "家居", "灯社", "暖光 2700K", "灯罩是磨砂玻璃。", "#c9a15b"),
    ("手帐三件套", 6800, 40, "家居", "纸间", "A6 方格", "本子、衬线和一管墨水。", "#6e7d62"),
    ("耶加雪菲咖啡豆", 8800, 25, "食品", "南风", "200g 浅烘", "柑橘和花香，适合手冲。", "#6b3e2e"),
    ("羊毛围巾", 32900, 4, "服饰", "北纬", "浅灰 / 180cm", "库存不多，适合用来演示抢库存。", "#8d8f93"),
]


def seed(db: Session) -> None:
    if db.query(Item).first():
        return
    for name, price, stock, category, brand, spec, blurb, tone in ITEMS:
        db.add(
            Item(
                name=name,
                price=price,
                stock=stock,
                category=category,
                brand=brand,
                spec=spec,
                blurb=blurb,
                tone=tone,
            )
        )
    user = User(
        username="demo",
        password=hash_password("123456"),
        phone="13800000000",
        balance=300000,
    )
    db.add(user)
    db.flush()
    db.add(
        Address(
            user_id=user.id,
            province="北京市",
            city="朝阳区",
            town="酒仙桥",
            street="北巷 12 号",
            contact="演示用户",
            mobile="13800000000",
            is_default=1,
        )
    )
    db.commit()
