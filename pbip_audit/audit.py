"""Audit Power BI projektu PBIP: kontroly modelu, reportu a připravenosti pro AI -> Markdown + CSV.

    python audit.py <report.pbip | složka *.Report | složka projektu> [--vystup slozka] [--bez-info]
    python audit.py <složka> --vse        # všechny reporty ve složce a podsložkách (každý zvlášť + souhrn)
    python audit.py <projekt> --nastaveni klient.json --baseline audit/audit_X.csv --fail-on chyba   # CI / opakovaný audit
    python audit.py <projekt> --lang en   # výstupy anglicky (nebo proměnná prostředí PBIP_AUDIT_LANG=en)

Výstup: audit_<nazev>.md (souhrn, skóre AI připravenosti, nálezy podle oblastí), audit_<nazev>.csv (všechny nálezy, se
stabilním id), dax_<nazev>.md (navržené přepisy měr před / po, jsou-li) a s --html grafický audit_<nazev>.html.
--html       samostatný HTML report (metriky, nálezy podle závažnosti a oblasti, doporučení, Jak pokračovat).
--shrnuti    text (Markdown) slovního shrnutí do HTML – typicky od AI; bez něj je v HTML hotový prompt.

--nastaveni  JSON klienta: glosář termínů (M23), rodiny měr (M24) a výjimky (potlačené nálezy s důvodem) – viz
             nastaveni_priklad.json.
--baseline   CSV z předchozího auditu: v souhrnu nové a vyřešené chyby/varování (páruje se podle id).
--fail-on    nic (výchozí) / chyba / varovani – kdy vrátit nenulový exit kód.

Exit kódy: 0 v pořádku (nebo pod prahem --fail-on), 1 varování, 2 chyby, 3 projekt nejde načíst nebo parser selhal.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from fnmatch import fnmatchcase
from pathlib import Path

import jazyk
from jazyk import SKORE, L, OBLAST, UROVEN_Z_EN
from kontroly import NADPISY, Nalez, spust
from pbip import Projekt, _jmeno, _rozdel_odkaz, najdi_reporty

POPIS_EN = """Audit a Power BI PBIP project: checks of the model, report, DAX, AI readiness and security -> Markdown + CSV (+ HTML).

    python audit.py <report.pbip | *.Report folder | project folder> [--output folder] [--no-info] --lang en
    python audit.py <folder> --all        # every report in the folder and subfolders (each separately + a summary)
    python audit.py <project> --settings client.json --baseline audit/audit_X.csv --fail-on error   # CI / repeated audit

Output: audit_<name>.md (summary, AI readiness score, findings by area), audit_<name>.csv (all findings with a stable
id), dax_<name>.md (proposed measure rewrites before / after, if any) and with --html a graphical audit_<name>.html.
--html       self-contained HTML report (metrics, findings by severity and area, recommendations, next steps).
--summary    Markdown text of a narrative summary for the HTML – typically from an AI; without it the HTML shows a prompt.

--settings   client JSON: glossary of terms (M23), measure families (M24) and exceptions (suppressed findings with a
             reason) – see nastaveni_priklad.json (English keys terms / families / exceptions / reason work too).
--baseline   CSV of a previous audit: new and resolved errors/warnings in the summary (matched by id).
--fail-on    none (default) / error / warning – when to return a non-zero exit code.
--lang       cs (default) / en – language of the output (or the PBIP_AUDIT_LANG=en environment variable).

Exit codes: 0 OK (or below the --fail-on threshold), 1 warnings, 2 errors, 3 project can't be loaded or parser failed.
"""

IKONA = {"chyba": "🔴", "varovani": "🟠", "info": "⚪"}
UROVNE = jazyk.LDict({"chyba": ("🔴 chyba", "🔴 error"), "varovani": ("🟠 varování", "🟠 warning"), "info": ("⚪ info", "⚪ info")})


VAHY_AI = {"popisy měr": 0.25, "popisy viditelných sloupců": 0.20, "popisy tabulek": 0.15, "skryté technické sloupce": 0.15,
           "srozumitelné názvy": 0.10, "míry ve složkách": 0.10, "označený kalendář": 0.05}


def skore_ai(p: Projekt) -> dict:
    """Skóre 0–100 (vážený průměr složek v VAHY_AI): popisy, skrytý technický šum, srozumitelné názvy tabulek / měr /
    sloupců, míry ve složkách (u tabulek s 8+ měrami) a označená tabulka kalendáře."""
    from kontroly import GENERICKE, SYSTEMOVE, TECHNICKA_TABULKA, TECHNICKE

    def podil(cast, celek):
        return round(100 * cast / celek) if celek else 100
    viditelne = [s for s in p.sloupce if not s.skryty]
    miry = [m for m in p.miry if not m.skryta]
    tabulky = [t for t in p.tabulky if not t.skryta and not t.nazev.startswith(SYSTEMOVE)]
    tech = [s for s in p.sloupce if TECHNICKE.search(s.nazev)]
    nazvy = [t.nazev for t in tabulky if not t.vypoctova_skupina] + [m.nazev for m in miry] + [s.nazev for s in viditelne]
    spatne = sum(1 for t in tabulky if not t.vypoctova_skupina and (TECHNICKA_TABULKA.search(t.nazev) or GENERICKE.search(t.nazev))) + \
        sum(1 for n in [m.nazev for m in miry] + [s.nazev for s in viditelne] if GENERICKE.search(n) or "_" in n)
    velke = [t.nazev for t in p.tabulky if sum(1 for m in miry if m.tabulka == t.nazev) >= 8]
    ve_slozkach = [m for m in miry if m.tabulka in velke]
    ma_datum = any(s.typ.lower() in ("datetime", "date") for s in p.sloupce)
    slozky = {
        "popisy měr": podil(sum(1 for m in miry if m.popis), len(miry)),
        "popisy viditelných sloupců": podil(sum(1 for s in viditelne if s.popis), len(viditelne)),
        "popisy tabulek": podil(sum(1 for t in tabulky if t.popis), len(tabulky)),
        "skryté technické sloupce": podil(sum(1 for s in tech if s.skryty), len(tech)),
        "srozumitelné názvy": podil(len(nazvy) - spatne, len(nazvy)),
        "míry ve složkách": podil(sum(1 for m in ve_slozkach if m.slozka), len(ve_slozkach)),
        "označený kalendář": 100 if not ma_datum or any(t.kategorie.lower() == "time" for t in p.tabulky) else 0,
    }
    return {"skore": round(sum(slozky[k] * VAHY_AI[k] for k in slozky)), **slozky}


def kontrola_nacteni(p: Projekt) -> list[str]:
    """Pojistka proti tichému selhání parseru: model s tabulkami a vztahy, ale bez sloupců, nebo vztahy, jejichž konce
    v načteném modelu chybí, znamenají, že parser formát nepřečetl – audit by pak hlásil „čistý“ nebo nesmyslný výsledek."""
    if not p.model_dir:
        return []                                                               # tenký report – model se nečte
    problemy = []
    if not p.tabulky:
        problemy.append(L(f"Model ({p.format_modelu or '?'}) nemá žádnou tabulku.", f"The model ({p.format_modelu or '?'}) has no table."))
    elif not p.sloupce:
        problemy.append(L(f"Načteno {len(p.tabulky)} tabulek, ale 0 sloupců.", f"Loaded {len(p.tabulky)} tables but 0 columns."))
    sloupce = {(s.tabulka, s.nazev) for s in p.sloupce}
    konce = [(_jmeno(_rozdel_odkaz(x)[0]), _rozdel_odkaz(x)[1]) for v in p.vztahy for x in (v.z, v.do)]
    chybi = [k for k in konce if k not in sloupce]
    if len(p.vztahy) >= 3 and len(chybi) > len(konce) / 2:
        problemy.append(L(f"{len(chybi)} z {len(konce)} konců vztahů v načtených sloupcích chybí (např. {chybi[0][0]}[{chybi[0][1]}]).",
                          f"{len(chybi)} of {len(konce)} relationship ends are missing from the loaded columns (e.g. {chybi[0][0]}[{chybi[0][1]}])."))
    return problemy


def nacti_nastaveni(cesta) -> dict:
    """JSON klienta. Klíče česky (terminy, rodiny, vyjimky: id / kod / objekt / duvod) nebo anglicky
    (terms, families, exceptions: id / code / object / reason) – uvnitř se převedou na české."""
    if not cesta:
        return {}
    d = json.loads(Path(cesta).read_text(encoding="utf-8-sig"))
    for en, cs in (("terms", "terminy"), ("families", "rodiny"), ("exceptions", "vyjimky")):
        if en in d and cs not in d:
            d[cs] = d.pop(en)
    d["vyjimky"] = [{{"code": "kod", "object": "objekt", "reason": "duvod"}.get(k, k): h for k, h in v.items()}
                    for v in d.get("vyjimky", [])]
    if not d["vyjimky"]:
        d.pop("vyjimky")
    for v in d.get("vyjimky", []):
        if not v.get("duvod"):
            raise ValueError(L(f"Výjimka bez důvodu v {cesta}: {v} – každá výjimka musí mít „duvod“.",
                               f"Exception without a reason in {cesta}: {v} – every exception needs a \"reason\"."))
    return d


def je_vyjimka(n: Nalez, vyjimky: list[dict]) -> bool:
    """Výjimka: {"id": "…"} nebo {"kod": "M21", "objekt": "Kurzy*"} (objekt = vzor se * a ?), vždy s „duvod“."""
    for v in vyjimky:
        if "id" in v and v["id"] == n.id:
            return True
        if "kod" in v and v["kod"] == n.kod and fnmatchcase(jazyk.cesky(n.objekt), v.get("objekt", "*")):
            return True
    return False


def nacti_baseline(cesta) -> set[str]:
    """Id nálezů z dřívějšího CSV (české i anglické hlavičky). Starší CSV bez sloupce id – id se dopočítá z kódu,
    objektu a popisu."""
    with open(cesta, newline="", encoding="utf-8-sig") as f:
        return {r.get("id") or Nalez(r.get("kod") or r.get("code"), "", "", r.get("objekt") or r.get("object", ""),
                                     r.get("popis") or r.get("description", "")).id
                for r in csv.DictReader(f, delimiter=";")}


def exit_kod(pocty: Counter, fail_on: str) -> int:
    fail_on = UROVEN_Z_EN.get(fail_on, fail_on)
    if pocty["chyba"] and fail_on in ("chyba", "varovani"):
        return 2
    if pocty["varovani"] and fail_on == "varovani":
        return 1
    return 0


def dax_navrhy(p: Projekt, nalezy) -> list[dict]:
    """Pro každou míru s nálezem D…: původní DAX, přepis jen přesnými úpravami a přepis včetně úprav k ověření."""
    import dax as daxlib
    from kontroly import _dax_kontext
    ctx = _dax_kontext(p)
    podle = {}
    for n in nalezy:
        if n.oblast == "dax":
            podle.setdefault(n.objekt, []).append(n)
    out = []
    for m in p.miry:
        kde = f"{m.tabulka}{m.plny}"
        if kde not in podle:
            continue
        presny, kody_p = daxlib.zjednodus(m.dax, ctx, jen_presne=True)
        vse, kody_v = daxlib.zjednodus(m.dax, ctx, jen_presne=False)
        out.append({"objekt": kde, "tabulka": m.tabulka, "mira": m.nazev, "puvodni": m.dax, "nalezy": podle[kde],
                    "presny": presny if kody_p else "", "kody_presne": kody_p,
                    "vse": vse if vse != (presny if kody_p else m.dax) else "", "kody_vse": kody_v})
    return out


def dax_md(p: Projekt, navrhy: list[dict]) -> list[str]:
    md = [L(f"# Návrhy úprav DAX – {p.nazev}", f"# Proposed DAX changes – {p.nazev}"), "",
          L("**Přesná úprava** dává stejný výsledek (refaktoring) – dá se převzít rovnou. **Úprava k ověření** mění chování "
            "(opravuje chybu nebo mění filtr) – před nasazením porovnej čísla v Desktopu. Zapsat do modelu jde přes "
            "`oprav.py --sablona` (řádky s akcí `dax`).",
            "An **exact rewrite** returns the same result (refactoring) – you can take it as is. A **rewrite to verify** changes "
            "behaviour (fixes a bug or changes a filter) – compare the numbers in Desktop before deploying. Write it into the model "
            "with `oprav.py --template` (rows with action `dax`)."), ""]
    for x in navrhy:
        md += [f"## {x['objekt']}", ""]
        md += [f"- {n.kod} ({L('přesné', 'exact') if n.presny else L('ověřit', 'verify') if n.navrh else L('bez návrhu', 'no proposal')}): {n.popis}"
               for n in x["nalezy"]]
        md += ["", L("Původní:", "Original:"), "", "```dax", x["puvodni"], "```", ""]
        if x["presny"]:
            md += [L(f"Přesná úprava ({', '.join(x['kody_presne'])}):", f"Exact rewrite ({', '.join(x['kody_presne'])}):"), "",
                   "```dax", x["presny"], "```", ""]
        if x["vse"]:
            md += [L(f"Včetně úprav k ověření ({', '.join(x['kody_vse'])}):", f"Including rewrites to verify ({', '.join(x['kody_vse'])}):"),
                   "", "```dax", x["vse"], "```", ""]
        if not x["presny"] and not x["vse"]:
            md += [L("Automatický přepis není – viz doporučení u nálezu.", "No automatic rewrite – see the recommendation of the finding."), ""]
    return md


def _jazyk_z_argv(argv: list[str]) -> None:
    """--lang / --jazyk se čte předem, aby byla i nápověda (--help) v daném jazyce."""
    for i, x in enumerate(argv):
        if x in ("--lang", "--jazyk") and i + 1 < len(argv):
            jazyk.nastav(argv[i + 1])
        elif x.startswith(("--lang=", "--jazyk=")):
            jazyk.nastav(x.split("=", 1)[1])


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=L(__doc__, POPIS_EN), formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projekt", metavar=L("projekt", "project"))
    ap.add_argument(*jazyk.volby("--vystup", "--output"), dest="vystup", default=".", metavar=L("SLOZKA", "FOLDER"), help=L("složka pro výstupy", "output folder"))
    ap.add_argument(*jazyk.volby("--bez-info", "--no-info"), dest="bez_info", action="store_true", help=L("vynechat nálezy úrovně info", "skip info-level findings"))
    ap.add_argument(*jazyk.volby("--vse", "--all"), dest="vse", action="store_true", help=L("auditovat všechny reporty ve složce", "audit every report in the folder"))
    ap.add_argument("--html", action="store_true", help=L("navíc grafický report audit_<nazev>.html (jeden soubor, otevře se v prohlížeči)",
                                                          "also a graphical report audit_<name>.html (single file, opens in a browser)"))
    ap.add_argument(*jazyk.volby("--shrnuti", "--summary"), dest="shrnuti", metavar="MD", help=L("text shrnutí (např. od AI) do HTML reportu",
                                                                                     "summary text (e.g. from an AI) for the HTML report"))
    ap.add_argument(*jazyk.volby("--nastaveni", "--settings"), dest="nastaveni", metavar="JSON", help=L("JSON klienta: terminy, rodiny, vyjimky", "client JSON: terms, families, exceptions"))
    ap.add_argument("--baseline", metavar="CSV", help=L("CSV z předchozího auditu – porovnat nové / vyřešené nálezy", "CSV of a previous audit – compare new / resolved findings"))
    ap.add_argument("--fail-on", choices=["nic", "chyba", "varovani", "none", "error", "warning"], default="nic",
                    help=L("kdy vrátit nenulový exit kód", "when to return a non-zero exit code"))
    ap.add_argument(*jazyk.volby("--jazyk", "--lang"), dest="lang", choices=["cs", "en"], help=L("jazyk výstupů (výchozí cs)", "output language (default cs)"))
    return ap


def main():
    _jazyk_z_argv(sys.argv[1:])
    a = parser().parse_args()
    jazyk.nastav(a.lang)
    try:
        a.nastaveni_data = nacti_nastaveni(a.nastaveni)
    except (OSError, ValueError) as e:
        print(L(f"CHYBA nastavení: {e}", f"SETTINGS ERROR: {e}"))
        sys.exit(3)
    cesty = najdi_reporty(a.projekt) if a.vse else [a.projekt]
    souhrn, kody = [], []
    for c in cesty:
        try:
            *radek, kod = audituj(Projekt(c), a)
            souhrn.append(tuple(radek)); kody.append(kod)
        except Exception as e:  # noqa: BLE001 – jeden rozbitý report nesmí zastavit dávku
            print(L(f"CHYBA {c}: {e}", f"ERROR {c}: {e}"))
            souhrn.append((str(c), L("nelze načíst", "can't be loaded"), str(e))); kody.append(3)
    if a.vse:
        soubor = L("audit_souhrn.md", "audit_summary.md")
        radky = [L("# Souhrn auditu", "# Audit summary"), "", L("| Report | Formát | Výsledek |", "| Report | Format | Result |"), "|---|---|---|"] + \
                [f"| {r} | {f} | {v} |" for r, f, v in souhrn]
        (Path(a.vystup) / soubor).write_text(chr(10).join(radky), encoding="utf-8")
        print(L(f"Souhrn {len(souhrn)} reportů -> {Path(a.vystup) / soubor}", f"Summary of {len(souhrn)} reports -> {Path(a.vystup) / soubor}"))
    sys.exit(max(kody, default=0))


def audituj(p: Projekt, a):
    nastaveni = getattr(a, "nastaveni_data", None) or {}
    p.nastaveni = nastaveni
    problemy = kontrola_nacteni(p)
    baseline = getattr(a, "baseline", None)
    stare = nacti_baseline(baseline) if baseline and Path(baseline).exists() else None   # před zápisem – může jít o tentýž soubor
    vsechny = [n for n in spust(p) if not (a.bez_info and n.uroven == "info")]
    vyjimky = nastaveni.get("vyjimky", [])
    nalezy = [n for n in vsechny if not je_vyjimka(n, vyjimky)]
    potlacene = len(vsechny) - len(nalezy)
    poradi = {"chyba": 0, "varovani": 1, "info": 2}
    nalezy.sort(key=lambda n: (poradi[n.uroven], n.kod, jazyk.cesky(n.objekt)))
    out = Path(a.vystup)
    out.mkdir(parents=True, exist_ok=True)

    with open(out / f"audit_{p.nazev}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if jazyk.en():
            w.writerow(["code", "level", "area", "object", "description", "recommendation", "id"])
            w.writerows([(n.kod, jazyk.UROVEN[n.uroven], n.oblast, n.objekt, n.popis, n.doporuceni, n.id) for n in nalezy])
        else:
            w.writerow(["kod", "uroven", "oblast", "objekt", "popis", "doporuceni", "id"])
            w.writerows([(n.kod, n.uroven, n.oblast, n.objekt, n.popis, n.doporuceni, n.id) for n in nalezy])

    sk = skore_ai(p)
    pocty = Counter(n.uroven for n in nalezy)
    md = [L(f"# Audit reportu {p.nazev}", f"# Report audit {p.nazev}"), "",
          L(f"Datum: {date.today():%d. %m. %Y} · nástroj: pbip_audit (github.com/vzr-repo/tools)",
            f"Date: {date.today():%Y-%m-%d} · tool: pbip_audit (github.com/vzr-repo/tools)"), "",
          L("## Souhrn", "## Summary"), "",
          L(f"- Formát: report {p.format_reportu}, model {p.format_modelu}", f"- Format: report {p.format_reportu}, model {p.format_modelu}"),
          L(f"- Stránky: {len(p.stranky)} · vizuály: {len(p.vizualy)} (skryté {sum(v.skryty for v in p.vizualy)}) · záložky: {len(p.zalozky)}",
            f"- Pages: {len(p.stranky)} · visuals: {len(p.vizualy)} (hidden {sum(v.skryty for v in p.vizualy)}) · bookmarks: {len(p.zalozky)}"),
          L(f"- Model: {len(p.tabulky)} tabulek · {len(p.sloupce)} sloupců · {len(p.miry)} měr · {len(p.vztahy)} vztahů · "
            f"{len(p.role)} rolí (RLS/OLS)",
            f"- Model: {len(p.tabulky)} tables · {len(p.sloupce)} columns · {len(p.miry)} measures · {len(p.vztahy)} relationships · "
            f"{len(p.role)} roles (RLS/OLS)"),
          L(f"- Nálezy: {pocty['chyba']} chyb · {pocty['varovani']} varování · {pocty['info']} info"
            + (f" · {potlacene} potlačeno výjimkou" if potlacene else ""),
            f"- Findings: {pocty['chyba']} errors · {pocty['varovani']} warnings · {pocty['info']} info"
            + (f" · {potlacene} suppressed by an exception" if potlacene else "")), ""]
    if problemy:
        md += [L("## ⚠️ Model se nenačetl správně", "## ⚠️ The model was not loaded correctly"), "",
               L("Výsledky auditu modelu nejsou spolehlivé (exit kód 3):", "Model audit results are not reliable (exit code 3):"), ""] + \
              [f"- {x}" for x in problemy] + ["", L("Ověř formát projektu (TMDL / model.bim) a pošli ukázku souboru k opravě parseru.",
                                                     "Check the project format (TMDL / model.bim) and send a sample file so the parser can be fixed."), ""]
    zmeny = None
    if stare is not None:
        dulezite = [n for n in nalezy if n.uroven != "info"]
        nove = [n for n in dulezite if n.id not in stare]
        vyresene = len(stare - {n.id for n in nalezy})
        zmeny = (len(nove), vyresene)
        md += [L(f"## Proti baseline ({Path(baseline).name})", f"## Against the baseline ({Path(baseline).name})"), "",
               L(f"- Nové chyby a varování: {len(nove)}", f"- New errors and warnings: {len(nove)}"),
               L(f"- Vyřešené nálezy (všech úrovní): {vyresene}", f"- Resolved findings (all levels): {vyresene}"), ""]
        md += [f"  - {n.kod} {n.popis} – `{n.objekt}`" for n in nove[:30]] + (["  - …"] if len(nove) > 30 else [])
        md += [""]
    md += [
          L(f"## Připravenost pro AI: {sk['skore']} / 100", f"## AI readiness: {sk['skore']} / 100"), "",
          L("| Složka | % | Váha |", "| Component | % | Weight |"), "|---|---|---|"] + \
        [f"| {SKORE[k]} | {v} | {round(VAHY_AI[k] * 100)} % |" for k, v in sk.items() if k != "skore"] + [
          "", L("AI (Copilot, agenti nad modelem) čte názvy a popisy tabulek, sloupců a měr. Čím víc popisů a méně technického šumu,",
                "AI (Copilot, agents over the model) reads the names and descriptions of tables, columns and measures. The more"),
          L("tím přesnější odpovědi.", "descriptions and the less technical noise, the more accurate the answers."), ""]
    for oblast in ("model", "report", "ai", "rls", "dax"):
        nazev = OBLAST[oblast]
        if oblast == "rls" and not p.role:
            md += [f"## {nazev}", "", L("Model nemá žádné role – RLS se nekontroluje.", "The model has no roles – RLS is not checked."), ""]
            continue
        sk_n = [n for n in nalezy if n.oblast == oblast]
        md += [f"## {nazev} ({len(sk_n)})", ""]
        if not sk_n:
            md += [L("Bez nálezů.", "No findings."), ""]
            continue
        for kod in dict.fromkeys(n.kod for n in sk_n):
            skupina = [n for n in sk_n if n.kod == kod]
            md += [f"### {kod} · {UROVNE[skupina[0].uroven]} · {NADPISY.get(kod, skupina[0].popis)} ({len(skupina)}×)",
                   "", L(f"Doporučení: {skupina[0].doporuceni}", f"Recommendation: {skupina[0].doporuceni}"), ""]
            md += [f"- {n.popis} – `{n.objekt}`" for n in skupina[:25]]
            if len(skupina) > 25:
                md.append(L(f"- … a dalších {len(skupina) - 25} (viz CSV)", f"- … and {len(skupina) - 25} more (see the CSV)"))
            md.append("")
    navrhy = dax_navrhy(p, nalezy)
    if navrhy:
        md += [L(f"Navržené přepisy měr (před / po): `dax_{p.nazev}.md`", f"Proposed measure rewrites (before / after): `dax_{p.nazev}.md`"), ""]
        (out / f"dax_{p.nazev}.md").write_text("\n".join(dax_md(p, navrhy)), encoding="utf-8")
    (out / f"audit_{p.nazev}.md").write_text("\n".join(md), encoding="utf-8")
    if getattr(a, "html", False):
        from html_report import html_report
        shrnuti = Path(a.shrnuti).read_text(encoding="utf-8-sig") if getattr(a, "shrnuti", None) else ""
        (out / f"audit_{p.nazev}.html").write_text(html_report(p, nalezy, sk, problemy, potlacene, navrhy, zmeny, shrnuti), encoding="utf-8")
        print(f"-> {out / f'audit_{p.nazev}.html'}")
    kod = 3 if problemy else exit_kod(pocty, getattr(a, "fail_on", "nic"))
    print(L(f"Audit {p.nazev}: {pocty['chyba']} chyb, {pocty['varovani']} varování, {pocty['info']} info; AI skóre {sk['skore']}/100"
            + (f"; baseline: +{zmeny[0]} nových, {zmeny[1]} vyřešených" if zmeny else "")
            + (f"; POZOR model se nenačetl správně: {problemy[0]}" if problemy else ""),
            f"Audit {p.nazev}: {pocty['chyba']} errors, {pocty['varovani']} warnings, {pocty['info']} info; AI score {sk['skore']}/100"
            + (f"; baseline: +{zmeny[0]} new, {zmeny[1]} resolved" if zmeny else "")
            + (f"; WARNING the model was not loaded correctly: {problemy[0]}" if problemy else "")))
    print(f"-> {out / f'audit_{p.nazev}.md'}")
    return (p.nazev, f"{p.format_reportu} / {p.format_modelu}",
            L(f"{pocty['chyba']} chyb, {pocty['varovani']} varování, AI {sk['skore']}/100",
              f"{pocty['chyba']} errors, {pocty['varovani']} warnings, AI {sk['skore']}/100") + (" · ⚠️ parser" if problemy else ""), kod)


if __name__ == "__main__":
    main()
