"""สร้างรายงาน HTML (เปิดด้วยเบราว์เซอร์ได้เลย)"""
import html
import os
from datetime import datetime

import config as C

from paths import REPORTS as OUT


def spark(vals, w=120, h=30):
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - (v - lo) / rng * h:.1f}" for i, v in enumerate(vals))
    col = "var(--up)" if vals[-1] >= vals[0] else "var(--down)"
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polyline fill="none" stroke="{col}" stroke-width="1.5" points="{pts}"/></svg>'


def equity_svg(eq, w=760, h=220):
    s = eq.resample("W").last().dropna()
    vals = list(s.values)
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - 10 - (v - lo) / rng * (h - 20):.1f}" for i, v in enumerate(vals))
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto">'
            f'<polyline fill="none" stroke="var(--accent)" stroke-width="2" points="{pts}"/>'
            f'<text x="4" y="14" class="ax">{hi:,.0f}</text><text x="4" y="{h - 2}" class="ax">{lo:,.0f}</text>'
            f'<text x="{w - 4}" y="{h - 2}" text-anchor="end" class="ax">{s.index[-1]:%Y-%m}</text>'
            f'<text x="60" y="{h - 2}" class="ax">{s.index[0]:%Y-%m}</text></svg>')


def _rows(rows):
    out = []
    for r in rows:
        p = r["plan"]
        fd = ", ".join(f"{k} {v}" for k, v in r["fund_detail"].items())
        badge = {"ซื้อ": "buy", "รอจังหวะ": "watch", "หลีกเลี่ยง": "avoid"}[r["status"]]
        up = "" if r["analyst_upside"] is None else f"{r['analyst_upside']:+.1f}%"
        out.append(f"""<tr>
<td><b>{r['ticker']}</b><div class="sub">{html.escape(r['name'][:28])}</div></td>
<td><span class="b {badge}">{r['status']}</span></td>
<td class="n"><b>{r['score']}</b><div class="sub">เทคนิค {r['tech']} · พื้นฐาน {r['fund']}</div></td>
<td class="n">{r['close']:,.2f}</td>
<td>{spark(r['spark'])}</td>
<td class="n">{r['roc126']:+.1f}%<div class="sub">RSI {r['rsi']}</div></td>
<td class="n">{p['stop']:,.2f}<div class="sub">{p['stop_pct']}%</div></td>
<td class="n">{p['target']:,.2f}<div class="sub">+{p['target_pct']}%</div></td>
<td class="n">{p['shares']:,}<div class="sub">~{p['cost']:,.0f} ฿</div></td>
<td>{html.escape(r['how'])}<div class="sub">{html.escape(' · '.join(r['signals']))}</div>
<div class="sub">{html.escape(fd)}{(' · นักวิเคราะห์ ' + up) if up else ''}</div></td>
</tr>""")
    return "\n".join(out)


def build(regimes, rows, bt=None, title="รายงานหุ้นน่าสนใจ"):
    os.makedirs(OUT, exist_ok=True)
    now = datetime.now()
    buys = [r for r in rows if r["status"] == "ซื้อ"]
    watch = [r for r in rows if r["status"] == "รอจังหวะ"]
    avoid = [r for r in rows if r["status"] == "หลีกเลี่ยง"]
    reg_html = "".join(
        f'<div class="card"><div class="sub">{"SET50 (TDEX)" if ".BK" in b else "S&P 500"}</div>'
        f'<b>{html.escape(v["text"])}</b><div class="sub">ดัชนี {v.get("close", "-")} / SMA200 {v.get("sma200", "-")}</div></div>'
        for b, v in regimes.items())
    head = ("<tr><th>หุ้น</th><th>สถานะ</th><th>คะแนน</th><th>ราคา</th><th>6 เดือน</th>"
            "<th>โมเมนตัม 6ด.</th><th>Stop</th><th>เป้า 2R</th><th>จำนวนหุ้น</th><th>วิธีเข้า / เหตุผล</th></tr>")

    bt_html = ""
    if bt:
        eq, tr, m = bt
        yearly = m.pop("รายปี%", {})
        cells = "".join(f'<div class="card"><div class="sub">{k}</div><b>{v}</b></div>' for k, v in m.items())
        yrs = "".join(f'<span class="yr {"pos" if v >= 0 else "neg"}">{k}: {v:+.1f}%</span>' for k, v in yearly.items())
        last = tr.tail(15).iloc[::-1] if len(tr) else []
        trows = "".join(f"<tr><td>{t.ticker.replace('.BK', '')}</td><td>{t.entry_date}</td><td>{t.exit_date}</td>"
                        f"<td class='n'>{t.entry}</td><td class='n'>{t.exit}</td>"
                        f"<td class='n {'pos' if t.pnl > 0 else 'neg'}'>{t.ret_pct:+.1f}%</td><td>{t.reason}</td></tr>"
                        for t in (last.itertuples() if len(tr) else []))
        bt_html = f"""<h2>ผลทดสอบย้อนหลัง (Backtest)</h2>
<div class="grid">{cells}</div><div class="yrs">{yrs}</div>
<div class="panel">{equity_svg(eq)}</div>
<details><summary>เทรดล่าสุด 15 ไม้</summary><div class="scroll"><table>
<tr><th>หุ้น</th><th>เข้า</th><th>ออก</th><th>ราคาเข้า</th><th>ราคาออก</th><th>ผล</th><th>เหตุผล</th></tr>{trows}</table></div></details>
<p class="sub">หมายเหตุ: ทดสอบด้วยรายชื่อหุ้นปัจจุบัน (มี survivorship bias) และไม่ได้ใช้คะแนนพื้นฐานในอดีต ผลจริงมักแย่กว่านี้</p>"""

    page = f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
:root{{--bg:#f7f7f5;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#e3e2dd;--accent:#2f6fde;--up:#1a8a4a;--down:#c43d3d;--watch:#b7791f}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151514;--fg:#ecebe7;--mut:#9a9993;--card:#1f1f1d;--line:#33332f;--accent:#6c9cf0;--up:#4cc27c;--down:#e46b6b;--watch:#e0a84a}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Segoe UI",Tahoma,sans-serif;margin:0;padding:24px 16px;max-width:1300px;margin:auto}}
h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:17px;margin:28px 0 10px}}
.sub{{color:var(--mut);font-size:12px}}.grid{{display:flex;flex-wrap:wrap;gap:10px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:140px}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin-top:10px}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;background:var(--card)}}
th,td{{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}}
th{{font-size:12px;color:var(--mut);font-weight:600;white-space:nowrap}}.n{{text-align:right;white-space:nowrap}}
.b{{padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600;white-space:nowrap}}
.buy{{background:color-mix(in srgb,var(--up) 18%,transparent);color:var(--up)}}
.watch{{background:color-mix(in srgb,var(--watch) 18%,transparent);color:var(--watch)}}
.avoid{{background:color-mix(in srgb,var(--mut) 15%,transparent);color:var(--mut)}}
.pos{{color:var(--up)}}.neg{{color:var(--down)}}.yrs{{margin-top:10px;display:flex;flex-wrap:wrap;gap:12px}}
.ax{{fill:var(--mut);font-size:11px}}details{{margin-top:10px}}summary{{cursor:pointer;color:var(--accent)}}
.warn{{border-left:3px solid var(--watch);padding:8px 12px;background:var(--card);margin-top:24px}}
</style></head><body>
<h1>{title}</h1><div class="sub">สร้างเมื่อ {now:%d/%m/%Y %H:%M} · เงินทุน {C.CAPITAL:,} · เสี่ยงต่อไม้ {C.RISK_PER_TRADE*100:.0f}% · ราคาปิดล่าสุด</div>
<h2>สภาพตลาด</h2><div class="grid">{reg_html}
<div class="card"><div class="sub">สัญญาณซื้อ</div><b>{len(buys)} ตัว</b></div>
<div class="card"><div class="sub">รอจังหวะ</div><b>{len(watch)} ตัว</b></div>
<div class="card"><div class="sub">หลีกเลี่ยง</div><b>{len(avoid)} ตัว</b></div></div>
<h2>มีสัญญาณซื้อ ({len(buys)})</h2><div class="scroll"><table>{head}{_rows(buys) or '<tr><td colspan=10 class="sub">วันนี้ไม่มีหุ้นที่ผ่านทุกเงื่อนไข — การไม่ซื้อก็เป็นการตัดสินใจที่ดีได้</td></tr>'}</table></div>
<h2>หุ้นแนวโน้มดี รอจังหวะเข้า ({len(watch)})</h2><div class="scroll"><table>{head}{_rows(watch)}</table></div>
<details><summary>หลีกเลี่ยง ({len(avoid)})</summary><div class="scroll"><table>{head}{_rows(avoid)}</table></div></details>
{bt_html}
<div class="warn"><b>คำเตือน:</b> รายงานนี้สร้างจากสูตรคำนวณอัตโนมัติ ไม่ใช่คำแนะนำการลงทุนเฉพาะบุคคล
ข้อมูลจาก Yahoo Finance อาจล่าช้าหรือคลาดเคลื่อน ผลในอดีตไม่รับประกันอนาคต
ตั้ง Stop ทุกครั้ง และใช้เงินที่เสียได้เท่านั้น</div>
</body></html>"""
    path = os.path.join(OUT, f"report_{now:%Y%m%d_%H%M}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path
