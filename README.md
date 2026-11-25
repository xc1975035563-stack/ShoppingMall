# 北巷商城

对照黑马商城业务做的 Python 面试项目，当前是**单体第一阶段**：用户、商品、购物车、订单、余额支付在一个 FastAPI 进程里，金额以分存储。页面可以直接完成登录、加购、下单和支付。

下一步再拆成 `user` / `catalog` / `trade` 三个服务。下单和支付里的条件更新（库存、余额、支付状态）就是为那一步准备的。

## 运行

这台机器没有全局 `python`，用项目里的虚拟环境启动：

```bash
uv venv --python D:\infra\python\Rail\cpython-3.14-windows-x86_64-none\python.exe .venv
uv pip install -r requirements.txt --python .venv\Scripts\python.exe
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

浏览器打开 http://127.0.0.1:8000

演示账号 `demo` / `123456`，余额 3000 元。支付密码与登录密码相同。数据库是项目下的 `data/mall.db`，首次启动会写入商品和演示账号。

## 主链路

1. 登录签发 JWT。
2. 购物车只记商品和数量，结算时按商品当前单价重算。
3. 下单在一个事务里写订单和价格快照、清空对应购物车，并用 `stock >= num` 扣库存。
4. 支付单按业务订单号幂等。余额扣减和支付状态都带条件更新，重复支付会被拒绝。
5. 只有已支付订单可以退款。退款先把状态从已支付改成已退款，成功后才回补库存和余额。未支付不能退，重复退会被拒绝。已支付订单不能改收货地址。

失败时接口返回 `detail.code` 和 `detail.message`，例如 `STOCK_NOT_ENOUGH`、`PAY_ALREADY_SUCCESS`、`ADDRESS_CHANGE_FORBIDDEN`、`REFUND_NOT_PAID`、`REFUND_ALREADY_DONE`。下单、支付、退款、改地址会各写一行审计，记用户、订单、动作、成功或失败。日志里是同一条 JSON。接口 `GET /api/trade-audits` 只返回当前用户最近 50 条。

退款和改地址的接口是 `POST /api/orders/{id}/refund`、`POST /api/orders/{id}/address`，请求体 `{"street":"..."}`。页面上下单失败时会弹出 `message`。

## 交易用例

不读取、不修改 `data/mall.db`，用临时库跑完就删：

```bash
.venv\Scripts\python.exe scripts\demo_trade_cases.py
```

脚本会依次检查：

1. 购买数量大于库存时下单失败，库存不变。
2. 两笔同时抢最后 1 件，只有一笔成功，库存剩 0。
3. 同一笔订单支付两次，第二次返回 `PAY_ALREADY_SUCCESS`，余额只减少一次。
4. 已支付订单改地址返回 `ADDRESS_CHANGE_FORBIDDEN`。
5. 未支付订单退款返回 `REFUND_NOT_PAID`。
6. 已支付订单退款后库存和余额回到支付前，再退一次返回 `REFUND_ALREADY_DONE`，库存和余额不再变化。

页面上可以这样看前几条：把数量加到超过库存再下单；支付成功后对同一支付单再付一次。退款和改地址用上面的接口，或在客服里对未支付订单说「帮我退款」、对已支付订单说「把订单改成新地址」。

## 实验室

顶栏「实验室」里有四块，都不依赖外网模型：

- 客服：订单、库存、余额走工具；退货和配送走 BM25 + 哈希向量，RRF 后再按词面重排。退款和改地址要回复「确认」才写库。
- 小模型：用知识库正文训练字符级单层模型，看交叉熵是否下降，再按上一个字采样续写。
- 审查：用语法树扫拼接 SQL、`eval`、空 `except`、硬编码口令和 shell，只对命中的行写说明。
- 行情：按日期幂等。主源失败会重试并改走兜底行情，新闻按标题哈希去重，摘要有次数上限。
