"""ČeskéReality.cz (HTML výpis po okresech) - portál realitních kanceláří; část nabídek jinde není.

Výpis: karty <article class="i-estate"> s titulkem "Prodej rodinného domu 132 m² Nezvěstice" a cenou,
stránkování ?strana=N. Detail má popis v ld+json, fotky na img-cache.ceskereality.cz, parametry jako
dvojice řádků a souřadnice.
"""
import html as html_mod
import json
import re
import urllib.error

import oblast
from .http import DETAIL_CACHE, cena, dispozice, druh, get_text, plocha, pozemek, telefon, text

WEB = "https://www.ceskereality.cz"
KATEGORIE = {"byty": ["byty"], "domy": ["rodinne-domy"], "pozemky": ["pozemky"]}


def _karta(a: str, kat: str, okres: str) -> dict | None:
    odkaz = re.search(r'<a href="(/prodej/[^"]+-(\d+)\.html)"', a)
    titulek = re.search(r'class="i-estate__header-title[^"]*"[^>]*>(.*?)</h2>', a, re.S)
    if not odkaz or not titulek:
        return None
    nadpis = text(titulek.group(1))  # "Prodej bytu 2+1 54 m² Plzeň, Hodonínská"
    misto = re.sub(r"^.*m²\s*", "", nadpis) if "m²" in nadpis else ""
    mesto, _, ulice = (x.strip() for x in misto.partition(","))
    mesto, _, cast = mesto.partition(" - ")
    cena_html = re.search(r'class="i-estate__footer-price-value[^"]*"[^>]*>(.*?)</', a, re.S)
    foto = re.search(r'src="(https://img-cache\.ceskereality\.cz/nemovitosti/320x320_jpg/[^"]+)"', a)
    nazev = nadpis[:len(nadpis) - len(misto)].strip() if misto else nadpis
    return {
        "id": f"ceskereality:{odkaz.group(2)}",
        "zdroj": "ČeskéReality",
        "kat": kat,
        "druh": druh(kat, nazev, odkaz.group(1)),
        "nazev": nazev,
        "cena": cena(text(cena_html.group(1))) if cena_html else None,
        "plocha": plocha(nazev),
        "pozemek": pozemek(nazev) if kat == "domy" else None,
        "dispozice": dispozice(nazev) if kat == "byty" else "",
        "mesto": mesto.strip(),
        "cast": cast.strip(),
        "ulice": ulice,
        "okres": okres,  # karta okres neuvádí; doporučené nabídky bývají i z vedlejšího okresu (opraví se podle obce)
        "misto": misto,
        "foto": foto.group(1).replace("320x320_jpg", "1336x891_jpg") if foto else None,
        "url": WEB + odkaz.group(1),
    }


def hledej(kat: str) -> list[dict]:
    out, videno = [], set()
    for cesta in KATEGORIE[kat]:
        for okres, _ in oblast.OKRESY:
            vypis = f"{WEB}/prodej/{cesta}/{oblast.slug(okres)}/"
            for strana in range(1, 80):
                try:
                    stranka = get_text(vypis + (f"?strana={strana}" if strana > 1 else ""))
                except urllib.error.HTTPError as e:
                    if e.code == 404:  # za poslední stránkou
                        break
                    raise
                karty = [k for k in (_karta(a.split("</article>")[0], kat, okres)
                                     for a in stranka.split('<article class="i-estate"')[1:]) if k]
                nove = [k for k in karty if k["id"] not in videno]
                if not nove:
                    break
                videno |= {k["id"] for k in nove}
                out += nove
    return out


def detail(b: dict) -> dict:
    stranka = get_text(b["url"], cache_hodin=DETAIL_CACHE)
    popis = ""
    for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', stranka, re.S):
        try:
            j = json.loads(m)
        except ValueError:
            continue
        if isinstance(j, dict) and j.get("description"):
            popis = re.sub(r"\n{3,}", "\n\n", j["description"].replace("\r", "")).strip()
    # galerie je v náhledech 320x320; stejná fotka jde i ve velikosti 1336x891
    fotky = [f"https://img-cache.ceskereality.cz/nemovitosti/1336x891_jpg/{k}.jpg" for k in dict.fromkeys(
        re.findall(r"img-cache\.ceskereality\.cz/nemovitosti/(?:320x320|1336x891)_jpg/(\d+/\w+/\w+)\.jpg", stranka))]
    # Parametry: v textu stránky řádky "Popisek" / "hodnota" mezi "Základní informace" a "Popis nemovitosti".
    telo = re.sub(r"<script.*?</script>|<style.*?</style>", "", stranka, flags=re.S)
    radky = [r.strip() for r in html_mod.unescape(re.sub(r"<[^>]+>", "\n", telo)).split("\n") if r.strip()]
    parametry = []
    if "Základní informace" in radky:
        i = radky.index("Základní informace") + 1
        konec = radky.index("Popis nemovitosti", i) if "Popis nemovitosti" in radky[i:] else i + 30
        blok = [r for r in radky[i:konec] if r != "Spočítat hypotéku"]
        parametry = [(blok[n], blok[n + 1]) for n in range(0, len(blok) - 1, 2)
                     if blok[n] not in ("ID nemovitosti", "Cena")]
    lat = re.search(r'lat(?:itude)?["\']?\s*[:=]\s*["\']?(\d{2}\.\d+)', stranka)
    lng = re.search(r'(?:lng|lon|longitude)["\']?\s*[:=]\s*["\']?(\d{1,2}\.\d+)', stranka)
    vysledek = {"telefon": telefon(stranka), "fotky": fotky, "popis": popis, "parametry": parametry,
                "gps": (float(lat.group(1)), float(lng.group(1))) if lat and lng else None}
    if b["kat"] == "domy" and not b.get("pozemek"):
        vysledek["pozemek"] = next((plocha(v) for k, v in parametry if "pozem" in k.lower()), None)
    return vysledek
