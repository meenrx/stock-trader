"""สแกนหุ้นทั้งรายชื่อ ให้คะแนน จัดอันดับ และบอกสถานะ ซื้อ / รอจังหวะ / หลีกเลี่ยง"""
import pandas as pd

import config as C
from data import get_fundamentals, get_prices, usd_thb
from indicators import add_indicators
from strategy import (add_signals, fundamental_score, market_regime, signal_names,
                      technical_score, trade_plan)

MIN_VALUE_TH = 5e6     # มูลค่าซื้อขายเฉลี่ยขั้นต่ำ 5 ล้านบาท/วัน (ซื้อขายได้จริงโดยราคาไม่หลุดมาก)
MIN_VALUE_US = 50e6


def bench_for(t):
    return C.BENCHMARK if t.endswith(".BK") else "^GSPC"


def prepare(tickers, period="3y", refresh=False):
    benches = sorted({bench_for(t) for t in tickers})
    px = get_prices(list(tickers) + benches, period, refresh)
    frames = {t: add_signals(add_indicators(px[t])) for t in tickers if t in px and len(px[t]) >= 260}
    bench = {b: add_indicators(px[b]) for b in benches if b in px}
    return frames, bench


def rs_ranks(frames):
    """อันดับความแข็งแกร่ง (Relative Strength) 0-1 เทียบภายในตลาดเดียวกัน"""
    raw = {}
    for t, df in frames.items():
        r = df.iloc[-1]
        vals = [r.get("ROC126"), r.get("MOM12_1"), r.get("ROC63")]
        if any(pd.isna(v) for v in vals):
            continue
        raw[t] = 0.5 * vals[0] + 0.3 * vals[1] + 0.2 * vals[2]
    out = {}
    for mkt in (True, False):
        s = pd.Series({t: v for t, v in raw.items() if t.endswith(".BK") == mkt}, dtype=float)
        if len(s):
            out.update(s.rank(pct=True).to_dict())
    return out


def scan(tickers, use_fund=True, refresh=False, capital=C.CAPITAL):
    frames, bench = prepare(tickers, refresh=refresh)
    regimes = {b: market_regime(df) for b, df in bench.items()}
    ranks = rs_ranks(frames)
    liquid_set = [t for t, df in frames.items()
                  if df["Value20"].iloc[-1] >= (MIN_VALUE_TH if t.endswith(".BK") else MIN_VALUE_US)]
    funds = get_fundamentals(liquid_set, refresh) if use_fund else {}   # ดึงงบเฉพาะหุ้นที่ซื้อขายคล่อง

    fx_us = usd_thb() if any(not t.endswith(".BK") for t in frames) else 1.0
    rows = []
    for t, df in frames.items():
        is_th = t.endswith(".BK")
        r = df.iloc[-1]
        liquid = r["Value20"] >= (MIN_VALUE_TH if is_th else MIN_VALUE_US)
        reg = regimes.get(bench_for(t), {"ok": True, "strong": True})
        tech, tdet = technical_score(df, ranks.get(t))
        info = funds.get(t, {})
        fund, fdet = fundamental_score(info) if use_fund and liquid else (12.5, {"note": "สภาพคล่องต่ำ — ไม่ได้ดึงงบการเงิน"} if use_fund else {})
        score = round(tech + fund, 1)
        sigs = signal_names(df)
        size_cap = capital if reg.get("strong") else capital * 0.5
        plan = trade_plan(df, size_cap, is_th, 1.0 if is_th else fx_us)

        trend = bool(r["trend_ok"])
        if sigs and trend and score >= C.BUY_SCORE and liquid and reg["ok"]:
            status = "ซื้อ"
            how = f"ซื้อได้ที่ราคาปัจจุบัน ~{plan['entry']} ตั้ง Stop {plan['stop']} เป้าแรก {plan['target']}"
        elif trend and score >= C.WATCH_SCORE and liquid:
            status = "รอจังหวะ"
            lo, hi = plan["pullback_zone"]
            how = f"รอย่อเข้าโซน {lo}–{hi} แล้วเด้ง หรือรอเบรก {plan['breakout_level']} พร้อมวอลุ่ม"
            if sigs and not reg["ok"]:
                how = "มีสัญญาณแต่ตลาดรวมเป็นขาลง — รอตลาดกลับเหนือเส้น 200 วันก่อน"
        else:
            status = "หลีกเลี่ยง"
            why = []
            if not trend:
                why.append("ไม่อยู่ในขาขึ้น")
            if not liquid:
                why.append("สภาพคล่องต่ำ")
            if score < C.WATCH_SCORE:
                why.append("คะแนนรวมต่ำ")
            how = ", ".join(why) or "-"

        if plan["shares"] == 0 and status != "หลีกเลี่ยง":
            how += " (ทุนตามเกณฑ์ความเสี่ยงไม่พอซื้อ 1 lot — เพิ่มทุนหรือข้าม)"
        tgt = info.get("targetMeanPrice")
        upside = round((tgt / r["Close"] - 1) * 100, 1) if tgt else None
        rows.append({
            "ticker": t.replace(".BK", ""), "symbol": t, "name": (info.get("shortName") or "").split("_", 1)[-1].strip() or C.TH_NAMES.get(t, ""),
            "sector": info.get("sector") or "", "status": status, "score": score,
            "tech": tech, "fund": fund, "signals": sigs, "how": how,
            "close": round(float(r["Close"]), 2), "rsi": round(float(r["RSI"]), 1),
            "adx": round(float(r["ADX"]), 1), "roc126": round(float(r["ROC126"]) * 100, 1),
            "from_high": round((r["Close"] / r["High252"] - 1) * 100, 1),
            "value20_m": round(float(r["Value20"]) / 1e6, 1),
            "analyst_upside": upside, "analyst_rec": info.get("recommendationKey"),
            "tech_detail": tdet, "fund_detail": fdet, "plan": plan,
            "liquid": bool(liquid), "spark": [round(float(x), 2) for x in df["Close"].tail(60)],
        })
    order = {"ซื้อ": 0, "รอจังหวะ": 1, "หลีกเลี่ยง": 2}
    rows.sort(key=lambda x: (order[x["status"]], -x["score"]))
    return regimes, rows, frames, bench
