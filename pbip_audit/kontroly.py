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
from jazyk import L, LDict, cesky
from pbip import Projekt, _jmeno, _rozdel_odkaz, dax_odkazy

KONTROLY = []
NADPISY = LDict({
    "M01": ("Míry bez popisu", "Measures without a description"), "M02": ("Viditelné sloupce bez popisu", "Visible columns without a description"),
    "M03": ("Tabulky bez popisu", "Tables without a description"), "M04": ("Míry bez formátu čísla", "Measures without a format string"),
    "M05": ("Nepoužitá pole", "Unused fields"), "M06": ("Viditelné technické sloupce", "Visible technical columns"),
    "M07": ("Automatické datum a čas", "Auto date/time"), "M08": ("Obousměrné a neaktivní vztahy", "Bidirectional and inactive relationships"),
    "M09": ("Technické názvy", "Technical names"), "M10": ("Kolize názvů", "Name collisions"), "M11": ("Rozbité odkazy v DAX", "Broken DAX references"),
    "R01": ("Datové vizuály bez titulku", "Data visuals without a title"), "R02": ("Barvy mimo theme", "Colours outside the theme"),
    "R03": ("Skryté stránky", "Hidden pages"), "R04": ("Vizuály mimo plátno", "Visuals off the canvas"),
    "R05": ("Překrývající se vizuály", "Overlapping visuals"), "R06": ("Výkon stránek a vizuálů", "Page and visual performance"),
    "R08": ("Slicery s uloženým výběrem", "Slicers with a saved selection"), "R09": ("Záložky měnící filtry", "Bookmarks that change filters"),
    "R10": ("Vizuály bez alternativního textu", "Visuals without alt text"), "R11": ("Vizuály s neexistujícím polem", "Visuals with a missing field"),
    "R12": ("Bez vlastního theme", "No custom theme"), "R13": ("Osiřelé formátování", "Orphaned formatting"),
    "M12": ("Chybí označená tabulka kalendáře", "No marked date table"), "M13": ("Generické a verzované názvy", "Generic and versioned names"),
    "M14": ("Míry bez složek (display folder)", "Measures without display folders"), "M15": ("Tabulky bez vztahu", "Tables without relationships"),
    "M16": ("Procentní míry bez formátu %", "Percentage measures without a % format"), "M17": ("Duplicitní míry", "Duplicate measures"),
    "M18": ("Vztahy mnoho:mnoho", "Many-to-many relationships"), "M19": ("Počítané sloupce na faktové tabulce", "Calculated columns on a fact table"),
    "R14": ("Slicer z tabulky bez vztahu", "Slicer on a table without a relationship"),
    "S01": ("Rozbitý filtr role", "Broken role filter"), "S02": ("Filtr role nedojde ke všem datům", "Role filter does not reach all data"),
    "S03": ("Bezpečnostní filtr oběma směry", "Security filter in both directions"), "S04": ("Role bez filtru", "Role without a filter"),
    "S05": ("OLS skrývá použité pole", "OLS hides a field in use"), "S06": ("USERNAME místo USERPRINCIPALNAME", "USERNAME instead of USERPRINCIPALNAME"),
    "S07": ("RLS filtr na faktové tabulce", "RLS filter on a fact table"), "S08": ("Dimenze mimo dosah filtru role", "Dimension outside the role filter"),
    "M20": ("Různé datové typy na koncích vztahu", "Mismatched data types in a relationship"), "M21": ("Textový klíč ve vztahu", "Text key in a relationship"),
    "M22": ("Cyklická závislost měr", "Circular measure dependency"), "M23": ("Nejednotné termíny (glosář)", "Inconsistent terms (glossary)"),
    "M24": ("Neúplná rodina měr", "Incomplete measure family"),
    "D01": ("FILTER jako filtr CALCULATE", "FILTER as a CALCULATE filter"), "D02": ("Dělení bez DIVIDE", "Division without DIVIDE"),
    "D03": ("Iterátor přes jediný sloupec", "Iterator over a single column"), "D04": ("COUNTROWS ( FILTER … )", "COUNTROWS ( FILTER … )"),
    "D05": ("Zbytečný CALCULATE", "Redundant CALCULATE"), "D06": ("Vnořené IF", "Nested IF"), "D07": ("Opakovaný výpočet míry", "Repeated measure evaluation"),
    "D08": ("Filtr CALCULATE bez sloupce", "CALCULATE filter without a column"), "D09": ("EARLIER v míře", "EARLIER in a measure"),
    "D10": ("USERELATIONSHIP bez vztahu", "USERELATIONSHIP without a relationship"),
    "D11": ("Časová funkce nad datem z faktu", "Time intelligence on a fact date"), "D12": ("Složité míry", "Complex measures"),
    "D13": ("Kvalifikace odkazů", "Reference qualification"),
})
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
        klic = "|".join((self.kod, cesky(self.objekt), re.sub(r"\d+", "#", cesky(self.popis))))     # id je stejné v obou jazycích
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
    return [Nalez("M01", "varovani", "ai", f"{m.tabulka}{m.plny}", L("Míra nemá popis.", "Measure has no description."),
                  L("Doplň popis (/// v TMDL nebo Vlastnosti → Popis): co měří, v jakých jednotkách, za jaké období. AI ho čte.",
                    "Add a description (/// in TMDL or Properties → Description): what it measures, in which units, for which period. AI reads it."))
            for m in p.miry if not m.popis and not m.skryta]


@kontrola
def sloupce_bez_popisu(p: Projekt):
    return [Nalez("M02", "info", "ai", s.plny, L("Viditelný sloupec nemá popis.", "Visible column has no description."),
                  L("Popiš význam a jednotku, nebo sloupec skryj.", "Describe its meaning and unit, or hide the column."))
            for s in p.sloupce if not s.popis and not s.skryty]


@kontrola
def tabulky_bez_popisu(p: Projekt):
    return [Nalez("M03", "varovani", "ai", t.nazev, L("Tabulka nemá popis.", "Table has no description."),
                  L("Popiš zrnitost (1 řádek = …) a zdroj dat.", "Describe the grain (1 row = …) and the data source."))
            for t in p.tabulky if not t.popis and not t.skryta and not t.nazev.startswith(("LocalDateTable", "DateTableTemplate"))]


@kontrola
def miry_bez_formatu(p: Projekt):
    out = []
    for m in p.miry:
        # textové míry (titulky, popisky, barvy) formát nepotřebují
        textova = bool(re.search(r'"[^"]*"\s*&|&\s*"|FORMAT\s*\(|CONCATENATEX|^\s*SELECTEDVALUE|"#[0-9A-Fa-f]{6}"', m.dax, re.I)) \
            or re.match(r"(Titulek|Popis|Barva|Text|Vybran)", m.nazev, re.I)
        if not m.format and not textova and not _procentni(m):
            out.append(Nalez("M04", "info", "model", f"{m.tabulka}{m.plny}", L("Míra nemá formát čísla.", "Measure has no format string."),
                             L("Nastav formát (#,0 / 0.0 % / měna), jinak se čísla zobrazují nekonzistentně.",
                               "Set a format (#,0 / 0.0 % / currency), otherwise numbers display inconsistently.")))
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
    out = [Nalez("M05", "info", "ai", s.plny, L("Viditelný sloupec se nikde nepoužívá.", "Visible column is not used anywhere."),
                  L("Skryj ho (nebo odstraň v Power Query).", "Hide it (or remove it in Power Query)."))
           for s in p.sloupce if not s.skryty and (s.tabulka, s.nazev) not in pouzite]
    out += [Nalez("M05", "info", "model", f"{m.tabulka}{m.plny}", L("Míru nepoužívá tento report (vizuály ani jiné míry).", "Measure is not used by this report (visuals or other measures)."),
                  L("Skryj ji nebo přesuň do složky „Nepoužité“. Před smazáním ověř Service → Lineage / Impact analysis: "
                    "jiné reporty, Excel ani dotazy přes XMLA nad stejným modelem audit nevidí.",
                    "Hide it or move it to an \"Unused\" folder. Before deleting, check Service → Lineage / Impact analysis: "
                    "the audit can't see other reports, Excel or XMLA queries over the same model."))
            for m in p.miry if (m.tabulka, m.nazev) not in pouzite and not m.skryta]
    return out


@kontrola
def technicke_sloupce_viditelne(p: Projekt):
    return [Nalez("M06", "varovani", "ai", s.plny, L("Technický sloupec (klíč / kód / pořadí) je viditelný.", "Technical column (key / code / sort order) is visible."),
                  L("Skryj klíče a řadicí sloupce – v seznamu polí i pro AI jsou to šum.",
                    "Hide keys and sort columns – they are noise in the field list and for AI."))
            for s in p.sloupce if not s.skryty and TECHNICKE.search(s.nazev)]


@kontrola
def auto_datum(p: Projekt):
    lokalni = [t.nazev for t in p.tabulky if t.nazev.startswith("LocalDateTable_")]
    return [Nalez("M07", "varovani", "model", L(f"{len(lokalni)} tabulek LocalDateTable", f"{len(lokalni)} LocalDateTable tables"),
                  L("Je zapnuté automatické datum a čas.", "Auto date/time is enabled."),
                  L("Vypni (Možnosti → Načtení dat → Automatické datum/čas) a používej jednu tabulku kalendáře.",
                    "Turn it off (Options → Data load → Auto date/time) and use a single date table."))] if lokalni else []


@kontrola
def vztahy(p: Projekt):
    out = []
    for v in p.vztahy:
        if v.smer == "bothDirections":
            out.append(Nalez("M08", "varovani", "model", f"{v.z} → {v.do}", L("Obousměrný vztah.", "Bidirectional relationship."),
                             L("Obousměrné filtrování zpomaluje a dělá nejednoznačné cesty – použij jen když je nutné.",
                               "Bidirectional filtering slows queries and creates ambiguous paths – use it only when necessary.")))
        if not v.aktivni:
            out.append(Nalez("M08", "info", "model", f"{v.z} → {v.do}", L("Neaktivní vztah.", "Inactive relationship."),
                             L("Ověř, že ho používá USERELATIONSHIP v nějaké míře; jinak ho smaž.",
                               "Check that some measure uses it via USERELATIONSHIP; otherwise delete it.")))
    return out


@kontrola
def nazvy_pro_lidi(p: Projekt):
    out = []
    for s in p.sloupce:
        if not s.skryty and ("_" in s.nazev or re.fullmatch(r"[a-z]+[A-Z]\w*", s.nazev)):
            out.append(Nalez("M09", "info", "ai", s.plny, L("Technický název (podtržítka / camelCase).", "Technical name (underscores / camelCase)."),
                             L("Přejmenuj na srozumitelný název (např. „Datum uzavření“), AI i uživatelé se pak lépe trefí.",
                               "Rename it to a readable name (e.g. \"Close Date\") so both AI and users find it.")))
    for t in p.tabulky:
        if not t.skryta and not t.nazev.startswith(SYSTEMOVE) and TECHNICKA_TABULKA.search(t.nazev):
            out.append(Nalez("M09", "info", "ai", t.nazev, L("Technický název tabulky (prefix tbl_/Dim/Fact, podtržítka).", "Technical table name (tbl_/Dim/Fact prefix, underscores)."),
                             L("Pojmenuj tabulku podle obsahu (Prodej, Zákazník, Kalendář) – v seznamu polí i pro AI je to první vodítko.",
                               "Name the table after its content (Sales, Customer, Date) – it is the first clue in the field list and for AI.")))
    for m in p.miry:
        if not m.skryta and ("_" in m.nazev or re.fullmatch(r"[A-Z]{2,4}", m.nazev)):
            out.append(Nalez("M09", "info", "ai", f"{m.tabulka}{m.plny}", L("Technický název míry (podtržítka / zkratka).", "Technical measure name (underscores / abbreviation)."),
                             L("Celý srozumitelný název („Průměrná hodnota objednávky“ místo AOV) – AI zkratky neodhadne.",
                               "Use a full readable name (\"Average Order Value\" instead of AOV) – AI can't guess abbreviations.")))
    return out


@kontrola
def kolize_nazvu(p: Projekt):
    out = []
    sl = {(s.tabulka, s.nazev) for s in p.sloupce}
    vsechny = {}
    for m in p.miry:
        vsechny.setdefault(m.nazev, []).append(m.tabulka)
        if (m.tabulka, m.nazev) in sl:
            out.append(Nalez("M10", "chyba", "model", f"{m.tabulka}{m.plny}", L("Míra má stejný název jako sloupec své tabulky.", "Measure has the same name as a column of its table."),
                             L("Přejmenuj – Desktop pak projekt nemusí otevřít.", "Rename it – Desktop may fail to open the project.")))
    out += [Nalez("M10", "chyba", "model", n, L(f"Míra s tímto názvem je ve více tabulkách: {', '.join(t)}.", f"A measure with this name exists in several tables: {', '.join(t)}."),
                    L("Názvy měr musí být unikátní.", "Measure names must be unique."))
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
                out.append(Nalez("M11", "chyba", "model", f"{m.tabulka}{m.plny}", L(f"Odkaz na neexistující míru [{x}].", f"Reference to a non-existent measure [{x}]."), L("Oprav název.", "Fix the name.")))
        for t, c in ref_s:
            if t in tabulky and (t, c) not in sloupce and c not in miry:
                out.append(Nalez("M11", "chyba", "model", f"{m.tabulka}{m.plny}", L(f"Odkaz na neexistující sloupec {t}[{c}].", f"Reference to a non-existent column {t}[{c}]."), L("Oprav název.", "Fix the name.")))
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
    return [Nalez("M12", "varovani", "ai", ", ".join(kandidati), L("Žádná tabulka není označená jako tabulka kalendáře.", "No table is marked as a date table."),
                  L("Označ kalendář (Nástroje tabulky → Označit jako tabulku kalendářních dat; v TMDL dataCategory: Time a isKey "
                    "na sloupci data). Časové funkce i Copilot pak vědí, které datum je to hlavní.",
                    "Mark the date table (Table tools → Mark as date table; in TMDL dataCategory: Time and isKey on the date "
                    "column). Time intelligence and Copilot then know which date is the main one."))]


@kontrola
def genericke_nazvy(p: Projekt):
    out = []
    for m in p.miry:
        if not m.skryta and GENERICKE.search(m.nazev):
            out.append(Nalez("M13", "varovani", "ai", f"{m.tabulka}{m.plny}", L("Generický nebo verzovaný název míry.", "Generic or versioned measure name."),
                             L("Název má říkat, co míra počítá („Tržby“, ne „Measure 23“ / „_FINAL_v2“). AI podle názvu vybírá míru.",
                               "The name should say what the measure calculates (\"Sales\", not \"Measure 23\" / \"_FINAL_v2\"). AI picks measures by name.")))
    for s in p.sloupce:
        if not s.skryty and GENERICKE.search(s.nazev):
            out.append(Nalez("M13", "varovani", "ai", s.plny, L("Generický nebo verzovaný název sloupce.", "Generic or versioned column name."),
                             L("Přejmenuj podle obsahu („Název produktu“, ne „Col1“).", "Rename it after its content (\"Product Name\", not \"Col1\").")))
    for t in p.tabulky:
        if not t.skryta and not t.nazev.startswith(SYSTEMOVE) and GENERICKE.search(t.nazev):
            out.append(Nalez("M13", "varovani", "ai", t.nazev, L("Generický nebo verzovaný název tabulky.", "Generic or versioned table name."),
                             L("Verze patří do gitu, ne do názvu („Sales_FINAL_v2“ → „Prodej“).",
                               "Versions belong in git, not in the name (\"Sales_FINAL_v2\" → \"Sales\").")))
    return out


@kontrola
def slozky_mer(p: Projekt):
    """Tabulka s 8+ viditelnými měrami a většinou mimo složky – plochý seznam se špatně čte lidem i AI."""
    out = []
    for t in p.tabulky:
        mm = [m for m in p.miry if m.tabulka == t.nazev and not m.skryta]
        bez = [m for m in mm if not m.slozka]
        if len(mm) >= 8 and len(bez) > len(mm) / 2:
            out.append(Nalez("M14", "varovani", "ai", t.nazev, L(f"{len(bez)} z {len(mm)} měr není v žádné složce.", f"{len(bez)} of {len(mm)} measures are not in any folder."),
                             L("Rozděl míry do složek podle tématu (Prodej, Marže, Časové srovnání) – vlastnost displayFolder.",
                               "Group measures into folders by topic (Sales, Margin, Time comparison) – the displayFolder property.")))
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
            out.append(Nalez("M15", "varovani", "model", t.nazev, L("Tabulka nemá žádný vztah (osiřelá dimenze).", "Table has no relationship (orphaned dimension)."),
                             L("Výběr v ní nic nefiltruje – připoj ji vztahem, nebo ji smaž. AI ji jinak nabídne jako platnou dimenzi.",
                               "Selecting from it filters nothing – connect it with a relationship or delete it. Otherwise AI offers it as a valid dimension.")))
        else:
            out.append(Nalez("M15", "info", "model", t.nazev, L("Malá tabulka bez vztahu.", "Small table without a relationship."),
                             L("Ověř, že jde o záměrnou odpojenou tabulku (parametr, výběr pro míry).",
                               "Check that it is an intentionally disconnected table (parameter, selection for measures).")))
    return out


@kontrola
def procentni_miry(p: Projekt):
    return [Nalez("M16", "varovani", "model", f"{m.tabulka}{m.plny}",
                  L(f"Procentní míra má formát „{m.format or 'žádný'}“ – zobrazí 0,42 místo 42 %.",
                    f"Percentage measure has format \"{m.format or 'none'}\" – shows 0.42 instead of 42 %."),
                  L("Nastav formát 0.0 % (Copilot i uživatel jinak čtou podíl jako číslo).",
                    "Set format 0.0 % (otherwise Copilot and users read the ratio as a plain number)."))
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
                             L(f"{len(skupina)} míry počítají totéž (stejný DAX).", f"{len(skupina)} measures calculate the same thing (identical DAX)."),
                             L("Nech jednu, ostatní smaž – dvě míry se stejným významem matou lidi i AI („která je ta správná?“).",
                               "Keep one and delete the rest – two measures with the same meaning confuse people and AI (\"which one is right?\").")))
    nazvy = {m.nazev for m in p.miry}
    for m in p.miry:
        cil = re.fullmatch(r"\s*\[([^\]]+)\]\s*", m.dax)
        if cil and cil.group(1) in nazvy:
            out.append(Nalez("M17", "info", "model", f"{m.tabulka}{m.plny}", L(f"Míra jen obaluje jinou míru [{cil.group(1)}].", f"Measure only wraps another measure [{cil.group(1)}]."),
                             L("Obal bez změny výpočtu je duplicita – smaž ho, nebo přejmenuj původní míru.",
                               "A wrapper that doesn't change the calculation is a duplicate – delete it or rename the original measure.")))
    return out


@kontrola
def vztahy_mnoho_mnoho(p: Projekt):
    return [Nalez("M18", "varovani", "model", f"{v.z} → {v.do}", L("Vztah mnoho:mnoho.", "Many-to-many relationship."),
                  L("Obvykle znamená chybějící dimenzi (most). Výsledky se snadno nafouknou nebo zdvojí – zvaž tabulku s jedinečnými hodnotami.",
                    "Usually means a missing dimension (bridge). Results easily inflate or double – consider a table of unique values."))
            for v in p.vztahy if v.kardinalita_z == "many" and v.kardinalita_do == "many"]


@kontrola
def pocitane_sloupce(p: Projekt):
    fakta = _faktove(p)
    return [Nalez("M19", "info", "model", s.plny, L("Počítaný sloupec (DAX) na faktové tabulce.", "Calculated column (DAX) on a fact table."),
                  L("Počítané sloupce na velkých tabulkách zvětšují model a zpomalují refresh – přesuň do Power Query / zdroje, "
                    "nebo nahraď mírou.", "Calculated columns on large tables grow the model and slow refresh – move it to Power Query / "
                    "the source, or replace it with a measure."))
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
            out.append(Nalez("M20", "chyba", "model", f"{v.z} → {v.do}", L(f"Konce vztahu mají různé typy: {a.typ} × {b.typ}.", f"Relationship ends have different types: {a.typ} × {b.typ}."),
                             L("Sjednoť datový typ v Power Query (obvykle celé číslo nebo text na obou stranách).",
                               "Align the data type in Power Query (usually integer or text on both sides).")))
        elif _typ(b.typ) == "string" and v.kardinalita_do == "one":
            out.append(Nalez("M21", "info", "model", f"{v.z} → {v.do}", L("Vztah spojuje textový klíč.", "Relationship joins on a text key."),
                             L("Funguje, ale celočíselný klíč je menší a rychlejší a nevadí mu mezery ani velikost písmen. "
                               "U kódů (měna, země) je text v pořádku.", "It works, but an integer key is smaller and faster and is not "
                               "sensitive to spaces or letter case. Text is fine for codes (currency, country).")))
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
                                 L("Cyklická závislost: ", "Circular dependency: ") + " → ".join(f"[{x}]" for x in cyklus) + ".",
                                 L("Rozbij cyklus – některá z měr musí počítat ze sloupců, ne z ostatních měr v kruhu.",
                                   "Break the cycle – one of the measures must calculate from columns, not from the other measures in the loop.")))
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
    objekty = [(L("tabulka", "table"), t.nazev, t.nazev) for t in p.tabulky if not t.skryta and not t.nazev.startswith(SYSTEMOVE)] + \
              [(L("míra", "measure"), m.nazev, f"{m.tabulka}{m.plny}") for m in p.miry if not m.skryta] + \
              [(L("sloupec", "column"), s.nazev, s.plny) for s in p.sloupce if not s.skryty]
    out = []
    for druh, nazev, objekt in objekty:
        tok = tokeny(nazev)
        for preferovany, varianty in terminy.items():
            if _obsahuje(tok, tokeny(preferovany)):
                continue
            nalezena = next((v for v in varianty if _obsahuje(tok, tokeny(v))), None)
            if nalezena:
                out.append(Nalez("M23", "varovani", "ai", objekt, L(f"{druh.cs.capitalize()} používá „{nalezena}“, glosář určuje „{preferovany}“.",
                                   f"{druh.en.capitalize()} uses \"{nalezena}\", the glossary says \"{preferovany}\"."),
                                 L("Jeden pojem = jeden název v celém modelu. Copilot jinak bere „CC“ a „Nákladové středisko“ jako dvě "
                                   "různé věci. Přejmenuj v Desktopu / Tabular Editoru (opraví i odkazy), nebo přidej výjimku.",
                                   "One concept = one name across the model. Otherwise Copilot treats \"CC\" and \"Cost Center\" as two "
                                   "different things. Rename in Desktop / Tabular Editor (fixes references too), or add an exception.")))
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
                                 L(f"V rodině {' / '.join(rodina)} chybí ", f"Family {' / '.join(rodina)} is missing ")
                                 + ", ".join(f"[{x}]" for x in chybi) + ".",
                                 L("Ověř, jestli protějšek má existovat (uživatel ho bude hledat). Automaticky se nevytváří.",
                                   "Check whether the counterpart should exist (users will look for it). It is not created automatically.")))
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
        return L("s filtrovanými tabulkami ji nespojuje žádný vztah", "no relationship connects it to the filtered tables")
    if any(not v.aktivni for v in p.vztahy) and cil in _dosah_jen_aktivni_obema(p, start):
        return L("cesta vede proti směru vztahu (filtr jde jen ze strany 1 na stranu N)",
                 "the path runs against the relationship direction (the filter only goes from the one side to the many side)")
    return L("cesta vede přes neaktivní vztah nebo proti směru (RLS nepoužije USERELATIONSHIP ani obousměrné filtrování)",
             "the path runs through an inactive relationship or against the direction (RLS uses neither USERELATIONSHIP nor bidirectional filtering)")


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
                out.append(Nalez("S01", "chyba", "rls", kde, L(f"Filtr role je na neexistující tabulce {tab}.", f"Role filter is on a non-existent table {tab}."),
                                 L("Tabulka byla přejmenována nebo smazána – role se nepodaří uložit / publikovat.",
                                   "The table was renamed or deleted – the role can't be saved / published.")))
                continue
            ref_m, ref_s = dax_odkazy(dax)
            for t, c in ref_s:
                if (t, c) not in sloupce and c not in miry:
                    out.append(Nalez("S01", "chyba", "rls", kde, L(f"Filtr odkazuje na neexistující sloupec {t}[{c}].", f"Filter references a non-existent column {t}[{c}]."),
                                     L("Oprav název ve filtru role.", "Fix the name in the role filter.")))
            for x in ref_m:
                if (tab, x) not in sloupce and x not in miry:
                    out.append(Nalez("S01", "chyba", "rls", kde, L(f"Filtr odkazuje na neexistující pole [{x}].", f"Filter references a non-existent field [{x}]."),
                                     L("Oprav název ve filtru role.", "Fix the name in the role filter.")))
            if re.search(r"\bUSERNAME\s*\(", dax, re.I):
                out.append(Nalez("S06", "varovani", "rls", kde, L("Filtr používá USERNAME().", "Filter uses USERNAME()."),
                                 L("V Desktopu vrací DOMÉNA\\uživatel, v Service e-mail – použij USERPRINCIPALNAME().",
                                   "It returns DOMAIN\\user in Desktop and an e-mail in the Service – use USERPRINCIPALNAME().")))
        for t in sorted(r.ols_tabulky - tabulky):
            out.append(Nalez("S01", "chyba", "rls", f"role {r.nazev} / {t}", L(f"OLS skrývá neexistující tabulku {t}.", f"OLS hides a non-existent table {t}."),
                             L("Oprav nebo smaž oprávnění.", "Fix or delete the permission.")))
        for t, c in sorted(r.ols_sloupce - sloupce):
            out.append(Nalez("S01", "chyba", "rls", f"role {r.nazev} / {t}", L(f"OLS skrývá neexistující sloupec {t}[{c}].", f"OLS hides a non-existent column {t}[{c}]."),
                             L("Oprav nebo smaž oprávnění.", "Fix or delete the permission.")))
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
                out.append(Nalez("S04", "info", "rls", f"role {r.nazev}", L("Role nemá žádný filtr řádků ani OLS – vidí všechna data.", "Role has no row filter and no OLS – it sees all data."),
                                 L("Pokud jde o roli „vše“ (vedení), je to v pořádku; jinak doplň filtr.",
                                   "Fine for an \"all data\" role (management); otherwise add a filter.")))
            continue
        dosah = _dosah(p, start)
        for t in datove:
            if t.nazev in dosah or t.nazev in r.ols_tabulky:
                continue
            fakt = t.nazev in fakta or t.nazev not in zapojene
            out.append(Nalez("S02" if fakt else "S08", "varovani" if fakt else "info", "rls", f"role {r.nazev} → {t.nazev}",
                             L(f"Filtr role ({', '.join(sorted(start))}) se k tabulce {'s daty ' if fakt else ''}nedostane – "
                               f"{_proc_nedojde(p, start, t.nazev).cs}.",
                               f"The role filter ({', '.join(sorted(start))}) does not reach this {'data ' if fakt else ''}table – "
                               f"{_proc_nedojde(p, start, t.nazev).en}."),
                             L("Uživatel role uvidí tuto tabulku celou. Filtruj dimenzi, ze které vede aktivní vztah 1:N k faktu, "
                               "nebo přidej filtr přímo na tabulku / skryj ji přes OLS.",
                               "Users of the role see this whole table. Filter a dimension with an active 1:N relationship to the fact, "
                               "or add a filter directly on the table / hide it with OLS.") if fakt else
                             L("U dimenzí bývá v pořádku (seznam produktů, kalendář); ověř, že neobsahuje citlivá data.",
                               "Usually fine for dimensions (product list, calendar); check that it holds no sensitive data.")))
        for tab in start:
            if tab in fakta:
                out.append(Nalez("S07", "info", "rls", f"role {r.nazev} / {tab}", L("RLS filtr je přímo na faktové tabulce.", "RLS filter is directly on a fact table."),
                                 L("Filtr na velké tabulce je pomalejší a nefiltruje dimenze – lepší je filtrovat malou dimenzi.",
                                   "A filter on a large table is slower and doesn't filter dimensions – better filter a small dimension.")))
    if p.role:
        out += [Nalez("S03", "info", "rls", f"{v.z} → {v.do}", L("Vztah posílá bezpečnostní filtr oběma směry.", "Relationship applies the security filter in both directions."),
                      L("Je to záměr? Zpomaluje dotazy a v modelu smí být jen jedna taková cesta mezi dvěma tabulkami.",
                        "Is it intentional? It slows queries and only one such path between two tables is allowed in a model."))
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
                                 L(f"Vizuál používá {pole[0]}[{pole[1]}], které role skrývá (OLS).",
                                   f"A visual uses {pole[0]}[{pole[1]}], which the role hides (OLS)."),
                                 L("Uživateli role vizuál ukáže chybu – udělej pro něj jinou stránku/report, nebo pole nechej viditelné.",
                                   "Users of the role see an error in the visual – give them another page/report, or keep the field visible.")))
        for m in p.miry:
            _, ref_s = dax_odkazy(m.dax)
            zakazane = sorted(f"{t}[{c}]" for t, c in ref_s if (t, c) in skryte)
            if zakazane and (m.tabulka, m.nazev) not in skryte:
                out.append(Nalez("S05", "chyba", "rls", f"role {r.nazev} / {m.tabulka}{m.plny}",
                                 L(f"Míra používá pole skryté OLS: {', '.join(zakazane)}.", f"Measure uses fields hidden by OLS: {', '.join(zakazane)}."),
                                 L("Míra uživateli role vrátí chybu – skryj i ji (OLS), nebo přepiš výpočet.",
                                   "The measure returns an error for users of the role – hide it too (OLS), or rewrite the calculation.")))
    return out


# ------------------------------------------------------------------ report
@kontrola
def vizualy_bez_titulku(p: Projekt):
    return [Nalez("R01", "info", "report", p.kde(v), L(f"{v.typ} nemá vlastní titulek.", f"{v.typ} has no custom title."),
                  L("Titulek „Co · jednotka · období“ (např. „Výdaje podle oblastí, mil. Kč, 2025“) pomáhá lidem i AI.",
                    "A \"What · unit · period\" title (e.g. \"Spending by area, € m, 2025\") helps people and AI."))
            for v in p.vizualy if v.typ in DATOVE_VIZUALY and not v.skryty and not v.titulek]


@kontrola
def natvrdo_barvy(p: Projekt):
    out = []
    for v in p.vizualy:
        barvy = sorted(set(re.findall(r"'(#[0-9A-Fa-f]{6})'", json.dumps(v.data.get("visual", {})))))
        if barvy and v.typ in DATOVE_VIZUALY:
            out.append(Nalez("R02", "info", "report", p.kde(v), L(f"Barvy zapsané ve vizuálu: {', '.join(barvy)}.", f"Colours hard-coded in the visual: {', '.join(barvy)}."),
                             L("Přesuň barvy do theme (dataColors / visualStyles), jinak se při změně vzhledu zapomenou.",
                               "Move colours to the theme (dataColors / visualStyles), otherwise they get forgotten when the look changes.")))
    return out


@kontrola
def mimo_platno(p: Projekt):
    out = []
    for v in p.vizualy:
        s, pos = p.stranka(v.stranka), v.data.get("position", {})
        if s and not v.skryty and (pos.get("x", 0) + pos.get("width", 0) > s.sirka + 2 or pos.get("y", 0) + pos.get("height", 0) > s.vyska + 2):
            out.append(Nalez("R04", "varovani", "report", p.kde(v), L("Vizuál přesahuje plátno stránky.", "Visual extends beyond the page canvas."), L("Posuň / zmenši ho.", "Move / resize it.")))
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
                    out.append(Nalez("R05", "varovani", "report", f"{s.zobrazeny}: {p.kde(a).split(' / ', 1)[1]} × {p.kde(b).split(' / ', 1)[1]}", L("Datové vizuály se překrývají.", "Data visuals overlap."),
                                     L("Překryv schovává data a ruší klikání.", "Overlaps hide data and interfere with clicking.")))
    return out


@kontrola
def vykon_stranky(p: Projekt):
    out = []
    for s in p.stranky:
        n = sum(1 for v in p.vizualy if v.stranka == s.nazev and not v.skryty and v.typ in DATOVE_VIZUALY | {"card", "cardVisual", "slicer", "multiRowCard"})
        if n > 20:
            out.append(Nalez("R06", "varovani", "report", s.zobrazeny, L(f"Stránka má {n} datových vizuálů.", f"Page has {n} data visuals."),
                             L("Každý vizuál = dotaz do modelu. Nad ~20 se stránka znatelně zpomalí – slouč karty, rozděl stránku.",
                               "Each visual = a query to the model. Above ~20 the page slows down noticeably – merge cards, split the page.")))
    for v in p.vizualy:
        k = len(v.pole())
        if k > 12:
            out.append(Nalez("R06", "info", "report", p.kde(v), L(f"Vizuál používá {k} polí.", f"Visual uses {k} fields."), L("Zvaž, zda jsou všechna potřeba.", "Consider whether all are needed.")))
    return out


@kontrola
def ulozene_vybery_slicru(p: Projekt):
    out = []
    for v in p.vizualy:
        if v.typ == "slicer":
            for g in v.data.get("visual", {}).get("objects", {}).get("general", []):
                f = g.get("properties", {}).get("filter")
                if f:
                    hodnoty = [h for h in re.findall(r"'([^']*)'", json.dumps(f, ensure_ascii=False)) if h]
                    cs = ", ".join(hodnoty[:5]) or "(hodnota není čitelná – zkontroluj v Desktopu)"
                    en = ", ".join(hodnoty[:5]) or "(value not readable – check in Desktop)"
                    out.append(Nalez("R08", "info", "report", p.kde(v), L(f"Slicer má uložený výběr: {cs}.", f"Slicer has a saved selection: {en}."),
                                     L("Ctrl+S v Desktopu ukládá aktuální výběr jako výchozí – ověř, že je to záměr.",
                                       "Ctrl+S in Desktop saves the current selection as the default – check that it is intended.")))
    return out


@kontrola
def zalozky_meni_data(p: Projekt):
    return [Nalez("R09", "info", "report", z.nazev, L("Záložka mění i data (filtry a slicery).", "Bookmark also changes data (filters and slicers)."),
                  L("U záložek pro zobrazení/skrytí panelů vypni „Data“ (suppressData), jinak resetují výběr uživatele.",
                    "For bookmarks that show/hide panels turn off \"Data\" (suppressData), otherwise they reset the user's selection."))
            for z in p.zalozky if not z.moznosti.get("suppressData")]


@kontrola
def alt_text(p: Projekt):
    out = []
    for v in p.vizualy:
        if v.typ in DATOVE_VIZUALY and not v.skryty:
            alt = [g for g in v.data.get("visual", {}).get("visualContainerObjects", {}).get("general", []) if g.get("properties", {}).get("altText")]
            if not alt:
                out.append(Nalez("R10", "info", "ai", p.kde(v), L("Vizuál nemá alternativní text.", "Visual has no alt text."),
                                 L("Alt text (Formát → Obecné → Alternativní text) čtou čtečky obrazovky i AI nástroje.",
                                   "Alt text (Format → General → Alt text) is read by screen readers and AI tools.")))
    return out


@kontrola
def neexistujici_pole(p: Projekt):
    if not p.tabulky:
        return []
    zname = {(s.tabulka, s.nazev) for s in p.sloupce} | {(m.tabulka, m.nazev) for m in p.miry}
    tabulky = {t.nazev for t in p.tabulky}
    ostre = p.pouzita_pole(bez_selektoru=True)
    out = [Nalez("R11", "chyba", "report", ", ".join(kde[:3]), L(f"Vizuál odkazuje na neexistující pole {t}[{c}].", f"Visual references a non-existent field {t}[{c}]."),
                 L("Pole bylo přejmenováno nebo smazáno – vizuál ukáže chybu.", "The field was renamed or deleted – the visual shows an error."))
           for (t, c), kde in ostre.items() if t in tabulky and (t, c) not in zname]
    out += [Nalez("R13", "info", "report", ", ".join(kde[:3]), L(f"Osiřelé formátování: barva / styl pro hodnotu ze smazaného pole {t}[{c}].",
                    f"Orphaned formatting: colour / style for a value of the deleted field {t}[{c}]."),
                  L("Nic se nerozbije, jen zbytečné nastavení – vyčistí se resetem formátování vizuálu.",
                    "Nothing breaks, it's just clutter – resetting the visual's formatting cleans it up."))
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
                out.append(Nalez("R14", "varovani", "report", p.kde(v), L(f"Slicer filtruje {t}[{c}], ale tabulka nemá aktivní vztah.", f"Slicer filters {t}[{c}], but the table has no active relationship."),
                                 L("Výběr nic nezmění (pokud ho nečte míra přes SELECTEDVALUE) – připoj tabulku vztahem.",
                                   "The selection changes nothing (unless a measure reads it via SELECTEDVALUE) – connect the table with a relationship.")))
    return out


@kontrola
def skryte_stranky(p: Projekt):
    return [Nalez("R03", "info", "report", s.zobrazeny, L("Stránka je skrytá.", "Page is hidden."),
                  L("Ověř, že má být (tooltip / drill-through / pracovní).", "Check that it should be (tooltip / drill-through / work page)."))
            for s in p.stranky if s.skryta]


@kontrola
def theme(p: Projekt):
    tc = p.report_json.get("themeCollection", {})
    if "customTheme" not in tc:
        return [Nalez("R12", "info", "report", L("celý report", "whole report"), L("Report nepoužívá vlastní theme.", "Report doesn't use a custom theme."),
                      L("Theme (barvy, písma, výchozí vzhled vizuálů) drží report konzistentní a umožní přebarvit vše najednou.",
                        "A theme (colours, fonts, default visual styles) keeps the report consistent and lets you recolour everything at once."))]
    return []


# ------------------------------------------------------------------ kvalita DAX (D…)
DAX_UROVEN = {"D01": "varovani", "D02": "varovani", "D03": "info", "D04": "varovani", "D05": "info", "D06": "info",
              "D07": "info", "D11": "varovani", "D13": "info"}
DAX_DOPORUCENI = LDict({
    "D01": ("Filtr přes celou tabulku je pomalý a filtruje i přes rozšířenou tabulku. Použij podmínku na sloupci "
            "(s KEEPFILTERS, pokud se mají zachovat stávající filtry).",
            "A filter over a whole table is slow and also filters through the expanded table. Use a column predicate "
            "(with KEEPFILTERS if existing filters should be kept)."),
    "D02": ("Používej DIVIDE ( čitatel, jmenovatel [, náhrada] ) – při nule vrátí prázdno místo chyby a je rychlejší než IF / IFERROR.",
            "Use DIVIDE ( numerator, denominator [, alternate] ) – it returns blank instead of an error on zero and is faster than IF / IFERROR."),
    "D03": ("SUMX ( T, T[sloupec] ) je totéž co SUM ( T[sloupec] ) – kratší a čitelnější.",
            "SUMX ( T, T[column] ) is the same as SUM ( T[column] ) – shorter and more readable."),
    "D04": ("COUNTROWS ( FILTER ( tabulka, … ) ) prochází řádek po řádku; CALCULATE ( COUNTROWS ( tabulka ), podmínka ) filtruje úložiště.",
            "COUNTROWS ( FILTER ( table, … ) ) iterates row by row; CALCULATE ( COUNTROWS ( table ), condition ) filters the storage engine."),
    "D05": ("CALCULATE bez filtrů kolem odkazu na míru nic nemění – smaž ho.",
            "CALCULATE without filters around a measure reference changes nothing – remove it."),
    "D06": ("Řetěz IF nahraď SWITCH ( TRUE (), podmínka1, výsledek1, … ) – čitelnější a snáz se rozšiřuje.",
            "Replace the IF chain with SWITCH ( TRUE (), condition1, result1, … ) – more readable and easier to extend."),
    "D07": ("Míru použitou víckrát ulož do VAR – počítá se jednou a výraz je kratší.",
            "Store a measure used several times in a VAR – it is evaluated once and the expression is shorter."),
    "D08": ("Filtr v CALCULATE musí filtrovat sloupec. Porovnání jen měr (např. [Tržby] > 0) Desktop odmítne – "
            "použij FILTER ( VALUES ( Tabulka[Sloupec] ), [Míra] > 0 ).",
            "A CALCULATE filter must filter a column. Desktop rejects a comparison of measures only (e.g. [Sales] > 0) – "
            "use FILTER ( VALUES ( Table[Column] ), [Measure] > 0 )."),
    "D09": ("EARLIER je pozůstatek před proměnnými – ulož hodnotu vnější řádky do VAR, výraz bude čitelnější.",
            "EARLIER is a leftover from before variables – store the outer row's value in a VAR for a more readable expression."),
    "D10": ("USERELATIONSHIP funguje jen se sloupci, mezi kterými v modelu existuje (neaktivní) vztah.",
            "USERELATIONSHIP only works with columns that have an (inactive) relationship in the model."),
    "D11": ("Časové funkce (TOTALYTD, SAMEPERIODLASTYEAR, DATEADD …) potřebují souvislý kalendář. Nad datem z faktové tabulky "
            "(chybí dny bez prodeje) vrací chybné nebo prázdné výsledky – použij sloupec z tabulky kalendáře.",
            "Time intelligence functions (TOTALYTD, SAMEPERIODLASTYEAR, DATEADD …) need a contiguous calendar. On a fact table date "
            "(days without sales are missing) they return wrong or blank results – use the date table column."),
    "D12": ("Rozděl míru na menší pojmenované míry nebo proměnné (VAR); dlouhý vnořený výraz se špatně ladí i čte.",
            "Split the measure into smaller named measures or variables (VAR); a long nested expression is hard to debug and read."),
    "D13": ("Sloupce piš vždy s tabulkou (Prodej[Kč]), míry vždy bez ní ([Tržby]) – jinak nejde na první pohled poznat, co je co.",
            "Always write columns with their table (Sales[Amount]) and measures without it ([Revenue]) – otherwise you can't tell them apart at a glance."),
})


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
            if (n.kod, cesky(n.popis)) in videno:
                continue
            videno.add((n.kod, cesky(n.popis)))
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
                        out.append(Nalez("D08", "chyba", "dax", kde, L(f"Filtr „{arg.strip()[:60]}“ porovnává jen míry – v CALCULATE nejde použít.",
                                           f"Filter \"{arg.strip()[:60]}\" compares only measures – it can't be used in CALCULATE."),
                                         DAX_DOPORUCENI["D08"]))
            elif v.nazev == "USERELATIONSHIP" and len(v.argumenty) == 2:
                a, b = daxlib.sloupec_odkaz(v.argumenty[0]), daxlib.sloupec_odkaz(v.argumenty[1])
                if a and b:
                    akt = pary.get(frozenset({a, b}))
                    if akt is None:
                        out.append(Nalez("D10", "chyba", "dax", kde, L(f"USERELATIONSHIP ( {a[0]}[{a[1]}], {b[0]}[{b[1]}] ) – mezi sloupci není vztah.",
                                           f"USERELATIONSHIP ( {a[0]}[{a[1]}], {b[0]}[{b[1]}] ) – there is no relationship between the columns."),
                                         DAX_DOPORUCENI["D10"]))
                    elif akt:
                        out.append(Nalez("D10", "info", "dax", kde, L(f"USERELATIONSHIP na aktivní vztah {a[0]}[{a[1]}] – {b[0]}[{b[1]}] nic nemění.",
                                           f"USERELATIONSHIP on the active relationship {a[0]}[{a[1]}] – {b[0]}[{b[1]}] changes nothing."),
                                         L("USERELATIONSHIP má smysl jen pro neaktivní vztah – smaž ho, nebo ověř, který vztah má být aktivní.",
                                           "USERELATIONSHIP only makes sense for an inactive relationship – remove it, or check which relationship should be active.")))
            elif v.nazev in ("EARLIER", "EARLIEST"):
                out.append(Nalez("D09", "info", "dax", kde, L(f"Míra používá {v.nazev}.", f"Measure uses {v.nazev}."), DAX_DOPORUCENI["D09"]))
                break
        sk = daxlib.slozitost(m.dax)
        if sk["hloubka"] >= 7 or sk["calculate"] >= 4 or (sk["znaky"] > 500 and not sk["var"]):
            out.append(Nalez("D12", "info", "dax", kde,
                             L(f"Složitá míra: {sk['znaky']} znaků, vnoření {sk['hloubka']}, CALCULATE {sk['calculate']}×"
                               + ("" if sk["var"] else ", bez proměnných") + ".",
                               f"Complex measure: {sk['znaky']} characters, nesting {sk['hloubka']}, CALCULATE {sk['calculate']}×"
                               + ("" if sk["var"] else ", no variables") + "."), DAX_DOPORUCENI["D12"]))
    return out


def spust(p: Projekt) -> list[Nalez]:
    nalezy = []
    for fn in KONTROLY:
        nalezy += fn(p)
    return nalezy
