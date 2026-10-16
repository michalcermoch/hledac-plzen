"""Denní souhrn e-mailem - jen z cloudu, jednou denně kolem 20:00 (hledac.py --cloud, viz SOUHRN_HODINY).

V souhrnu je všechno, co od minulého souhrnu přibylo nebo zlevnilo (všechny kategorie, v rámci pevných filtrů),
s fotkou a odkazem na každý inzerát. Když nic nepřibylo, nic se neposílá.
  e-mail (SMTP)  Gmail s heslem aplikace nebo bezplatné Brevo (SMTP klíč) - nastavení v nastaveni.py / Secrets.
  ntfy           nepovinně stejný souhrn i do aplikace ntfy (jen když je nastavený kanál).
"""
import base64
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape

import nastaveni

NTFY = "https://ntfy.sh/"
NA_KATEGORII = 15         # kolik inzerátů z každé kategorie vypsat; zbytek jen počtem
TITULY = {"byty": "🏢 Byty", "domy": "🏡 Rodinné domy", "pozemky": "🌳 Pozemky"}


def _kc(n) -> str:
    return f"{int(n):,}".replace(",", " ") + " Kč" if n else "cena na dotaz"


def _m2(n) -> str:
    return f"{int(n):,} m²".replace(",", " ")


def _cena_tehdy(i: dict, od: str):
    """Cena platná v okamžiku minulého souhrnu (historie_cen = [(čas, cena)] od prvního vidění)."""
    ceny = [c for cas, c in i.get("historie_cen") or [] if cas <= od]
    return ceny[-1] if ceny else None


def vyber(sekce: list[tuple], od: str) -> dict[str, list[tuple[dict, str]]]:
    """{kategorie: [(inzerát, 'nové' / 'zlevnilo')]} - co přibylo nebo zlevnilo od času `od` (ISO)."""
    out = {}
    for s in sekce:
        kat, inz = s[0], s[1]
        polozky = []
        for i in inz:
            if (i.get("prvni_videno") or "") > od:
                polozky.append((i, "nové"))
            elif i.get("cena") and (_cena_tehdy(i, od) or 0) > i["cena"]:
                polozky.append((i, "zlevnilo"))
        if polozky:  # zlevněné první, pak od nejlevnějšího
            out[kat] = sorted(polozky, key=lambda x: (x[1] != "zlevnilo", x[0].get("cena") or 10 ** 12))
    return out


def _kde(i: dict) -> str:
    misto = i.get("mesto") or i.get("misto") or ""
    okres = f"okres {i['okres']}" if i.get("okres") and i["okres"] not in misto else ""
    return ", ".join(x for x in (misto, okres) if x)


def _udaje(kat: str, i: dict) -> list[str]:
    return [x for x in (i.get("dispozice") if kat == "byty" else i.get("druh"),
                        _m2(i["plocha"]) if i.get("plocha") else "",
                        f"pozemek {_m2(i['pozemek'])}" if i.get("pozemek") else "", _kde(i))
            if x]


def nadpis(polozky: dict) -> str:
    nove = sum(1 for p in polozky.values() for _, d in p if d == "nové")
    zlev = sum(1 for p in polozky.values() for _, d in p if d == "zlevnilo")
    return "Hledač: " + ", ".join(x for x in (
        f"{nove} {'nová nemovitost' if nove == 1 else 'nové nemovitosti' if nove < 5 else 'nových nemovitostí'}" if nove else "",
        f"{zlev} {'zlevněná' if zlev == 1 else 'zlevněné' if zlev < 5 else 'zlevněných'}" if zlev else "") if x)


def text(polozky: dict, od: str, odkazy: bool = True) -> str:
    """Prostý text souhrnu (ntfy a textová verze e-mailu)."""
    bloky = []
    for kat, seznam in polozky.items():
        radky = [f"{TITULY.get(kat, kat)} ({len(seznam)})"]
        for i, duvod in seznam[:NA_KATEGORII]:
            cena = _kc(i.get("cena")) if duvod == "nové" else f"↓ {_kc(i.get('cena'))} (dřív {_kc(_cena_tehdy(i, od))})"
            radky.append("• " + " · ".join([cena] + _udaje(kat, i)) + (f"\n  {i['url']}" if odkazy else ""))
        if len(seznam) > NA_KATEGORII:
            radky.append(f"  … a dalších {len(seznam) - NA_KATEGORII} v přehledu")
        bloky.append("\n".join(radky))
    return "\n\n".join(bloky)


def html(polozky: dict, od: str, osloveni: str, odkaz: str | None) -> str:
    """HTML e-mail: po kategoriích karty s fotkou, cenou, údaji a odkazem (inline styly kvůli poštovním klientům)."""
    pismo = "font-family:Segoe UI,Helvetica,Arial,sans-serif"
    casti = [f'<p style="{pismo};font-size:15px;color:#1d3328;margin:0 0 16px">'
             f'{"Ahoj " + escape(osloveni) + ", t" if osloveni else "T"}ady je, co dnes přibylo nebo zlevnilo '
             f'v Plzni a okolí.</p>']
    for kat, seznam in polozky.items():
        casti.append(f'<h2 style="{pismo};font-size:17px;color:#1f4a37;margin:22px 0 8px">'
                     f'{TITULY.get(kat, kat)} <span style="color:#6b685f;font-weight:400">({len(seznam)})</span></h2>')
        for i, duvod in seznam[:NA_KATEGORII]:
            foto = (i.get("fotky") or [i.get("foto")] or [None])[0]
            obrazek = (f'<img src="{escape(foto)}" width="120" height="90" alt="" style="display:block;width:120px;'
                       f'height:90px;object-fit:cover;border-radius:8px;background:#eeebe3">' if foto else "")
            cena = escape(_kc(i.get("cena")))
            if duvod == "zlevnilo":
                cena = (f'<span style="color:#c0581c">↓ {cena}</span> <s style="color:#6b685f;font-weight:400;font-size:13px">'
                        f'{escape(_kc(_cena_tehdy(i, od)))}</s>')
            m2 = f' <span style="color:#6b685f;font-weight:400;font-size:12px">{_kc(i["cena"] / i["plocha"])}/m²</span>' \
                if i.get("cena") and i.get("plocha") else ""
            casti.append(
                f'<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;'
                f'margin:0 0 10px;background:#fcfbf7;border:1px solid #dcd6c8;border-radius:10px"><tr>'
                f'<td style="width:132px;padding:6px;vertical-align:top"><a href="{escape(i["url"])}">{obrazek}</a></td>'
                f'<td style="padding:8px 10px 8px 4px;vertical-align:top;{pismo};color:#1d3328">'
                f'<div style="font-size:16px;font-weight:700">{cena}{m2}</div>'
                f'<div style="font-size:13px;margin:3px 0">{escape(" · ".join(_udaje(kat, i)))}</div>'
                f'<a href="{escape(i["url"])}" style="font-size:13px;color:#2f7a55;font-weight:600">'
                f'{escape(i.get("nazev") or "Inzerát")} – {escape(i.get("zdroj") or "web")} ›</a></td></tr></table>')
        if len(seznam) > NA_KATEGORII:
            casti.append(f'<p style="{pismo};font-size:13px;color:#6b685f">… a dalších {len(seznam) - NA_KATEGORII} v přehledu</p>')
    if odkaz:
        casti.append(f'<p style="margin:24px 0 8px"><a href="{escape(odkaz)}" style="{pismo};display:inline-block;'
                     f'background:#1f4a37;color:#fff;text-decoration:none;font-weight:600;padding:11px 18px;'
                     f'border-radius:10px">Otevřít celý přehled</a></p>')
    casti.append(f'<p style="{pismo};font-size:11px;color:#8a877e;margin-top:20px">Hledač nemovitostí · souhrn chodí '
                 f'jednou denně kolem 20:00, jen když něco přibude.</p>')
    return (f'<!doctype html><html><body style="margin:0;padding:16px;background:#eeebe3">'
            f'<div style="max-width:640px;margin:0 auto">{"".join(casti)}</div></body></html>')


def _email(nast: dict, predmet: str, prosty: str, html_text: str):
    zprava = EmailMessage()
    zprava["Subject"] = predmet
    zprava["From"] = formataddr(("Hledač nemovitostí", nast["email_od"] or nast["smtp_uzivatel"]))
    zprava["To"] = nast["email_komu"]
    zprava["Message-ID"] = make_msgid(domain="hledac-plzen")
    zprava.set_content(prosty)
    zprava.add_alternative(html_text, subtype="html")
    port = int(nast.get("smtp_port") or 587)
    kontext = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(nast["smtp_server"], port, context=kontext, timeout=60)
    else:
        server = smtplib.SMTP(nast["smtp_server"], port, timeout=60)
        server.starttls(context=kontext)
    with server:
        server.login(nast["smtp_uzivatel"], nast["smtp_heslo"])
        server.send_message(zprava)


def _hlavicka(t: str) -> str:
    """HTTP hlavičky musí být latin-1; ntfy umí RFC 2047 (=?UTF-8?B?...?=) pro češtinu."""
    return "=?UTF-8?B?" + base64.b64encode(t.encode("utf-8")).decode("ascii") + "?="


def _ntfy(kanal: str, predmet: str, zprava: str, odkaz: str | None):
    hlavicky = {"Title": _hlavicka(predmet), "Tags": "house", "Priority": "default"}
    if odkaz:
        hlavicky["Click"] = odkaz
    req = urllib.request.Request(NTFY + kanal, data=zprava[:3900].encode("utf-8"), headers=hlavicky, method="POST")
    with urllib.request.urlopen(req, timeout=30):
        pass


def denni_souhrn(sekce: list[tuple], od: str, odkaz_prehled: str | None, log=print) -> bool:
    """Pošle souhrn všeho od času `od` e-mailem (a do ntfy, je-li nastavený). Vrací True, když se aspoň jeden
    kanál podařil nebo nebylo co poslat (další souhrn se pak počítá od teď)."""
    nast = nastaveni.nacti()
    polozky = vyber(sekce, od)
    if not polozky:
        log("souhrn: od minula nic nového")
        return True
    predmet = nadpis(polozky)
    povedlo = False
    if nast.get("email_komu") and nast.get("smtp_server") and nast.get("smtp_heslo"):
        try:
            osloveni = nast.get("osloveni") or nast.get("jmeno") or ""
            _email(nast, predmet, text(polozky, od) + (f"\n\nCelý přehled: {odkaz_prehled}" if odkaz_prehled else ""),
                   html(polozky, od, osloveni, odkaz_prehled))
            povedlo = True
            log("souhrn: odeslán e-mailem")
        except Exception as e:  # upozornění nesmí shodit běh; text chyby může obsahovat adresu, proto jen typ
            log(f"souhrn: e-mail se nepodařil ({type(e).__name__})")
    else:
        log("souhrn: e-mail není nastavený (EMAIL_KOMU, SMTP_SERVER, SMTP_UZIVATEL, SMTP_HESLO)")
    if nast.get("ntfy_kanal"):
        try:
            _ntfy(nast["ntfy_kanal"], predmet, text(polozky, od, odkazy=False), odkaz_prehled)
            povedlo = True
            log("souhrn: odeslán na ntfy")
        except Exception as e:
            log(f"souhrn: ntfy se nepodařil ({type(e).__name__})")
    return povedlo
