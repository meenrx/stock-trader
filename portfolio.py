"""พอร์ตจำลอง (Paper trading) — ฝึกเทรดตามสัญญาณโดยไม่ใช้เงินจริง เก็บใน data/paper_portfolio.json"""
import json
import os
import threading
from datetime import date

import config as C
from data import get_prices, usd_thb
from indicators import add_indicators
from paths import DATA
from strategy import add_signals

PATH = os.path.join(DATA, "paper_portfolio.json")
_LOCK = threading.Lock()


class PaperError(ValueError):
    pass


def cost_rate():
    return C.COMMISSION + C.SLIPPAGE


def norm(t):
    t = t.strip().upper()
    return t if "." in t or t in C.US_STOCKS or t.startswith("^") else f"{t}.BK"


def load():
    if os.path.exists(PATH):
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"cash": C.CAPITAL, "start_capital": C.CAPITAL, "positions": {}, "history": []}


def save(p):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


def fx(t):
    return 1.0 if t.endswith(".BK") else usd_thb()


def _frame(t):
    px = get_prices([t], "2y", refresh=True)
    if t not in px:
        raise PaperError(f"ไม่พบข้อมูลหุ้น {t}")
    return add_signals(add_indicators(px[t]))


def buy(ticker, shares=None, price=None):
    t = norm(ticker)
    df = _frame(t)
    r = df.iloc[-1]
    with _LOCK:
        p = load()
        if t in p["positions"]:
            raise PaperError(f"มี {t} อยู่ในพอร์ตแล้ว")
        px = float(price or r["Close"])
        stop = px - C.ATR_STOP_MULT * float(r["ATR"])
        rate = fx(t)
        equity = p["cash"] + sum(v["shares"] * v["last"] * v.get("fx", 1) for v in p["positions"].values())
        lot = C.LOT_SIZE_TH if t.endswith(".BK") else 1
        if not shares:
            shares = min(equity * C.RISK_PER_TRADE / ((px - stop) * rate),
                         equity * C.MAX_POSITION_PCT / (px * rate))
        shares = int(int(shares) // lot * lot)
        cost = shares * px * rate * (1 + cost_rate())
        if shares <= 0:
            raise PaperError("จำนวนหุ้นตามเกณฑ์ความเสี่ยงไม่ถึง 1 lot (ลองเพิ่มทุนหรือระบุจำนวนเอง)")
        if cost > p["cash"]:
            raise PaperError(f"เงินสดไม่พอ (ต้องใช้ {cost:,.0f} มี {p['cash']:,.0f})")
        p["cash"] -= cost
        p["positions"][t] = {"shares": shares, "entry": px, "stop": round(stop, 2),
                             "risk": round(px - stop, 4), "high": px, "last": px,
                             "date": str(date.today()), "fx": rate}
        p["history"].append({"date": str(date.today()), "side": "BUY", "ticker": t,
                             "shares": shares, "price": px})
        save(p)
    return {"msg": f"ซื้อ {t.replace('.BK', '')} {shares:,} หุ้น @ {px:,.2f}  Stop {stop:,.2f}",
            "cash": p["cash"]}


def sell(ticker, price=None):
    t = norm(ticker)
    with _LOCK:
        if t not in load()["positions"]:
            raise PaperError(f"ไม่มี {t} ในพอร์ต")
    px = float(price or _frame(t).iloc[-1]["Close"])
    with _LOCK:
        p = load()
        pos = p["positions"].pop(t)
        rate, rate0 = fx(t), pos.get("fx", 1)
        p["cash"] += pos["shares"] * px * rate * (1 - cost_rate())
        pnl = pos["shares"] * (px * rate * (1 - cost_rate()) - pos["entry"] * rate0 * (1 + cost_rate()))
        p["history"].append({"date": str(date.today()), "side": "SELL", "ticker": t,
                             "shares": pos["shares"], "price": px, "pnl": round(pnl, 0)})
        save(p)
    return {"msg": f"ขาย {t.replace('.BK', '')} @ {px:,.2f} กำไร/ขาดทุน {pnl:+,.0f}", "pnl": pnl}


def status(update=True):
    """อัปเดตราคา เลื่อน trailing stop และเตือนเมื่อควรขาย"""
    with _LOCK:
        p = load()
    px = get_prices(list(p["positions"]), "2y", refresh=True) if update and p["positions"] else {}
    rows, alerts, total = [], [], p["cash"]
    for t, v in p["positions"].items():
        alert = None
        if t in px:
            df = add_signals(add_indicators(px[t]))
            r = df.iloc[-1]
            v["last"] = float(r["Close"])
            v["high"] = max(v["high"], v["last"])
            v["stop"] = round(max(v["stop"], v["high"] - C.ATR_TRAIL_MULT * float(r["ATR"])), 2)
            risk = v.get("risk") or C.ATR_STOP_MULT * float(r["ATR"])
            if r["Low"] <= v["stop"]:
                alert = ("sell", f"ชน Stop {v['stop']} → ควรขาย")
            elif r["exit_trend"]:
                alert = ("sell", "หลุดเส้น 200 วัน → ควรขาย")
            elif v["last"] >= v["entry"] + C.TARGET_R * risk:
                alert = ("target", f"ถึงเป้า {C.TARGET_R:g}R → ขายครึ่งหนึ่ง ที่เหลือถือตาม trailing stop")
        rate = fx(t) if t in px else v.get("fx", 1)
        value = v["shares"] * v["last"] * rate
        total += value
        row = {"ticker": t, "shares": v["shares"], "entry": v["entry"], "last": v["last"],
               "stop": v["stop"], "date": v["date"], "value": round(value, 0),
               "chg_pct": round((v["last"] / v["entry"] - 1) * 100, 2),
               "pnl": round(v["shares"] * (v["last"] * rate - v["entry"] * v.get("fx", 1)), 0),
               "alert": alert}
        rows.append(row)
        if alert:
            alerts.append(f"{t.replace('.BK', '')}: {alert[1]}")
    if update:
        with _LOCK:
            cur = load()
            for t, v in p["positions"].items():
                if t in cur["positions"]:
                    cur["positions"][t].update(last=v["last"], high=v["high"], stop=v["stop"])
            save(cur)
    return {"cash": round(p["cash"], 0), "total": round(total, 0), "start": p["start_capital"],
            "gain_pct": round((total / p["start_capital"] - 1) * 100, 2),
            "positions": rows, "alerts": alerts, "history": p["history"][-50:][::-1]}


def print_status(s):
    print(f"\n{'หุ้น':<10}{'จำนวน':>8}{'ทุน':>10}{'ล่าสุด':>10}{'Stop':>10}{'กำไร%':>9}")
    for r in s["positions"]:
        print(f"{r['ticker']:<10}{r['shares']:>8,}{r['entry']:>10.2f}{r['last']:>10.2f}"
              f"{r['stop']:>10.2f}{r['chg_pct']:>+9.1f}")
    print(f"\nเงินสด {s['cash']:,.0f} | มูลค่าพอร์ต {s['total']:,.0f} | ผลตอบแทน {s['gain_pct']:+.2f}%")
    for a in s["alerts"]:
        print("⚠", a)


def reset(capital=None):
    capital = float(capital or C.CAPITAL)
    with _LOCK:
        save({"cash": capital, "start_capital": capital, "positions": {}, "history": []})
    return {"msg": f"เริ่มพอร์ตจำลองใหม่ เงินทุน {capital:,.0f}"}
