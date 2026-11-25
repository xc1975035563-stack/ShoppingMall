"""交易失败用稳定业务码返回，页面和脚本都读 message。"""

from fastapi import HTTPException


class TradeError(HTTPException):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        super().__init__(status_code=status, detail={"code": code, "message": message})
