"""ทดสอบกลยุทธ์ย้อนหลังแบบพอร์ตจริง (หลายหุ้นพร้อมกัน, คิดค่าคอม, ซื้อขายราคาเปิดวันถัดไป)"""
import numpy as np
import pandas as pd

import config as C


def run_backtest(frames, bench=None, start=None, capital=C.CAPITAL,
                 max_pos=C.MAX_POSITIONS, max_pos_pct=C.MAX_POSITION_PCT,
                 risk=C.RISK_PER_TRADE, use_regime=True):
    tick = list(frames)
    idx = sorted(set().union(*[f.index for f in frames.values()]))
    idx = pd.DatetimeIndex(idx)
    if start is not None:
        idx = idx[idx >= pd.Timestamp(start)]

    def panel(col, ffill=False):
        p = pd.DataFrame({t: frames[t][col] for t in tick}).reindex(idx)
        return p.ffill() if ffill else p

    O, L, Cl = panel("Open"), panel("Low"), panel("Close")
    Cm = panel("Close", ffill=True)
    ATR = panel("ATR")
    ENT = panel("entry").fillna(False).astype(bool)
    EXT = panel("exit_trend").fillna(False).astype(bool)
    RNK = panel("ROC126")
    if use_regime and bench is not None:
        reg = (bench["Close"] > bench["SMA200"]).reindex(idx).ffill().fillna(True)
    else:
        reg = pd.Series(True, index=idx)

    cost = C.COMMISSION + C.SLIPPAGE
    cash, pos, trades, eq_curve = float(capital), {}, [], []
    pend_buy, pend_sell = [], set()
    lot = {t: (C.LOT_SIZE_TH if t.endswith(".BK") else 1) for t in tick}

    def close(t, price, d, why):
        nonlocal cash
        p = pos.pop(t)
        cash += p["sh"] * price * (1 - cost)
        pnl = p["sh"] * (price * (1 - cost) - p["px"] * (1 + cost))
        trades.append({"ticker": t, "entry_date": p["d"].date(), "exit_date": d.date(),
                       "entry": round(p["px"], 2), "exit": round(price, 2), "shares": p["sh"],
                       "pnl": round(pnl, 0), "ret_pct": round((price / p["px"] - 1) * 100, 2),
                       "R": round((price - p["px"]) / p["r"], 2), "days": (d - p["d"]).days,
                       "reason": why})

    for d in idx:
        # 1) ขายตามสัญญาณเมื่อวาน ที่ราคาเปิด
        for t in list(pend_sell):
            if t in pos and not np.isnan(O.at[d, t]):
                close(t, O.at[d, t], d, "หลุด SMA200")
                pend_sell.discard(t)
        # 2) ซื้อตามสัญญาณเมื่อวาน ที่ราคาเปิด
        eq_prev = eq_curve[-1] if eq_curve else capital
        for t, atr in pend_buy:
            if len(pos) >= max_pos or t in pos:
                continue
            o = O.at[d, t]
            if np.isnan(o) or np.isnan(atr) or atr <= 0:
                continue
            r_ps = C.ATR_STOP_MULT * atr
            sh = min(eq_prev * risk / r_ps, eq_prev * max_pos_pct / o, cash / (o * (1 + cost)))
            sh = int(sh // lot[t] * lot[t])
            if sh <= 0:
                continue
            cash -= sh * o * (1 + cost)
            pos[t] = {"sh": sh, "px": o, "stop": o - r_ps, "hi": o, "d": d, "r": r_ps}
        pend_buy = []
        # 3) ชน Stop ระหว่างวัน (ถ้าเปิดกระโดดต่ำกว่า stop ขายที่ราคาเปิด)
        for t in list(pos):
            lo = L.at[d, t]
            if not np.isnan(lo) and lo <= pos[t]["stop"]:
                close(t, min(O.at[d, t], pos[t]["stop"]), d, "ชน Stop")
        # 4) สิ้นวัน: เลื่อน trailing stop, หาสัญญาณขาย/ซื้อ
        for t, p in pos.items():
            c = Cl.at[d, t]
            if np.isnan(c):
                continue
            p["hi"] = max(p["hi"], c)
            p["stop"] = max(p["stop"], p["hi"] - C.ATR_TRAIL_MULT * ATR.at[d, t])
            if EXT.at[d, t]:
                pend_sell.add(t)
        free = max_pos - len(pos) + len(pend_sell)
        if reg.at[d] and free > 0:
            cands = [t for t in tick if ENT.at[d, t] and t not in pos]
            cands.sort(key=lambda t: -(RNK.at[d, t] if not np.isnan(RNK.at[d, t]) else -9))
            pend_buy = [(t, ATR.at[d, t]) for t in cands[:free]]
        # 5) มูลค่าพอร์ต
        eq_curve.append(cash + sum(p["sh"] * Cm.at[d, t] for t, p in pos.items()))

    for t in list(pos):   # ปิดสถานะที่ค้างอยู่วันสุดท้าย (เพื่อคิดสถิติ)
        close(t, Cm.iloc[-1][t], idx[-1], "ยังถืออยู่ (ปิดสมมติ)")

    eq = pd.Series(eq_curve, index=idx)
    tr = pd.DataFrame(trades)
    return eq, tr, metrics(eq, tr, bench, capital)


def metrics(eq, tr, bench=None, capital=C.CAPITAL):
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    ret = eq.pct_change().dropna()
    dd = eq / eq.cummax() - 1
    m = {
        "เริ่ม": str(eq.index[0].date()), "สิ้นสุด": str(eq.index[-1].date()),
        "เงินต้น": capital, "มูลค่าสุดท้าย": round(eq.iloc[-1], 0),
        "ผลตอบแทนรวม%": round((eq.iloc[-1] / capital - 1) * 100, 1),
        "ผลตอบแทนต่อปี(CAGR)%": round(((eq.iloc[-1] / capital) ** (1 / years) - 1) * 100, 1),
        "ขาดทุนสูงสุดจากจุดสูงสุด(MaxDD)%": round(dd.min() * 100, 1),
        "Sharpe": round(ret.mean() / ret.std() * np.sqrt(252), 2) if ret.std() > 0 else 0,
    }
    if len(tr):
        win = tr[tr.pnl > 0]
        loss = tr[tr.pnl <= 0]
        m.update({
            "จำนวนเทรด": len(tr),
            "อัตราชนะ%": round(len(win) / len(tr) * 100, 1),
            "กำไรเฉลี่ยไม้ชนะ%": round(win.ret_pct.mean(), 2) if len(win) else 0,
            "ขาดทุนเฉลี่ยไม้แพ้%": round(loss.ret_pct.mean(), 2) if len(loss) else 0,
            "Profit Factor": round(win.pnl.sum() / -loss.pnl.sum(), 2) if loss.pnl.sum() < 0 else None,
            "ถือเฉลี่ย(วัน)": round(tr.days.mean(), 1),
            "R เฉลี่ยต่อไม้": round(tr.R.mean(), 2),
        })
    if bench is not None:
        b = bench["Close"].reindex(eq.index).ffill().dropna()
        if len(b) > 1:
            m["ดัชนีอ้างอิง(ซื้อถือ)%"] = round((b.iloc[-1] / b.iloc[0] - 1) * 100, 1)
            bdd = b / b.cummax() - 1
            m["ดัชนีอ้างอิง MaxDD%"] = round(bdd.min() * 100, 1)
    yearly = eq.resample("YE").last()
    first = pd.Series([capital], index=[eq.index[0] - pd.Timedelta(days=1)])
    yr = pd.concat([first, yearly]).pct_change().dropna()
    m["รายปี%"] = {str(k.year): round(v * 100, 1) for k, v in yr.items()}
    return m
