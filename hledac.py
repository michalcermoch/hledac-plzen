"""Hledač nemovitostí - Plzeň a okolí do 20 km (byty, domy, pozemky).

    py hledac.py --server       # webový přehled na http://localhost:8766 s tlačítkem Aktualizovat (Hledač.cmd)
    py hledac.py                # jednorázově stáhne vše a otevře prehled.html
    py hledac.py domy pozemky   # jen některé kategorie
    py hledac.py --neotvirat
    py hledac.py --prekreslit   # jen znovu vykreslí přehled z posledních výsledků (bez stahování)
    py hledac.py --cloud        # běh v GitHub Actions (stránka do web/index.html, denní souhrn e-mailem)

Stáhne inzeráty z 8 realitních webů, vyfiltruje je (natvrdo v nemovitosti.py a oblast.py), zapamatuje si je
v hledac.db a vygeneruje prehled.html (nové od minula a zlevněné jsou označené). K inzerátům může přidat
postřeh AI (ai.py, Google Gemini zdarma - jen když je klíč).
"""
import json
import sqlite3
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import ai
import nastaveni
import nemovitosti
import prehled
import upozorneni

KOREN = Path(__file__).parent
DB = KOREN / "hledac.db"
PREHLED = KOREN / "prehled.html"
POSLEDNI = KOREN / "posledni.json"  # výsledky posledního běhu pro --prekreslit a server
PORT = 8766  # 8765 má Hledač bytů a aut, ať můžou běžet oba
PREVZIT_DNI = 3  # jak dlouho držet inzeráty webu, který neodpovídá

TITULY = {kat: k["titul"] for kat, k in nemovitosti.KATEGORIE.items()}
# Co se hledá, pro AI (ať posuzuje inzeráty vůči zadání)
ZADANI = {kat: "; ".join(f"{n} ({', '.join(p)})" for n, p in nemovitosti.POPIS[kat]) for kat in TITULY}


def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS inzerat (
        id TEXT PRIMARY KEY, kategorie TEXT, prvni_videno TEXT,
        naposled_videno TEXT, cena INTEGER, puvodni_cena INTEGER)""")
    c.execute("CREATE TABLE IF NOT EXISTS cena (id TEXT, cas TEXT, cena INTEGER)")  # každá změna ceny
    c.execute("CREATE INDEX IF NOT EXISTS cena_id ON cena(id)")
    # Otisk vozu/bytu: přežije smazání inzerátu, takže se pozná, když ho prodejce vloží znovu.
    c.execute("""CREATE TABLE IF NOT EXISTS otisk (otisk TEXT PRIMARY KEY, kategorie TEXT, id TEXT,
        prvni TEXT, posledni TEXT, ceny TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS ai (id TEXT PRIMARY KEY, otisk TEXT, cas TEXT, vysledek TEXT)")  # postřehy AI
    c.execute("CREATE TABLE IF NOT EXISTS meta (klic TEXT PRIMARY KEY, hodnota TEXT)")  # např. kdy odešel souhrn
    if not c.execute("SELECT 1 FROM cena LIMIT 1").fetchone():  # první spuštění s historií: převzít, co víme
        c.execute("INSERT INTO cena SELECT id, prvni_videno, puvodni_cena FROM inzerat")
        c.execute("INSERT INTO cena SELECT id, naposled_videno, cena FROM inzerat WHERE cena IS NOT puvodni_cena")
        c.commit()
    return c


def otisk(i: dict, kat: str) -> str | None:
    """Stejná nemovitost i v jiném inzerátu: kategorie + dispozice + plocha (+ pozemek) + obec."""
    if i.get("plocha") and i.get("mesto"):
        return f"{kat}:{i.get('dispozice') or ''}|{i['plocha']}|{i.get('pozemek') or ''}|{i['mesto'].lower()}"
    return None


def _znovu_vlozene(c, kat: str, i: dict, ted: str):
    """Pozná znovu vložený inzerát (jiné ID, stejný otisk) a doplní 'znovu' = kdy ho Hledač viděl poprvé a za kolik."""
    o = otisk(i, kat)
    if not o:
        return
    row = c.execute("SELECT id, prvni, ceny FROM otisk WHERE otisk=?", (o,)).fetchone()
    if row is None:
        c.execute("INSERT INTO otisk VALUES (?,?,?,?,?,?)", (o, kat, i["id"], ted, ted, json.dumps([[ted[:10], i["cena"]]])))
        return
    ceny = json.loads(row[2] or "[]")
    if i["cena"] and (not ceny or ceny[-1][1] != i["cena"]):
        ceny.append([ted[:10], i["cena"]])
    if row[0] != i["id"] and row[1][:10] < ted[:10]:
        # jiný inzerát, stejná nemovitost, dřív viděná -> znovu vložený; historii cen převzít od prvního inzerátu
        i["znovu"] = {"prvni": row[1][:10], "cena": ceny[0][1] if ceny else None}
        i["historie_cen"] = [tuple(x) for x in ceny]
    c.execute("UPDATE otisk SET id=?, posledni=?, ceny=? WHERE otisk=?", (i["id"], ted, json.dumps(ceny), o))


def zapamatuj(c, kat: str, inzeraty: list[dict], ted: str) -> dict:
    """Uloží inzeráty a doplní k nim 'novy', 'puvodni_cena', 'zlevneno_ted', 'historie_cen' a 'dni' (v nabídce).
    Vrací souhrn pro oznámení po aktualizaci."""
    dnes = datetime.fromisoformat(ted).date()
    souhrn = {"nove": 0, "zlevnene": 0}
    for i in inzeraty:
        row = c.execute("SELECT prvni_videno, puvodni_cena, cena FROM inzerat WHERE id=?", (i["id"],)).fetchone()
        i["zlevneno_ted"] = False
        if row is None:
            i["novy"], i["puvodni_cena"], i["prvni_videno"] = True, i["cena"], ted
            c.execute("INSERT INTO inzerat VALUES (?,?,?,?,?,?)", (i["id"], kat, ted, ted, i["cena"], i["cena"]))
            c.execute("INSERT INTO cena VALUES (?,?,?)", (i["id"], ted, i["cena"]))
            souhrn["nove"] += 1
        else:
            i["novy"], i["prvni_videno"], i["puvodni_cena"] = False, row[0], row[1]
            if i["cena"] != row[2]:
                c.execute("INSERT INTO cena VALUES (?,?,?)", (i["id"], ted, i["cena"]))
                if i["cena"] and row[2] and i["cena"] < row[2]:
                    i["zlevneno_ted"] = True
                    souhrn["zlevnene"] += 1
            c.execute("UPDATE inzerat SET naposled_videno=?, cena=? WHERE id=?", (ted, i["cena"], i["id"]))
        i["historie_cen"] = [(cas, cena) for cas, cena in
                             c.execute("SELECT cas, cena FROM cena WHERE id=? ORDER BY cas", (i["id"],))]
        # Doba v nabídce u každého inzerátu: ze skutečného data vložení na webu (Sreality); kde ho web neuvádí,
        i["dni_min"] = not i.get("vlozeno")
        i["dni"] = max(0, (dnes - datetime.fromisoformat((i.get("vlozeno") or i["prvni_videno"])[:10]).date()).days)
        _znovu_vlozene(c, kat, i, ted)
    c.commit()
    return souhrn


def smaz_zmizele(c, kat: str, inzeraty: list[dict], weby: list[dict], log):
    """Inzeráty, které z webu zmizely (nejspíš prodané), rovnou smaže i s historií ceny.
    Jen u webů, které tentokrát doběhly bez chyby - jinak by se výpadek webu tvářil jako prodej."""
    ok = {w["predpona"] for w in weby if w["ok"]} - {w["predpona"] for w in weby if not w["ok"]}
    videne = {i["id"] for i in inzeraty} | {x for i in inzeraty for x in i.get("dalsi_id") or []}
    zmizele = [id_ for (id_,) in c.execute("SELECT id FROM inzerat WHERE kategorie=?", (kat,))
               if id_ not in videne and id_.split(":")[0] in ok]
    for id_ in zmizele:
        c.execute("DELETE FROM inzerat WHERE id=?", (id_,))
        c.execute("DELETE FROM cena WHERE id=?", (id_,))
        c.execute("DELETE FROM ai WHERE id=?", (id_,))
    c.commit()
    if zmizele:
        log(f"{TITULY[kat]}: {len(zmizele)} zmizelých inzerátů smazáno")


def hledej(kategorie: list[str], log=print) -> dict:
    """Stáhne a vyfiltruje inzeráty, uloží posledni.json a prehled.html. Vrací souhrn (nové/zlevněné)."""
    ted = datetime.now().isoformat(timespec="seconds")
    # Kategorie po sobě (weby v každé běží souběžně) - souběžně by se na stejné weby jen čekalo ve frontě.
    vysledky = [nemovitosti.hledej(kat, log=lambda r, k=kat: log(f"{TITULY[k]}: {r.strip()}")) for kat in kategorie]
    c = db()
    sekce, souhrn = [], {}
    drivejsi = {s[0]: s[1] for s in posledni()[0]} if POSLEDNI.exists() else {}
    for kat, (vybrane, hlasky, weby) in zip(kategorie, vysledky):
        # Web, který tentokrát selhal (typicky Bazoš s 429): převzít jeho inzeráty z minula, ať z přehledu nezmizí.
        selhane = {w["predpona"] for w in weby if not w.get("ok")}
        videne = {i["id"] for i in vybrane}
        prevzate = [i for i in drivejsi.get(kat, []) if i["id"] not in videne and i["id"].split(":")[0] in selhane]
        for i in prevzate:
            i.setdefault("prevzato_od", ted)
        # web nedostupný déle -> staré inzeráty nedržet donekonečna
        prevzate = [i for i in prevzate if datetime.fromisoformat(ted) - datetime.fromisoformat(i["prevzato_od"])
                    < timedelta(days=PREVZIT_DNI)]
        if prevzate:
            log(f"{TITULY[kat]}: {len(prevzate)} inzerátů převzato z minula (web teď neodpověděl)")
            vybrane = vybrane + prevzate
        souhrn[kat] = zapamatuj(c, kat, vybrane, ted)
        smaz_zmizele(c, kat, vybrane, weby, log)
        try:
            ai.dopln(c, kat, vybrane, ZADANI[kat], log=lambda r, k=kat: log(f"{TITULY[k]}: {r.strip()}"))
        except Exception as e:  # AI je jen doplněk, hledání nesmí shodit
            log(f"{TITULY[kat]}: AI selhala ({type(e).__name__}: {e})")
        log(f"{TITULY[kat]}: celkem {len(vybrane)}, z toho {souhrn[kat]['nove']} nových")
        sekce.append((kat, vybrane, hlasky, weby))
    c.close()
    # Hledalo se jen v části kategorií -> ostatní převzít z posledního běhu, ať z přehledu nezmizí.
    hotove = {s[0] for s in sekce}
    if POSLEDNI.exists() and hotove != set(TITULY):
        drivejsi = {s[0]: s for s in posledni()[0]}
        sekce = [next((s for s in sekce if s[0] == kat), None) or drivejsi.get(kat) or (kat, [], [], [])
                 for kat in TITULY]
    POSLEDNI.write_text(json.dumps({"ted": ted, "sekce": sekce}, ensure_ascii=False), encoding="utf-8")
    PREHLED.write_text(prehled.html(sekce, ted), encoding="utf-8")
    return souhrn


def posledni():
    """(sekce, čas) z posledního běhu; sekce = (kategorie, inzeráty, hlášky, stav webů)."""
    if not POSLEDNI.exists():
        return [(k, [], [], []) for k in TITULY], datetime.now().isoformat(timespec="seconds")
    data = json.loads(POSLEDNI.read_text(encoding="utf-8"))
    return [(tuple(x) + ([],) * 4)[:4] for x in data["sekce"]], data["ted"]  # starší soubory neměly stav webů


# --- server s tlačítkem Aktualizovat ---

class Stav:
    zamek = threading.Lock()
    bezi = False
    log: list[str] = []
    chyba = ""
    dokonceno = ""
    souhrn: dict = {}
    mobil_url: str | None = None


AUTOMATICKY_KAZDYCH_S = 3 * 3600  # dokud Hledač běží, sám se aktualizuje (upozornění posílá jen cloud)


def _aktualizuj():
    def log(radek):
        print(radek)
        Stav.log.append(str(radek))
    try:
        Stav.souhrn = hledej(list(TITULY), log=log)
        Stav.dokonceno = datetime.now().isoformat(timespec="seconds")
    except Exception as e:  # chybu ukázat v přehledu, server nechat běžet
        Stav.chyba = f"{type(e).__name__}: {e}"
        log(f"CHYBA {Stav.chyba}")
    finally:
        Stav.bezi = False


class Handler(BaseHTTPRequestHandler):
    def _posli(self, kod: int, telo: str, typ: str):
        data = telo.encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", f"{typ}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] == "/":
            sekce, ted = posledni()
            self._posli(200, prehled.html(sekce, ted, Stav.mobil_url), "text/html")  # vždy s aktuálním vzhledem
        elif self.path == "/stav":
            self._posli(200, json.dumps({"bezi": Stav.bezi, "log": Stav.log[-1:], "chyba": Stav.chyba,
                                         "dokonceno": Stav.dokonceno, "souhrn": Stav.souhrn},
                                        ensure_ascii=False), "application/json")
        else:
            self._posli(404, "nenalezeno", "text/plain")

    def do_POST(self):
        if self.path != "/aktualizovat":
            return self._posli(404, "nenalezeno", "text/plain")
        with Stav.zamek:
            if not Stav.bezi:
                Stav.bezi, Stav.log, Stav.chyba = True, [], ""
                threading.Thread(target=_aktualizuj, daemon=True).start()
        self._posli(202, json.dumps({"bezi": True}), "application/json")

    def log_message(self, *args):  # bez výpisu každého požadavku
        pass


def _ip_v_siti() -> str | None:
    """IP adresa počítače v domácí síti (kvůli otevření Hledače z mobilu)."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 9))  # nic se neposílá, jen se zjistí, přes které rozhraní by šlo
            return s.getsockname()[0]
    except OSError:
        return None


def _automaticky():
    """Každé 3 hodiny aktualizace (jen dokud běží Hledač; žádný Plánovač úloh). Upozornění posílá jen cloud."""
    while True:
        time.sleep(AUTOMATICKY_KAZDYCH_S)
        with Stav.zamek:
            if Stav.bezi:
                continue
            Stav.bezi, Stav.log, Stav.chyba = True, [], ""
        _aktualizuj()


def server():
    # 0.0.0.0 = i z ostatních zařízení v domácí síti (mobil); Windows se napoprvé zeptá na povolení ve firewallu
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    url = f"http://localhost:{PORT}/"
    ip = _ip_v_siti()
    Stav.mobil_url = f"http://{ip}:{PORT}/" if ip else None
    print(f"Hledač běží na {url} (ukončení: Ctrl+C nebo zavřít okno)")
    if Stav.mobil_url:
        print(f"Z mobilu (stejná Wi-Fi): {Stav.mobil_url}")
    print(f"Automatická aktualizace každé {AUTOMATICKY_KAZDYCH_S // 3600} h (upozornění na mobil posílá jen cloud)")
    threading.Thread(target=_automaticky, daemon=True).start()
    if "--neotvirat" not in sys.argv:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def cloud():
    """Běh v GitHub Actions: hledání, zašifrovaná stránka do web/index.html a upozornění.
    Proměnné: HLAVNI_KLIC (base64, 32 B - jím je stránka zašifrovaná; bez něj nezašifrovaná),
    HESLO_STRANKY (kód z pozvánky pro první přihlášení), PRISTUP_KANAL (skrytý kanál ntfy, kam prohlížeč pošle
    nově nastavené heslo - zamčený klíč, ne heslo), WEB_URL (adresa stránky), AKCE_URL (spuštění hledání na GitHubu),
    AKTUALIZACE_TOKEN (nepovinný: tlačítko Aktualizovat spustí hledání přímo). Viz sifrovani.py."""
    import base64
    import os
    import sifrovani
    from zdroje import http
    http.procisti_cache()
    hledej(list(TITULY))
    sekce, ted = posledni()
    web = KOREN / "web"
    web.mkdir(exist_ok=True)
    stranka = prehled.html(sekce, ted, akce_url=os.environ.get("AKCE_URL"),
                           akce_token=os.environ.get("AKTUALIZACE_TOKEN") or None,
                           akce_repo=os.environ.get("GITHUB_REPOSITORY"))
    if os.environ.get("HLAVNI_KLIC"):
        soubor = KOREN / "pristupy.json"  # nastavená hesla (zamčené klíče) - workflow ho bere z gh-pages
        pristupy = [p for p in (json.loads(soubor.read_text(encoding="utf-8")) if soubor.exists() else [])
                    if sifrovani.platny_pristup(p)]
        kanal = os.environ.get("PRISTUP_KANAL")
        if kanal:
            pristupy = sifrovani.nove_pristupy(kanal, pristupy)
        (web / "pristupy.json").write_text(json.dumps(pristupy, indent=1), encoding="utf-8")
        print(f"Přístupy: {len(pristupy)} nastavených hesel" + ("" if pristupy else ", platí kód z pozvánky"))
        stranka = sifrovani.zasifruj(stranka, base64.b64decode(os.environ["HLAVNI_KLIC"]),
                                     os.environ.get("HESLO_STRANKY"), pristupy, kanal, nastaveni.nacti().get("jmeno"))
    (web / "index.html").write_text(stranka, encoding="utf-8")
    (web / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Zašifrovaná stránka: {web / 'index.html'}")
    denni_souhrn(sekce, os.environ.get("WEB_URL"))


SOUHRN_HODINY = range(20, 24)  # souhrn jde první běh po 20:00 (Praha); pozdější jen když se ten 20:07 zpozdí


def denni_souhrn(sekce: list[tuple], odkaz: str | None):
    """Jednou denně kolem 20:00: souhrn všeho, co od minulého souhrnu přibylo nebo zlevnilo (upozorneni.py)."""
    import os
    ted = datetime.now()  # workflow má TZ=Europe/Prague
    if os.environ.get("SOUHRN_TEST"):  # ruční zkouška: posledních 24 h hned, čas souhrnu se neposouvá
        od = (ted - timedelta(days=1)).isoformat(timespec="seconds")
        print("souhrn: zkušební, od", od)
        upozorneni.denni_souhrn(sekce, od, odkaz)
        return
    if ted.hour not in SOUHRN_HODINY:
        return
    c = db()
    row = c.execute("SELECT hodnota FROM meta WHERE klic='souhrn'").fetchone()
    if row and row[0][:10] == ted.date().isoformat():
        c.close()
        return  # dnes už odešel
    # první souhrn: od prvního běhu (co bylo v nabídce už tehdy, není novinka)
    od = row[0] if row else c.execute("SELECT MIN(prvni_videno) FROM inzerat").fetchone()[0] or ted.isoformat()
    if upozorneni.denni_souhrn(sekce, od, odkaz):
        c.execute("INSERT OR REPLACE INTO meta VALUES ('souhrn', ?)", (ted.isoformat(timespec="seconds"),))
        c.commit()
    c.close()


def main():
    if "--server" in sys.argv:
        return server()
    if "--cloud" in sys.argv:
        return cloud()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--prekreslit" in sys.argv:
        sekce, ted = posledni()
        PREHLED.write_text(prehled.html(sekce, ted), encoding="utf-8")
    else:
        hledej(args or list(TITULY))
    print(f"Přehled: {PREHLED}")
    if "--neotvirat" not in sys.argv:
        webbrowser.open(PREHLED.as_uri())


if __name__ == "__main__":
    main()
