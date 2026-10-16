# Hledač nemovitostí – Plzeň a okolí

Osobní hledač pro Domču. Prochází 8 realitních webů, vybírá **byty, rodinné domy a pozemky na prodej
do 15 mil. Kč a do 20 km od centra Plzně**, slučuje duplicity a pamatuje si, co je nové a co zlevnilo.
Výsledek je jedna zaheslovaná webová stránka (telefon i počítač) a upozornění na mobil.

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
Osobní nastavení je v `nastaveni.json` (není v gitu): jméno, oslovení, kanál ntfy, WhatsApp, klíč AI.

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
| `NTFY_KANAL` | kanál pro push na mobil | ne |
| `WHATSAPP_TELEFON`, `WHATSAPP_KLIC` | zprávy na WhatsApp (CallMeBot) | ne |
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

## Upozornění na mobil

**Jen z cloudu, jednou denně kolem 20:00** – jeden souhrn všeho, co od minulého souhrnu přibylo nebo zlevnilo
(po kategoriích, nejvýš 8 inzerátů z každé, zbytek počtem). Když nic nepřibylo, nic nepřijde. Místní server
(`Hledač.cmd`) nic neposílá. Souhrn jde při prvním běhu po 20:00 pražského času (`SOUHRN_HODINY` v `hledac.py`).

- **ntfy** (doporučeno): nainstalovat aplikaci *ntfy* (Android/iPhone), dát „Subscribe to topic“
  a vložit název kanálu. Klepnutím na souhrn se otevře přehled.
- **WhatsApp** (CallMeBot, zdarma): Domča si podle návodu na
  <https://www.callmebot.com/blog/free-api-whatsapp-messages/> uloží číslo bota (aktuální je v návodu)
  a pošle mu zprávu `I allow callmebot to send me messages`. Bot odpoví klíčem (apikey). Telefon (ve tvaru +420…) a klíč
  se vloží do secrets `WHATSAPP_TELEFON` a `WHATSAPP_KLIC`. Ve WhatsAppu je u každého inzerátu i odkaz.
- **E-mail** zatím ne: chtělo by to heslo k poštovnímu účtu uložené v GitHubu.
