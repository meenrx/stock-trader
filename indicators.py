"""อินดิเคเตอร์ทางเทคนิค: SMA, EMA, RSI, MACD, ATR, Bollinger, ADX, Stochastic, OBV ฯลฯ"""
import numpy as np
import pandas as pd


def wilder(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()


def add_indicators(df):
    df = df.copy()
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]

    # เส้นค่าเฉลี่ย
    for n in (20, 50, 200):
        df[f"SMA{n}"] = c.rolling(n).mean()
    df["EMA20"] = c.ewm(span=20, adjust=False).mean()
    df["SMA200_slope"] = df["SMA200"].pct_change(20)  # ความชันของเส้น 200 วัน (1 เดือน)

    # RSI 14
    d = c.diff()
    rs = wilder(d.clip(lower=0), 14) / wilder(-d.clip(upper=0), 14)
    df["RSI"] = 100 - 100 / (1 + rs)

    # MACD 12-26-9
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    df["MACD"] = macd
    df["MACD_sig"] = macd.ewm(span=9, adjust=False).mean()
    df["MACD_hist"] = macd - df["MACD_sig"]

    # ATR 14
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["ATR"] = wilder(tr, 14)
    df["ATR_pct"] = df["ATR"] / c

    # Bollinger 20,2
    sd = c.rolling(20).std()
    df["BB_up"] = df["SMA20"] + 2 * sd
    df["BB_lo"] = df["SMA20"] - 2 * sd
    df["BB_pctb"] = (c - df["BB_lo"]) / (df["BB_up"] - df["BB_lo"])

    # ADX 14 (ความแรงของแนวโน้ม)
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    atr = wilder(tr, 14)
    pdi = 100 * wilder(pdm, 14) / atr
    mdi = 100 * wilder(mdm, 14) / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    df["ADX"] = wilder(dx, 14)
    df["PDI"], df["MDI"] = pdi, mdi

    # Stochastic 14,3
    ll14, hh14 = l.rolling(14).min(), h.rolling(14).max()
    df["STO_K"] = 100 * (c - ll14) / (hh14 - ll14).replace(0, np.nan)
    df["STO_D"] = df["STO_K"].rolling(3).mean()

    # วอลุ่ม / OBV
    df["VolMA20"] = v.rolling(20).mean()
    df["VolRatio"] = v / df["VolMA20"]
    df["Value20"] = (c * v).rolling(20).mean()          # มูลค่าซื้อขายเฉลี่ย 20 วัน
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    df["OBV_slope"] = (obv - obv.shift(20)) / (v.rolling(20).mean() * 20).replace(0, np.nan)

    # กรอบราคา / โมเมนตัม
    df["HH55"] = h.rolling(55).max().shift(1)    # ไฮ 55 วันก่อนหน้า (จุดเบรกเอาต์)
    df["LL20"] = l.rolling(20).min().shift(1)
    df["High252"] = h.rolling(252, min_periods=120).max()
    df["Low252"] = l.rolling(252, min_periods=120).min()
    df["ROC63"] = c.pct_change(63)
    df["ROC126"] = c.pct_change(126)
    df["MOM12_1"] = c.shift(21) / c.shift(252) - 1    # โมเมนตัม 12 เดือนตัดเดือนล่าสุด
    df["Vol60"] = c.pct_change().rolling(60).std() * np.sqrt(252)
    return df
