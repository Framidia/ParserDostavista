@echo off
title Android RE Stack

echo [1] Starting emulator...
start "" "C:\Users\user\AppData\Local\Android\Sdk\emulator\emulator.exe" -avd Pixel_8

echo Waiting for emulator...
adb wait-for-device

echo [2] Waiting for boot...
:loop
adb shell getprop sys.boot_completed | find "1" >nul
if errorlevel 1 (
    timeout /t 2 >nul
    goto loop
)

echo Emulator booted!

echo [3] Starting frida-server...
start cmd /k adb shell pkill frida-server /data/local/tmp/frida-server &

echo [4] Starting mitmweb...
start cmd /k mitmweb

echo [5] Starting objection...
timeout /t 3 >nul
start cmd /k objection -g com.sebbia.delivery explore

echo DONE
pause