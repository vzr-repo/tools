"""Kontroly reportu a modelu. Každá kontrola je funkce `def kontrola(p: Projekt) -> list[Nalez]` registrovaná dekorátorem
@kontrola – nová kontrola = nová funkce, nic dalšího se nemění.

Úrovně: chyba (rozbité / bude se chovat špatně), varovani (zhoršuje použitelnost nebo výkon), info (ke zvážení).
Oblasti: model, report, ai (připravenost pro Copilot / AI agenty – popisy, srozumitelné názvy, méně šumu),
rls (zabezpečení na úrovni řádků a objektů – jestli filtry rolí dojdou ke všem datům a nic se nerozbije).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import dax as daxlib
from pbip import Projekt, _jmeno, _rozdel_odkaz, dax_odkazy

KONTROLY = []
NADPISY = {
    "M01": "Míry bez popisu", "M02": "Viditelné sloupce bez popisu", "M03": "Tabulky bez popisu", "M04": "Míry bez formátu čísla",
    "M05": "Nepoužitá pole", "M06": "Viditelné technické sloupce", "M07": "Automatické datum a čas", "M08": "Obousměrné a neaktivní vztahy",
    "M09": "Technické názvy", "M10": "Kolize názvů", "M11": "Rozbité odkazy v DAX", "R01": "Datové vizuály bez titulku",
    "R02": "Barvy mimo theme", "R03": "Skryté stránky", "R04": "Vizuály mimo plátno", "R05": "Překrývající se vizuály",
    "R06": "Výkon stránek a vizuálů", "R08": "Slicery s uloženým výběrem", "R09": "Záložky měnící filtry",
    "R10": "Vizuály bez alternativního textu", "R11": "Vizuály s neexistujícím polem", "R12": "Bez vlastního theme",
    "R13": "Osiřelé formátování", "M12": "Chybí označená tabulka kalendáře", "M13": "Generické a verzované názvy",
    "M14": "Míry bez složek (display folder)", "M15": "Tabulky bez vztahu", "M16": "Procentní míry bez formátu %",
    "M17": "Duplicitní míry", "M18": "Vztahy mnoho:mnoho", "M19": "Počítané sloupce na faktové tabulce",
    "R14": "Slicer z tabulky bez vztahu",
    "S01": "Rozbitý filtr role", "S02": "Filtr role nedojde ke všem datům", "S03": "Bezpečnostní filtr oběma směry",
    "S04": "Role bez filtru", "S05": "OLS skrývá použité pole", "S06": "USERNAME místo USERPRINCIPALNAME",
    "S07": "RLS filtr na faktové tabulce", "S08": "Dimenze mimo dosah filtru role",
    "M20": "Různé datové typy na koncích vztahu", "M21": "Textový klíč ve vztahu", "M22": "Cyklická závislost měr",
    "M23": "Nejednotné termíny (glosář)", "M24": "Neúplná rodina měr",
    "D01": "FILTER jako filtr CALCULATE", "D02": "Dělení bez DIVIDE", "D03": "Iterátor přes jediný sloupec",
    "D04": "COUNTROWS ( FILTER … )", "D05": "Zbytečný CALCULATE", "D06": "Vnořené IF", "D07": "Opakovaný výpočet míry",
    "D08": "Filtr CALCULATE bez sloupce", "D09": "EARLIER v míře", "D10": "USERELATIONSHIP bez vztahu",
    "D11": "Časová funkce nad datem z faktu", "D12": "Složité míry", "D13": "Kvalifikace odkazů",
}
DATOVE_VIZUALY = {"barChart", "clusteredBarChart", "columnChart", "clusteredColumnChart", "lineChart", "areaChart", "pieChart",
                  "donutChart", "tableEx", "pivotTable", "map", "azureMap", "filledMap", "scatterChart", "funnel", "waterfallChart",
                  "lineClusteredColumnComboChart", "lineStackedColumnComboChart", "hundredPercentStackedBarChart",
                  "hundredPercentStackedColumnChart", "ribbonChart", "treemap", "gauge", "kpi", "decompositionTreeVisual"}
TECHNICKE = re.compile(r"(^id$|id$|key$|^kod|kod$|poradi|sort|^_|guid|lineage)", re.I)
GENERICKE = re.compile(r"^(measure|míra|mira|column|sloupec|col|field|pole|table|tabulka|query|dotaz)[ _]?\d*$"
                       r"|([ _-](final|v\d+|old|new|copy|kopie|test|tmp|temp|bak|backup)|\d{4})$", re.I)
TECHNICKA_TABULKA = re.compile(r"^(tbl|dim|fact|fct|stg|vw|v|d|f)[_ ]|^(Dim|Fact)[A-Z]|_", re.I)
PROCENTA = re.compile(r"%|perc|pct|procent|podíl|podil|\bratio\b", re.I)
SYSTEMOVE = ("LocalDateTable", "DateTableTemplate")


def _datove_tabulky(p: Projekt):
    """Tabulky s daty (ne výpočtové skupiny, ne automatické kalendáře, aspoň jeden sloupec)."""
    se_sloupci = {s.tabulka for s in p.sloupce}
    return [t for t in p.tabulky if not t.vypoctova_skupina and not t.nazev.startswith(SYSTEMOVE) and t.nazev in se_sloupci]


def _faktove(p: Projekt) -> set[str]:
    """Tabulky na straně „mnoho“ aspoň jednoho vztahu (fakta / mosty)."""
    return {v.tabulka_z for v in p.vztahy if v.kardinalita_z == "many"} | \
           {v.tabulka_do for v in p.vztahy if v.kardinalita_do == "many"}


def _procentni(m) -> bool:
    return bool(PROCENTA.search(m.nazev))


@dataclass
class Nalez:
    kod: str
    uroven: str          # chyba / varovani / info
    oblast: str          # model / report / ai / rls
    objekt: str
    popis: str
    doporuceni: str = ""
    navrh: str = ""      # navržený nový DAX celé míry (kontroly D…)
    presny: bool = False  # True = přepis dává stejný výsledek; False = ověřit v Desktopu

    @property
    def id(self) -> str:
        """Stabilní ID nálezu (kód + objekt + popis bez čísel) – pro baseline a výjimky. Mění se jen se změnou objektu
        nebo typu problému, ne s počty („12 z 14 měr“ → „11 z 14“ je pořád tentýž nález)."""
        klic = "|".join((self.kod, self.objekt, re.sub(r"\d+", "#", self.popis)))
        return hashlib.sha1(klic.encode("utf-8")).hexdigest()[:10]


def nastaveni(p: Projekt) -> dict:
    """Nastavení klienta (glosář termínů, rodiny měr) – audit.py ho přiřadí do p.nastaveni z --nastaveni soubor.json."""
    return getattr(p, "nastaveni", None) or {}


def tokeny(nazev: str) -> list[str]:
    """„TotalCostCenter_2024“ / „Total cost-center“ -> ['total', 'cost', 'center', '2024'] (camelCase, zkratky, _ - mezery)."""
    nazev = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", nazev)
    nazev = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", nazev)
    return [t.casefold() for t in re.findall(r"\w+", nazev.replace("_", " "))]


def _obsahuje(tok: list[str], fraze: list[str]) -> bool:
    return bool(fraze) and any(tok[i:i + len(fraze)] == fraze for i in range(len(tok) - len(fraze) + 1))


def kontrola(fn):
    KONTROLY.append(fn)
    return fn


# ------------------------------------------------------------------ model
@kontrola
def miry_bez_popisu(p: Projekt):
    return [Nalez("M01", "varovani", "ai", f"{m.tabulka}{m.plny}", "Míra nemá popis.",
                  "Doplň popis (/// v TMDL nebo Vlastnosti → Popis): co měří, v jakých jednotkách, za jaké období. AI ho čte.")
            for m in p.miry if not m.popis and not m.skryta]


@kontrola
def sloupce_bez_popisu(p: Projekt):
    return [Nalez("M02", "info", "ai", s.plny, "Viditelný sloupec nemá popis.", "Popiš význam a jednotku, nebo sloupec skryj.")
            for s in p.sloupce if not s.popis and not s.skryty]


@kontrola
def tabulky_bez_popisu(p: Projekt):
    return [Nalez("M03", "varovani", "ai", t.nazev, "Tabulka nemá popis.", "Popiš zrnitost (1 řádek = …) a zdroj dat.")
            for t in p.tabulky if not t.popis and not t.skryta and not t.nazev.startswith(("LocalDateTable", "DateTableTemplate"))]


@kontrola
def miry_bez_formatu(p: Projekt):
    out = []
    for m in p.miry:
        # textové míry (titulky, popisky, barvy) formát nepotřebují
        textova = bool(re.search(r'"[^"]*"\s*&|&\s*"|FORMAT\s*\(|CONCATENATEX|^\s*SELECTEDVALUE|"#[0-9A-Fa-f]{6}"', m.dax, re.I)) \
            or re.match(r"(Titulek|Popis|Barva|Text|Vybran)", m.nazev, re.I)
        if not m.format and not textova and not _procentni(m):
            out.append(Nalez("M04", "info", "model", f"{m.tabulka}{m.plny}", "Míra nemá formát čísla.",
                             "Nastav formát (#,0 / 0.0 % / měna), jinak se čísla zobrazují nekonzistentně."))
    return out


@kontrola
def nepouzita_pole(p: Projekt):
    """Viditelná pole, která nepoužívá žádný vizuál, míra, vztah ani řazení – kandidáti ke skrytí (méně šumu pro uživatele i AI)."""
    pouzite = {(t, n) for t, n in p.pouzita_pole()}
    mira_tab = {m.nazev: m.tabulka for m in p.miry}
    for m in p.miry:
        miry, sloupce = dax_odkazy(m.dax)
        pouzite |= sloupce | {(mira_tab.get(x, ""), x) for x in miry}
    for s in p.sloupce:
        if s.vypocet:
            miry, sloupce = dax_odkazy(s.vypocet)
            pouzite |= sloupce | {(mira_tab.get(x, ""), x) for x in miry}
        if s.radit_podle:
            pouzite.add((s.tabulka, s.radit_podle))
    for v in p.vztahy:
        for strana in (v.z, v.do):
            t, c = _rozdel_odkaz(strana)
            pouzite.add((_jmeno(t), c))
    out = [Nalez("M05", "info", "ai", s.plny, "Viditelný sloupec se nikde nepoužívá.", "Skryj ho (nebo odstraň v Power Query).")
           for s in p.sloupce if not s.skryty and (s.tabulka, s.nazev) not in pouzite]
    out += [Nalez("M05", "info", "model", f"{m.tabulka}{m.plny}", "Míru nepoužívá tento report (vizuály ani jiné míry).",
                  "Skryj ji nebo přesuň do složky „Nepoužité“. Před smazáním ověř Service → Lineage / Impact analysis: "
                  "jiné reporty, Excel ani dotazy přes XMLA nad stejným modelem audit nevidí.")
            for m in p.miry if (m.tabulka, m.nazev) not in pouzite and not m.skryta]
    return out


@kontrola
def technicke_sloupce_viditelne(p: Projekt):
    return [Nalez("M06", "varovani", "ai", s.plny, "Technický sloupec (klíč / kód / pořadí) je viditelný.",
                  "Skryj klíče a řadicí sloupce – v seznamu polí i pro AI jsou to šum.")
            for s in p.sloupce if not s.skryty and TECHNICKE.search(s.nazev)]


@kontrola
def auto_datum(p: Projekt):
    lokalni = [t.nazev for t in p.tabulky if t.nazev.startswith("LocalDateTable_")]
    return [Nalez("M07", "varovani", "model", f"{len(lokalni)} tabulek LocalDateTable", "Je zapnuté automatické datum a čas.",
                  "Vypni (Možnosti → Načtení dat → Automatické datum/čas) a používej jednu tabulku kalendáře.")] if lokalni else []


@kontrola
def vztahy(p: Projekt):
    out = []
    for v in p.vztahy:
        if v.smer == "bothDirections":
            out.append(Nalez("M08", "varovani", "model", f"{v.z} → {v.do}", "Obousměrný vztah.",
                             "Obousměrné filtrování zpomaluje a dělá nejednoznačné cesty – použij jen když je nutné."))
        if not v.aktivni:
            out.append(Nalez("M08", "info", "model", f"{v.z} → {v.do}", "Neaktivní vztah.",
                             "Ověř, že ho používá USERELATIONSHIP v nějaké míře; jinak ho smaž."))
    return out


@kontrola
def nazvy_pro_lidi(p: Projekt):
    out = []
    for s in p.sloupce:
        if not s.skryty and ("_" in s.nazev or re.fullmatch(r"[a-z]+[A-Z]\w*", s.nazev)):
            out.append(Nalez("M09", "info", "ai", s.plny, "Technický název (podtržítka / camelCase).",
                             "Přejmenuj na srozumitelný název (např. „Datum uzavření“), AI i uživatelé se pak lépe trefí."))
    for t in p.tabulky:
        if not t.skryta and not t.nazev.startswith(SYSTEMOVE) and TECHNICKA_TABULKA.search(t.nazev):
            out.append(Nalez("M09", "info", "ai", t.nazev, "Technický název tabulky (prefix tbl_/Dim/Fact, podtržítka).",
                             "Pojmenuj tabulku podle obsahu (Prodej, Zákazník, Kalendář) – v seznamu polí i pro AI je to první vodítko."))
    for m in p.miry:
        if not m.skryta and ("_" in m.nazev or re.fullmatch(r"[A-Z]{2,4}", m.nazev)):
            out.append(Nalez("M09", "info", "ai", f"{m.tabulka}{m.plny}", "Technický název míry (podtržítka / zkratka).",
                             "Celý srozumitelný název („Průměrná hodnota objednávky“ místo AOV) – AI zkratky neodhadne."))
    return out


@kontrola
def kolize_nazvu(p: Projekt):
    out = []
    sl = {(s.tabulka, s.nazev) for s in p.sloupce}
    vsechny = {}
    for m in p.miry:
        vsechny.setdefault(m.nazev, []).append(m.tabulka)
        if (m.tabulka, m.nazev) in sl:
            out.append(Nalez("M10", "chyba", "model", f"{m.tabulka}{m.plny}", "Míra má stejný název jako sloupec své tabulky.",
                             "Přejmenuj – Desktop pak projekt nemusí otevřít."))
    out += [Nalez("M10", "chyba", "model", n, f"Míra s tímto názvem je ve více tabulkách: {', '.join(t)}.", "Názvy měr musí být unikátní.")
            for n, t in vsechny.items() if len(t) > 1]
    return out


@kontrola
def rozbite_odkazy_v_dax(p: Projekt):
    miry = {m.nazev for m in p.miry}
    sloupce = {(s.tabulka, s.nazev) for s in p.sloupce}
    tabulky = {t.nazev for t in p.tabulky}
    out = []
    for m in p.miry:
        ref_m, ref_s = dax_odkazy(m.dax)
        promenne = set(re.findall(r"\bVAR\s+([A-Za-z_]\w*)", m.dax))
        promenne |= set(re.findall(r'"([^"]+)"\s*,', m.dax))   # sloupce pojmenované v SUMMARIZE / ADDCOLUMNS / SELECTCOLUMNS
        promenne |= {x for x in ref_m if re.fullmatch(r"Value\d*", x)}       # implicitní sloupce konstruktoru tabulky { ( … ) }
        for x in ref_m - miry:
            if x not in promenne and not any(x == c for _, c in sloupce):
                out.append(Nalez("M11", "chyba", "model", f"{m.tabulka}{m.plny}", f"Odkaz na neexistující míru [{x}].", "Oprav název."))
        for t, c in ref_s:
            if t in tabulky and (t, c) not in sloupce and c not in miry:
                out.append(Nalez("M11", "chyba", "model", f"{m.tabulka}{m.plny}", f"Odkaz na neexistující sloupec {t}[{c}].", "Oprav název."))
    return out


@kontrola
def kalendar(p: Projekt):
    """Bez tabulky označené jako kalendář (dataCategory Time) časová inteligence i Copilot hádají, které datum použít."""
    if not p.tabulky or any(t.kategorie.lower() == "time" for t in p.tabulky):
        return []
    datumove = {(s.tabulka, s.nazev) for s in p.sloupce if s.typ.lower() in ("datetime", "date")}
    cile = sorted({v.tabulka_do for v in p.vztahy if (v.tabulka_do, _rozdel_odkaz(v.do)[1]) in datumove})
    kandidati = cile or sorted({t.nazev for t in p.tabulky if re.search(r"date|kalend|calend|datum", t.nazev, re.I)
                                and not t.nazev.startswith(SYSTEMOVE)})
    if not kandidati:
        return []
    return [Nalez("M12", "varovani", "ai", ", ".join(kandidati), "Žádná tabulka není označená jako tabulka kalendáře.",
                  "Označ kalendář (Nástroje tabulky → Označit jako tabulku kalendářních dat; v TMDL dataCategory: Time a isKey "
                  "na sloupci data). Časové funkce i Copilot pak vědí, které datum je to hlavní.")]


@kontrola
def genericke_nazvy(p: Projekt):
    out = []
    for m in p.miry:
        if not m.skryta and GENERICKE.search(m.nazev):
            out.append(Nalez("M13", "varovani", "ai", f"{m.tabulka}{m.plny}", "Generický nebo verzovaný název míry.",
                             "Název má říkat, co míra počítá („Tržby“, ne „Measure 23“ / „_FINAL_v2“). AI podle názvu vybírá míru."))
    for s in p.sloupce:
        if not s.skryty and GENERICKE.search(s.nazev):
            out.append(Nalez("M13", "varovani", "ai", s.plny, "Generický nebo verzovaný název sloupce.",
                             "Přejmenuj podle obsahu („Název produktu“, ne „Col1“)."))
    for t in p.tabulky:
        if not t.skryta and not t.nazev.startswith(SYSTEMOVE) and GENERICKE.search(t.nazev):
            out.append(Nalez("M13", "varovani", "ai", t.nazev, "Generický nebo verzovaný název tabulky.",
                             "Verze patří do gitu, ne do názvu („Sales_FINAL_v2“ → „Prodej“)."))
    return out


@kontrola
def slozky_mer(p: Projekt):
    """Tabulka s 8+ viditelnými měrami a většinou mimo složky – plochý seznam se špatně čte lidem i AI."""
    out = []
    for t in p.tabulky:
        mm = [m for m in p.miry if m.tabulka == t.nazev and not m.skryta]
        bez = [m for m in mm if not m.slozka]
        if len(mm) >= 8 and len(bez) > len(mm) / 2:
            out.append(Nalez("M14", "varovani", "ai", t.nazev, f"{len(bez)} z {len(mm)} měr není v žádné složce.",
                             "Rozděl míry do složek podle tématu (Prodej, Marže, Časové srovnání) – vlastnost displayFolder."))
    return out


@kontrola
def tabulky_bez_vztahu(p: Projekt):
    if not p.vztahy and len(p.tabulky) < 2:
        return []
    zapojene = {v.tabulka_z for v in p.vztahy} | {v.tabulka_do for v in p.vztahy}
    out = []
    for t in _datove_tabulky(p):
        if t.nazev in zapojene or t.skryta or "NAMEOF" in t.m_vyraz.upper():         # NAMEOF = parametr polí
            continue
        # parametry „co kdyby“ a výběrové tabulky bývají DAX (DATATABLE, GENERATESERIES, { … }) – ty jsou odpojené záměrně
        parametr = bool(re.match(r"\s*(DATATABLE|GENERATESERIES|\{|SELECTCOLUMNS\s*\(\s*\{)", t.m_vyraz, re.I))
        if not parametr:
            out.append(Nalez("M15", "varovani", "model", t.nazev, "Tabulka nemá žádný vztah (osiřelá dimenze).",
                             "Výběr v ní nic nefiltruje – připoj ji vztahem, nebo ji smaž. AI ji jinak nabídne jako platnou dimenzi."))
        else:
            out.append(Nalez("M15", "info", "model", t.nazev, "Malá tabulka bez vztahu.",
                             "Ověř, že jde o záměrnou odpojenou tabulku (parametr, výběr pro míry)."))
    return out


@kontrola
def procentni_miry(p: Projekt):
    return [Nalez("M16", "varovani", "model", f"{m.tabulka}{m.plny}",
                  f"Procentní míra má formát „{m.format or 'žádný'}“ – zobrazí 0,42 místo 42 %.",
                  "Nastav formát 0.0 % (Copilot i uživatel jinak čtou podíl jako číslo).")
            for m in p.miry if _procentni(m) and "%" not in m.format and not m.skryta]


@kontrola
def duplicitni_miry(p: Projekt):
    def norm(dax):
        return re.sub(r"\s+", "", re.sub(r"//[^\n]*|--[^\n]*|/\*.*?\*/", "", dax, flags=re.S)).upper()
    out, podle = [], {}
    for m in p.miry:
        if norm(m.dax):
            podle.setdefault(norm(m.dax), []).append(m)
    for skupina in podle.values():
        if len(skupina) > 1:
            out.append(Nalez("M17", "varovani", "model", ", ".join(f"{m.tabulka}{m.plny}" for m in skupina),
                             f"{len(skupina)} míry počítají totéž (stejný DAX).",
                             "Nech jednu, ostatní smaž – dvě míry se stejným významem matou lidi i AI („která je ta správná?“)."))
    nazvy = {m.nazev for m in p.miry}
    for m in p.miry:
        cil = re.fullmatch(r"\s*\[([^\]]+)\]\s*", m.dax)
        if cil and cil.group(1) in nazvy:
            out.append(Nalez("M17", "info", "model", f"{m.tabulka}{m.plny}", f"Míra jen obaluje jinou míru [{cil.group(1)}].",
                             "Obal bez změny výpočtu je duplicita – smaž ho, nebo přejmenuj původní míru."))
    return out


@kontrola
def vztahy_mnoho_mnoho(p: Projekt):
    return [Nalez("M18", "varovani", "model", f"{v.z} → {v.do}", "Vztah mnoho:mnoho.",
                  "Obvykle znamená chybějící dimenzi (most). Výsledky se snadno nafouknou nebo zdvojí – zvaž tabulku s jedinečnými hodnotami.")
            for v in p.vztahy if v.kardinalita_z == "many" and v.kardinalita_do == "many"]


@kontrola
def pocitane_sloupce(p: Projekt):
    fakta = _faktove(p)
    return [Nalez("M19", "info", "model", s.plny, "Počítaný sloupec (DAX) na faktové tabulce.",
                  "Počítané sloupce na velkých tabulkách zvětšují model a zpomalují refresh – přesuň do Power Query / zdroje, "
                  "nebo nahraď mírou.")
            for s in p.sloupce if s.vypocet and s.tabulka in fakta]


def _typ(t: str) -> str:
    t = t.casefold()
    return {"datetime": "dateTime", "date": "dateTime", "int64": "int64", "integer": "int64", "decimal": "decimal",
            "double": "double", "string": "string", "boolean": "boolean"}.get(t, t)


@kontrola
def typy_ve_vztazich(p: Projekt):
    """M20 různé datové typy na koncích vztahu (Desktop takový vztah odmítne / tiše nespáruje řádky),
    M21 textový klíč na straně 1 (info – větší model, pomalejší spojení, citlivé na mezery a velikost písmen)."""
    sloupce = {(s.tabulka, s.nazev): s for s in p.sloupce}
    out = []
    for v in p.vztahy:
        (tz, cz), (td, cd) = _rozdel_odkaz(v.z), _rozdel_odkaz(v.do)
        a, b = sloupce.get((_jmeno(tz), cz)), sloupce.get((_jmeno(td), cd))
        if not a or not b or not a.typ or not b.typ:
            continue
        if _typ(a.typ) != _typ(b.typ):
            out.append(Nalez("M20", "chyba", "model", f"{v.z} → {v.do}", f"Konce vztahu mají různé typy: {a.typ} × {b.typ}.",
                             "Sjednoť datový typ v Power Query (obvykle celé číslo nebo text na obou stranách)."))
        elif _typ(b.typ) == "string" and v.kardinalita_do == "one":
            out.append(Nalez("M21", "info", "model", f"{v.z} → {v.do}", "Vztah spojuje textový klíč.",
                             "Funguje, ale celočíselný klíč je menší a rychlejší a nevadí mu mezery ani velikost písmen. "
                             "U kódů (měna, země) je text v pořádku."))
    return out


@kontrola
def cykly_mer(p: Projekt):
    """Míra, která přes jiné míry odkazuje sama na sebe. Desktop ji neuloží / vrátí chybu „circular dependency“."""
    miry = {m.nazev: m for m in p.miry}
    hrany = {n: sorted(x for x in dax_odkazy(m.dax)[0] if x in miry) for n, m in miry.items()}
    out, videne, hotovo = [], set(), set()

    def dfs(n, cesta):
        if n in cesta:
            cyklus = cesta[cesta.index(n):] + [n]
            if frozenset(cyklus) not in videne:
                videne.add(frozenset(cyklus))
                m = miry[n]
                out.append(Nalez("M22", "chyba", "model", f"{m.tabulka}{m.plny}",
                                 "Cyklická závislost: " + " → ".join(f"[{x}]" for x in cyklus) + ".",
                                 "Rozbij cyklus – některá z měr musí počítat ze sloupců, ne z ostatních měr v kruhu."))
            return
        if n in hotovo:
            return
        for x in hrany[n]:
            dfs(x, cesta + [n])
        hotovo.add(n)

    for n in sorted(miry):
        dfs(n, [])
    return out


@kontrola
def glosar_terminu(p: Projekt):
    """Názvy, které používají jinou variantu termínu, než určuje glosář klienta („CC“, „CostCenter“ místo
    „Nákladové středisko“). Bez glosáře (--nastaveni) se nekontroluje. Shoda po celých slovech, takže „CC“ nenajde „Account“."""
    terminy = nastaveni(p).get("terminy", {})
    if not terminy:
        return []
    objekty = [("tabulka", t.nazev, t.nazev) for t in p.tabulky if not t.skryta and not t.nazev.startswith(SYSTEMOVE)] + \
              [("míra", m.nazev, f"{m.tabulka}{m.plny}") for m in p.miry if not m.skryta] + \
              [("sloupec", s.nazev, s.plny) for s in p.sloupce if not s.skryty]
    out = []
    for druh, nazev, objekt in objekty:
        tok = tokeny(nazev)
        for preferovany, varianty in terminy.items():
            if _obsahuje(tok, tokeny(preferovany)):
                continue
            nalezena = next((v for v in varianty if _obsahuje(tok, tokeny(v))), None)
            if nalezena:
                out.append(Nalez("M23", "varovani", "ai", objekt, f"{druh.capitalize()} používá „{nalezena}“, glosář určuje „{preferovany}“.",
                                 "Jeden pojem = jeden název v celém modelu. Copilot jinak bere „CC“ a „Nákladové středisko“ jako dvě "
                                 "různé věci. Přejmenuj v Desktopu / Tabular Editoru (opraví i odkazy), nebo přidej výjimku."))
                break
    return out


@kontrola
def rodiny_mer(p: Projekt):
    """Rodiny měr z nastavení klienta (např. Skutečnost / Plán, Actual / Budget): když existuje „Tržby Skutečnost“
    (nebo „Skutečnost Tržby“), má existovat i „Tržby Plán“. Bez nastavení se nekontroluje."""
    nazvy = {m.nazev.casefold() for m in p.miry}
    out = []
    for rodina in nastaveni(p).get("rodiny", []):
        for m in sorted(p.miry, key=lambda m: m.nazev):
            protejsky = None
            for clen in rodina:
                konec = re.search(rf"(?i)[ _-]{re.escape(clen)}$", m.nazev)
                zacatek = re.match(rf"(?i){re.escape(clen)}[ _-]", m.nazev)
                if konec:
                    protejsky = [m.nazev[:konec.start() + 1] + jiny for jiny in rodina if jiny != clen]
                elif zacatek:
                    protejsky = [jiny + m.nazev[zacatek.end() - 1:] for jiny in rodina if jiny != clen]
                if protejsky is not None:
                    break
            chybi = [x for x in protejsky or [] if x.casefold() not in nazvy]
            if chybi:
                out.append(Nalez("M24", "info", "model", f"{m.tabulka}{m.plny}",
                                 f"V rodině {' / '.join(rodina)} chybí " + ", ".join(f"[{x}]" for x in chybi) + ".",
                                 "Ověř, jestli protějšek má existovat (uživatel ho bude hledat). Automaticky se nevytváří."))
    return out


# ------------------------------------------------------------------ rls
def _dosah(p: Projekt, start: set[str], vse: bool = False) -> set[str]:
    """Kam dojde bezpečnostní filtr z tabulek `start`. RLS jde jen aktivními vztahy, ze strany 1 na stranu N;
    opačně jen u 1:1 nebo se securityFilteringBehavior bothDirections. vse=True: i neaktivní a všechny oběma směry (co by šlo)."""
    hrany = {}
    for v in p.vztahy:
        if not v.aktivni and not vse:
            continue
        a, b = v.tabulka_do, v.tabulka_z                                        # směr filtru: strana do -> strana z
        oba = vse or v.bezpecnost == "bothDirections" or (v.kardinalita_z == "one" and v.kardinalita_do == "one")
        if v.kardinalita_z == "one" and v.kardinalita_do == "many":
            a, b = b, a
        hrany.setdefault(a, set()).add(b)
        if oba:
            hrany.setdefault(b, set()).add(a)
    hotovo, fronta = set(start), list(start)
    while fronta:
        for n in hrany.get(fronta.pop(), ()):
            if n not in hotovo:
                hotovo.add(n); fronta.append(n)
    return hotovo


def _proc_nedojde(p: Projekt, start: set[str], cil: str) -> str:
    if cil not in _dosah(p, start, vse=True):
        return "s filtrovanými tabulkami ji nespojuje žádný vztah"
    if any(not v.aktivni for v in p.vztahy) and cil in _dosah_jen_aktivni_obema(p, start):
        return "cesta vede proti směru vztahu (filtr jde jen ze strany 1 na stranu N)"
    return "cesta vede přes neaktivní vztah nebo proti směru (RLS nepoužije USERELATIONSHIP ani obousměrné filtrování)"


def _dosah_jen_aktivni_obema(p: Projekt, start: set[str]) -> set[str]:
    hrany = {}
    for v in p.vztahy:
        if v.aktivni:
            hrany.setdefault(v.tabulka_do, set()).add(v.tabulka_z); hrany.setdefault(v.tabulka_z, set()).add(v.tabulka_do)
    hotovo, fronta = set(start), list(start)
    while fronta:
        for n in hrany.get(fronta.pop(), ()):
            if n not in hotovo:
                hotovo.add(n); fronta.append(n)
    return hotovo


@kontrola
def rls_odkazy(p: Projekt):
    tabulky = {t.nazev for t in p.tabulky}
    sloupce = {(s.tabulka, s.nazev) for s in p.sloupce}
    miry = {m.nazev for m in p.miry}
    out = []
    for r in p.role:
        for tab, dax in r.filtry.items():
            kde = f"role {r.nazev} / {tab}"
            if tab not in tabulky:
                out.append(Nalez("S01", "chyba", "rls", kde, f"Filtr role je na neexistující tabulce {tab}.",
                                 "Tabulka byla přejmenována nebo smazána – role se nepodaří uložit / publikovat."))
                continue
            ref_m, ref_s = dax_odkazy(dax)
            for t, c in ref_s:
                if (t, c) not in sloupce and c not in miry:
                    out.append(Nalez("S01", "chyba", "rls", kde, f"Filtr odkazuje na neexistující sloupec {t}[{c}].", "Oprav název ve filtru role."))
            for x in ref_m:
                if (tab, x) not in sloupce and x not in miry:
                    out.append(Nalez("S01", "chyba", "rls", kde, f"Filtr odkazuje na neexistující pole [{x}].", "Oprav název ve filtru role."))
            if re.search(r"\bUSERNAME\s*\(", dax, re.I):
                out.append(Nalez("S06", "varovani", "rls", kde, "Filtr používá USERNAME().",
                                 "V Desktopu vrací DOMÉNA\\uživatel, v Service e-mail – použij USERPRINCIPALNAME()."))
        for t in sorted(r.ols_tabulky - tabulky):
            out.append(Nalez("S01", "chyba", "rls", f"role {r.nazev} / {t}", f"OLS skrývá neexistující tabulku {t}.", "Oprav nebo smaž oprávnění."))
        for t, c in sorted(r.ols_sloupce - sloupce):
            out.append(Nalez("S01", "chyba", "rls", f"role {r.nazev} / {t}", f"OLS skrývá neexistující sloupec {t}[{c}].", "Oprav nebo smaž oprávnění."))
    return out


@kontrola
def rls_dosah(p: Projekt):
    """Prochází filtr role všude? Pro každou roli: ke kterým datovým tabulkám se filtr nedostane (uživatel je vidí celé)."""
    out = []
    datove = _datove_tabulky(p)
    fakta = _faktove(p)
    zapojene = {v.tabulka_z for v in p.vztahy} | {v.tabulka_do for v in p.vztahy}
    for r in p.role:
        start = {t for t in r.filtry if t in {x.nazev for x in p.tabulky}}
        if not start:
            if not r.ols_tabulky and not r.ols_sloupce and r.opravneni in ("read", "readRefresh"):
                out.append(Nalez("S04", "info", "rls", f"role {r.nazev}", "Role nemá žádný filtr řádků ani OLS – vidí všechna data.",
                                 "Pokud jde o roli „vše“ (vedení), je to v pořádku; jinak doplň filtr."))
            continue
        dosah = _dosah(p, start)
        for t in datove:
            if t.nazev in dosah or t.nazev in r.ols_tabulky:
                continue
            fakt = t.nazev in fakta or t.nazev not in zapojene
            out.append(Nalez("S02" if fakt else "S08", "varovani" if fakt else "info", "rls", f"role {r.nazev} → {t.nazev}",
                             f"Filtr role ({', '.join(sorted(start))}) se k tabulce {'s daty ' if fakt else ''}nedostane – "
                             f"{_proc_nedojde(p, start, t.nazev)}.",
                             "Uživatel role uvidí tuto tabulku celou. Filtruj dimenzi, ze které vede aktivní vztah 1:N k faktu, "
                             "nebo přidej filtr přímo na tabulku / skryj ji přes OLS." if fakt else
                             "U dimenzí bývá v pořádku (seznam produktů, kalendář); ověř, že neobsahuje citlivá data."))
        for tab in start:
            if tab in fakta:
                out.append(Nalez("S07", "info", "rls", f"role {r.nazev} / {tab}", "RLS filtr je přímo na faktové tabulce.",
                                 "Filtr na velké tabulce je pomalejší a nefiltruje dimenze – lepší je filtrovat malou dimenzi."))
    if p.role:
        out += [Nalez("S03", "info", "rls", f"{v.z} → {v.do}", "Vztah posílá bezpečnostní filtr oběma směry.",
                      "Je to záměr? Zpomaluje dotazy a v modelu smí být jen jedna taková cesta mezi dvěma tabulkami.")
                for v in p.vztahy if v.bezpecnost == "bothDirections"]
    return out


@kontrola
def ols_pouzita_pole(p: Projekt):
    """Pole skrytá OLS pro roli, která přitom používá vizuál nebo míra – uživateli role se vizuál/míra rozbije."""
    out = []
    pouzite = p.pouzita_pole(bez_selektoru=True)
    for r in p.role:
        skryte = set(r.ols_sloupce) | {(s.tabulka, s.nazev) for s in p.sloupce if s.tabulka in r.ols_tabulky} | \
                 {(m.tabulka, m.nazev) for m in p.miry if m.tabulka in r.ols_tabulky}
        if not skryte:
            continue
        for pole, kde in pouzite.items():
            if pole in skryte:
                out.append(Nalez("S05", "chyba", "rls", f"role {r.nazev} / {', '.join(kde[:3])}",
                                 f"Vizuál používá {pole[0]}[{pole[1]}], které role skrývá (OLS).",
                                 "Uživateli role vizuál ukáže chybu – udělej pro něj jinou stránku/report, nebo pole nechej viditelné."))
        for m in p.miry:
            _, ref_s = dax_odkazy(m.dax)
            zakazane = sorted(f"{t}[{c}]" for t, c in ref_s if (t, c) in skryte)
            if zakazane and (m.tabulka, m.nazev) not in skryte:
                out.append(Nalez("S05", "chyba", "rls", f"role {r.nazev} / {m.tabulka}{m.plny}",
                                 f"Míra používá pole skryté OLS: {', '.join(zakazane)}.",
                                 "Míra uživateli role vrátí chybu – skryj i ji (OLS), nebo přepiš výpočet."))
    return out


# ------------------------------------------------------------------ report
@kontrola
def vizualy_bez_titulku(p: Projekt):
    return [Nalez("R01", "info", "report", p.kde(v), f"{v.typ} nemá vlastní titulek.",
                  "Titulek „Co · jednotka · období“ (např. „Výdaje podle oblastí, mil. Kč, 2025“) pomáhá lidem i AI.")
            for v in p.vizualy if v.typ in DATOVE_VIZUALY and not v.skryty and not v.titulek]


@kontrola
def natvrdo_barvy(p: Projekt):
    out = []
    for v in p.vizualy:
        barvy = sorted(set(re.findall(r"'(#[0-9A-Fa-f]{6})'", json.dumps(v.data.get("visual", {})))))
        if barvy and v.typ in DATOVE_VIZUALY:
            out.append(Nalez("R02", "info", "report", p.kde(v), f"Barvy zapsané ve vizuálu: {', '.join(barvy)}.",
                             "Přesuň barvy do theme (dataColors / visualStyles), jinak se při změně vzhledu zapomenou."))
    return out


@kontrola
def mimo_platno(p: Projekt):
    out = []
    for v in p.vizualy:
        s, pos = p.stranka(v.stranka), v.data.get("position", {})
        if s and not v.skryty and (pos.get("x", 0) + pos.get("width", 0) > s.sirka + 2 or pos.get("y", 0) + pos.get("height", 0) > s.vyska + 2):
            out.append(Nalez("R04", "varovani", "report", p.kde(v), "Vizuál přesahuje plátno stránky.", "Posuň / zmenši ho."))
    return out


@kontrola
def prekryvy(p: Projekt):
    out = []
    for s in p.stranky:
        vv = [v for v in p.vizualy if v.stranka == s.nazev and v.typ in DATOVE_VIZUALY and not v.skryty]
        for i, a in enumerate(vv):
            for b in vv[i + 1:]:
                pa, pb = a.data["position"], b.data["position"]
                sx = min(pa["x"] + pa["width"], pb["x"] + pb["width"]) - max(pa["x"], pb["x"])
                sy = min(pa["y"] + pa["height"], pb["y"] + pb["height"]) - max(pa["y"], pb["y"])
                if sx > 8 and sy > 8:
                    out.append(Nalez("R05", "varovani", "report", f"{s.zobrazeny}: {p.kde(a).split(' / ', 1)[1]} × {p.kde(b).split(' / ', 1)[1]}", "Datové vizuály se překrývají.",
                                     "Překryv schovává data a ruší klikání."))
    return out


@kontrola
def vykon_stranky(p: Projekt):
    out = []
    for s in p.stranky:
        n = sum(1 for v in p.vizualy if v.stranka == s.nazev and not v.skryty and v.typ in DATOVE_VIZUALY | {"card", "cardVisual", "slicer", "multiRowCard"})
        if n > 20:
            out.append(Nalez("R06", "varovani", "report", s.zobrazeny, f"Stránka má {n} datových vizuálů.",
                             "Každý vizuál = dotaz do modelu. Nad ~20 se stránka znatelně zpomalí – slouč karty, rozděl stránku."))
    for v in p.vizualy:
        k = len(v.pole())
        if k > 12:
            out.append(Nalez("R06", "info", "report", p.kde(v), f"Vizuál používá {k} polí.", "Zvaž, zda jsou všechna potřeba."))
    return out


@kontrola
def ulozene_vybery_slicru(p: Projekt):
    out = []
    for v in p.vizualy:
        if v.typ == "slicer":
            for g in v.data.get("visual", {}).get("objects", {}).get("general", []):
                f = g.get("properties", {}).get("filter")
                if f:
                    hodnoty = [h for h in re.findall(r"'([^']*)'", json.dumps(f, ensure_ascii=False)) if h] or ["(hodnota není čitelná – zkontroluj v Desktopu)"]
                    out.append(Nalez("R08", "info", "report", p.kde(v), f"Slicer má uložený výběr: {', '.join(hodnoty[:5])}.",
                                     "Ctrl+S v Desktopu ukládá aktuální výběr jako výchozí – ověř, že je to záměr."))
    return out


@kontrola
def zalozky_meni_data(p: Projekt):
    return [Nalez("R09", "info", "report", z.nazev, "Záložka mění i data (filtry a slicery).",
                  "U záložek pro zobrazení/skrytí panelů vypni „Data“ (suppressData), jinak resetují výběr uživatele.")
            for z in p.zalozky if not z.moznosti.get("suppressData")]


@kontrola
def alt_text(p: Projekt):
    out = []
    for v in p.vizualy:
        if v.typ in DATOVE_VIZUALY and not v.skryty:
            alt = [g for g in v.data.get("visual", {}).get("visualContainerObjects", {}).get("general", []) if g.get("properties", {}).get("altText")]
            if not alt:
                out.append(Nalez("R10", "info", "ai", p.kde(v), "Vizuál nemá alternativní text.",
                                 "Alt text (Formát → Obecné → Alternativní text) čtou čtečky obrazovky i AI nástroje."))
    return out


@kontrola
def neexistujici_pole(p: Projekt):
    if not p.tabulky:
        return []
    zname = {(s.tabulka, s.nazev) for s in p.sloupce} | {(m.tabulka, m.nazev) for m in p.miry}
    tabulky = {t.nazev for t in p.tabulky}
    ostre = p.pouzita_pole(bez_selektoru=True)
    out = [Nalez("R11", "chyba", "report", ", ".join(kde[:3]), f"Vizuál odkazuje na neexistující pole {t}[{c}].",
                 "Pole bylo přejmenováno nebo smazáno – vizuál ukáže chybu.")
           for (t, c), kde in ostre.items() if t in tabulky and (t, c) not in zname]
    out += [Nalez("R13", "info", "report", ", ".join(kde[:3]), f"Osiřelé formátování: barva / styl pro hodnotu ze smazaného pole {t}[{c}].",
                  "Nic se nerozbije, jen zbytečné nastavení – vyčistí se resetem formátování vizuálu.")
            for (t, c), kde in p.pouzita_pole().items() if t in tabulky and (t, c) not in zname and (t, c) not in ostre]
    return out


@kontrola
def slicer_bez_vztahu(p: Projekt):
    if not p.vztahy:
        return []
    zapojene = {v.tabulka_z for v in p.vztahy if v.aktivni} | {v.tabulka_do for v in p.vztahy if v.aktivni}
    tabulky = {t.nazev: t for t in p.tabulky}
    out = []
    for v in p.vizualy:
        if v.typ != "slicer" or v.skryty:
            continue
        for t, c in v.pole(bez_selektoru=True):
            if t in tabulky and t not in zapojene and "NAMEOF" not in tabulky[t].m_vyraz.upper():
                out.append(Nalez("R14", "varovani", "report", p.kde(v), f"Slicer filtruje {t}[{c}], ale tabulka nemá aktivní vztah.",
                                 "Výběr nic nezmění (pokud ho nečte míra přes SELECTEDVALUE) – připoj tabulku vztahem."))
    return out


@kontrola
def skryte_stranky(p: Projekt):
    return [Nalez("R03", "info", "report", s.zobrazeny, "Stránka je skrytá.", "Ověř, že má být (tooltip / drill-through / pracovní).")
            for s in p.stranky if s.skryta]


@kontrola
def theme(p: Projekt):
    tc = p.report_json.get("themeCollection", {})
    if "customTheme" not in tc:
        return [Nalez("R12", "info", "report", "celý report", "Report nepoužívá vlastní theme.",
                      "Theme (barvy, písma, výchozí vzhled vizuálů) drží report konzistentní a umožní přebarvit vše najednou.")]
    return []


# ------------------------------------------------------------------ kvalita DAX (D…)
DAX_UROVEN = {"D01": "varovani", "D02": "varovani", "D03": "info", "D04": "varovani", "D05": "info", "D06": "info",
              "D07": "info", "D11": "varovani", "D13": "info"}
DAX_DOPORUCENI = {
    "D01": "Filtr přes celou tabulku je pomalý a filtruje i přes rozšířenou tabulku. Použij podmínku na sloupci "
           "(s KEEPFILTERS, pokud se mají zachovat stávající filtry).",
    "D02": "Používej DIVIDE ( čitatel, jmenovatel [, náhrada] ) – při nule vrátí prázdno místo chyby a je rychlejší než IF / IFERROR.",
    "D03": "SUMX ( T, T[sloupec] ) je totéž co SUM ( T[sloupec] ) – kratší a čitelnější.",
    "D04": "COUNTROWS ( FILTER ( tabulka, … ) ) prochází řádek po řádku; CALCULATE ( COUNTROWS ( tabulka ), podmínka ) filtruje úložiště.",
    "D05": "CALCULATE bez filtrů kolem odkazu na míru nic nemění – smaž ho.",
    "D06": "Řetěz IF nahraď SWITCH ( TRUE (), podmínka1, výsledek1, … ) – čitelnější a snáz se rozšiřuje.",
    "D07": "Míru použitou víckrát ulož do VAR – počítá se jednou a výraz je kratší.",
    "D08": "Filtr v CALCULATE musí filtrovat sloupec. Porovnání jen měr (např. [Tržby] > 0) Desktop odmítne – "
           "použij FILTER ( VALUES ( Tabulka[Sloupec] ), [Míra] > 0 ).",
    "D09": "EARLIER je pozůstatek před proměnnými – ulož hodnotu vnější řádky do VAR, výraz bude čitelnější.",
    "D10": "USERELATIONSHIP funguje jen se sloupci, mezi kterými v modelu existuje (neaktivní) vztah.",
    "D11": "Časové funkce (TOTALYTD, SAMEPERIODLASTYEAR, DATEADD …) potřebují souvislý kalendář. Nad datem z faktové tabulky "
           "(chybí dny bez prodeje) vrací chybné nebo prázdné výsledky – použij sloupec z tabulky kalendáře.",
    "D12": "Rozděl míru na menší pojmenované míry nebo proměnné (VAR); dlouhý vnořený výraz se špatně ladí i čte.",
    "D13": "Sloupce piš vždy s tabulkou (Prodej[Kč]), míry vždy bez ní ([Tržby]) – jinak nejde na první pohled poznat, co je co.",
}


def _dax_kontext(p: Projekt) -> dict:
    vztahy = []
    for v in p.vztahy:
        (zt, zc), (dt, dc) = _rozdel_odkaz(v.z), _rozdel_odkaz(v.do)
        vztahy.append((_jmeno(zt), zc, _jmeno(dt), dc, v.aktivni))
    return {"miry": {m.nazev for m in p.miry}, "sloupce": {(s.tabulka, s.nazev) for s in p.sloupce},
            "typy": {(s.tabulka, s.nazev): s.typ for s in p.sloupce},
            "kalendare": {t.nazev for t in p.tabulky if t.kategorie.lower() == "time"}, "vztahy": vztahy}


@kontrola
def dax_vzory(p: Projekt):
    """Vzory DAX, které jdou zjednodušit nebo nefungují, jak by měly – s navrženým přepisem celé míry."""
    if not p.miry:
        return []
    ctx, out = _dax_kontext(p), []
    for m in p.miry:
        if not m.dax.strip():
            continue
        videno = set()
        for n in daxlib.navrhy(m.dax, ctx):
            if (n.kod, n.popis) in videno:
                continue
            videno.add((n.kod, n.popis))
            out.append(Nalez(n.kod, DAX_UROVEN.get(n.kod, "info"), "dax", f"{m.tabulka}{m.plny}", n.popis,
                             DAX_DOPORUCENI[n.kod], n.dax, n.presny))
    return out


@kontrola
def dax_chyby(p: Projekt):
    """Vzory, které v DAX nefungují: filtr CALCULATE bez sloupce, USERELATIONSHIP bez vztahu, EARLIER; a příliš složité míry."""
    if not p.miry:
        return []
    ctx, out = _dax_kontext(p), []
    pary = {}
    for zt, zc, dt, dc, akt in ctx["vztahy"]:
        pary[frozenset({(zt, zc), (dt, dc)})] = akt
    for m in p.miry:
        kde = f"{m.tabulka}{m.plny}"
        for v in daxlib.volani(m.dax, {"CALCULATE", "CALCULATETABLE", "USERELATIONSHIP", "EARLIER", "EARLIEST"}):
            if v.nazev in ("CALCULATE", "CALCULATETABLE"):
                for arg in v.argumenty[1:]:
                    sl, hole = daxlib.odkazy(arg)
                    if daxlib.je_porovnani(arg) and not sl and hole and all(h in ctx["miry"] for h in hole) and not daxlib.volani(arg):
                        out.append(Nalez("D08", "chyba", "dax", kde, f"Filtr „{arg.strip()[:60]}“ porovnává jen míry – v CALCULATE nejde použít.",
                                         DAX_DOPORUCENI["D08"]))
            elif v.nazev == "USERELATIONSHIP" and len(v.argumenty) == 2:
                a, b = daxlib.sloupec_odkaz(v.argumenty[0]), daxlib.sloupec_odkaz(v.argumenty[1])
                if a and b:
                    akt = pary.get(frozenset({a, b}))
                    if akt is None:
                        out.append(Nalez("D10", "chyba", "dax", kde, f"USERELATIONSHIP ( {a[0]}[{a[1]}], {b[0]}[{b[1]}] ) – mezi sloupci není vztah.",
                                         DAX_DOPORUCENI["D10"]))
                    elif akt:
                        out.append(Nalez("D10", "info", "dax", kde, f"USERELATIONSHIP na aktivní vztah {a[0]}[{a[1]}] – {b[0]}[{b[1]}] nic nemění.",
                                         "USERELATIONSHIP má smysl jen pro neaktivní vztah – smaž ho, nebo ověř, který vztah má být aktivní."))
            elif v.nazev in ("EARLIER", "EARLIEST"):
                out.append(Nalez("D09", "info", "dax", kde, f"Míra používá {v.nazev}.", DAX_DOPORUCENI["D09"]))
                break
        sk = daxlib.slozitost(m.dax)
        if sk["hloubka"] >= 7 or sk["calculate"] >= 4 or (sk["znaky"] > 500 and not sk["var"]):
            out.append(Nalez("D12", "info", "dax", kde,
                             f"Složitá míra: {sk['znaky']} znaků, vnoření {sk['hloubka']}, CALCULATE {sk['calculate']}×"
                             + ("" if sk["var"] else ", bez proměnných") + ".", DAX_DOPORUCENI["D12"]))
    return out


def spust(p: Projekt) -> list[Nalez]:
    nalezy = []
    for fn in KONTROLY:
        nalezy += fn(p)
    return nalezy
