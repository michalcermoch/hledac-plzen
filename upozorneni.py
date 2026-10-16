"""Upozornění na telefon o nových a zlevněných nemovitostech - obojí zdarma:

  ntfy (https://ntfy.sh)  push do aplikace ntfy, bez účtu a hesla; kanál z nastaveni.json (náhodný dlouhý
                          název, ať ho nikdo neuhodne) - v aplikaci ho stačí odebírat. Každá novinka zvlášť
                          i s fotkou, klepnutím se otevře inzerát.
  WhatsApp (CallMeBot)    jedna souhrnná zpráva na běh; jen když je v nastavení telefon a apikey (klíč si
                          majitel čísla jednou vyžádá zprávou botovi, návod v README).
"""
import base64
import urllib.parse
import urllib.request

import nastaveni

SERVER = "https://ntfy.sh/"
MAX_JEDNOTLIVE = 6  # víc novinek najednou -> zbytek jen souhrnem
TAGY = {"byty": "house", "domy": "house_with_garden", "pozemky": "deciduous_tree"}


def _kc(n) -> str:
    return f"{int(n):,}".replace(",", " ") + " Kč" if n else "cena na dotaz"


def vyber(sekce: list[tuple]) -> list[tuple[str, dict, str]]:
    """[(kategorie, inzerát, důvod)] - co stojí za upozornění: zlevnění první, pak nové."""
    out = []
    for s in sekce:
        kat, inz = s[0], s[1]
        for i in inz:
            if i.get("zlevneno_ted"):
                out.append((kat, i, "zlevnilo"))
            elif i.get("novy"):
                out.append((kat, i, "nové"))
    return sorted(out, key=lambda x: x[2] != "zlevnilo")


def _hlavicka(text: str) -> str:
    """HTTP hlavičky musí být latin-1; ntfy umí RFC 2047 (=?UTF-8?B?...?=) pro češtinu."""
    return "=?UTF-8?B?" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "?="


def posli(kanal: str, titulek: str, zprava: str, odkaz: str | None = None, obrazek: str | None = None,
          tagy: str = "", priorita: str = "default") -> None:
    hlavicky = {"Title": _hlavicka(titulek), "Priority": priorita}
    if tagy:
        hlavicky["Tags"] = tagy
    if odkaz:
        hlavicky["Click"] = odkaz
    if obrazek:
        hlavicky["Attach"] = obrazek
    req = urllib.request.Request(SERVER + kanal, data=zprava.encode("utf-8"), headers=hlavicky, method="POST")
    with urllib.request.urlopen(req, timeout=30):
        pass


def _udaje(i: dict) -> str:
    vel = f"{i['plocha']:,} m²".replace(",", " ") if i.get("plocha") else ""
    poz = f"pozemek {i['pozemek']:,} m²".replace(",", " ") if i.get("pozemek") else ""
    km = f"{i['vzdalenost'] / 1000:.1f} km od centra".replace(".", ",") if i.get("vzdalenost") is not None else ""
    return " · ".join(x for x in (i.get("druh"), i.get("dispozice"), vel, poz, km) if x)


def whatsapp(polozky: list[tuple], odkaz_prehled: str | None, log=print) -> None:
    """Jedna zpráva přes CallMeBot: až 6 novinek s odkazy, zbytek počtem."""
    nast = nastaveni.nacti()
    if not (nast.get("whatsapp_telefon") and nast.get("whatsapp_klic")) or not polozky:
        return
    if len(polozky) > 100:  # první běh
        radky = [f"🏡 Hledač: {len(polozky)} nemovitostí v nabídce. Odteď sem budou chodit jen nové a zlevněné."]
    else:
        radky = [f"🏡 Hledač: {len(polozky)} {'novinka' if len(polozky) == 1 else 'novinky' if len(polozky) < 5 else 'novinek'}"]
        for kat, i, duvod in polozky[:MAX_JEDNOTLIVE]:
            radky.append(f"\n{'📉 Zlevnilo' if duvod == 'zlevnilo' else '🆕 Nové'}: {_kc(i.get('cena'))}\n"
                         f"{i['nazev']}\n{_udaje(i)}\n{i.get('misto') or ''}\n{i['url']}")
        if len(polozky) > MAX_JEDNOTLIVE:
            radky.append(f"\n… a dalších {len(polozky) - MAX_JEDNOTLIVE}")
    if odkaz_prehled:
        radky.append(f"\nPřehled: {odkaz_prehled}")
    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
        {"phone": nast["whatsapp_telefon"], "text": "\n".join(radky)[:3500], "apikey": nast["whatsapp_klic"]})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "HledacPlzen/1.0"}), timeout=60):
            pass
        log("upozornění: zpráva odeslána na WhatsApp")
    except Exception as e:  # upozornění nesmí shodit aktualizaci
        log(f"upozornění: WhatsApp se nepodařil ({type(e).__name__})")


def odesli(sekce: list[tuple], odkaz_prehled: str | None, log=print) -> None:
    kanal = nastaveni.nacti().get("ntfy_kanal")
    polozky = vyber(sekce)
    if not polozky:
        log("upozornění: nic nového")
        return
    whatsapp(polozky, odkaz_prehled, log)
    if not kanal:
        return
    try:
        if len(polozky) > 100:  # první běh (všechno je nové) - jen jedno souhrnné oznámení
            posli(kanal, f"Hledač: {len(polozky)} nemovitostí v nabídce",
                  "Odteď ti sem budou chodit jen nové a zlevněné. Přehled otevřeš klepnutím.", odkaz=odkaz_prehled, tagy="mag")
            log("upozornění: souhrn odeslán na ntfy (první běh)")
            return
        for kat, i, duvod in polozky[:MAX_JEDNOTLIVE]:
            pred = ""
            if duvod == "zlevnilo" and len(i.get("historie_cen") or []) >= 2:
                pred = f" (dřív {_kc(i['historie_cen'][-2][1])})"
            foto = (i.get("fotky") or [i.get("foto")] or [None])[0]
            misto = ", ".join(x for x in (i.get("misto"), i.get("okres") and f"okres {i['okres']}") if x)
            ai = (i.get("ai") or {})
            ai = f"\n⚠ AI: {ai['varovani']}" if ai.get("varovani") else f"\nAI: {ai['shrnuti']}" if ai.get("shrnuti") else ""
            posli(kanal, f"{'Zlevnilo' if duvod == 'zlevnilo' else 'Nové'}: {_kc(i.get('cena'))}{pred}",
                  f"{i['nazev']}\n{_udaje(i)}\n{misto}{ai}", odkaz=i["url"], obrazek=foto,
                  tagy="chart_with_downwards_trend" if duvod == "zlevnilo" else TAGY.get(kat, "house"),
                  priorita="high" if duvod == "zlevnilo" else "default")
        if len(polozky) > MAX_JEDNOTLIVE:
            posli(kanal, f"Hledač: a dalších {len(polozky) - MAX_JEDNOTLIVE} novinek",
                  "Celý přehled otevřeš klepnutím.", odkaz=odkaz_prehled, tagy="mag")
        log(f"upozornění: {min(len(polozky), MAX_JEDNOTLIVE)} oznámení odesláno na ntfy")
    except Exception as e:  # upozornění nesmí shodit aktualizaci
        log(f"upozornění: ntfy se nepodařilo ({e})")
