"""โหมดโปรแกรมปกติ: ไม่มีหน้าต่าง command — เปิดเป็นหน้าต่างแอป + ไอคอนที่ถาดมุมขวาล่าง

- ดับเบิลคลิกซ้ำขณะเปิดอยู่ → แค่เปิดหน้าต่างใหม่ ไม่เปิดโปรแกรมซ้อน
- ปิดหน้าต่าง → โปรแกรมยังทำงานที่ถาด (มือถือยังเข้าได้)
- ปิดโปรแกรมจริง → คลิกขวาไอคอนที่ถาด → "ปิดโปรแกรม"
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

from paths import DATA, FROZEN, WEB

PORT = 8765


def _quiet_io():
    """โหมดไม่มีหน้าต่าง: ส่งข้อความ/ข้อผิดพลาดลงไฟล์ data/app.log แทน"""
    if sys.stdout is None or sys.stderr is None:
        log = open(os.path.join(DATA, "app.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def find_browser():
    env = os.environ
    cands = [
        os.path.join(env.get("ProgramFiles(x86)", ""), r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(env.get("ProgramFiles", ""), r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(env.get("ProgramFiles", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(env.get("ProgramFiles(x86)", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(env.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    ]
    return next((c for c in cands if c and os.path.exists(c)), None)


def open_window(port, page=""):
    """เปิดเป็นหน้าต่างแอป (ไม่มีแถบที่อยู่/แท็บ) ด้วย Edge หรือ Chrome"""
    url = f"http://localhost:{port}/{('#' + page) if page else ''}"
    exe = find_browser()
    if exe:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([exe, f"--app={url}", "--window-size=540,920"], creationflags=flags)
    else:
        webbrowser.open(url)


def running_port():
    """ถ้าโปรแกรมเปิดอยู่แล้ว คืนพอร์ตของตัวที่เปิดอยู่"""
    for p in range(PORT, PORT + 20):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{p}/api/ping", timeout=0.4) as r:
                if json.load(r).get("app") == "stocktrader":
                    return p
        except Exception:
            continue
    return None


def wait_ready(port, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=0.5)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    _quiet_io()
    p = running_port()
    if p:                       # เปิดอยู่แล้ว → แค่เปิดหน้าต่าง
        open_window(p)
        return

    import server
    port = server.start_background(PORT)
    wait_ready(port)
    open_window(port)

    try:
        import pystray
        from PIL import Image
    except ImportError:          # ไม่มีไลบรารีถาด → ทำงานต่อจนกว่าจะปิดด้วยวิธีอื่น
        while True:
            time.sleep(3600)

    def quit_app(icon, _item=None):
        icon.visible = False
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("เปิดโปรแกรม", lambda i, _: open_window(port), default=True),
        pystray.MenuItem("เปิดบนมือถือ (QR code)", lambda i, _: open_window(port, "set")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("ปิดโปรแกรม", quit_app),
    )
    icon = pystray.Icon("StockTrader", Image.open(os.path.join(WEB, "icon-192.png")),
                        "หุ้นเด่น — โปรแกรมช่วยเทรดหุ้น", menu)

    def setup(ic):
        ic.visible = True
        try:
            ic.notify("โปรแกรมทำงานอยู่ที่ไอคอนมุมขวาล่าง\nปิดหน้าต่างได้ — ปิดโปรแกรมจริงให้คลิกขวาที่ไอคอน",
                      "หุ้นเด่น")
        except Exception:
            pass

    icon.run(setup)


if __name__ == "__main__":
    if len(sys.argv) > 1:       # มีคำสั่งต่อท้าย เช่น StockTrader.exe scan → โหมดคำสั่ง
        import main as cli
        cli.main()
    else:
        main()
