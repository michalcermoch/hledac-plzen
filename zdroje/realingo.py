"""Realingo.cz - vyhledávač, který sbírá nabídky z celého internetu (i z webů realitek).

Většinu inzerátů má i jinde (iDNES, Bazoš, ČeskéReality...), ty se sloučí jako duplicity; přidá ale to,
co jinde nemáme. Výpis je Next.js: data v __NEXT_DATA__ (props.pageProps.store.offer.list), 40 na
stránku, stránky /N_strana/, po okresech (/prodej_domy/Okres_Plzeň-jih/). Část nabídek je „zamčená“
(jen pro přihlášené, bez údajů) - ty se přeskočí. Detail má popis, parametry a odkaz na původní inzerát.
"""
import json
import re
import urllib.parse

import oblast
from .http import DETAIL_CACHE, druh, get_text

WEB = "https://www.realingo.cz"
KATEGORIE = {"byty": ("byty", "FLAT"), "domy": ("domy", "HOUSE"), "pozemky": ("pozemky", "LAND")}
FOTO = WEB + "/static/images/"
DISPOZICE = {"FLAT11": "1+1", "FLAT21": "2+1", "FLAT31": "3+1", "FLAT41": "4+1", "FLAT51": "5+1", "FLAT1_KK": "1+kk",
             "FLAT2_KK": "2+kk", "FLAT3_KK": "3+kk", "FLAT4_KK": "4+kk", "FLAT5_KK": "5+kk"}
# kategorie Realinga -> česky, ať ji pochopí jednotné druhy (zdroje.http.druh)
SLOVA = {"FAMILY": "rodinný", "VILLA": "vila", "COTTAGE": "chalupa", "HUT": "chata", "FARM": "usedlost",
         "HOUSING": "bydlení", "BUILDING": "stavební", "GARDEN": "zahrada", "COMMERCIAL": "komerční", "FIELD": "pole",
         "MEADOW": "louka", "FOREST": "les", "ORCHARD": "sad", "POND": "rybník", "WATER": "rybník"}
MAX_FOTEK = 30
PARAMETRY = {
    "ownership": ("Vlastnictví", {"PERSONAL": "osobní", "PRIVATE": "osobní", "COLLECTIVE": "družstevní",
                                  "STATE": "obecní"}),
    "buildingType": ("Stavba", {"PANEL": "panelová", "BRICK": "cihlová", "WOOD": "dřevostavba", "SKELETON": "skeletová"}),
    "buildingStatus": ("Stav", {"VERY_GOOD": "velmi dobrý", "GOOD": "dobrý", "BAD": "špatný", "NEW": "novostavba",
                                "AFTER_RECONSTRUCTION": "po rekonstrukci", "BEFORE_RECONSTRUCTION": "před rekonstrukcí",
                                "IN_RECONSTRUCTION": "v rekonstrukci"}),
    "furniture": ("Vybavení", {"NO": "nevybaveno", "YES": "vybaveno", "PARTIAL": "částečně"}),
    "energyPerformance": ("Energetická třída", {}),  # "D_LESS_EFFICIENT" -> "D" níž
}


def _next_data(stranka: str) -> dict:
    return json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', stranka, re.S).group(1))


def _inzerat(x: dict, kat: str, okres: str) -> dict:
    lo = x.get("location") or {}
    adresa = lo.get("address") or ""
    # "Hodonínská, Plzeň - Severní Předměstí" / "Chotíkov"
    casti = [c.strip() for c in adresa.split(",")]
    mesto, _, cast = (casti[-1] if casti else "").partition(" - ")
    kategorie = x.get("category") or ""
    plocha = (x.get("area") or {}).get("main")
    plot = (x.get("area") or {}).get("plot")
    fotky = [FOTO + f for f in ([(x.get("photos") or {}).get("main")] + ((x.get("photos") or {}).get("list") or [])) if f]
    fotky = list(dict.fromkeys(fotky))[:MAX_FOTEK]
    cena = (x.get("price") or {}).get("total")
    popis_kat = " ".join(SLOVA.get(s, "") for s in kategorie.split("_"))
    disp = DISPOZICE.get(kategorie, "")
    nazev = {"byty": f"Prodej bytu {disp}", "domy": "Prodej domu", "pozemky": "Prodej pozemku"}[kat]
    return {
        "id": f"realingo:{x['id']}",
        "zdroj": "Realingo",
        "kat": kat,
        "druh": druh(kat, popis_kat, (x.get("url") or "").rstrip("/").rsplit("/", 2)[-2].replace("-", " ")),
        "nazev": f"{nazev} {f'{plocha or plot} m²' if plocha or plot else ''}".replace("  ", " ").strip(),
        "cena": cena if cena and cena > 1000 else None,  # "1 Kč" = cena na dotaz
        "plocha": (plot or plocha) if kat == "pozemky" else plocha,
        "pozemek": plot if kat == "domy" else None,
        "dispozice": disp,
        "mesto": mesto.strip(),
        "cast": cast.strip(),
        "ulice": casti[0] if len(casti) > 1 else "",
        "okres": okres,
        "misto": adresa,
        "gps": (lo["latitude"], lo["longitude"]) if lo.get("latitude") and lo.get("locationPrecision") in ("EXACT", "STREET") else None,
        "foto": fotky[0] if fotky else None,
        "fotky": fotky,
        # createdAt = kdy ho Realingo našel, ne kdy vznikl původní inzerát -> "vloženo" se neuvádí
        "url": WEB + x["url"],
    }


def hledej(kat: str) -> list[dict]:
    cesta, typ = KATEGORIE[kat]
    out, videno = [], set()
    for okres, _ in oblast.OKRESY:
        vypis = f"{WEB}/prodej_{cesta}/{urllib.parse.quote('Okres_' + okres)}/"
        for strana in range(1, 60):
            seznam = _next_data(get_text(vypis + (f"{strana}_strana/" if strana > 1 else "")))
            seznam = seznam["props"]["pageProps"]["store"]["offer"]["list"]
            data = seznam.get("data") or []
            nove = [x for x in data if x["id"] not in videno]
            if not nove:
                break
            videno |= {x["id"] for x in nove}
            out += [_inzerat(x, kat, okres) for x in nove
                    if x.get("purpose") == "SELL" and x.get("property") == typ and x.get("url") and not x.get("isLocked")]
            if strana * 40 >= seznam.get("total", 0):
                break
    return out


def _najdi_detail(o):
    if isinstance(o, dict):
        if isinstance(o.get("detail"), dict) and "description" in o["detail"]:
            return o["detail"]
        o = list(o.values())
    if isinstance(o, list):
        for x in o:
            r = _najdi_detail(x)
            if r:
                return r
    return None


def detail(b: dict) -> dict:
    d = _najdi_detail(_next_data(get_text(b["url"], cache_hodin=DETAIL_CACHE))) or {}
    parametry = [(popisek, preklad.get(d[k], d[k].split("_")[0] if k == "energyPerformance" else d[k].lower())
                  if isinstance(d[k], str) else str(d[k]))
                 for k, (popisek, preklad) in PARAMETRY.items() if d.get(k)]
    if d.get("floor") is not None:
        parametry.append(("Podlaží", f"{d['floor']}." + (f" z {d['floorTotal']}" if d.get("floorTotal") else "")))
    if d.get("externalUrl"):
        parametry.append(("Původní inzerát", d["externalUrl"]))
    return {"popis": (d.get("description") or "").strip(), "parametry": parametry}
