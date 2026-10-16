"""Sreality (JSON API, které používá jejich web) - hledá rovnou okruhem kolem středu."""
import urllib.parse

import oblast
from .http import DETAIL_CACHE, druh, get_json, plocha, pozemek, slug_url, strankuj

API = "https://www.sreality.cz/api/v1/estates/search"
KATEGORIE = {"byty": (1, "byt"), "domy": (2, "dum"), "pozemky": (3, "pozemek")}
FOTO = "?fl=res,400,300,3|shr,,20|jpg,90"  # bez parametru vrací SDN 401; jiné rozměry 400
# Okruh API je volnější než vzdušná vzdálenost (vrací i obce za hranicí) - přesně se třídí až podle souřadnic.
OKRUH_API_KM = oblast.OKRUH_KM + 3


def hledej(kat: str) -> list[dict]:
    cislo, seo_kat = KATEGORIE[kat]
    params = {"category_main_cb": cislo, "category_type_cb": 1, "locality_gps_lat": oblast.STRED[0],
              "locality_gps_lon": oblast.STRED[1], "locality_radius": OKRUH_API_KM}
    out = []
    for r in strankuj(API + "?" + urllib.parse.urlencode(params), 5000):
        loc = r.get("locality") or {}
        nazev = r.get("advert_name") or ""
        sub = (r.get("category_sub_cb") or {}).get("name", "")
        seo = "-".join(x for x in (loc.get("city_seo_name"), loc.get("citypart_seo_name"),
                                   loc.get("street_seo_name")) if x) or "x"
        obrazky = r.get("advert_images") or [im.get("advert_image_sdn_url") for im in r.get("advert_images_all") or []]
        obrazky = [o for o in obrazky if o]
        out.append({
            "id": f"sreality:{r['hash_id']}",
            "zdroj": "Sreality",
            "kat": kat,
            "druh": druh(kat, sub, nazev),
            "nazev": nazev,
            "cena": int(r.get("price_summary_czk") or r.get("price_czk") or 0) or None,
            "plocha": plocha(nazev),
            "pozemek": pozemek(nazev) if kat == "domy" else None,
            "dispozice": sub if kat == "byty" else "",
            "mesto": loc.get("city") or "",
            "cast": loc.get("citypart") if loc.get("citypart") != loc.get("city") else "",
            "ulice": loc.get("street") or "",
            "okres": loc.get("district") or "",
            "misto": ", ".join(x for x in (loc.get("street"), loc.get("citypart"), loc.get("city")) if x),
            "foto": "https:" + obrazky[0] + FOTO if obrazky else None,
            "gps": (loc["gps_lat"], loc["gps_lon"]) if loc.get("gps_lat") and loc.get("gps_lon") else None,
            "url": f"https://www.sreality.cz/detail/prodej/{seo_kat}/{slug_url(sub)}/{seo}/{r['hash_id']}",
        })
    return out


FOTO_VELKA = "?fl=res,749,562,3|shr,,20|jpg,90"  # největší rozměr, který SDN pro Sreality povolí


def detail(b: dict) -> dict:
    """Fotky, popis a parametry z detailu inzerátu."""
    r = get_json(f"https://www.sreality.cz/api/v1/estates/{b['id'].split(':')[1]}", cache_hodin=DETAIL_CACHE)
    r = r.get("result", r)
    jmeno = lambda k: (r.get(k) or {}).get("name") if isinstance(r.get(k), dict) else None  # noqa: E731
    mnozina = lambda k: ", ".join(h["name"] for h in r.get(k) or [] if isinstance(h, dict) and h.get("name"))  # noqa: E731
    podlazi = f"{r['floor_number']}. z {r['floors']}" if r.get("floor_number") is not None and r.get("floors") else None
    prislusenstvi = ", ".join(n for k, n in (("balcony", "balkon"), ("loggia", "lodžie"), ("terrace", "terasa"),
                                             ("cellar", "sklep"), ("garage", "garáž"), ("parking_lots", "parkování"),
                                             ("basin", "bazén")) if r.get(k))
    m2 = lambda k: f"{r[k]} m²" if r.get(k) else None  # noqa: E731
    parametry = [("Užitná plocha", m2("usable_area")), ("Plocha pozemku", m2("estate_area")),
                 ("Zahrada", m2("garden_area")), ("Podlaží", podlazi), ("Vlastnictví", jmeno("ownership")),
                 ("Stavba", jmeno("building_type")), ("Stav", jmeno("building_condition")),
                 ("Rok kolaudace", r.get("acceptance_year")), ("Rekonstrukce", r.get("reconstruction_year")),
                 ("Energetická třída", jmeno("energy_efficiency_rating_cb")), ("Výtah", jmeno("elevator")),
                 ("Vybavení", jmeno("furnished")), ("Vytápění", mnozina("heating_set")),
                 ("Voda", mnozina("water_set")), ("Odpad", mnozina("gully_set")), ("Elektřina", mnozina("electricity_set")),
                 ("Plyn", mnozina("gas_set")), ("Příjezd", mnozina("road_type_set")),
                 ("Příslušenství", prislusenstvi), ("Poloha", jmeno("object_location"))]
    telefony = ((r.get("user") or {}).get("user_phones") or [])
    obrazky = [im.get("url") or im.get("advert_image_sdn_url") for im in r.get("advert_images") or []]
    return {
        "telefon": telefony[0].get("phone") if telefony else None,
        "vlozeno": r.get("since") or None,  # datum vložení inzerátu na Sreality
        "fotky": ["https:" + u + FOTO_VELKA for u in obrazky if u],
        "popis": r.get("advert_description") or "",
        "parametry": [(k, str(v)) for k, v in parametry if v],
        "pozemek": r.get("estate_area") if b["kat"] == "domy" else None,
    }
