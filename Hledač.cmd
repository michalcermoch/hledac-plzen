@echo off
rem Spustí Hledač nemovitostí jako místní web (http://localhost:8766) s tlačítkem Aktualizovat.
rem Okno nech otevřené, dokud s přehledem pracuješ; zavřením se Hledač ukončí.
title Hledac nemovitosti
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
py hledac.py --server
pause
