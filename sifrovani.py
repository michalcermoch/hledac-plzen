"""Zašifrovaná stránka pro veřejné GitHub Pages - s heslem, které si Domča nastaví sám při prvním přihlášení.

Jak to funguje (stránka je statická, server nemá kam si heslo uložit):
  - Obsah (gzip) je zašifrovaný HLAVNÍM KLÍČEM (32 B, GitHub Secret HLAVNI_KLIC) - AES-256-GCM.
  - Hlavní klíč je na stránce několikrát „zamčený“ heslem (PBKDF2-SHA256 310k -> AES-GCM): kódem z pozvánky
    (Secret HESLO_STRANKY) a hesly, která si uživatel nastavil. Kdo zná jedno z nich, klíč odemkne.
  - První přihlášení: kód z pozvánky -> stránka si řekne o vlastní heslo -> zamkne jím hlavní klíč a výsledek
    (ne heslo!) pošle do skrytého kanálu ntfy (název je zašifrovaný hlavním klíčem). Na tomto zařízení platí
    hned, další běh v cloudu ho převezme (pristupy.json v gh-pages) a od té chvíle kód z pozvánky neplatí.
  - Zapomenuté heslo: smazat pristupy.json ve větvi gh-pages -> zase platí kód z pozvánky.
Telefon si může odemčený klíč pamatovat (localStorage), takže se heslo zadává jen jednou.
"""
import base64
import gzip
import hashlib
import json
import os
import re
import urllib.request
from html import escape

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERACI = 310_000  # PBKDF2 - doporučení OWASP pro SHA-256
MAX_PRISTUPU = 3   # nejnovější nastavená hesla (starší = změněná) se zahodí
NTFY = "https://ntfy.sh/"

b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731


def _zamkni_klic(klic: bytes, heslo: str) -> dict:
    sul, nonce = os.urandom(16), os.urandom(12)
    k = hashlib.pbkdf2_hmac("sha256", heslo.encode("utf-8"), sul, ITERACI, dklen=32)
    return {"sul": b64(sul), "nonce": b64(nonce), "data": b64(AESGCM(k).encrypt(nonce, klic, None)), "iteraci": ITERACI}


def _zasifruj(klic: bytes, data: bytes) -> dict:
    nonce = os.urandom(12)
    return {"nonce": b64(nonce), "data": b64(AESGCM(klic).encrypt(nonce, data, None))}


def platny_pristup(v) -> bool:
    """Zamčený klíč od prohlížeče: jen správný tvar (heslo ověřit nejde - to zná jen uživatel)."""
    try:
        return (isinstance(v, dict) and len(base64.b64decode(v["sul"])) == 16 and len(base64.b64decode(v["nonce"])) == 12
                and len(base64.b64decode(v["data"])) == 48 and 100_000 <= int(v["iteraci"]) <= 2_000_000)
    except (KeyError, ValueError, TypeError):
        return False


def _zpravy(kanal: str) -> list[dict]:
    """Zprávy ze skrytého kanálu ntfy (drží je 12 h), nejstarší první."""
    with urllib.request.urlopen(f"{NTFY}{kanal}/json?poll=1&since=all", timeout=30) as r:
        zpravy = [json.loads(radek) for radek in r.read().decode("utf-8").splitlines() if radek.strip()]
    return sorted((z for z in zpravy if z.get("event") == "message"), key=lambda z: z.get("time", 0))


def _rozsifruj(klic: bytes, obal: dict) -> bytes:
    return AESGCM(klic).decrypt(base64.b64decode(obal["nonce"]), base64.b64decode(obal["data"]), None)


def novy_email(kanal: str, klic: bytes, ulozeny: dict | None, log=print) -> dict | None:
    """E-mail pro upozornění, který si uživatel nastavil na stránce (po prvním přihlášení vlastním heslem).
    Prohlížeč ho pošle do kanálu zašifrovaný hlavním klíčem; vrací záznam k uložení (email.json v gh-pages,
    zašifrovaný - repo je veřejné), nejnovější vyhrává. Beze změny vrací uložený."""
    try:
        zpravy = _zpravy(kanal)
    except Exception as e:
        log(f"e-mail: kanál nejde přečíst ({type(e).__name__}) - beru, co bylo")
        return ulozeny
    for z in reversed(zpravy):
        try:
            obal = json.loads(z.get("message") or "")["email"]
            adresa = json.loads(_rozsifruj(klic, obal))["email"].strip()
        except Exception:
            continue
        if re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+", adresa) and len(adresa) <= 120:
            if not ulozeny or email_z(ulozeny, klic) != adresa:
                log("e-mail: uživatel si nastavil novou adresu pro upozornění")
                return _zasifruj(klic, json.dumps({"email": adresa}).encode("utf-8"))
            break
    return ulozeny


def email_z(zaznam: dict, klic: bytes) -> str | None:
    try:
        return json.loads(_rozsifruj(klic, zaznam))["email"]
    except Exception:
        return None


def nove_pristupy(kanal: str, pristupy: list[dict], log=print) -> list[dict]:
    """Přidá hesla, která si někdo nastavil od minula (zprávy v kanálu ntfy drží 12 h, běh je každé 2 h)."""
    try:
        zpravy = _zpravy(kanal)
    except Exception as e:
        log(f"přístupy: kanál nejde přečíst ({type(e).__name__}) - beru, co bylo")
        return pristupy
    znama = {p["data"] for p in pristupy}
    nove = []
    for z in zpravy:
        try:
            v = json.loads(z.get("message") or "")
        except ValueError:
            continue
        if platny_pristup(v) and v["data"] not in znama:
            znama.add(v["data"])
            nove.append({k: v[k] for k in ("sul", "nonce", "data", "iteraci")} | {"cas": z.get("time")})
    if nove:
        log(f"přístupy: {len(nove)} nově nastavené heslo")
    return (pristupy + nove)[-MAX_PRISTUPU:]


def zasifruj(html: str, klic: bytes, pozvanka: str | None, pristupy: list[dict], kanal: str | None,
             jmeno: str = "", email_nastaven: bool = False) -> str:
    """klic = hlavní klíč (32 B); pozvanka = kód pro první přihlášení (platí, jen dokud si nikdo nenastavil heslo);
    email_nastaven = uživatel už si e-mail pro upozornění nastavil (stránka se pak neptá)."""
    vstupy = [{"typ": "heslo"} | {k: p[k] for k in ("sul", "nonce", "data", "iteraci")} for p in pristupy]
    if pozvanka and not pristupy:
        vstupy.append({"typ": "pozvanka"} | _zamkni_klic(klic, pozvanka))
    balik = {"obsah": _zasifruj(klic, gzip.compress(html.encode("utf-8"), 9)), "vstupy": vstupy,
             "kanal": _zasifruj(klic, kanal.encode("utf-8")) if kanal else None, "email": email_nastaven}
    kdo = f" · {escape(jmeno)}" if jmeno else ""
    return ZAMEK.replace("__KDO__", kdo).replace("__BALIK__", json.dumps(balik))


ZAMEK = """<!doctype html><html lang="cs"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Hledač__KDO__</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
background:linear-gradient(135deg,#10251c,#1f4a37 45%,#2f6b4f);color:#f3f1ea}
form{width:min(380px,calc(100% - 32px));background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);
border-radius:20px;padding:28px 24px;backdrop-filter:blur(12px);box-shadow:0 20px 60px rgba(0,0,0,.35)}
form[hidden]{display:none}
h1{margin:0 0 4px;font-size:24px}p{margin:0 0 18px;color:rgba(243,241,234,.78);font-size:14px}
input[type=password],input[type=text]{width:100%;box-sizing:border-box;font:inherit;padding:12px 14px;border-radius:12px;
border:1px solid rgba(255,255,255,.3);background:rgba(255,255,255,.95);color:#10251c;margin-bottom:12px}
label{display:flex;gap:8px;align-items:center;font-size:13px;color:rgba(243,241,234,.85);margin-bottom:16px}
button{width:100%;font:600 15px system-ui,sans-serif;padding:12px;border:0;border-radius:12px;background:#e9b95a;color:#2a1c04;cursor:pointer}
button:disabled{opacity:.6;cursor:progress}
input[type=email]{width:100%;box-sizing:border-box;font:inherit;padding:12px 14px;border-radius:12px;
border:1px solid rgba(255,255,255,.3);background:rgba(255,255,255,.95);color:#10251c;margin-bottom:12px}
.pozdeji{margin-top:8px;background:none;color:rgba(243,241,234,.8);font-weight:500}
.chyba{color:#ffb4a8;font-size:13px;min-height:1.2em;margin:-4px 0 10px}
small{display:block;margin-top:14px;font-size:12px;color:rgba(243,241,234,.6)}
</style></head><body>
<form id="f1" autocomplete="on"><h1>🏡 Hledač__KDO__</h1><p id="p1">Nemovitosti v Plzni a okolí do 20 km.</p>
<input type="password" id="h1" autocomplete="current-password" placeholder="Heslo" autofocus>
<div class="chyba" id="e1"></div>
<label><input type="checkbox" id="z" checked> Zapamatovat na tomto zařízení</label>
<button>Odemknout</button></form>
<form id="f2" hidden autocomplete="on"><h1>Vítej! 👋</h1><p>Teď si nastav vlastní heslo. Kód z pozvánky pak přestane platit.</p>
<input type="text" name="username" autocomplete="username" value="Hledač" hidden>
<input type="password" id="n1" autocomplete="new-password" placeholder="Nové heslo (aspoň 8 znaků)">
<input type="password" id="n2" autocomplete="new-password" placeholder="Nové heslo znovu">
<div class="chyba" id="e2"></div>
<button id="b2">Uložit heslo a otevřít</button>
<small>Na tomhle zařízení platí hned, na ostatních nejpozději do dvou hodin (po další aktualizaci přehledu).</small></form>
<form id="f3" hidden autocomplete="on"><h1>Upozornění e-mailem 📬</h1>
<p>Kam ti mám posílat novinky? Jednou denně kolem 20:00 přijde souhrn nových a zlevněných domů – jen když nějaké přibyly.</p>
<input type="email" id="m1" autocomplete="email" inputmode="email" placeholder="tvuj@email.cz">
<div class="chyba" id="e3"></div>
<button id="b3">Uložit e-mail</button>
<button type="button" class="pozdeji" id="b3p">Teď ne</button>
<small>Adresa se uloží zašifrovaně, vidí ji jen Hledač.</small></form>
<script>
// Vše uvnitř funkce: přehled se zapíše do stejného okna (document.write) a globální const/let zámku
// by kolidovaly s jeho skriptem („Identifier '$' has already been declared“ -> prázdná stránka).
(()=>{
const B=__BALIK__,ITER=310000;
const d=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0)),e64=b=>btoa(String.fromCharCode(...new Uint8Array(b)));
const ls={get:k=>{try{return localStorage.getItem(k)}catch(e){return null}},set:(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}},
  del:k=>{try{localStorage.removeItem(k)}catch(e){}}};
const $=id=>document.getElementById(id);
async function kdf(heslo,sul,iter){const k=await crypto.subtle.importKey('raw',new TextEncoder().encode(heslo),'PBKDF2',false,['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2',salt:sul,iterations:iter,hash:'SHA-256'},k,{name:'AES-GCM',length:256},false,['encrypt','decrypt'])}
async function aes(klic,obal){const k=await crypto.subtle.importKey('raw',klic,'AES-GCM',false,['decrypt']);
  return crypto.subtle.decrypt({name:'AES-GCM',iv:d(obal.nonce)},k,d(obal.data))}
// nastavené heslo, které cloud ještě nepřevzal, platí na tomhle zařízení hned
let cekajici=null;try{cekajici=JSON.parse(ls.get('hledac-plzen-cekajici'))}catch(e){}
if(cekajici&&B.vstupy.some(v=>v.data===cekajici.data)){ls.del('hledac-plzen-cekajici');cekajici=null}
const vstupy=B.vstupy.concat(cekajici?[Object.assign({typ:'heslo'},cekajici)]:[]);
const jenPozvanka=vstupy.length&&vstupy.every(v=>v.typ==='pozvanka');
if(jenPozvanka){$('p1').textContent='První přihlášení – zadej kód z pozvánky.';$('h1').placeholder='Kód z pozvánky';$('h1').autocomplete='off'}
async function klicZHesla(heslo){for(const v of vstupy){try{const k=await kdf(heslo,d(v.sul),v.iteraci);
  return {klic:new Uint8Array(await crypto.subtle.decrypt({name:'AES-GCM',iv:d(v.nonce)},k,d(v.data))),typ:v.typ}}catch(e){}}return null}
async function otevri(klic){const data=await aes(klic,B.obsah);
  const html=await new Response(new Blob([data]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
  document.open();document.write(html);document.close()}
// E-mail pro upozornění: zeptat se při prvním otevření vlastním heslem (ne kódem z pozvánky), dokud ho cloud
// nemá; „Teď ne“ = zeptat se znovu za týden. Hodnota v ls: 'ulozen' nebo čas odložení.
const TYDEN=7*864e5;
function chciEmail(){if(B.email||!B.kanal)return false;const s=ls.get('hledac-plzen-email');
  return !s||(s!=='ulozen'&&Date.now()-(+s||0)>TYDEN)}
async function poOdemceni(klic){if(chciEmail()){odemceny=klic;$('f1').hidden=true;$('f2').hidden=true;$('f3').hidden=false;$('m1').focus();return}
  await otevri(klic)}
let odemceny=null;
(async()=>{const k=ls.get('hledac-plzen-klic');if(!k)return;try{await aes(d(k),B.kanal||B.obsah);await poOdemceni(d(k))}catch(e){ls.del('hledac-plzen-klic')}})();
$('f1').onsubmit=async ev=>{ev.preventDefault();const e=$('e1');e.textContent='Odemykám…';
  const r=await klicZHesla($('h1').value);if(!r){e.textContent=jenPozvanka?'Špatný kód.':'Špatné heslo.';return}
  if($('z').checked)ls.set('hledac-plzen-klic',e64(r.klic));
  if(r.typ==='pozvanka'&&B.kanal){odemceny=r.klic;$('f1').hidden=true;$('f2').hidden=false;$('n1').focus();return}
  try{await poOdemceni(r.klic)}catch(x){e.textContent='Stránku se nepodařilo otevřít.'}};
$('f3').onsubmit=async ev=>{ev.preventDefault();const e=$('e3'),m=$('m1').value.trim();
  if(!/^[^@\\s,;]+@[^@\\s,;]+\\.[^@\\s,;]+$/.test(m)){e.textContent='Tohle nevypadá jako e-mailová adresa.';return}
  $('b3').disabled=true;e.textContent='Ukládám…';
  try{const iv=crypto.getRandomValues(new Uint8Array(12));
    const k=await crypto.subtle.importKey('raw',odemceny,'AES-GCM',false,['encrypt']);
    const data=await crypto.subtle.encrypt({name:'AES-GCM',iv},k,new TextEncoder().encode(JSON.stringify({email:m})));
    const kanal=new TextDecoder().decode(await aes(odemceny,B.kanal));
    const r=await fetch('https://ntfy.sh/'+kanal,{method:'POST',body:JSON.stringify({email:{nonce:e64(iv),data:e64(data)}})});
    if(!r.ok)throw new Error(r.status);ls.set('hledac-plzen-email','ulozen');await otevri(odemceny)}
  catch(x){$('b3').disabled=false;e.textContent='E-mail se nepodařilo uložit ('+x.message+'). Zkus to znovu.'}};
$('b3p').onclick=async()=>{ls.set('hledac-plzen-email',String(Date.now()));await otevri(odemceny)};
$('f2').onsubmit=async ev=>{ev.preventDefault();const e=$('e2'),h=$('n1').value;
  if(h.length<8){e.textContent='Heslo musí mít aspoň 8 znaků.';return}if(h!==$('n2').value){e.textContent='Hesla se neshodují.';return}
  $('b2').disabled=true;e.textContent='Ukládám…';
  try{const sul=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12));
    const k=await kdf(h,sul,ITER),data=await crypto.subtle.encrypt({name:'AES-GCM',iv},k,odemceny);
    const v={sul:e64(sul),nonce:e64(iv),data:e64(data),iteraci:ITER};
    const kanal=new TextDecoder().decode(await aes(odemceny,B.kanal));
    const r=await fetch('https://ntfy.sh/'+kanal,{method:'POST',body:JSON.stringify(v)});if(!r.ok)throw new Error(r.status);
    ls.set('hledac-plzen-cekajici',JSON.stringify(v));await otevri(odemceny)}
  catch(x){$('b2').disabled=false;e.textContent='Heslo se nepodařilo uložit ('+x.message+'). Zkus to znovu.'}};
})();
</script></body></html>"""
