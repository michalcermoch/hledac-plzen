"""RealityMix (HTML výpis po okresech)."""
import re
import urllib.error

import oblast
from .http import (DETAIL_CACHE, cena, dispozice, druh, get_text, okres_z_textu, plocha, telefon, text,
                   text_radky)

URL = "https://realitymix.cz/reality/{typ}/prodej/{kraj}/{okres}"
KATEGORIE = {"byty": "byty", "domy": "domy", "pozemky": "pozemky"}


def _vypis(kat: str, okres: str, kraj: str, videno: set) -> list[dict]:
    out = []
    url = URL.format(typ=KATEGORIE[kat], kraj=oblast.slug(kraj).removesuffix("-kraj"), okres=oblast.slug(okres))
    for strana in range(1, 80):
        try:
            html = get_text(url + (f"?stranka={strana}" if strana > 1 else ""))
        except urllib.error.HTTPError as e:
            if e.code == 404:  # za poslední stránkou
                break
            raise
        nove = 0
        for li in html.split('<li class="w-full advert-item"')[1:]:
            h2 = re.search(r'<h2[^>]*>\s*<a href="([^"]+-(\d+)\.html)"[^>]*>(.*?)</a>\s*</h2>\s*<p[^>]*>(.*?)</p>', li, re.S)
            if not h2 or h2.group(2) in videno:
                continue
            videno.add(h2.group(2))
            nove += 1
            nadpis, adresa = text(h2.group(3)), text(h2.group(4))
            # "Plzeň 2-Slovany, Plzeň, okr. Plzeň-město" / "Chotíkov, okr. Plzeň-sever"
            casti = [c.strip() for c in adresa.split(",") if not c.strip().startswith("okr.")]
            cena_html = re.search(r'class="text-xl font-extrabold[^>]*>(.*?)</div>', li, re.S)
            foto = re.search(r'<img[^>]+src="([^"]+nab_[^"]+)"', li)
            parcela = re.search(r'alt="Plocha parcely"[^>]*/>\s*<span>(.*?)</span>', li, re.S)
            parcela = plocha(text(parcela.group(1))) if parcela else None
            out.append({
                "id": f"realitymix:{h2.group(2)}",
                "zdroj": "RealityMix",
                "kat": kat,
                "druh": druh(kat, nadpis, h2.group(1).rsplit("/", 1)[-1].replace("-", " ")),
                "nazev": nadpis,
                "cena": cena(text(cena_html.group(1))) if cena_html else None,
                "plocha": (plocha(nadpis) or parcela) if kat == "pozemky" else plocha(nadpis),
                "pozemek": parcela if kat == "domy" else None,
                "dispozice": dispozice(nadpis) if kat == "byty" else "",
                "mesto": casti[-1].split(" - ")[0] if casti else "",
                "cast": casti[0] if len(casti) > 1 else "",
                "ulice": "",
                "okres": okres_z_textu(adresa) or okres,
                "misto": ", ".join(casti),
                "foto": foto.group(1).replace("http://", "https://") if foto else None,
                "url": h2.group(1),
            })
        if not nove:
            break
    return out


def hledej(kat: str) -> list[dict]:
    videno: set = set()
    return [b for okres, kraj in oblast.OKRESY for b in _vypis(kat, okres, kraj, videno)]


def detail(b: dict) -> dict:
    """Fotky (st.realitymix.cz/i/<realitka>/<id>/nab_<n>.jpg), popis, parametry a poloha z detailu."""
    html = get_text(b["url"], cache_hodin=DETAIL_CACHE)
    cislo = b["id"].split(":")[1]
    fotky = list(dict.fromkeys(f"https://st.realitymix.cz/i/{rk}/{cislo}/nab_{n}.jpg" for rk, n in
                               re.findall(rf"//st\.realitymix\.cz/i/(\d+)/{cislo}/nab_(\d+)", html)))
    popis = re.search(r'<div[^>]+(?:advert-description|description)[^>]*>(.*?)</div>', html, re.S)
    popis = text_radky(popis.group(1)) if popis else ""
    if "|" in popis.split("\n", 1)[0]:  # první řádek je nadpis s adresou
        popis = popis.split("\n", 1)[1].strip() if "\n" in popis else ""
    parametry = [(text(k).rstrip(":"), text(v)) for k, v in re.findall(
        r"<li[^>]*>\s*<span[^>]*>([^<]{2,60})</span>\s*<(?:span|strong)[^>]*>(.*?)</(?:span|strong)>", html, re.S)]
    lat = re.search(r'data-gps-lat="(\d{2}\.\d+)"', html)
    lon = re.search(r'data-gps-lon="(\d{1,2}\.\d+)"', html)
    vysledek = {"telefon": telefon(html), "fotky": fotky, "popis": popis,
                "parametry": [(k, v) for k, v in parametry if v and not k.startswith("Energetický ukazatel")],
                "gps": (float(lat.group(1)), float(lon.group(1))) if lat and lon else None}
    if b["kat"] == "domy" and not b.get("pozemek"):
        vysledek["pozemek"] = next((plocha(v) for k, v in vysledek["parametry"] if "pozem" in k.lower()
                                    or "parcel" in k.lower()), None)
    return vysledek
