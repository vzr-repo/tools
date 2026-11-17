"""Dokumentace Power BI projektu pro AI (a pro lidi): jeden Markdown se vším, co model a report obsahují.

    python ai_dokumentace.py <report.pbip | složka *.Report | složka projektu> [--vystup slozka] [--bez-dax] [--bez-m] [--lang en]

Výstup model_<nazev>.md:
- tabulky (popis, zrnitost, zdrojový dotaz Power Query), sloupce (typ, popis), míry (popis, formát, DAX),
- vztahy, role (RLS filtry, OLS), stránky reportu s vizuály a poli, které zobrazují.
Soubor dej AI jako kontext („tady je dokumentace mého modelu…“) – pro psaní DAX, vysvětlování čísel, revize nebo
návrh popisů. Skryté technické objekty jsou označené, ať AI ví, že nejsou pro uživatele.
"""
import argparse
import sys
from pathlib import Path

import jazyk
from jazyk import L
from pbip import Projekt

POPIS_EN = """Documentation of a Power BI project for AI (and for people): one Markdown file with everything in the model and report.

    python ai_dokumentace.py <report.pbip | *.Report folder | project folder> [--output folder] [--no-dax] [--no-m] --lang en

Output model_<name>.md:
- tables (description, grain, Power Query source), columns (type, description), measures (description, format, DAX),
- relationships, roles (RLS filters, OLS), report pages with their visuals and the fields they show.
Give the file to an AI as context ("here is the documentation of my model…") – for writing DAX, explaining numbers, reviews
or drafting descriptions. Hidden technical objects are marked so the AI knows they are not for users.
"""


def main():
    from audit import _jazyk_z_argv
    _jazyk_z_argv(sys.argv[1:])
    ap = argparse.ArgumentParser(description=L(__doc__, POPIS_EN), formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projekt", metavar=L("projekt", "project"))
    ap.add_argument(*jazyk.volby("--vystup", "--output"), dest="vystup", default=".", metavar=L("SLOZKA", "FOLDER"), help=L("složka pro výstup", "output folder"))
    ap.add_argument(*jazyk.volby("--bez-dax", "--no-dax"), dest="bez_dax", action="store_true", help=L("bez DAX výrazů měr (kratší)", "without measure DAX (shorter)"))
    ap.add_argument(*jazyk.volby("--bez-m", "--no-m"), dest="bez_m", action="store_true", help=L("bez Power Query dotazů", "without Power Query"))
    ap.add_argument(*jazyk.volby("--jazyk", "--lang"), dest="lang", choices=["cs", "en"], help=L("jazyk výstupů (výchozí cs)", "output language (default cs)"))
    a = ap.parse_args()
    jazyk.nastav(a.lang)
    p = Projekt(a.projekt)
    skryta, skryty = L(" (skrytá)", " (hidden)"), L(" (skrytý)", " (hidden)")
    bez_popisu = L("_bez popisu_", "_no description_")
    md = [L(f"# Model a report {p.nazev}", f"# Model and report {p.nazev}"), "",
          L(f"{len(p.tabulky)} tabulek, {len(p.sloupce)} sloupců, {len(p.miry)} měr, {len(p.vztahy)} vztahů, {len(p.role)} rolí, "
            f"{len(p.stranky)} stránek reportu. (skryté) = technický objekt, uživatel ho nevidí.",
            ", ".join(jazyk.tvar(n, "", "", "", a, b) for n, a, b in ((len(p.tabulky), "table", "tables"), (len(p.sloupce), "column", "columns"),
                      (len(p.miry), "measure", "measures"), (len(p.vztahy), "relationship", "relationships"), (len(p.role), "role", "roles"),
                      (len(p.stranky), "report page", "report pages"))) + ". (hidden) = technical object, users don't see it."),
          L(f"Formát: report {p.format_reportu}, model {p.format_modelu}.", f"Format: report {p.format_reportu}, model {p.format_modelu}."),
          "", L("## Tabulky", "## Tables"), ""]
    for t in sorted(p.tabulky, key=lambda t: t.nazev):
        if t.nazev.startswith(("LocalDateTable", "DateTableTemplate")):
            continue
        md += [f"### {t.nazev}{skryta if t.skryta else ''}{L(' · tabulka kalendáře', ' · date table') if t.kategorie.lower() == 'time' else ''}",
               "", t.popis or bez_popisu, ""]
        sl = [s for s in p.sloupce if s.tabulka == t.nazev]
        if sl:
            md += [L("| Sloupec | Typ | Popis |", "| Column | Type | Description |"), "|---|---|---|"]
            md += [f"| {s.nazev}{skryty if s.skryty else ''} | {s.typ}{' · DAX' if s.vypocet else ''} | {s.popis} |" for s in sl]
            md.append("")
        miry = [m for m in p.miry if m.tabulka == t.nazev]
        if miry:
            md += [L("Míry:", "Measures:"), ""]
            for m in miry:
                md.append(f"- **{m.nazev}**{skryta if m.skryta else ''}{L(f' · složka {m.slozka}', f' · folder {m.slozka}') if m.slozka else ''}"
                          f"{L(f' · formát `{m.format}`', f' · format `{m.format}`') if m.format else ''} – {m.popis or bez_popisu}")
                if not a.bez_dax:
                    md += ["  ```dax", "  " + m.dax.replace("\n", "\n  "), "  ```"]
            md.append("")
        if t.m_vyraz and not a.bez_m:
            md += ["<details><summary>Power Query</summary>", "", "```powerquery", t.m_vyraz, "```", "</details>", ""]
    md += [L("## Vztahy", "## Relationships"), "", L("| Z (mnoho) | Do (jedna) | Poznámka |", "| From (many) | To (one) | Note |"), "|---|---|---|"]
    md += [f"| {v.z} | {v.do} | {L('neaktivní ', 'inactive ') if not v.aktivni else ''}{L('obousměrný ', 'bidirectional ') if v.smer == 'bothDirections' else ''}"
           f"{L('mnoho:mnoho ', 'many-to-many ') if v.kardinalita_do == 'many' else ''}"
           f"{L('RLS oběma směry', 'RLS both directions') if v.bezpecnost == 'bothDirections' else ''} |"
           for v in p.vztahy]
    if p.role:
        md += ["", L("## Role (zabezpečení)", "## Roles (security)"), ""]
        for r in p.role:
            md += [f"### {r.nazev} ({r.opravneni})", ""]
            md += [L(f"- filtr řádků na **{t}**: `{d.replace(chr(10), ' ')}`", f"- row filter on **{t}**: `{d.replace(chr(10), ' ')}`")
                   for t, d in r.filtry.items()]
            md += [L(f"- OLS skrývá tabulku {t}", f"- OLS hides table {t}") for t in sorted(r.ols_tabulky)]
            md += [L(f"- OLS skrývá sloupec {t}[{c}]", f"- OLS hides column {t}[{c}]") for t, c in sorted(r.ols_sloupce)]
            if not r.filtry and not r.ols_tabulky and not r.ols_sloupce:
                md.append(L("- bez omezení", "- no restrictions"))
            md.append("")
    md += ["", L("## Stránky reportu", "## Report pages"), ""]
    for s in p.stranky:
        vv = [v for v in p.vizualy if v.stranka == s.nazev and not v.skryty and v.pole()]
        md += [f"### {s.zobrazeny}{skryta if s.skryta else ''}", ""]
        for v in vv:
            pole = ", ".join(sorted(f"{t}[{c}]" for t, c in v.pole()))
            md.append(f"- {v.typ}{L(f' „{v.titulek}“', f' “{v.titulek}”') if v.titulek else ''}: {pole}")
        md.append("")
    out = Path(a.vystup)
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"model_{p.nazev}.md"
    f.write_text("\n".join(md), encoding="utf-8")
    print(f"-> {f} ({f.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
