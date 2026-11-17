"""Porovnání dvou stavů reportu (před / po úpravách, nebo dva různé reporty): skóre AI, počty nálezů podle kontrol,
vyřešené a nové nálezy -> Markdown.

    python porovnej.py <před: .pbip | složka> <po: .pbip | složka> [--vystup slozka]

Typicky: zkopíruj projekt (nebo použij git worktree / starší commit), uprav, porovnej. Nálezy se párují podle
kódu kontroly a objektu – po přejmenování se objekt počítá jako vyřešený + nový; počty podle kódů platí vždy.
"""
import argparse
from collections import Counter
from pathlib import Path

from audit import VAHY_AI, skore_ai
from kontroly import NADPISY, spust
from pbip import Projekt


def stav(cesta):
    p = Projekt(cesta)
    nalezy = spust(p)
    return p, nalezy, skore_ai(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pred")
    ap.add_argument("po")
    ap.add_argument("--vystup", default=".")
    a = ap.parse_args()
    (pa, na, sa), (pb, nb, sb) = stav(a.pred), stav(a.po)

    def zn(d):
        return f"+{d}" if d > 0 else str(d)
    md = [f"# Porovnání: {pa.nazev} → {pb.nazev}", "",
          f"## Skóre AI: {sa['skore']} → {sb['skore']} ({zn(sb['skore'] - sa['skore'])})", "",
          "| Složka | Váha | Před | Po | Rozdíl |", "|---|---|---|---|---|"]
    md += [f"| {k} | {round(VAHY_AI[k] * 100)} % | {sa[k]} | {sb[k]} | {zn(sb[k] - sa[k])} |" for k in VAHY_AI]
    ua, ub = Counter(n.uroven for n in na), Counter(n.uroven for n in nb)
    md += ["", "## Nálezy", "", "| Úroveň | Před | Po | Rozdíl |", "|---|---|---|---|"]
    md += [f"| {u} | {ua[u]} | {ub[u]} | {zn(ub[u] - ua[u])} |" for u in ("chyba", "varovani", "info")]
    md += ["", f"Model: {len(pa.tabulky)} → {len(pb.tabulky)} tabulek · {len(pa.miry)} → {len(pb.miry)} měr · "
           f"{sum(not s.skryty for s in pa.sloupce)} → {sum(not s.skryty for s in pb.sloupce)} viditelných sloupců · "
           f"{len({m.slozka for m in pa.miry if m.slozka})} → {len({m.slozka for m in pb.miry if m.slozka})} složek měr", ""]
    ka, kb = Counter(n.kod for n in na), Counter(n.kod for n in nb)
    md += ["## Podle kontrol", "", "| Kód | Kontrola | Před | Po | Rozdíl |", "|---|---|---|---|---|"]
    for kod in sorted(set(ka) | set(kb)):
        if ka[kod] != kb[kod] or ka[kod]:
            md.append(f"| {kod} | {NADPISY.get(kod, '')} | {ka[kod]} | {kb[kod]} | {zn(kb[kod] - ka[kod])} |")
    klic = {(n.kod, n.objekt, n.popis) for n in na}, {(n.kod, n.objekt, n.popis) for n in nb}
    for nadpis, mnozina, nalezy in (("Nové chyby a varování", klic[1] - klic[0], nb), ("Vyřešené chyby a varování", klic[0] - klic[1], na)):
        vyber = [n for n in nalezy if (n.kod, n.objekt, n.popis) in mnozina and n.uroven != "info"]
        md += ["", f"## {nadpis} ({len(vyber)})", ""]
        md += [f"- {n.kod} {n.popis} – `{n.objekt}`" for n in sorted(vyber, key=lambda n: (n.kod, n.objekt))[:60]]
        if len(vyber) > 60:
            md.append(f"- … a dalších {len(vyber) - 60}")
        if not vyber:
            md.append("Žádné.")
    out = Path(a.vystup)
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"porovnani_{pa.nazev}_{pb.nazev}.md"
    f.write_text("\n".join(md), encoding="utf-8")
    print(f"Skóre AI {sa['skore']} → {sb['skore']}; chyby {ua['chyba']} → {ub['chyba']}, varování {ua['varovani']} → {ub['varovani']}")
    print(f"-> {f}")


if __name__ == "__main__":
    main()
