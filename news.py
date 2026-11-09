"""รวบรวมข่าวหุ้นไทยจากหลายแหล่ง → site/data/news.json

แหล่งข่าว: RSS ของสำนักข่าวหุ้น/เศรษฐกิจโดยตรง + Google News (รวมข่าวจากเว็บอื่นอีกมาก)
ทุกข่าวจะถูกจับคู่กับชื่อย่อหุ้นที่พูดถึง และประเมินโทนข่าวคร่าว ๆ จากคำในหัวข่าว

    python news.py                 # ดึงข่าวทั่วไป + ข่าวรายหุ้นของหุ้นที่น่าสนใจ
    python news.py --quick         # ดึงเร็ว (ใช้ระหว่างวัน)
"""
import argparse
import email.utils
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import config as C
from paths import BASE

OUT = os.path.join(BASE, "site", "data", "news.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; stocktrader-news/1.0)"}
BKK = timezone(timedelta(hours=7))
KEEP_DAYS = 7
MAX_ITEMS = 2500

# ---------------------------------------------------------------- แหล่งข่าว
WP_FEEDS = {   # เว็บ WordPress — ดึงได้หลายหน้า
    "ข่าวหุ้น": "https://www.kaohoon.com/feed",
    "ทันหุ้น": "https://www.thunhoon.com/feed",
    "HoonSmart": "https://www.hoonsmart.com/feed",
    "มิติหุ้น": "https://www.mitihoon.com/feed",
    "InfoQuest": "https://www.infoquest.co.th/feed",
    "Brand Inside": "https://brandinside.asia/feed",
}
FEEDS = {
    "ประชาชาติ": "https://www.prachachat.net/finance/feed",
    "Investing.com": "https://th.investing.com/rss/news_25.rss",
}
GNEWS_QUERIES = [
    "หุ้น when:1d", "ตลาดหุ้นไทย when:1d", "SET index when:2d", "หุ้นไทย วันนี้ when:1d",
    "หุ้นเด่น when:2d", "โบรกแนะนำ หุ้น when:2d", "กลยุทธ์ลงทุน หุ้น when:2d",
    "กำไรสุทธิ ไตรมาส บริษัท when:3d", "ปันผล หุ้น when:3d", "หุ้น IPO when:7d",
    "ก.ล.ต. หุ้น when:3d", "ตลาดหลักทรัพย์ when:2d", "ฟันด์โฟลว์ ต่างชาติ หุ้นไทย when:3d",
    "site:thunhoon.com when:1d", "site:thansettakij.com หุ้น when:2d",
    "site:bangkokbiznews.com หุ้น when:2d", "site:efinancethai.com when:2d",
    "site:posttoday.com หุ้น when:2d", "site:kaohoon.com when:1d", "site:moneyandbanking.co.th หุ้น when:3d",
    "site:stockradars.co when:3d", "site:longtunman.com when:7d",
]

POS = ["กำไรเพิ่ม", "กำไรโต", "กำไรพุ่ง", "กำไรสุทธิเพิ่ม", "โตต่อเนื่อง", "พุ่ง", "ทะยาน", "บวก", "ฟื้นตัว",
       "นิวไฮ", "ปรับเป้าขึ้น", "เพิ่มเป้า", "แนะนำซื้อ", "น่าซื้อ", "เติบโต", "สูงสุดเป็นประวัติการณ์", "ทุบสถิติ",
       "ชนะประมูล", "ได้งาน", "เซ็นสัญญา", "ปันผลสูง", "จ่ายปันผล", "แรงซื้อ", "Outperform", "ซื้อคืนหุ้น",
       "ขยายกิจการ", "รายได้เพิ่ม", "ยอดขายเพิ่ม", "พลิกกำไร", "Upside"]
NEG = ["ขาดทุน", "กำไรลด", "กำไรหด", "กำไรวูบ", "ร่วง", "ดิ่ง", "ทรุด", "ติดลบ", "หลุดแนวรับ", "เทขาย", "แรงขาย",
       "ลดเป้า", "ปรับเป้าลง", "ผิดนัด", "คดี", "ฟ้อง", "ขึ้นเครื่องหมาย", "ทุจริต", "ล้มละลาย", "ฟื้นฟูกิจการ",
       "Underperform", "หดตัว", "ต่ำสุดในรอบ", "ขายทิ้ง", "ถูกสั่ง", "ปรับลด", "รายได้ลด", "ยอดขายลด", "ชะลอตัว",
       "Turnaround ไม่ทัน", "Force Sell", "กล่าวโทษ"]
# ชื่อย่อที่เป็นคำทั่วไป จับคู่ผิดง่าย — ต้องมีคำว่า "หุ้น" นำหน้าถึงจะนับ
AMBIGUOUS = {"ALL", "ONE", "TOP", "BIG", "NEW", "SUN", "PRO", "CEO", "GDP", "USD", "THB", "ESG", "IPO", "SET",
             "MAI", "WIN", "NOW", "PLUS", "HOME", "FUND", "CASH", "BANK", "GOLD", "SMART", "POWER", "GREEN",
             "AGE", "AIT", "FN", "GL", "UP", "TV", "IT", "AI", "EV", "OR", "AS", "AP", "M", "S", "K", "J",
             "ACE", "FAST", "LIFE", "PEACE", "TRUE", "BE8", "WAVE", "GLOBAL", "STAR", "BEST", "KEY", "MORE",
             "JAS", "SUPER", "PRIME", "NEX", "SAM", "PEN", "CI", "CH", "CM", "PR", "PG", "SC", "MC", "LH", "TU"}


# ---------------------------------------------------------------- ดึงและแยกข้อมูล
def fetch(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _date(s):
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(BKK)
    except Exception:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(BKK)
        except Exception:
            return datetime.now(BKK)


def parse(raw, default_src):
    """อ่าน RSS — ถ้า XML เสีย (บางเว็บ) ใช้วิธีแยกด้วย regex แทน"""
    items = []
    try:
        root = ET.fromstring(raw)
        for it in root.iter("item"):
            src_el = it.find("source")
            items.append({"title": it.findtext("title"), "link": it.findtext("link"),
                          "date": it.findtext("pubDate"), "desc": it.findtext("description"),
                          "src": src_el.text if src_el is not None and src_el.text else default_src})
    except ET.ParseError:
        txt = raw.decode("utf-8", "replace")
        for block in re.findall(r"<item>(.*?)</item>", txt, re.S):
            g = lambda tag: (re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S) or [None, ""])[1]
            items.append({"title": re.sub(r"<!\[CDATA\[|\]\]>", "", g("title")),
                          "link": re.sub(r"<!\[CDATA\[|\]\]>", "", g("link")).strip(),
                          "date": g("pubDate"), "desc": re.sub(r"<!\[CDATA\[|\]\]>", "", g("description")),
                          "src": default_src})
    out = []
    for i in items:
        title = _clean(i["title"])
        src = _clean(i["src"])
        if default_src == "Google News" and " - " in title:          # "หัวข่าว - ชื่อเว็บ"
            title, _, src2 = title.rpartition(" - ")
            src = src or src2
        if not title or not i["link"]:
            continue
        desc = _clean(i["desc"])
        desc = re.sub(r"\s*(The post .*|\[(…|\.\.\.)\].*)$", "", desc).strip()
        if desc.startswith(title[:30]):
            desc = ""
        out.append({"t": title, "l": i["link"].strip(), "s": src or default_src,
                    "d": _date(i["date"]).isoformat(timespec="minutes"), "x": desc[:240]})
    return out


def gnews_url(q):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "th", "gl": "TH", "ceid": "TH:th"})


def source_jobs(symbols=(), pages=3):
    jobs = []
    for name, url in WP_FEEDS.items():
        for p in range(1, pages + 1):
            jobs.append((name, url + (f"?paged={p}" if p > 1 else ""), None))
    jobs += [(name, url, None) for name, url in FEEDS.items()]
    jobs += [("Google News", gnews_url(q), None) for q in GNEWS_QUERIES]
    for s in symbols:          # ข่าวเจาะรายหุ้น
        jobs.append(("Google News", gnews_url(f'"{s}" หุ้น when:7d'), s))
    return jobs


def run_job(job):
    name, url, sym = job
    try:
        items = parse(fetch(url), name)
        if sym:
            pat = re.compile(rf"(?<![A-Z0-9]){re.escape(sym)}(?![A-Z0-9])")
            items = [i for i in items if pat.search(i["t"] + " " + i["x"])]
            for i in items:
                i["force"] = sym
        return name, items, None
    except Exception as e:
        return name, [], f"{type(e).__name__}: {str(e)[:80]}"


# ---------------------------------------------------------------- จับคู่หุ้น + โทนข่าว
TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9&\-]{0,9})(?![A-Za-z0-9])")


# คำอังกฤษทั่วไปที่บังเอิญเป็นชื่อย่อหุ้น — นับเฉพาะเมื่อเขียนแบบ "บมจ. XXX" หรือ "(XXX)"
STRICT = {"AI", "THE", "IT", "EV", "TV", "UP", "AS", "OR", "ONE", "ALL", "NEW", "TOP", "BIG", "NOW", "WIN",
          "PRO", "SUN", "STAR", "BEST", "KEY", "MORE", "LIFE", "GOLD", "CASH", "HOME", "PLUS", "FUND", "BANK",
          "SMART", "POWER", "GREEN", "GLOBAL", "SUPER", "PRIME", "FAST", "PEACE", "AGE", "ACE", "WAVE", "SET",
          "IPO", "CEO", "GDP", "USD", "THB", "ESG", "MAI", "NEX", "SAM", "PEN"}


def tag_symbols(text, symbols):
    found = []
    for tok in TOKEN.findall(text):
        tok = tok.rstrip("-")
        if tok not in symbols or tok in found:
            continue
        if tok in STRICT:
            if not re.search(rf"(บมจ\.?\s*|\(){re.escape(tok)}(?![A-Za-z0-9])", text):
                continue
        elif tok in AMBIGUOUS or len(tok) <= 2:
            # ยอมรับ: "หุ้น LH", "บมจ. LH" หรือขึ้นต้นหัวข่าวด้วย "LH ตามด้วยภาษาไทย"
            if not (re.search(rf"(หุ้น|บมจ\.?|บริษัท)\s*{re.escape(tok)}(?![A-Za-z0-9])", text)
                    or re.match(rf"\W*{re.escape(tok)}\s+[฀-๿]", text)):
                continue
        found.append(tok)
    return found


def sentiment(text):
    p = sum(text.count(w) for w in POS)
    n = sum(text.count(w) for w in NEG)
    return 1 if p > n else -1 if n > p else 0


def norm_title(t):
    return re.sub(r"[\s\W_]+", "", t.lower())[:80]


def collect(symbols_focus=(), quick=False, previous=None, log=print):
    allsyms = {t.replace(".BK", "") for t in C.WATCHLISTS["set"]}
    jobs = source_jobs(symbols_focus, pages=1 if quick else 3)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(run_job, jobs))
    stats = {}
    fresh = []
    for name, items, err in results:
        st = stats.setdefault(name, {"items": 0, "errors": 0})
        st["items"] += len(items)
        st["errors"] += 1 if err else 0
        fresh += items
    log(f"ดึงข่าว {len(jobs)} แหล่ง ได้ {len(fresh)} รายการ ({time.time() - t0:.0f} วินาที)")

    merged, seen = [], set()
    cutoff = (datetime.now(BKK) - timedelta(days=KEEP_DAYS)).isoformat()
    for it in fresh + (previous or []):
        key = norm_title(it["t"])
        if key in seen or it["d"] < cutoff:
            # ข่าวซ้ำ: เพิ่มชื่อหุ้นที่บังคับจับคู่เข้าไปในข่าวเดิม
            if key in seen and it.get("force"):
                for m in merged:
                    if norm_title(m["t"]) == key and it["force"] not in m["sym"]:
                        m["sym"].append(it["force"])
            continue
        seen.add(key)
        text = it["t"] + " " + it.get("x", "")
        syms = it.get("sym") or tag_symbols(text, allsyms)
        if it.get("force") and it["force"] not in syms:
            syms = [it["force"]] + syms
        merged.append({"id": hashlib.md5(it["l"].encode()).hexdigest()[:10], "t": it["t"], "l": it["l"],
                       "s": it["s"], "d": it["d"], "x": it.get("x", ""), "sym": syms[:8],
                       "sen": it.get("sen", sentiment(it["t"]))})
    merged.sort(key=lambda x: x["d"], reverse=True)
    return merged[:MAX_ITEMS], stats


def load_previous(path=OUT):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("items", [])
    except Exception:
        return []


def focus_symbols():
    """หุ้นที่ควรเจาะข่าว: สัญญาณซื้อ + รอจังหวะคะแนนสูง (จากผลสแกนล่าสุด)"""
    try:
        with open(os.path.join(BASE, "site", "data", "scan_set.json"), encoding="utf-8") as f:
            rows = json.load(f)["rows"]
    except Exception:
        return []
    buys = [r["ticker"] for r in rows if r["status"] == "ซื้อ"]
    watch = [r["ticker"] for r in rows if r["status"] == "รอจังหวะ"][:25]
    return list(dict.fromkeys(buys + watch))


def main(quick=False, extra=()):
    prev = load_previous()
    focus = list(dict.fromkeys(list(extra) + ([] if quick else focus_symbols())))
    items, stats = collect(focus, quick=quick, previous=prev)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"time": datetime.now(BKK).isoformat(timespec="minutes"), "items": items,
                   "sources": stats}, f, ensure_ascii=False, separators=(",", ":"))
    tagged = sum(1 for i in items if i["sym"])
    print(f"บันทึกข่าว {len(items)} รายการ (ระบุหุ้นได้ {tagged}) → {OUT}")
    return items


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--symbols", nargs="*", default=[])
    a = ap.parse_args()
    main(a.quick, a.symbols)
