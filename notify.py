"""บอท Telegram: แจ้งจุดซื้อ/จุดขาย และรับคำสั่งบันทึกหุ้นที่ซื้อจริง

ทำงานบน GitHub Actions ตามเวลา (ไม่ต้องเปิดคอม):
    python notify.py daily-set   สรุปหุ้นไทยหลังตลาดปิด + อัปเดต Stop ของหุ้นที่ถือ
    python notify.py daily-us    สรุปหุ้นอเมริกาหลังตลาดปิด
    python notify.py intraday    ระหว่างวัน: เตือนชน Stop / ทะลุจุดซื้อ
    python notify.py commands    รับคำสั่งจาก Telegram อย่างเดียว

ตัวแปรแวดล้อม: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, STATE_KEY (กุญแจเข้ารหัสไฟล์สถานะ), SITE_URL
ถ้าไม่มี TELEGRAM_BOT_TOKEN จะพิมพ์ข้อความออกจอแทน (ใช้ทดสอบ)
"""
import html
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import config as C
from paths import BASE

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
SITE_URL = os.environ.get("SITE_URL", "").strip()
STATE_DIR = os.path.join(BASE, "state")
SITE_DATA = os.path.join(BASE, "site", "data")
BKK = timezone(timedelta(hours=7))
E = html.escape


# ------------------------------------------------------------ สถานะ (เข้ารหัสเพราะ repo เป็นสาธารณะ)
def _fernet():
    key = os.environ.get("STATE_KEY", "").strip()
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def load_state():
    f = _fernet()
    enc, plain = os.path.join(STATE_DIR, "state.enc"), os.path.join(STATE_DIR, "state.json")
    st = None
    if f and os.path.exists(enc):
        with open(enc, "rb") as fh:
            st = json.loads(f.decrypt(fh.read()))
    elif not f and os.path.exists(plain):
        with open(plain, encoding="utf-8") as fh:
            st = json.load(fh)
    st = st or {}
    st.setdefault("offset", 0)
    st.setdefault("capital", C.CAPITAL)
    st.setdefault("holdings", {})
    st.setdefault("watch", {})
    st.setdefault("sent", {})       # กันแจ้งเตือนซ้ำ: key -> วันที่
    st.setdefault("history", [])
    return st


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    today = now().date().isoformat()
    st["sent"] = {k: v for k, v in st["sent"].items() if v >= (now() - timedelta(days=10)).date().isoformat() or v == today}
    st["history"] = st["history"][-200:]
    data = json.dumps(st, ensure_ascii=False, indent=1).encode()
    f = _fernet()
    if f:
        with open(os.path.join(STATE_DIR, "state.enc"), "wb") as fh:
            fh.write(f.encrypt(data))
    else:
        with open(os.path.join(STATE_DIR, "state.json"), "wb") as fh:
            fh.write(data)


def now():
    return datetime.now(BKK)


# ------------------------------------------------------------ Telegram
def tg(method, **params):
    if not TOKEN:
        return None
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}",
                                 data=json.dumps(params).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def send(text, chat=None):
    chat = chat or CHAT
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) > 3800:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    parts.append(cur)
    for p in parts:
        if not p.strip():
            continue
        if not TOKEN or not chat:
            print("---- (ไม่ได้ส่ง Telegram — ทดสอบ) ----\n" + p)
            continue
        try:
            tg("sendMessage", chat_id=chat, text=p, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            print("ส่ง Telegram ไม่สำเร็จ:", e)


# ------------------------------------------------------------ ข้อมูลราคา
def norm(t):
    t = t.strip().upper()
    return t if "." in t or t in C.US_STOCKS or t.startswith("^") else f"{t}.BK"


def short(t):
    return t.replace(".BK", "")


def is_th(t):
    return t.endswith(".BK")


def fx(t):
    if is_th(t):
        return 1.0
    from data import usd_thb
    return usd_thb()


def latest(tickers):
    """ราคาล่าสุด (รวมแท่งของวันนี้ถ้าตลาดเปิดอยู่) + ATR, เส้น 200 วัน"""
    from data import get_prices
    from indicators import add_indicators
    from strategy import add_signals
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {}
    px = get_prices(tickers, "2y", refresh=True)
    out = {}
    for t, d in px.items():
        df = add_signals(add_indicators(d))
        r = df.iloc[-1]
        out[t] = {"close": float(r["Close"]), "low": float(r["Low"]), "high": float(r["High"]),
                  "atr": float(r["ATR"]), "exit_trend": bool(r["exit_trend"]),
                  "date": df.index[-1].date().isoformat(), "vol_ratio": float(r["VolRatio"])}
    return out


def site_json(path):
    """อ่านข้อมูลที่เว็บสร้างไว้ (ไฟล์ในเครื่องก่อน ไม่มีก็โหลดจากเว็บ)"""
    local = os.path.join(SITE_DATA, path)
    if os.path.exists(local):
        with open(local, encoding="utf-8") as f:
            return json.load(f)
    if SITE_URL:
        try:
            with urllib.request.urlopen(SITE_URL.rstrip("/") + "/data/" + path, timeout=30) as r:
                return json.load(r)
        except Exception:
            return None
    return None


def size(plan_entry, plan_stop, t, capital, strong=True):
    rate = fx(t)
    cap = capital * (1 if strong else 0.5) / rate
    risk = plan_entry - plan_stop
    lot = C.LOT_SIZE_TH if is_th(t) else 1
    sh = min(cap * C.RISK_PER_TRADE / risk, cap * C.MAX_POSITION_PCT / plan_entry)
    return max(0, int(sh // lot * lot))


def money(x, d=2):
    return f"{x:,.{d}f}"


# ------------------------------------------------------------ คำสั่งจาก Telegram
HELP = """<b>บอทหุ้นเด่น</b> — แจ้งจุดซื้อ/จุดขายอัตโนมัติ

<b>บันทึกเมื่อซื้อขายจริงใน KS</b> (บอทจะเฝ้าจุดขายให้)
/buy GULF 300 61.25 — ซื้อ GULF 300 หุ้น ราคา 61.25
/buy GULF — ไม่ใส่จำนวน/ราคา = ใช้ราคาล่าสุดและจำนวนตามแผน
/sell GULF 64.5 — ขายทั้งหมด (ไม่ใส่ราคา = ราคาล่าสุด)
/stop GULF 60 — ตั้งจุดตัดขาดทุนเอง

<b>ดูข้อมูล</b>
/port — หุ้นที่ถือ กำไร/ขาดทุน และ Stop
/signals — หุ้นที่มีสัญญาณซื้อล่าสุด
/stock PTT — สรุปหุ้นรายตัว
/news — ข่าวหุ้นล่าสุด · /news GULF — ข่าวของหุ้นตัวนั้น
/capital 200000 — ตั้งเงินทุนสำหรับคำนวณจำนวนหุ้น

บอทจะส่งข่าวใหม่ของหุ้นที่คุณถือให้อัตโนมัติ
บอทตอบกลับภายใน ~30 นาทีช่วงตลาดเปิด (นอกเวลาตลาดภายใน ~3 ชั่วโมง)"""


def cmd_buy(st, args):
    if not args:
        return "ใช้แบบนี้: /buy GULF 300 61.25"
    t = norm(args[0])
    if t in st["holdings"]:
        return f"มี {short(t)} อยู่แล้ว (ขายก่อนด้วย /sell {short(t)})"
    lp = latest([t]).get(t)
    if not lp:
        return f"ไม่พบข้อมูลหุ้น {E(short(t))}"
    shares = int(float(args[1].replace(",", ""))) if len(args) > 1 else None
    price = float(args[2].replace(",", "")) if len(args) > 2 else lp["close"]
    from strategy import to_tick
    stop = round(price - C.ATR_STOP_MULT * lp["atr"], 2)
    if is_th(t):
        stop = to_tick(stop, "down")          # ราคาที่ตั้งใน Streaming ได้จริง
    if not shares:
        shares = size(price, stop, t, st["capital"])
    if shares <= 0:
        return "จำนวนหุ้นตามแผนไม่ถึง 1 lot — ระบุจำนวนเอง เช่น /buy GULF 100"
    target = round(price + C.TARGET_R * (price - stop), 2)
    if is_th(t):
        target = to_tick(target, "down")
    st["holdings"][t] = {"shares": shares, "entry": price, "stop": stop, "risk": price - stop,
                         "high": price, "date": now().date().isoformat(), "fx": fx(t)}
    st["history"].append({"d": now().isoformat(timespec="minutes"), "side": "BUY", "t": t,
                          "shares": shares, "price": price})
    return (f"✅ บันทึกซื้อ <b>{short(t)}</b> {shares:,} หุ้น @ {money(price)}\n"
            f"🛑 Stop {money(stop)} ({(stop / price - 1) * 100:.1f}%) — จะเตือนเมื่อราคาแตะ\n"
            f"🎯 เป้าแรก {money(target)} (+{(target / price - 1) * 100:.1f}%)\n"
            f"อย่าลืมตั้งคำสั่ง Stop ในแอป KS ด้วย")


def cmd_sell(st, args):
    if not args:
        return "ใช้แบบนี้: /sell GULF 64.5"
    t = norm(args[0])
    h = st["holdings"].get(t)
    if not h:
        return f"ไม่มี {E(short(t))} ในรายการที่ถือ (ดู /port)"
    price = float(args[1].replace(",", "")) if len(args) > 1 else latest([t])[t]["close"]
    cost = C.COMMISSION + C.SLIPPAGE
    pnl = h["shares"] * (price * (1 - cost) - h["entry"] * (1 + cost)) * h.get("fx", 1)
    del st["holdings"][t]
    st["history"].append({"d": now().isoformat(timespec="minutes"), "side": "SELL", "t": t,
                          "shares": h["shares"], "price": price, "pnl": round(pnl)})
    icon = "🟢" if pnl > 0 else "🔴"
    return (f"{icon} บันทึกขาย <b>{short(t)}</b> {h['shares']:,} หุ้น @ {money(price)}\n"
            f"กำไร/ขาดทุนหลังค่าคอม ≈ {pnl:+,.0f} บาท ({(price / h['entry'] - 1) * 100:+.1f}%)")


def cmd_stop(st, args):
    if len(args) < 2:
        return "ใช้แบบนี้: /stop GULF 60"
    t = norm(args[0])
    if t not in st["holdings"]:
        return f"ไม่มี {E(short(t))} ในรายการที่ถือ"
    st["holdings"][t]["stop"] = float(args[1].replace(",", ""))
    st["sent"].pop(f"stop:{t}", None)
    return f"ตั้ง Stop {short(t)} = {money(st['holdings'][t]['stop'])} แล้ว"


def port_text(st, prices=None):
    hs = st["holdings"]
    if not hs:
        return "ยังไม่มีหุ้นที่บันทึกไว้ — ใช้ /buy เมื่อซื้อจริง"
    prices = prices or latest(list(hs))
    lines, tot_pnl = ["💼 <b>หุ้นที่ถือ</b>"], 0
    for t, h in hs.items():
        p = prices.get(t)
        if not p:
            lines.append(f"• {short(t)} — ดึงราคาไม่ได้")
            continue
        pnl = h["shares"] * (p["close"] - h["entry"]) * h.get("fx", 1)
        tot_pnl += pnl
        chg = (p["close"] / h["entry"] - 1) * 100
        gap = (h["stop"] / p["close"] - 1) * 100
        lines.append(f"{'🟢' if chg >= 0 else '🔴'} <b>{short(t)}</b> {money(p['close'])} ({chg:+.1f}%) "
                     f"{h['shares']:,} หุ้น · {pnl:+,.0f}฿\n    Stop {money(h['stop'])} (ห่าง {gap:.1f}%)")
    lines.append(f"\nรวมกำไร/ขาดทุนที่ยังไม่ขาย {tot_pnl:+,.0f} บาท")
    return "\n".join(lines)


def signals_text(st, mkt="set", limit=10):
    scan = site_json(f"scan_{mkt}.json")
    if not scan:
        return "ยังไม่มีข้อมูลสแกน"
    reg = next(iter(scan["regimes"].values()), {})
    buys = [r for r in scan["rows"] if r["status"] == "ซื้อ"]
    watch = [r for r in scan["rows"] if r["status"] == "รอจังหวะ"][:5]
    name = "หุ้นไทย" if mkt == "set" else "หุ้นอเมริกา"
    lines = [f"📊 <b>{name}</b> — {E(reg.get('text', ''))}"]
    if buys:
        lines.append(f"\n🟢 <b>สัญญาณซื้อ ({len(buys)})</b>")
        for r in buys[:limit]:
            p = r["plan"]
            sh = size(p["entry"], p["stop"], r["symbol"], st["capital"], reg.get("strong", True))
            lines.append(f"<b>{E(r['ticker'])}</b> {money(p['entry'])} · คะแนน {r['score']:.0f}"
                         f" · ซื้อขาย {r.get('value20_m', 0):,.0f} ล้าน/วัน\n"
                         f"    🛑 {money(p['stop'])} ({p['stop_pct']}%) 🎯 {money(p['target'])} (+{p['target_pct']}%)"
                         f" · {sh:,} หุ้น\n    {E(' · '.join(r['signals']))}")
            nw = next((n for n in news_items() if r["ticker"] in n["sym"]), None)
            if nw:
                lines.append("    " + news_line(nw))
    else:
        lines.append("\nวันนี้ไม่มีหุ้นผ่านทุกเงื่อนไข — ไม่ซื้อก็ไม่เป็นไร")
    if watch:
        lines.append("\n🟡 <b>รอจังหวะ (คะแนนสูงสุด)</b>")
        for r in watch:
            p = r["plan"]
            lines.append(f"<b>{E(r['ticker'])}</b> {money(r['close'])} → เบรก {money(p['breakout_level'] or 0)}"
                         f" / ย่อ {money(p['pullback_zone'][0])}–{money(p['pullback_zone'][1])}")
    if SITE_URL:
        lines.append(f"\n🔗 {SITE_URL}")
    return "\n".join(lines)


def stock_text(args):
    if not args:
        return "ใช้แบบนี้: /stock PTT"
    t = norm(args[0])
    d = site_json(f"stocks/s_{t}.json")
    if not d:
        return f"ไม่มีข้อมูล {E(short(t))} (มีเฉพาะหุ้นในรายชื่อที่ระบบติดตาม)"
    r, p, i = d["row"], d["row"]["plan"], d["ind"]
    return (f"<b>{E(r['ticker'])}</b> {E(r['name'])}\n"
            f"ราคา {money(r['close'])} · สถานะ <b>{r['status']}</b> · คะแนน {r['score']:.0f}/100\n"
            f"→ {E(r['how'])}\n"
            f"RSI {i['RSI']:.0f} · ADX {i['ADX']:.0f} · 6 เดือน {r['roc126']:+.1f}%\n"
            f"🛑 Stop {money(p['stop'])} · 🎯 เป้า {money(p['target'])}"
            + (f"\n🔗 {SITE_URL}#stock/{t}" if SITE_URL else ""))


def news_items():
    d = site_json("news.json")
    return d.get("items", []) if d else []


def news_line(n):
    dot = "🟢" if n.get("sen", 0) > 0 else "🔴" if n.get("sen", 0) < 0 else "▫️"
    return f'{dot} <a href="{E(n["l"])}">{E(n["t"])}</a> <i>({E(n["s"])})</i>'


def news_text(args):
    items = news_items()
    if not items:
        return "ยังไม่มีข้อมูลข่าว"
    if args:
        sym = short(norm(args[0]))
        sel = [n for n in items if sym in n["sym"]][:10]
        head = f"📰 <b>ข่าว {E(sym)}</b> (7 วันล่าสุด)"
        if not sel:
            return head + "\nยังไม่พบข่าว"
    else:
        sel = [n for n in items if n["sym"]][:12]
        head = "📰 <b>ข่าวหุ้นล่าสุด</b>"
    return head + "\n\n" + "\n\n".join(news_line(n) for n in sel)


def holding_news(st, hours=8, limit=6):
    """ข่าวใหม่ของหุ้นที่ถือ (ยังไม่เคยส่ง)"""
    held = {short(t) for t in st["holdings"]}
    if not held:
        return []
    cutoff = (now() - timedelta(hours=hours)).isoformat()
    out = []
    for n in news_items():
        hit = [x for x in n["sym"] if x in held]
        key = f"news:{n['id']}"
        if hit and n["d"] >= cutoff and key not in st["sent"]:
            st["sent"][key] = now().date().isoformat()
            out.append(f"<b>{', '.join(hit)}</b> · " + news_line(n))
            if len(out) >= limit:
                break
    return out


def refresh_news(st):
    """ดึงข่าวรอบสั้น (ระหว่างวัน) รวมข่าวเจาะหุ้นที่ถือ"""
    try:
        import news
        news.main(quick=True, extra=[short(t) for t in st["holdings"]])
    except Exception as e:
        print("ดึงข่าวไม่สำเร็จ:", e)


def process_commands(st):
    if not TOKEN:
        return
    try:
        res = tg("getUpdates", offset=st["offset"] + 1, timeout=0, allowed_updates=["message"])
    except Exception as e:
        print("อ่านข้อความ Telegram ไม่ได้:", e)
        return
    for u in res.get("result", []):
        st["offset"] = max(st["offset"], u["update_id"])
        msg = u.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if not text or (CHAT and chat != CHAT):
            continue                     # รับคำสั่งจากเจ้าของเท่านั้น
        parts = text.split()
        cmd, args = parts[0].split("@")[0].lower(), parts[1:]
        try:
            if cmd in ("/start", "/help"):
                reply = HELP
            elif cmd == "/buy":
                reply = cmd_buy(st, args)
            elif cmd == "/sell":
                reply = cmd_sell(st, args)
            elif cmd == "/stop":
                reply = cmd_stop(st, args)
            elif cmd == "/port":
                reply = port_text(st)
            elif cmd == "/signals":
                reply = signals_text(st, "set", 25)
            elif cmd == "/news":
                reply = news_text(args)
            elif cmd == "/stock":
                reply = stock_text(args)
            elif cmd == "/capital" and args:
                st["capital"] = float(args[0].replace(",", ""))
                reply = f"ตั้งเงินทุน {st['capital']:,.0f} บาทแล้ว"
            else:
                reply = "ไม่รู้จักคำสั่งนี้ พิมพ์ /help ดูคำสั่งทั้งหมด"
        except Exception as e:
            reply = f"ทำคำสั่งไม่สำเร็จ: {E(str(e))}"
        send(reply, chat)


# ------------------------------------------------------------ เฝ้าราคา
def market_open(mkt):
    n = now()
    if n.weekday() >= 5:
        return False
    if mkt == "set":
        return (10, 0) <= (n.hour, n.minute) <= (17, 0)
    u = n.astimezone(timezone.utc)
    return (13, 30) <= (u.hour, u.minute) <= (21, 0)


def check_holdings(st, markets, daily=False):
    hs = {t: h for t, h in st["holdings"].items() if ("set" if is_th(t) else "us") in markets}
    if not hs:
        return [], {}
    prices = latest(list(hs))
    today = now().date().isoformat()
    alerts = []
    for t, h in hs.items():
        p = prices.get(t)
        if not p:
            continue
        if p["low"] <= h["stop"] and st["sent"].get(f"stop:{t}") != today:
            alerts.append(f"🛑 <b>{short(t)} ชน Stop {money(h['stop'])}</b> (ล่าสุด {money(p['close'])}) → ควรขาย\n"
                          f"    ขายแล้วพิมพ์ /sell {short(t)} ราคาที่ขาย")
            st["sent"][f"stop:{t}"] = today
        elif daily and p["exit_trend"] and st["sent"].get(f"trend:{t}") != today:
            alerts.append(f"⚠️ <b>{short(t)} ปิดต่ำกว่าเส้น 200 วัน</b> → แนวโน้มขาขึ้นจบ ควรขาย")
            st["sent"][f"trend:{t}"] = today
        target = h["entry"] + C.TARGET_R * h.get("risk", C.ATR_STOP_MULT * p["atr"])
        if p["high"] >= target and f"target:{t}:{h['date']}" not in st["sent"]:
            alerts.append(f"🎯 <b>{short(t)} ถึงเป้า {money(target)}</b> → พิจารณาขายครึ่งหนึ่ง ที่เหลือถือตาม Stop")
            st["sent"][f"target:{t}:{h['date']}"] = today
        if daily:                                   # เลื่อน trailing stop ด้วยราคาปิด
            h["high"] = max(h["high"], p["close"])
            new_stop = round(max(h["stop"], h["high"] - C.ATR_TRAIL_MULT * p["atr"]), 2)
            if is_th(t):
                from strategy import to_tick
                new_stop = max(h["stop"], to_tick(new_stop, "down"))
            if new_stop > h["stop"] + 1e-9:
                alerts.append(f"⬆️ {short(t)} เลื่อน Stop {money(h['stop'])} → <b>{money(new_stop)}</b> (แก้ในแอป KS ด้วย)")
                h["stop"] = new_stop
    return alerts, prices


def update_watch(st, mkt):
    """เก็บจุดซื้อของหุ้นที่ 'รอจังหวะ' ไว้เฝ้าระหว่างวัน"""
    scan = site_json(f"scan_{mkt}.json")
    if not scan:
        return
    st["watch"] = {t: w for t, w in st["watch"].items() if ("set" if is_th(t) else "us") != mkt}
    for r in [r for r in scan["rows"] if r["status"] == "รอจังหวะ"][:15]:
        lvl = r["plan"].get("breakout_level")
        if lvl:
            st["watch"][r["symbol"]] = {"level": lvl, "stop_atr": r["plan"]["entry"] - r["plan"]["stop"]}


def check_watch(st, markets):
    ws = {t: w for t, w in st["watch"].items()
          if ("set" if is_th(t) else "us") in markets and t not in st["holdings"]}
    if not ws:
        return []
    prices = latest(list(ws))
    today = now().date().isoformat()
    out = []
    for t, w in ws.items():
        p = prices.get(t)
        if not p or p["date"] != today:
            continue
        if p["close"] > w["level"] and st["sent"].get(f"bo:{t}") != today:
            from strategy import to_tick
            stop = to_tick(p["close"] - w["stop_atr"], "down") if is_th(t) else p["close"] - w["stop_atr"]
            out.append(f"🚀 <b>{short(t)} ทะลุจุดซื้อ {money(w['level'])}</b> (ล่าสุด {money(p['close'])}, "
                       f"วอลุ่ม {p['vol_ratio']:.1f} เท่าของเฉลี่ย)\n"
                       f"    ถ้ายืนได้ถึงปิดตลาดและวอลุ่มหนุน = จุดซื้อ · Stop ~{money(stop)}")
            st["sent"][f"bo:{t}"] = today
    return out


# ------------------------------------------------------------ โหมดทำงาน
def run(mode):
    st = load_state()
    if mode in ("intraday", "commands"):
        refresh_news(st)
    process_commands(st)
    if mode in ("daily-set", "daily-us"):
        mkt = mode.split("-")[1]
        alerts, prices = check_holdings(st, [mkt], daily=True)
        update_watch(st, mkt)
        msg = signals_text(st, mkt)
        held = {t: h for t, h in st["holdings"].items() if ("set" if is_th(t) else "us") == mkt}
        if held:
            msg += "\n\n" + port_text({"holdings": held}, prices)
        if alerts:
            msg = "\n".join(alerts) + "\n\n" + msg
        hn = holding_news(st, hours=24)
        if hn:
            msg += "\n\n📰 <b>ข่าวหุ้นที่ถือ</b>\n" + "\n".join(hn)
        send(f"🗓 <b>สรุปหลังตลาดปิด {now():%d/%m/%Y}</b>\n\n" + msg)
    elif mode == "commands":
        hn = holding_news(st)
        if hn:
            send("📰 <b>ข่าวใหม่ของหุ้นที่ถือ</b>\n" + "\n".join(hn))
    elif mode == "intraday":
        markets = ["set"] if market_open("set") else []
        if markets:
            alerts, _ = check_holdings(st, markets)
            alerts += check_watch(st, markets)
            hn = holding_news(st)
            if hn:
                alerts.append("📰 <b>ข่าวใหม่ของหุ้นที่ถือ</b>\n" + "\n".join(hn))
            if alerts:
                send("⏰ <b>แจ้งเตือนระหว่างวัน</b>\n\n" + "\n\n".join(alerts))
    save_state(st)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "commands")
