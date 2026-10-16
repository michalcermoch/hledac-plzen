"""iDnes Reality (HTML výpis po okresech)."""
import re
from html import unescape

import oblast
from .http import (DETAIL_CACHE, cena, dispozice, druh, get_text, okres_z_textu, plocha, pozemek, telefon, text,
                   text_radky)

WEB = "https://reality.idnes.cz/s/prodej/"
KATEGORIE = {"byty": ["byty"], "domy": ["domy"], "pozemky": ["pozemky"]}  # domy zahrnují i chaty a chalupy


def _vypis(kat: str, cesta: str, okres: str, videno: set) -> list[dict]:
    out = []
    for strana in range(80):
        html = get_text(f"{WEB}{cesta}/{oblast.slug(okres)}/" + (f"?page={strana}" if strana else ""))
        nove = 0
        for a in html.split("<article")[1:]:
            m = re.search(r'href="(https://reality\.idnes\.cz/detail/[^"]+/([0-9a-f]{24})/)"', a)
            if not m or m.group(2) in videno:
                continue
            videno.add(m.group(2))
            nove += 1
            nadpis = text(re.search(r'c-products__title">(.*?)</h2>', a, re.S).group(1))
            info = text(re.search(r'c-products__info">(.*?)</p>', a, re.S).group(1))
            # "Neurazy, okres Plzeň-jih" / "Hodonínská, Plzeň - Severní Předměstí"
            casti = [c.strip() for c in info.split(",") if not c.strip().startswith("okres")]
            mesto, _, cast = (casti[-1] if casti else "").partition(" - ")
            foto = re.search(r'data-src="([^"]+)"', a)
            out.append({
                "id": f"idnes:{m.group(2)}",
                "zdroj": "iDnes",
                "kat": kat,
                "druh": druh(kat, nadpis, cesta),
                "nazev": nadpis[:1].upper() + nadpis[1:],
                "cena": cena(text(re.search(r'c-products__price">(.*?)</p>', a, re.S).group(1))),
                "plocha": plocha(nadpis),
                "pozemek": pozemek(nadpis) if kat == "domy" else None,
                "dispozice": dispozice(nadpis) if kat == "byty" else "",
                "mesto": mesto.strip(),
                "cast": cast.strip(),
                "ulice": casti[0] if len(casti) > 1 else "",
                "okres": okres_z_textu(info) or okres,
                "misto": info,
                "foto": foto.group(1) if foto else None,
                "url": m.group(1),
            })
        if not nove or "paging__item next" not in html:
            break
    return out


def hledej(kat: str) -> list[dict]:
    videno: set = set()
    return [b for cesta in KATEGORIE[kat] for okres, _ in oblast.OKRESY for b in _vypis(kat, cesta, okres, videno)]


def detail(b: dict) -> dict:
    """Galerie (odkazy data-fancybox), popis a tabulka parametrů z detailu."""
    html = get_text(b["url"], cache_hodin=DETAIL_CACHE)
    fotky = list(dict.fromkeys(re.findall(r'<a[^>]+href="(https://sta-reality2\.1gr\.cz/[^"]+)"[^>]*data-fancybox="images"', html)))
    popis = re.search(r'<div class="b-desc[^"]*"[^>]*>(.*?)</div>', html, re.S)
    parametry = []
    for k, v in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", html, re.S):
        # "54 m<sup>2</sup>" -> "54 m²"; ‍ = neviditelný spojovač, který iDnes vkládá do cen
        k, v = text(k), re.sub(r"\bm 2\b", "m²", text(v)).replace("‍", "")
        if k in ("Cena", "Číslo zakázky") or k.startswith("Spočítej"):
            continue
        parametry.append((k, v or "ano"))  # prázdná hodnota = zaškrtnuto (sklep, výtah)
    vysledek = {"telefon": telefon(html), "fotky": [unescape(f) for f in fotky],
                "popis": text_radky(popis.group(1)) if popis else "", "parametry": parametry}
    if b["kat"] == "domy" and not b.get("pozemek"):
        vysledek["pozemek"] = next((plocha(v) for k, v in parametry if k.lower().startswith("plocha pozemku")), None)
    return vysledek
