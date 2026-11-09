"""ตั้งค่าหลักของโปรแกรม — แก้ตัวเลขตรงนี้ให้เข้ากับตัวเอง"""

# ---------- เงินทุนและการคุมความเสี่ยง ----------
CAPITAL = 100_000          # เงินทุน (บาท)
RISK_PER_TRADE = 0.01      # ยอมขาดทุนต่อไม้ไม่เกิน 1% ของพอร์ต
MAX_POSITION_PCT = 0.20    # ถือหุ้นตัวเดียวไม่เกิน 20% ของพอร์ต
MAX_POSITIONS = 6          # ถือพร้อมกันไม่เกิน 6 ตัว

# ---------- ค่าใช้จ่าย (โบรกออนไลน์ไทยทั่วไป) ----------
COMMISSION = 0.00157 * 1.07   # ค่าคอม 0.157% + VAT 7% ต่อขา
SLIPPAGE = 0.001              # เผื่อราคาคลาดเคลื่อน 0.1% ต่อขา

# ---------- จุดตัดขาดทุน / ทำกำไร ----------
ATR_STOP_MULT = 2.0     # จุดตัดขาดทุนเริ่มต้น = ราคาเข้า - 2 x ATR
ATR_TRAIL_MULT = 3.0    # จุดตัดขาดทุนแบบเลื่อนตาม = ราคาปิดสูงสุด - 3 x ATR
TARGET_R = 2.0          # เป้าแรก = กำไร 2 เท่าของความเสี่ยง (2R)

# ---------- เกณฑ์การให้คะแนน ----------
BUY_SCORE = 60          # คะแนนขั้นต่ำที่จะให้สถานะ "ซื้อ"
WATCH_SCORE = 50        # คะแนนขั้นต่ำที่จะให้สถานะ "รอจังหวะ"
SIGNAL_LOOKBACK = 3     # สัญญาณซื้อที่เกิดภายใน N วันทำการล่าสุดยังถือว่าใช้ได้

BENCHMARK = "TDEX.BK"   # ETF ที่ตาม SET50 (Yahoo ไม่มีประวัติดัชนี SET) ใช้ดูสภาพตลาด
LOT_SIZE_TH = 100       # หุ้นไทยซื้อขายขั้นต่ำ 100 หุ้น

# ---------- รายชื่อหุ้น ----------
# หุ้นไทยขนาดใหญ่ สภาพคล่องสูง (ใกล้เคียง SET50/SET100) — เพิ่ม/ลบได้ตามใจ
SET_STOCKS = [
    "ADVANC", "AOT", "AWC", "BANPU", "BBL", "BCP", "BDMS", "BEM", "BH", "BJC",
    "BTS", "CBG", "CCET", "CENTEL", "COM7", "CPALL", "CPF", "CPN", "CRC", "DELTA",
    "EGCO", "GPSC", "GULF", "HMPRO", "IVL", "KBANK", "KKP", "KTB", "KTC", "LH",
    "MINT", "MTC", "OR", "OSP", "PTT", "PTTEP", "PTTGC", "RATCH", "SAWAD", "SCB",
    "SCC", "SCGP", "SPALI", "TISCO", "TOP", "TRUE", "TTB", "TU", "WHA", "TIDLOR",
    "AP", "SIRI", "QH", "BGRIM", "CK", "STA", "JMT", "PLANB", "M", "AEONTS",
    "BLA", "TLI", "BAM", "ICHI", "SISB", "HANA", "KCE", "ERW", "AMATA", "THANI",
]
US_STOCKS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK-B", "JPM",
    "V", "MA", "LLY", "UNH", "COST", "WMT", "XOM", "JNJ", "PG", "HD",
    "NFLX", "AMD", "ORCL", "CRM", "ADBE", "KO", "PEP", "MRK", "ABBV", "TSM",
]


def th(symbols):
    return [s if s.endswith(".BK") else f"{s}.BK" for s in symbols]


def _all_th():
    """หุ้นไทยทั้งตลาด (SET + mai) จาก th_stocks.json — ไม่มีไฟล์ก็ใช้รายชื่อหุ้นใหญ่ด้านบน"""
    import json
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "th_stocks.json")
    try:
        with open(p, encoding="utf-8") as f:
            rows = json.load(f)
        names = {r["s"] + ".BK": r.get("n", "") for r in rows}
        return list(names), names
    except Exception:
        return th(SET_STOCKS), {}


TH_ALL, TH_NAMES = _all_th()

WATCHLISTS = {
    "set": TH_ALL,
    "set100": th(SET_STOCKS),
    "us": US_STOCKS,
}
WATCHLISTS["all"] = WATCHLISTS["set"] + WATCHLISTS["us"]


# ---------- ค่าที่ผู้ใช้ปรับจากหน้าเว็บ (เก็บใน data/settings.json) ----------
SETTING_KEYS = {"CAPITAL": float, "RISK_PER_TRADE": float,
                "MAX_POSITION_PCT": float, "MAX_POSITIONS": int}


def _settings_path():
    from paths import DATA
    import os
    return os.path.join(DATA, "settings.json")


def load_settings():
    import json
    import os
    p = _settings_path()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            for k, typ in SETTING_KEYS.items():
                if k in d:
                    globals()[k] = typ(d[k])
        except Exception:
            pass
    return {k: globals()[k] for k in SETTING_KEYS}


def save_settings(new):
    import json
    cur = load_settings()
    for k, typ in SETTING_KEYS.items():
        if k in new and new[k] is not None:
            cur[k] = typ(new[k])
            globals()[k] = cur[k]
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2)
    return cur


load_settings()
