"""เว็บแอป (Flask + waitress) — เปิดจากคอมพิวเตอร์ แล้วใช้มือถือในวง WiFi เดียวกันเข้าผ่าน QR code

ความปลอดภัย: คอมพิวเตอร์เครื่องนี้เข้าได้เลย อุปกรณ์อื่นต้องใช้ PIN 6 หลัก (อยู่ใน QR code แล้ว)
"""
import io
import json
import os
import secrets
import socket
import threading
import time
import webbrowser

from flask import Flask, Response, jsonify, make_response, redirect, request, send_from_directory

import config as C
import portfolio as P
import service as S
from paths import DATA, WEB

app = Flask(__name__, static_folder=None)
PUBLIC = {"/login", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png",
          "/apple-touch-icon.png", "/style.css", "/favicon.ico"}
_fails = {}


def get_pin():
    path = os.path.join(DATA, "access_pin.txt")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(f"{secrets.randbelow(10**6):06d}")
    with open(path) as f:
        return f.read().strip()


PIN = get_pin()


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _authed_resp(resp):
    resp.set_cookie("pin", PIN, max_age=400 * 86400, httponly=True, samesite="Lax")
    return resp


@app.before_request
def guard():
    if request.remote_addr in ("127.0.0.1", "::1") or request.path in PUBLIC:
        return None
    if request.cookies.get("pin") == PIN:
        return None
    if request.args.get("k") == PIN:                       # มาจาก QR code
        return _authed_resp(redirect("/"))
    if request.path.startswith("/api/"):
        return jsonify(error="ต้องใส่ PIN ก่อน"), 401
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    msg = ""
    ip = request.remote_addr
    if request.method == "POST":
        n, t = _fails.get(ip, (0, 0))
        if n >= 8 and time.time() - t < 600:
            msg = "ใส่ผิดหลายครั้ง กรุณารอ 10 นาที"
        elif request.form.get("pin", "").strip() == PIN:
            _fails.pop(ip, None)
            return _authed_resp(redirect("/"))
        else:
            _fails[ip] = (n + 1, time.time())
            msg = "PIN ไม่ถูกต้อง"
    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>เข้าสู่ระบบ</title>
<link rel="stylesheet" href="/style.css"><link rel="manifest" href="/manifest.webmanifest"></head>
<body class="login"><form method="post" class="card">
<h1>หุ้นเด่น</h1><p class="mut">ใส่ PIN 6 หลักที่แสดงบนหน้าจอคอมพิวเตอร์</p>
<input name="pin" inputmode="numeric" pattern="[0-9]*" maxlength="6" autofocus autocomplete="one-time-code">
<button class="btn primary">เข้าใช้งาน</button><p class="err">{msg}</p></form></body></html>"""


# ------------------------------------------------------------ หน้าเว็บ
@app.route("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.route("/<path:name>")
def static_file(name):
    return send_from_directory(WEB, name)


def ok(data):
    return Response(json.dumps(S.clean(data), ensure_ascii=False), mimetype="application/json")


def err(msg, code=400):
    return Response(json.dumps({"error": msg}, ensure_ascii=False), code, mimetype="application/json")


# ------------------------------------------------------------ API
@app.get("/api/scan")
def api_scan():
    lst = request.args.get("list", "set")
    if lst not in C.WATCHLISTS:
        return err("ไม่รู้จักรายชื่อนี้")
    force = request.args.get("refresh") == "1"
    return ok(S.job(f"scan:{lst}", S.scan_data, lst, force=force, refresh=force))


@app.get("/api/analyze")
def api_analyze():
    t = (request.args.get("t") or "").strip().upper()
    if not t or len(t) > 15 or not all(ch.isalnum() or ch in ".-^&" for ch in t):
        return err("ชื่อย่อหุ้นไม่ถูกต้อง")
    return ok(S.job(f"analyze:{t}", S.analyze_data, t))


@app.get("/api/backtest")
def api_backtest():
    lst = request.args.get("list", "set")
    years = max(3, min(20, int(request.args.get("years", 10))))
    force = request.args.get("refresh") == "1"
    return ok(S.job(f"backtest:{lst}:{years}", S.backtest_json, lst, years, force=force))


@app.get("/api/paper")
def api_paper():
    try:
        return ok(P.status(update=request.args.get("update", "1") == "1"))
    except Exception as e:
        return err(str(e), 500)


@app.post("/api/paper/<action>")
def api_paper_action(action):
    body = request.get_json(silent=True) or {}
    try:
        if action == "buy":
            res = P.buy(body.get("ticker", ""), body.get("shares") or None)
        elif action == "sell":
            res = P.sell(body.get("ticker", ""))
        elif action == "reset":
            res = P.reset(body.get("capital"))
        else:
            return err("ไม่รู้จักคำสั่ง")
        return ok(res)
    except P.PaperError as e:
        return err(str(e))


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        try:
            new = {"CAPITAL": max(1000, float(body["CAPITAL"])),
                   "RISK_PER_TRADE": min(0.05, max(0.001, float(body["RISK_PER_TRADE"]))),
                   "MAX_POSITION_PCT": min(1.0, max(0.02, float(body["MAX_POSITION_PCT"]))),
                   "MAX_POSITIONS": min(30, max(1, int(body["MAX_POSITIONS"])))}
        except (KeyError, TypeError, ValueError):
            return err("ค่าที่กรอกไม่ถูกต้อง")
        C.save_settings(new)
        S.invalidate("scan")
        S.invalidate("backtest")
        S.invalidate("analyze")
    return ok({"settings": C.load_settings(), "lists": {k: C.WATCHLISTS[k] for k in ("set", "us")}})


@app.get("/api/connect")
def api_connect():
    url = f"http://{lan_ip()}:{app.config['PORT']}/?k={PIN}"
    svg = ""
    try:
        import qrcode
        import qrcode.image.svg
        buf = io.BytesIO()
        qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).save(buf)
        svg = buf.getvalue().decode()
    except Exception:
        pass
    local = request.remote_addr in ("127.0.0.1", "::1")
    return ok({"url": url if local else None, "pin": PIN if local else None, "qr": svg if local else None,
               "local": local})


# ------------------------------------------------------------ เริ่มเซิร์ฟเวอร์
def _free_port(port):
    for p in range(port, port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return port


@app.get("/api/ping")
def api_ping():
    return ok({"app": "stocktrader"})


def start_background(port=8765):
    """เริ่มเซิร์ฟเวอร์ในเธรดเบื้องหลัง คืนค่าพอร์ตที่ใช้ (สำหรับโหมดหน้าต่างโปรแกรม)"""
    from waitress import serve
    port = _free_port(port)
    app.config["PORT"] = port
    threading.Thread(target=serve, args=(app,), daemon=True,
                     kwargs=dict(host="0.0.0.0", port=port, threads=8, _quiet=True)).start()
    return port


def run(port=8765, open_browser=True):
    from waitress import serve
    port = _free_port(port)
    app.config["PORT"] = port
    url = f"http://{lan_ip()}:{port}/?k={PIN}"
    print("=" * 60)
    print("  โปรแกรมช่วยเทรดหุ้น — เว็บแอปพร้อมใช้งาน")
    print(f"  บนคอมพิวเตอร์นี้ : http://localhost:{port}")
    print(f"  บนมือถือ (WiFi เดียวกัน): {url}")
    print(f"  PIN: {PIN}")
    print("  (ถ้า Windows ถามเรื่อง Firewall ให้กด Allow / อนุญาต สำหรับเครือข่ายส่วนตัว)")
    print("  ปิดหน้าต่างนี้ = ปิดโปรแกรม")
    print("=" * 60)
    try:
        import qrcode
        q = qrcode.QRCode(border=1)
        q.add_data(url)
        q.print_ascii(invert=True)
    except Exception:
        pass
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    serve(app, host="0.0.0.0", port=port, threads=8, _quiet=True)
