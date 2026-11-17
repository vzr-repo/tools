"""Porovnání dvou stavů reportu (před / po úpravách, nebo dva různé reporty): skóre AI, počty nálezů podle kontrol,
vyřešené a nové nálezy -> Markdown.

    python porovnej.py <před: .pbip | složka> <po: .pbip | složka> [--vystup slozka] [--lang en]

Typicky: zkopíruj projekt (nebo použij git worktree / starší commit), uprav, porovnej. Nálezy se párují podle
kódu kontroly a objektu – po přejmenování se objekt počítá jako vyřešený + nový; počty podle kódů platí vždy.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import jazyk
from audit import VAHY_AI, _jazyk_z_argv, skore_ai
from jazyk import SKORE, UROVEN, L
from kontroly import NADPISY, spust
from pbip import Projekt

POPIS_EN = """Compare two states of a report (before / after changes, or two different reports): AI score, findings per check,
resolved and new findings -> Markdown.

    python porovnej.py <before: .pbip | folder> <after: .pbip | folder> [--output folder] --lang en

Typically: copy the project (or use a git worktree / an older commit), change it, compare. Findings are matched by
check code and object – after a rename the object counts as resolved + new; counts per check always hold.
"""


def stav(cesta):
    p = Projekt(cesta)
    nalezy = spust(p)
    return p, nalezy, skore_ai(p)


def main():
    _jazyk_z_argv(sys.argv[1:])
    ap = argparse.ArgumentParser(description=L(__doc__, POPIS_EN), formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pred", metavar=L("pred", "before"))
    ap.add_argument("po", metavar=L("po", "after"))
    ap.add_argument(*jazyk.volby("--vystup", "--output"), dest="vystup", default=".", metavar=L("SLOZKA", "FOLDER"), help=L("složka pro výstup", "output folder"))
    ap.add_argument(*jazyk.volby("--jazyk", "--lang"), dest="lang", choices=["cs", "en"], help=L("jazyk výstupů (výchozí cs)", "output language (default cs)"))
    a = ap.parse_args()
    jazyk.nastav(a.lang)
    (pa, na, sa), (pb, nb, sb) = stav(a.pred), stav(a.po)

    def zn(d):
        return f"+{d}" if d > 0 else str(d)
    md = [L(f"# Porovnání: {pa.nazev} → {pb.nazev}", f"# Comparison: {pa.nazev} → {pb.nazev}"), "",
          L(f"## Skóre AI: {sa['skore']} → {sb['skore']} ({zn(sb['skore'] - sa['skore'])})",
            f"## AI score: {sa['skore']} → {sb['skore']} ({zn(sb['skore'] - sa['skore'])})"), "",
          L("| Složka | Váha | Před | Po | Rozdíl |", "| Component | Weight | Before | After | Change |"), "|---|---|---|---|---|"]
    md += [f"| {SKORE[k]} | {round(VAHY_AI[k] * 100)} % | {sa[k]} | {sb[k]} | {zn(sb[k] - sa[k])} |" for k in VAHY_AI]
    ua, ub = Counter(n.uroven for n in na), Counter(n.uroven for n in nb)
    md += ["", L("## Nálezy", "## Findings"), "", L("| Úroveň | Před | Po | Rozdíl |", "| Level | Before | After | Change |"), "|---|---|---|---|"]
    md += [f"| {u if not jazyk.en() else UROVEN[u]} | {ua[u]} | {ub[u]} | {zn(ub[u] - ua[u])} |" for u in ("chyba", "varovani", "info")]
    md += ["", L(f"Model: {len(pa.tabulky)} → {len(pb.tabulky)} tabulek · {len(pa.miry)} → {len(pb.miry)} měr · "
                 f"{sum(not s.skryty for s in pa.sloupce)} → {sum(not s.skryty for s in pb.sloupce)} viditelných sloupců · "
                 f"{len({m.slozka for m in pa.miry if m.slozka})} → {len({m.slozka for m in pb.miry if m.slozka})} složek měr",
                 f"Model: {len(pa.tabulky)} → {len(pb.tabulky)} tables · {len(pa.miry)} → {len(pb.miry)} measures · "
                 f"{sum(not s.skryty for s in pa.sloupce)} → {sum(not s.skryty for s in pb.sloupce)} visible columns · "
                 f"{len({m.slozka for m in pa.miry if m.slozka})} → {len({m.slozka for m in pb.miry if m.slozka})} measure folders"), ""]
    ka, kb = Counter(n.kod for n in na), Counter(n.kod for n in nb)
    md += [L("## Podle kontrol", "## By check"), "", L("| Kód | Kontrola | Před | Po | Rozdíl |", "| Code | Check | Before | After | Change |"),
           "|---|---|---|---|---|"]
    for kod in sorted(set(ka) | set(kb)):
        if ka[kod] != kb[kod] or ka[kod]:
            md.append(f"| {kod} | {NADPISY.get(kod, '')} | {ka[kod]} | {kb[kod]} | {zn(kb[kod] - ka[kod])} |")
    klic = {n.id for n in na}, {n.id for n in nb}
    for nadpis, mnozina, nalezy in ((L("Nové chyby a varování", "New errors and warnings"), klic[1] - klic[0], nb),
                                    (L("Vyřešené chyby a varování", "Resolved errors and warnings"), klic[0] - klic[1], na)):
        vyber = [n for n in nalezy if n.id in mnozina and n.uroven != "info"]
        md += ["", f"## {nadpis} ({len(vyber)})", ""]
        md += [f"- {n.kod} {n.popis} – `{n.objekt}`" for n in sorted(vyber, key=lambda n: (n.kod, jazyk.cesky(n.objekt)))[:60]]
        if len(vyber) > 60:
            md.append(L(f"- … a dalších {len(vyber) - 60}", f"- … and {len(vyber) - 60} more"))
        if not vyber:
            md.append(L("Žádné.", "None."))
    out = Path(a.vystup)
    out.mkdir(parents=True, exist_ok=True)
    f = out / (L("porovnani_", "comparison_") + f"{pa.nazev}_{pb.nazev}.md")
    f.write_text("\n".join(md), encoding="utf-8")
    print(L(f"Skóre AI {sa['skore']} → {sb['skore']}; chyby {ua['chyba']} → {ub['chyba']}, varování {ua['varovani']} → {ub['varovani']}",
            f"AI score {sa['skore']} → {sb['skore']}; errors {ua['chyba']} → {ub['chyba']}, warnings {ua['varovani']} → {ub['varovani']}"))
    print(f"-> {f}")


if __name__ == "__main__":
    main()
