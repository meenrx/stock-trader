@echo off
cd /d "%~dp0"
pip install -q yfinance pandas numpy flask waitress qrcode pystray pillow pyinstaller
pyinstaller --noconfirm --onefile --windowed --name StockTrader --icon web\app.ico ^
  --add-data "web;web" ^
  --collect-all yfinance --collect-all curl_cffi --collect-data certifi ^
  --hidden-import waitress --hidden-import qrcode.image.svg --hidden-import pystray._win32 ^
  desktop.py
echo.
echo Done: dist\StockTrader.exe
pause
