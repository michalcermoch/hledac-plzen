"""Kde se hledá: střed, okruh a okresy, které do okruhu zasahují.

Weby se prohledávají po okresech (každý web je pojmenovává po svém, převod je v zdroje/*.py) nebo rovnou
okruhem (Sreality, Bazoš). Co je dál než OKRUH_KM od středu, se vyřadí podle souřadnic inzerátu,
u webů bez souřadnic podle obce/ulice (OpenStreetMap).

Při změně středu nebo okruhu zkontroluj OKRESY: musí pokrýt celý kruh (mapa okresů: mapy.cz, vrstva Okresy).
"""
from zdroje.http import bez_diakritiky

NAZEV = "Plzeň a okolí"
STRED = (49.7475, 13.3776)          # Plzeň, náměstí Republiky
STRED_POPIS = "náměstí Republiky"   # odkud se počítá vzdálenost (štítek „12,3 km od centra“)
OKRUH_KM = 20
# (okres, kraj) - do 20 km od Plzně zasahují jen tyhle čtyři (Domažlice, Klatovy a Tachov začínají za 25 km)
OKRESY = [("Plzeň-město", "Plzeňský kraj"), ("Plzeň-jih", "Plzeňský kraj"), ("Plzeň-sever", "Plzeňský kraj"),
          ("Rokycany", "Plzeňský kraj")]
PSC = "30100"                        # Bazoš hledá okruhem kolem PSČ
MESTO = "Plzeň"                      # pro srovnání cen „v Plzni“ / „v okolí“
# Obdélník pro OpenStreetMap: obec se hledá jen tady (jinak by „Lhota“ našla jednu z desítek Lhot v Česku)
OBLAST_OSM = (STRED[1] - 0.5, STRED[0] + 0.35, STRED[1] + 0.5, STRED[0] - 0.35)  # lon1, lat1, lon2, lat2


def slug(nazev: str) -> str:
    """'Plzeň-město' -> 'plzen-mesto'."""
    return bez_diakritiky(nazev).replace(" ", "-")


def slug_velky(nazev: str) -> str:
    """'Plzeň-město' -> 'Plzen-mesto' (Reality.cz)."""
    s = slug(nazev)
    return s[:1].upper() + s[1:]
