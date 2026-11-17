"""Audit Power BI projektu PBIP: kontroly modelu, reportu a připravenosti pro AI -> Markdown + CSV.

    python audit.py <report.pbip | složka *.Report | složka projektu> [--vystup slozka] [--bez-info]
    python audit.py <složka> --vse        # všechny reporty ve složce a podsložkách (každý zvlášť + souhrn)
    python audit.py <projekt> --nastaveni klient.json --baseline audit/audit_X.csv --fail-on chyba   # CI / opakovaný audit

Výstup: audit_<nazev>.md (souhrn, skóre AI připravenosti, nálezy podle oblastí) a audit_<nazev>.csv (všechny nálezy, se
stabilním id).

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

from kontroly import NADPISY, Nalez, spust
from pbip import Projekt, _jmeno, _rozdel_odkaz, najdi_reporty

UROVNE = {"chyba": "🔴 chyba", "varovani": "🟠 varování", "info": "⚪ info"}


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
        problemy.append(f"Model ({p.format_modelu or '?'}) nemá žádnou tabulku.")
    elif not p.sloupce:
        problemy.append(f"Načteno {len(p.tabulky)} tabulek, ale 0 sloupců.")
    sloupce = {(s.tabulka, s.nazev) for s in p.sloupce}
    konce = [(_jmeno(_rozdel_odkaz(x)[0]), _rozdel_odkaz(x)[1]) for v in p.vztahy for x in (v.z, v.do)]
    chybi = [k for k in konce if k not in sloupce]
    if len(p.vztahy) >= 3 and len(chybi) > len(konce) / 2:
        problemy.append(f"{len(chybi)} z {len(konce)} konců vztahů v načtených sloupcích chybí (např. {chybi[0][0]}[{chybi[0][1]}]).")
    return problemy


def nacti_nastaveni(cesta) -> dict:
    if not cesta:
        return {}
    d = json.loads(Path(cesta).read_text(encoding="utf-8-sig"))
    for v in d.get("vyjimky", []):
        if not v.get("duvod"):
            raise ValueError(f"Výjimka bez důvodu v {cesta}: {v} – každá výjimka musí mít „duvod“.")
    return d


def je_vyjimka(n: Nalez, vyjimky: list[dict]) -> bool:
    """Výjimka: {"id": "…"} nebo {"kod": "M21", "objekt": "Kurzy*"} (objekt = vzor se * a ?), vždy s „duvod“."""
    for v in vyjimky:
        if "id" in v and v["id"] == n.id:
            return True
        if "kod" in v and v["kod"] == n.kod and fnmatchcase(n.objekt, v.get("objekt", "*")):
            return True
    return False


def nacti_baseline(cesta) -> set[str]:
    """Id nálezů z dřívějšího CSV. Starší CSV bez sloupce id – id se dopočítá z kódu, objektu a popisu."""
    with open(cesta, newline="", encoding="utf-8-sig") as f:
        return {r.get("id") or Nalez(r["kod"], r["uroven"], r["oblast"], r["objekt"], r["popis"]).id
                for r in csv.DictReader(f, delimiter=";")}


def exit_kod(pocty: Counter, fail_on: str) -> int:
    if pocty["chyba"] and fail_on in ("chyba", "varovani"):
        return 2
    if pocty["varovani"] and fail_on == "varovani":
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projekt")
    ap.add_argument("--vystup", default=".")
    ap.add_argument("--bez-info", action="store_true", help="vynechat nálezy úrovně info")
    ap.add_argument("--vse", action="store_true", help="auditovat všechny reporty ve složce")
    ap.add_argument("--nastaveni", help="JSON klienta: terminy, rodiny, vyjimky")
    ap.add_argument("--baseline", help="CSV z předchozího auditu – porovnat nové / vyřešené nálezy")
    ap.add_argument("--fail-on", choices=["nic", "chyba", "varovani"], default="nic", help="kdy vrátit nenulový exit kód")
    a = ap.parse_args()
    try:
        a.nastaveni_data = nacti_nastaveni(a.nastaveni)
    except (OSError, ValueError) as e:
        print(f"CHYBA nastavení: {e}")
        sys.exit(3)
    cesty = najdi_reporty(a.projekt) if a.vse else [a.projekt]
    souhrn, kody = [], []
    for c in cesty:
        try:
            *radek, kod = audituj(Projekt(c), a)
            souhrn.append(tuple(radek)); kody.append(kod)
        except Exception as e:  # noqa: BLE001 – jeden rozbitý report nesmí zastavit dávku
            print(f"CHYBA {c}: {e}")
            souhrn.append((str(c), "nelze načíst", str(e))); kody.append(3)
    if a.vse:
        radky = ["# Souhrn auditu", "", "| Report | Formát | Výsledek |", "|---|---|---|"] + [f"| {r} | {f} | {v} |" for r, f, v in souhrn]
        (Path(a.vystup) / "audit_souhrn.md").write_text(chr(10).join(radky), encoding="utf-8")
        print(f"Souhrn {len(souhrn)} reportů -> {Path(a.vystup) / 'audit_souhrn.md'}")
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
    nalezy.sort(key=lambda n: (poradi[n.uroven], n.kod, n.objekt))
    out = Path(a.vystup)
    out.mkdir(parents=True, exist_ok=True)

    with open(out / f"audit_{p.nazev}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["kod", "uroven", "oblast", "objekt", "popis", "doporuceni", "id"])
        w.writerows([(n.kod, n.uroven, n.oblast, n.objekt, n.popis, n.doporuceni, n.id) for n in nalezy])

    sk = skore_ai(p)
    pocty = Counter(n.uroven for n in nalezy)
    md = [f"# Audit reportu {p.nazev}", "", f"Datum: {date.today():%d. %m. %Y} · nástroj: pbip_audit (github.com/vzr-repo/tools)", "",
          "## Souhrn", "",
          f"- Formát: report {p.format_reportu}, model {p.format_modelu}",
          f"- Stránky: {len(p.stranky)} · vizuály: {len(p.vizualy)} (skryté {sum(v.skryty for v in p.vizualy)}) · záložky: {len(p.zalozky)}",
          f"- Model: {len(p.tabulky)} tabulek · {len(p.sloupce)} sloupců · {len(p.miry)} měr · {len(p.vztahy)} vztahů · "
          f"{len(p.role)} rolí (RLS/OLS)",
          f"- Nálezy: {pocty['chyba']} chyb · {pocty['varovani']} varování · {pocty['info']} info"
          + (f" · {potlacene} potlačeno výjimkou" if potlacene else ""), ""]
    if problemy:
        md += ["## ⚠️ Model se nenačetl správně", "", "Výsledky auditu modelu nejsou spolehlivé (exit kód 3):", ""] + \
              [f"- {x}" for x in problemy] + ["", "Ověř formát projektu (TMDL / model.bim) a pošli ukázku souboru k opravě parseru.", ""]
    zmeny = None
    if stare is not None:
        dulezite = [n for n in nalezy if n.uroven != "info"]
        nove = [n for n in dulezite if n.id not in stare]
        vyresene = len(stare - {n.id for n in nalezy})
        zmeny = (len(nove), vyresene)
        md += [f"## Proti baseline ({Path(baseline).name})", "", f"- Nové chyby a varování: {len(nove)}",
               f"- Vyřešené nálezy (všech úrovní): {vyresene}", ""]
        md += [f"  - {n.kod} {n.popis} – `{n.objekt}`" for n in nove[:30]] + (["  - …"] if len(nove) > 30 else [])
        md += [""]
    md += [
          f"## Připravenost pro AI: {sk['skore']} / 100", "",
          "| Složka | % | Váha |", "|---|---|---|"] + [f"| {k} | {v} | {round(VAHY_AI[k] * 100)} % |" for k, v in sk.items() if k != "skore"] + [
          "", "AI (Copilot, agenti nad modelem) čte názvy a popisy tabulek, sloupců a měr. Čím víc popisů a méně technického šumu,",
          "tím přesnější odpovědi.", ""]
    for oblast, nazev in (("model", "Model"), ("report", "Report"), ("ai", "Připravenost pro AI"), ("rls", "Zabezpečení (RLS / OLS)")):
        if oblast == "rls" and not p.role:
            md += ["## Zabezpečení (RLS / OLS)", "", "Model nemá žádné role – RLS se nekontroluje.", ""]
            continue
        sk_n = [n for n in nalezy if n.oblast == oblast]
        md += [f"## {nazev} ({len(sk_n)})", ""]
        if not sk_n:
            md += ["Bez nálezů.", ""]
            continue
        for kod in dict.fromkeys(n.kod for n in sk_n):
            skupina = [n for n in sk_n if n.kod == kod]
            md += [f"### {kod} · {UROVNE[skupina[0].uroven]} · {NADPISY.get(kod, skupina[0].popis)} ({len(skupina)}×)",
                   "", f"Doporučení: {skupina[0].doporuceni}", ""]
            md += [f"- {n.popis} – `{n.objekt}`" for n in skupina[:25]]
            if len(skupina) > 25:
                md.append(f"- … a dalších {len(skupina) - 25} (viz CSV)")
            md.append("")
    (out / f"audit_{p.nazev}.md").write_text("\n".join(md), encoding="utf-8")
    kod = 3 if problemy else exit_kod(pocty, getattr(a, "fail_on", "nic"))
    print(f"Audit {p.nazev}: {pocty['chyba']} chyb, {pocty['varovani']} varování, {pocty['info']} info; AI skóre {sk['skore']}/100"
          + (f"; baseline: +{zmeny[0]} nových, {zmeny[1]} vyřešených" if zmeny else "")
          + (f"; POZOR model se nenačetl správně: {problemy[0]}" if problemy else ""))
    print(f"-> {out / f'audit_{p.nazev}.md'}")
    return (p.nazev, f"{p.format_reportu} / {p.format_modelu}",
            f"{pocty['chyba']} chyb, {pocty['varovani']} varování, AI {sk['skore']}/100" + (" · ⚠️ parser" if problemy else ""), kod)


if __name__ == "__main__":
    main()
