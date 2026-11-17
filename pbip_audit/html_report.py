"""Grafický report auditu jako jeden samostatný HTML soubor (bez internetu, bez knihoven): metriky stavu, skóre AI,
nálezy podle závažnosti a oblasti s doporučením, návrhy úprav DAX (před / po) a „Jak pokračovat“ odvozené z nálezů.

Volá se z audit.py (`--html`). Slovní shrnutí pro vedení / klienta je jediná část, kterou Python neumí napsat
smysluplně – na ni je v reportu místo: `--shrnuti shrnuti.md` (text od AI nebo vlastní), jinak se ukáže hotový prompt.
"""
from __future__ import annotations

import html
import re
from collections import Counter
from datetime import date

UROVNE = [("chyba", "Chyby", "critical", "✕"), ("varovani", "Varování", "warning", "!"), ("info", "Info", "info", "i")]
OBLASTI = [("model", "Model"), ("dax", "Kvalita DAX"), ("rls", "Zabezpečení (RLS / OLS)"), ("ai", "Připravenost pro AI"),
           ("report", "Report")]
SKORE_POPIS = {"popisy měr": "Míry s popisem", "popisy viditelných sloupců": "Viditelné sloupce s popisem",
               "popisy tabulek": "Tabulky s popisem", "skryté technické sloupce": "Skryté technické sloupce",
               "srozumitelné názvy": "Srozumitelné názvy", "míry ve složkách": "Míry ve složkách",
               "označený kalendář": "Označený kalendář"}
SKORE_KROK = {  # složka skóre -> co udělat
    "popisy měr": "Doplň popisy měr – `oprav.py --sablona`, popisy navrhni s AI nad `model_<název>.md` (ai_dokumentace.py).",
    "popisy viditelných sloupců": "Popiš viditelné sloupce, nebo je skryj (M02, M05).",
    "popisy tabulek": "Popiš tabulky: zrnitost (1 řádek = …) a zdroj (M03).",
    "skryté technické sloupce": "Skryj klíče, kódy a řadicí sloupce (M06) – `oprav.py --sablona` je předvyplní.",
    "srozumitelné názvy": "Přejmenuj technické a generické názvy (M09, M13) v Desktopu nebo Tabular Editoru.",
    "míry ve složkách": "Rozděl míry do složek (M14) – sloupec „slozka“ v šabloně oprav.py.",
    "označený kalendář": "Označ tabulku kalendáře (M12).",
}


def tvar(n: int, jedna: str, dve: str, pet: str) -> str:
    """Český tvar podle čísla: 1 tabulka, 2 tabulky, 5 tabulek."""
    return f"{n} " + (jedna if n == 1 else dve if 2 <= n <= 4 else pet)


def e(x) -> str:
    return html.escape(str(x), quote=True)


def _md(text: str) -> str:
    """Minimální Markdown pro shrnutí: odstavce, odrážky, **tučně**, `kód`."""
    out = []
    odrazka = re.compile(r"^\s*[-*]\s+")
    for blok in re.split(r"\n\s*\n", text.strip()):
        radky = [r for r in blok.splitlines() if r.strip()]
        if all(odrazka.match(r) for r in radky):
            out.append("<ul>" + "".join("<li>" + _inline(odrazka.sub("", r)) + "</li>" for r in radky) + "</ul>")
        elif radky and radky[0].startswith("#"):
            out.append(f"<h3>{_inline(radky[0].lstrip('#').strip())}</h3>" + (f"<p>{_inline(' '.join(radky[1:]))}</p>" if radky[1:] else ""))
        else:
            out.append(f"<p>{_inline(' '.join(radky))}</p>")
    return "\n".join(out)


def _inline(t: str) -> str:
    t = e(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)


def kroky(p, nalezy, sk, problemy, navrhy) -> list[tuple[str, str]]:
    """Doporučené pořadí práce odvozené pravidly z nálezů: [(nadpis, detail)]."""
    pocty = Counter(n.kod for n in nalezy)
    chyby = Counter(n.kod for n in nalezy if n.uroven == "chyba")
    out = []
    if problemy:
        out.append(("Ověř, že se model načetl správně", "Parser hlásí problém: " + "; ".join(problemy) +
                    " Výsledky kontrol modelu nejsou spolehlivé, dokud se to nevyřeší."))
    if chyby:
        out.append((f"Oprav chyby ({sum(chyby.values())})", "Rozbité věci, které se projeví uživatelům: " +
                    ", ".join(f"{k} {NAZEV.get(k, '')} ({c}×)" for k, c in chyby.most_common()) + "."))
    model_var = Counter(n.kod for n in nalezy if n.uroven == "varovani" and n.oblast == "model")
    if model_var:
        out.append((f"Oprav varování v modelu ({sum(model_var.values())})", ", ".join(
            f"{k} {NAZEV.get(k, '')} ({c}×)" for k, c in model_var.most_common()) + " – zhoršují správnost čísel nebo výkon."))
    if pocty.get("S02"):
        out.append(("Uzavři díry v RLS", f"{pocty['S02']}× se filtr role nedostane k tabulce s daty – uživatelé role ji vidí celou. "
                    "Filtruj dimenzi s aktivním vztahem 1:N k faktu, nebo tabulku skryj přes OLS."))
    presne = [x for x in navrhy if x["presny"]]
    overit = [x for x in navrhy if x["vse"]]
    if presne:
        out.append((f"Zjednoduš DAX bez změny výsledku ({len(presne)} měr)",
                    "Přesné přepisy (DIVIDE, SUM místo SUMX, SWITCH, VAR …) – `oprav.py --sablona` je předvyplní, "
                    "po náhledu zapiš `--zapsat`."))
    if overit:
        out.append((f"Prověř DAX, který se počítá jinak, než vypadá ({len(overit)} měr)",
                    "Návrhy k ověření (filtry přes celou tabulku, časové funkce nad datem z faktu …) mění výsledek – "
                    "porovnej čísla v Desktopu, než je převezmeš."))
    slabe = sorted(((v, k) for k, v in sk.items() if k != "skore" and v < 80), key=lambda x: x[0])
    for v, k in slabe[:4]:
        out.append((f"Zvedni skóre AI: {SKORE_POPIS.get(k, k).lower()} ({v} %)", SKORE_KROK.get(k, "")))
    rep = [k for k in ("R11", "R14", "R05", "R04", "R01", "R10") if pocty.get(k)]
    if rep:
        out.append(("Dotáhni report", "; ".join(f"{k} {NAZEV.get(k, '')} ({pocty[k]}×)" for k in rep) + "."))
    out.append(("Spusť audit znovu a porovnej", "`audit.py … --baseline audit_<název>.csv` ukáže nové a vyřešené nálezy, "
                "`porovnej.py` před/po po složkách skóre."))
    return out


NAZEV: dict = {}


CSS = """
.viz-root{color-scheme:light;--surface-0:#f4f3f0;--surface-1:#fcfcfb;--border:#e2e1dc;--grid:#ebeae6;
--text-primary:#0b0b0b;--text-secondary:#52514e;--text-muted:#77766f;--accent:#2a78d6;--accent-soft:#cde2fb;
--critical:#d03b3b;--warning:#fab219;--info:#86b6ef;--good:#0ca30c;--code:#f0efec}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;--surface-0:#121211;
--surface-1:#1a1a19;--border:#33332f;--grid:#2a2a27;--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#99988f;
--accent:#3987e5;--accent-soft:#184f95;--info:#5598e7;--code:#232321}}
*{box-sizing:border-box}body{margin:0}
.viz-root{background:var(--surface-0);color:var(--text-primary);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
min-height:100vh;padding:32px 20px 60px}
.wrap{max-width:1120px;margin:0 auto}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 12px}h3{font-size:16px;margin:0 0 6px}
.muted{color:var(--text-muted)}.sec{color:var(--text-secondary)}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:18px 20px}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}.g2{grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
.kpi .lbl{font-size:13px;color:var(--text-secondary)}.kpi .val{font-size:34px;font-weight:650;line-height:1.15;font-variant-numeric:tabular-nums}
.kpi .sub{font-size:13px;color:var(--text-muted)}
.hero .val{font-size:48px}.meter{height:10px;background:var(--grid);border-radius:5px;overflow:hidden;margin:10px 0 4px}
.meter>span{display:block;height:100%;background:var(--accent);border-radius:5px}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;
border:1px solid var(--border);color:var(--text-primary);white-space:nowrap}
.dot{width:16px;height:16px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:11px;
font-weight:800;color:#fff;flex:none}
.d-critical{background:var(--critical)}.d-warning{background:var(--warning);color:#1a1a19}.d-info{background:var(--info);color:#0b0b0b}
.bars{display:flex;flex-direction:column;gap:12px}.barrow{display:grid;grid-template-columns:190px 1fr 92px;gap:12px;align-items:center}
.barrow .name{font-size:14px;color:var(--text-secondary)}.track{display:flex;gap:2px;height:16px}
.seg{height:100%;border-radius:0}.seg:first-child{border-radius:4px 0 0 4px}.seg:last-child{border-radius:0 4px 4px 0}
.seg:only-child{border-radius:4px}.seg.critical{background:var(--critical)}.seg.warning{background:var(--warning)}.seg.info{background:var(--info)}
.num{font-variant-numeric:tabular-nums;text-align:right;font-size:14px}
.sbar{height:12px;background:var(--grid);border-radius:4px;overflow:hidden}.sbar>span{display:block;height:100%;background:var(--accent);border-radius:0 4px 4px 0}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--text-secondary);margin-top:14px}
.legend span{display:inline-flex;gap:6px;align-items:center}.sw{width:12px;height:12px;border-radius:3px;display:inline-block}
ol.steps{margin:0;padding:0;list-style:none;counter-reset:s}ol.steps li{counter-increment:s;position:relative;padding:12px 0 12px 46px;
border-top:1px solid var(--grid)}ol.steps li:first-child{border-top:0}
ol.steps li::before{content:counter(s);position:absolute;left:0;top:12px;width:30px;height:30px;border-radius:50%;
background:var(--accent-soft);color:var(--text-primary);font-weight:700;display:flex;align-items:center;justify-content:center}
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 14px}
.chip{border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary);border-radius:999px;padding:5px 12px;
font:inherit;font-size:13px;cursor:pointer}.chip[aria-pressed="true"]{background:var(--text-primary);color:var(--surface-1);border-color:var(--text-primary)}
input[type=search]{border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary);border-radius:8px;padding:6px 10px;
font:inherit;font-size:14px;min-width:220px;margin-left:auto}
details.grp{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;margin:0 0 8px}
details.grp>summary{list-style:none;cursor:pointer;padding:12px 16px;display:flex;gap:10px;align-items:center}
details.grp>summary::-webkit-details-marker{display:none}
details.grp>summary .t{font-weight:600}details.grp>summary .c{margin-left:auto;color:var(--text-muted);font-size:13px;white-space:nowrap}
details.grp .body{padding:0 16px 14px 42px}.rec{background:var(--code);border-radius:8px;padding:10px 12px;margin:0 0 10px;font-size:14px}
ul.items{margin:0;padding-left:18px;font-size:14px}ul.items li{margin:3px 0}code,pre{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:12.5px}
code{background:var(--code);padding:1px 5px;border-radius:4px}
pre{background:var(--code);border-radius:8px;padding:10px 12px;overflow:auto;margin:6px 0 10px;white-space:pre-wrap}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:760px){.pair{grid-template-columns:1fr}.barrow{grid-template-columns:120px 1fr 50px}}
.tag{font-size:12px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em}
.ai-box{border:1px dashed var(--border);border-radius:10px;padding:14px 16px}
table.t{border-collapse:collapse;width:100%;font-size:14px}table.t td,table.t th{padding:6px 8px;border-bottom:1px solid var(--grid);text-align:left}
table.t td.num,table.t th.num{text-align:right}
.hidden{display:none!important}footer{margin-top:40px;font-size:13px;color:var(--text-muted)}
"""

JS = """
(function(){const st={u:new Set(),o:new Set(),q:''};
function apply(){document.querySelectorAll('[data-u]').forEach(el=>{const ok=(!st.u.size||st.u.has(el.dataset.u))&&
(!st.o.size||st.o.has(el.dataset.o))&&(!st.q||el.textContent.toLowerCase().includes(st.q));el.classList.toggle('hidden',!ok)});
document.querySelectorAll('section[data-sev]').forEach(s=>{s.classList.toggle('hidden',!s.querySelector('[data-u]:not(.hidden)'))})}
document.querySelectorAll('.chip').forEach(b=>b.addEventListener('click',()=>{const k=b.dataset.k,v=b.dataset.v,set=st[k];
if(set.has(v)){set.delete(v);b.setAttribute('aria-pressed','false')}else{set.add(v);b.setAttribute('aria-pressed','true')}apply()}));
const q=document.getElementById('q');if(q)q.addEventListener('input',()=>{st.q=q.value.trim().toLowerCase();apply()});
document.querySelectorAll('[data-open]').forEach(a=>a.addEventListener('click',()=>{const d=document.getElementById(a.dataset.open);if(d)d.open=true}));})();
"""


def html_report(p, nalezy, sk, problemy, potlacene, navrhy, zmeny=None, shrnuti: str = "") -> str:
    from kontroly import NADPISY
    NAZEV.clear(); NAZEV.update(NADPISY)
    pocty = Counter(n.uroven for n in nalezy)
    podle_oblasti = {o: Counter(n.uroven for n in nalezy if n.oblast == o) for o, _ in OBLASTI}
    h = [f"<!DOCTYPE html><html lang='cs'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Audit {e(p.nazev)}</title><style>{CSS}</style></head><body><div class='viz-root'><div class='wrap'>"]
    h.append(f"<header><div class='tag'>Audit Power BI projektu</div><h1>{e(p.nazev)}</h1>"
             f"<div class='sec'>{date.today():%d. %m. %Y} · report {e(p.format_reportu)} · model {e(p.format_modelu)}</div></header>")
    if problemy:
        h.append("<div class='card' style='border-color:var(--critical);margin-top:18px'><h3>⚠️ Model se nenačetl správně</h3>"
                 + "".join(f"<div class='sec'>{e(x)}</div>" for x in problemy) + "<div class='muted'>Výsledky kontrol modelu nejsou spolehlivé.</div></div>")

    # --- metriky
    skore = sk["skore"]
    hodnoceni = "dobrý základ" if skore >= 80 else "potřebuje doplnit" if skore >= 50 else "pro AI zatím nepřipravený"
    h.append("<h2>Stav v číslech</h2><div class='grid g4'>")
    h.append(f"<div class='card kpi hero'><div class='lbl'>Připravenost pro AI</div><div class='val'>{skore}<span class='muted' style='font-size:20px'> / 100</span></div>"
             f"<div class='meter' role='img' aria-label='Skóre {skore} ze 100'><span style='width:{skore}%'></span></div><div class='sub'>{hodnoceni}</div></div>")
    for u, nazev, cls, ikona in UROVNE:
        h.append(f"<div class='card kpi'><div class='lbl'><span class='dot d-{cls}' aria-hidden='true'>{ikona}</span> {nazev}</div>"
                 f"<div class='val'>{pocty[u]}</div><div class='sub'>"
                 + {"chyba": "rozbité – projeví se uživatelům", "varovani": "zhoršuje použitelnost nebo výkon", "info": "ke zvážení"}[u]
                 + "</div></div>")
    h.append("</div><div class='grid g4' style='margin-top:14px'>")
    for lbl, val, sub in (("Model", tvar(len(p.tabulky), "tabulka", "tabulky", "tabulek"),
                           " · ".join((tvar(len(p.sloupce), "sloupec", "sloupce", "sloupců"), tvar(len(p.miry), "míra", "míry", "měr"),
                                       tvar(len(p.vztahy), "vztah", "vztahy", "vztahů")))),
                          ("Report", tvar(len(p.stranky), "stránka", "stránky", "stránek"),
                           tvar(len(p.vizualy), "vizuál", "vizuály", "vizuálů") + " · " + tvar(len(p.zalozky), "záložka", "záložky", "záložek")),
                          ("Zabezpečení", tvar(len(p.role), "role", "role", "rolí"), "RLS / OLS" if p.role else "model nemá role"),
                          ("DAX", tvar(len(navrhy), "míra k úpravě", "míry k úpravě", "měr k úpravě"),
                           f"{sum(1 for x in navrhy if x['presny'])} přesně · {sum(1 for x in navrhy if x['vse'])} k ověření")):
        h.append(f"<div class='card kpi'><div class='lbl'>{lbl}</div><div class='val' style='font-size:24px'>{e(val)}</div><div class='sub'>{e(sub)}</div></div>")
    h.append("</div>")
    if potlacene or zmeny:
        h.append("<p class='muted'>" + (f"{potlacene} nálezů potlačeno výjimkou klienta. " if potlacene else "")
                 + (f"Proti baseline: {zmeny[0]} nových chyb a varování, {zmeny[1]} vyřešených nálezů." if zmeny else "") + "</p>")

    # --- oblasti × závažnost + složky skóre
    mx = max([sum(c.values()) for c in podle_oblasti.values()] + [1])
    h.append("<div class='grid g2' style='margin-top:14px'><div class='card'><h3>Nálezy podle oblasti</h3><div class='muted' style='font-size:13px;margin-bottom:12px'>"
             "počet nálezů, rozdělený podle závažnosti</div><div class='bars'>")
    for o, nazev in OBLASTI:
        c = podle_oblasti[o]
        celk = sum(c.values())
        segs = "".join(f"<span class='seg {cls}' style='width:{100 * c[u] / mx:.2f}%' title='{e(nazev)}: {c[u]} × {lbl.lower()}'></span>"
                       for u, lbl, cls, _ in UROVNE if c[u])
        h.append(f"<div class='barrow'><span class='name'>{e(nazev)}</span><div class='track'>{segs}</div><span class='num'>{celk}</span></div>")
    h.append("</div><div class='legend'>" + "".join(f"<span><i class='sw' style='background:var(--{cls})'></i>{lbl}</span>" for _, lbl, cls, _ in UROVNE)
             + "</div></div>")
    h.append("<div class='card'><h3>Skóre AI po složkách</h3><div class='muted' style='font-size:13px;margin-bottom:12px'>% splnění · váha ve skóre</div><div class='bars'>")
    from audit import VAHY_AI
    for k in VAHY_AI:
        h.append(f"<div class='barrow'><span class='name'>{e(SKORE_POPIS.get(k, k))}</span><div class='sbar' title='{sk[k]} %'><span style='width:{sk[k]}%'></span></div>"
                 f"<span class='num'>{sk[k]} % <span class='muted'>· {round(VAHY_AI[k] * 100)}</span></span></div>")
    h.append("</div></div></div>")

    # --- shrnutí (LLM / vlastní text)
    h.append("<h2>Shrnutí</h2>")
    if shrnuti.strip():
        h.append(f"<div class='card'>{_md(shrnuti)}</div>")
    else:
        h.append("<div class='ai-box'><div class='tag'>Doplní AI nebo auditor</div><p class='sec' style='margin:6px 0'>Slovní shrnutí pro klienta "
                 "(co čísla znamenají pro jeho reporting a priority) Python nenapíše smysluplně. Dej AI soubory "
                 f"<code>audit_{e(p.nazev)}.md</code> a <code>model_{e(p.nazev)}.md</code> s tímto zadáním a výsledek ulož jako "
                 f"<code>shrnuti.md</code>; pak spusť audit s <code>--html --shrnuti shrnuti.md</code>:</p>"
                 "<pre>Napiš shrnutí auditu Power BI modelu pro vedoucího týmu (5–8 vět + 3 odrážky priorit). Vycházej jen z přiložených "
                 "souborů, nevymýšlej čísla. Vysvětli dopad chyb a varování na uživatele reportu a na Copilot, doporuč pořadí kroků.</pre></div>")

    # --- jak pokračovat
    h.append("<h2>Jak pokračovat</h2><div class='card'><ol class='steps'>")
    for nadpis, detail in kroky(p, nalezy, sk, problemy, navrhy):
        h.append(f"<li><h3>{_inline(nadpis)}</h3><div class='sec'>{_inline(detail)}</div></li>")
    h.append("</ol></div>")

    # --- nálezy
    h.append(f"<h2 id='nalezy'>Nálezy ({len(nalezy)})</h2><div class='filters' role='group' aria-label='Filtr nálezů'>")
    for u, lbl, cls, ikona in UROVNE:
        h.append(f"<button class='chip' data-k='u' data-v='{u}' aria-pressed='false'><span class='dot d-{cls}' aria-hidden='true'>{ikona}</span> {lbl} {pocty[u]}</button>")
    for o, nazev in OBLASTI:
        if sum(podle_oblasti[o].values()):
            h.append(f"<button class='chip' data-k='o' data-v='{o}' aria-pressed='false'>{e(nazev)}</button>")
    h.append("<input type='search' id='q' placeholder='Hledat objekt nebo text…' aria-label='Hledat'></div>")
    dax_podle = {x["objekt"]: x for x in navrhy}
    for u, lbl, cls, ikona in UROVNE:
        nn = [n for n in nalezy if n.uroven == u]
        if not nn:
            continue
        h.append(f"<section data-sev='{u}'><h3 style='margin:18px 0 10px'><span class='dot d-{cls}' aria-hidden='true'>{ikona}</span> {lbl} ({len(nn)})</h3>")
        for o, onazev in OBLASTI:
            for kod in dict.fromkeys(n.kod for n in nn if n.oblast == o):
                sk_n = [n for n in nn if n.oblast == o and n.kod == kod]
                gid = f"g-{u}-{kod}"
                h.append(f"<details class='grp' id='{gid}' data-u='{u}' data-o='{o}'><summary><span class='dot d-{cls}' aria-hidden='true'>{ikona}</span>"
                         f"<span class='t'>{kod} · {e(NAZEV.get(kod, sk_n[0].popis))}</span><span class='badge'>{e(onazev)}</span>"
                         f"<span class='c'>{len(sk_n)}×</span></summary><div class='body'>"
                         f"<div class='rec'><strong>Doporučení:</strong> {_inline(sk_n[0].doporuceni)}</div><ul class='items'>")
                for n in sk_n[:100]:
                    h.append(f"<li><code>{e(n.objekt)}</code> – {e(n.popis)}</li>")
                if len(sk_n) > 100:
                    h.append(f"<li class='muted'>… a dalších {len(sk_n) - 100} v CSV</li>")
                h.append("</ul>")
                if o == "dax":
                    for n in sk_n[:30]:
                        x = dax_podle.get(n.objekt)
                        if n.navrh and x:
                            h.append(f"<div style='margin-top:10px'><div class='tag'>{e(n.objekt)} · {'přesná úprava' if n.presny else 'k ověření'}</div>"
                                     f"<div class='pair'><div><div class='muted' style='font-size:12px'>Před</div><pre>{e(x['puvodni'])}</pre></div>"
                                     f"<div><div class='muted' style='font-size:12px'>Po</div><pre>{e(n.navrh)}</pre></div></div></div>")
                h.append("</div></details>")
        h.append("</section>")
    if not nalezy:
        h.append("<div class='card'>Bez nálezů.</div>")

    # --- tabulka pro přístupnost / tisk
    h.append("<h2>Přehled v tabulce</h2><div class='card' style='overflow:auto'><table class='t'><thead><tr><th>Oblast</th>"
             + "".join(f"<th class='num'>{lbl}</th>" for _, lbl, _, _ in UROVNE) + "<th class='num'>Celkem</th></tr></thead><tbody>")
    for o, nazev in OBLASTI:
        c = podle_oblasti[o]
        h.append(f"<tr><td>{e(nazev)}</td>" + "".join(f"<td class='num'>{c[u]}</td>" for u, _, _, _ in UROVNE) + f"<td class='num'>{sum(c.values())}</td></tr>")
    h.append("</tbody></table></div>")
    h.append(f"<footer>Vygenerováno nástrojem <a href='https://github.com/vzr-repo/tools' style='color:inherit'>pbip_audit</a> · statická kontrola "
             "souborů projektu – nezná data ani uživatele, čísla ověřuj v Power BI Desktopu.</footer>")
    h.append(f"</div></div><script>{JS}</script></body></html>")
    return "".join(h)
