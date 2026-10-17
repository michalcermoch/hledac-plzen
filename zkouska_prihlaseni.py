"""Zkouška přihlášení nanečisto - projdi si sám, co uvidí Domča na zašifrované stránce, bez sahání na jeho přístup.

    py zkouska_prihlaseni.py        (nebo Zkouška přihlášení.cmd)

Vyrobí zkušební zašifrovanou stránku stejně jako cloud (sifrovani.py), jen s vlastním zkušebním klíčem, kódem
z pozvánky ZKOUSKA-2026 a vlastním skrytým kanálem. Obsah je tvůj místní přehled (prehled.html).
Běží na http://localhost:8767 (jiná adresa = jiné zapamatované údaje než Domčova stránka i místní Hledač).

V okně pak Enter = „další běh cloudu“: převezme nastavené heslo a e-mail z kanálu a stránku vyrobí znovu,
přesně jako GitHub. Nic se neposílá e-mailem a nic se nezapisuje do Domčova cloudu.
"""
import json
import os
import secrets
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sifrovani

KOREN = Path(__file__).parent
SLOZKA = KOREN / "web-zkouska"  # v .gitignore
PORT = 8767
KOD = "ZKOUSKA-2026"


def vyrob(klic: bytes, kanal: str, pristupy: list[dict], email: dict | None):
    obsah = (KOREN / "prehled.html").read_text(encoding="utf-8") if (KOREN / "prehled.html").exists() \
        else "<h1>Zkušební obsah</h1><p>Místní přehled zatím není - spusť jednou Hledač.cmd.</p>"
    SLOZKA.mkdir(exist_ok=True)
    (SLOZKA / "index.html").write_text(
        sifrovani.zasifruj(obsah, klic, KOD, pristupy, kanal, "zkouška", email_nastaven=bool(email)), encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    klic = secrets.token_bytes(32)
    kanal = "hledac-zkouska-" + secrets.token_hex(12)  # náhodný, platí jen pro tuhle zkoušku
    pristupy, email = [], None
    vyrob(klic, kanal, pristupy, email)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), partial(SimpleHTTPRequestHandler, directory=str(SLOZKA)))
    server.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://localhost:{PORT}/"
    print(f"Zkušební stránka: {url}\nKód z pozvánky: {KOD}\n")
    print("Tip: otevři ji v anonymním okně - pak začínáš vždy od nuly jako Domča na novém telefonu.\n")
    webbrowser.open(url)
    krok = 1
    while True:
        try:
            vstup = input(f"[Enter] = další běh cloudu ({krok}.), k = konec: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if vstup == "k":
            break
        pristupy = sifrovani.nove_pristupy(kanal, pristupy)
        email = sifrovani.novy_email(kanal, klic, email)
        vyrob(klic, kanal, pristupy, email)
        adresa = sifrovani.email_z(email, klic) if email else None
        print(f"  cloud: nastavená hesla {len(pristupy)}"
              + (" -> kód z pozvánky už NEPLATÍ" if pristupy else " -> pořád platí kód z pozvánky")
              + f"; e-mail pro upozornění: {adresa or 'zatím žádný'}")
        print("  stránku v prohlížeči obnov (F5).\n")
        krok += 1
    server.shutdown()


if __name__ == "__main__":
    main()
