"""Reality.cz (HTML výpis po okresech). Malý, ale souřadnice má už ve výpisu (třída gpsx49.76 gpsy13.35)."""
import re

import oblast
from .http import DETAIL_CACHE, cena, dispozice, druh, get_text, plocha, pozemek, telefon, text, text_radky

WEB = "https://www.reality.cz"
KATEGORIE = {"byty": ["byty"], "domy": ["domy"], "pozemky": ["pozemky"]}
NA_STRANKU = 25


def _vypis(kat: str, cesta: str, okres: str, videno: set) -> list[dict]:
    zaklad = f"{WEB}/prodej/{cesta}/okres-{oblast.slug_velky(okres)}/"
    out, celkem = [], None
    for strana in range(0, 80):
        html = get_text(zaklad + (f"?g={strana}-0-{celkem}" if strana else ""))
        if celkem is None:
            m = re.search(r'class="bld fsbg">(\d+)</span>', html)
            celkem = int(m.group(1)) if m else 0
        nove = 0
        for blok in re.split(r'<div class="xvypis', html)[1:]:
            m = re.search(r'href="([A-Z0-9]{3}-[A-Z0-9]{6})/', blok)
            if not m or m.group(1) in videno:
                continue
            videno.add(m.group(1))
            nove += 1
            gps = re.search(r"gpsx(\d+\.\d+) gpsy(\d+\.\d+)", blok)
            nazev_html = re.search(r'class="vypisnaz">\s*<a[^>]*>(.*?)</a>', blok, re.S)
            adresa = text(nazev_html.group(1)) if nazev_html else ""   # "Hodonínská, Plzeň 1 - Severní Předměstí"
            popis = re.search(r'class="lokalita">(.*?)</p>', blok, re.S)
            popis = text(popis.group(1)) if popis else ""               # "byt 2+kk, 46 m², panel, osobní"
            casti = [c.strip() for c in adresa.split(",")]
            mesto, _, cast = (casti[-1] if casti else "").partition(" - ")
            mesto = re.sub(r"\s+\d+$", "", mesto.strip())  # "Plzeň 1" -> "Plzeň"
            cena_html = re.search(r'class="vypiscena">(.*?)</p>', blok, re.S)
            foto = re.search(r'src="(/thumb/[^"]+\.jpg)"', blok)
            out.append({
                "id": f"realitycz:{m.group(1)}",
                "zdroj": "Reality.cz",
                "kat": kat,
                "druh": druh(kat, popis, cesta),
                "nazev": f"Prodej – {popis}" if popis else "Prodej",
                "cena": cena(text(cena_html.group(1))) if cena_html else None,
                "plocha": plocha(popis),
                "pozemek": pozemek(popis) if kat == "domy" else None,
                "dispozice": dispozice(popis) if kat == "byty" else "",
                "mesto": mesto,
                "cast": cast.strip(),
                "ulice": casti[0] if len(casti) > 1 else "",
                "okres": okres,
                "misto": adresa,
                "gps": (float(gps.group(1)), float(gps.group(2))) if gps else None,
                "foto": WEB + foto.group(1).replace("/thumb/", "/photo/") if foto else None,
                "url": zaklad + m.group(1) + "/",
            })
        if not nove or len(videno) >= celkem or (strana + 1) * NA_STRANKU >= celkem:
            break
    return out


def hledej(kat: str) -> list[dict]:
    videno: set = set()
    return [b for cesta in KATEGORIE[kat] for okres, _ in oblast.OKRESY for b in _vypis(kat, cesta, okres, videno)]


def detail(b: dict) -> dict:
    html = get_text(b["url"], cache_hodin=DETAIL_CACHE)
    popis = re.search(r'<div id="poznext">(.*?)</div>\s*</div>', html, re.S)
    fotky = [WEB + f for f in dict.fromkeys(re.findall(r'href="(/photo/\d+/[^"]+\.jpg)"', html))]
    vynechat = ("Kraj", "Okres", "Obec", "Část obce", "Ulice")
    parametry = [(text(k).rstrip(":"), text(v)) for k, v in re.findall(r"<th>([^<]+)</th>\s*<td>(.*?)</td>", html, re.S)]
    parametry = [(k, v) for k, v in parametry if v and k not in vynechat]
    vysledek = {"telefon": telefon(html), "fotky": fotky, "popis": text_radky(popis.group(1)) if popis else "",
                "parametry": parametry}
    if b["kat"] == "domy" and not b.get("pozemek"):
        vysledek["pozemek"] = next((plocha(v) for k, v in parametry if "pozem" in k.lower()), None)
    return vysledek
