"""Postřeh AI k inzerátu: přečte text inzerátu a vytáhne, co pevné filtry nepoznají.

Vše zdarma, bez karty. Poskytovatelé v pořadí (každý, ke kterému je klíč; když jeden odmítne - přetížení 503
nebo vyčerpaný limit 429 - jde se na další):
  Google Gemini  ai_api_klic        aistudio.google.com/apikey     ~250-1500 dotazů/den, 250 tis. tokenů/min
  Cerebras       cerebras_api_klic  cloud.cerebras.ai              1 mil. tokenů/den
  Groq           groq_api_klic      console.groq.com/keys          200 tis. tokenů/den, 8 tis./min
Klíče jsou v nastaveni.json, v cloudu v GitHub Secrets (AI_API_KLIC, CEREBRAS_API_KLIC, GROQ_API_KLIC).
Bez klíčů se krok přeskočí a Hledač funguje jako dřív. (GitHub Models, původní volba, skončily 30. 7. 2026.)
Bezplatné tarify smí vstupy použít ke zlepšení modelů - posílají se jen veřejné inzeráty, nic osobního.

Bezplatné limity počítají hlavně DOTAZY, ne délku textu -> Gemini dostane 25 inzerátů najednou, všechna
auta tak zaberou pár dotazů. Model si nejdřív nemyslí nahlas (reasoning_effort low) - rychlejší a levnější.

Výsledek je u každého inzerátu v 'ai' = {shrnuti, plusy, rizika, varovani}. Skóre nejlepší volby nemění -
AI se může mýlit, proto je jen vedle jako druhý názor. Každý inzerát se posílá jen jednou; znovu až po
změně textu (hledac.db, tabulka ai). Co se v běhu nestihne, doplní se příště.
"""
import hashlib
import json
import re
import time
from datetime import datetime, timedelta
import urllib.error
import urllib.request

import nastaveni
import nemovitosti

POSKYTOVATELE = [
    # na_dotaz: inzerátů v jednom dotazu (podle limitu tokenů za minutu); odstup: s mezi dotazy (dotazy za minutu)
    dict(nazev="Gemini", klic="ai_api_klic", api="https://generativelanguage.googleapis.com/v1beta/openai/",
         na_dotaz=25, odstup=7, modelu=4),
    dict(nazev="Cerebras", klic="cerebras_api_klic", api="https://api.cerebras.ai/v1/", na_dotaz=10, odstup=13, modelu=2),
    dict(nazev="Groq", klic="groq_api_klic", api="https://api.groq.com/openai/v1/", na_dotaz=3, odstup=8, modelu=2),
]
MAX_DOTAZU = 12      # na jeden běh (s 25 inzeráty na dotaz to je 300 inzerátů); zbytek příště
MAX_POPIS = 2000     # znaků popisu na inzerát
OBNOVIT_DNI = 7      # změněný text inzerátu se posílá znovu, až je postřeh starší
PAUZY_S = (20, 45)   # všechno přetížené -> počkat a zkusit znovu (víc ne, běh by pálil minuty GitHub Actions)

POKYNY = """Jsi zkušený a střízlivý poradce při koupi {co} v Česku. Kupující hledá: {hledani}.
Dostaneš několik inzerátů (parametry z webu + text od prodejce). U každého z textu vytáhni to, co z parametrů
není vidět, a stručně česky odpověz. Pravidla:
- Piš jen to, co v inzerátu opravdu je nebo zjevně chybí. Nic si nedomýšlej, neopakuj cenu ani parametry.
- "shrnuti": 1 věta (max 20 slov), proč inzerát stojí nebo nestojí za pozornost.
- "plusy": max 3 krátké body (např. po rekonstrukci, nová střecha, zasíťovaný pozemek, klidná lokalita, garáž).
- "rizika": max 3 krátké body (např. text a parametry si odporují, nejasný stav, nutná rekonstrukce,
  vysoký fond oprav, prodává realitka ač tvrdí opak, pozemek bez sítí nebo přístupové cesty, záplavové území).
- "varovani": vyplň JEN při vážném podezření (znaky podvodu - záloha předem, prodejce v zahraničí, jen e-mail;
  exekuce, věcné břemeno/dožití, jen spoluvlastnický podíl, družstevní byt bez převodu, nestavební pozemek
  vydávaný za stavební); jinak null.
Odpověz jen JSON s položkou pro KAŽDÝ inzerát:
{{"inzeraty": [{{"k": "<klíč>", "shrnuti": "...", "plusy": [...], "rizika": [...], "varovani": null}}]}}"""

_cile: list[dict] | None = None  # (poskytovatel, model) v pořadí zkoušení; drží se po celý běh


def _hlavicky(klic: str) -> dict:
    return {"Authorization": f"Bearer {klic}", "x-goog-api-key": klic, "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "Hledac/1.0"}


def _poradi(p: dict, m: str):
    """Řazení modelů v nabídce poskytovatele: nejvhodnější první; None = nepoužívat."""
    if any(x in m for x in ("image", "tts", "live", "audio", "embed", "vision", "guard", "whisper", "thinking")):
        return None
    verze = [-int(x) for x in re.findall(r"\d+", m)]
    if p["nazev"] == "Gemini":
        if "flash" not in m:
            return None  # pro (placený) a gemma vynechat; flash je rychlý a v bezplatném tarifu
        return ("lite" in m, "preview" in m or "exp" in m, verze)
    # Cerebras/Groq: velké obecné modely první (česky píší nejlíp), malé až nakonec
    preferovane = ("gpt-oss-120b", "qwen-3-235b", "qwen3", "gpt-oss", "llama")
    return (next((n for n, x in enumerate(preferovane) if x in m), len(preferovane)), "20b" in m or "8b" in m, verze)


def _cile_behu(log) -> list[dict]:
    """Seznam cílů (poskytovatel + model) ze všech poskytovatelů, ke kterým je klíč. Nabídka modelů se čte
    z API, protože názvy se s novými verzemi mění."""
    global _cile
    if _cile is not None:
        return _cile
    nast = nastaveni.nacti()
    _cile = []
    for p in POSKYTOVATELE:
        klic = nast.get(p["klic"])
        if not klic:
            continue
        try:
            req = urllib.request.Request(p["api"] + "models", headers=_hlavicky(klic))
            with urllib.request.urlopen(req, timeout=30) as r:
                nabidka = [m["id"].removeprefix("models/") for m in json.loads(r.read()).get("data", [])]
        except (OSError, ValueError) as e:
            log(f"  AI: {p['nazev']} nedostupný ({e})")
            continue
        vhodne = sorted((m for m in nabidka if _poradi(p, m) is not None), key=lambda m: _poradi(p, m))
        if p["nazev"] == "Gemini":  # 3 nejlepší plné + nejlepší lite (vyšší limit dotazů, záchrana)
            vhodne = [m for m in vhodne if "lite" not in m][:3] + [m for m in vhodne if "lite" in m][:1]
        _cile += [dict(p=p, klic=klic, model=m, mrtvy=False) for m in vhodne[:p["modelu"]]]
    return _cile


_posledni_dotaz: dict[str, float] = {}


def _dotaz(cil: dict, pokyny: str, inzeraty: list[str]) -> dict:
    p = cil["p"]
    cekat = _posledni_dotaz.get(p["nazev"], 0) + p["odstup"] - time.monotonic()
    if cekat > 0:
        time.sleep(cekat)
    telo = {"model": cil["model"], "temperature": 0.2, "max_tokens": 450 * len(inzeraty) + 600,
            "messages": [{"role": "system", "content": pokyny}, {"role": "user", "content": "\n".join(inzeraty)}]}
    if not cil.get("bez_uvahy"):
        telo["reasoning_effort"] = "low"  # bez dlouhého přemýšlení: rychlejší, míň tokenů z limitu
        if "gpt-oss" in cil["model"]:
            telo["max_tokens"] += 3000  # gpt-oss přemýšlí vždy, úvaha se počítá do max_tokens
    req = urllib.request.Request(p["api"] + "chat/completions", data=json.dumps(telo).encode("utf-8"),
                                 method="POST", headers=_hlavicky(cil["klic"]))
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            surove = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 400 and not cil.get("bez_uvahy"):  # model nezná reasoning_effort -> znovu bez něj
            cil["bez_uvahy"] = True
            return _dotaz(cil, pokyny, inzeraty)
        raise
    finally:
        _posledni_dotaz[p["nazev"]] = time.monotonic()
    try:
        obsah = json.loads(surove)["choices"][0]["message"]["content"] or ""
        # model občas obalí JSON do ```json ... ``` nebo před něj napíše větu -> vzít jen objekt
        return json.loads(obsah[obsah.index("{"):obsah.rindex("}") + 1])
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise ValueError(f"nečitelná odpověď ({e}): {surove[:300]!r}") from None


def _otisk(i: dict) -> str:
    """Změní se jen se změnou textu inzerátu (cena ne - ta se hodnotí jinde)."""
    t = json.dumps([i.get("nazev"), i.get("popis") or i.get("text"), i.get("parametry"), (i.get("vybava") or [])[:40]],
                   ensure_ascii=False)
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


def _inzerat(k: str, i: dict, kat: str) -> str:
    udaje = {"klíč": k, "název": i.get("nazev"), "cena Kč": i.get("cena"), "místo": i.get("misto"), "web": i.get("zdroj")}
    udaje |= {"druh": i.get("druh"), "dispozice": i.get("dispozice"), "plocha m²": i.get("plocha"),
              "pozemek m²": i.get("pozemek"), "okres": i.get("okres")}
    udaje["parametry"] = "; ".join(f"{a}: {b}" for a, b in (i.get("parametry") or [])[:30])
    if i.get("vybava"):
        udaje["výbava"] = ", ".join(i["vybava"][:40])
    udaje["text"] = (i.get("popis") or i.get("text") or "")[:MAX_POPIS]
    return json.dumps({k: v for k, v in udaje.items() if v not in (None, "", [])}, ensure_ascii=False)


def _cisti(v: dict) -> dict:
    seznam = lambda x: [str(s).strip() for s in x if str(s).strip()][:3] if isinstance(x, list) else []  # noqa: E731
    varovani = v.get("varovani")
    return {"shrnuti": str(v.get("shrnuti") or "").strip(), "plusy": seznam(v.get("plusy")),
            "rizika": seznam(v.get("rizika")),
            "varovani": str(varovani).strip() if varovani and str(varovani).strip().lower() not in ("null", "none") else None}


def dopln(c, kat: str, inzeraty: list[dict], popis_hledani: str, log=print) -> None:
    """Doplní ke každému inzerátu 'ai' - z paměti (hledac.db), nové a změněné se pošlou modelu."""
    c.execute("CREATE TABLE IF NOT EXISTS ai (id TEXT PRIMARY KEY, otisk TEXT, cas TEXT, vysledek TEXT)")
    fronta = []
    for i in inzeraty:
        row = c.execute("SELECT otisk, vysledek, cas FROM ai WHERE id=?", (i["id"],)).fetchone()
        # Stejný byt na víc webech bere popis z toho webu, který zrovna doběhl dřív -> „jiný“ text, i když se nic
        # nezměnilo. Znovu se proto posílá jen změněný text, jehož postřeh je starší než týden.
        if row and (row[0] == _otisk(i) or row[2] >= (datetime.now() - timedelta(days=OBNOVIT_DNI)).isoformat()):
            i["ai"] = json.loads(row[1])
        else:
            i.pop("ai", None)  # převzatý z minula se starým postřehem - text se změnil
            fronta.append(i)
    if not fronta:
        return
    cile = _cile_behu(log)
    if not cile:
        log(f"  AI: žádný klíč ani dostupný poskytovatel ({len(fronta)} inzerátů bez postřehu)")
        return
    pokyny = POKYNY.format(co=nemovitosti.KATEGORIE[kat]["co"], hledani=popis_hledani)
    celkem, hotovo, dotazu, pauz, pouzite, chyby = len(fronta), 0, 0, 0, set(), []
    while fronta and dotazu < MAX_DOTAZU:
        povedlo = False
        for cil in [x for x in cile if not x["mrtvy"]]:
            davka = fronta[:cil["p"]["na_dotaz"]]
            klice = {str(k + 1): i for k, i in enumerate(davka)}
            try:
                vysledek = _dotaz(cil, pokyny, [_inzerat(k, i, kat) for k, i in klice.items()])
            except urllib.error.HTTPError as e:
                jmeno = f"{cil['p']['nazev']}/{cil['model']}"
                chyby.append(f"{jmeno} {e.code}")
                if e.code in (401, 403):  # špatný klíč: celý poskytovatel pryč
                    for x in cile:
                        x["mrtvy"] = x["mrtvy"] or x["p"] is cil["p"]
                    log(f"  AI: {cil['p']['nazev']} odmítl klíč ({e.code})")
                elif e.code in (404, 429):  # model zmizel / vyčerpaný limit: v tomhle běhu už ne
                    cil["mrtvy"] = True
                continue  # 503 přetížení a ostatní: zkusit další cíl
            except (OSError, ValueError, KeyError) as e:
                chyby.append(f"{cil['p']['nazev']}/{cil['model']} {type(e).__name__}: {str(e)[:100]}")
                continue
            ted = time.strftime("%Y-%m-%dT%H:%M:%S")
            for v in vysledek.get("inzeraty") or []:
                i = klice.get(str(v.get("k"))) if isinstance(v, dict) else None
                if not i or i.get("ai"):
                    continue
                i["ai"] = _cisti(v)
                c.execute("INSERT OR REPLACE INTO ai VALUES (?,?,?,?)",
                          (i["id"], _otisk(i), ted, json.dumps(i["ai"], ensure_ascii=False)))
                hotovo += 1
            c.commit()
            dotazu += 1
            fronta = fronta[len(davka):]  # co model vynechal, zkusí se v příštím běhu
            pouzite.add(f"{cil['p']['nazev']} {cil['model']}")
            if cile[0] is not cil:  # tenhle teď funguje -> dál rovnou on
                cile.remove(cil)
                cile.insert(0, cil)
            povedlo = True
            break
        if povedlo:
            continue
        if pauz >= len(PAUZY_S) or not any(not x["mrtvy"] for x in cile):
            break
        time.sleep(PAUZY_S[pauz])  # všichni přetížení: chvíli počkat
        pauz += 1
    zbyva = celkem - hotovo
    log(f"  AI: {hotovo} nových postřehů" + (f", {zbyva} příště" if zbyva else "") +
        (f" ({', '.join(sorted(pouzite))})" if pouzite else "") +
        (f"; odmítnuto: {', '.join(chyby[:8])}" if chyby else ""))
