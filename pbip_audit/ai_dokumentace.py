"""Dokumentace Power BI projektu pro AI (a pro lidi): jeden Markdown se vším, co model a report obsahují.

    python ai_dokumentace.py <report.pbip | složka *.Report | složka projektu> [--vystup slozka] [--bez-dax] [--bez-m]

Výstup model_<nazev>.md:
- tabulky (popis, zrnitost, zdrojový dotaz Power Query), sloupce (typ, popis), míry (popis, formát, DAX),
- vztahy, role (RLS filtry, OLS), stránky reportu s vizuály a poli, které zobrazují.
Soubor dej AI jako kontext („tady je dokumentace mého modelu…“) – pro psaní DAX, vysvětlování čísel, revize nebo
návrh popisů. Skryté technické objekty jsou označené, ať AI ví, že nejsou pro uživatele.
"""
import argparse
from pathlib import Path

from pbip import Projekt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projekt")
    ap.add_argument("--vystup", default=".")
    ap.add_argument("--bez-dax", action="store_true", help="bez DAX výrazů měr (kratší)")
    ap.add_argument("--bez-m", action="store_true", help="bez Power Query dotazů")
    a = ap.parse_args()
    p = Projekt(a.projekt)
    md = [f"# Model a report {p.nazev}", "",
          f"{len(p.tabulky)} tabulek, {len(p.sloupce)} sloupců, {len(p.miry)} měr, {len(p.vztahy)} vztahů, {len(p.role)} rolí, "
          f"{len(p.stranky)} stránek reportu. (skryté) = technický objekt, uživatel ho nevidí.",
          f"Formát: report {p.format_reportu}, model {p.format_modelu}.", "", "## Tabulky", ""]
    for t in sorted(p.tabulky, key=lambda t: t.nazev):
        if t.nazev.startswith(("LocalDateTable", "DateTableTemplate")):
            continue
        md += [f"### {t.nazev}{' (skrytá)' if t.skryta else ''}{' · tabulka kalendáře' if t.kategorie.lower() == 'time' else ''}",
               "", t.popis or "_bez popisu_", ""]
        sl = [s for s in p.sloupce if s.tabulka == t.nazev]
        if sl:
            md += ["| Sloupec | Typ | Popis |", "|---|---|---|"]
            md += [f"| {s.nazev}{' (skrytý)' if s.skryty else ''} | {s.typ}{' · DAX' if s.vypocet else ''} | {s.popis} |" for s in sl]
            md.append("")
        miry = [m for m in p.miry if m.tabulka == t.nazev]
        if miry:
            md += ["Míry:", ""]
            for m in miry:
                md.append(f"- **{m.nazev}**{' (skrytá)' if m.skryta else ''}{f' · složka {m.slozka}' if m.slozka else ''}"
                          f"{f' · formát `{m.format}`' if m.format else ''} – {m.popis or '_bez popisu_'}")
                if not a.bez_dax:
                    md += ["  ```dax", "  " + m.dax.replace("\n", "\n  "), "  ```"]
            md.append("")
        if t.m_vyraz and not a.bez_m:
            md += ["<details><summary>Power Query</summary>", "", "```powerquery", t.m_vyraz, "```", "</details>", ""]
    md += ["## Vztahy", "", "| Z (mnoho) | Do (jedna) | Poznámka |", "|---|---|---|"]
    md += [f"| {v.z} | {v.do} | {'neaktivní ' if not v.aktivni else ''}{'obousměrný ' if v.smer == 'bothDirections' else ''}"
           f"{'mnoho:mnoho ' if v.kardinalita_do == 'many' else ''}{'RLS oběma směry' if v.bezpecnost == 'bothDirections' else ''} |"
           for v in p.vztahy]
    if p.role:
        md += ["", "## Role (zabezpečení)", ""]
        for r in p.role:
            md += [f"### {r.nazev} ({r.opravneni})", ""]
            md += [f"- filtr řádků na **{t}**: `{d.replace(chr(10), ' ')}`" for t, d in r.filtry.items()]
            md += [f"- OLS skrývá tabulku {t}" for t in sorted(r.ols_tabulky)]
            md += [f"- OLS skrývá sloupec {t}[{c}]" for t, c in sorted(r.ols_sloupce)]
            if not r.filtry and not r.ols_tabulky and not r.ols_sloupce:
                md.append("- bez omezení")
            md.append("")
    md += ["", "## Stránky reportu", ""]
    for s in p.stranky:
        vv = [v for v in p.vizualy if v.stranka == s.nazev and not v.skryty and v.pole()]
        md += [f"### {s.zobrazeny}{' (skrytá)' if s.skryta else ''}", ""]
        for v in vv:
            pole = ", ".join(sorted(f"{t}[{c}]" for t, c in v.pole()))
            md.append(f"- {v.typ}{f' „{v.titulek}“' if v.titulek else ''}: {pole}")
        md.append("")
    out = Path(a.vystup)
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"model_{p.nazev}.md"
    f.write_text("\n".join(md), encoding="utf-8")
    print(f"-> {f} ({f.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
