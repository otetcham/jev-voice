@echo off
chcp 65001 > nul
title Jev Voice (PTT Mode)
cd /d "%~dp0"
call "%~dp0.venv\Scripts\python.exe" -m jev_voice.main --ptt
if errorlevel 1 pause
