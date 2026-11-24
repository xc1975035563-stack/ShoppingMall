const CATEGORIES = ["", "数码", "家居", "服饰", "食品"];
const PHOTOS = {
  "橡木机械键盘": "keyboard.jpg",
  "手冲陶瓷壶": "kettle.jpg",
  "亚麻托特包": "tote.jpg",
  "头戴降噪耳机": "headphones.jpg",
  "黄铜书桌灯": "lamp.jpg",
  "手帐三件套": "notebook.jpg",
  "耶加雪菲咖啡豆": "coffee.jpg",
  "羊毛围巾": "scarf.jpg",
};

function photoSrc(name) {
  const file = PHOTOS[name];
  return file ? `/assets/images/${file}` : "";
}

function photo(name) {
  const src = photoSrc(name);
  return src ? `<img src="${src}" alt="${name}" />` : "";
}

const state = {
  view: "shop",
  user: null,
  token: localStorage.getItem("mall_token") || "",
  items: [],
  category: "",
  keyword: "",
  cart: [],
  orders: [],
  orderTab: "all",
  addresses: [],
  addressId: null,
  detail: null,
  detailQty: 1,
  checkoutLines: [],
  payOrder: null,
  authMode: "login",
  labTab: "agent",
  labMessages: [],
  labPending: null,
  labTrace: [],
  labCitations: [],
};

const app = document.querySelector("#app");
const account = document.querySelector("#account");
const toast = document.querySelector("#toast");

function money(fen) {
  const [yuan, cent] = (fen / 100).toFixed(2).split(".");
  return `<span class="g-price"><em>¥</em><b>${Number(yuan).toLocaleString("zh-CN")}</b><i>.${cent}</i></span>`;
}

function plainYuan(fen) {
  return (fen / 100).toLocaleString("zh-CN", { style: "currency", currency: "CNY" });
}

function showToast(message) {
  toast.hidden = false;
  toast.textContent = message;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 2200);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    logout(false);
    showToast(data.detail || "请先登录");
    throw new Error(data.detail || "请先登录");
  }
  if (!response.ok) {
    const message = data.detail || "请求失败";
    showToast(message);
    throw new Error(message);
  }
  return data;
}

function logout(renderNow = true) {
  state.token = "";
  state.user = null;
  state.cart = [];
  localStorage.removeItem("mall_token");
  if (renderNow) render();
}

function setUser(payload) {
  state.token = payload.token;
  state.user = payload.user;
  localStorage.setItem("mall_token", payload.token);
}

async function refreshUser() {
  if (!state.token) return;
  state.user = await api("/api/users/me");
}

async function loadShop() {
  const query = new URLSearchParams({ category: state.category, keyword: state.keyword });
  const page = await api(`/api/items?${query}`);
  state.items = page.list;
}

async function loadCart() {
  if (!state.token) { state.cart = []; return; }
  state.cart = await api("/api/carts");
}

async function loadOrders() {
  state.orders = await api("/api/orders");
}

async function loadAddresses() {
  state.addresses = await api("/api/addresses");
  const preferred = state.addresses.find((item) => item.is_default) || state.addresses[0];
  state.addressId = preferred ? preferred.id : null;
}

function renderAccount() {
  if (!state.user) {
    account.innerHTML = `
      <button type="button" id="open-auth">你好，请登录</button>
      <button type="button" id="open-register">免费注册</button>
      <button type="button" data-view="orders">我的订单</button>
      <button type="button" data-view="lab">实验室</button>`;
    document.querySelector("#open-auth").onclick = () => { state.authMode = "login"; state.view = "auth"; render(); };
    document.querySelector("#open-register").onclick = () => { state.authMode = "register"; state.view = "auth"; render(); };
    return;
  }
  account.innerHTML = `
    <span class="hello">${state.user.username}</span>
    <span>余额 ${plainYuan(state.user.balance)}</span>
    <button type="button" data-view="orders">我的订单</button>
    <button type="button" data-view="lab">实验室</button>
    <button type="button" id="logout">退出</button>`;
  document.querySelector("#logout").onclick = () => logout();
}

function renderNav() {
  document.querySelector("#cate-nav").innerHTML = CATEGORIES.map((name) =>
    `<button type="button" class="${state.category === name && state.view === "shop" ? "on" : ""}" data-cat="${name}">${name || "首页"}</button>`
  ).join("");
  document.querySelectorAll("#cate-nav [data-cat]").forEach((button) => {
    button.onclick = async () => {
      state.category = button.dataset.cat;
      if (!state.category) {
        state.keyword = "";
        document.querySelector("#keyword").value = "";
      }
      state.view = "shop";
      await loadShop();
      render();
    };
  });
  document.querySelector("#cart-count").textContent = state.cart.reduce((sum, row) => sum + row.num, 0);
}

function render() {
  renderAccount();
  renderNav();
  const views = {
    shop: renderShop,
    cart: renderCart,
    orders: renderOrders,
    checkout: renderCheckout,
    pay: renderPay,
    auth: renderAuth,
    detail: renderDetail,
    lab: renderLab,
  };
  (views[state.view] || renderShop)();
}

function renderShop() {
  const title = state.keyword ? `“${state.keyword}”的搜索结果` : (state.category || "为你推荐");
  app.innerHTML = `
    <section class="home-top">
      <div class="cat-menu">
        ${CATEGORIES.filter(Boolean).map((name) => `<button type="button" class="${state.category === name ? "on" : ""}" data-side="${name}">${name}</button>`).join("")}
      </div>
      <div class="banner" style="background-image:url('/assets/images/banner.jpg')">
        <span class="banner-tag">北巷自营</span>
        <h2>${state.category || "今日值得买"}</h2>
        <p>${state.items.length} 件在售 · 下单锁定库存 · 支持余额支付</p>
      </div>
      <aside class="user-card">
        <div class="avatar">${state.user ? state.user.username.slice(0, 1) : "北"}</div>
        <p class="name">${state.user ? `Hi，${state.user.username}` : "Hi，请登录"}</p>
        <p class="balance">${state.user ? `账户余额 ${plainYuan(state.user.balance)}` : "登录后查看余额"}</p>
        ${state.user ? "" : `<div class="user-actions"><button type="button" class="btn-line" id="side-login">登录</button><button type="button" class="btn-line" id="side-reg">注册</button></div>`}
        <div class="quick">
          <button type="button" data-view="orders">待支付</button>
          <button type="button" data-view="cart">购物车</button>
          <button type="button" data-view="lab">实验室</button>
        </div>
      </aside>
    </section>
    <section class="floor">
      <div class="floor-hd"><h3>${title}</h3><span>共 ${state.items.length} 个商品</span></div>
      <div class="grid">
        ${state.items.map((item) => `
          <button class="goods" type="button" data-id="${item.id}">
            <div class="pic">${photo(item.name)}</div>
            ${money(item.price)}
            <div class="g-name">${item.name} ${item.spec}</div>
            <div class="g-extra"><span>已售 ${item.sold}</span><span>${item.brand}</span></div>
          </button>`).join("") || `<div class="empty">没有找到相关商品</div>`}
      </div>
    </section>`;
  app.querySelectorAll("[data-side]").forEach((button) => {
    button.onclick = async () => {
      state.category = button.dataset.side;
      state.view = "shop";
      await loadShop();
      render();
    };
  });
  const sideLogin = document.querySelector("#side-login");
  const sideReg = document.querySelector("#side-reg");
  if (sideLogin) sideLogin.onclick = () => { state.authMode = "login"; state.view = "auth"; render(); };
  if (sideReg) sideReg.onclick = () => { state.authMode = "register"; state.view = "auth"; render(); };
  app.querySelectorAll(".goods").forEach((card) => {
    card.onclick = () => {
      state.detail = state.items.find((item) => item.id === Number(card.dataset.id));
      state.detailQty = 1;
      state.view = "detail";
      render();
    };
  });
}

function renderDetail() {
  const item = state.detail;
  if (!item) { state.view = "shop"; renderShop(); return; }
  app.innerHTML = `
    <div class="crumb">
      <button type="button" id="back-home">首页</button> &gt; ${item.category} &gt; ${item.name}
    </div>
    <section class="detail">
      <div class="detail-pic">${photo(item.name)}</div>
      <div>
        <h1>${item.name}</h1>
        <p>${item.blurb}</p>
        <div class="price-box">
          <div><span class="k">价格</span>${money(item.price)}</div>
        </div>
        <div class="spec-row"><span class="k">品牌</span><span>${item.brand}</span></div>
        <div class="spec-row"><span class="k">规格</span><span class="spec">${item.spec}</span></div>
        <div class="qty-row">
          <span class="k">数量</span>
          <div class="stepper">
            <button type="button" id="q-dec">-</button>
            <span id="q-num">${state.detailQty}</span>
            <button type="button" id="q-inc">+</button>
          </div>
          <span class="stock-note">库存 ${item.stock} 件 · 已售 ${item.sold}</span>
        </div>
        <div class="buy-row">
          <button class="btn-cart" type="button" id="add" ${item.stock < 1 ? "disabled" : ""}>加入购物车</button>
          <button class="btn-buy" type="button" id="buy" ${item.stock < 1 ? "disabled" : ""}>立即购买</button>
        </div>
      </div>
    </section>`;
  document.querySelector("#back-home").onclick = () => { state.view = "shop"; render(); };
  document.querySelector("#q-dec").onclick = () => { state.detailQty = Math.max(1, state.detailQty - 1); render(); };
  document.querySelector("#q-inc").onclick = () => { state.detailQty = Math.min(item.stock, state.detailQty + 1); render(); };
  document.querySelector("#add").onclick = () => addCurrent(false);
  document.querySelector("#buy").onclick = () => addCurrent(true);
}

async function addCurrent(buyNow) {
  const item = state.detail;
  if (!state.token) { state.authMode = "login"; state.view = "auth"; render(); return; }
  if (buyNow) {
    state.checkoutLines = [{
      item_id: item.id,
      num: state.detailQty,
      name: item.name,
      spec: item.spec,
      price: item.price,
      tone: item.tone,
    }];
    await loadAddresses();
    state.view = "checkout";
    render();
    return;
  }
  state.cart = await api("/api/carts", {
    method: "POST",
    body: JSON.stringify({ item_id: item.id, num: state.detailQty }),
  });
  showToast("已加入购物车");
  render();
}

function renderCart() {
  if (!requireAuth()) return;
  const count = state.cart.reduce((sum, row) => sum + row.num, 0);
  const total = state.cart.reduce((sum, row) => sum + row.price * row.num, 0);
  app.innerHTML = `
    <h2 class="cart-title">全部商品 ${count}</h2>
    ${state.cart.length ? `
      <div class="cart-page">
        <div class="cart-head"><span>商品</span><span>单价</span><span>数量</span><span>小计</span><span>操作</span></div>
        <div class="shop-tag">北巷自营</div>
        ${state.cart.map((row) => `
          <div class="cart-line">
            <div class="cart-goods">
              <div class="thumb">${photo(row.name)}</div>
              <div><div>${row.name}</div><div class="hint">${row.spec}</div></div>
            </div>
            <div>${plainYuan(row.price)}</div>
            <div class="stepper">
              <button type="button" data-dec="${row.id}">-</button>
              <span>${row.num}</span>
              <button type="button" data-inc="${row.id}">+</button>
            </div>
            <div class="sub">${plainYuan(row.price * row.num)}</div>
            <button class="link" type="button" data-del="${row.id}">删除</button>
          </div>`).join("")}
      </div>
      <div class="settle">
        <div class="sum">合计：<b>${plainYuan(total)}</b></div>
        <button class="btn-buy" type="button" id="checkout">去结算</button>
      </div>` : `<div class="empty">购物车空空如也，去挑点东西吧</div>`}`;
  app.querySelectorAll("[data-dec]").forEach((button) => { button.onclick = () => changeQty(Number(button.dataset.dec), -1); });
  app.querySelectorAll("[data-inc]").forEach((button) => { button.onclick = () => changeQty(Number(button.dataset.inc), 1); });
  app.querySelectorAll("[data-del]").forEach((button) => {
    button.onclick = async () => {
      state.cart = await api(`/api/carts/${button.dataset.del}`, { method: "DELETE" });
      render();
    };
  });
  const checkout = document.querySelector("#checkout");
  if (checkout) checkout.onclick = async () => {
    state.checkoutLines = state.cart.map((row) => ({ ...row }));
    await loadAddresses();
    state.view = "checkout";
    render();
  };
}

async function changeQty(id, delta) {
  const row = state.cart.find((item) => item.id === id);
  const next = row.num + delta;
  if (next < 1) state.cart = await api(`/api/carts/${id}`, { method: "DELETE" });
  else state.cart = await api(`/api/carts/${id}`, { method: "PUT", body: JSON.stringify({ num: next }) });
  render();
}

function renderCheckout() {
  if (!requireAuth()) return;
  const lines = state.checkoutLines;
  const count = lines.reduce((sum, row) => sum + row.num, 0);
  const total = lines.reduce((sum, row) => sum + row.price * row.num, 0);
  app.innerHTML = `
    <div class="sheet">
      <h3>确认收货地址</h3>
      <div class="addr-list">
        ${state.addresses.map((addr) => `
          <button class="addr ${addr.id === state.addressId ? "on" : ""}" type="button" data-addr="${addr.id}">
            <b>${addr.contact} ${addr.mobile}</b>
            <span>${addr.province}${addr.city}${addr.town}${addr.street}</span>
          </button>`).join("")}
      </div>
    </div>
    <div class="sheet" style="margin-top:12px">
      <h3>确认订单信息</h3>
      <div class="shop-tag">北巷自营</div>
      ${lines.map((row) => `
        <div class="order-line">
          <span>${row.name} ${row.spec} × ${row.num}</span>
          <span>${plainYuan(row.price * row.num)}</span>
        </div>`).join("")}
    </div>
    <div class="settle">
      <div class="sum">${count} 件商品　应付：<b>${plainYuan(total)}</b></div>
      <button class="btn-buy" type="button" id="place">提交订单</button>
    </div>`;
  app.querySelectorAll("[data-addr]").forEach((button) => {
    button.onclick = () => { state.addressId = Number(button.dataset.addr); render(); };
  });
  document.querySelector("#place").onclick = placeOrder;
}

async function placeOrder() {
  const button = document.querySelector("#place");
  button.disabled = true;
  const details = state.checkoutLines.map((row) => ({ item_id: row.item_id, num: row.num }));
  try {
    const order = await api("/api/orders", {
      method: "POST",
      body: JSON.stringify({ address_id: state.addressId, payment_type: 3, details }),
    });
    state.cart = state.cart.filter((row) => !details.some((line) => line.item_id === row.item_id));
    state.payOrder = await api("/api/pay-orders", {
      method: "POST",
      body: JSON.stringify({
        biz_order_no: order.id,
        amount: order.total_fee,
        pay_channel_code: "balance",
        pay_type: 5,
        order_info: order.details.map((line) => line.name).join("、"),
      }),
    });
    state.view = "pay";
    render();
  } catch {
    if (button) button.disabled = false;
  }
}

function renderPay() {
  const pay = state.payOrder;
  app.innerHTML = `
    <section class="cashier">
      <div class="cashier-top">
        <div>
          <h2>收银台</h2>
          <div class="hint">订单号 ${pay.biz_order_no} · 支付单 ${pay.id}</div>
        </div>
        <div class="due">应付金额<br />${money(pay.amount)}</div>
      </div>
      <div class="pay-list">
        <div class="pay-item"><b>余额支付</b><span class="hint">可用 ${state.user ? plainYuan(state.user.balance) : ""}</span></div>
      </div>
      <input class="pw" id="pw" type="password" value="123456" />
      <div class="hint" style="margin-left:24px">演示账号支付密码与登录密码相同</div>
      <button class="btn-buy" type="button" id="confirm">立即支付</button>
      <button class="btn-ghost" type="button" id="later" style="margin-left:8px">稍后支付</button>
    </section>`;
  document.querySelector("#later").onclick = () => { state.view = "orders"; loadOrders().then(render); };
  document.querySelector("#confirm").onclick = async () => {
    const result = await api(`/api/pay-orders/${pay.id}`, {
      method: "POST",
      body: JSON.stringify({ pw: document.querySelector("#pw").value }),
    });
    state.user.balance = result.balance;
    showToast("支付成功");
    state.view = "orders";
    state.orderTab = "paid";
    await loadOrders();
    await loadCart();
    render();
  };
}

function renderOrders() {
  if (!requireAuth()) return;
  const statusText = { 1: "等待付款", 2: "已付款", 5: "已关闭", 6: "已退款" };
  const tabs = [["all", "全部订单"], ["unpaid", "待付款"], ["paid", "已付款"]];
  const visible = state.orders.filter((order) => {
    if (state.orderTab === "unpaid") return order.status === 1;
    if (state.orderTab === "paid") return order.status === 2;
    return true;
  });
  app.innerHTML = `
    <div class="order-tabs">
      ${tabs.map(([key, label]) => `<button type="button" class="${state.orderTab === key ? "on" : ""}" data-tab="${key}">${label}</button>`).join("")}
    </div>
    ${visible.length ? visible.map((order) => `
      <article class="order-card">
        <div class="order-hd">
          <span>${order.create_time.replace("T", " ").slice(0, 19)}　订单号 ${order.id}　北巷自营</span>
          <span class="st ${order.status === 2 ? "paid" : ""}">${statusText[order.status] || order.status}</span>
        </div>
        ${order.details.map((line) => `<div class="order-line"><span>${line.name} × ${line.num}</span><span>${plainYuan(line.price * line.num)}</span></div>`).join("")}
        <div class="order-ft">
          <span>${order.contact} ${order.full_address}</span>
          <span>实付 <b style="color:#e1251b">${plainYuan(order.total_fee)}</b>
            ${order.status === 1 ? `<button class="btn-buy pay-btn" type="button" data-pay="${order.id}" data-fee="${order.total_fee}">付款</button>` : ""}
          </span>
        </div>
      </article>`).join("") : `<div class="empty">还没有相关订单</div>`}`;
  app.querySelectorAll("[data-tab]").forEach((button) => {
    button.onclick = () => { state.orderTab = button.dataset.tab; render(); };
  });
  app.querySelectorAll("[data-pay]").forEach((button) => {
    button.onclick = async () => {
      state.payOrder = await api("/api/pay-orders", {
        method: "POST",
        body: JSON.stringify({
          biz_order_no: Number(button.dataset.pay),
          amount: Number(button.dataset.fee),
          pay_channel_code: "balance",
          pay_type: 5,
        }),
      });
      state.view = "pay";
      render();
    };
  });
}

const REVIEW_SAMPLE = [
  "def find_user(name):",
  "    sql = f\"SELECT * FROM users WHERE name = '{name}'\"",
  "    cursor.execute(sql)",
  "    password = \"admin123\"",
  "    try:",
  "        return eval(name)",
  "    except:",
  "        os.system(name)",
].join("\n");

function renderLab() {
  const tabs = [
    ["agent", "客服"],
    ["mind", "小模型"],
    ["review", "审查"],
    ["market", "行情"],
  ];
  app.innerHTML = `
    <div class="lab-tabs">
      ${tabs.map(([key, label]) => `<button type="button" class="${state.labTab === key ? "on" : ""}" data-lab="${key}">${label}</button>`).join("")}
    </div>
    <div id="lab-body"></div>`;
  app.querySelectorAll("[data-lab]").forEach((button) => {
    button.onclick = () => {
      state.labTab = button.dataset.lab;
      render();
    };
  });
  const body = document.querySelector("#lab-body");
  if (state.labTab === "agent") renderAgent(body);
  if (state.labTab === "mind") renderMind(body);
  if (state.labTab === "review") renderReview(body);
  if (state.labTab === "market") renderMarket(body);
}

function renderAgent(body) {
  if (!state.token) {
    body.innerHTML = `<div class="empty">登录后才能查自己的订单和余额</div>`;
    return;
  }
  const pending = state.labPending;
  body.innerHTML = `
    <section class="lab-card">
      <h3>客服</h3>
      <p class="hint">试试：耳机还有吗 / 有没有手机 / 那它能退吗。没有的商品会直接说暂时没有，并说明可以登记、后续持续关注。</p>
      ${pending ? `<div class="hit"><b>待确认</b> ${pending.action === "refund" ? "退款" : "改地址"} · 订单 ${pending.order_id}${pending.street ? " · " + pending.street : ""}</div>` : ""}
      <div class="chat-log" id="chat-log">
        ${state.labMessages.map(chatLine).join("") || `<div class="hint">还没有对话</div>`}
      </div>
      ${state.labTrace.length ? `<div class="trace">${state.labTrace.map(escapeHtml).join(" · ")}</div>` : ""}
      ${state.labCitations.length ? `<div class="cite">引用 ${state.labCitations.map((row) => escapeHtml(row.title)).join("、")}</div>` : ""}
      <form id="chat-form" class="lab-row">
        <input id="chat-text" placeholder="问政策、查订单，或说确认" autocomplete="off" />
        <button class="btn-buy" type="submit" id="chat-send">发送</button>
      </form>
    </section>`;
  const log = document.querySelector("#chat-log");
  log.scrollTop = log.scrollHeight;
  log.querySelectorAll("[data-item]").forEach((button) => {
    button.onclick = () => openItem(Number(button.dataset.item));
  });
  document.querySelector("#chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    sendChat();
  });
  document.querySelector("#chat-text").focus();
}

function chatLine(row) {
  const mine = row.role === "user";
  const cards = mine ? "" : (row.cards || []).map((card) => `
    <button type="button" class="sku-card" data-item="${card.id}">
      <img src="${photoSrc(card.name)}" alt="" />
      <span>
        <b>${escapeHtml(card.name)}</b>
        <i>${escapeHtml(card.spec || "")}</i>
        <em>${plainYuan(card.price)}</em>
        <small>查看详情，直接下单</small>
      </span>
    </button>`).join("");
  return `<div class="bubble ${mine ? "user" : "assist"}">${escapeHtml(row.content)}${cards}</div>`;
}

async function openItem(itemId) {
  let item = state.items.find((row) => row.id === itemId);
  if (!item) item = await api(`/api/items/${itemId}`);
  state.detail = item;
  state.detailQty = 1;
  state.view = "detail";
  render();
}

async function sendChat() {
  const input = document.querySelector("#chat-text");
  const message = input.value.trim();
  if (!message || sendChat.busy) return;
  sendChat.busy = true;
  const previous = state.labMessages;
  state.labMessages = [...previous, { role: "user", content: message }];
  render();
  const sending = document.querySelector("#chat-send");
  if (sending) sending.textContent = "发送中";
  try {
    const data = await api("/api/lab/agent", { method: "POST", body: JSON.stringify({ message }) });
    state.labMessages = data.messages;
    state.labPending = data.pending;
    state.labTrace = data.trace || [];
    state.labCitations = data.citations || [];
    if (data.route === "confirm") await refreshUser();
    render();
  } catch {
    state.labMessages = previous;
    render();
    const box = document.querySelector("#chat-text");
    if (box) box.value = message;
  } finally {
    sendChat.busy = false;
  }
}

function renderMind(body) {
  body.innerHTML = `
    <section class="lab-card">
      <h3>字符级单层模型</h3>
      <p class="hint" id="mind-meta">读取训练状态…</p>
      <div class="lab-row">
        <button class="btn-buy" type="button" id="mind-train">用知识库训练</button>
        <input id="mind-prompt" value="退款" />
        <button class="btn-ghost" type="button" id="mind-gen">续写</button>
      </div>
      <pre class="chat-log" id="mind-out"></pre>
    </section>`;
  document.querySelector("#mind-train").onclick = async () => {
    const meta = await api("/api/lab/mind/train", { method: "POST", body: JSON.stringify({ steps: 400 }) });
    document.querySelector("#mind-meta").textContent = mindText(meta);
    showToast("训练完成");
  };
  document.querySelector("#mind-gen").onclick = async () => {
    const prompt = document.querySelector("#mind-prompt").value;
    const data = await api("/api/lab/mind/generate", { method: "POST", body: JSON.stringify({ prompt, n: 40 }) });
    document.querySelector("#mind-out").textContent = data.text;
  };
  api("/api/lab/mind").then((meta) => {
    const node = document.querySelector("#mind-meta");
    if (node) node.textContent = mindText(meta);
  }).catch(() => {});
}

function mindText(meta) {
  if (!meta.trained && meta.loss_end == null) return "还没训练。语料是退货、配送和商品说明。";
  return `词表 ${meta.vocab} 字，训练 ${meta.steps} 步。前 20 步平均损失 ${meta.loss_start}，后 20 步 ${meta.loss_end}。`;
}

function renderReview(body) {
  body.innerHTML = `
    <section class="lab-card">
      <h3>规则审查</h3>
      <p class="hint">只解析语法树，不执行这段代码。命中之后才写行级说明。扫描 app 目录时，会指出演示用的 JWT 密钥。</p>
      <textarea id="review-code"></textarea>
      <div class="lab-row">
        <button class="btn-buy" type="button" id="review-run">审查这段</button>
        <button class="btn-ghost" type="button" id="review-app">扫描 app 目录</button>
      </div>
      <div id="review-out"></div>
    </section>`;
  document.querySelector("#review-code").value = REVIEW_SAMPLE;
  document.querySelector("#review-run").onclick = async () => {
    const code = document.querySelector("#review-code").value;
    paintReview(await api("/api/lab/review", { method: "POST", body: JSON.stringify({ code }) }));
  };
  document.querySelector("#review-app").onclick = async () => {
    paintReview(await api("/api/lab/review/app"));
  };
}

function paintReview(data) {
  const out = document.querySelector("#review-out");
  const rows = (data.comments || []).map((row) => `
    <div class="finding"><b class="${row.severity}">${row.file ? row.file + " " : ""}第 ${row.line} 行 · ${row.rule}</b><div>${escapeHtml(row.message)}</div></div>`).join("");
  out.innerHTML = `<p>${escapeHtml(data.summary || "")}</p>${rows}`;
}

function renderMarket(body) {
  const today = new Date().toISOString().slice(0, 10);
  body.innerHTML = `
    <section class="lab-card">
      <h3>行情日报</h3>
      <p class="hint">同一天成功后再跑会直接返回原日报。勾选故障后，第一次拉主源会失败，重试后改用兜底行情。</p>
      <div class="lab-row">
        <input id="market-date" value="${today}" />
        <label class="hint"><input type="checkbox" id="market-fail" /> 主源故障</label>
        <button class="btn-buy" type="button" id="market-run">跑流水线</button>
      </div>
      <div id="market-out"></div>
    </section>`;
  document.querySelector("#market-run").onclick = async () => {
    const payload = {
      trade_date: document.querySelector("#market-date").value.trim(),
      fail_primary: document.querySelector("#market-fail").checked,
    };
    paintMarket(await api("/api/lab/market/run", { method: "POST", body: JSON.stringify(payload) }));
  };
  api("/api/lab/market").then((data) => {
    if (data && data.report && document.querySelector("#market-out")) paintMarket(data);
  }).catch(() => {});
}

function paintMarket(data) {
  const out = document.querySelector("#market-out");
  if (!out || !data.report) return;
  const quotes = (data.quotes || []).map((row) => `
    <div class="quote-line"><span>${row.name} ${row.symbol}</span><span>${(row.price_cent / 100).toFixed(2)}（${(row.change_bp / 100).toFixed(2)}%）</span></div>`).join("");
  out.innerHTML = `
    <p>${data.idempotent_hit ? "命中当日已成功任务，没有重新入库。" : "本次写库完成。"} 尝试 ${data.attempts} 次${data.used_fallback ? "，已改用兜底行情" : ""}。新新闻 ${data.new_news} 条。摘要成本 ${data.cost_units}/${data.cost_cap}。</p>
    ${data.last_error ? `<p class="hint">主源：${escapeHtml(data.last_error)}</p>` : ""}
    ${quotes}
    <pre class="chat-log">${escapeHtml(data.report)}</pre>`;
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function renderAuth() {
  const login = state.authMode === "login";
  app.innerHTML = `
    <section class="login-wrap">
      <div class="login-side" style="background-image:url('/assets/images/banner.jpg')">
        <div>北巷自营</div>
        <h2>多快好省<br />逛北巷</h2>
        <p>登录后可使用余额支付</p>
      </div>
      <div class="login-box">
        <div class="login-tabs">
          <button type="button" class="${login ? "on" : ""}" data-mode="login">账户登录</button>
          <button type="button" class="${login ? "" : "on"}" data-mode="register">免费注册</button>
        </div>
        <label>用户名</label>
        <input id="username" value="${login ? "demo" : ""}" />
        <label>密码</label>
        <input id="password" type="password" value="${login ? "123456" : ""}" />
        ${login ? "" : `<label>手机</label><input id="phone" placeholder="选填" />`}
        <p class="hint">${login ? "演示账号 demo / 123456" : "新用户赠送 1000 元余额"}</p>
        <button class="btn-buy" type="button" id="submit">${login ? "登 录" : "注 册"}</button>
      </div>
    </section>`;
  app.querySelectorAll("[data-mode]").forEach((button) => {
    button.onclick = () => { state.authMode = button.dataset.mode; render(); };
  });
  document.querySelector("#submit").onclick = submitAuth;
}

async function submitAuth() {
  const body = {
    username: document.querySelector("#username").value.trim(),
    password: document.querySelector("#password").value,
  };
  const path = state.authMode === "login" ? "/api/auth/login" : "/api/auth/register";
  if (state.authMode === "register") body.phone = document.querySelector("#phone").value.trim();
  const payload = await api(path, { method: "POST", body: JSON.stringify(body) });
  setUser(payload);
  await loadCart();
  state.view = "shop";
  showToast("登录成功");
  render();
}

function requireAuth() {
  if (state.token) return true;
  state.authMode = "login";
  state.view = "auth";
  renderAuth();
  renderAccount();
  return false;
}

document.body.addEventListener("click", async (event) => {
  const hot = event.target.closest("[data-hot]");
  if (hot) {
    state.keyword = hot.dataset.hot;
    document.querySelector("#keyword").value = state.keyword;
    state.category = "";
    state.view = "shop";
    await loadShop();
    render();
    return;
  }
  const button = event.target.closest("[data-view]");
  if (!button || button.closest("#cate-nav")) return;
  state.view = button.dataset.view;
  if (state.view === "orders" && state.token) await loadOrders();
  if (state.view === "cart" && state.token) await loadCart();
  if (state.view === "lab" && state.token && state.labTab === "agent") {
    const data = await api("/api/lab/agent");
    state.labMessages = data.messages || [];
    state.labPending = data.pending;
  }
  if (state.view === "shop") {
    if (button.classList.contains("logo")) {
      state.keyword = "";
      state.category = "";
      document.querySelector("#keyword").value = "";
    }
    await loadShop();
  }
  render();
});

document.querySelector("#search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.keyword = document.querySelector("#keyword").value.trim();
  state.category = "";
  state.view = "shop";
  await loadShop();
  render();
});

(async function start() {
  await loadShop();
  if (state.token) {
    try {
      await refreshUser();
      await loadCart();
    } catch {
      logout(false);
    }
  }
  render();
})();
