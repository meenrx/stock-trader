"""กลยุทธ์: สัญญาณซื้อ/ขาย, การให้คะแนนหุ้น และแผนเทรด (จุดเข้า/ตัดขาดทุน/เป้า/จำนวนหุ้น)

หลักการที่ใช้ (รวมแนวคิดที่มีหลักฐานรองรับมากที่สุด):
  1. Trend following  — ซื้อเฉพาะหุ้นที่อยู่เหนือเส้น 200 วัน และ SMA50 > SMA200 (Stage 2)
  2. Momentum          — หุ้นที่แข็งแรงกว่าตลาดใน 3-12 เดือน มักไปต่อ
  3. Buy the pullback  — เข้าตอนย่อตัวในขาขึ้น (RSI ลงไปต่ำแล้วกลับขึ้นเหนือ EMA20)
  4. Breakout          — เข้าตอนทะลุไฮ 55 วันพร้อมวอลุ่ม (Donchian / Turtle)
  5. Value & Quality   — P/E, P/BV, ROE, ปันผล, หนี้, การเติบโต
  6. Risk management   — ตัดขาดทุนด้วย ATR, เสี่ยงไม่เกิน 1% ต่อไม้, กรองสภาพตลาด
"""
import numpy as np
import pandas as pd

import config as C


# ---------------------------------------------------------------- สัญญาณ
def add_signals(df):
    df = df.copy()
    c = df["Close"]
    trend = (c > df["SMA200"]) & (df["SMA50"] > df["SMA200"]) & (df["SMA200_slope"] > 0)
    not_hot = df["RSI"] < 75

    pullback = (trend & not_hot
                & (df["RSI"].rolling(6).min() < 45)
                & (c > df["EMA20"]) & (c.shift(1) <= df["EMA20"].shift(1)))
    breakout = (trend & not_hot & (c > df["HH55"])
                & (df["VolRatio"] > 1.5) & (df["ADX"] > 20))
    macd_x = (trend & not_hot & (df["MACD"] > df["MACD_sig"])
              & (df["MACD"].shift(1) <= df["MACD_sig"].shift(1)) & (df["RSI"] < 65))

    df["trend_ok"] = trend
    df["sig_pullback"] = pullback
    df["sig_breakout"] = breakout
    df["sig_macd"] = macd_x
    df["entry"] = pullback | breakout | macd_x
    df["exit_trend"] = c < df["SMA200"]   # หลุดเส้น 200 วัน = ขาขึ้นจบ
    return df


# ---------------------------------------------------------------- คะแนนพื้นฐาน
def _num(x):
    try:
        x = float(x)
        return None if np.isnan(x) else x
    except (TypeError, ValueError):
        return None


def fundamental_score(info):
    """คืน (คะแนน 0-25, รายละเอียด) — ถ้าข้อมูลไม่ครบจะเฉลี่ยจากเท่าที่มี"""
    if not info:
        return 12.5, {"note": "ไม่มีข้อมูลพื้นฐาน (ให้คะแนนกลาง)"}
    fin = (info.get("sector") or "") == "Financial Services"
    got, full, d = 0.0, 0.0, {}

    pe = _num(info.get("trailingPE"))
    if pe is not None:
        full += 5
        got += 5 if 0 < pe <= 15 else 3 if 0 < pe <= 25 else 1 if 0 < pe <= 40 else 0
        d["P/E"] = round(pe, 1)
    pb = _num(info.get("priceToBook"))
    if pb is not None:
        full += 3
        got += 3 if 0 < pb <= 1.5 else 2 if 0 < pb <= 3 else 0
        d["P/BV"] = round(pb, 2)
    roe = _num(info.get("returnOnEquity"))
    if roe is not None:
        full += 5
        got += 5 if roe >= 0.15 else 3 if roe >= 0.10 else 1 if roe > 0 else 0
        d["ROE%"] = round(roe * 100, 1)
    dy = _num(info.get("dividendYield"))
    if dy is not None:
        dy = dy if dy > 1 else dy * 100   # yfinance บางเวอร์ชันส่งเป็น % บางเวอร์ชันเป็นทศนิยม
        full += 4
        got += 4 if dy >= 4 else 3 if dy >= 2.5 else 1 if dy > 0 else 0
        d["ปันผล%"] = round(dy, 2)
    de = _num(info.get("debtToEquity"))
    if de is not None and not fin:          # ธนาคารหนี้สูงโดยธรรมชาติ ไม่นับ
        full += 3
        got += 3 if de <= 80 else 2 if de <= 150 else 0
        d["D/E"] = round(de / 100, 2)
    rg = _num(info.get("revenueGrowth"))
    if rg is not None:
        full += 3
        got += 3 if rg >= 0.08 else 2 if rg > 0 else 0
        d["โตรายได้%"] = round(rg * 100, 1)
    pm = _num(info.get("profitMargins"))
    if pm is not None:
        full += 2
        got += 2 if pm >= 0.10 else 1 if pm > 0 else 0
        d["อัตรากำไร%"] = round(pm * 100, 1)

    if full == 0:
        return 12.5, {"note": "ไม่มีข้อมูลพื้นฐาน (ให้คะแนนกลาง)"}
    return round(got / full * 25, 1), d


# ---------------------------------------------------------------- คะแนนเทคนิค
def technical_score(df, rs_rank=None):
    """คืน (คะแนน 0-75, รายละเอียด) จากแถวล่าสุด"""
    r = df.iloc[-1]
    c = r["Close"]
    s_trend = 0
    s_trend += 8 if c > r["SMA200"] else 0
    s_trend += 7 if r["SMA50"] > r["SMA200"] else 0
    s_trend += 5 if r["SMA200_slope"] > 0 else 0
    s_trend += 5 if c > r["SMA50"] else 0
    hi = r["High252"]
    s_trend += 5 if hi and c >= 0.85 * hi else 2 if hi and c >= 0.7 * hi else 0   # ใกล้ไฮ 52 สัปดาห์

    s_mom = 0
    if rs_rank is not None:                  # อันดับโมเมนตัมเทียบหุ้นอื่น (0-1)
        s_mom += 12 * rs_rank
    elif r["ROC126"] > 0:
        s_mom += 6
    rsi = r["RSI"]
    s_mom += 6 if 50 <= rsi <= 68 else 3 if 40 <= rsi < 50 or 68 < rsi <= 75 else 0
    s_mom += 4 if r["MACD_hist"] > 0 else 0
    s_mom += 3 if r["ADX"] > 20 and r["PDI"] > r["MDI"] else 0

    s_vol = 0
    s_vol += 6 if r["OBV_slope"] > 0.1 else 3 if r["OBV_slope"] > 0 else 0
    s_vol += 4 if r["VolRatio"] > 1.2 and c > df["Close"].iloc[-2] else 0

    s_risk = 0
    s_risk += 6 if r["ATR_pct"] < 0.025 else 3 if r["ATR_pct"] < 0.04 else 0
    s_risk += 4 if c > r["BB_lo"] and r["BB_pctb"] < 0.95 else 0

    total = s_trend + s_mom + s_vol + s_risk   # เต็ม 30+25+10+10 = 75
    return round(total, 1), {"แนวโน้ม": s_trend, "โมเมนตัม": round(s_mom, 1),
                             "วอลุ่ม": s_vol, "ความผันผวน": s_risk}


# ---------------------------------------------------------------- แผนเทรด
def tick_size(p):
    """ช่วงราคา (tick) ของตลาดหลักทรัพย์ฯ — ราคาที่ส่งคำสั่งใน Streaming ได้จริง"""
    for lim, t in ((2, 0.01), (5, 0.02), (10, 0.05), (25, 0.10), (100, 0.25), (200, 0.50), (400, 1.00)):
        if p < lim:
            return t
    return 2.00


def to_tick(p, mode="nearest"):
    """ปัดราคาให้ตรงช่วงราคา: down = ปัดลง (Stop), up = ปัดขึ้น, nearest = ใกล้สุด"""
    import math
    if p is None or p != p or p <= 0:
        return p
    t = tick_size(p)
    n = p / t
    n = math.floor(n + 1e-9) if mode == "down" else math.ceil(n - 1e-9) if mode == "up" else round(n)
    v = round(n * t, 2)
    if tick_size(v) != t:            # ข้ามช่วงราคาแล้ว ปัดใหม่ด้วย tick ของช่วงใหม่
        t2 = tick_size(v)
        v = round(round(v / t2) * t2, 2)
    return v


def trade_plan(df, capital=C.CAPITAL, is_th=True, fx=1.0):
    """capital เป็นเงินบาท; fx = บาทต่อ 1 หน่วยสกุลเงินของหุ้น (หุ้นไทย = 1)"""
    capital = capital / fx
    r = df.iloc[-1]
    entry = float(r["Close"])
    atr = float(r["ATR"])
    stop = entry - C.ATR_STOP_MULT * atr
    target = entry + C.TARGET_R * (entry - stop)
    if is_th:                                   # ราคาที่ส่งคำสั่งใน Streaming ได้จริง
        entry, stop, target = to_tick(entry), to_tick(stop, "down"), to_tick(target, "down")
    risk_ps = entry - stop
    shares = min(capital * C.RISK_PER_TRADE / risk_ps, capital * C.MAX_POSITION_PCT / entry)
    lot = C.LOT_SIZE_TH if is_th else 1
    shares = int(shares // lot * lot)
    return {
        "entry": round(entry, 2), "stop": round(stop, 2), "target": round(target, 2),
        "stop_pct": round(-risk_ps / entry * 100, 1),
        "target_pct": round((target - entry) / entry * 100, 1),
        "shares": shares, "cost": round(shares * entry, 0),
        "max_loss": round(shares * risk_ps * fx, 0), "cost_thb": round(shares * entry * fx, 0),
        "ccy": "฿" if is_th else "$", "fx": round(fx, 3),
        "breakout_level": (to_tick(float(r["HH55"]), "up") if is_th else round(float(r["HH55"]), 2))
        if pd.notna(r["HH55"]) else None,
        "pullback_zone": tuple((to_tick(float(x)) if is_th else round(float(x), 2))
                               for x in sorted((r["EMA20"], r["SMA50"]))),
    }


def signal_names(df, lookback=C.SIGNAL_LOOKBACK):
    tail = df.tail(lookback)
    names = []
    if tail["sig_breakout"].any():
        names.append("เบรกไฮ 55 วัน+วอลุ่ม")
    if tail["sig_pullback"].any():
        names.append("ย่อแล้วเด้งกลับเหนือ EMA20")
    if tail["sig_macd"].any():
        names.append("MACD ตัดขึ้น")
    return names


def market_regime(bench_df):
    """สภาพตลาดรวม: ดัชนีเหนือเส้น 200 วัน = ตลาดขาขึ้น"""
    if bench_df is None or len(bench_df) < 210:
        return {"ok": True, "text": "ไม่ทราบสภาพตลาด"}
    b = bench_df.iloc[-1]
    ok = b["Close"] > b["SMA200"]
    strong = ok and b["SMA50"] > b["SMA200"]
    text = ("ตลาดขาขึ้น — ลงทุนได้เต็มแผน" if strong else
            "ตลาดฟื้นตัว — ลงทุนได้แต่ลดขนาดลงครึ่งหนึ่ง" if ok else
            "ตลาดขาลง — ควรถือเงินสดมาก ลดความเสี่ยง/ขนาดไม้")
    return {"ok": bool(ok), "strong": bool(strong), "text": text,
            "close": round(float(b["Close"]), 2), "sma200": round(float(b["SMA200"]), 2)}
