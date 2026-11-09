"""สร้างเว็บแอปแบบไฟล์นิ่ง (static) ไว้ในโฟลเดอร์ site/ สำหรับขึ้น GitHub Pages

    python build_site.py              # สร้างทั้งหุ้นไทยและอเมริกา
    python build_site.py --list set   # เฉพาะหุ้นไทย (ข้อมูลตลาดอื่นใช้ของเดิมใน site/)

ข้อมูลทุกอย่างคำนวณล่วงหน้า หน้าเว็บจึงเปิดได้ทันทีโดยไม่ต้องมีเซิร์ฟเวอร์
"""
import argparse
import json
import os
import shutil
import time
from datetime import datetime

import config as C
import service as S
from paths import BASE, WEB

SITE = os.path.join(BASE, "site")
DATA = os.path.join(SITE, "data")
STATIC_FILES = ["app.js", "static.js","style.css", "manifest.webmanifest", "icon-192.png", "icon-512.png",
                "apple-touch-icon.png"]


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(S.clean(obj), f, ensure_ascii=False, separators=(",", ":"))


def build_market(lst, years=10):
    from data import usd_thb
    from scanner import bench_for, prepare

    t0 = time.time()
    scan = S.scan_data(lst)
    dump(os.path.join(DATA, f"scan_{lst}.json"), scan)
    print(f"[{lst}] สแกน {len(scan['rows'])} หุ้น ({time.time() - t0:.0f} วินาที)")

    # ราคา 10 ปี ใช้ทั้ง backtest ทั้งพอร์ตและรายตัว
    tickers = C.WATCHLISTS[lst]
    long_frames, _ = prepare(tickers, period=f"{years}y")
    frames, _ = prepare(tickers)                   # 3 ปี (แคชเดียวกับตอนสแกน)
    regime = scan["regimes"].get(bench_for(tickers[0]))
    n = 0
    for row in scan["rows"]:
        t = row["symbol"]
        # หน้ารายตัวเฉพาะหุ้นที่มีการซื้อขายพอสมควร (≥ 1 ล้านบาท/วัน) หรือมีสถานะน่าสนใจ
        if t not in frames or (row["value20_m"] < 1 and row["status"] == "หลีกเลี่ยง"):
            continue
        d = S.stock_detail(t, row, frames[t], regime, long_frames.get(t))
        dump(os.path.join(DATA, "stocks", f"s_{t}.json"), d)
        n += 1
    print(f"[{lst}] หน้าหุ้นรายตัว {n} ไฟล์ ({time.time() - t0:.0f} วินาที)")

    dump(os.path.join(DATA, f"backtest_{lst}_{years}.json"), S.backtest_json(lst, years))
    print(f"[{lst}] backtest เสร็จ ({time.time() - t0:.0f} วินาที)")
    return usd_thb()


def copy_static():
    os.makedirs(SITE, exist_ok=True)
    for f in STATIC_FILES:
        shutil.copy2(os.path.join(WEB, f), os.path.join(SITE, f))
    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace("<!--STATIC-->", '<script src="static.js"></script>', 1)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    open(os.path.join(SITE, ".nojekyll"), "w").close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", choices=["set", "us", "all"], default="set")
    ap.add_argument("--no-news", action="store_true")
    args = ap.parse_args()
    copy_static()
    lists = ["set", "us"] if args.list == "all" else [args.list]
    fx = None
    for lst in lists:
        fx = build_market(lst)
    if not args.no_news:
        import news
        news.main()
    meta_path = os.path.join(DATA, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    meta.update({"time": datetime.now().isoformat(timespec="minutes"), "fx_usd_thb": fx,
                 "defaults": {k: getattr(C, k) for k in C.SETTING_KEYS},
                 "lists": {"set": C.WATCHLISTS["set"], "us": []}, "names": C.TH_NAMES,
                 "stock_pages": sorted(f[2:-5] for f in os.listdir(os.path.join(DATA, "stocks"))
                                       if f.startswith("s_") and f.endswith(".BK.json")),
                 "lot_th": C.LOT_SIZE_TH, "stop_mult": C.ATR_STOP_MULT,
                 "trail_mult": C.ATR_TRAIL_MULT, "target_r": C.TARGET_R,
                 "cost": C.COMMISSION + C.SLIPPAGE,
                 "bot": os.environ.get("TELEGRAM_BOT_USERNAME", "")})
    for lst in lists:
        meta[f"updated_{lst}"] = meta["time"]
    dump(meta_path, meta)
    print("เสร็จ:", SITE)


if __name__ == "__main__":
    main()
