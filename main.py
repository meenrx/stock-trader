"""โปรแกรมช่วยเทรดหุ้น — วิธีใช้:  python main.py --help

  python main.py web                   เปิดเว็บแอป (ใช้บนมือถือได้)  ← ค่าเริ่มต้นของ .exe
  python main.py scan                  สแกนหุ้นไทย บอก ซื้อ/รอจังหวะ/หลีกเลี่ยง
  python main.py scan --list us        สแกนหุ้นอเมริกา
  python main.py analyze PTT           วิเคราะห์หุ้นรายตัวแบบละเอียด
  python main.py backtest              ทดสอบกลยุทธ์ย้อนหลัง 10 ปีทั้งพอร์ต
  python main.py report                สแกน + backtest แล้วสร้างรายงาน HTML
  python main.py paper buy PTT         ซื้อในพอร์ตจำลอง (คำนวณจำนวนหุ้นให้)
  python main.py paper status          ดูพอร์ตจำลอง + เตือนจุดขาย
"""
import argparse
import os
import sys
import webbrowser

import config as C

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")


def tickers_from(args):
    if getattr(args, "tickers", None):
        from portfolio import norm
        return [norm(t) for t in args.tickers]
    return C.WATCHLISTS[args.list]


def print_rows(rows, regimes, top):
    for b, v in regimes.items():
        print(f"สภาพตลาด {b}: {v['text']}")
    for status in ("ซื้อ", "รอจังหวะ"):
        allr = [r for r in rows if r["status"] == status]
        print(f"\n===== {status} ({len(allr)}) =====")
        if not allr:
            print("  (ไม่มี)")
        for r in allr[:top]:
            p = r["plan"]
            print(f"  {r['ticker']:<8} คะแนน {r['score']:>5}  ราคา {r['close']:>9,.2f}  "
                  f"Stop {p['stop']:>9,.2f} ({p['stop_pct']}%)  เป้า {p['target']:>9,.2f}  "
                  f"{p['shares']:>6,} หุ้น")
            print(f"           → {r['how']}" + (f"  [{', '.join(r['signals'])}]" if r["signals"] else ""))


def cmd_scan(args):
    from scanner import scan
    regimes, rows, *_ = scan(tickers_from(args), use_fund=not args.no_fund,
                             refresh=args.refresh, capital=C.CAPITAL)
    print_rows(rows, regimes, args.top)


def cmd_analyze(args):
    from service import analyze_data
    a = analyze_data(args.ticker)
    r, i = a["row"], a["ind"]
    print(f"\n{r['ticker']}  {r['name']}  ({r['sector']})")
    print(f"สถานะ: {r['status']}  |  คะแนนรวม {r['score']}/100 (เทคนิค {r['tech']}/75, พื้นฐาน {r['fund']}/25)")
    print(f"→ {r['how']}")
    print(f"\nราคา {i['Close']:.2f} | SMA20 {i['SMA20']:.2f} | SMA50 {i['SMA50']:.2f} | SMA200 {i['SMA200']:.2f}")
    print(f"RSI {i['RSI']:.1f} | MACD hist {i['MACD_hist']:.3f} | ADX {i['ADX']:.1f} | ATR {i['ATR']:.2f} ({i['ATR_pct']*100:.1f}%)")
    print(f"ห่างจากไฮ 52 สัปดาห์ {r['from_high']}% | โมเมนตัม 6 เดือน {r['roc126']}% | มูลค่าซื้อขาย/วัน {r['value20_m']} ล้าน")
    print("คะแนนเทคนิคย่อย:", r["tech_detail"])
    print("ข้อมูลพื้นฐาน:", r["fund_detail"])
    if r["analyst_upside"] is not None:
        print(f"เป้านักวิเคราะห์เฉลี่ย: {r['analyst_upside']:+.1f}% ({r['analyst_rec']})")
    p = r["plan"]
    print(f"\nแผนเทรด (ทุน {C.CAPITAL:,.0f}): เข้า {p['entry']} | Stop {p['stop']} ({p['stop_pct']}%) | "
          f"เป้า {p['target']} (+{p['target_pct']}%) | {p['shares']:,} หุ้น ≈ {p['cost']:,.0f} | เสียได้สูงสุด {p['max_loss']:,.0f}")
    print(f"จุดเบรกเอาต์: {p['breakout_level']} | โซนย่อซื้อ: {p['pullback_zone'][0]}–{p['pullback_zone'][1]}")
    if a["bt"]:
        print("\nทดสอบกลยุทธ์ย้อนหลังกับหุ้นตัวนี้ตัวเดียว (ลงเต็มพอร์ตทุกไม้):")
        for k, v in a["bt"].items():
            print(f"  {k}: {v}")


def run_bt(args, verbose=True):
    from service import backtest_data
    eq, tr, m, _ = backtest_data(args.list, args.years)
    if verbose:
        print(f"\nทดสอบย้อนหลังหุ้น ({args.list}) — ทุน {C.CAPITAL:,.0f}")
        for k, v in m.items():
            if k != "รายปี%":
                print(f"  {k}: {v}")
        print("  รายปี:", "  ".join(f"{k} {v:+.1f}%" for k, v in m.get("รายปี%", {}).items()))
        from paths import REPORTS as out
        tr.to_csv(os.path.join(out, "backtest_trades.csv"), index=False, encoding="utf-8-sig")
        eq.to_csv(os.path.join(out, "backtest_equity.csv"), header=["equity"], encoding="utf-8-sig")
        print(f"  บันทึกรายการเทรดไว้ที่ {out}\\backtest_trades.csv")
    return eq, tr, m


def cmd_report(args):
    from report import build
    from scanner import scan
    regimes, rows, *_ = scan(tickers_from(args), use_fund=not args.no_fund,
                             refresh=args.refresh, capital=C.CAPITAL)
    print_rows(rows, regimes, args.top)
    bt = None if args.no_backtest else run_bt(args, verbose=False)
    path = build(regimes, rows, bt)
    print(f"\nรายงาน: {path}")
    if not args.no_open:
        webbrowser.open("file:///" + path.replace("\\", "/"))


def cmd_paper(args):
    import portfolio as P
    try:
        if args.action == "buy":
            print(P.buy(args.ticker, args.shares, args.price)["msg"])
        elif args.action == "sell":
            print(P.sell(args.ticker, args.price)["msg"])
        elif args.action == "reset":
            print(P.reset()["msg"])
        else:
            P.print_status(P.status())
    except P.PaperError as e:
        raise SystemExit(f"ผิดพลาด: {e}")


def cmd_web(args):
    from server import run
    run(port=args.port, open_browser=not args.no_open)


def main(argv=None):
    ap = argparse.ArgumentParser(description="โปรแกรมช่วยเทรดหุ้น (เว็บแอป/สแกน/วิเคราะห์/ทดสอบย้อนหลัง/พอร์ตจำลอง)")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--list", default="set", choices=list(C.WATCHLISTS), help="set / us / all")
        p.add_argument("--tickers", nargs="+", help="ระบุหุ้นเอง เช่น --tickers PTT CPALL AOT")
        p.add_argument("--top", type=int, default=15, help="แสดงกี่ตัวต่อกลุ่ม")
        p.add_argument("--no-fund", action="store_true", help="ข้ามข้อมูลพื้นฐาน (เร็วขึ้น)")
        p.add_argument("--refresh", action="store_true", help="โหลดข้อมูลใหม่ ไม่ใช้แคช")
        p.add_argument("--years", type=int, default=10, help="จำนวนปีสำหรับ backtest")

    p = sub.add_parser("web", help="เปิดเว็บแอป (ค่าเริ่มต้น)")
    p.add_argument("--port", type=int, default=8765); p.add_argument("--no-open", action="store_true")
    p.set_defaults(f=cmd_web)
    p = sub.add_parser("scan", help="สแกนหุ้นทั้งรายชื่อ"); common(p); p.set_defaults(f=cmd_scan)
    p = sub.add_parser("analyze", help="วิเคราะห์หุ้นรายตัว"); p.add_argument("ticker"); p.set_defaults(f=cmd_analyze)
    p = sub.add_parser("backtest", help="ทดสอบย้อนหลัง"); common(p); p.set_defaults(f=lambda a: run_bt(a))
    p = sub.add_parser("report", help="สร้างรายงาน HTML"); common(p)
    p.add_argument("--no-backtest", action="store_true"); p.add_argument("--no-open", action="store_true")
    p.set_defaults(f=cmd_report)
    p = sub.add_parser("paper", help="พอร์ตจำลอง")
    p.add_argument("action", choices=["buy", "sell", "status", "reset"])
    p.add_argument("ticker", nargs="?"); p.add_argument("--shares", type=int); p.add_argument("--price", type=float)
    p.set_defaults(f=cmd_paper)

    args = ap.parse_args(argv)
    if not args.cmd:                       # ดับเบิลคลิก .exe / ไม่ใส่คำสั่ง → เปิดเว็บแอป
        args = ap.parse_args(["web"] + (argv or []))
    args.f(args)


if __name__ == "__main__":
    main()
