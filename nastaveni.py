"""Osobní nastavení v nastaveni.json vedle programu - není v gitu. V cloudu (GitHub Actions) se berou
z proměnných prostředí (GitHub Secrets): JMENO, OSLOVENI, NTFY_KANAL, WHATSAPP_TELEFON, WHATSAPP_KLIC,
AI_API_KLIC, CEREBRAS_API_KLIC, GROQ_API_KLIC.

{
  "jmeno": "",                  komu Hledač patří - oslovení na stránce a v titulku (např. „Domča“)
  "osloveni": "",               5. pád pro pozdrav („Ahoj Domčo“); prázdné = stejné jako jméno
  "ntfy_kanal": "hledac-...",   kanál pro upozornění v aplikaci ntfy (vygeneruje se sám, náhodný a dlouhý)
  "whatsapp_telefon": "",       číslo pro zprávy na WhatsApp přes CallMeBot, např. +420777123456 (nepovinné)
  "whatsapp_klic": "",          apikey od CallMeBot (zdarma: https://www.callmebot.com/blog/free-api-whatsapp-messages/)
  "ai_api_klic": "",            klíč Google Gemini pro postřehy AI (zdarma, bez karty: https://aistudio.google.com/apikey)
  "cerebras_api_klic": "",      záloha, když je Gemini přetížený (zdarma: https://cloud.cerebras.ai)
  "groq_api_klic": ""           další záloha (zdarma: https://console.groq.com/keys)
}
"""
import json
import os
import secrets
from pathlib import Path

SOUBOR = Path(__file__).parent / "nastaveni.json"
VYCHOZI = {"jmeno": "", "osloveni": "", "ntfy_kanal": "", "whatsapp_telefon": "", "whatsapp_klic": "",
           "ai_api_klic": "", "cerebras_api_klic": "", "groq_api_klic": ""}
PROMENNE = {"jmeno": "JMENO", "osloveni": "OSLOVENI", "ntfy_kanal": "NTFY_KANAL", "whatsapp_telefon": "WHATSAPP_TELEFON",
            "whatsapp_klic": "WHATSAPP_KLIC", "ai_api_klic": "AI_API_KLIC", "cerebras_api_klic": "CEREBRAS_API_KLIC",
            "groq_api_klic": "GROQ_API_KLIC"}


def nacti() -> dict:
    data = dict(VYCHOZI)
    if SOUBOR.exists():
        try:
            data |= json.loads(SOUBOR.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    for klic, promenna in PROMENNE.items():  # cloud: tajné hodnoty z GitHub Secrets
        if os.environ.get(promenna):
            data[klic] = os.environ[promenna]
    if os.environ.get("GITHUB_ACTIONS"):
        return data  # v cloudu nic nezapisovat
    if not data.get("ntfy_kanal") or not SOUBOR.exists():
        # náhodný kanál: kdo název nezná, oznámení neuvidí
        data["ntfy_kanal"] = data.get("ntfy_kanal") or "hledac-plzen-" + secrets.token_hex(12)
        SOUBOR.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
