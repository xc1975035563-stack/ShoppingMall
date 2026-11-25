"""关键写操作的结构化日志和审计行。失败在回滚后单独提交，避免和业务变更绑在一起丢掉。"""

import json
import logging

from sqlalchemy.orm import Session

from app.models import TradeAudit

logger = logging.getLogger("mall.trade")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def write_audit(
    db: Session,
    user_id: int,
    username: str,
    order_id: int | None,
    action: str,
    success: bool,
    code: str,
    message: str,
) -> None:
    db.add(
        TradeAudit(
            user_id=user_id,
            username=username,
            order_id=order_id,
            action=action,
            success=1 if success else 0,
            code=code,
            message=message[:256],
        )
    )
    logger.info(
        json.dumps(
            {
                "user_id": user_id,
                "username": username,
                "order_id": order_id,
                "action": action,
                "success": success,
                "code": code,
                "message": message,
            },
            ensure_ascii=False,
        )
    )
