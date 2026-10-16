"""Osobní nastavení v nastaveni.json vedle programu - není v gitu. V cloudu (GitHub Actions) se berou
z proměnných prostředí (GitHub Secrets) se stejným názvem velkými písmeny (JMENO, EMAIL_KOMU, SMTP_HESLO, ...).

{
  "jmeno": "",                  komu Hledač patří - oslovení na stránce a v titulku (např. „Domča“)
  "osloveni": "",               5. pád pro pozdrav („Ahoj Domčo“); prázdné = stejné jako jméno
  "email_komu": "",             kam chodí denní souhrn (víc adres oddělit čárkou)
  "email_od": "",               odesílatel (u Gmailu stejná adresa jako smtp_uzivatel, u Brevo ověřený odesílatel)
  "smtp_server": "",            např. smtp.gmail.com nebo smtp-relay.brevo.com
  "smtp_port": "587",           587 = STARTTLS (465 = SSL)
  "smtp_uzivatel": "",          přihlašovací jméno k SMTP
  "smtp_heslo": "",             heslo aplikace (Gmail) nebo SMTP klíč (Brevo) - nikdy běžné heslo k poště
  "ntfy_kanal": "",             nepovinné: kanál aplikace ntfy pro souhrn i na mobil
  "ai_api_klic": "",            klíč Google Gemini pro postřehy AI (zdarma, bez karty: https://aistudio.google.com/apikey)
  "cerebras_api_klic": "",      záloha, když je Gemini přetížený (zdarma: https://cloud.cerebras.ai)
  "groq_api_klic": ""           další záloha (zdarma: https://console.groq.com/keys)
}
"""
import json
import os
from pathlib import Path

SOUBOR = Path(__file__).parent / "nastaveni.json"
VYCHOZI = {"jmeno": "", "osloveni": "", "email_komu": "", "email_od": "", "smtp_server": "", "smtp_port": "587",
           "smtp_uzivatel": "", "smtp_heslo": "", "ntfy_kanal": "", "ai_api_klic": "", "cerebras_api_klic": "",
           "groq_api_klic": ""}


def nacti() -> dict:
    data = dict(VYCHOZI)
    if SOUBOR.exists():
        try:
            data |= json.loads(SOUBOR.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    for klic in VYCHOZI:  # cloud: tajné hodnoty z GitHub Secrets
        if os.environ.get(klic.upper()):
            data[klic] = os.environ[klic.upper()]
    return data
