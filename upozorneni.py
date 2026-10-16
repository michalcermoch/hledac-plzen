"""Denní souhrn na telefon - jen z cloudu, jednou denně kolem 20:00 (hledac.py --cloud, viz SOUHRN_HODINY).

V souhrnu je všechno, co od minulého souhrnu přibylo nebo zlevnilo (všechny kategorie, v rámci pevných filtrů).
Když nic nepřibylo, nic se neposílá. Obojí zdarma:
  ntfy (https://ntfy.sh)  jedna zpráva do aplikace ntfy, bez účtu a hesla; kanál z nastavení (náhodný dlouhý
                          název, ať ho nikdo neuhodne). Klepnutím se otevře přehled.
  WhatsApp (CallMeBot)    stejný souhrn i s odkazy na inzeráty; jen když je v nastavení telefon a apikey (klíč si
                          majitel čísla jednou vyžádá zprávou botovi, návod v README).
"""
import base64
import urllib.parse
import urllib.request

import nastaveni

NTFY = "https://ntfy.sh/"
NA_KATEGORII = 8          # kolik inzerátů z každé kategorie vypsat; zbytek jen počtem
TITULY = {"byty": "🏢 Byty", "domy": "🏡 Rodinné domy", "pozemky": "🌳 Pozemky"}


def _kc(n) -> str:
    return f"{int(n):,}".replace(",", " ") + " Kč" if n else "cena na dotaz"


def _m2(n) -> str:
    return f"{int(n):,} m²".replace(",", " ")


def _cena_tehdy(i: dict, od: str):
    """Cena platná v okamžiku minulého souhrnu (historie_cen = [(čas, cena)] od prvního vidění)."""
    ceny = [c for cas, c in i.get("historie_cen") or [] if cas <= od]
    return ceny[-1] if ceny else None


def vyber(sekce: list[tuple], od: str) -> dict[str, list[tuple[dict, str]]]:
    """{kategorie: [(inzerát, 'nové' / 'zlevnilo')]} - co přibylo nebo zlevnilo od času `od` (ISO)."""
    out = {}
    for s in sekce:
        kat, inz = s[0], s[1]
        polozky = []
        for i in inz:
            if (i.get("prvni_videno") or "") > od:
                polozky.append((i, "nové"))
            elif i.get("cena") and (_cena_tehdy(i, od) or 0) > i["cena"]:
                polozky.append((i, "zlevnilo"))
        if polozky:  # zlevněné první, pak od nejlevnějšího
            out[kat] = sorted(polozky, key=lambda x: (x[1] != "zlevnilo", x[0].get("cena") or 10 ** 12))
    return out


def _radek(kat: str, i: dict, duvod: str, od: str) -> str:
    cena = _kc(i.get("cena"))
    if duvod == "zlevnilo":
        cena = f"↓ {cena} (dřív {_kc(_cena_tehdy(i, od))})"
    casti = [cena, i.get("dispozice") if kat == "byty" else i.get("druh"),
             _m2(i["plocha"]) if i.get("plocha") else "", f"pozemek {_m2(i['pozemek'])}" if i.get("pozemek") else "",
             i.get("mesto") or i.get("misto") or ""]
    return " · ".join(x for x in casti if x)


def text(polozky: dict, od: str, odkazy: bool) -> tuple[str, str]:
    """(nadpis, text) souhrnu; odkazy=True přidá ke každému inzerátu adresu (WhatsApp)."""
    nove = sum(1 for p in polozky.values() for _, d in p if d == "nové")
    zlev = sum(1 for p in polozky.values() for _, d in p if d == "zlevnilo")
    nadpis = "Hledač: " + ", ".join(x for x in (
        f"{nove} {'nová nemovitost' if nove == 1 else 'nové nemovitosti' if nove < 5 else 'nových nemovitostí'}" if nove else "",
        f"{zlev} {'zlevněná' if zlev == 1 else 'zlevněné' if zlev < 5 else 'zlevněných'}" if zlev else "") if x)
    bloky = []
    for kat, seznam in polozky.items():
        radky = [f"{TITULY.get(kat, kat)} ({len(seznam)})"]
        for i, duvod in seznam[:NA_KATEGORII]:
            radky.append(f"• {_radek(kat, i, duvod, od)}" + (f"\n  {i['url']}" if odkazy else ""))
        if len(seznam) > NA_KATEGORII:
            radky.append(f"  … a dalších {len(seznam) - NA_KATEGORII} v přehledu")
        bloky.append("\n".join(radky))
    return nadpis, "\n\n".join(bloky)


def _hlavicka(t: str) -> str:
    """HTTP hlavičky musí být latin-1; ntfy umí RFC 2047 (=?UTF-8?B?...?=) pro češtinu."""
    return "=?UTF-8?B?" + base64.b64encode(t.encode("utf-8")).decode("ascii") + "?="


def _ntfy(kanal: str, nadpis: str, zprava: str, odkaz: str | None):
    hlavicky = {"Title": _hlavicka(nadpis), "Tags": "house", "Priority": "default"}
    if odkaz:
        hlavicky["Click"] = odkaz
    req = urllib.request.Request(NTFY + kanal, data=zprava[:3900].encode("utf-8"), headers=hlavicky, method="POST")
    with urllib.request.urlopen(req, timeout=30):
        pass


def _whatsapp(telefon: str, klic: str, zprava: str):
    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
        {"phone": telefon, "text": zprava[:3500], "apikey": klic})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "HledacPlzen/1.0"}), timeout=60):
        pass


def denni_souhrn(sekce: list[tuple], od: str, odkaz_prehled: str | None, log=print) -> bool:
    """Pošle souhrn všeho od času `od` na ntfy a WhatsApp (co je nastavené). Vrací True, když se aspoň jeden
    kanál podařil nebo nebylo co poslat (pak se další souhrn počítá od teď)."""
    nast = nastaveni.nacti()
    polozky = vyber(sekce, od)
    if not polozky:
        log("souhrn: od minula nic nového")
        return True
    nadpis, telo = text(polozky, od, odkazy=False)
    povedlo = False
    if nast.get("ntfy_kanal"):
        try:
            _ntfy(nast["ntfy_kanal"], nadpis, telo, odkaz_prehled)
            povedlo = True
            log("souhrn: odeslán na ntfy")
        except Exception as e:  # upozornění nesmí shodit běh
            log(f"souhrn: ntfy se nepodařil ({type(e).__name__})")
    if nast.get("whatsapp_telefon") and nast.get("whatsapp_klic"):
        zprava = "\n\n".join(text(polozky, od, odkazy=True)) + (f"\n\nPřehled: {odkaz_prehled}" if odkaz_prehled else "")
        try:
            _whatsapp(nast["whatsapp_telefon"], nast["whatsapp_klic"], zprava)
            povedlo = True
            log("souhrn: odeslán na WhatsApp")
        except Exception as e:
            log(f"souhrn: WhatsApp se nepodařil ({type(e).__name__})")
    return povedlo
