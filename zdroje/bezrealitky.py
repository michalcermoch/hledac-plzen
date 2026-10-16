"""Bezrealitky (data Next.js stránky výpisu, po okresech) - nabídky přímo od majitelů."""
import json
import re

import oblast
from .http import DETAIL_CACHE, dispozice, druh, get_text

URL = "https://www.bezrealitky.cz/vypis/nabidka-prodej/{typ}/okres-{okres}"
KATEGORIE = {"byty": "byt", "domy": "dum", "pozemky": "pozemek"}


def _apollo(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1))["props"]["pageProps"]["apolloCache"]


def _pole(a: dict, zacatek: str):
    """Klíče Apolla nesou parametry: 'address({"locale":"CS"})' -> hodnota podle začátku názvu."""
    return next((v for k, v in a.items() if k.startswith(zacatek)), None)


def _vypis(kat: str, okres: str, videno: set) -> list[dict]:
    out = []
    for strana in range(1, 40):
        url = URL.format(typ=KATEGORIE[kat], okres=oblast.slug(okres))
        cache = _apollo(get_text(url + (f"?page={strana}" if strana > 1 else "")))
        nove = 0
        for klic, a in cache.items():
            if not klic.startswith("Advert:") or a.get("offerType") != "PRODEJ" or a["id"] in videno:
                continue
            videno.add(a["id"])
            nove += 1
            adresa = _pole(a, "address") or ""
            # "Malesická, Město Touškov - Město Touškov, Plzeňský kraj" / "Plzeň - Bolevec, Plzeňský kraj"
            casti = [c.strip() for c in adresa.split(",") if not c.strip().endswith(" kraj")]
            mesto, _, cast = (casti[-1] if casti else "").partition(" - ")
            foto = cache.get((a.get("mainImage") or {}).get("__ref", ""), {}) or {}
            nazev = _pole(a, "imageAltText") or ""
            out.append({
                "id": f"bezrealitky:{a['id']}",
                "zdroj": "Bezrealitky",
                "kat": kat,
                "druh": druh(kat, nazev, a.get("landType") or ""),
                "nazev": nazev,
                "cena": a.get("price") or None,
                "plocha": (a.get("surfaceLand") or a.get("surface")) if kat == "pozemky" else a.get("surface"),
                "pozemek": a.get("surfaceLand") if kat == "domy" else None,
                "dispozice": dispozice(a.get("disposition") or "") if kat == "byty" else "",
                "mesto": mesto.strip(),
                "cast": cast.strip() if cast.strip() != mesto.strip() else "",
                "ulice": casti[0] if len(casti) > 1 else "",
                "okres": okres,
                "misto": adresa.replace(", Plzeňský kraj", ""),
                "foto": _pole(foto, "url"),
                "gps": (a["gps"]["lat"], a["gps"]["lng"]) if (a.get("gps") or {}).get("lat") else None,
                "url": f"https://www.bezrealitky.cz/nemovitosti-byty-domy/{a['uri']}",
            })
        if not nove:
            break
    return out


def hledej(kat: str) -> list[dict]:
    videno: set = set()
    return [b for okres, _ in oblast.OKRESY for b in _vypis(kat, okres, videno)]


_CISELNIK = {"OSOBNI": "osobní", "DRUZSTEVNI": "družstevní", "STATNI": "státní/obecní", "PANEL": "panelová",
             "BRICK": "cihlová", "CIHLA": "cihlová", "GOOD": "dobrý", "VERY_GOOD": "velmi dobrý", "NEW": "novostavba",
             "BAD": "špatný", "BEFORE_RECONSTRUCTION": "před rekonstrukcí", "AFTER_RECONSTRUCTION": "po rekonstrukci",
             "VYBAVENY": "vybavený", "CASTECNE": "částečně", "NEVYBAVENY": "nevybavený", "REMOTE": "dálkové",
             "LOCAL": "lokální", "GAS": "plyn", "ELECTRIC": "elektřina"}


def detail(b: dict) -> dict:
    """Fotky, popis a parametry z dat Next.js stránky inzerátu."""
    cache = _apollo(get_text(b["url"], cache_hodin=DETAIL_CACHE))
    a = cache.get(f"Advert:{b['id'].split(':')[1]}") or {}
    fotky = []
    for ref in _pole(a, "publicImages") or []:
        url = _pole(cache.get(ref.get("__ref", ""), {}), "url(")
        if url:
            fotky.append(url)
    ciselnik = lambda v: _CISELNIK.get(v, str(v).replace("_", " ").lower()) if v else None  # noqa: E731
    parametry = [("Plocha pozemku", f"{a['surfaceLand']} m²" if a.get("surfaceLand") else None),
                 ("Podlaží", f"{a['etage']}. z {a['totalFloors']}" if a.get("etage") and a.get("totalFloors") else a.get("etage")),
                 ("Vlastnictví", ciselnik(a.get("ownership"))), ("Stavba", ciselnik(a.get("construction"))),
                 ("Stav", ciselnik(a.get("condition"))), ("Energetická třída", a.get("penb")),
                 ("Výtah", "ano" if a.get("lift") else None), ("Vybavení", ciselnik(a.get("equipped"))),
                 ("Vytápění", ciselnik(a.get("heating"))), ("Poplatky", f"{a['charges']} Kč/měs." if a.get("charges") else None)]
    return {"fotky": fotky, "popis": _pole(a, "descriptionByLocale") or a.get("description") or "",
            "parametry": [(k, str(v)) for k, v in parametry if v]}
