"""Hromadné opravy modelu TMDL podle schváleného návrhu (CSV): popisy, skrytí polí, složky měr, formáty.

    python oprav.py <projekt> --sablona navrh.csv      # 1) vygeneruj návrh z nálezů auditu (prázdné popisy, pole ke skrytí …)
    (doplň sloupec „hodnota“ – ručně nebo nech AI; řádky s prázdnou hodnotou se přeskočí)
    python oprav.py <projekt> navrh.csv                # 2) náhled: co se změní (nic nezapíše)
    python oprav.py <projekt> navrh.csv --zapsat       # 3) zápis do souborů *.tmdl

CSV (oddělovač ;, UTF-8): objekt;typ;akce;hodnota;nalez;kontext
- objekt: Tabulka  nebo  Tabulka[Sloupec / Míra]
- typ: tabulka / sloupec / mira (prázdné = dohledá se)
- akce: popis (/// nad objektem) · skryt (isHidden; hodnota ano/ne) · slozka (displayFolder) · format (formatString)
        · dax (nový výraz míry; v šabloně předvyplněný jen přesný přepis, úpravy k ověření jsou ve sloupci kontext)
Jen model TMDL (*.SemanticModel/definition/tables). Před zápisem měj projekt v gitu nebo zálohu a v Power BI Desktopu
ho zavři – Desktop při uložení soubory přepíše.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import re
import sys
from pathlib import Path

from kontroly import spust
from pbip import Projekt, _odsazeni, _rozdel_deklaraci, _jmeno

POLE = ["objekt", "typ", "akce", "hodnota", "nalez", "kontext"]
VLASTNOST = {"skryt": "isHidden", "slozka": "displayFolder", "format": "formatString"}
AKCE = ("popis", "dax", *VLASTNOST)


# ------------------------------------------------------------------ šablona
def sablona(p: Projekt, soubor: Path):
    miry = {f"{m.tabulka}[{m.nazev}]": m for m in p.miry}
    sloupce = {s.plny: s for s in p.sloupce}
    radky, videno = [], set()

    def pridej(objekt, typ, akce, hodnota, nalez, kontext=""):
        if (objekt, akce) not in videno:
            videno.add((objekt, akce))
            radky.append([objekt, typ, akce, hodnota, nalez, kontext.replace("\n", " ")[:300]])
    for n in spust(p):
        if n.kod == "M01":
            m = miry.get(n.objekt.replace("[", "[", 1))
            pridej(n.objekt, "mira", "popis", "", "M01", f"DAX: {m.dax}" if m else "")
        elif n.kod == "M03":
            pridej(n.objekt, "tabulka", "popis", "", "M03", "")
        elif n.kod == "M02":
            s = sloupce.get(n.objekt)
            pridej(n.objekt, "sloupec", "popis", "", "M02", f"typ {s.typ}" if s else "")
        elif n.kod in ("M05", "M06") and n.objekt in sloupce:
            pridej(n.objekt, "sloupec", "skryt", "ano", n.kod, n.popis)
        elif n.kod == "M16":
            pridej(n.objekt, "mira", "format", "0.0%", "M16", "")
        elif n.kod == "M04":
            pridej(n.objekt, "mira", "format", "", "M04", f"DAX: {miry[n.objekt].dax}" if n.objekt in miry else "")
        elif n.kod == "M14":
            for m in p.miry:
                if m.tabulka == n.objekt and not m.slozka and not m.skryta:
                    pridej(f"{m.tabulka}[{m.nazev}]", "mira", "slozka", "", "M14", f"DAX: {m.dax}")
    from audit import dax_navrhy
    for x in dax_navrhy(p, [n for n in spust(p) if n.oblast == "dax"]):
        if x["presny"]:
            pozn = f"PŘESNÉ ({', '.join(x['kody_presne'])}) – stejný výsledek" + \
                (" (u dělení nulou prázdno místo chyby)" if "D02" in x["kody_presne"] else "")
            if x["vse"]:
                pozn += f" | K OVĚŘENÍ ({', '.join(x['kody_vse'])}): {x['vse']}"
            radky.append([x["objekt"], "mira", "dax", x["presny"], "D", pozn])
        elif x["vse"]:
            radky.append([x["objekt"], "mira", "dax", "", "D",
                          f"K OVĚŘENÍ ({', '.join(x['kody_vse'])}) – po kontrole zkopíruj do hodnota: {x['vse']}"])
    with open(soubor, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(POLE)
        w.writerows(radky)
    print(f"Šablona: {len(radky)} řádků -> {soubor}")
    print("Doplň „hodnota“ (popis / složka / formát; u skrytí ano/ne), prázdné řádky se přeskočí. Pak: oprav.py <projekt> návrh.csv")


# ------------------------------------------------------------------ úpravy TMDL
PORADI = ["dataType", "isHidden", "formatString", "displayFolder", "lineageTag"]


def _poradi(radek: str) -> int:
    k = radek.split(":", 1)[0].strip()
    return PORADI.index(k) if k in PORADI else len(PORADI)


class Soubor:
    """Text souboru TMDL s uchováním BOM a konců řádků."""
    def __init__(self, cesta: Path):
        self.cesta = cesta
        surove = cesta.read_bytes()
        self.bom = surove.startswith(b"\xef\xbb\xbf")
        text = surove.decode("utf-8-sig")
        self.eol = "\r\n" if "\r\n" in text else "\n"
        self.konec = text.endswith(("\n", "\r\n"))
        self.puvodni = text.splitlines()
        self.radky = list(self.puvodni)

    def text(self, radky=None) -> str:
        return self.eol.join(self.radky if radky is None else radky) + (self.eol if self.konec else "")

    def uloz(self):
        self.cesta.write_bytes((b"\xef\xbb\xbf" if self.bom else b"") + self.text().encode("utf-8"))

    def najdi(self, typ: str, nazev: str) -> int:
        for i, r in enumerate(self.radky):
            s, o = r.strip(), _odsazeni(r)
            if typ == "tabulka" and o == 0 and s.startswith("table ") and _jmeno(s[6:]) == nazev:
                return i
            klic = {"mira": "measure ", "sloupec": "column "}.get(typ)
            if klic and o == 1 and s.startswith(klic) and _rozdel_deklaraci(s[len(klic):])[0] == nazev:
                return i
        raise KeyError(f"{typ} {nazev} nenalezen v {self.cesta.name}")

    def popis(self, typ, nazev, text):
        i = self.najdi(typ, nazev)
        o = _odsazeni(self.radky[i])
        z = i
        while z > 0 and self.radky[z - 1].strip().startswith("///"):
            z -= 1
        radky = [o * "\t" + "/// " + r.strip() for r in text.strip().splitlines() if r.strip()]
        self.radky[z:i] = radky

    def vyraz(self, nazev, novy: str):
        """Nahradí výraz míry: jednořádkový za „=“, víceřádkový jako pokračovací řádky odsazené o 2 úrovně."""
        i = self.najdi("mira", nazev)
        o = _odsazeni(self.radky[i])
        hlavicka = re.match(r"\s*measure\s+(?:'(?:[^']|'')*'|[^\s=]+)", self.radky[i]).group(0)
        j, v_blok = i + 1, self.radky[i].rstrip().endswith("```")
        while j < len(self.radky):                                       # konec starého výrazu
            r, oo = self.radky[j], _odsazeni(self.radky[j])
            if v_blok:
                j += 1
                if r.strip() == "```":
                    break
                continue
            if r.strip() and oo <= o + 1:
                break
            if not r.strip():                                            # prázdný řádek: patří k výrazu, jen když za ním výraz pokračuje
                k = j
                while k < len(self.radky) and not self.radky[k].strip():
                    k += 1
                if k >= len(self.radky) or _odsazeni(self.radky[k]) <= o + 1:
                    break
            j += 1
        radky = [r.rstrip() for r in novy.strip("\n").splitlines()]
        if len(radky) == 1:
            nove = [f"{hlavicka} = {radky[0].strip()}"]
        else:
            nove = [f"{hlavicka} ="] + [(o + 2) * "\t" + r if r.strip() else "" for r in radky]
        self.radky[i:j] = nove

    def vlastnost(self, typ, nazev, klic, hodnota):
        """hodnota None = odstranit, True = příznak bez hodnoty (isHidden), jinak „klic: hodnota“."""
        i = self.najdi(typ, nazev)
        o = _odsazeni(self.radky[i]) + 1
        j, prvni, posledni_vyraz, posledni, pred = i + 1, None, i, None, None
        while j < len(self.radky) and (not self.radky[j].strip() or _odsazeni(self.radky[j]) >= o):
            r, oo = self.radky[j].strip(), _odsazeni(self.radky[j])
            if r and oo == o:
                if typ == "tabulka" and r.split(" ", 1)[0] in ("measure", "column", "partition", "hierarchy", "calculationGroup"):
                    break                                                   # konec vlastností tabulky
                if r == klic or r.split(":", 1)[0].strip() == klic:
                    if hodnota is None:
                        del self.radky[j]
                    else:
                        self.radky[j] = o * "\t" + (klic if hodnota is True else f"{klic}: {hodnota}")
                    return
                prvni = j if prvni is None else prvni
                posledni = j
                if pred is None and _poradi(r) > _poradi(klic):
                    pred = j                                                # pořadí jako při uložení z Desktopu
            elif r and prvni is None:
                posledni_vyraz = j                                          # pokračování výrazu nad vlastnostmi
            j += 1
        if hodnota is None:
            return
        kam = pred if pred is not None else (posledni + 1 if posledni is not None else posledni_vyraz + 1)
        self.radky.insert(kam, o * "\t" + (klic if hodnota is True else f"{klic}: {hodnota}"))


def nacti_navrh(soubor: Path) -> list[dict]:
    with open(soubor, newline="", encoding="utf-8-sig") as f:
        prvni = f.readline(); f.seek(0)
        return list(csv.DictReader(f, delimiter=";" if prvni.count(";") >= prvni.count(",") else ","))


def proved(p: Projekt, navrh: list[dict], zapsat: bool) -> int:
    if p.format_modelu != "TMDL":
        sys.exit(f"Opravy umí jen model TMDL (tento: {p.format_modelu}). V Desktopu: Soubor → Možnosti → Funkce verze Preview → TMDL.")
    tabulky = {t.nazev: t for t in p.tabulky}
    miry = {(m.tabulka, m.nazev) for m in p.miry}
    sloupce = {(s.tabulka, s.nazev) for s in p.sloupce}
    soubory, chyby, pocet = {}, [], 0
    for r in navrh:
        objekt, akce, hodnota = r.get("objekt", "").strip(), r.get("akce", "").strip().lower(), (r.get("hodnota") or "").strip()
        if not objekt or not akce or not hodnota:
            continue
        tab, _, pole = objekt.partition("[")
        tab, pole = tab.strip().strip("'"), pole.rstrip("]")
        typ = (r.get("typ") or "").strip().lower() or ("tabulka" if not pole else "mira" if (tab, pole) in miry else "sloupec")
        if tab not in tabulky or (typ == "mira" and (tab, pole) not in miry) or (typ == "sloupec" and (tab, pole) not in sloupce):
            chyby.append(f"{objekt}: objekt v modelu není"); continue
        if akce not in AKCE:
            chyby.append(f"{objekt}: neznámá akce „{akce}“"); continue
        if akce == "slozka" and typ == "tabulka":
            chyby.append(f"{objekt}: složka jde jen u míry / sloupce"); continue
        if akce == "dax" and typ != "mira":
            chyby.append(f"{objekt}: akce dax jde jen u míry"); continue
        f = tabulky[tab].soubor
        s = soubory.setdefault(f, Soubor(f))
        nazev = tab if typ == "tabulka" else pole
        try:
            if akce == "popis":
                s.popis(typ, nazev, hodnota)
            elif akce == "dax":
                s.vyraz(nazev, (r.get("hodnota") or "").strip("\r\n"))
            elif akce == "skryt":
                s.vlastnost(typ, nazev, "isHidden", True if hodnota.lower() in ("ano", "a", "yes", "y", "1", "true") else None)
            else:
                s.vlastnost(typ, nazev, VLASTNOST[akce], hodnota)
            pocet += 1
        except KeyError as e:
            chyby.append(str(e))
    zmenene = [s for s in soubory.values() if s.radky != s.puvodni]
    for s in zmenene:
        diff = list(difflib.unified_diff(s.puvodni, s.radky, s.cesta.name, s.cesta.name, n=1, lineterm=""))
        print("\n".join(diff[:80]) + ("\n…" if len(diff) > 80 else ""))
    for c in chyby:
        print(f"PŘESKOČENO {c}")
    if zapsat:
        for s in zmenene:
            s.uloz()
        kontrola = Projekt(p.report_dir)                                     # znovu načíst – nic se nesmí ztratit
        if (len(kontrola.tabulky), len(kontrola.sloupce), len(kontrola.miry)) != (len(p.tabulky), len(p.sloupce), len(p.miry)):
            print("POZOR: po zápisu nesedí počty objektů – zkontroluj git diff!")
        print(f"Zapsáno: {pocet} úprav v {len(zmenene)} souborech. Otevři projekt v Desktopu a spusť znovu audit.")
    else:
        print(f"Náhled: {pocet} úprav v {len(zmenene)} souborech. Nic se nezapsalo – pro zápis přidej --zapsat.")
    return pocet


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projekt")
    ap.add_argument("navrh", nargs="?", help="CSV se schválenými úpravami")
    ap.add_argument("--sablona", metavar="CSV", help="vygenerovat návrh z nálezů auditu")
    ap.add_argument("--zapsat", action="store_true", help="opravdu zapsat (jinak jen náhled)")
    a = ap.parse_args()
    p = Projekt(a.projekt)
    if a.sablona:
        sablona(p, Path(a.sablona))
    elif a.navrh:
        proved(p, nacti_navrh(Path(a.navrh)), a.zapsat)
    else:
        ap.error("zadej návrh CSV, nebo --sablona soubor.csv")


if __name__ == "__main__":
    main()
