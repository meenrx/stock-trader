"""ชั้นบริการที่ทั้งเว็บแอปและคำสั่งบรรทัดใช้ร่วมกัน: สแกน, วิเคราะห์รายตัว, backtest, งานเบื้องหลัง"""
import json
import math
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import numpy as np
import pandas as pd

import config as C
from paths import DATA


# ------------------------------------------------------------ แปลงเป็น JSON ได้
def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return o.isoformat()[:10] if isinstance(o, (pd.Timestamp, date)) else o.isoformat()
    return o


# ------------------------------------------------------------ งานหลัก
def scan_data(lst="set", refresh=False):
    from scanner import scan
    regimes, rows, *_ = scan(C.WATCHLISTS[lst], use_fund=True, refresh=refresh, capital=C.CAPITAL)
    return {"time": datetime.now().isoformat(timespec="minutes"), "list": lst,
            "capital": C.CAPITAL, "regimes": regimes, "rows": rows}


def stock_detail(t, row, df, regime=None, bt_frame=None):
    """ข้อมูลหน้าหุ้นรายตัว: กราฟ, อินดิเคเตอร์, ผลย้อนหลังของหุ้นตัวนั้น"""
    from backtest import run_backtest
    last = df.iloc[-1]
    tail = df.tail(250)
    chart = {"d": [i.strftime("%Y-%m-%d") for i in tail.index],
             **{k: [round(float(x), 4) if pd.notna(x) else None for x in tail[col]]
                for k, col in (("c", "Close"), ("ema20", "EMA20"), ("sma50", "SMA50"),
                               ("sma200", "SMA200"), ("v", "Volume"), ("rsi", "RSI"))}}
    ind = {k: float(last[k]) for k in ("Close", "Low", "SMA20", "SMA50", "SMA200", "EMA20", "RSI",
                                       "MACD", "MACD_sig", "MACD_hist", "ADX", "ATR", "ATR_pct",
                                       "STO_K", "BB_up", "BB_lo", "VolRatio", "High252", "Low252")}
    ind["exit_trend"] = bool(last["exit_trend"])
    bt = None
    f = bt_frame
    if f is not None and len(f) > 260:
        start = f.index[200]
        _, tr, m = run_backtest({t: f}, start=start, capital=C.CAPITAL, max_pos=1,
                                max_pos_pct=1.0, risk=1.0, use_regime=False)
        m.pop("รายปี%", None)
        m["ซื้อแล้วถือเฉย ๆ%"] = round((f["Close"].iloc[-1] / f["Close"].loc[start] - 1) * 100, 1)
        bt = m
    return {"time": datetime.now().isoformat(timespec="minutes"), "row": row, "chart": chart,
            "capital": C.CAPITAL, "risk": C.RISK_PER_TRADE,
            "ind": ind, "bt": bt, "regime": regime}


def analyze_data(ticker):
    from data import get_prices
    from indicators import add_indicators
    from portfolio import norm
    from scanner import bench_for, scan
    from strategy import add_signals

    t = norm(ticker)
    peers = C.WATCHLISTS["set" if t.endswith(".BK") else "us"]
    universe = peers if t in peers else peers + [t]   # เทียบโมเมนตัมกับหุ้นตลาดเดียวกัน
    regimes, rows, frames, _ = scan(universe, capital=C.CAPITAL)
    row = next((r for r in rows if r["symbol"] == t), None)
    if row is None:
        raise ValueError(f"ไม่พบข้อมูล {t} (ชื่อย่อผิด หรือซื้อขายยังไม่ถึง 1 ปี)")
    px = get_prices([t], "10y")
    bt_frame = add_signals(add_indicators(px[t])) if t in px else None
    return stock_detail(t, row, frames[t], regimes.get(bench_for(t)), bt_frame)


def backtest_data(lst="set", years=10):
    from backtest import run_backtest
    from scanner import bench_for, prepare
    tickers = C.WATCHLISTS[lst]
    frames, bench = prepare(tickers, period=f"{years}y")
    b = bench.get(bench_for(tickers[0]))
    start = b.index[210] if b is not None and len(b) > 210 else None   # รอให้ SMA200 คำนวณได้
    eq, tr, m = run_backtest(frames, b, start=start, capital=C.CAPITAL,
                             max_pos=C.MAX_POSITIONS, max_pos_pct=C.MAX_POSITION_PCT,
                             risk=C.RISK_PER_TRADE)
    return eq, tr, m, b


def backtest_json(lst="set", years=10):
    eq, tr, m, b = backtest_data(lst, years)
    w = eq.resample("W").last().dropna()
    bench = None
    if b is not None:
        bw = b["Close"].reindex(eq.index).ffill().resample("W").last().reindex(w.index).ffill()
        bench = [round(float(x / bw.dropna().iloc[0] * C.CAPITAL), 0) if pd.notna(x) else None
                 for x in bw]
    trades = tr.tail(40).iloc[::-1].to_dict("records") if len(tr) else []
    return {"time": datetime.now().isoformat(timespec="minutes"), "list": lst, "years": years,
            "metrics": m, "eq": {"d": [i.strftime("%Y-%m-%d") for i in w.index],
                                 "v": [round(float(x), 0) for x in w], "b": bench},
            "trades": trades, "n_stocks": len(C.WATCHLISTS[lst])}


# ------------------------------------------------------------ งานเบื้องหลัง (เว็บ)
_pool = ThreadPoolExecutor(max_workers=3)
_jobs = {}
_lock = threading.Lock()
TTL = {"scan": 6 * 3600, "analyze": 15 * 60, "backtest": 24 * 3600}


def _disk(key):
    return os.path.join(DATA, "last_" + key.replace(":", "_").replace("/", "_") + ".json")


def _load_disk(key):
    p = _disk(key)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def job(key, fn, *args, force=False, **kw):
    """คืนสถานะงาน ถ้ายังไม่มี/เก่าเกินไป/สั่ง force จะเริ่มงานใหม่ในเบื้องหลัง"""
    kind = key.split(":")[0]
    with _lock:
        j = _jobs.get(key)
        if j is None:
            saved = _load_disk(key) if kind in ("scan", "backtest") else None
            j = {"state": "done" if saved else "none", "result": saved, "error": None,
                 "finished": os.path.getmtime(_disk(key)) if saved else 0}
            _jobs[key] = j
        stale = time.time() - j.get("finished", 0) > TTL.get(kind, 600)
        if j["state"] == "running" or not (force or j["state"] in ("none", "error") or stale):
            return dict(j)
        j.update(state="running", error=None, started=time.time())

    def work():
        try:
            res = clean(fn(*args, **kw))
            if kind in ("scan", "backtest"):
                with open(_disk(key), "w", encoding="utf-8") as f:
                    json.dump(res, f, ensure_ascii=False)
            j.update(state="done", result=res, finished=time.time())
        except Exception as e:
            traceback.print_exc()
            j.update(state="error", error=str(e), finished=time.time())

    _pool.submit(work)
    return dict(j)


def invalidate(prefix=""):
    """ล้างผลเก่า (เช่น หลังเปลี่ยนเงินทุน)"""
    with _lock:
        for k, j in _jobs.items():
            if k.startswith(prefix) and j["state"] != "running":
                j["finished"] = 0
        for f in os.listdir(DATA):
            if f.startswith("last_" + prefix.replace(":", "_")):
                try:
                    os.utime(os.path.join(DATA, f), (0, 0))
                except OSError:
                    pass
