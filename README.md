# Hledač nemovitostí – Plzeň a okolí

Osobní hledač pro Domču. Prochází 8 realitních webů, vybírá **rodinné domy na prodej
do 15 mil. Kč a do 20 km od centra Plzně** (od 17. 10. 2026 jen domy; byty a pozemky weby umí dál,
zapínají se v `HLEDAT` v `nemovitosti.py`), slučuje duplicity a pamatuje si, co je nové a co zlevnilo.
Výsledek je jedna zaheslovaná webová stránka (telefon i počítač) a denní souhrn e-mailem.

Stejný princip jako Hledač bytů a aut (`C:\Projects\Hledac`), jen pro nemovitosti a s filtry přímo na stránce.

## Weby

| Web | Jak se hledá | Poznámka |
|---|---|---|
| Sreality | API, okruh kolem Plzně | největší, souřadnice i datum vložení |
| iDnes Reality | výpis po okresech | bez souřadnic → poloha podle obce |
| Bezrealitky | data stránky po okresech | jen od majitelů, malé |
| RealityMix | výpis po okresech | souřadnice z detailu |
| ČeskéReality | výpis po okresech | souřadnice z detailu |
| Reality.cz | výpis po okresech | malý, souřadnice ve výpisu |
| Bazoš | okruh 20 km kolem PSČ 301 00 | bez adresy → poloha podle obce/PSČ |
| Realingo | výpis po okresech | sbírá nabídky z celého netu, většina se sloučí |

Okresy: Plzeň-město, Plzeň-jih, Plzeň-sever, Rokycany (pokrývají celý kruh 20 km). Co je dál než 20 km
od náměstí Republiky, se vyřadí podle souřadnic inzerátu, jinak podle polohy obce (OpenStreetMap).

## Co je natvrdo a co na stránce

- **Natvrdo** (`nemovitosti.py`, `oblast.py`): koupě, do 15 mil. Kč, do 20 km, u domů jen rodinné
  (vily a vícegenerační ano; chaty, chalupy, usedlosti a činžáky ne).
- **Na stránce** (pamatuje si prohlížeč): druh / dispozice, okres, obec, cena do, plocha od–do,
  pozemek od (u domů), vzdálenost od centra; řazení podle novosti, ceny, velikosti, ceny za m²,
  vzdálenosti a doby v nabídce. Mapa ukazuje přesně to, co prošlo filtrem.

## Spuštění

```
Hledač.cmd                 # místní web na http://localhost:8766 s tlačítkem Aktualizovat
py hledac.py               # jednorázově, výsledek v prehled.html
py hledac.py domy          # jen jedna kategorie (byty / domy / pozemky)
py hledac.py --prekreslit  # jen překreslit stránku z posledních dat
```

Jen Python 3.11+ a standardní knihovna (pro šifrování stránky v cloudu ještě `cryptography`).
Osobní nastavení je v `nastaveni.json` (není v gitu): jméno, oslovení, e-mail, klíč AI (viz `nastaveni.py`).

Napoprvé stahuje detaily tisíců inzerátů – každý web na ně má za běh 7 minut, co se nestihne, doplní
se příště. Detaily se drží 3–6 dní v `cache.db`, polohy obcí 90 dní.

## Cloud (GitHub)

Repo je veřejné (Actions zdarma bez limitu minut), v kódu nic tajného není. Workflow
`.github/workflows/hledac.yml` běží každé 2 hodiny od 6 do 22 h, stav drží v Actions cache
(data tak nejsou v gitu) a zašifrovanou stránku dává do větve `gh-pages` → GitHub Pages.

GitHub Secrets:

| Secret | K čemu | Povinné |
|---|---|---|
| `HLAVNI_KLIC` | 32 náhodných bajtů (base64), jimi je stránka zašifrovaná | ano (bez něj by stránka byla veřejná) |
| `HESLO_STRANKY` | kód z pozvánky pro první přihlášení | ano |
| `PRISTUP_KANAL` | skrytý kanál ntfy, kam stránka pošle nově nastavené heslo | ano |
| `JMENO`, `OSLOVENI` | „Hledač · Domča“, „Ahoj Domčo!“ | ne |
| `EMAIL_KOMU` a `SMTP_…`, `EMAIL_OD` | denní souhrn e-mailem (viz níž) | pro souhrn ano |
| `NTFY_KANAL` | souhrn i do aplikace ntfy | ne |
| `AI_API_KLIC` | postřehy AI k inzerátům (Google Gemini, zdarma) | ne |
| `AKTUALIZACE_TOKEN` | tlačítko Aktualizovat spustí hledání přímo ze stránky | ne |

GitHub vypne plánované běhy veřejného repa po 60 dnech bez commitu – stačí občas cokoli commitnout
(nebo workflow znovu zapnout v záložce Actions).

## Přihlášení

Při prvním přihlášení se zadá **kód z pozvánky** a hned potom si Domča nastaví **vlastní heslo** (aspoň 8 znaků).
Stránka je statická, proto to funguje takhle (`sifrovani.py`): obsah je zašifrovaný hlavním klíčem a ten je na
stránce „zamčený“ kódem z pozvánky a nastavenými hesly. Prohlížeč zamkne klíč novým heslem a výsledek (ne heslo)
pošle do skrytého kanálu; další běh v cloudu ho převezme do `pristupy.json` ve větvi `gh-pages` a od té chvíle
kód z pozvánky neplatí. Na zařízení, kde si heslo nastavil, platí hned; jinde do dvou hodin.

Zapomenuté heslo: smazat `pristupy.json` ve větvi `gh-pages` – po dalším běhu zase platí kód z pozvánky.

## Denní souhrn e-mailem

**Jen z cloudu, jednou denně kolem 20:00** – jeden e-mail se vším, co od minulého souhrnu přibylo nebo zlevnilo
(po kategoriích, u každého inzerátu fotka, cena, cena za m², údaje a odkaz; nejvýš 15 z kategorie, zbytek počtem).
Když nic nepřibylo, nic nepřijde. Místní server (`Hledač.cmd`) nic neposílá. Souhrn jde při prvním běhu po 20:00
pražského času (`SOUHRN_HODINY` v `hledac.py`).

Posílá se přes SMTP (secrets `EMAIL_KOMU`, `EMAIL_OD`, `SMTP_SERVER`, `SMTP_PORT`, `SMTP_UZIVATEL`, `SMTP_HESLO`):

- **Gmail:** účet s dvoufázovým ověřením → https://myaccount.google.com/apppasswords → vytvořit heslo aplikace
  (16 znaků). `SMTP_SERVER` = `smtp.gmail.com`, `SMTP_PORT` = `587`, `SMTP_UZIVATEL` = `EMAIL_OD` = adresa toho
  Gmailu, `SMTP_HESLO` = heslo aplikace. Běžné heslo k Gmailu nikdy.
- **Brevo** (zdarma 300 e-mailů denně, bez karty): účet → Settings → SMTP & API → SMTP key.
  `SMTP_SERVER` = `smtp-relay.brevo.com`, `SMTP_PORT` = `587`, `SMTP_UZIVATEL` = přihlašovací login z té stránky,
  `SMTP_HESLO` = SMTP klíč, `EMAIL_OD` = ověřený odesílatel (Senders).

Nepovinně jde stejný souhrn i do aplikace **ntfy** (secret `NTFY_KANAL`).
