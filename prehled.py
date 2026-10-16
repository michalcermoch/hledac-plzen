"""Vykreslení přehledu (prehled.html / web na localhost / zašifrovaná stránka v cloudu).

Inzerátů jsou tisíce, proto stránka nese jen data (JSON) a karty, filtry, řazení i mapu kreslí prohlížeč:
napoprvé ukáže 48 karet a další dokresluje při posouvání. Filtry (druh, okres, obec, cena, velikost,
vzdálenost) jen skrývají - nic se znovu nestahuje.
"""
import json
from datetime import datetime
from html import escape

import nastaveni
import nemovitosti
import oblast
from zdroje.http import DRUHY


def _svg(obsah: str, velikost: int = 16, tah: float = 2) -> str:
    return (f'<svg viewBox="0 0 24 24" width="{velikost}" height="{velikost}" fill="none" stroke="currentColor" '
            f'stroke-width="{tah}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{obsah}</svg>')


IKONA_LUPA = _svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>', 20, 2.2)
IKONA_FOTO = _svg('<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-8 8"/>', 36, 1.5)
IKONA_OBNOVIT = _svg('<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>', 16, 2.4)
IKONA_VEN = _svg('<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>', 13, 2.2)
IKONA_MISTO = _svg('<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>', 14)
IKONA_DUM = _svg('<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>', 22, 1.8)
IKONA_BYT = _svg('<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2M11 21v-3h2v3"/>', 22, 1.8)
IKONA_STROM = _svg('<path d="M12 22v-6"/><path d="M12 16c-4 0-7-2.5-7-6 0-3 2.5-6 7-8 4.5 2 7 5 7 8 0 3.5-3 6-7 6z"/><path d="M3 22h18"/>', 22, 1.8)
IKONA_TEL = _svg('<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>', 16, 2)
IKONA_AI = _svg('<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>', 14, 1.8)
IKONA_MAPA = _svg('<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>', 15, 2)
IKONA_FILTR = _svg('<path d="M3 5h18l-7 8v6l-4 2v-8z"/>', 15, 2)
# Ikony k údajům v detailu
IKONY_FAKT = {
    "druh": _svg('<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/>', 13),
    "dispozice": _svg('<rect x="3" y="4" width="18" height="16" rx="1"/><path d="M12 4v9M3 13h9"/>', 13),
    "plocha": _svg('<path d="M4 4h16v16H4z"/><path d="M4 9h3M4 14h3M9 4v3M14 4v3"/>', 13),
    "pozemek": _svg('<path d="M12 22v-6"/><path d="M12 16c-4 0-7-2.5-7-6 0-3 2.5-6 7-8 4.5 2 7 5 7 8 0 3.5-3 6-7 6z"/>', 13),
    "km": _svg('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>', 13),
    "okres": IKONA_MISTO,
}

IKONY_KAT = {"byty": IKONA_BYT, "domy": IKONA_DUM, "pozemky": IKONA_STROM}
PRAZDNO = {"byty": "Žádný byt teď neodpovídá zadání.", "domy": "Žádný dům teď neodpovídá zadání.",
           "pozemky": "Žádný pozemek teď neodpovídá zadání."}
MAX_FOTEK = 20      # do stránky; víc fotek je na webu inzerátu
MAX_POPIS = 5000    # znaků popisu
CENY_DO = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15]  # mil. Kč - nabídka filtru „Cena do“


def kc(n) -> str:
    return f"{int(n):,}".replace(",", " ") + " Kč" if n else "Cena na dotaz"


def cislo(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def _dni(n, minimalne: bool = False) -> str:
    """minimalne = web datum vložení neuvádí, počítá se od chvíle, kdy inzerát poprvé viděl Hledač."""
    if n is None:
        return ""
    if n == 0:
        return "poprvé viděn dnes" if minimalne else "vloženo dnes"
    return f"v nabídce {'min. ' if minimalne else ''}{n} {'den' if n == 1 else 'dny' if n < 5 else 'dní'}"


def _zlevneno(i: dict) -> int:
    return i["puvodni_cena"] - i["cena"] if i.get("cena") and i.get("puvodni_cena") and i["cena"] < i["puvodni_cena"] else 0


def _zlevneni(i: dict) -> int:
    """Kolikrát inzerát zlevnil (podle uložené historie cen)."""
    ceny = [c for _, c in i.get("historie_cen") or [] if c]
    return sum(1 for a, b in zip(ceny, ceny[1:]) if b < a)


def _trh_text(t: dict) -> str:
    proc = round(abs(t["rozdil"]) * 100)
    if proc < 3:
        return f"cena za m² jako průměr ({t['zaklad']})"
    return f"o {proc} % {'pod' if t['rozdil'] < 0 else 'nad'} průměrem ({t['zaklad']})"


def data(i: dict) -> dict:
    """Údaje jednoho inzerátu pro stránku (karta, filtry, mapa i detail) - vkládají se jako JSON."""
    fotky = i.get("fotky") or ([i["foto"]] if i.get("foto") else [])
    popis = i.get("popis") or ""
    if len(popis) > MAX_POPIS:
        popis = popis[:MAX_POPIS].rsplit(" ", 1)[0] + " …"
    return {
        "nazev": i["nazev"], "cena": i.get("cena"), "zlevneno": _zlevneno(i), "zlevneni": _zlevneni(i),
        "novy": bool(i.get("novy")), "druh": i.get("druh") or "", "dispozice": i.get("dispozice") or "",
        "plocha": i.get("plocha"), "pozemek": i.get("pozemek"),
        "obec": (i.get("mesto") or "").strip(), "cast": i.get("cast") or "", "okres": i.get("okres") or "",
        "misto": i.get("misto") or "", "vzdalenost": i.get("vzdalenost"),
        "gps": [round(x, 5) for x in i["gps"]] if i.get("gps") else None, "gps_odhad": i.get("gps_odhad"),
        "fotky": fotky[:MAX_FOTEK], "popis": popis, "parametry": i.get("parametry") or [],
        "odkazy": i.get("odkazy") or [(i["zdroj"], i["url"])], "url": i["url"], "zdroj": i["zdroj"],
        "telefon": i.get("telefon"), "dni": i.get("dni"), "dni_text": _dni(i.get("dni"), i.get("dni_min")),
        "historie_cen": i.get("historie_cen") or [], "znovu": i.get("znovu"),
        "trh": i.get("trh"), "trh_text": _trh_text(i["trh"]) if i.get("trh") else "", "ai": i.get("ai"),
    }


def _statistiky(kat: str, inz: list[dict], aktivni: bool) -> str:
    ceny = [i["cena"] for i in inz if i.get("cena")]
    novych = sum(bool(i.get("novy")) for i in inz)
    zlevneno = sum(1 for i in inz if _zlevneno(i))
    dlazdice = [("Inzerátů", len(inz), "", "", ""), ("Nových od minula", novych, " pos" if novych else "", "", "novy"),
                ("Zlevněných", zlevneno, " drop" if zlevneno else "", "", "zlev"),
                ("Nejlevnější", min(ceny) if ceny else 0, " wide", " Kč" if ceny else "", "")]
    # Nové / zlevněné jdou rozkliknout: přehled se vyfiltruje jen na ně (znovu kliknout = zrušit).
    polozky = "".join(
        (f'<div class="stat{c} klik" data-filtr="{filtr}" role="button" tabindex="0" title="Ukázat jen tyto inzeráty"'
         if filtr and hodnota else f'<div class="stat{c}"') +
        f' style="--d:{n * 80}ms"><span>{nazev}</span>'
        f'<strong data-cil="{hodnota}" data-pripona="{pripona}">{cislo(hodnota) + pripona if hodnota or not c.strip() == "wide" else "–"}</strong></div>'
        for n, (nazev, hodnota, c, pripona, filtr) in enumerate(dlazdice))
    return f'<div class="stats" data-t="{kat}" {"" if aktivni else "hidden"}>{polozky}</div>'


def _hledam(kat: str) -> str:
    return '<div class="criteria">' + "".join(
        '<div class="crit"><span class="lbl">Co hledám</span>' + "".join(
            f'<span class="chip">{escape(p)}</span>' for p in parametry) + "</div>"
        for _, parametry in nemovitosti.POPIS[kat]) + "</div>"


def _stav_webu(weby: list[dict]) -> str:
    """Panel: který web jak odpověděl a kolik vrátil - změna struktury webu se pozná hned (0 nebo chyba)."""
    if not weby:
        return ""
    chyby = [w for w in weby if not w.get("ok")]
    prazdne = [w for w in weby if w.get("ok") and not w.get("pocet")]
    if chyby:
        souhrn, trida = f"{len(chyby)} {'web hlásí' if len(chyby) == 1 else 'weby hlásí'} chybu", "err"
    elif prazdne:
        souhrn, trida = f"{len(prazdne)} bez výsledků – možná změna webu", "warn"
    else:
        souhrn, trida = f"všech {len(weby)} v pořádku", "ok"
    radky = []
    for w in weby:
        stav = "err" if not w.get("ok") else "warn" if w in prazdne else "ok"
        popis = (escape(w.get("chyba", "")[:90]) if not w.get("ok")
                 else f'{cislo(w.get("pocet", 0))} staženo · {cislo(w.get("vybrano", 0))} v okruhu a do ceny')
        radky.append(f'<tr class="{stav}"><td><i></i>{escape(w["nazev"])}</td><td>{popis}</td><td>{w.get("sekund", 0)} s</td></tr>')
    return (f'<details class="weby {trida}"><summary><span class="dot"></span>Stav webů: {souhrn}</summary>'
            f'<table>{"".join(radky)}</table></details>')


def _filtry(kat: str) -> str:
    """Kostra panelu filtrů; štítky druhů, okresů a seznam obcí doplní prohlížeč podle dat."""
    ceny = "".join(f'<option value="{c * 1_000_000}">{c} mil. Kč</option>' for c in CENY_DO)
    pozemek = ('<label class="pole"><span>Pozemek od</span><input type="number" class="f-poz" min="0" step="50" '
               'inputmode="numeric" placeholder="m²"></label>') if kat == "domy" else ""
    velikost = "Plocha pozemku" if kat == "pozemky" else "Užitná plocha"
    return f"""<div class="filtry" data-t="{kat}">
  <div class="f-radek"><span class="lbl">{"Dispozice" if kat == "byty" else "Druh"}</span><div class="volby f-druh"></div></div>
  <div class="f-radek"><span class="lbl">Okres</span><div class="volby f-okres"></div></div>
  <div class="f-pole">
    <label class="pole obec"><span>Obec / město</span><input type="search" class="f-obec" list="obce-{kat}" placeholder="např. Chotíkov" autocomplete="off"><datalist id="obce-{kat}"></datalist></label>
    <label class="pole"><span>Cena do</span><select class="f-cena"><option value="">bez omezení</option>{ceny}</select></label>
    <label class="pole"><span>{velikost} od</span><input type="number" class="f-od" min="0" step="10" inputmode="numeric" placeholder="m²"></label>
    <label class="pole"><span>do</span><input type="number" class="f-do" min="0" step="10" inputmode="numeric" placeholder="m²"></label>
    {pozemek}
    <label class="pole km"><span>Od centra Plzně do <output class="f-km-v">{oblast.OKRUH_KM} km</output></span><input type="range" class="f-km" min="1" max="{oblast.OKRUH_KM}" step="1" value="{oblast.OKRUH_KM}"></label>
    <button type="button" class="f-reset">Zrušit filtry</button>
  </div>
</div>"""


def sekce(kat: str, inz: list[dict], hlasky: list[str], weby: list[dict], aktivni: bool) -> str:
    chyby = "".join(f'<div class="error">⚠ {escape(h)}</div>' for h in hlasky)
    if inz:
        obsah = (f'{_filtry(kat)}<div class="vysledek"><span class="f-pocet"></span>'
                 f'<button type="button" class="mapa-prepinac" aria-pressed="true">{IKONA_MAPA}<span>Mapa</span></button></div>'
                 f'<div class="mapa-obal"><div class="mapa"></div></div>'
                 f'<div class="grid"></div><div class="dalsi" hidden><button type="button" class="btn ghost">Ukázat další</button></div>'
                 f'<p class="none" hidden>Nic neodpovídá zvoleným filtrům. <button type="button" class="f-reset odkaz">Zrušit filtry</button></p>')
    else:
        obsah = (f'<div class="empty"><div class="pulse">{IKONY_KAT[kat]}</div><h3>Zatím nic</h3>'
                 f'<p>{escape(PRAZDNO[kat])}</p></div>')
    return (f'<section id="s-{kat}" data-t="{kat}" {"" if aktivni else "hidden"}>'
            f'<div class="info-radek">{_hledam(kat)}{_stav_webu(weby)}</div>{chyby}{obsah}</section>')


def html(sekce_data: list[tuple], ted: str, mobil_url: str | None = None, akce_url: str | None = None,
         akce_token: str | None = None, akce_repo: str | None = None) -> str:
    """akce_url = statická stránka v cloudu: tlačítko Aktualizovat spustí hledání na GitHubu. S akce_token (jen práva
    Actions repa akce_repo) přímo přes API, jinak otevře stránku workflow. Token je jen v zašifrované stránce."""
    sekce_data = [(tuple(s) + ([],) * 4)[:4] for s in sekce_data]  # (kategorie, inzeráty, hlášky, stav webů)
    nast = nastaveni.nacti()
    jmeno, osloveni = nast.get("jmeno") or "", nast.get("osloveni") or nast.get("jmeno") or ""

    def zalozka(n, kat, inz):
        novych = sum(bool(i.get("novy")) for i in inz)
        return (f'<button role="tab" data-t="{kat}" aria-selected="{"true" if n == 0 else "false"}">'
                f'{nemovitosti.KATEGORIE[kat]["titul"]}<span class="count">{len(inz)}</span>'
                f'{f"<span class=new-dot>+{novych}</span>" if novych else ""}</button>')

    zalozky = "".join(zalozka(n, kat, inz) for n, (kat, inz, _, _) in enumerate(sekce_data))
    statistiky = "".join(_statistiky(kat, inz, n == 0) for n, (kat, inz, _, _) in enumerate(sekce_data))
    obsah = "".join(sekce(kat, inz, hl, weby, n == 0) for n, (kat, inz, hl, weby) in enumerate(sekce_data))
    popisky = {kat: {"titul": nemovitosti.KATEGORIE[kat]["titul"],
                     "pod": f'{cislo(len(inz))} {"inzerátů" if len(inz) != 1 else "inzerát"} z {len(nemovitosti.WEBY)} webů'}
               for kat, inz, _, _ in sekce_data}
    d = datetime.fromisoformat(ted)
    # "<" escapovat, aby text inzerátu nemohl ukončit <script>
    json_data = json.dumps({"inzeraty": {kat: [data(i) for i in inz] for kat, inz, _, _ in sekce_data},
                            "druhy": DRUHY, "popisky": popisky, "stred": oblast.STRED, "okruh": oblast.OKRUH_KM * 1000,
                            "stred_popis": oblast.STRED_POPIS, "okresy": [o for o, _ in oblast.OKRESY],
                            "akce_url": akce_url, "akce_token": akce_token, "akce_repo": akce_repo},
                           ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    prvni = sekce_data[0][0]
    titulek = f"Hledač · {jmeno}" if jmeno else "Hledač nemovitostí"
    pozdrav = (f"Ahoj {escape(osloveni)}! " if osloveni else "") + f"Nemovitosti na prodej v Plzni a do {oblast.OKRUH_KM} km kolem."
    return f"""<!doctype html>
<html lang="cs"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{escape(titulek)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>{CSS}</style></head>
<body>
<header class="hero">
  <div class="aurora" aria-hidden="true"><i class="b1"></i><i class="b2"></i><i class="b3"></i></div>
  <div class="wrap">
    <div class="hero-top">
      <div class="brand"><span class="logo">{IKONA_DUM}</span><b>Hledač{f' <em>· {escape(jmeno)}</em>' if jmeno else ''}</b></div>
      <div class="akce">{f'<a class="mobil" href="{mobil_url}" title="Stejná adresa funguje na telefonu ve stejné Wi-Fi">{IKONA_TEL}na mobilu: {mobil_url.replace("http://", "").rstrip("/")}</a>' if mobil_url else ""}<span class="prubeh" id="prubeh" hidden></span>
        <button class="obnovit" id="obnovit" hidden title="Znovu prohledat všechny weby">{IKONA_OBNOVIT}<span>Aktualizovat</span></button></div>
    </div>
    <div class="hero-main">
      <div><p class="pozdrav">{pozdrav}</p><h1 id="heroTitul">{popisky[prvni]["titul"]}</h1>
        <p id="heroPod">{popisky[prvni]["pod"]} · staženo {d.day}. {d.month}. v {d:%H:%M}</p></div>
      {statistiky}
    </div>
  </div>
  <div class="pruh" aria-hidden="true"></div>
</header>
<div class="toolbar" id="toolbar"><div class="wrap"><div class="tb-row">
  <nav class="tabs" role="tablist"><span class="ind" aria-hidden="true"></span>{zalozky}</nav>
  <div class="sp"></div>
  <label class="razeni-obal">{IKONA_FILTR}<span>Řadit</span><select id="razeni" aria-label="Řazení">
    <option value="novy">nové první</option><option value="cena">nejlevnější</option><option value="-cena">nejdražší</option>
    <option value="-plocha">největší</option><option value="plocha">nejmenší</option><option value="m2">nejnižší cena za m²</option>
    <option value="km">nejblíž centru</option><option value="dni">nejdéle v nabídce</option></select></label>
  <label class="switch"><input type="checkbox" id="jenNove"><span></span>Jen nové</label>
</div></div></div>
<main class="wrap">{obsah}</main>
<footer class="foot wrap">Hledač nemovitostí{f' pro {escape(jmeno)}' if jmeno else ''} · {", ".join(nemovitosti.WEBY)} · staženo {d.day}. {d.month}. {d.year} v {d:%H:%M} · mapa © OpenStreetMap</footer>
<div class="toast" id="toast" role="status" aria-live="polite" hidden></div>
{DETAIL}
<script type="application/json" id="data">{json_data}</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>{JS}</script>
</body></html>"""


CSS = """
/* Paleta pro Domču: teplé světlé plochy, lesní zelená a jantarová (dům a zahrada).
   Proměnné se jmenují jako v Hledači bytů a aut (navy = hlavní tmavá, carolina = akcent). */
:root{--bg:#eeebe3;--surface:#fcfbf7;--surface-2:#f2efe6;--text:#1d3328;--muted:#6b685f;--line:#dcd6c8;
--navy:#1f4a37;--navy-2:#13301f;--carolina:#d9a441;--carolina-light:#e9c47a;--sky:#f1d9a6;--accent:#2f7a55;
--accent-soft:#e2efe6;--on-carolina:#2a1c04;--titan:#8a8d90;--pos:#2f7a55;--drop:#c0581c;--drop-soft:#f8e4d6;
--err:#b42318;--err-soft:#fbe9e7;--r:20px;--ease:cubic-bezier(.2,.8,.2,1);
--shadow:0 1px 2px rgba(29,51,40,.05),0 8px 24px -8px rgba(29,51,40,.14);
--shadow-hover:0 2px 6px rgba(29,51,40,.08),0 22px 48px -12px rgba(29,51,40,.32);color-scheme:light}
*{box-sizing:border-box}[hidden]{display:none!important}html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;
-webkit-font-smoothing:antialiased;font-feature-settings:"tnum" 1}
a{color:inherit}code{font:12px ui-monospace,Consolas,monospace;background:var(--surface-2);padding:1px 6px;border-radius:5px}
h1,h2,h3,.price,.stat strong,.brand b{font-family:"Plus Jakarta Sans",Inter,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding-left:24px;padding-right:24px}
button{font:inherit;color:inherit}

/* --- hero s pomalu se přelévajícím světlem --- */
.hero{position:relative;overflow:hidden;background:linear-gradient(135deg,#10251c 0%,var(--navy) 45%,#2f6b4f 100%);color:#f4f1ea;
padding-bottom:22px}
.aurora{position:absolute;inset:0;pointer-events:none;filter:blur(60px);opacity:.75}
.aurora i{position:absolute;border-radius:50%;mix-blend-mode:screen}
.aurora .b1{width:520px;height:520px;left:-120px;top:-220px;background:radial-gradient(circle,var(--carolina) 0%,transparent 65%);animation:plyn1 18s ease-in-out infinite alternate}
.aurora .b2{width:460px;height:460px;right:-80px;top:-120px;background:radial-gradient(circle,var(--sky) 0%,transparent 60%);animation:plyn2 22s ease-in-out infinite alternate}
.aurora .b3{width:600px;height:420px;left:35%;bottom:-300px;background:radial-gradient(circle,#c9b99b 0%,transparent 60%);opacity:.55;animation:plyn3 26s ease-in-out infinite alternate}
@keyframes plyn1{to{transform:translate(260px,120px) scale(1.2)}}
@keyframes plyn2{to{transform:translate(-220px,90px) scale(.85)}}
@keyframes plyn3{to{transform:translate(-160px,-60px) scale(1.15)}}
.hero::after{content:"";position:absolute;inset:0;pointer-events:none;opacity:.35;
background-image:radial-gradient(rgba(255,255,255,.18) 1px,transparent 1px);background-size:22px 22px;
-webkit-mask-image:linear-gradient(180deg,#000,transparent 85%)}
.hero .wrap{position:relative;z-index:1}
.hero-top{display:flex;align-items:center;justify-content:space-between;gap:16px;height:60px}
.brand{display:flex;align-items:center;gap:12px}.brand b{font-size:19px;font-weight:800;letter-spacing:-.02em}
.logo{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;color:var(--navy);
background:linear-gradient(135deg,#fff,var(--carolina-light));box-shadow:0 6px 18px rgba(217,164,65,.45)}
.akce{display:flex;align-items:center;gap:12px}
.obnovit{display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:14px;padding:10px 16px;border-radius:12px;cursor:pointer;
color:#fff;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);backdrop-filter:blur(10px);
transition:background .2s,transform .2s var(--ease)}
.obnovit:hover{background:rgba(255,255,255,.22);transform:translateY(-1px)}.obnovit:disabled{cursor:progress}
.obnovit.bezi svg{animation:toc 1s linear infinite}@keyframes toc{to{transform:rotate(360deg)}}
.prubeh{font-size:12px;color:rgba(244,241,234,.8);max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hero-main{display:flex;align-items:flex-end;justify-content:space-between;gap:28px;flex-wrap:wrap;padding-top:8px}
.hero h1{margin:0;font-size:40px;line-height:1;font-weight:800;letter-spacing:-.035em;
background:linear-gradient(180deg,#fff 30%,var(--sky));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{margin:6px 0 0;color:rgba(244,241,234,.78);font-size:15px}
.stats{display:flex;gap:12px;flex-wrap:wrap}
.stat{min-width:118px;padding:10px 16px;border-radius:16px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.16);
backdrop-filter:blur(12px);animation:vyjed .7s var(--ease) both;animation-delay:var(--d)}
.stat span{display:block;font-size:12px;color:rgba(244,241,234,.7);font-weight:500}
.stat strong{display:block;font-size:22px;font-weight:800;letter-spacing:-.02em;margin-top:2px;white-space:nowrap}
.stat.pos strong{color:var(--sky)}.stat.drop strong{color:#f3c47a}
.stat.klik{cursor:pointer;transition:background .2s,border-color .2s,transform .2s var(--ease)}.stat.klik span:after{content:"  ›";opacity:.8}
.stat.klik:hover{background:rgba(255,255,255,.16);transform:translateY(-2px)}.stat.klik.on{border-color:var(--sky);background:rgba(233,196,122,.22)}
@keyframes vyjed{from{opacity:0;transform:translateY(14px)}}

/* --- nástrojová lišta (lepí se nahoru) --- */
.toolbar{position:sticky;top:0;z-index:6;background:color-mix(in srgb,var(--bg) 82%,transparent);backdrop-filter:blur(14px) saturate(1.4);
border-bottom:1px solid transparent;transition:box-shadow .25s,border-color .25s,background .25s}
.toolbar.stuck{border-color:var(--line);box-shadow:0 8px 24px -14px rgba(29,51,40,.35);background:color-mix(in srgb,var(--surface) 88%,transparent)}
.toolbar .wrap{padding-top:10px;padding-bottom:10px}
.tb-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.sp{flex:1}
.tabs{position:relative;display:flex;gap:2px;background:var(--surface);border:1px solid var(--line);padding:4px;border-radius:14px;box-shadow:var(--shadow)}
.tabs .ind{position:absolute;top:4px;bottom:4px;left:0;width:0;border-radius:10px;background:var(--navy);
box-shadow:0 4px 14px rgba(29,51,40,.35);transition:transform .45s var(--ease),width .45s var(--ease)}
.tabs button{position:relative;z-index:1;border:0;background:none;cursor:pointer;font-weight:600;color:var(--muted);
padding:8px 16px;border-radius:10px;display:flex;align-items:center;gap:8px;transition:color .3s}
.tabs button[aria-selected=true]{color:#fff}
.count{font-size:12px;padding:0 7px;border-radius:99px;line-height:20px;background:rgba(29,51,40,.08);transition:background .3s}
.tabs button[aria-selected=true] .count{background:rgba(255,255,255,.18)}
.new-dot{font-size:12px;color:var(--accent);font-weight:700}.tabs button[aria-selected=true] .new-dot{color:var(--sky)}
.pills{display:flex;gap:6px;margin-top:8px;overflow-x:auto;scrollbar-width:none;padding:2px 0 4px}.pills[hidden]{display:none}
.pills::-webkit-scrollbar{display:none}.pill{flex:none;white-space:nowrap}
.pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--surface);color:var(--text);cursor:pointer;
font-size:12.5px;font-weight:600;padding:4px 11px;border-radius:99px;transition:all .25s var(--ease)}
.pill span{font-size:11px;color:var(--muted);background:var(--surface-2);border-radius:99px;padding:0 6px;line-height:18px;transition:inherit}
.pill:hover{border-color:var(--carolina);transform:translateY(-1px)}
.pill.on{background:var(--carolina-light);border-color:var(--carolina-light);color:var(--on-carolina);box-shadow:0 4px 12px -2px rgba(217,164,65,.55)}
.pill.on span{background:rgba(16,37,28,.12);color:var(--on-carolina)}
.seg{display:flex;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:3px}
.seg button{border:0;background:none;cursor:pointer;font-size:13px;font-weight:600;color:var(--muted);padding:6px 12px;border-radius:9px;transition:all .25s}
.seg button.on{background:var(--surface-2);color:var(--text);box-shadow:inset 0 0 0 1px var(--line)}
.switch{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:500;cursor:pointer;user-select:none}
.switch input{position:absolute;opacity:0}.switch span{width:38px;height:22px;border-radius:99px;background:#cdc6b6;position:relative;transition:background .25s}
.switch span:after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;
box-shadow:0 1px 3px rgba(0,0,0,.3);transition:transform .3s var(--ease)}
.switch input:checked+span{background:var(--carolina)}.switch input:checked+span:after{transform:translateX(16px)}
.switch input:focus-visible+span{outline:2px solid var(--accent);outline-offset:2px}

/* --- obsah --- */
main.wrap{padding-top:14px;padding-bottom:48px}
section{animation:prolni .5s var(--ease)}@keyframes prolni{from{opacity:0;transform:translateY(8px)}}
.criteria{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;margin-bottom:18px;color:var(--muted);font-size:13px}
.criteria .lbl{font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:11px}
.crit{display:flex;flex-wrap:wrap;align-items:center;gap:6px}.crit b{color:var(--text);font-size:13px;margin-right:2px}
.crit[hidden]{display:none}.crit .lbl{margin-right:6px}.criteria.vyber .crit{animation:prolni .35s var(--ease)}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:500;padding:3px 9px;border-radius:8px;
background:var(--surface-2);border:1px solid var(--line);white-space:nowrap}.chip svg{color:var(--titan)}
.weby{position:relative}.weby[open]>table,.weby[open]>.panel{position:absolute;right:0;top:100%;z-index:5}



.btns{display:flex;gap:8px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:6px;font-weight:600;font-size:13px;text-decoration:none;padding:8px 13px;border-radius:10px;
background:var(--navy);color:#fff;border:1px solid var(--navy);transition:transform .2s var(--ease),box-shadow .2s}
.btn:hover{transform:translateY(-1px);box-shadow:0 6px 16px -6px rgba(29,51,40,.6)}
.btn.ghost{background:var(--accent-soft);color:var(--accent);border-color:transparent}
.error{background:var(--err-soft);color:var(--err);border-radius:12px;padding:10px 14px;margin-bottom:14px;font-size:14px}

/* --- karty --- */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:22px}
.card{background:var(--surface);border-radius:var(--r);overflow:hidden;display:flex;flex-direction:column;box-shadow:var(--shadow);
border:1px solid rgba(29,51,40,.06);opacity:0;transform:translateY(22px) scale(.985);
transition:opacity .6s var(--ease),transform .6s var(--ease),box-shadow .35s var(--ease);transition-delay:var(--d,0ms)}
.card.in{opacity:1;transform:none}
/* jantarové podsvícení karty po najetí myší */
.card.in:hover{transform:translateY(-6px);transition-delay:0ms;border-color:rgba(217,164,65,.9);
box-shadow:0 0 0 2px rgba(233,196,122,.7),0 0 48px 10px rgba(233,196,122,.45),0 30px 70px -12px rgba(160,110,30,.4)}
.media{position:relative;aspect-ratio:4/3;overflow:hidden;cursor:zoom-in;
background:linear-gradient(100deg,var(--surface-2) 30%,#f7f4ec 50%,var(--surface-2) 70%) 0 0/300% 100%;animation:shimmer 1.6s linear infinite}
.media.nacteno{animation:none;background:var(--surface-2)}
@keyframes shimmer{to{background-position:-150% 0}}
.media img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;
transition:transform .9s var(--ease),opacity .28s ease}
.media img.skryto{opacity:0}
.card:hover .media img{transform:scale(1.07)}
.nophoto{position:absolute;inset:0;display:grid;place-content:center;justify-items:center;gap:4px;color:var(--titan);font-size:12px;
background:repeating-linear-gradient(45deg,var(--surface-2) 0 14px,#ebe6da 14px 28px)}
.shade{position:absolute;inset:0;pointer-events:none;background:linear-gradient(180deg,rgba(16,37,28,.35) 0%,transparent 28%,transparent 48%,rgba(16,37,28,.88) 100%)}
.overlay{position:absolute;left:0;right:0;bottom:0;padding:14px 16px;color:#fff;pointer-events:none}
.overlay .price{font-size:26px;font-weight:800;letter-spacing:-.025em;line-height:1.1;text-shadow:0 2px 12px rgba(0,0,0,.35);
display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.overlay .price small{font-family:Inter,sans-serif;font-size:12px;font-weight:500;opacity:.85;letter-spacing:0}
.loc{display:flex;align-items:center;gap:5px;font-size:12.5px;opacity:.9;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.badges{position:absolute;top:12px;left:12px;display:flex;gap:6px;z-index:2}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;padding:4px 9px;border-radius:8px;
box-shadow:0 4px 12px rgba(0,0,0,.25);backdrop-filter:blur(6px)}
.badge-new{background:rgba(255,255,255,.92);color:var(--navy)}
.badge-new i{width:7px;height:7px;border-radius:50%;background:var(--carolina);box-shadow:0 0 0 0 rgba(217,164,65,.7);animation:tep 1.8s infinite}
@keyframes tep{70%{box-shadow:0 0 0 7px rgba(217,164,65,0)}100%{box-shadow:0 0 0 0 rgba(217,164,65,0)}}
.badge-drop{background:var(--drop);color:#fff}
.tag{position:absolute;top:12px;right:12px;z-index:2;font-size:11.5px;font-weight:600;padding:4px 9px;border-radius:8px;color:#fff;
background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.3);backdrop-filter:blur(8px)}
.nav{position:absolute;top:44%;transform:translateY(-50%) scale(.85);width:36px;height:36px;border-radius:50%;border:0;cursor:pointer;z-index:3;
display:grid;place-items:center;font:600 22px/1 Inter,sans-serif;padding-bottom:3px;color:var(--navy);background:rgba(255,255,255,.9);
box-shadow:0 4px 14px rgba(0,0,0,.3);opacity:0;transition:opacity .25s,transform .25s var(--ease)}
.nav.prev{left:12px}.nav.next{right:12px}.nav:hover{background:#fff}
.media:hover .nav,.nav:focus-visible{opacity:1;transform:translateY(-50%) scale(1)}
@media (hover:none){.card .nav{opacity:.85;transform:translateY(-50%) scale(.9)}}
.dots{position:absolute;bottom:14px;right:16px;display:flex;gap:5px;z-index:2}
.dots i{width:6px;height:6px;border-radius:99px;background:rgba(255,255,255,.5);transition:width .3s var(--ease),background .3s}
.dots i.on{width:18px;background:#fff}
.media .counter{display:none}
.body{padding:14px 18px 12px;flex:1;display:flex;flex-direction:column;gap:10px}
.card h3{margin:0;font-size:15.5px;font-weight:700;line-height:1.35;letter-spacing:-.01em;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card h3 a{text-decoration:none;cursor:pointer;background:linear-gradient(var(--carolina),var(--carolina)) 0 100%/0 2px no-repeat;
transition:background-size .35s var(--ease)}.card h3 a:hover{background-size:100% 2px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.radek{margin:0;font-size:13.5px;font-weight:600;color:var(--text);line-height:1.5}
.radek span{white-space:nowrap}.radek i{font-style:normal;color:var(--titan);margin:0 6px;font-weight:400}.radek .nevi{color:var(--muted);font-weight:400}
.hist{display:flex;flex-wrap:wrap;gap:6px;align-items:flex-start;align-content:flex-start}
.h{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:600;padding:3px 9px;border-radius:99px}
.h.ok{background:#e1f0e4;color:#23693a;box-shadow:inset 0 0 0 1px #bfdcc6}.h.ok svg{color:#2f8a4c}
.h.nevi{color:var(--muted);box-shadow:inset 0 0 0 1px var(--line);font-weight:500}.h.nevi svg{opacity:.7}
.h.inf{background:var(--accent-soft);color:var(--accent);box-shadow:inset 0 0 0 1px #c6dfcf}
.h.zle{background:var(--err-soft);color:var(--err);box-shadow:inset 0 0 0 1px #f2c3bd}
.chip.nevi{background:none;border-style:dashed;color:var(--muted)}
.warn{font-size:12px;color:var(--drop);background:var(--drop-soft);padding:4px 9px;border-radius:8px;align-self:flex-start}
.card footer{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:11px 18px;border-top:1px solid var(--line);font-size:12px}
.seen{color:var(--muted);white-space:nowrap}.srcs{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.src{display:inline-flex;align-items:center;gap:4px;font-weight:600;color:var(--accent);text-decoration:none;padding:3px 9px;border-radius:7px;
background:var(--accent-soft);transition:background .2s,color .2s}.src:hover{background:var(--carolina-light);color:var(--on-carolina)}
.empty{text-align:center;padding:64px 20px;border-radius:24px;background:var(--surface);box-shadow:var(--shadow);color:var(--muted)}
.pulse{position:relative;width:84px;height:84px;margin:0 auto;border-radius:50%;display:grid;place-items:center;color:#fff;
background:linear-gradient(135deg,var(--carolina-light),var(--navy))}
.pulse svg{width:34px;height:34px}
.pulse:before,.pulse:after{content:"";position:absolute;inset:0;border-radius:50%;border:2px solid var(--carolina-light);animation:vlna 2.6s var(--ease) infinite}
.pulse:after{animation-delay:1.3s}@keyframes vlna{from{transform:scale(1);opacity:.8}to{transform:scale(1.8);opacity:0}}
.empty h3{color:var(--text);margin:22px 0 6px;font-size:22px}.empty p{max-width:470px;margin:0 auto}
.none{color:var(--muted);text-align:center;padding:30px}
.foot{color:var(--muted);font-size:12px;padding-bottom:32px}

/* --- okno s detailem --- */
html:has(dialog[open]){overflow:hidden}
dialog#detail{width:min(1200px,calc(100% - 32px));max-height:calc(100dvh - 32px);padding:0;border:0;border-radius:24px;
background:var(--surface);color:var(--text);box-shadow:0 30px 90px rgba(16,37,28,.45);overflow:auto}
dialog#detail[open]{animation:okno .45s var(--ease)}
@keyframes okno{from{opacity:0;transform:translateY(24px) scale(.97)}}
dialog#detail::backdrop{background:rgba(16,37,28,.6);backdrop-filter:blur(6px);animation:pozadi .35s ease}
@keyframes pozadi{from{opacity:0}}
.dlg{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);position:relative}
.close{position:absolute;top:14px;right:14px;z-index:3;width:40px;height:40px;border-radius:50%;border:0;cursor:pointer;
font:400 26px/1 Inter,sans-serif;color:var(--navy);background:rgba(255,255,255,.92);box-shadow:0 4px 14px rgba(0,0,0,.2);transition:transform .3s var(--ease)}
.close:hover{transform:rotate(90deg)}
/* galerie jen na výšku fotky + náhledů + tlačítek (dřív se natahovala na výšku pravého sloupce
   a pod náhledy zůstávala prázdná tmavá plocha) */
.gal{background:#0d1622;display:flex;flex-direction:column;min-width:0;align-self:start;border-bottom-right-radius:18px;overflow:hidden}
.stage{position:relative;aspect-ratio:4/3;display:grid;place-items:center;overflow:hidden;touch-action:pan-y}
.stage img{max-width:100%;max-height:100%;object-fit:contain;display:block;transition:opacity .25s ease}
.stage img.skryto{opacity:0}
.stage .nav{opacity:.95;transform:translateY(-50%);width:46px;height:46px;font-size:26px;top:50%}
.stage .nav.prev{left:16px}.stage .nav.next{right:16px}
.stage .counter{position:absolute;bottom:14px;right:14px;font-size:12px;font-weight:600;color:#fff;background:rgba(16,37,28,.7);
padding:3px 10px;border-radius:99px;backdrop-filter:blur(4px)}
.bezfotek{display:flex;flex-direction:column;align-items:center;gap:10px;color:#8f9aa6;font-size:14px}.bezfotek svg{width:56px;height:56px}
.thumbs{display:flex;gap:8px;padding:10px;overflow-x:auto;scrollbar-width:thin;background:#0a111b}
.thumbs button{flex:none;width:80px;height:58px;padding:0;border:2px solid transparent;border-radius:8px;overflow:hidden;cursor:pointer;
opacity:.5;background:#1b2533;transition:opacity .2s,border-color .2s,transform .2s var(--ease)}
.thumbs button img{width:100%;height:100%;object-fit:cover;display:block}
.thumbs button:hover{opacity:.9;transform:translateY(-2px)}.thumbs button[aria-current=true]{border-color:var(--carolina-light);opacity:1}
.info{padding:26px 28px;display:flex;flex-direction:column;gap:12px;min-width:0}
.info .tagline{display:flex;gap:6px;flex-wrap:wrap;padding-right:48px}
.info .tagline span{font-size:12px;font-weight:700;padding:4px 9px;border-radius:8px;background:var(--accent-soft);color:var(--accent)}
.info .tagline .badge-new{background:var(--carolina-light);color:var(--on-carolina)}.info .tagline .badge-drop{background:var(--drop);color:#fff}
.info h2{margin:0;font-size:22px;line-height:1.25;letter-spacing:-.02em}
.info .price{font-size:34px;font-weight:800;letter-spacing:-.03em;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;
background:linear-gradient(90deg,var(--navy),var(--accent));-webkit-background-clip:text;background-clip:text;color:transparent}
.info .price small{font-family:Inter,sans-serif;font-size:13px;font-weight:500;color:var(--muted);-webkit-text-fill-color:var(--muted)}
.meta{font-size:13px;color:var(--muted)}
.params{display:grid;grid-template-columns:auto 1fr;gap:8px 18px;margin:4px 0 0;font-size:14px;border-top:1px solid var(--line);padding-top:14px}
.params dt{color:var(--muted)}.params dd{margin:0;font-weight:600;overflow-wrap:anywhere}
.info .btns{margin-top:auto;padding-top:8px}
.texty{grid-column:1/-1;padding:6px 28px 28px;border-top:1px solid var(--line);display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:28px}
.texty h4{margin:20px 0 10px;font-size:11.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}
.popis{white-space:pre-line;font-size:14.5px;line-height:1.65;overflow-wrap:anywhere}
.popis.zkraceny{max-height:15em;overflow:hidden;-webkit-mask-image:linear-gradient(#000 65%,transparent)}
.vice{font-size:13px;font-weight:600;color:var(--accent);background:none;border:0;padding:8px 0;cursor:pointer}
.vybava{display:flex;flex-wrap:wrap;gap:6px;align-content:flex-start}

@media (max-width:860px){.dlg{grid-template-columns:1fr}.gal{border-radius:0}.texty{grid-template-columns:1fr;gap:0}
dialog#detail{width:100%;max-width:100%;max-height:100dvh;height:100dvh;border-radius:0;margin:0}.info{padding:20px 18px}.texty{padding:0 18px 26px}}
@media (max-width:720px){.wrap{padding-left:16px;padding-right:16px}.hero h1{font-size:32px}.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px}.stat{min-width:0;padding:12px 14px}
.stat strong{font-size:clamp(17px,5.6vw,24px)}.chip{white-space:normal}
.obnovit span,.prubeh{display:none}.obnovit{padding:10px 12px}.grid{grid-template-columns:1fr}.sp{display:none}
.toolbar{overflow-x:clip}.tb-row{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none}.tb-row>*{flex:none}}
@media (prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}.card{opacity:1;transform:none}}

.info-radek{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:flex-end;gap:8px 10px;margin-bottom:14px}
.info-radek .criteria{margin-bottom:0;flex:1 1 520px}
.chip.hl{background:var(--accent-soft);border-color:#c6dfcf;color:var(--accent);font-weight:600}.chip.hl svg{color:var(--accent)}
.card footer .seen{display:inline-flex;align-items:center;gap:5px}
.card footer .seen.dlouho{color:var(--drop);font-weight:600}

/* mobil, znovu vložené, trh, registr */
.mobil{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:rgba(244,241,234,.85);text-decoration:none;
padding:7px 11px;border-radius:10px;border:1px dashed rgba(255,255,255,.3)}.mobil:hover{color:#fff;border-style:solid}
.badge-znovu{background:#fff;color:var(--navy)}
.chip.dobre{background:#e1f0e4;border-color:#bfdcc6;color:#23693a;font-weight:600}
.chip.spatne{background:var(--drop-soft);border-color:#ecd3a8;color:var(--drop);font-weight:600}
.fakt.trh{grid-column:1/-1;font-weight:600}.fakt.trh.dobre{background:#e1f0e4;color:#23693a}.fakt.trh.spatne{background:var(--drop-soft);color:var(--drop)}
.znovu{font-size:13px;font-weight:600;color:var(--navy);background:#fff;border:1px dashed var(--carolina);border-radius:12px;padding:9px 12px}



@media (max-width:720px){.mobil{display:none}}

/* skóre nejlepší volby */





.proc{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:3px;font-size:12.5px}
.proc li{display:flex;gap:6px;align-items:baseline}.proc li:before{font-weight:800;flex:none;width:10px}
.proc li.plus:before{content:"+";color:#2f8a4c}.proc li.minus:before{content:"–";color:var(--drop)}
.proc li.minus{color:var(--muted)}.proc li.pozn:before{content:"?";color:var(--accent)}





/* postřeh AI */
.card .ai{display:flex;gap:6px;align-items:flex-start;margin:8px 0 0;padding:7px 10px;border-radius:10px;background:var(--accent-soft);
color:var(--navy);font-size:12.5px;line-height:1.45}
.ai-lbl{flex:none;display:inline-flex;align-items:center;gap:3px;padding:1px 7px 1px 5px;border-radius:99px;background:var(--navy);
color:#fff;font:800 10.5px/1.6 "Plus Jakarta Sans",Inter,sans-serif;letter-spacing:.06em}.ai-lbl svg{width:11px;height:11px}
.card .ai span{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.badge-ai{background:#fbe3df;color:#8a2a1c}
.ai-blok{padding:12px 14px;border-radius:14px;background:var(--accent-soft);border:1px solid #c6dfcf}
.ai-blok h4{display:flex;align-items:center;gap:6px;margin:0 0 6px;font-size:11.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--accent)}
.ai-shrnuti{margin:0 0 8px;font-size:14px;font-weight:600;color:var(--navy)}
.ai-varovani{margin:0 0 8px;padding:8px 10px;border-radius:10px;background:#fbe3df;color:#8a2a1c;font-size:13px;font-weight:600}
.ai-blok .proc{font-size:13px;margin-bottom:8px}.ai-blok small{font-size:11.5px;color:var(--muted)}

/* stav webů */
.weby{font-size:13px;color:var(--muted);flex:0 1 auto}
.weby summary{cursor:pointer;list-style:none;display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:99px;
background:var(--surface);border:1px solid var(--line);font-weight:600;color:var(--text);white-space:nowrap}
.weby summary::-webkit-details-marker{display:none}
.weby.ok:not(.mobde) summary{background:none;border-color:transparent;box-shadow:none;padding-left:4px;padding-right:4px;font-size:12.5px}
.weby .dot,.weby td i{width:8px;height:8px;border-radius:50%;background:#2f8a4c;display:inline-block;flex:none}
.weby.warn .dot,.weby tr.warn td i{background:var(--drop)}.weby.err .dot,.weby tr.err td i{background:var(--err)}
.weby.err summary{color:var(--err);border-color:#f2c3bd;background:var(--err-soft)}
.weby table{margin-top:8px;border-collapse:collapse;background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;
box-shadow:var(--shadow);min-width:420px}
.weby td{padding:6px 12px;border-top:1px solid var(--line);white-space:nowrap}.weby tr:first-child td{border-top:0}
.weby td:first-child{display:flex;align-items:center;gap:8px;color:var(--text);font-weight:600}.weby td:last-child{text-align:right}
.weby tr.err td:nth-child(2){color:var(--err);white-space:normal}

/* mapa bytů */
.mapa-obal{position:relative;z-index:0;isolation:isolate;border-radius:var(--r);overflow:hidden;box-shadow:var(--shadow);margin-bottom:22px;border:1px solid rgba(29,51,40,.08)}
.mapa{height:380px;background:var(--surface-2)}
.leaflet-container{font-family:Inter,sans-serif}
.pin{background:var(--navy);color:#fff;font:700 12px/1 Inter,sans-serif;padding:6px 9px;border-radius:99px;white-space:nowrap;
box-shadow:0 4px 12px rgba(29,51,40,.4);border:2px solid #fff;transform:translate(-50%,-50%);cursor:pointer;transition:transform .2s}
.pin:hover{transform:translate(-50%,-50%) scale(1.12);background:var(--accent)}
.pin.odhad{background:#fff;color:var(--navy);border:2px dashed var(--navy)}
.pin-cil{width:26px;height:26px;border-radius:50%;background:var(--carolina);border:3px solid #fff;box-shadow:0 0 0 6px rgba(217,164,65,.35);
transform:translate(-50%,-50%);animation:tepcil 2.4s infinite}
@keyframes tepcil{50%{box-shadow:0 0 0 14px rgba(217,164,65,0)}}
.leaflet-div-icon{background:none;border:0}

/* detail: hlavní údaje, kontakt, graf ceny */
.fakta{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:8px}
.fakt{display:flex;align-items:center;gap:8px;padding:9px 11px;border-radius:12px;background:var(--surface-2);border:1px solid var(--line);
font-size:13px;font-weight:600;line-height:1.2}
.fakt svg{width:18px;height:18px;flex:none;color:var(--accent)}
.kontakt{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:12px;background:#0a111b;margin-top:auto}
.kontakt .btn{flex:1 1 160px;justify-content:center;padding:12px 14px;font-size:14px}
.kontakt .volat{background:var(--carolina-light);border-color:var(--carolina-light);color:var(--on-carolina)}
.kontakt .otevrit{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.2);color:#fff}
.bez-tel{color:#8f9aa6;font-size:12px;flex:1 1 100%;text-align:center}
.cenovy{border:1px solid var(--line);border-radius:14px;padding:12px 14px;background:var(--surface-2)}
.cenovy-hlava{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.cenovy h4,.take h4{margin:0;font-size:11.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}
.dCenaSouhrn{font-size:13px;font-weight:600}.dCenaSouhrn.dolu{color:#23693a}.dCenaSouhrn.nahoru{color:var(--err)}
.graf svg{display:block;width:100%;height:auto;margin-top:8px;overflow:visible}
.graf .osa{font:500 10px Inter,sans-serif;fill:var(--muted)}
.take h4{margin-bottom:8px}

/* průběh aktualizace + oznámení */
.hero .pruh{position:absolute;left:0;right:0;bottom:0;height:3px;opacity:0;transition:opacity .3s;
background:linear-gradient(90deg,transparent,var(--sky),var(--carolina-light),transparent) 0 0/40% 100% no-repeat}
body.aktualizuji .hero .pruh{opacity:1;animation:pruh 1.4s linear infinite}
@keyframes pruh{from{background-position:-40% 0}to{background-position:140% 0}}
body.aktualizuji main .card{filter:grayscale(.9);opacity:.5;pointer-events:none;transition:filter .6s,opacity .6s}
body.aktualizuji main .card .media:after{content:"";position:absolute;inset:0;z-index:4;
background:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.55) 50%,transparent 70%) 0 0/300% 100%;animation:shimmer 1.4s linear infinite}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:50;display:flex;align-items:center;gap:12px;
background:var(--navy);color:#fff;padding:12px 16px 12px 18px;border-radius:14px;box-shadow:0 18px 50px rgba(16,37,28,.45);
font-size:14px;animation:toast .5s var(--ease)}
.toast b{color:var(--sky)}.toast button{background:rgba(255,255,255,.14);border:0;color:#fff;border-radius:8px;width:28px;height:28px;cursor:pointer}
@keyframes toast{from{opacity:0;transform:translate(-50%,20px)}}
@media (max-width:720px){.weby table{min-width:0;width:100%}.mapa{height:300px}.info-radek{position:relative}.weby{position:static}
.weby[open]>table,.weby[open]>.panel{left:0;right:0;width:auto;max-width:none}}
"""

# Doplňky stylů pro nemovitosti: filtry, výsledek, mapa, osobní pozdrav
CSS += """
.brand em{font-style:normal;font-weight:600;color:var(--sky)}
.pozdrav{margin:0 0 6px!important;font-size:14px!important;color:rgba(243,241,234,.9)!important;font-weight:500}
.razeni-obal{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600;color:var(--muted);background:var(--surface);
border:1px solid var(--line);border-radius:12px;padding:3px 4px 3px 10px}
.razeni-obal select{font:600 13px Inter,sans-serif;color:var(--text);border:0;background:var(--surface-2);border-radius:9px;padding:6px 8px;cursor:pointer}
.filtry{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);padding:14px 16px;
display:flex;flex-direction:column;gap:10px;margin-bottom:12px}
.f-radek{display:flex;gap:10px;align-items:flex-start}
.f-radek .lbl,.pole span{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.f-radek .lbl{flex:none;width:76px;padding-top:6px}
.volby{display:flex;flex-wrap:wrap;gap:6px}
.f-pole{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:flex-end;border-top:1px solid var(--line);padding-top:12px}
.pole{display:flex;flex-direction:column;gap:4px}
.pole input,.pole select{font:500 14px Inter,sans-serif;color:var(--text);background:var(--surface-2);border:1px solid var(--line);
border-radius:10px;padding:7px 10px;width:118px}
.pole select{width:142px}.pole.obec input{width:200px}.pole input:focus,.pole select:focus{outline:2px solid var(--carolina);outline-offset:1px}
.pole.km input{width:200px;padding:0;accent-color:var(--accent);background:none;border:0;height:34px}
.pole.km output{color:var(--text);text-transform:none;letter-spacing:0;font-size:12px}
.f-reset{font:600 13px Inter,sans-serif;color:var(--accent);background:var(--accent-soft);border:0;border-radius:10px;padding:9px 12px;cursor:pointer}
.f-reset[disabled]{opacity:.45;cursor:default}
.f-reset.odkaz{background:none;padding:0;text-decoration:underline}
.vysledek{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 2px 12px;font-size:13.5px;font-weight:600;color:var(--muted)}
.mapa-prepinac{display:inline-flex;align-items:center;gap:6px;font:600 13px Inter,sans-serif;color:var(--text);background:var(--surface);
border:1px solid var(--line);border-radius:10px;padding:6px 11px;cursor:pointer}
.mapa-prepinac[aria-pressed=true]{background:var(--navy);border-color:var(--navy);color:#fff}
.dalsi{text-align:center;margin-top:22px}.dalsi .btn{padding:11px 22px;cursor:pointer}
.loc small{opacity:.75;margin-left:4px}
.zdroj-pocet{font-size:11px;color:var(--muted)}
@media (max-width:720px){.f-radek{flex-direction:column;gap:6px}.f-radek .lbl{width:auto;padding:0}
.pole{flex:1 1 40%}.pole input,.pole select,.pole.obec input,.pole.km input{width:100%}.pole.obec,.pole.km{flex-basis:100%}
.razeni-obal span{display:none}.volby{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;max-width:100%;padding-bottom:2px}}
"""

DETAIL_SABLONA = """<dialog id="detail" aria-label="Detail inzerátu"><div class="dlg">
  <button class="close" aria-label="Zavřít">×</button>
  <div class="gal">
    <div class="stage"><img id="dImg" alt="" referrerpolicy="no-referrer"><div class="bezfotek" hidden>__IKONA_FOTO__<span>Inzerát nemá fotky</span></div>
      <button class="nav prev" data-krok="-1" aria-label="Předchozí fotka">‹</button>
      <button class="nav next" data-krok="1" aria-label="Další fotka">›</button><span class="counter"></span></div>
    <div class="thumbs"></div>
    <div class="kontakt">
      <a class="btn volat" id="dVolat">__IKONA_TEL__<span>Volat prodejci</span></a>
      <a class="btn otevrit" id="dOtevrit" target="_blank" rel="noopener"><span>Otevřít inzerát</span>__IKONA_VEN__</a>
      <span class="bez-tel" id="dBezTel" hidden>Telefon je jen na webu inzerátu</span>
    </div>
  </div>
  <div class="info">
    <div class="tagline"></div>
    <h2></h2>
    <div class="price"></div>
    <div class="ai-blok dAi"><h4><b class="ai-lbl">__IKONA_AI__AI</b>Postřeh umělé inteligence</h4><p class="ai-shrnuti"></p><div class="ai-varovani"></div>
      <ul class="proc"></ul><small>Z textu inzerátu, automaticky (Google Gemini, zdarma). Může se mýlit – ber jako tip, co ověřit.</small></div>
    <div class="fakta dFakta"></div>
    <div class="meta dMisto"></div>
    <div class="znovu dZnovu"></div>
    <div class="cenovy dCena"><div class="cenovy-hlava"><h4>Vývoj ceny</h4><span class="dCenaSouhrn"></span></div><div class="graf"></div></div>
    <dl class="params"></dl>
    <div class="take dTake"><h4>Stejný inzerát i na</h4><div class="btns dOdkazy"></div></div>
  </div>
  <div class="texty">
    <div class="dPopisBlok"><h4>Popis od prodejce</h4><div class="popis"></div><button class="vice" hidden>Zobrazit celý popis</button></div>
  </div>
</div></dialog>"""
DETAIL = (DETAIL_SABLONA.replace("__IKONA_FOTO__", IKONA_FOTO).replace("__IKONA_TEL__", IKONA_TEL)
          .replace("__IKONA_VEN__", IKONA_VEN).replace("__IKONA_AI__", IKONA_AI))

JS = r"""
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const D=JSON.parse($('#data').textContent),DATA=D.inzeraty,VEN=__IKONA_VEN__,FOTO=__IKONA_FOTO__,MISTO=__IKONA_MISTO__;
const IKONY=__IKONY_FAKT__,CIL=IKONY.km;
const klidne=matchMedia('(prefers-reduced-motion: reduce)').matches;
const el=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e};
const fmt=n=>Math.round(n).toLocaleString('cs-CZ').replace(/ /g,' ');
const datumCz=iso=>{const[r,m,d]=iso.slice(0,10).split('-');return (+d)+'. '+(+m)+'. '+r};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bezd=s=>(s||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
const kc=n=>n?fmt(n)+' Kč':'Cena na dotaz';
const kmT=m=>m<1000?m+' m':(m/1000).toFixed(1).replace('.',',')+' km';
const POCET=48,OKRUH_KM=D.okruh/1000;

// --- stav filtrů (pamatuje si ho prohlížeč) ---
const VYCHOZI=()=>({druh:[],okres:[],obec:'',cena:'',od:'',do:'',poz:'',km:OKRUH_KM});
let F={},razeni='novy',jenNove=false,jenZlev=false;
try{F=JSON.parse(localStorage.getItem('hledac-plzen-filtry'))||{}}catch(e){}
Object.keys(DATA).forEach(k=>F[k]=Object.assign(VYCHOZI(),F[k]||{}));
try{razeni=localStorage.getItem('hledac-plzen-razeni')||'novy'}catch(e){}
const ulozF=()=>{try{localStorage.setItem('hledac-plzen-filtry',JSON.stringify(F));localStorage.setItem('hledac-plzen-razeni',razeni)}catch(e){}};
const disp=d=>{const m=/^(\d)\+(kk|\d)/i.exec(d.dispozice||'');if(!m)return 'neuvedeno';return +m[1]>=5?'5+ a větší':m[1]+'+'+m[2].toLowerCase()};
const skupina=(kat,d)=>kat==='byty'?disp(d):(d.druh||'neuvedeno');
const vychozi=kat=>JSON.stringify(F[kat])===JSON.stringify(VYCHOZI());

function vol(box,polozky,vybrane,zmena){
  box.replaceChildren(...polozky.map(([k,n])=>{const b=el('button','pill'+(vybrane.includes(k)?' on':''),k);b.type='button';
    b.append(el('span','',n));b.onclick=()=>{const i=vybrane.indexOf(k);i<0?vybrane.push(k):vybrane.splice(i,1);
      b.classList.toggle('on',i<0);zmena()};return b}))}

const postaveno={};
function sestav(kat){const s=$('#s-'+kat),fp=s&&s.querySelector('.filtry');if(!fp||postaveno[kat])return;postaveno[kat]=true;
  const data=DATA[kat],f=F[kat];
  const pocty=fn=>{const m=new Map();data.forEach(d=>{const k=fn(d);if(k)m.set(k,(m.get(k)||0)+1)});return m};
  const poradi=D.druhy[kat]||[],dr=pocty(d=>skupina(kat,d));
  const kd=[...dr.keys()].sort(kat==='byty'?(a,b)=>a.localeCompare(b,'cs',{numeric:true}):(a,b)=>((poradi.indexOf(a)+1)||99)-((poradi.indexOf(b)+1)||99));
  vol(fp.querySelector('.f-druh'),kd.map(k=>[k,dr.get(k)]),f.druh,()=>prekresli(kat));
  const ok=pocty(d=>d.okres||'neuvedeno');
  const ko=[...ok.keys()].sort((a,b)=>(((D.okresy.indexOf(a)+1)||99)-((D.okresy.indexOf(b)+1)||99))||a.localeCompare(b,'cs'));
  vol(fp.querySelector('.f-okres'),ko.map(k=>[k,ok.get(k)]),f.okres,()=>prekresli(kat));
  const ob=pocty(d=>d.obec);fp.querySelector('datalist').replaceChildren(...[...ob.keys()].sort((a,b)=>a.localeCompare(b,'cs'))
    .map(o=>{const x=el('option');x.value=o;x.label=ob.get(o)+' inzerátů';return x}));
  const pole={obec:'.f-obec',cena:'.f-cena',od:'.f-od',do:'.f-do',poz:'.f-poz',km:'.f-km'};let cas;
  Object.entries(pole).forEach(([k,sel])=>{const x=fp.querySelector(sel);if(!x)return;x.value=f[k];
    x.addEventListener(k==='cena'?'change':'input',()=>{f[k]=k==='km'?+x.value:x.value;
      if(k==='km')fp.querySelector('.f-km-v').textContent=x.value+' km';clearTimeout(cas);cas=setTimeout(()=>prekresli(kat),k==='obec'||k==='km'?250:400)})});
  fp.querySelector('.f-km-v').textContent=f.km+' km';
  s.querySelectorAll('.f-reset').forEach(b=>b.onclick=()=>{F[kat]=VYCHOZI();postaveno[kat]=false;sestav(kat);prekresli(kat)});
  const mp=s.querySelector('.mapa-prepinac'),mo=s.querySelector('.mapa-obal');let skryt=false;
  try{skryt=localStorage.getItem('hledac-plzen-mapa')==='0'}catch(e){}
  mo.hidden=skryt;mp.setAttribute('aria-pressed',!skryt);
  mp.onclick=()=>{const vid=mo.hidden;$$('.mapa-obal').forEach(x=>x.hidden=!vid);$$('.mapa-prepinac').forEach(x=>x.setAttribute('aria-pressed',vid));
    try{localStorage.setItem('hledac-plzen-mapa',vid?'1':'0')}catch(e){}if(vid)mapa(kat)};
  const dl=s.querySelector('.dalsi');dl.querySelector('button').onclick=()=>pridej(kat);
  if('IntersectionObserver' in window)new IntersectionObserver(z=>{if(z[0].isIntersecting&&!dl.hidden)pridej(kat)},{rootMargin:'600px 0px'}).observe(dl)}

function projde(kat,d){const f=F[kat];
  if(jenNove&&!d.novy)return false;if(jenZlev&&!d.zlevneno)return false;
  if(f.druh.length&&!f.druh.includes(skupina(kat,d)))return false;
  if(f.okres.length&&!f.okres.includes(d.okres||'neuvedeno'))return false;
  if(f.obec&&!bezd(d.obec+' '+d.cast+' '+d.misto).includes(bezd(f.obec.trim())))return false;
  if(f.cena&&d.cena&&d.cena>+f.cena)return false;
  if(f.od&&!(d.plocha>=+f.od))return false;if(f.do&&!(d.plocha<=+f.do))return false;
  if(f.poz&&!(d.pozemek>=+f.poz))return false;
  if(f.km<OKRUH_KM&&!(d.vzdalenost!=null&&d.vzdalenost<=f.km*1000))return false;
  return true}
const M2=d=>d.cena&&d.plocha?d.cena/d.plocha:null;
const vzest=v=>v==null?Infinity:v,sest=v=>v==null?-Infinity:v;
const RAZENI={
  novy:(a,b)=>(b.novy-a.novy)||(vzest(a.dni)-vzest(b.dni))||(vzest(a.cena)-vzest(b.cena)),
  cena:(a,b)=>vzest(a.cena)-vzest(b.cena),'-cena':(a,b)=>sest(b.cena)-sest(a.cena),
  plocha:(a,b)=>vzest(a.plocha)-vzest(b.plocha),'-plocha':(a,b)=>sest(b.plocha)-sest(a.plocha),
  m2:(a,b)=>vzest(M2(a))-vzest(M2(b)),km:(a,b)=>vzest(a.vzdalenost)-vzest(b.vzdalenost),
  dni:(a,b)=>sest(b.dni)-sest(a.dni)};
const stav={};
function prekresli(kat){const s=$('#s-'+kat);if(!s||!s.querySelector('.grid'))return;sestav(kat);ulozF();
  const data=DATA[kat],p=data.map((d,i)=>i).filter(i=>projde(kat,data[i])).sort((x,y)=>RAZENI[razeni](data[x],data[y])||x-y);
  stav[kat]={poradi:p,zobrazeno:0};s.querySelector('.grid').replaceChildren();pridej(kat);
  s.querySelector('.none').hidden=p.length>0;
  s.querySelector('.f-pocet').textContent=p.length===data.length?'Všech '+fmt(p.length)+' inzerátů':'Zobrazeno '+fmt(p.length)+' z '+fmt(data.length);
  s.querySelectorAll('.filtry .f-reset').forEach(b=>b.disabled=vychozi(kat));
  $$('.stat.klik').forEach(t=>t.classList.toggle('on',t.dataset.filtr==='novy'?jenNove:jenZlev));
  mapa(kat)}
function pridej(kat){const st=stav[kat],s=$('#s-'+kat),g=s.querySelector('.grid');
  const dalsi=st.poradi.slice(st.zobrazeno,st.zobrazeno+POCET);st.zobrazeno+=dalsi.length;
  g.insertAdjacentHTML('beforeend',dalsi.map(i=>karta(kat,i)).join(''));
  s.querySelector('.dalsi').hidden=st.zobrazeno>=st.poradi.length;
  g.querySelectorAll('.card:not(.hotova)').forEach(k=>{k.classList.add('hotova');k._i=0;tecky(k);
    const m=k.querySelector('.media'),img=m.querySelector('img');if(!img||img.complete)m.classList.add('nacteno')});
  odhal()}

// --- karta ---
function karta(kat,i){const d=DATA[kat][i],f=d.fotky,b=[];
  if(d.novy)b.push('<span class="badge badge-new"><i></i>Nové</span>');
  if(d.zlevneno)b.push('<span class="badge badge-drop">↓ '+kc(d.zlevneno)+(d.zlevneni>1?' · '+d.zlevneni+'×':'')+'</span>');
  if(d.znovu)b.push('<span class="badge badge-znovu" title="Stejnou nemovitost Hledač viděl už v dřívějším inzerátu">↻ znovu vložené</span>');
  if(d.ai&&d.ai.varovani)b.push('<span class="badge badge-ai" title="'+esc(d.ai.varovani)+'">⚠ AI varuje</span>');
  const foto=f.length?'<img src="'+esc(f[0])+'" loading="lazy" referrerpolicy="no-referrer" alt="">':'<div class="nophoto">'+FOTO+'<span>bez fotek</span></div>';
  const listovani=f.length>1?'<button class="nav prev" data-krok="-1" aria-label="Předchozí fotka">‹</button><button class="nav next" data-krok="1" aria-label="Další fotka">›</button><div class="dots">'+'<i></i>'.repeat(Math.min(f.length,5))+'</div>':'';
  const m2=M2(d),podcena=m2?'<small>'+fmt(m2)+' Kč/m²</small>':'';
  const udaje=[kat==='byty'?d.dispozice:d.druh,d.plocha?fmt(d.plocha)+' m²':'',d.pozemek?'pozemek '+fmt(d.pozemek)+' m²':''].filter(Boolean);
  let chips='';
  if(d.vzdalenost!=null)chips+='<span class="chip hl">'+CIL+kmT(d.vzdalenost)+' od centra'+(d.gps_odhad==='obec'||d.gps_odhad==='PSČ'?' (obec)':'')+'</span>';
  if(d.trh)chips+='<span class="chip '+(d.trh.rozdil<=-0.03?'dobre':d.trh.rozdil>=0.03?'spatne':'')+'">'+esc(d.trh_text)+'</span>';
  const ai=d.ai&&d.ai.shrnuti?'<p class="ai" title="Napsala umělá inteligence z textu inzerátu – může se mýlit"><b class="ai-lbl">AI</b><span>'+esc(d.ai.shrnuti)+'</span></p>':'';
  const misto=esc(d.obec||d.misto||'')+(d.cast&&d.cast!==d.obec?', '+esc(d.cast):'')+(d.okres?'<small>okres '+esc(d.okres)+'</small>':'');
  const dni=d.dni_text?'<span class="seen'+(d.dni>=60?' dlouho':'')+'">'+esc(d.dni_text)+'</span>':'<span class="seen"></span>';
  const zdroje=d.odkazy.map(([z,u])=>'<a class="src" href="'+esc(u)+'" target="_blank" rel="noopener">'+esc(z)+VEN+'</a>').join('');
  return '<article class="card" data-k="'+kat+'" data-i="'+i+'"><div class="media" data-open title="Otevřít detail">'+foto+'<div class="shade"></div>'+listovani
    +'<div class="badges">'+b.join('')+'</div><div class="overlay"><div class="price">'+kc(d.cena)+podcena+'</div><div class="loc">'+MISTO+misto+'</div></div></div>'
    +'<div class="body"><h3><a href="'+esc(d.url)+'" data-open>'+esc(d.nazev)+'</a></h3>'
    +(udaje.length?'<p class="radek">'+udaje.map(u=>'<span>'+esc(u)+'</span>').join('<i>·</i>')+'</p>':'')
    +(chips?'<div class="chips">'+chips+'</div>':'')+ai+'</div><footer>'+dni+'<span class="srcs">'+zdroje+'</span></footer></article>'}

// --- karty vyjíždějí postupně, jak přicházejí do obrazu ---
const pozor=('IntersectionObserver' in window)&&!klidne?new IntersectionObserver(zaznamy=>{let n=0;
  zaznamy.forEach(z=>{if(z.isIntersecting){z.target.style.setProperty('--d',(n++*60)+'ms');z.target.classList.add('in');pozor.unobserve(z.target)}})},
  {rootMargin:'0px 0px -40px 0px'}):null;
function odhal(){$$('main section:not([hidden]) .card:not(.in)').forEach(k=>pozor?pozor.observe(k):k.classList.add('in'))}

// --- fotky na kartě: prolínání, tečky, nefunkční fotky pryč ---
const polozka=k=>DATA[k.dataset.k][+k.dataset.i];
function tecky(k){const f=polozka(k).fotky,t=k.querySelectorAll('.dots i');if(!t.length)return;
  const on=f.length<=t.length?k._i:Math.round(k._i/(f.length-1)*(t.length-1));t.forEach((x,j)=>x.classList.toggle('on',j===on))}
function fotkaKarty(k,i){const f=polozka(k).fotky;if(!f.length)return;k._i=(i+f.length)%f.length;
  const img=k.querySelector('.media img');img.classList.add('skryto');
  const n=new Image();n.referrerPolicy='no-referrer';n.onload=n.onerror=()=>{img.src=f[k._i];img.classList.remove('skryto')};n.src=f[k._i];tecky(k)}
document.addEventListener('load',e=>{const m=e.target.closest&&e.target.closest('.card .media');if(m)m.classList.add('nacteno')},true);
document.addEventListener('error',e=>{const img=e.target;if(!(img.tagName==='IMG'&&img.closest('.card .media')))return;
  const k=img.closest('.card'),d=polozka(k),m=img.closest('.media');d.fotky.splice(k._i||0,1);
  if(d.fotky.length)fotkaKarty(k,k._i||0);else{img.replaceWith(Object.assign(el('div','nophoto'),{innerHTML:FOTO+'<span>bez fotek</span>'}));m.classList.add('nacteno')}
  if(d.fotky.length<2)k.querySelectorAll('.nav,.dots').forEach(x=>x.remove())},true);
document.addEventListener('click',e=>{
  const nav=e.target.closest('.card .nav');
  if(nav){e.preventDefault();e.stopPropagation();const k=nav.closest('.card');fotkaKarty(k,(k._i||0)+ +nav.dataset.krok);return}
  const o=e.target.closest('.card [data-open]');
  if(o&&!(e.ctrlKey||e.metaKey||e.shiftKey||e.button===1)){e.preventDefault();const k=o.closest('.card');otevri(polozka(k),k._i||0)}});

// --- záložky s plovoucím ukazatelem ---
const tabs=$$('.tabs button'),ind=$('.tabs .ind'),pod=$('#heroPod').textContent.split(' · ').slice(1).join(' · ');
let aktivni=null;
function posunInd(){const b=tabs.find(x=>x.getAttribute('aria-selected')==='true');if(!b)return;
  ind.style.width=b.offsetWidth+'px';ind.style.transform='translateX('+b.offsetLeft+'px)'}
function napocitej(box){box.querySelectorAll('strong[data-cil]').forEach(s=>{const cil=+s.dataset.cil,pr=s.dataset.pripona;
  if(!cil)return;if(klidne){s.textContent=fmt(cil)+pr;return}const t0=performance.now(),T=1100;
  const krok=t=>{const p=Math.min(1,(t-t0)/T),e=1-Math.pow(1-p,3);s.textContent=fmt(cil*e)+pr;if(p<1)requestAnimationFrame(krok)};
  requestAnimationFrame(krok)})}
function prepni(t){aktivni=t;tabs.forEach(b=>b.setAttribute('aria-selected',b.dataset.t===t));
  $$('main section').forEach(s=>s.hidden=s.dataset.t!==t);
  $$('.stats').forEach(s=>{const vidim=s.dataset.t===t;if(vidim&&s.hidden){s.hidden=false;s.querySelectorAll('.stat').forEach(x=>{x.style.animation='none';x.offsetWidth;x.style.animation=''});napocitej(s)}else s.hidden=!vidim});
  const p=D.popisky[t];$('#heroTitul').textContent=p.titul;$('#heroPod').textContent=[p.pod,pod].filter(Boolean).join(' · ');
  posunInd();if(!stav[t])prekresli(t);else mapa(t);odhal();
  try{localStorage.setItem('hledac-plzen-tab',t)}catch(e){}}
tabs.forEach(b=>b.onclick=()=>prepni(b.dataset.t));
addEventListener('resize',posunInd);document.fonts&&document.fonts.ready.then(posunInd);
const rz=$('#razeni');rz.value=razeni;rz.onchange=()=>{razeni=rz.value;Object.keys(stav).forEach(prekresli)};
$('#jenNove').onchange=e=>{jenNove=e.target.checked;jenZlev=false;Object.keys(stav).forEach(prekresli)};
$$('.stat.klik').forEach(t=>{const klik=()=>{if(t.dataset.filtr==='novy'){jenNove=!jenNove;jenZlev=false}else{jenZlev=!jenZlev;jenNove=false}
    $('#jenNove').checked=jenNove;Object.keys(stav).forEach(prekresli);
    scrollTo({top:$('main').getBoundingClientRect().top+scrollY-$('#toolbar').offsetHeight,behavior:'smooth'})};
  t.onclick=klik;t.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();klik()}}});
const tb=$('#toolbar'),hlidka=el('div');tb.before(hlidka);
new IntersectionObserver(([z])=>tb.classList.toggle('stuck',!z.isIntersecting)).observe(hlidka);

// --- mapa: centrum Plzně, kruh okruhu, nemovitosti jako tečky (klik = detail) ---
const mapy={};
function mapa(kat){const s=$('#s-'+kat),box=s&&s.querySelector('.mapa');
  if(!box||!window.L||s.hidden||s.querySelector('.mapa-obal').hidden||!stav[kat])return;
  let M=mapy[kat];
  if(!M){const m=L.map(box,{scrollWheelZoom:false,preferCanvas:true});
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(m);
    L.circle(D.stred,{radius:D.okruh,color:'#2f6b4f',weight:1.5,dashArray:'6 6',fillColor:'#e9c47a',fillOpacity:.06,interactive:false}).addTo(m);
    L.marker(D.stred,{icon:L.divIcon({className:'',iconSize:null,html:'<div class="pin-cil"></div>'})}).addTo(m).bindTooltip('Centrum Plzně – '+D.stred_popis);
    M=mapy[kat]={m,vrstva:L.layerGroup().addTo(m)};m.fitBounds(L.latLng(D.stred).toBounds(D.okruh*1.75))}
  else setTimeout(()=>M.m.invalidateSize(),50);
  M.vrstva.clearLayers();
  stav[kat].poradi.forEach(i=>{const d=DATA[kat][i];if(!d.gps)return;const hruba=d.gps_odhad==='obec'||d.gps_odhad==='PSČ';
    const mk=L.circleMarker(d.gps,{radius:d.novy?7:5.5,weight:hruba?1:2,color:'#fff',
      fillColor:d.zlevneno?'#c0581c':d.novy?'#d9a441':'#1f4a37',fillOpacity:hruba?.55:.9});
    mk.bindTooltip(esc(d.nazev)+'<br><b>'+kc(d.cena)+'</b> · '+esc(d.obec)+(hruba?' <i>(poloha obce)</i>':''));
    mk.on('click',()=>otevri(d,0));mk.addTo(M.vrstva)})}

// --- graf vývoje ceny (schodovitá čára: cena platí až do další změny) ---
function grafCeny(hist){const box=dlg.querySelector('.graf'),souhrn=dlg.querySelector('.dCenaSouhrn');box.replaceChildren();souhrn.className='dCenaSouhrn';
  const b=hist.filter(x=>x[1]);if(!b.length){dlg.querySelector('.dCena').hidden=true;return}dlg.querySelector('.dCena').hidden=false;
  const prvni=b[0][1],posl=b[b.length-1][1],zmen=b.length-1;
  if(!zmen){souhrn.textContent='beze změny od '+datumCz(b[0][0]);return}
  const rozdil=posl-prvni,proc=Math.round(Math.abs(rozdil)/prvni*1000)/10;
  souhrn.textContent=(rozdil<0?'↓ zlevněno':'↑ zdraženo')+' o '+fmt(Math.abs(rozdil))+' Kč ('+(rozdil<0?'−':'+')+String(proc).replace('.',',')+' %) · '+zmen+'× změna';
  souhrn.classList.add(rozdil<0?'dolu':'nahoru');
  const dny=b.map(x=>new Date(x[0]).getTime()),dnes=Date.now(),t0=dny[0],t1=Math.max(dnes,dny[dny.length-1]+864e5);
  const ceny=b.map(x=>x[1]),mn=Math.min(...ceny),mx=Math.max(...ceny),W=320,H=96,P=8;
  const X=t=>P+(t-t0)/(t1-t0)*(W-2*P),Y=c=>mx===mn?H/2:P+(mx-c)/(mx-mn)*(H-2*P-14);
  let d='M'+X(dny[0])+' '+Y(ceny[0]);for(let i=1;i<b.length;i++)d+=' H'+X(dny[i])+' V'+Y(ceny[i]);d+=' H'+X(t1);
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 '+W+' '+(H+4));
  svg.innerHTML='<defs><linearGradient id="gc" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#e9c47a" stop-opacity=".4"/><stop offset="1" stop-color="#e9c47a" stop-opacity="0"/></linearGradient></defs>'
    +'<path d="'+d+' V'+(H-14)+' H'+X(dny[0])+' Z" fill="url(#gc)"/><path d="'+d+'" fill="none" stroke="#2f7a55" stroke-width="2.2" stroke-linejoin="round"/>'
    +b.map((x,i)=>'<circle cx="'+X(dny[i])+'" cy="'+Y(ceny[i])+'" r="3.5" fill="#fff" stroke="#2f7a55" stroke-width="2"><title>'+datumCz(x[0])+': '+fmt(x[1])+' Kč</title></circle>').join('')
    +'<text class="osa" x="'+P+'" y="'+(H+2)+'">'+datumCz(b[0][0])+'</text><text class="osa" x="'+(W-P)+'" y="'+(H+2)+'" text-anchor="end">dnes</text>';
  box.append(svg)}

// --- okno s detailem ---
const dlg=$('#detail'),dImg=$('#dImg'),thumbs=dlg.querySelector('.thumbs');let akt=null,ai=0;
function ukaz(i){const f=akt.fotky,bez=!f.length;dImg.hidden=bez;dlg.querySelector('.bezfotek').hidden=!bez;
  if(bez){dImg.removeAttribute('src');return}ai=(i+f.length)%f.length;
  dImg.classList.add('skryto');const n=new Image();n.referrerPolicy='no-referrer';
  n.onload=n.onerror=()=>{if(akt&&akt.fotky[ai]===f[ai]){dImg.src=f[ai];dImg.classList.remove('skryto')}};n.src=f[ai];
  dlg.querySelector('.stage .counter').textContent=(ai+1)+' / '+f.length;
  thumbs.querySelectorAll('button').forEach((b,j)=>{b.setAttribute('aria-current',j===ai);if(j===ai)b.scrollIntoView({block:'nearest',inline:'nearest',behavior:'smooth'})});
  [1,-1].forEach(s=>{const x=f[(ai+s+f.length)%f.length];if(x)new Image().src=x})}
dImg.addEventListener('error',()=>{if(!akt||!akt.fotky.length)return;akt.fotky.splice(ai,1);thumbs.children[ai]?.remove();
  thumbs.querySelectorAll('button').forEach((b,j)=>b.dataset.j=j);ukaz(ai)});
function fakt(k,v){const x=el('div','fakt');x.innerHTML=IKONY[k]||'';x.append(v);return x}
function otevri(d,start){akt=d;
  const tl=dlg.querySelector('.tagline');tl.replaceChildren();
  if(d.novy)tl.append(el('span','badge-new','Nové'));if(d.zlevneno)tl.append(el('span','badge-drop','↓ '+kc(d.zlevneno)));
  if(d.druh)tl.append(el('span','',d.druh));
  dlg.querySelector('h2').textContent=d.nazev;
  const p=dlg.querySelector('.price'),m2=M2(d);p.textContent=kc(d.cena);if(m2)p.append(el('small','',fmt(m2)+' Kč/m²'));
  const ab=dlg.querySelector('.dAi');ab.hidden=!(d.ai&&d.ai.shrnuti);
  if(!ab.hidden){ab.querySelector('.ai-shrnuti').textContent=d.ai.shrnuti;const av=ab.querySelector('.ai-varovani');
    av.hidden=!d.ai.varovani;av.textContent='⚠ '+(d.ai.varovani||'');
    ab.querySelector('.proc').replaceChildren(...d.ai.plusy.map(t=>el('li','plus',t)),...d.ai.rizika.map(t=>el('li','minus',t)))}
  const fk=[];if(d.dispozice)fk.push(fakt('dispozice',d.dispozice));if(d.plocha)fk.push(fakt('plocha',fmt(d.plocha)+' m²'));
  if(d.pozemek)fk.push(fakt('pozemek','pozemek '+fmt(d.pozemek)+' m²'));
  if(d.vzdalenost!=null)fk.push(fakt('km',kmT(d.vzdalenost)+' od centra'));if(d.okres)fk.push(fakt('okres','okres '+d.okres));
  if(d.trh_text){const x=el('div','fakt trh'+(d.trh.rozdil<=-0.03?' dobre':d.trh.rozdil>=0.03?' spatne':''));
    x.textContent=d.trh_text[0].toUpperCase()+d.trh_text.slice(1)+' – průměr '+fmt(d.trh.median)+' Kč/m² z '+d.trh.n+' inzerátů';fk.push(x)}
  dlg.querySelector('.dFakta').replaceChildren(...fk);
  const kde=d.gps_odhad==='obec'||d.gps_odhad==='PSČ'?'na mapě jen poloha obce':d.gps_odhad?'poloha podle ulice':'';
  dlg.querySelector('.dMisto').textContent=[d.misto,d.dni_text,kde].filter(Boolean).join(' · ');
  grafCeny(d.historie_cen);
  const zn=dlg.querySelector('.dZnovu');zn.hidden=!d.znovu;
  if(d.znovu)zn.textContent='↻ Znovu vložený inzerát – Hledač stejnou nemovitost poprvé viděl '+datumCz(d.znovu.prvni)+(d.znovu.cena?' za '+fmt(d.znovu.cena)+' Kč':'')+'. Prodává se déle, než ukazuje nový inzerát.';
  const dl=dlg.querySelector('.params');dl.replaceChildren();d.parametry.forEach(([k,v])=>dl.append(el('dt','',k),el('dd','',v)));dl.hidden=!d.parametry.length;
  const volat=$('#dVolat'),ot=$('#dOtevrit');volat.hidden=!d.telefon;$('#dBezTel').hidden=!!d.telefon;
  if(d.telefon){volat.href='tel:'+d.telefon;volat.title=d.telefon;volat.querySelector('span').textContent='Volat '+d.telefon}
  ot.href=d.url;ot.querySelector('span').textContent='Otevřít na '+d.zdroj;
  const dalsi=d.odkazy.filter(([z,u])=>u!==d.url);dlg.querySelector('.dTake').hidden=!dalsi.length;
  dlg.querySelector('.dOdkazy').replaceChildren(...dalsi.map(([z,u])=>{const a=el('a','btn ghost',z);
    a.href=u;a.target='_blank';a.rel='noopener';a.insertAdjacentHTML('beforeend',VEN);return a}));
  const pop=dlg.querySelector('.popis'),vice=dlg.querySelector('.dPopisBlok .vice');pop.textContent=d.popis;
  dlg.querySelector('.texty').hidden=!d.popis;const dlouhy=d.popis.length>700;pop.classList.toggle('zkraceny',dlouhy);vice.hidden=!dlouhy;
  vice.onclick=()=>{pop.classList.remove('zkraceny');vice.hidden=true};
  thumbs.replaceChildren(...d.fotky.map((f,j)=>{const b=el('button');b.type='button';b.dataset.j=j;b.setAttribute('aria-label','Fotka '+(j+1));
    const im=el('img');im.loading='lazy';im.referrerPolicy='no-referrer';im.src=f;b.append(im);return b}));
  thumbs.hidden=d.fotky.length<2;dlg.querySelectorAll('.stage .nav,.stage .counter').forEach(x=>x.hidden=d.fotky.length<2);
  ukaz(start);if(!dlg.open)dlg.showModal();dlg.scrollTop=0}
thumbs.addEventListener('click',e=>{const b=e.target.closest('button');if(b)ukaz(+b.dataset.j)});
dlg.querySelectorAll('.stage .nav').forEach(b=>b.onclick=()=>ukaz(ai+ +b.dataset.krok));
dlg.querySelector('.close').onclick=()=>dlg.close();
dlg.addEventListener('click',e=>{if(e.target===dlg)dlg.close()});
dlg.addEventListener('keydown',e=>{if(e.key==='ArrowRight')ukaz(ai+1);if(e.key==='ArrowLeft')ukaz(ai-1)});
let tx=null;const st=dlg.querySelector('.stage');
st.addEventListener('touchstart',e=>{tx=e.touches[0].clientX},{passive:true});
st.addEventListener('touchend',e=>{if(tx==null)return;const dx=e.changedTouches[0].clientX-tx;if(Math.abs(dx)>40)ukaz(ai+(dx<0?1:-1));tx=null});

// --- aktualizace ---
const btn=$('#obnovit'),prubeh=$('#prubeh');
function oznameni(html,ms){const t=$('#toast');t.innerHTML=html+'<button aria-label="Zavřít">×</button>';t.hidden=false;
  t.querySelector('button').onclick=()=>t.hidden=true;if(ms)setTimeout(()=>t.hidden=true,ms)}
const tvar=(n,a,b,c)=>n===1?a:n<5?b:c;
function souhrnText(s){return Object.entries(s||{}).map(([k,v])=>'<span>'+((D.popisky[k]||{}).titul||k)+': '
  +(v.nove||v.zlevnene?[v.nove?'<b>+'+v.nove+' '+tvar(v.nove,'nový','nové','nových')+'</b>':'',
    v.zlevnene?'<b>'+v.zlevnene+' '+tvar(v.zlevnene,'zlevněný','zlevněné','zlevněných')+'</b>':''].filter(Boolean).join(', '):'nic nového')+'</span>').join(' · ')}
// Cloud bez tokenu: tlačítko otevře stránku workflow na GitHubu.
if(D.akce_url&&!D.akce_token){btn.hidden=false;btn.title='Otevře GitHub, tam „Run workflow“ (je potřeba být přihlášený)';
  btn.onclick=()=>window.open(D.akce_url,'_blank')}
// Cloud s tokenem (jen Actions tohoto repa): spustí hledání přes API, hlídá běh a po zveřejnění obnoví stránku.
if(D.akce_url&&D.akce_token){btn.hidden=false;btn.title='Znovu prohledat všechny weby (asi 10 minut)';
  const api='https://api.github.com/repos/'+D.akce_repo+'/actions/workflows/hledac.yml/',
    hl={Authorization:'Bearer '+D.akce_token,Accept:'application/vnd.github+json'};
  const zapni=t=>{btn.disabled=true;btn.classList.add('bezi');btn.lastChild.textContent='Hledám…';prubeh.hidden=false;
    prubeh.textContent=t;document.body.classList.add('aktualizuji')};
  const vypni=chyba=>{btn.disabled=false;btn.classList.remove('bezi');btn.lastChild.textContent='Aktualizovat';
    document.body.classList.remove('aktualizuji');prubeh.hidden=!chyba;if(chyba)prubeh.textContent=chyba};
  const zmeneno=async()=>{try{return(await fetch(location.pathname+'?t='+Date.now(),{method:'HEAD',cache:'no-store'})).headers.get('last-modified')}catch(e){return null}};
  const beh=async()=>{const r=await fetch(api+'runs?per_page=1',{headers:hl,cache:'no-store'});
    if(!r.ok)throw new Error('GitHub '+r.status);return(await r.json()).workflow_runs[0]};
  const hlidej=async stranka=>{
    let b;try{b=await beh()}catch(e){return vypni('Nejde zjistit stav hledání ('+e.message+')')}
    if(b&&b.status!=='completed'){const min=Math.max(0,Math.round((Date.now()-Date.parse(b.run_started_at||b.created_at))/60000));
      zapni(b.status==='queued'?'Čeká ve frontě…':'Prohledávám weby… '+min+' min (obvykle 10)');return setTimeout(()=>hlidej(stranka),15000)}
    if(b&&b.conclusion!=='success')return vypni('Hledání selhalo – detail na GitHubu');
    zapni('Zveřejňuji novou stránku…');
    for(let i=0;i<30;i++){const t=await zmeneno();if(t&&t!==stranka)break;await new Promise(r=>setTimeout(r,10000))}
    try{sessionStorage.setItem('hledac-cloud','1')}catch(e){}
    location.replace(location.pathname+'?t='+Date.now())};
  btn.onclick=async()=>{zapni('Spouštím hledání…');const stranka=await zmeneno();
    try{const b=await beh();
      if(!b||b.status==='completed'){const r=await fetch(api+'dispatches',{method:'POST',headers:hl,body:JSON.stringify({ref:'main'})});
        if(!r.ok)throw new Error('GitHub '+r.status);await new Promise(r=>setTimeout(r,5000))}}
    catch(e){return vypni('Hledání nejde spustit ('+e.message+')')}
    hlidej(stranka)};
  (async()=>{try{const b=await beh();if(b&&b.status!=='completed'){const s=await zmeneno();hlidej(s)}}catch(e){}})();
  try{if(sessionStorage.getItem('hledac-cloud')){sessionStorage.removeItem('hledac-cloud');
    setTimeout(()=>oznameni('Aktualizováno · '+pod,8000),300)}}catch(e){}}
// Místní server (py hledac.py --server): tlačítko spustí hledání a hlídá průběh.
if(!D.akce_url&&location.protocol.startsWith('http')){btn.hidden=false;
  const hlidej=async()=>{try{const s=await(await fetch('/stav',{cache:'no-store'})).json();
      if(s.bezi){btn.disabled=true;btn.classList.add('bezi');btn.lastChild.textContent='Hledám…';prubeh.hidden=false;
        document.body.classList.add('aktualizuji');prubeh.textContent=(s.log[0]||'začínám').trim();setTimeout(hlidej,1500)}
      else if(btn.classList.contains('bezi')){
        if(s.chyba){alert('Aktualizace selhala: '+s.chyba)}else{try{sessionStorage.setItem('hledac-souhrn',JSON.stringify(s.souhrn))}catch(e){}}
        location.reload()}
    }catch(e){prubeh.hidden=false;prubeh.textContent='Hledač neběží – spusť Hledač.cmd';btn.disabled=false;btn.classList.remove('bezi');
      document.body.classList.remove('aktualizuji')}};
  btn.onclick=async()=>{btn.disabled=true;btn.classList.add('bezi');document.body.classList.add('aktualizuji');
    try{await fetch('/aktualizovat',{method:'POST'})}catch(e){}hlidej()};
  hlidej()}
try{const s=sessionStorage.getItem('hledac-souhrn');if(s){sessionStorage.removeItem('hledac-souhrn');oznameni('Aktualizováno · '+souhrnText(JSON.parse(s)),9000)}}catch(e){}

// --- start ---
let ulozena=null;try{ulozena=localStorage.getItem('hledac-plzen-tab')}catch(e){}
const kotva=location.hash.slice(1),ok=t=>tabs.some(b=>b.dataset.t===t);
const start=ok(kotva)?kotva:ok(ulozena)?ulozena:tabs[0].dataset.t;
$$('.stats').forEach(s=>s.hidden=true);prepni(start);
"""
JS = (JS.replace("__IKONA_VEN__", json.dumps(IKONA_VEN)).replace("__IKONA_FOTO__", json.dumps(IKONA_FOTO))
      .replace("__IKONA_MISTO__", json.dumps(IKONA_MISTO)).replace("__IKONY_FAKT__", json.dumps(IKONY_FAKT)))
