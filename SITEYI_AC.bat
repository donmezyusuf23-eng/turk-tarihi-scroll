@echo off
chcp 65001 >nul
title Bozkirdan Cumhuriyete - Yerel Sunucu
cd /d "%~dp0"

echo.
echo   Bozkirdan Cumhuriyete
echo.

if not exist "dist\index.html" (
  echo   dist\index.html bulunamadi.
  echo   Once README.md icindeki "Kurulum" adimlarini calistir:
  echo.
  echo     python tools\frames_from_photos.py --photos "bozkir=photos/bozkir.jpg,osmanli=photos/osmanli.jpg,cumhuriyet=photos/cumhuriyet.jpg" --out frames --count 180
  echo     python tools\frames_from_photos.py --photos "bozkir=photos/bozkir.jpg,osmanli=photos/osmanli.jpg,cumhuriyet=photos/cumhuriyet.jpg" --out frames-mobile --count 180 --width 900 --height 1600
  echo     node tools\build.mjs
  echo.
  pause
  exit /b 1
)

start "" http://127.0.0.1:4321/

node "%~dp0tools\serve.mjs" --dir dist --port 4321

echo.
echo   Sunucu kapandi.
pause
