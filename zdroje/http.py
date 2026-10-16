"""Společné stahování a parsování - jen standardní knihovna."""
import http.client
import json
import re
import sqlite3
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html import unescape
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

# --- ohleduplnost: weby se prohledávají souběžně, ale na jednu doménu jde vždy jen jeden požadavek
# a mezi požadavky je minimální odstup. Bazoš při rychlejším tempu vrací 429.
# Nominatim: max 1 dotaz za sekundu; iDnes z GitHubu při rychlejším tempu shazuje spojení
ODSTUP = {"bazos.cz": 2.0, "openstreetmap.org": 1.1, "idnes.cz": 1.0, "ceskereality.cz": 1.0}  # ČeskéReality: 429 při 0,3 s
ODSTUP_VYCHOZI = 0.3
_zamky: dict[str, threading.Lock] = {}
_posledni: dict[str, float] = {}
_zamek_zamku = threading.Lock()


def _domena(url: str) -> str:
    host = urllib.parse.urlsplit(url).hostname or ""
    return ".".join(host.split(".")[-2:])  # auto.bazos.cz i reality.bazos.cz = bazos.cz


MAX_CEKANI_429 = 20
BLOKACE_S = 600  # doména, která opakovaně vrací 429, se tak dlouho přeskakuje (jinak by hledání viselo)
_blokovano: dict[str, float] = {}


def _stahni(url: str, accept: str, pokusu: int = 4, hlavicky: dict | None = None) -> tuple[bytes, str]:
    domena = _domena(url)
    if time.monotonic() - _blokovano.get(domena, -1e9) < BLOKACE_S:
        raise RuntimeError(f"{domena} teď blokuje příliš mnoho požadavků (429), přeskakuji")
    with _zamek_zamku:
        zamek = _zamky.setdefault(domena, threading.Lock())
    with zamek:
        cekat = _posledni.get(domena, 0) + ODSTUP.get(domena, ODSTUP_VYCHOZI) - time.monotonic()
        if cekat > 0:
            time.sleep(cekat)
        try:
            return _stahni_hned(url, accept, pokusu, hlavicky)
        finally:
            _posledni[domena] = time.monotonic()


def _stahni_hned(url: str, accept: str, pokusu: int, hlavicky: dict | None = None) -> tuple[bytes, str]:
    """Stáhne tělo odpovědi; přerušené spojení zkusí znovu (iDnes občas shazuje spojení)."""
    # Nominatim (OpenStreetMap) chce, aby se aplikace představila vlastním jménem, ne jako prohlížeč
    # ČeskéReality od 30. 9. 2026 vrací 403 na "Chrome" bez jeho dalších hlaviček (sec-ch-ua); vlastní jméno projde
    ua = "HledacPlzen/1.0 (osobni hledani nemovitosti)" if "openstreetmap.org" in url or "ceskereality.cz" in url else UA
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": accept, "Accept-Language": "cs"} | (hlavicky or {}))
    for pokus in range(pokusu):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read(), r.headers.get_content_charset() or "utf-8"
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise  # 404 apod. opakovat nemá smysl
            if pokus == pokusu - 1:
                _blokovano[_domena(url)] = time.monotonic()
                raise
            # 429 Too Many Requests (Bazoš): chvíli počkat, ale nikdy ne minuty (Retry-After umí být dlouhé)
            cekej = e.headers.get("Retry-After", "")
            s = min(int(cekej) if cekej.isdigit() else 5 * (pokus + 1), MAX_CEKANI_429)
            print(f"    {_domena(url)}: 429, čekám {s} s")
            time.sleep(s)
        except (OSError, http.client.IncompleteRead):  # přerušené spojení, timeout, utržená odpověď
            if pokus == pokusu - 1:
                raise
            time.sleep(3 * 3 ** pokus)  # 3, 9, 27 s - iDnes po shození spojení chvíli odmítá i další pokusy


# --- mezipaměť detailů inzerátů (fotky, popis, parametry se mezi aktualizacemi skoro nemění) ---
CACHE = Path(__file__).parent.parent / "cache.db"
DETAIL_CACHE = 72  # hodin; ceny se berou z výpisů, takže se nezastarají
# Detailů jsou stovky: platnost se podle adresy rozprostře na 72-144 h, ať nevyprší všechny v jednom běhu.


def _z_cache(url: str, hodin: float | None, stahni) -> str:
    if not hodin:
        return stahni()
    if hodin == DETAIL_CACHE:
        hodin *= 1 + zlib.crc32(url.encode()) % 1000 / 1000
    with sqlite3.connect(CACHE, timeout=30) as c:
        c.execute("CREATE TABLE IF NOT EXISTS stranka (url TEXT PRIMARY KEY, cas REAL, obsah TEXT)")
        row = c.execute("SELECT cas, obsah FROM stranka WHERE url=?", (url,)).fetchone()
        if row and time.time() - row[0] < hodin * 3600:
            return row[1]
    obsah = stahni()
    with sqlite3.connect(CACHE, timeout=30) as c:
        c.execute("INSERT OR REPLACE INTO stranka VALUES (?,?,?)", (url, time.time(), obsah))
    return obsah


def procisti_cache(dni: int = 91) -> None:
    """Smaže stránky starší než nejdelší doba platnosti (geokódování 90 dní), ať cache neroste donekonečna."""
    if not CACHE.exists():
        return
    with sqlite3.connect(CACHE, timeout=30) as c:
        c.execute("CREATE TABLE IF NOT EXISTS stranka (url TEXT PRIMARY KEY, cas REAL, obsah TEXT)")
        c.execute("DELETE FROM stranka WHERE cas < ?", (time.time() - dni * 86400,))
    c = sqlite3.connect(CACHE, timeout=30)
    c.execute("VACUUM")
    c.close()


def get_json(url: str, cache_hodin: float | None = None, hlavicky: dict | None = None) -> dict:
    return json.loads(_z_cache(url, cache_hodin,
                               lambda: _stahni(url, "application/json", hlavicky=hlavicky)[0].decode("utf-8")))


def get_text(url: str, cache_hodin: float | None = None) -> str:
    return _z_cache(url, cache_hodin, lambda: _dekoduj(*_stahni(url, "text/html")))


def _dekoduj(data: bytes, charset: str) -> str:
    if charset.lower() == "utf-8":
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:  # některé weby posílají cp1250 bez hlavičky
            return data.decode("cp1250", errors="replace")
    return data.decode(charset, errors="replace")


def pauza(s: float = 0.5):
    """Dřív pevná pauza; odstup mezi požadavky teď hlídá _stahni podle domény (a u cache se nečeká)."""


def strankuj(zaklad_url: str, max_pocet: int, stranka: int = 200):
    """Projde JSON výsledky po stránkách (limit/offset), dokud nejsou všechny nebo max_pocet."""
    offset = 0
    while offset < max_pocet:
        sep = "&" if "?" in zaklad_url else "?"
        data = get_json(f"{zaklad_url}{sep}limit={stranka}&offset={offset}")
        vysledky = data.get("results") or []
        yield from vysledky
        celkem = data.get("pagination", {}).get("total", 0)
        offset += stranka
        if not vysledky or offset >= celkem:
            break
        pauza()


# --- parsování textu inzerátů ---

def text(html: str) -> str:
    """HTML fragment -> prostý text na jednom řádku."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def text_radky(html: str) -> str:
    """HTML popis -> prostý text se zachovanými řádky (pro detail inzerátu)."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</(?:p|div|li|h\d|tr)>", "\n", s, flags=re.I)
    s = unescape(re.sub(r"<[^>]+>", "", s)).replace("​", "")
    radky = [re.sub(r"[ \t\xa0]+", " ", r).strip() for r in s.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(radky)).strip()


def bez_diakritiky(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)).lower()


def dispozice(s: str) -> str:
    """'2+1', '2 + kk', 'DISP_2_1', 'byty/3+1' -> '2+1' / '2+kk' / '3+1'; nic -> ''."""
    m = re.search(r"(\d)\s*\+\s*(kk|\d)", s, re.I) or re.search(r"DISP_(\d)_(KK|\d)", s)
    return f"{m.group(1)}+{m.group(2).lower()}" if m else ""


def cena(s: str) -> int | None:
    """'1 890 000 Kč' -> 1890000; 'Info o ceně u RK' -> None."""
    m = re.search(r"(\d[\d\s\xa0.]*)\s*(Kč|CZK)", s)
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def plocha(s: str) -> int | None:
    """První plocha v textu: 'Prodej rodinného domu 120 m², pozemek 600 m²' -> 120; '1 250 m²' -> 1250."""
    m = re.search(r"(?<![\d,.])(\d{1,3}(?:[  .]\d{3})+|\d+)(?:,\d+)?\s*m(?:²|2)(?!\w)", s)
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def pozemek(s: str) -> int | None:
    """'..., pozemek 1 968 m²' / 's pozemkem 2 122 m²' / 'Plocha pozemku: 800 m²' -> plocha pozemku."""
    m = re.search(r"pozem\w*\W{0,3}(\d{1,3}(?:[  .]\d{3})+|\d+)(?:,\d+)?\s*m(?:²|2)(?!\w)", s, re.I)
    return int(re.sub(r"\D", "", m.group(1))) if m else None


# --- telefon, souřadnice, vzdálenost ---

def telefon(html: str) -> str | None:
    """První odkaz tel: na stránce (prodejce, makléř)."""
    m = re.search(r'href="tel:([+\d][\d\s/()-]{7,})"', html)
    return re.sub(r"[^\d+]", "", m.group(1)) if m else None


def geokoduj(dotaz: str, oblast: tuple | None = None) -> tuple[float, float] | None:
    """Adresa -> (lat, lon) přes OpenStreetMap Nominatim; výsledek se pamatuje 90 dní.
    oblast = (lon1, lat1, lon2, lat2): hledat jen v tomhle obdélníku (stejně pojmenované obce jinde se nepletou)."""
    params = {"q": dotaz, "format": "json", "limit": 1, "countrycodes": "cz"}
    if oblast:
        params |= {"viewbox": ",".join(str(x) for x in oblast), "bounded": 1}
    try:
        vysledky = get_json("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params),
                            cache_hodin=24 * 90)
    except Exception:
        return None
    return (float(vysledky[0]["lat"]), float(vysledky[0]["lon"])) if vysledky else None


def vzdalenost_m(a: tuple[float, float], b: tuple[float, float]) -> int:
    """Vzdušná vzdálenost dvou bodů v metrech (haversine)."""
    import math
    f1, f2 = math.radians(a[0]), math.radians(b[0])
    df, dl = f2 - f1, math.radians(b[1] - a[1])
    h = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return round(2 * 6371000 * math.asin(math.sqrt(h)))


# --- druh nemovitosti: jednotné názvy napříč weby ---
DRUHY = {
    "byty": ["byt"],
    "domy": ["rodinný dům", "vila", "vícegenerační dům", "chata / chalupa", "zemědělská usedlost", "činžovní dům",
             "mobilní dům", "dům"],
    "pozemky": ["stavební pozemek", "zahrada", "komerční pozemek", "pole", "louka", "les", "sad / vinice", "rybník",
                "pozemek"],
}
_DRUH_VZORY = {
    # pořadí rozhoduje: „komerční stavební pozemek“ je komerční, „stavební pozemek se zahradou“ stavební
    "domy": [(r"mobilheim|mobilni dum|mobil home|maringotk|tiny ?house|obytn\w* bunk|\bbunk", "mobilní dům"),
             (r"vicegener", "vícegenerační dům"), (r"\bvil[ayu]\b|\bvile\b", "vila"), (r"chalup|\bchat[aeyu]?\b|chatk|rekreacn", "chata / chalupa"),
             (r"usedlost|statek|zemedelsk", "zemědělská usedlost"), (r"cinzov|najemni dum|bytovy dum|bytoveho domu", "činžovní dům"), (r"rodin|\brd\b|na klic|radov", "rodinný dům")],
    "pozemky": [(r"komercn", "komerční pozemek"), (r"staveb|bydleni", "stavební pozemek"), (r"zahrad", "zahrada"),
                (r"\bsad|vinic", "sad / vinice"), (r"\bpole\b|\bpoli\b|\born[ae]", "pole"), (r"louk", "louka"),
                (r"\bles[uy]?\b|lesni", "les"), (r"rybni", "rybník"), (r"zemedel", "pole")],
}


def druh(kat: str, *texty: str) -> str:
    """Druh nemovitosti z názvu/kategorie webu: 'Prodej rodinného domu 120 m²' -> 'rodinný dům'.
    Projde texty v pořadí (nejdřív kategorie webu, pak nadpis); nic nesedí -> obecný druh kategorie."""
    for t in texty:
        t = bez_diakritiky(t or "").replace("domu/vily", "domu")  # RealityMix tak píše každý dům
        for vzor, nazev in _DRUH_VZORY.get(kat, []):
            if re.search(vzor, t):
                return nazev
    return DRUHY[kat][-1]


def slug_url(s: str) -> str:
    """'Rodinný' -> 'rodinny', '2+kk' -> '2+kk' (část adresy inzerátu)."""
    return re.sub(r"[^a-z0-9+]+", "-", bez_diakritiky(s)).strip("-") or "x"


def okres_z_textu(s: str) -> str:
    """'Neurazy, okres Plzeň-jih' / 'okr. Plzeň-město' -> 'Plzeň-jih' / 'Plzeň-město'."""
    m = re.search(r"\bokr(?:es|\.)\s*([^,]+)", s or "")
    return m.group(1).strip() if m else ""
