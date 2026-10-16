"""Bazoš (HTML výpis, okruh kolem PSČ) - hodně inzerátů od majitelů, ale bez adresy a souřadnic.

Bazoš hledá sám okruhem (humkreis) kolem PSČ, takže všechno ve výpisu je zhruba v okruhu. U inzerátu je
jen „obec nebo okres + PSČ“ - poloha se pak odhadne podle PSČ (OpenStreetMap), přesná adresa bývá jen v textu.
"""
import re

import oblast
from .http import DETAIL_CACHE, bez_diakritiky, cena, dispozice, druh, get_text, plocha, pozemek, text, text_radky

WEB = "https://reality.bazos.cz"
KATEGORIE = {"byty": ["byt"], "domy": ["dum"], "pozemky": ["pozemek", "zahrada"]}
PO = 20


def _vypis(kat: str, cesta: str, videno: set) -> list[dict]:
    out = []
    for strana in range(60):
        html = get_text(f"{WEB}/prodam/{cesta}/{f'{strana * PO}/' if strana else ''}"
                        f"?hlokalita={oblast.PSC}&humkreis={oblast.OKRUH_KM}")
        nove = 0
        for blok in html.split('<div class="inzeraty inzeratyflex">')[1:]:
            m = re.search(r'<h2 class=nadpis><a href="(/inzerat/(\d+)/[^"]+)">(.*?)</a>', blok, re.S)
            if not m or m.group(2) in videno:
                continue
            videno.add(m.group(2))
            nove += 1
            nadpis = text(m.group(3))
            if re.match(r"(koup|hledam|popt|shanim)", bez_diakritiky(nadpis)):
                continue  # poptávka, ne nabídka
            popis = re.search(r"<div class=popis>(.*?)</div>", blok, re.S)
            popis = text(popis.group(1)) if popis else ""
            lok = re.search(r'inzeratylok">(.*?)<br>(.*?)</div>', blok, re.S)
            misto, psc = (text(lok.group(1)), text(lok.group(2))) if lok else ("", "")
            okres = next((o for o, _ in oblast.OKRESY if o == misto), "")
            foto = re.search(r'<img src="([^"]+)" class="obrazek"', blok)
            out.append({
                "id": f"bazos:{m.group(2)}",
                "zdroj": "Bazoš",
                "kat": kat,
                "druh": druh(kat, nadpis, popis[:200], cesta),
                "nazev": nadpis,
                "cena": cena(text(re.search(r'inzeratycena">(.*?)</div>', blok, re.S).group(1))),
                "plocha": plocha(nadpis) or plocha(popis),
                "pozemek": (pozemek(nadpis) or pozemek(popis)) if kat == "domy" else None,
                "dispozice": (dispozice(nadpis) or dispozice(popis)) if kat == "byty" else "",
                "mesto": "" if okres else misto,   # "Plzeň-sever" je okres, ne obec
                "cast": "",
                "ulice": "",
                "okres": okres,
                "psc": psc.replace(" ", ""),
                "text": f"{nadpis} {popis}",
                "misto": f"{misto} {psc}".strip(),
                "foto": foto.group(1).replace("/img/1t/", "/img/1/") if foto else None,  # 1t = malý náhled
                "url": WEB + m.group(1),
            })
        if not nove or ("Další</a>" not in html and "Další</b>" not in html):
            break
    return out


def hledej(kat: str) -> list[dict]:
    videno: set = set()
    return [b for cesta in KATEGORIE[kat] for b in _vypis(kat, cesta, videno)]


def detail(b: dict) -> dict:
    stranka = get_text(b["url"], cache_hodin=DETAIL_CACHE)
    popis = re.search(r"<div class=popisdetail>(.*?)</div>", stranka, re.S)
    # Fotky jsou očíslované: /img/1/..., /img/2/...; "1t" je malý náhled.
    cisla = {int(n): u for u, n in re.findall(r"(https://www\.bazos\.cz/img/(\d+)/\d+/\d+\.jpg[^\"' ]*)", stranka)}
    vysledek = {"fotky": [cisla[n] for n in sorted(cisla)], "popis": text_radky(popis.group(1)) if popis else ""}
    if popis:
        vysledek["text"] = f"{b['nazev']} {text(popis.group(1))}"
        if b["kat"] == "domy" and not b.get("pozemek"):
            vysledek["pozemek"] = pozemek(vysledek["text"])
    return vysledek
