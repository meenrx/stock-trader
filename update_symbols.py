"""อัปเดตรายชื่อหุ้นไทยทั้งตลาด (SET + mai) จาก Yahoo Finance screener → th_stocks.json

เก็บเฉพาะหุ้นสามัญ/กองทุนอสังหาฯ ที่ซื้อขายใน Streaming ได้ตามปกติ
ตัดออก: DR (เช่น NVDA80), NVDR (-R), ใบสำคัญแสดงสิทธิ (-W), หุ้นต่างด้าว (-F), DW, ETF
"""
import json
import os
import re

import yfinance as yf
from yfinance import EquityQuery

from paths import BASE

OUT = os.path.join(BASE, "th_stocks.json")


def fetch():
    q = EquityQuery("eq", ["region", "th"])
    quotes, off = [], 0
    while True:
        r = yf.screen(q, offset=off, size=250, sortField="intradaymarketcap", sortAsc=False)
        qs = r.get("quotes", [])
        quotes += qs
        if len(qs) < 250:
            break
        off += 250
    return quotes


def keep(x):
    s = x.get("symbol", "")
    name = x.get("shortName") or x.get("longName") or ""
    if not s.endswith(".BK") or x.get("quoteType") != "EQUITY":
        return None
    base = s[:-3]
    if "_DR" in name or "#" in name:
        return None
    if re.match(r"^[A-Z]+\d{2}$", base) and len(base) > 4:          # DR
        return None
    if re.search(r"-(W\d*|F|R|P|Q|T)$", base):                     # warrant / foreign / NVDR / preferred
        return None
    if re.match(r"^[A-Z0-9]+\d{2}[CP]\d{4}[A-Z]$", base):          # DW
        return None
    name = name.split("_", 1)[-1].strip()
    return {"s": base, "n": name, "mcap": x.get("marketCap")}


def main():
    rows = [k for k in (keep(x) for x in fetch()) if k]
    seen, out = set(), []
    for r in rows:
        if r["s"] not in seen:
            seen.add(r["s"])
            out.append(r)
    if len(out) < 500:                       # ผลผิดปกติ — ไม่ทับรายชื่อเดิม
        raise SystemExit(f"ได้รายชื่อแค่ {len(out)} ตัว ผิดปกติ — ใช้รายชื่อเดิม")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    print(f"บันทึก {len(out)} หุ้นที่ {OUT}")


if __name__ == "__main__":
    main()
