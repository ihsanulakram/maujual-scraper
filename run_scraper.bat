@echo off
title Maujual Scraper & Telegram Bot
echo ========================================================
echo         Maujual.com HP Scraper ^& Telegram Bot
echo ========================================================
echo Memeriksa file Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak ditemukan di PATH! Silakan install Python terlebih dahulu.
    pause
    exit /b
)

echo Memulai bot...
python scraper_maujual.py
pause
