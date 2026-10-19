"""Nemovitosti: stažení ze všech webů, filtr (natvrdo), poloha a okres, sloučení duplicit, srovnání s trhem.

Co se hledá, je tady a v oblast.py (střed, okruh, okresy). Jemnější výběr (druh, okres, obec, cena,
velikost, vzdálenost) si Domča dělá přímo na stránce - filtry tam nic nestahují znovu.
"""
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from statistics import median

import oblast
from zdroje import bazos, bezrealitky, ceskereality, idnes, realingo, realitycz, realitymix, sreality
from zdroje.http import DRUHY, bez_diakritiky, get_json, vzdalenost_m

# --- Filtr natvrdo: koupě, do 15 mil. Kč, do 20 km od centra Plzně (oblast.py) ---
CENA_DO = 15_000_000
# Domy jen rodinné (Domča nechce chaty, chalupy ani usedlosti); obecné „dům“ = web druh neuvádí, radši ukázat.
DRUHY_DOMU = {"rodinný dům", "vila", "vícegenerační dům", "dům"}
DUM_OD = 250_000  # levnější „domy“ jsou mobilheimy, podíly a stavební buňky (Bazoš)
VYMYSLENE_CENY = {123_456, 1_234_567, 12_345_678, 111_111, 1_111_111, 999_999, 9_999_999}  # = cena na dotaz
KATEGORIE = {
    "byty": dict(titul="Byty", jednotne="byt", co="bytu"),
    "domy": dict(titul="Rodinné domy", jednotne="dům", co="rodinného domu"),
    "pozemky": dict(titul="Pozemky", jednotne="pozemek", co="pozemku (stavební, zahrada, pole, les…)"),
}
# Co se opravdu hledá a ukazuje: rodinné domy a zvlášť pozemky (19. 10. 2026: Domča zvažuje i pozemek a dřevostavbu);
# byty weby umí dál.
HLEDAT = ["domy", "pozemky"]
# Pro panel „Co hledám“ v přehledu.
POPIS = {kat: [(f"{k['titul']} – {oblast.NAZEV}", ["koupě"] + (["bez chat a chalup"] if kat == "domy" else []) +
                                                   [f"do {CENA_DO // 1_000_000} mil. Kč",
                                                    f"do {oblast.OKRUH_KM} km od centra Plzně",
                                                    "okresy " + ", ".join(o for o, _ in oblast.OKRESY)])]
         for kat, k in KATEGORIE.items()}

ZDROJE = [  # (název, modul, předpona id)
    ("Sreality", sreality, "sreality"),
    ("iDnes", idnes, "idnes"),
    ("Bezrealitky", bezrealitky, "bezrealitky"),
    ("RealityMix", realitymix, "realitymix"),
    ("ČeskéReality", ceskereality, "ceskereality"),
    ("Reality.cz", realitycz, "realitycz"),
    ("Bazoš", bazos, "bazos"),
    ("Realingo", realingo, "realingo"),  # vyhledávač nad celým internetem, většina se sloučí jako duplicity
]
WEBY = [n for n, _, _ in ZDROJE]
PREDPONY = {n: p for n, _, p in ZDROJE}

# Detail (fotky, popis, parametry) se stahuje u každého inzerátu v okruhu. Napoprvé jich jsou tisíce, proto má
# každý web na detaily jen tolik času za běh; co se nestihne, doplní se příště (stažené jsou v cache.db 3-6 dní).
DETAIL_LIMIT_S = 420


# --- poloha: souřadnice z inzerátu, jinak obec / ulice / PSČ přes OpenStreetMap ---

@lru_cache(maxsize=None)
def _osm(dotaz: str = "", psc: str = "") -> tuple | None:
    """(lat, lon, okres) - hledá se jen v okolí (oblast.OBLAST_OSM), ať se nepletou stejně pojmenované obce."""
    params = {"format": "json", "limit": 1, "countrycodes": "cz", "addressdetails": 1, "bounded": 1,
              "viewbox": ",".join(str(x) for x in oblast.OBLAST_OSM)}
    params |= {"postalcode": psc, "country": "cz"} if psc else {"q": dotaz}
    if psc:
        params.pop("countrycodes")
    try:
        v = get_json("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params), cache_hodin=24 * 90)
    except Exception:
        return None
    if not v:
        return None
    okres = ((v[0].get("address") or {}).get("county") or "").removeprefix("okres ").strip()
    return float(v[0]["lat"]), float(v[0]["lon"]), okres


def _obec(b: dict) -> tuple | None:
    if b.get("mesto"):
        return _osm(b["mesto"] if not b.get("okres") else f"{b['mesto']}, okres {b['okres']}") or _osm(b["mesto"])
    if b.get("psc"):
        return _osm(psc=b["psc"])
    return None


def _dopln_polohu(b: dict, presne: bool = False):
    """Doplní 'gps' (+ 'gps_odhad'), 'vzdalenost' (m od středu) a případně 'okres'.
    presne=True: bez souřadnic z inzerátu zkusí i ulici / část obce (pro mapu); jinak stačí obec (pro filtr)."""
    if not b.get("gps") or (presne and b.get("gps_odhad") == "obec"):
        nalez, uroven = None, None
        if presne and b.get("mesto"):
            for dotaz, u in ((b.get("ulice"), "ulice"), (b.get("cast"), "část obce")):
                if dotaz:
                    nalez, uroven = _osm(f"{dotaz}, {b['mesto']}"), u
                    if nalez:
                        break
        if not nalez:
            nalez, uroven = _obec(b), "obec" if b.get("mesto") else "PSČ"
        if nalez:
            b["gps"], b["gps_odhad"] = [nalez[0], nalez[1]], uroven
            if nalez[2] and (not b.get("okres") or b["zdroj"] in ("ČeskéReality", "Bazoš")):
                b["okres"] = nalez[2]
    if b.get("gps"):
        b["vzdalenost"] = vzdalenost_m(tuple(b["gps"]), oblast.STRED)
    b["okres"] = _okres(b.get("okres"))


_OKRESY = {bez_diakritiky(o): o for o, _ in oblast.OKRESY}


def _okres(nazev: str) -> str:
    """'Plzeň-Jih' / 'plzen-jih' -> 'Plzeň-jih' (weby píšou okresy různě)."""
    return _OKRESY.get(bez_diakritiky(nazev or "").strip(), (nazev or "").strip())


def _v_okruhu(b: dict) -> bool:
    if b.get("vzdalenost") is None:
        return b["zdroj"] == "Bazoš"  # Bazoš hledá okruhem sám; bez polohy radši ukázat
    return b["vzdalenost"] <= oblast.OKRUH_KM * 1000


def vyhovuje(b: dict) -> bool:
    if b["kat"] == "domy" and (b.get("druh") not in DRUHY_DOMU or (b.get("cena") or DUM_OD) < DUM_OD):
        return False
    return b.get("cena") is None or b["cena"] <= CENA_DO  # „cena na dotaz“ radši ukázat


# --- hledání ---

def hledej(kat: str, log=print) -> tuple[list[dict], list[str], list[dict]]:
    """Vrací (vyhovující inzeráty se sloučenými duplicitami, hlášky o chybách, stav jednotlivých webů)."""
    hlasky, trh = [], []  # trh: všechny inzeráty v okruhu (i dražší) pro průměrnou cenu za m²

    def web(nazev, modul, predpona) -> tuple[list[dict], dict]:
        zacatek = time.monotonic()
        stav = {"nazev": nazev, "web": nazev, "predpona": predpona, "ok": True}
        try:
            nalez = modul.hledej(kat)
        except Exception as e:  # jeden nedostupný web nesmí shodit ostatní
            hlasky.append(f"{nazev}: chyba – {e}")
            log(f"  {nazev}: CHYBA {e}")
            return [], stav | {"ok": False, "chyba": str(e), "pocet": 0, "vybrano": 0,
                               "sekund": round(time.monotonic() - zacatek)}
        for b in nalez:
            if b.get("cena") and (b["cena"] < 10_000 or b["cena"] in VYMYSLENE_CENY):
                b["cena"] = None  # „1 Kč“ = cena na dotaz; u pozemků občas cena za m² místo celkové
            _dopln_polohu(b)
        v_okruhu = [b for b in nalez if _v_okruhu(b)]
        trh.extend(b for b in v_okruhu if b.get("cena") and b.get("plocha"))
        vybrane = [b for b in v_okruhu if vyhovuje(b)]
        log(f"  {nazev}: {len(nalez)} staženo, {len(v_okruhu)} v okruhu, {len(vybrane)} podle filtru")
        konec, chybi = time.monotonic() + DETAIL_LIMIT_S, 0
        for b in vybrane:
            if time.monotonic() > konec:
                chybi += 1
                continue
            _dopln_detail(modul, b, log)
        if chybi:
            log(f"  {nazev}: {chybi} detailů se nestihlo, doplní se příště")
        for b in vybrane:  # detail mohl přinést přesné souřadnice
            _dopln_polohu(b, presne=True)
        vybrane = [b for b in vybrane if _v_okruhu(b)]
        sekund = round(time.monotonic() - zacatek)
        log(f"  {nazev}: hotovo ({sekund} s)")
        return vybrane, stav | {"pocet": len(nalez), "vybrano": len(vybrane), "sekund": sekund}

    # Weby souběžně; ohleduplnost (1 požadavek na doménu, odstup) hlídá zdroje.http.
    with ThreadPoolExecutor(max_workers=len(ZDROJE)) as ex:
        casti = list(ex.map(lambda z: web(*z), ZDROJE))
    vse = [b for z_webu, _ in casti for b in z_webu]
    weby = [stav for _, stav in casti]
    vysledek = _sluc(vse)
    _dopln_okresy(vysledek)
    _trh(kat, vysledek, trh, log)
    if kat == "domy":
        _trh_domy(vysledek, log)  # přepíše hrubé srovnání za m² odhadem pro podobný dům, když je dost dat
    return vysledek, hlasky, weby


def _dopln_okresy(inzeraty: list[dict]):
    """Okres chybí hlavně u Bazoše (jen PSČ): stejná obec jinde, jinak nejbližší inzerát se známým okresem do 3 km."""
    znamy = [b for b in inzeraty if b.get("okres") and b.get("gps")]
    podle_obce = {bez_diakritiky(b.get("mesto") or ""): b["okres"] for b in znamy if b.get("mesto")}
    for b in inzeraty:
        if b.get("okres"):
            continue
        b["okres"] = podle_obce.get(bez_diakritiky(b.get("mesto") or ""), "")
        if not b["okres"] and b.get("gps") and znamy:
            vzd, nejblizsi = min((vzdalenost_m(tuple(b["gps"]), tuple(z["gps"])), z["okres"]) for z in znamy)
            b["okres"] = nejblizsi if vzd <= 3000 else ""


def _dopln_detail(modul, b: dict, log):
    try:
        d = modul.detail(b)
    except Exception as e:  # bez detailu se inzerát ukáže aspoň se základními údaji
        log(f"    detail {b['url']}: {e}")
        return
    for k, v in d.items():
        if not v:
            continue
        if k == "gps":
            b["gps"], b["gps_odhad"] = list(v), None
        else:
            b[k] = v


def _klic(b: dict):
    """Stejná nemovitost na víc webech: stejná kategorie, plocha a cena (u bytů i dispozice)."""
    if b.get("cena") and b.get("plocha"):
        return (b["kat"], b.get("dispozice") or "", b["plocha"], b["cena"])
    return b["id"]


PRESNOST = {None: 0, "ulice": 1, "část obce": 2, "obec": 3, "PSČ": 4}


def _sluc(vse: list[dict]) -> list[dict]:
    slouceno: dict = {}
    for b in vse:
        b["odkazy"] = [(b["zdroj"], b["url"])]
        k = _klic(b)
        if k not in slouceno:
            b["dalsi_id"] = []
            slouceno[k] = b
            continue
        s = slouceno[k]
        s["odkazy"].append((b["zdroj"], b["url"]))
        s["dalsi_id"].append(b["id"])
        # Stejná nemovitost na víc webech: vzít nejbohatší galerii, nejdelší popis a nejvíc parametrů.
        for pole in ("fotky", "popis", "parametry"):
            if len(b.get(pole) or "") > len(s.get(pole) or ""):
                s[pole] = b[pole]
        for pole in ("foto", "telefon", "pozemek", "ulice", "mesto", "okres"):
            if not s.get(pole) and b.get(pole):
                s[pole] = b[pole]
        if b.get("gps") and PRESNOST.get(b.get("gps_odhad"), 4) < PRESNOST.get(s.get("gps_odhad"), 4):
            s["gps"], s["gps_odhad"], s["vzdalenost"] = b["gps"], b.get("gps_odhad"), b.get("vzdalenost")
        if s["druh"] == DRUHY[s["kat"]][-1] and b["druh"] != s["druh"]:
            s["druh"] = b["druh"]  # obecné „dům“ / „pozemek“ nahradit konkrétnějším z jiného webu
        if b.get("vlozeno") and (not s.get("vlozeno") or b["vlozeno"] < s["vlozeno"]):
            s["vlozeno"] = b["vlozeno"]  # v nabídce od nejstaršího inzerátu
    return list(slouceno.values())


def _v_plzni(b: dict) -> bool:
    return bez_diakritiky(b.get("mesto") or "").startswith(bez_diakritiky(oblast.MESTO))


# --- srovnání s podobnými domy (17. 10. 2026: krásný dům po rekonstrukci nemá vycházet „o 47 % nad průměrem“
#     jen proto, že se srovnával s průměrnou cenou za m² všech domů včetně těch k rekonstrukci) ---

STAV_KLICE = ("stav budovy", "stav objektu", "stav nemovitosti", "stav")  # „Stavba“ = konstrukce, ne stav
NOVY, DOBRY, KREK = "nový nebo po rekonstrukci", "v dobrém stavu", "k rekonstrukci"
MNOZNE = {NOVY: "nové nebo po rekonstrukci", DOBRY: "v dobrém stavu", KREK: "k rekonstrukci"}
STAVY = [  # (třída, vzor v hodnotě parametru nebo v textu); pořadí = přednost
    (KREK, r"pred rekonstrukci|k rekonstrukci|ke kompletni rekonstrukci|spatn|demolic|rozestaven|havarij"),
    (NOVY, r"novostavb|ve vystavbe|projekt|bezvadn|po rekonstrukci|po kompletni rekonstrukci"),
    (DOBRY, r"velmi dobr|dobr|udrzovan"),
]
VYBAVA = {"bazén": r"bazen", "sauna": r"saun", "vířivka": r"virivk|whirlpool", "tepelné čerpadlo": r"tepeln\w* cerpadl",
          "fotovoltaika": r"fotovolt|\bfve\b", "garáž": r"garaz", "klimatizace": r"klimatiz", "krb": r"\bkrb"}
PODOBNYCH_MIN = 6
# Postupné uvolňování: (užitná plocha ±, pozemek ×/÷, stejný stav, stejně Plzeň/okolí)
STUPNE = [(0.25, 2.0, True, True), (0.25, None, True, True), (0.40, None, True, True), (0.40, None, True, False),
          (0.40, None, False, True)]


def _rok(b: dict, *nazvy: str) -> int | None:
    for k, v in b.get("parametry") or []:
        if bez_diakritiky(k) in nazvy:
            m = re.search(r"\b(1[89]\d\d|20\d\d)\b", str(v))
            if m:
                return int(m.group(1))
    return None


def stav_domu(b: dict) -> tuple[str | None, str]:
    """(třída stavu, čím je doložená) - rok rekonstrukce/výstavby, parametr webu, pak text inzerátu."""
    letos = time.localtime().tm_year
    rekonstrukce = _rok(b, "rekonstrukce", "rok rekonstrukce")
    vystavba = _rok(b, "vystavba", "rok vystavby", "rok kolaudace")
    if rekonstrukce and letos - 6 <= rekonstrukce <= letos + 1:
        return NOVY, f"rekonstrukce {rekonstrukce}"
    if vystavba and vystavba >= letos - 10:
        return NOVY, f"postaven {vystavba}"
    for k, v in b.get("parametry") or []:
        if bez_diakritiky(k) in STAV_KLICE:
            for trida, vzor in STAVY:
                if re.search(vzor, bez_diakritiky(str(v))):
                    return trida, str(v).strip().lower()
    text = bez_diakritiky(f'{b.get("nazev") or ""} {b.get("popis") or ""}')
    for trida, vzor in STAVY[:2]:  # „dobrý“ v textu nic neznamená („dobrá dostupnost“)
        if re.search(vzor, text):
            return trida, ""
    return None, ""


def vybava_domu(b: dict) -> list[str]:
    text = bez_diakritiky(" ".join([b.get("nazev") or "", b.get("popis") or ""] +
                                   [f"{k} {v}" for k, v in b.get("parametry") or []]))
    return [n for n, vzor in VYBAVA.items() if re.search(vzor, text)]


def _trh_domy(domy: list[dict], log):
    """Cena vůči podobným domům: stejná třída stavu, podobná užitná plocha a pozemek, stejně Plzeň / okolí.
    Odhad = medián ceny za m² podobných domů × plocha. Když podobných není dost, podmínky se postupně uvolní.
    Doplní 'trh' = {odhad (Kč), popis (s čím se srovnává), n, stav, dolozeno, vybava, rozdil (záporný = levnější)}."""
    ucet = [b for b in domy if b.get("cena") and 30 <= (b.get("plocha") or 0) <= 1000 and b["cena"] >= DUM_OD]
    info = {id(b): (stav_domu(b), _v_plzni(b), b.get("pozemek") if (b.get("pozemek") or 0) >= 50 else None)
            for b in domy}
    hotovo = 0
    for b in domy:
        b.pop("trh", None)  # hrubé srovnání za m² všech domů zavádí - radši nic, než ho nechat
        if not (b.get("cena") and 30 <= (b.get("plocha") or 0) <= 1000):
            continue
        (trida, dolozeno), plzen, poz = info[id(b)]
        for velikost, pozemek, stejny_stav, stejne_misto in STUPNE:
            if stejny_stav and trida is None:
                continue  # neznámý stav: rovnou srovnat bez ohledu na stav
            podobne = [o for o in ucet if o is not b
                       and abs(o["plocha"] - b["plocha"]) <= velikost * b["plocha"]
                       and (not stejny_stav or info[id(o)][0][0] == trida)
                       and (not stejne_misto or info[id(o)][1] == plzen)
                       and (pozemek is None or not poz or not info[id(o)][2]
                            or poz / pozemek <= info[id(o)][2] <= poz * pozemek)]
            if len(podobne) >= PODOBNYCH_MIN:
                break
        else:
            continue
        odhad = median(o["cena"] / o["plocha"] for o in podobne) * b["plocha"]
        cast = ([MNOZNE[trida]] if stejny_stav else []) \
            + [f'{round(b["plocha"] * (1 - velikost))}–{round(b["plocha"] * (1 + velikost))} m²'] \
            + ([f'pozemek {round(poz / pozemek)}–{round(poz * pozemek)} m²'] if pozemek and poz else []) \
            + ([("v Plzni" if plzen else "v okolí Plzně")] if stejne_misto else [])
        popis = f'{len(podobne)} podobných domů ({", ".join(cast)})'
        b["trh"] = {"odhad": round(odhad, -4), "popis": popis, "n": len(podobne),
                    "stav": trida if stejny_stav else None, "dolozeno": dolozeno, "vybava": vybava_domu(b),
                    "rozdil": round((b["cena"] - odhad) / odhad, 3)}
        hotovo += 1
    log(f"  trh: {hotovo} domů srovnáno s podobnými (stav, velikost, pozemek, Plzeň/okolí)")


def _skupina(kat: str, b: dict) -> str:
    return b.get("dispozice") or "" if kat == "byty" else b.get("druh") or "" if kat == "pozemky" else ""


def _trh(kat: str, inzeraty: list[dict], vse: list[dict], log):
    """Cena za m² vůči trhu: medián všech inzerátů v okruhu (bez duplicit mezi weby) - zvlášť Plzeň a okolí,
    u bytů podle dispozice, u pozemků podle druhu. Doplní 'trh' = {median, zaklad, n, rozdil (záporný = levnější)}."""
    meze = {"byty": (15, 300), "domy": (30, 1000), "pozemky": (100, 200_000)}[kat]
    unikatni = list({(b.get("dispozice"), b["plocha"], b["cena"]): b for b in vse
                     if meze[0] <= b["plocha"] <= meze[1] and 100_000 <= b["cena"] <= 60_000_000}.values())
    if len(unikatni) < 10:
        return
    skupiny: dict[tuple, list[float]] = {}
    for b in unikatni:
        cm2 = b["cena"] / b["plocha"]
        for klic in ((_skupina(kat, b), _v_plzni(b)), (_skupina(kat, b), None), ("", _v_plzni(b)), ("", None)):
            skupiny.setdefault(klic, []).append(cm2)
    for b in inzeraty:
        if not (b.get("cena") and b.get("plocha")):
            continue
        for sk, plzen in ((_skupina(kat, b), _v_plzni(b)), (_skupina(kat, b), None), ("", _v_plzni(b)), ("", None)):
            hodnoty = skupiny.get((sk, plzen)) or []
            if len(hodnoty) >= 8:
                break
        med = median(hodnoty)
        kde = "v Plzni" if plzen else "v okolí Plzně" if plzen is False else "v okruhu"
        b["trh"] = {"median": round(med), "zaklad": f"{sk + ' ' if sk else ''}{kde}".strip(), "n": len(hodnoty),
                    "rozdil": round((b["cena"] / b["plocha"] - med) / med, 3)}
    log(f"  trh: medián {round(median(skupiny[('', None)])):,} Kč/m² z {len(unikatni)} inzerátů".replace(",", " "))
