"""Plzeňská kobka - mini hra ve stylu DnD na dlouhou chvíli (vtip pro Domču).

Krátké dobrodružství (3 náhodná setkání + Drak Katastr), hod kostkou d20 proti obtížnosti. Verze pro PC (klávesy)
a pro mobil (velká tlačítka, vibrace) - hra pozná zařízení a nabídne tu správnou. Při prvním spuštění provede
průvodce krok za krokem. Odměnou za výhru je skutečný dům z výsledků hledání (DATA z prehled.py).
Vše běží v prohlížeči, nic se neposílá; v localStorage jen zvolená verze, průvodce hotový a nejlepší skóre.
"""

TLACITKO = ('<button class="hra-tlacitko" id="hraOtevrit" type="button" title="Plzeňská kobka – hra na dlouhou chvíli" '
            'aria-label="Hra na dlouhou chvíli"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.5 20.5 7.5v9L12 21.5 3.5 16.5v-9z"/>'
            '<path d="M12 2.5 7.5 15h9zM3.5 7.5 7.5 15 12 21.5 16.5 15l4-7.5M7.5 15H3.5M16.5 15h4"/></svg></button>')

HTML = """<dialog class="hra" id="hra" aria-label="Plzeňská kobka">
  <div class="h-okno">
    <header class="h-hlava">
      <b class="h-titul">🐉 Plzeňská kobka</b>
      <div class="h-tlacitka">
        <button type="button" class="h-mini" data-h="verze" title="Přepnout verzi PC / mobil">💻 / 📱</button>
        <button type="button" class="h-mini" data-h="pruvodce" title="Průvodce">?</button>
        <button type="button" class="h-mini" data-h="zavrit" title="Zavřít (Esc)" aria-label="Zavřít">×</button>
      </div>
    </header>
    <div class="h-obsah"></div>
  </div>
  <div class="h-pruvodce" hidden><div class="h-svetlo"></div><div class="h-bublina" role="dialog" aria-live="polite">
    <p></p><div class="h-bublina-akce"><span class="h-krok"></span><button type="button" class="h-preskocit">Přeskočit</button>
    <button type="button" class="h-dalsi">Další</button></div></div></div>
</dialog>"""

CSS = r"""
.hra-tlacitko{display:inline-grid;place-items:center;width:38px;height:38px;border-radius:12px;cursor:pointer;margin-right:6px;
color:rgba(244,241,234,.85);background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);transition:transform .3s,background .3s}
.hra-tlacitko:hover{background:rgba(255,255,255,.16);transform:rotate(-20deg)}
.hra{--h-bg:#16131f;--h-panel:#221d2e;--h-panel-2:#2c2540;--h-line:#3d3456;--h-text:#f3ecdc;--h-muted:#b3a88f;--h-gold:#e7b84b;
--h-red:#e0604f;--h-green:#74c47a;--h-accent:#8f7cf0;padding:0;border:0;background:transparent;color:var(--h-text);
max-width:none;max-height:none;font:15px/1.5 Inter,system-ui,sans-serif;overflow:visible}
.hra::backdrop{background:rgba(8,6,14,.72);backdrop-filter:blur(3px)}
.hra .h-okno{background:radial-gradient(120% 80% at 50% 0%,#2a2140 0%,var(--h-bg) 60%);display:flex;flex-direction:column;overflow:hidden}
.hra.pc .h-okno{width:min(980px,94vw);height:min(700px,92vh);border-radius:20px;border:1px solid var(--h-line);box-shadow:0 30px 80px rgba(0,0,0,.5)}
.hra.mob{margin:0;width:100vw;height:100dvh}.hra.mob .h-okno{width:100vw;height:100dvh;padding-bottom:env(safe-area-inset-bottom)}
.h-hlava{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 16px;border-bottom:1px solid var(--h-line)}
.h-titul{font:800 17px "Plus Jakarta Sans",Inter,sans-serif;letter-spacing:-.01em;color:var(--h-gold)}
.h-tlacitka{display:flex;gap:6px}
.h-mini{min-width:36px;height:36px;border-radius:10px;border:1px solid var(--h-line);background:var(--h-panel);color:var(--h-text);
cursor:pointer;font:700 14px Inter,sans-serif;padding:0 9px}.h-mini:hover{background:var(--h-panel-2)}
.h-obsah{flex:1;min-height:0;overflow:auto;padding:18px}
.hra h2{font:800 24px/1.2 "Plus Jakarta Sans",Inter,sans-serif;margin:0 0 6px;letter-spacing:-.02em}
.hra h3{font:800 20px/1.25 "Plus Jakarta Sans",Inter,sans-serif;margin:4px 0 8px}
.h-pod{color:var(--h-muted);margin:0 0 18px}
.h-volby{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.h-volba{position:relative;text-align:left;cursor:pointer;border:1px solid var(--h-line);background:var(--h-panel);color:var(--h-text);
border-radius:16px;padding:16px;display:flex;flex-direction:column;gap:6px;transition:transform .2s,border-color .2s,background .2s}
.h-volba:hover,.h-volba:focus-visible{transform:translateY(-2px);border-color:var(--h-gold);background:var(--h-panel-2);outline:0}
.h-volba .h-velka{font-size:34px;line-height:1}.h-volba b{font:800 16px "Plus Jakarta Sans",Inter,sans-serif}
.h-volba small{color:var(--h-muted);font-size:13px}
.h-volba.dop{border-color:var(--h-gold);box-shadow:0 0 0 1px var(--h-gold) inset}
.h-stitek{position:absolute;top:12px;right:12px;font:700 11px Inter,sans-serif;color:#2a1d00;background:var(--h-gold);border-radius:99px;padding:3px 8px}
.h-staty{display:flex;gap:10px;font:700 13px Inter,sans-serif;color:var(--h-muted)}.h-staty span b{color:var(--h-text)}
.h-hra{display:grid;gap:16px}
.hra.pc .h-hra{grid-template-columns:1.35fr 1fr;height:100%}
.h-scena{background:var(--h-panel);border:1px solid var(--h-line);border-radius:18px;padding:18px;display:flex;flex-direction:column;min-height:0;overflow:auto}
.h-ikona{font-size:64px;line-height:1;filter:drop-shadow(0 8px 18px rgba(0,0,0,.4));animation:h-vznes 3s ease-in-out infinite}
@keyframes h-vznes{50%{transform:translateY(-6px)}}
.h-kolo{font:700 12px Inter,sans-serif;text-transform:uppercase;letter-spacing:.1em;color:var(--h-accent);margin-top:12px}
.h-text{margin:0;color:#e3dac6}
.h-vysledek{margin-top:14px;padding:12px 14px;border-radius:12px;font-weight:600;animation:h-prolni .3s ease}
.h-vysledek.ok{background:rgba(116,196,122,.14);color:#bfe8c2;border:1px solid rgba(116,196,122,.35)}
.h-vysledek.ko{background:rgba(224,96,79,.14);color:#f4c0b8;border:1px solid rgba(224,96,79,.35)}
.h-vysledek small{display:block;font-weight:500;opacity:.8;margin-top:4px}
@keyframes h-prolni{from{opacity:0;transform:translateY(6px)}}
.h-panel{display:flex;flex-direction:column;gap:12px;min-height:0}
.h-postava{background:var(--h-panel);border:1px solid var(--h-line);border-radius:16px;padding:12px 14px;display:flex;flex-direction:column;gap:8px}
.h-jmeno{display:flex;align-items:center;gap:8px;font:800 15px "Plus Jakarta Sans",Inter,sans-serif}
.h-hp{height:10px;border-radius:99px;background:#3a2f3a;overflow:hidden}.h-hp i{display:block;height:100%;border-radius:inherit;
background:linear-gradient(90deg,#d9534f,#f08a5d);transition:width .5s ease}
.h-radek{display:flex;align-items:center;justify-content:space-between;gap:8px;font:700 13px Inter,sans-serif;color:var(--h-muted)}
.h-radek b{color:var(--h-text)}
.h-pivo{border:1px solid var(--h-line);background:var(--h-panel-2);color:var(--h-text);border-radius:10px;padding:6px 10px;cursor:pointer;font:700 13px Inter,sans-serif}
.h-pivo[disabled]{opacity:.4;cursor:default}
.h-akce{display:grid;gap:8px}
.h-akce button{display:flex;align-items:center;gap:10px;text-align:left;border:1px solid var(--h-line);background:var(--h-panel);color:var(--h-text);
border-radius:14px;padding:10px 12px;cursor:pointer;font:700 15px Inter,sans-serif;transition:border-color .2s,background .2s,transform .15s}
.h-akce button:hover:not([disabled]){border-color:var(--h-accent);background:var(--h-panel-2)}
.h-akce button.on{border-color:var(--h-gold);background:#3a2f1a}
.h-akce button[disabled]{opacity:.45;cursor:default}
.h-akce .ik{font-size:22px}.h-akce span{display:flex;flex-direction:column;flex:1}
.h-akce small{font:500 12px Inter,sans-serif;color:var(--h-muted)}
.h-akce kbd{font:700 11px Inter,sans-serif;color:var(--h-muted);border:1px solid var(--h-line);border-radius:6px;padding:1px 6px}
.hra.mob .h-akce kbd{display:none}
.h-hod{display:flex;align-items:center;gap:12px}
.h-kostka{flex:none;width:84px;height:84px;border:0;background:none;padding:0;cursor:pointer;color:var(--h-gold);position:relative}
/* d20: barvy stěn přes proměnné (kritický zásah zezelená, trapas zčervená) */
.h-d20{--d0:#f8dc86;--d1:#fdeab0;--d2:#efc75e;--d3:#d6a33f;--d4:#b8852c;--d5:#946620;--dh:#4a3208;display:block;width:100%;height:100%;overflow:visible}
.h-d20 .h-cislo{font:800 21px "Plus Jakarta Sans",Inter,sans-serif;fill:#2a1d00}
.h-d20 .h-male text{font:700 8px Inter,sans-serif;fill:#3b2806;opacity:.45}
.krit .h-d20{--d0:#c9f2b8;--d1:#e2fbd6;--d2:#9ddc85;--d3:#74c25c;--d4:#4f9a3e;--d5:#367a2c;--dh:#163d10}
.trapas .h-d20{--d0:#f6b3a6;--d1:#fbd1c8;--d2:#ec8b78;--d3:#d4644f;--d4:#ad4633;--d5:#862f22;--dh:#3d0f08}
.h-kostka svg{filter:drop-shadow(0 6px 14px rgba(231,184,75,.3))}
.h-kostka[disabled]{opacity:.45;cursor:default}.h-kostka.krit,.h-kostka.trapas{opacity:1}
.h-kostka.ceka{animation:h-pulz 1.2s ease-in-out infinite}.h-kostka.ceka svg{filter:drop-shadow(0 0 18px rgba(231,184,75,.6))}
@keyframes h-pulz{50%{transform:scale(1.08) rotate(-6deg)}}
.h-kostka.toci svg{animation:h-toc 1.1s cubic-bezier(.2,.7,.3,1)}
@keyframes h-toc{to{transform:rotate(720deg)}}
.h-kostka.krit svg{filter:drop-shadow(0 0 16px rgba(116,196,122,.7))}
/* velká kostka při hodu */
.h-okno{position:relative}
.h-hod-velky{position:absolute;inset:0;z-index:5;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;
background:radial-gradient(circle at 50% 45%,rgba(22,19,31,.5),rgba(10,8,16,.86));animation:h-prolni .2s ease;cursor:pointer;transition:opacity .35s}
.h-hod-velky .h-d20{width:min(210px,52vw);height:auto;animation:h-kutal 1.1s cubic-bezier(.25,.8,.3,1) both;filter:drop-shadow(0 24px 30px rgba(0,0,0,.6))}
@keyframes h-kutal{0%{transform:translate(-160%,-70%) rotate(-620deg) scale(.45);opacity:0}
40%{transform:translate(12%,10%) rotate(-80deg) scale(1.06);opacity:1}62%{transform:translate(-5%,-8%) rotate(24deg) scale(.95)}
80%{transform:translate(2%,2%) rotate(-7deg) scale(1.02)}100%{transform:none}}
.h-hod-velky b{font:800 22px "Plus Jakarta Sans",Inter,sans-serif;color:var(--h-gold);text-shadow:0 2px 12px rgba(0,0,0,.6);min-height:30px;opacity:0}
.h-hod-velky.dopad b{opacity:1;animation:h-pop .35s cubic-bezier(.3,1.6,.5,1)}
.h-hod-velky.dopad .h-d20{animation:h-dopad .35s ease}
.h-hod-velky.krit b{color:var(--h-green);font-size:28px}.h-hod-velky.trapas b{color:var(--h-red);font-size:28px}
.h-hod-velky.krit .h-d20{filter:drop-shadow(0 0 40px rgba(116,196,122,.85))}
.h-hod-velky.pryc{opacity:0}
@keyframes h-pop{from{transform:scale(.5);opacity:0}}
@keyframes h-dopad{40%{transform:scale(1.12,.9)}}
.h-napoveda{font-size:13px;color:var(--h-muted);flex:1}
.h-dal,.h-hlavni{border:0;border-radius:14px;padding:12px 18px;cursor:pointer;font:800 15px "Plus Jakarta Sans",Inter,sans-serif;
background:var(--h-gold);color:#2a1d00}.h-dal[hidden]{display:none}
.h-druhe{border:1px solid var(--h-line);border-radius:14px;padding:12px 18px;cursor:pointer;font:700 14px Inter,sans-serif;background:var(--h-panel);color:var(--h-text)}
.h-konec{max-width:560px;margin:0 auto;text-align:center;display:flex;flex-direction:column;align-items:center;gap:12px}
.h-konec .h-ikona{font-size:80px}
.h-dum{width:100%;text-align:left;background:var(--h-panel);border:1px solid var(--h-gold);border-radius:16px;overflow:hidden}
.h-dum img{display:block;width:100%;height:190px;object-fit:cover;background:#2c2540}
.h-dum div{padding:12px 14px}.h-dum b{display:block}.h-dum small{color:var(--h-muted)}
.h-konec-akce{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}
/* mobil: kompaktní, akce dole na dosah palce */
.hra.mob .h-obsah{padding:12px}
.hra.mob .h-hra{grid-template-rows:auto 1fr auto;min-height:100%}
.hra.mob .h-scena{padding:14px}.hra.mob .h-ikona{font-size:48px}.hra.mob h3{font-size:18px}
.hra.mob .h-panel{display:contents}
.hra.mob .h-postava{order:-1;padding:10px 12px}
.hra.mob .h-ovladani{position:sticky;bottom:0;background:linear-gradient(transparent,var(--h-bg) 18%);padding-top:14px;display:flex;flex-direction:column;gap:10px}
.hra.mob .h-akce{grid-template-columns:repeat(3,1fr)}
.hra.mob .h-akce button{flex-direction:column;text-align:center;gap:2px;padding:10px 6px;min-height:76px;font-size:14px}
.hra.mob .h-akce span{align-items:center}
.hra.mob .h-kostka{width:76px;height:76px}
.hra.mob .h-dal,.hra.mob .h-hlavni{padding:15px 18px;font-size:16px}
.hra.pc .h-ovladani{display:flex;flex-direction:column;gap:12px}
/* průvodce */
.h-pruvodce{position:fixed;inset:0;z-index:10}.h-pruvodce[hidden]{display:none}
.h-svetlo{position:fixed;border-radius:14px;box-shadow:0 0 0 9999px rgba(8,6,14,.7),0 0 0 3px var(--h-gold);transition:all .35s cubic-bezier(.2,.8,.2,1);pointer-events:none}
.h-bublina{position:fixed;width:min(340px,calc(100vw - 32px));background:#fbf6ea;color:#231b10;border-radius:16px;padding:14px 16px;
box-shadow:0 18px 50px rgba(0,0,0,.45);transition:top .35s,left .35s;animation:h-prolni .3s ease}
.h-bublina p{margin:0 0 12px;font-size:14.5px;line-height:1.5}
.h-bublina-akce{display:flex;align-items:center;gap:8px}.h-krok{flex:1;font:700 12px Inter,sans-serif;color:#8a7c60}
.h-preskocit{border:0;background:none;color:#8a7c60;font:600 13px Inter,sans-serif;cursor:pointer;padding:8px}
.h-dalsi{border:0;border-radius:10px;background:#231b10;color:#fbf6ea;font:700 13px Inter,sans-serif;padding:9px 14px;cursor:pointer}
@media (prefers-reduced-motion:reduce){.h-ikona,.h-kostka.ceka,.h-kostka.toci svg{animation:none}}
"""

JS = r"""
// Plzeňská kobka: všechno v jedné funkci, ať nic nekoliduje se skripty přehledu
(()=>{const dlg=document.getElementById('hra'),btn=document.getElementById('hraOtevrit');if(!dlg||!btn)return;
const Q=s=>dlg.querySelector(s),obsah=Q('.h-obsah');
const cti=k=>{try{return localStorage.getItem(k)}catch(e){return null}},uloz=(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}};
const klidne=matchMedia('(prefers-reduced-motion: reduce)').matches;
const naMobilu=()=>matchMedia('(pointer: coarse)').matches||innerWidth<720;
const k=n=>1+Math.floor(Math.random()*n);
// d20 zepředu: šestiúhelník, prostřední stěna s hodem a devět sousedních stěn (na pravé d20 kolem 20 leží 2, 8 a 14)
const d20=c=>'<svg class="h-d20" viewBox="0 0 100 100" aria-hidden="true"><g stroke="var(--dh)" stroke-width="1.6" stroke-linejoin="round">'
  +'<path fill="var(--d1)" d="M50 2 8 26 50 22z"/><path fill="var(--d2)" d="M50 2 92 26 50 22z"/>'
  +'<path fill="var(--d2)" d="M8 26 50 22 22 70z"/><path fill="var(--d3)" d="M92 26 50 22 78 70z"/>'
  +'<path fill="var(--d3)" d="M8 26 8 74 22 70z"/><path fill="var(--d4)" d="M92 26 92 74 78 70z"/>'
  +'<path fill="var(--d4)" d="M8 74 22 70 50 98z"/><path fill="var(--d5)" d="M92 74 78 70 50 98z"/>'
  +'<path fill="var(--d4)" d="M22 70 78 70 50 98z"/><path fill="var(--d0)" d="M50 22 78 70 22 70z"/></g>'
  +'<g class="h-male" text-anchor="middle"><text x="27" y="44">8</text><text x="73" y="44">14</text><text x="50" y="86">2</text></g>'
  +'<text class="h-cislo" x="50" y="60" text-anchor="middle">'+c+'</text></svg>';
const zn=n=>(n>=0?'+':'−')+Math.abs(n);
const h=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e};
let verze=cti('hledac-hra-verze'),S=null;
const vibruj=v=>{if(verze==='mob'&&navigator.vibrate)try{navigator.vibrate(v)}catch(e){}};

const POVOLANI=[
  {ikona:'⚔️',nazev:'Bojovník z Doudlevců',popis:'Hodně vydrží, problémy řeší ramenem.',hp:14,sila:3,rec:0,mag:-1},
  {ikona:'🧙',nazev:'Hypoteční mág',popis:'Kouzlí s úroky. Moc toho nevydrží.',hp:9,sila:-1,rec:1,mag:3},
  {ikona:'🗝️',nazev:'Šibal z Lochotína',popis:'Ukecá i katastrální úřad.',hp:11,sila:1,rec:3,mag:0}];
const AKCE=[{k:'sila',ikona:'⚔️',nazev:'Zaútočit'},{k:'rec',ikona:'💬',nazev:'Ukecat'},{k:'mag',ikona:'✨',nazev:'Kouzlo'}];
const SETKANI=[
  {ikona:'🕴️',nazev:'Makléř v naleštěných polobotkách',text:'U branky stojí makléř. „Dům je skvělý, jen provize 5 % a prohlídka jen dnes v 6:00 ráno.“',
   dc:{sila:12,rec:10,mag:13},odmena:200,ko:'Makléř ti prodá „asistenční balíček“ za 30 000. Bolí to.',
   ok:{sila:'Vyklopíš ho do živého plotu. Polobotky už nejsou naleštěné.',rec:'Usmlouváš provizi na jedno pivo a vizitku.',mag:'Kouzlem Exclusivitas Nulla zrušíš exkluzivní smlouvu.'}},
  {ikona:'🍄',nazev:'Plísňový slizoun ze sklepa',text:'Sklep voní čerstvou výmalbou. Až moc čerstvou. Za skříní se něco hýbe.',
   dc:{sila:13,rec:16,mag:10},odmena:150,ko:'Slizoun tě obejme. Kašleš a rozpočet na sanaci roste.',
   ok:{sila:'Rozmázneš ho lopatou. Výmalba už to nezachrání.',rec:'Kupodivu se s tebou baví. Odstěhuje se k sousedům.',mag:'Vysoušecí kouzlo! Sklep je suchý jak Plzeň v srpnu.'}},
  {ikona:'🚧',nazev:'Kolona na Rokycanské',text:'Na prohlídku to máš 20 minut. Navigace ukazuje dvě hodiny. Uzavírka.',
   dc:{sila:14,rec:12,mag:11},odmena:100,ko:'Přijedeš pozdě. Dům mezitím ukázali dalším dvanácti zájemcům.',
   ok:{sila:'Odtlačíš tramvaj. Řidič ti zamává.',rec:'Přesvědčíš policistu, že jedeš k porodu. Domu.',mag:'Teleport! Jen přistaneš trochu v Boleveckém rybníce.'}},
  {ikona:'🏦',nazev:'Úředník Hypotékus',text:'„Bonita? Příjem? Výpis z účtu za posledních 47 let?“ Úředník zvedá razítko.',
   dc:{sila:16,rec:11,mag:12},odmena:300,ko:'Žádost zamítnuta. Musíš donést potvrzení o potvrzení.',
   ok:{sila:'Vyrveš mu razítko. Překvapivě to funguje.',rec:'Ukecáš fixaci na 10 let s úrokem 0,9 %. Legenda.',mag:'Kouzlo Bonitas Maxima. Úvěr schválen!'}},
  {ikona:'🐕',nazev:'Sousedův pes Brok',text:'Přes plot se tyčí sousedův pes. Má větší pozemek než ty.',
   dc:{sila:13,rec:11,mag:12},odmena:100,ko:'Brok ti ukousne nohavici i kus sebevědomí.',
   ok:{sila:'Přetáhneš se s ním o klacek a vyhraješ. Je to tvůj nový kamarád.',rec:'„Hodnej pejsek.“ Sousedka ti k tomu nabídne buchty.',mag:'Vyčaruješ párek. Brok je okouzlen.'}}];
const DRAK={ikona:'🐉',nazev:'Drak Katastr',drak:true,
  text:'V jeskyni pod radnicí sedí Drak Katastr na hromadě listů vlastnictví. Tvůj dům má zástavní právo, věcné břemeno a předkupní právo prastrýce. Musíš ho zasáhnout dvakrát.',
  dc:{sila:14,rec:14,mag:14},odmena:500,ko:'Drak na tebe dýchne lhůtou 30 dní na vklad.',
  ok:{sila:'Zasáhneš draka přímo do razítka!',rec:'Přesvědčíš draka, že věcné břemeno je jen nedorozumění.',mag:'Ohnivá koule spálí jedno zástavní právo!'}};

// --- průvodce (při prvním spuštění sám, pak tlačítkem ?) ---
const PRUVODCE={
  verze:()=>[{sel:'.h-volby',t:'Vítej v Plzeňské kobce! Nejdřív vyber verzi. Tu pro tvoje zařízení jsem označil jako doporučenou, druhou si můžeš zvolit taky.'}],
  povolani:()=>[{sel:'.h-volby',t:'Vyber si povolání. Čísla u ⚔️ 💬 ✨ jsou bonusy, které se přičítají k hodu kostkou. ❤️ jsou životy.'}],
  scena:()=>[
    {sel:'.h-postava',t:'Tohle jsi ty. ❤️ Když životy klesnou na nulu, dobrodružství končí. 💰 Zlaťáky dostáváš za úspěchy.'},
    {sel:'.h-pivo',t:'Pivo Plzeň 12° doplní pár životů. Máš dvě, schovej si je na draka.'},
    {sel:'.h-scena',t:'Tady se odehrává příběh. Čekají tě tři setkání a nakonec Drak Katastr.'},
    {sel:'.h-akce',t:'Vyber, jak problém vyřešíš. „Potřebuješ 12“ je obtížnost, bonus máš podle povolání.'},
    {sel:'.h-kostka',t:(verze==='pc'?'Pak hoď kostkou d20: klikni na ni, nebo zmáčkni mezerník.':'Pak ťukni na kostku d20.')+
      ' Hod + bonus ≥ obtížnost = úspěch. Dvacítka je kritický zásah, jednička trapas.'},
    ...(verze==='pc'?[{sel:'.h-akce',t:'Tip pro PC: klávesy 1–3 vyberou akci, mezerník hází a pokračuje, P otevře pivo.'}]:
      [{sel:'.h-ovladani',t:'Všechno ovládáš palcem tady dole. Telefon při hodu zavibruje. Hodně štěstí!'}])]};
let pruvodce=null;
function spustPruvodce(obr,vynutit){const hotovo=JSON.parse(cti('hledac-hra-pruvodce')||'{}');
  if(!vynutit&&hotovo[obr])return;const kroky=PRUVODCE[obr]().filter(x=>Q(x.sel));if(!kroky.length)return;
  pruvodce={obr,kroky,i:0};Q('.h-pruvodce').hidden=false;ukazKrok()}
function konecPruvodce(){if(!pruvodce)return;const hotovo=JSON.parse(cti('hledac-hra-pruvodce')||'{}');hotovo[pruvodce.obr]=1;
  uloz('hledac-hra-pruvodce',JSON.stringify(hotovo));pruvodce=null;Q('.h-pruvodce').hidden=true}
// zvýraznění se měří až po posunu obsahu (jinak sedí vedle) a přepočítá se při každém dalším posunu
function ukazKrok(){const p=pruvodce;if(!p)return;const x=p.kroky[p.i],cil=Q(x.sel);
  cil.scrollIntoView({block:'nearest'});umisti();setTimeout(umisti,klidne?0:120)}
function umisti(){if(!pruvodce)return;const p=pruvodce,x=p.kroky[p.i],cil=Q(x.sel);if(!cil)return;
  {const r=cil.getBoundingClientRect(),o=6,sv=Q('.h-svetlo'),b=Q('.h-bublina');
    Object.assign(sv.style,{left:r.left-o+'px',top:r.top-o+'px',width:r.width+2*o+'px',height:r.height+2*o+'px'});
    b.querySelector('p').textContent=x.t;Q('.h-krok').textContent=(p.i+1)+' / '+p.kroky.length;
    Q('.h-dalsi').textContent=p.i===p.kroky.length-1?'Rozumím':'Další';
    const bw=b.offsetWidth,bh=b.offsetHeight,W=innerWidth,H=innerHeight;
    let top=r.bottom+14;if(top+bh>H-12)top=Math.max(12,r.top-bh-14);if(top+bh>H-12)top=Math.max(12,H-bh-12);
    b.style.top=top+'px';b.style.left=Math.min(Math.max(12,r.left+r.width/2-bw/2),W-bw-12)+'px';Q('.h-dalsi').focus({preventScroll:true})}}
obsah.addEventListener('scroll',()=>{if(pruvodce)umisti()},{passive:true});
Q('.h-dalsi').onclick=()=>{if(!pruvodce)return;pruvodce.i++;pruvodce.i>=pruvodce.kroky.length?konecPruvodce():ukazKrok()};
Q('.h-preskocit').onclick=konecPruvodce;
addEventListener('resize',()=>{if(pruvodce)umisti()});

// --- obrazovky ---
let obrazovka='';
function nastavVerzi(v,ulozit=true){verze=v;if(ulozit)uloz('hledac-hra-verze',v);dlg.classList.toggle('pc',v==='pc');dlg.classList.toggle('mob',v==='mob')}
function obrVerze(){obrazovka='verze';const doporuc=naMobilu()?'mob':'pc';
  obsah.replaceChildren(h('h2','','Na čem hraješ?'),h('p','h-pod','Hra je krátká – akorát na dlouhou chvíli. Vyber verzi, která ti sedne.'));
  const box=h('div','h-volby');
  [['pc','💻','Verze pro PC','Větší okno, ovládání myší i klávesami 1–3, mezerník a P.'],
   ['mob','📱','Verze pro mobil','Celá obrazovka, velká tlačítka na dosah palce, kostka zavibruje.']].forEach(([v,ik,n,p])=>{
    const b=h('button','h-volba'+(v===doporuc?' dop':''));b.type='button';
    if(v===doporuc)b.append(h('span','h-stitek',v==='pc'?'Doporučeno – jsi na PC':'Doporučeno – jsi na mobilu'));
    b.append(h('span','h-velka',ik),h('b','',n),h('small','',p));b.onclick=()=>{nastavVerzi(v);obrPovolani()};box.append(b)});
  obsah.append(box);setTimeout(()=>spustPruvodce('verze'),300)}
function obrPovolani(){obrazovka='povolani';
  const nej=+cti('hledac-hra-rekord')||0;
  obsah.replaceChildren(h('h2','','Vyber si hrdinu'),h('p','h-pod','Cíl: dostat se přes nástrahy realitního trhu k domu snů.'+(nej?' Tvůj rekord: '+nej+' 💰.':'')));
  const box=h('div','h-volby');
  POVOLANI.forEach(p=>{const b=h('button','h-volba');b.type='button';const st=h('div','h-staty');
    st.innerHTML='<span>❤️ <b>'+p.hp+'</b></span><span>⚔️ <b>'+zn(p.sila)+'</b></span><span>💬 <b>'+zn(p.rec)+'</b></span><span>✨ <b>'+zn(p.mag)+'</b></span>';
    b.append(h('span','h-velka',p.ikona),h('b','',p.nazev),h('small','',p.popis),st);b.onclick=()=>novaHra(p);box.append(b)});
  obsah.append(box);setTimeout(()=>spustPruvodce('povolani'),300)}
function novaHra(p){const balik=[...SETKANI].sort(()=>Math.random()-.5).slice(0,3);
  S={p,hp:p.hp,max:p.hp,zlato:0,pivo:2,cesta:[...balik,DRAK],i:0,drak:2,postup:false,hod:null,faze:'vyber',akce:null,vysledek:null};obrScena();
  setTimeout(()=>spustPruvodce('scena'),350)}

function obrScena(){obrazovka='scena';const s=S.cesta[S.i],pc=verze==='pc';
  const hra=h('div','h-hra'),sc=h('section','h-scena');
  sc.append(h('div','h-ikona',s.ikona),h('div','h-kolo',s.drak?(S.drak<=0?'Závěrečný boj · drak padá!':'Závěrečný boj · drak ještě vydrží '+S.drak+(S.drak===1?' zásah':' zásahy')):'Setkání '+(S.i+1)+' ze '+(S.cesta.length-1)),
    h('h3','',s.nazev),h('p','h-text',s.text));
  if(S.vysledek){const v=h('div','h-vysledek '+(S.vysledek.ok?'ok':'ko'),S.vysledek.text);v.append(h('small','',S.vysledek.detail));sc.append(v)}
  const panel=h('aside','h-panel'),post=h('div','h-postava');
  const jm=h('div','h-jmeno');jm.append(h('span','',S.p.ikona),h('span','',S.p.nazev));
  const hp=h('div','h-hp');const pr=h('i');pr.style.width=Math.max(0,S.hp/S.max*100)+'%';hp.append(pr);
  const r=h('div','h-radek');r.innerHTML='<span>❤️ <b>'+Math.max(0,S.hp)+'</b> / '+S.max+'</span><span>💰 <b>'+S.zlato+'</b></span>';
  const pivo=h('button','h-pivo','🍺 Pivo ×'+S.pivo);pivo.type='button';pivo.disabled=!S.pivo||S.hp>=S.max||S.faze!=='vyber';
  pivo.title='Plzeň 12°: doplní 1k6+2 životů (P)';pivo.onclick=napijSe;r.append(pivo);
  post.append(jm,hp,r);
  const ovl=h('div','h-ovladani'),ak=h('div','h-akce');
  AKCE.forEach((a,n)=>{const b=h('button',S.akce===a.k?'on':'');b.type='button';b.disabled=S.faze==='vysledek';
    const bonus=S.p[a.k],t=h('span');t.append(h('b','',a.nazev),h('small','','potřebuješ '+s.dc[a.k]+' · bonus '+zn(bonus)));
    b.append(h('i','ik',a.ikona),t);if(pc)b.append(h('kbd','',n+1));b.onclick=()=>vyberAkci(a.k);ak.append(b)});
  const hod=h('div','h-hod'),kost=h('button','h-kostka'+(S.faze==='hod'?' ceka':''));kost.type='button';kost.disabled=S.faze!=='hod';
  kost.setAttribute('aria-label','Hodit kostkou d20');
  kost.innerHTML=d20(S.hod||20);
  kost.onclick=hodKostkou;
  const nap=h('div','h-napoveda',S.faze==='vyber'?(pc?'Vyber akci (1–3).':'Vyber akci.'):S.faze==='hod'?(pc?'Hoď kostkou – klikni nebo mezerník.':'Ťukni na kostku!'):'');
  const dal=h('button','h-dal',S.hp<=0?'Co se stalo? ›':(S.postup&&s.drak?'Pro odměnu ›':'Dál ›'));dal.type='button';dal.hidden=S.faze!=='vysledek';dal.onclick=dalsi;
  hod.append(kost,nap);ovl.append(ak,hod,dal);panel.append(post,ovl);hra.append(sc,panel);obsah.replaceChildren(hra);
  if(verze==='mob'&&S.faze==='vysledek')dal.scrollIntoView({block:'end'})}

function vyberAkci(a){if(!S||S.faze==='vysledek'||S.faze==='toci')return;S.akce=a;S.faze='hod';S.vysledek=null;obrScena();
  if(verze==='mob')Q('.h-kostka').scrollIntoView({block:'nearest',behavior:'smooth'})}
function napijSe(){if(!S||!S.pivo||S.hp>=S.max||S.faze!=='vyber')return;S.pivo--;const plus=k(6)+2;S.hp=Math.min(S.max,S.hp+plus);
  S.vysledek={ok:true,text:'🍺 Glo glo glo. +'+plus+' životů.',detail:'Plzeň 12° – léčivý lektvar západních Čech.'};vibruj(20);obrScena()}
function hodKostkou(){if(S.faze!=='hod')return;const s=S.cesta[S.i],a=S.akce,hod=k(20),bonus=S.p[a],dc=s.dc[a],celkem=hod+bonus;
  S.faze='toci';const kost=Q('.h-kostka');kost.classList.remove('ceka');kost.classList.add('toci');kost.disabled=true;
  // velká d20 se přikutálí přes scénu, odrazí se a dopadne na výsledek (ťuknutí ji schová)
  let velka=null;if(!klidne){velka=h('div','h-hod-velky');velka.innerHTML=d20('?')+'<b></b>';velka.onclick=()=>velka.remove();Q('.h-okno').append(velka)}
  const cisla=[kost,velka].filter(Boolean).map(x=>x.querySelector('.h-cislo'));
  vibruj(30);const tik=setInterval(()=>cisla.forEach(t=>t.textContent=k(20)),70);
  const hra=S;setTimeout(()=>{clearInterval(tik);if(S!==hra||S.faze!=='toci'||obrazovka!=='scena'){if(velka)velka.remove();return}S.hod=hod;const krit=hod===20,trapas=hod===1,ok=krit||(!trapas&&celkem>=dc);
    const detail='Hod '+hod+' '+zn(bonus)+' = '+celkem+' proti '+dc+(krit?' · KRITICKÝ ZÁSAH!':trapas?' · kritický trapas':'');
    if(ok){const zisk=s.odmena*(krit?2:1);S.zlato+=zisk;if(s.drak)S.drak-=krit?2:1;
      S.vysledek={ok:true,text:(krit?'🌟 ':'✅ ')+s.ok[a]+' +'+zisk+' 💰',detail};vibruj(krit?[60,40,60,40,120]:40)}
    else{const dmg=(s.drak?k(6):k(4))+1+(trapas?2:0);S.hp-=dmg;
      S.vysledek={ok:false,text:(trapas?'🤦 ':'💥 ')+s.ko+' −'+dmg+' ❤️',detail};vibruj([80,50,80])}
    S.postup=ok&&(!s.drak||S.drak<=0);S.faze='vysledek';S.akce=null;obrScena();
    const nk=Q('.h-kostka');if(krit)nk.classList.add('krit');if(trapas)nk.classList.add('trapas');
    if(velka){velka.querySelector('.h-cislo').textContent=hod;velka.classList.add('dopad',...(krit?['krit']:trapas?['trapas']:[]));
      velka.querySelector('b').textContent=krit?'Kritický zásah!':trapas?'Trapas!':hod+' '+zn(bonus)+' = '+celkem+(ok?' ✓':' ✗');
      setTimeout(()=>{velka.classList.add('pryc');setTimeout(()=>velka.remove(),350)},krit||trapas?1100:750)}},klidne?0:1100)}
function dalsi(){if(!S||S.faze!=='vysledek')return;if(S.hp<=0)return obrKonec(false);if(S.postup){S.i++;S.postup=false}
  if(S.i>=S.cesta.length)return obrKonec(true);S.faze='vyber';S.vysledek=null;S.hod=null;obrScena()}

function nahodnyDum(){if(typeof DATA==='undefined')return null;
  const vse=Object.values(DATA).flat().filter(d=>d&&d.nazev&&(d.fotky||[]).length);return vse.length?vse[Math.floor(Math.random()*vse.length)]:null}
function obrKonec(vyhra){obrazovka='konec';const skore=S.zlato+(vyhra?Math.max(0,S.hp)*50:0),nej=+cti('hledac-hra-rekord')||0;
  if(skore>nej)uloz('hledac-hra-rekord',skore);
  const box=h('div','h-konec');box.append(h('div','h-ikona',vyhra?'🏡':'🪦'),h('h2','',vyhra?'Drak je poražen, dům je tvůj!':'Padl jsi.'),
    h('p','h-pod',vyhra?'Katastr zapsal vklad za rekordních 5 minut. Skóre '+skore+' 💰'+(skore>nej?' – nový rekord!':' (rekord '+nej+').')
      :'Makléř si účtuje provizi i za pohřeb. Skóre '+skore+' 💰. Zkus jiné povolání, nebo víc piva.'));
  const akce=h('div','h-konec-akce');
  if(vyhra){const d=nahodnyDum();if(d){const k2=h('div','h-dum'),img=h('img');img.src=d.fotky[0];img.alt='';img.referrerPolicy='no-referrer';
      img.onerror=()=>img.remove();const t=h('div');t.append(h('small','','Tvá odměna z dnešní nabídky:'),h('b','',d.nazev),
      h('small','',[d.cena?Math.round(d.cena).toLocaleString('cs-CZ')+' Kč':'',d.obec].filter(Boolean).join(' · ')));k2.append(img,t);box.append(k2);
      if(typeof otevri==='function'){const b=h('button','h-hlavni','Ukázat ten dům');b.type='button';b.onclick=()=>{dlg.close();otevri(d,0)};akce.append(b)}}}
  const znovu=h('button',vyhra?'h-druhe':'h-hlavni','Hrát znovu');znovu.type='button';znovu.onclick=obrPovolani;
  const zpet=h('button','h-druhe','Zpět k hledání');zpet.type='button';zpet.onclick=()=>dlg.close();akce.append(znovu,zpet);
  box.append(akce);obsah.replaceChildren(box);vibruj(vyhra?[50,30,50,30,200]:300)}

// --- ovládání ---
// první otevření na tomhle zařízení: nabídnout verzi (doporučená podle zařízení); pak rovnou hra, rozehraná zůstává
function otevrit(){const ulozena=cti('hledac-hra-verze');nastavVerzi(ulozena||(naMobilu()?'mob':'pc'),!!ulozena);dlg.showModal();
  if(!ulozena)obrVerze();else if(!obrazovka||obrazovka==='verze')obrPovolani()}
btn.onclick=otevrit;
dlg.addEventListener('click',e=>{const t=e.target.closest('[data-h]');if(e.target===dlg){dlg.close();return}if(!t)return;
  if(t.dataset.h==='zavrit')dlg.close();
  if(t.dataset.h==='verze'){konecPruvodce();nastavVerzi(verze==='pc'?'mob':'pc');if(obrazovka==='scena')obrScena();if(obrazovka==='verze')obrPovolani()}
  if(t.dataset.h==='pruvodce'){if(obrazovka==='konec')return;spustPruvodce(obrazovka,true)}});
dlg.addEventListener('close',konecPruvodce);
dlg.addEventListener('keydown',e=>{if(pruvodce){if(e.key==='Escape'){e.preventDefault();konecPruvodce()}return}
  if(obrazovka!=='scena'||verze!=='pc'||e.target.closest('.h-hlava'))return;
  if(['1','2','3'].includes(e.key)){e.preventDefault();vyberAkci(AKCE[+e.key-1].k)}
  else if(e.key===' '||e.key==='Enter'){e.preventDefault();if(S.faze==='hod')hodKostkou();else if(S.faze==='vysledek')dalsi()}
  else if(e.key==='p'||e.key==='P'){napijSe()}});
})();
"""
