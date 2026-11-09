"""ตำแหน่งไฟล์ — ใช้ได้ทั้งตอนรันเป็น .py และเป็น .exe (ข้อมูลเก็บข้างไฟล์ .exe)"""
import os
import sys

FROZEN = getattr(sys, "frozen", False)
BASE = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
RES = getattr(sys, "_MEIPASS", BASE)          # ไฟล์ที่ฝังมากับ .exe (หน้าเว็บ)
DATA = os.path.join(BASE, "data")
CACHE = os.path.join(DATA, "cache")
REPORTS = os.path.join(BASE, "reports")
WEB = os.path.join(RES, "web")
for _d in (DATA, CACHE, REPORTS):
    os.makedirs(_d, exist_ok=True)
