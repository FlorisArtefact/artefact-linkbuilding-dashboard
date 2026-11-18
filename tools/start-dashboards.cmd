@echo off
rem Start both dashboards (double-click). BWJ = admin view on 8501, Hornbach = client view on 8502.
rem The first load takes about 3 minutes; open the pages a few minutes before the demo.
cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
start "BWJ dashboard 8501" cmd /k ""%TEMP%\bwjvenv\Scripts\streamlit.exe" run app.py --server.port 8501 --server.headless true"
start "Hornbach dashboard 8502" cmd /k "set CONFIG_FILE=clients/hornbach.json&& set VIEW_MODE=client&& set AHREFS_ENABLED=0&& "%TEMP%\bwjvenv\Scripts\streamlit.exe" run app.py --server.port 8502 --server.headless true"
timeout /t 8 >nul
start "" http://localhost:8501
start "" http://localhost:8502
