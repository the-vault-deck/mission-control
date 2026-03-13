@echo off

echo ============================================
echo   mAIn St. Solutions - Mission Control 3.11
echo ============================================
echo.

echo Starting MC3 Bridge v1.4...
start cmd /k "cd /d C:\Users\Tony\Desktop\soul-staging && python bridge_v1.4.py"

timeout /t 3

echo Opening Mission Control...
start chrome http://localhost:7070/mc3

echo.
echo   Bridge: http://localhost:7070
echo   MC3:    http://localhost:7070/mc3
echo   Health: http://localhost:7070/health
echo.
echo   Close the bridge CMD window to stop.
echo ============================================