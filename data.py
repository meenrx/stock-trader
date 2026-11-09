"""ดึงราคาหุ้นและข้อมูลพื้นฐานจาก Yahoo Finance (มีแคชรายวันเพื่อไม่ต้องโหลดซ้ำ)"""
import hashlib
import json
import os
import pickle
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import yfinance as yf

from paths import CACHE


def _cache_path(kind, key):
    h = hashlib.md5(key.encode()).hexdigest()[:10]
    return os.path.join(CACHE, f"{kind}_{date.today():%Y%m%d}_{h}")


def get_prices(tickers, period="3y", refresh=False):
    """คืนค่า dict {ticker: DataFrame(Open,High,Low,Close,Volume)}"""
    tickers = list(dict.fromkeys(tickers))
    path = _cache_path("px", period + ",".join(sorted(tickers))) + ".pkl"
    if not refresh and os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)

    raw = yf.download(tickers, period=period, group_by="ticker", auto_adjust=True,
                      threads=True, progress=False)
    out = {}
    for t in tickers:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if t not in raw.columns.get_level_values(0):
                    continue
                d = raw[t].copy()
            else:
                d = raw.copy()
            d = d[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            d = d[d["Close"] > 0]
            d.index = pd.to_datetime(d.index).tz_localize(None)
            if len(d) >= 60:
                out[t] = d
        except Exception:
            continue
    with open(path, "wb") as f:
        pickle.dump(out, f)
    return out


def usd_thb():
    """อัตราแลกเปลี่ยน USD→THB ล่าสุด (แคชรายวัน) ใช้แปลงเงินทุนบาทเมื่อซื้อหุ้นอเมริกา"""
    path = _cache_path("fx", "USDTHB") + ".json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)["rate"]
    rate = 33.0
    try:
        d = yf.download("THB=X", period="10d", progress=False, auto_adjust=True)["Close"].squeeze().dropna()
        if len(d) and 20 < float(d.iloc[-1]) < 60:
            rate = float(d.iloc[-1])
    except Exception:
        pass
    with open(path, "w") as f:
        json.dump({"rate": rate}, f)
    return rate


FUND_KEYS = ["shortName", "sector", "industry", "marketCap", "trailingPE", "forwardPE",
             "priceToBook", "returnOnEquity", "dividendYield", "debtToEquity",
             "revenueGrowth", "earningsGrowth", "profitMargins", "currentPrice",
             "targetMeanPrice", "recommendationKey", "numberOfAnalystOpinions"]


def _fetch_info(t):
    try:
        info = yf.Ticker(t).info or {}
        return t, {k: info.get(k) for k in FUND_KEYS}
    except Exception:
        return t, {}


def get_fundamentals(tickers, refresh=False):
    """ข้อมูลพื้นฐาน (P/E, ROE, ปันผล ฯลฯ) — แคชไว้วันละครั้ง"""
    path = os.path.join(CACHE, f"fund_{date.today():%Y%m%d}.json")
    cache = {}
    if os.path.exists(path) and not refresh:
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
    missing = [t for t in tickers if t not in cache]
    if missing:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for t, info in ex.map(_fetch_info, missing):
                cache[t] = info
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    return {t: cache.get(t, {}) for t in tickers}
