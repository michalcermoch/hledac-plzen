@echo off
rem Zkouška přihlášení nanečisto (kód z pozvánky -> vlastní heslo -> e-mail), nesahá na Domčův přístup.
title Zkouska prihlaseni
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
py zkouska_prihlaseni.py
pause
