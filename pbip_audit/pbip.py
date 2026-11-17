"""Načtení Power BI projektu PBIP (report + model) do Python objektů – bez Power BI Desktopu.

    from pbip import Projekt, najdi_reporty
    p = Projekt("cesta/MujReport.pbip")       # nebo složka *.Report, nebo složka s jedním reportem
    p.stranky, p.vizualy, p.zalozky, p.tabulky, p.sloupce, p.miry, p.vztahy, p.role
    for cesta in najdi_reporty("slozka"):     # všechny reporty ve složce (i víc reportů nad sdíleným modelem)
        ...

Podporované formáty:
- report: PBIR (definition/pages/…/visual.json) i starší PBIR-Legacy (jeden report.json),
- model: TMDL (definition/tables/*.tmdl) i TMSL (model.bim); složka *.SemanticModel i starší *.Dataset,
- tenký report (datasetReference byConnection na model v Power BI Service): načte se jen report, model je prázdný,
- role (RLS filtry řádků, OLS skrytí tabulek/sloupců) z definition/roles/*.tmdl nebo model.bim.
Report → model se páruje podle definition.pbir (datasetReference.byPath), ne podle názvu složky.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------- objekty
@dataclass
class Sloupec:
    tabulka: str
    nazev: str
    typ: str = ""
    popis: str = ""
    skryty: bool = False
    format: str = ""
    zdroj: str = ""             # sourceColumn
    vypocet: str = ""           # DAX u počítaného sloupce
    radit_podle: str = ""       # sortByColumn
    slozka: str = ""

    @property
    def plny(self) -> str:
        return f"{self.tabulka}[{self.nazev}]"


@dataclass
class Mira:
    tabulka: str
    nazev: str
    dax: str
    popis: str = ""
    format: str = ""
    skryta: bool = False
    slozka: str = ""

    @property
    def plny(self) -> str:
        return f"[{self.nazev}]"


@dataclass
class Tabulka:
    nazev: str
    popis: str = ""
    skryta: bool = False
    m_vyraz: str = ""           # Power Query / DAX zdroj partition
    vypoctova_skupina: bool = False
    soubor: Path | None = None
    kategorie: str = ""         # dataCategory (Time = označená tabulka kalendáře)


@dataclass
class Vztah:
    z: str                      # Tabulka.Sloupec (strana mnoho)
    do: str                     # Tabulka.Sloupec (strana jedna)
    aktivni: bool = True
    smer: str = ""              # crossFilteringBehavior
    kardinalita_z: str = "many" # fromCardinality
    kardinalita_do: str = "one" # toCardinality
    bezpecnost: str = ""        # securityFilteringBehavior (bothDirections = RLS jde oběma směry)

    @property
    def tabulka_z(self) -> str:
        return _jmeno(_rozdel_odkaz(self.z)[0])

    @property
    def tabulka_do(self) -> str:
        return _jmeno(_rozdel_odkaz(self.do)[0])


@dataclass
class Role:
    nazev: str
    opravneni: str = "read"                                     # modelPermission
    filtry: dict = field(default_factory=dict)                  # tabulka -> DAX filtr řádků (RLS)
    ols_tabulky: set = field(default_factory=set)               # tabulky skryté OLS
    ols_sloupce: set = field(default_factory=set)               # (tabulka, sloupec) skryté OLS
    clenove: int = 0


@dataclass
class Vizual:
    stranka: str
    nazev: str
    data: dict                  # PBIR tvar (starý formát se převádí na stejný tvar)
    cesta: Path | None = None

    @property
    def typ(self) -> str:
        return self.data.get("visual", {}).get("visualType", "skupina" if "visualGroup" in self.data else "?")

    @property
    def skryty(self) -> bool:
        return bool(self.data.get("isHidden"))

    @property
    def titulek(self) -> str:
        """Pevný text titulku; titulek z míry vrací „=Míra“."""
        for t in self.data.get("visual", {}).get("visualContainerObjects", {}).get("title", []):
            text = t.get("properties", {}).get("text", {}).get("expr", {})
            if "Literal" in text:
                return text["Literal"]["Value"].strip("'")
            if "Measure" in text:
                return "=" + text["Measure"].get("Property", "")
        return ""

    def pole(self, bez_selektoru: bool = False) -> set[tuple[str, str]]:
        """Pole modelu, na která vizuál odkazuje (data, filtry, podmíněné formátování): {(Tabulka, Pole)}.
        bez_selektoru=True vynechá selektory formátování (barva konkrétní hodnoty) – ty po smazání pole jen osiří, nic nerozbijí."""
        return set(_najdi_pole(self.data, bez_selektoru))


@dataclass
class Stranka:
    nazev: str                  # interní název (složka / name)
    zobrazeny: str
    sirka: int
    vyska: int
    skryta: bool
    data: dict = field(repr=False, default_factory=dict)


@dataclass
class Zalozka:
    nazev: str
    zobrazeny: str
    stranka: str
    moznosti: dict


# ---------------------------------------------------------------- pomůcky
def _json(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def _jmeno(s: str) -> str:
    s = s.strip()
    return s[1:-1].replace("''", "'") if len(s) > 1 and s.startswith("'") and s.endswith("'") else s


def _odsazeni(radek: str) -> int:
    return len(radek) - len(radek.lstrip("\t"))


def _text(h) -> str:
    """TMSL ukládá dlouhé texty (DAX, M, popis) i jako seznam řádků."""
    return "\n".join(h) if isinstance(h, list) else (h or "")


def _najdi_pole(uzel, bez_selektoru=False):
    if isinstance(uzel, dict):
        if "Property" in uzel and isinstance(uzel.get("Expression"), dict):
            ent = uzel["Expression"].get("SourceRef", {}).get("Entity")
            if ent:
                yield ent, uzel["Property"]
        for k, h in uzel.items():
            if not (bez_selektoru and k == "selector"):
                yield from _najdi_pole(h, bez_selektoru)
    elif isinstance(uzel, list):
        for h in uzel:
            yield from _najdi_pole(h, bez_selektoru)


def _rozdel_deklaraci(zbytek: str) -> tuple[str, str]:
    """„'Název s mezerami' = výraz“ / „Nazev = výraz“ / „Nazev“ -> (název, výraz)."""
    zbytek = zbytek.strip()
    if zbytek.startswith("'"):
        k = 1
        while k < len(zbytek):
            if zbytek[k] == "'":
                if k + 1 < len(zbytek) and zbytek[k + 1] == "'":
                    k += 2; continue
                break
            k += 1
        nazev, zbytek = zbytek[:k + 1], zbytek[k + 1:]
        _, _, vyraz = zbytek.partition("=")
        return _jmeno(nazev), vyraz.strip()
    nazev, _, vyraz = zbytek.partition("=")
    return _jmeno(nazev), vyraz.strip()


def _tmdl_jmeno(n: str) -> str:
    """Název v zápisu TMDL: s uvozovkami, když obsahuje mezery, tečky, diakritiku apod."""
    return n if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) else "'" + n.replace("'", "''") + "'"


def _odkaz(tabulka: str, sloupec: str) -> str:
    return f"{_tmdl_jmeno(tabulka)}.{_tmdl_jmeno(sloupec)}"


def _rozdel_odkaz(odkaz: str) -> tuple[str, str]:
    """„'Moje tabulka'.'Sloupec s tečkou.'“ / „Tabulka.Sloupec“ -> (tabulka, sloupec) – tečka uvnitř uvozovek se nedělí."""
    odkaz, k, v_uvozovkach = odkaz.strip(), 0, False
    while k < len(odkaz):
        if odkaz[k] == "'":
            v_uvozovkach = not v_uvozovkach
        elif odkaz[k] == "." and not v_uvozovkach:
            return odkaz[:k], _jmeno(odkaz[k + 1:])
        k += 1
    return odkaz, ""


def _bez_backticku(vyraz: str) -> str:
    return "\n".join(r for r in vyraz.splitlines() if r.strip() != "```").strip()


# ---------------------------------------------------------------- model: TMDL
def nacti_tmdl_tabulku(soubor: Path):
    """Parser TMDL tabulky: tabulka, sloupce, míry, partition. /// = popis objektu na dalším řádku.
    Bloky, které nečte (hierarchy, calculationItem, variation, annotation …), přeskakuje podle odsazení."""
    radky = soubor.read_text(encoding="utf-8-sig").splitlines()
    tab, sloupce, miry, popis, i = None, [], [], [], 0
    while i < len(radky):
        r, s = radky[i], radky[i].strip()
        o = _odsazeni(r)
        if s.startswith("///"):
            popis.append(s[3:].strip()); i += 1; continue
        if o == 0 and s.startswith("table "):
            tab = Tabulka(_jmeno(s[6:]), " ".join(popis), soubor=soubor); popis = []
        elif o == 1 and tab and (s.startswith("measure ") or s.startswith("column ")):
            druh, zbytek = s.split(" ", 1)
            nazev, vyraz = _rozdel_deklaraci(zbytek)
            ma_vyraz = "=" in zbytek
            vlastnosti, j = {}, i + 1
            while j < len(radky) and (not radky[j].strip() or _odsazeni(radky[j]) >= 2):
                rr, oo = radky[j].strip(), _odsazeni(radky[j])
                if oo >= 3 and ma_vyraz and not vlastnosti:          # pokračování výrazu (před první vlastností)
                    vyraz += "\n" + rr
                elif oo == 2 and rr:
                    k, dvojtecka, h = rr.partition(":")
                    vlastnosti[k.strip()] = h.strip() if dvojtecka else True
                j += 1
            vyraz = _bez_backticku(vyraz)
            if druh == "measure":
                miry.append(Mira(tab.nazev, nazev, vyraz, " ".join(popis), str(vlastnosti.get("formatString", "")).strip('"'),
                                 "isHidden" in vlastnosti, str(vlastnosti.get("displayFolder", ""))))
            else:
                sloupce.append(Sloupec(tab.nazev, nazev, str(vlastnosti.get("dataType", "")), " ".join(popis), "isHidden" in vlastnosti,
                                       str(vlastnosti.get("formatString", "")).strip('"'), str(vlastnosti.get("sourceColumn", "")),
                                       vyraz, _jmeno(str(vlastnosti.get("sortByColumn", ""))), str(vlastnosti.get("displayFolder", ""))))
            popis, i = [], j
            continue
        elif o == 1 and tab and s.startswith("partition "):
            _, vyraz = _rozdel_deklaraci(s[10:])
            j, m = i + 1, []
            while j < len(radky) and (not radky[j].strip() or _odsazeni(radky[j]) >= 2):
                rr = radky[j].strip()
                if _odsazeni(radky[j]) >= 3:
                    m.append(rr)
                elif rr.startswith("source") and "=" in rr:
                    m.append(rr.split("=", 1)[1].strip())
                j += 1
            tab.m_vyraz = _bez_backticku("\n".join(x for x in m if x))
            popis, i = [], j
            continue
        elif o == 1 and tab and s.startswith("calculationGroup"):
            tab.vypoctova_skupina = True
        elif o == 1 and tab and s == "isHidden":
            tab.skryta = True
        elif o == 1 and tab and s.startswith("dataCategory:"):
            tab.kategorie = s.split(":", 1)[1].strip()
        elif s:
            popis = []
        i += 1
    return tab, sloupce, miry


def nacti_tmdl_vztahy(soubor: Path) -> list[Vztah]:
    vztahy, akt = [], None
    if not soubor.exists():
        return vztahy
    for r in soubor.read_text(encoding="utf-8-sig").splitlines():
        s = r.strip()
        if s.startswith("relationship "):
            akt = Vztah("", ""); vztahy.append(akt)
        elif akt and ":" in s:
            k, _, h = s.partition(":")
            h = h.strip()
            if k == "fromColumn":
                akt.z = h
            elif k == "toColumn":
                akt.do = h
            elif k == "isActive":
                akt.aktivni = h != "false"
            elif k == "crossFilteringBehavior":
                akt.smer = h
            elif k == "fromCardinality":
                akt.kardinalita_z = h
            elif k == "toCardinality":
                akt.kardinalita_do = h
            elif k == "securityFilteringBehavior":
                akt.bezpecnost = h
    return vztahy


def nacti_tmdl_roli(soubor: Path) -> Role | None:
    """role Název / modelPermission / tablePermission Tab = filtr (víc řádků) / columnPermission Sl = none / member …"""
    role, tp, i = None, None, 0
    radky = soubor.read_text(encoding="utf-8-sig").splitlines()
    while i < len(radky):
        r, s = radky[i], radky[i].strip()
        o = _odsazeni(r)
        if o == 0 and s.startswith("role "):
            role = Role(_jmeno(s[5:]))
        elif role and o == 1 and s.startswith("modelPermission:"):
            role.opravneni = s.split(":", 1)[1].strip()
        elif role and o == 1 and s.startswith("member "):
            role.clenove += 1
        elif role and o == 1 and s.startswith("tablePermission "):
            tp, vyraz = _rozdel_deklaraci(s[16:])
            j = i + 1
            while j < len(radky) and (not radky[j].strip() or _odsazeni(radky[j]) >= 2):
                rr, oo = radky[j].strip(), _odsazeni(radky[j])
                if oo >= 3 and not rr.startswith("metadataPermission"):
                    vyraz += "\n" + rr
                elif oo == 2 and rr.startswith("metadataPermission:") and rr.split(":", 1)[1].strip() == "none":
                    role.ols_tabulky.add(tp)
                elif oo == 2 and rr.startswith("columnPermission "):
                    sl, h = _rozdel_deklaraci(rr[17:])
                    dalsi = radky[j + 1].strip() if j + 1 < len(radky) else ""
                    if h == "none" or (not h and dalsi.replace(" ", "") == "metadataPermission:none"):
                        role.ols_sloupce.add((tp, sl))
                elif oo == 2 and rr.startswith("filterExpression"):
                    vyraz += rr.partition("=")[2].strip()
                j += 1
            vyraz = _bez_backticku(vyraz)
            if vyraz:
                role.filtry[tp] = vyraz
            i = j
            continue
        i += 1
    return role


# ---------------------------------------------------------------- model: TMSL (model.bim)
def nacti_bim(soubor: Path):
    m = _json(soubor).get("model", {})
    tabulky, sloupce, miry = [], [], []
    for t in m.get("tables", []):
        src = next((_text(p.get("source", {}).get("expression")) for p in t.get("partitions", []) if p.get("source", {}).get("expression")), "")
        tabulky.append(Tabulka(t["name"], _text(t.get("description")), bool(t.get("isHidden")), src, "calculationGroup" in t, soubor,
                               t.get("dataCategory", "")))
        for c in t.get("columns", []):
            if c.get("type") == "rowNumber":
                continue
            sloupce.append(Sloupec(t["name"], c["name"], c.get("dataType", ""), _text(c.get("description")), bool(c.get("isHidden")),
                                   c.get("formatString", ""), c.get("sourceColumn", ""), _text(c.get("expression")),
                                   c.get("sortByColumn", ""), c.get("displayFolder", "")))
        for x in t.get("measures", []):
            miry.append(Mira(t["name"], x["name"], _text(x.get("expression")), _text(x.get("description")), x.get("formatString", ""),
                             bool(x.get("isHidden")), x.get("displayFolder", "")))
    vztahy = [Vztah(_odkaz(r['fromTable'], r['fromColumn']), _odkaz(r['toTable'], r['toColumn']), r.get("isActive", True),
                    r.get("crossFilteringBehavior", ""), r.get("fromCardinality", "many"), r.get("toCardinality", "one"),
                    r.get("securityFilteringBehavior", "")) for r in m.get("relationships", [])]
    role = []
    for r in m.get("roles", []):
        ro = Role(r.get("name", ""), r.get("modelPermission", "read"), clenove=len(r.get("members", [])))
        for tp in r.get("tablePermissions", []):
            if _text(tp.get("filterExpression")):
                ro.filtry[tp["name"]] = _text(tp["filterExpression"])
            if tp.get("metadataPermission") == "none":
                ro.ols_tabulky.add(tp["name"])
            ro.ols_sloupce |= {(tp["name"], c["name"]) for c in tp.get("columnPermissions", []) if c.get("metadataPermission") == "none"}
        role.append(ro)
    return tabulky, sloupce, miry, vztahy, role


# ---------------------------------------------------------------- report: PBIR-Legacy (report.json)
def _rozres_aliasy(uzel, mapa: dict | None = None):
    """SourceRef {"Source": "c"} -> {"Entity": "Tabulka"} – starý formát pak jde číst stejně jako PBIR.
    Aliasy platí jen v rámci dotazu, kde je jejich From (stejný alias „s“ může v jiném filtru znamenat jinou tabulku)."""
    mapa = dict(mapa or {})
    if isinstance(uzel, dict):
        if isinstance(uzel.get("From"), list):
            mapa.update({f["Name"]: f["Entity"] for f in uzel["From"] if isinstance(f, dict) and "Name" in f and "Entity" in f})
        sr = uzel.get("SourceRef")
        if isinstance(sr, dict) and "Source" in sr and "Entity" not in sr and sr["Source"] in mapa:
            uzel["SourceRef"] = {"Entity": mapa[sr["Source"]]}
        for h in uzel.values():
            _rozres_aliasy(h, mapa)
    elif isinstance(uzel, list):
        for h in uzel:
            _rozres_aliasy(h, mapa)
    return uzel


def _nacti_json_retezec(h):
    if isinstance(h, str):
        try:
            return json.loads(h)
        except json.JSONDecodeError:
            return {}
    return h or {}


def nacti_legacy_report(soubor: Path):
    """report.json (PBIR-Legacy) -> stránky, vizuály (v PBIR tvaru), záložky, nastavení reportu."""
    d = _json(soubor)
    cfg = _nacti_json_retezec(d.get("config"))
    stranky, vizualy = [], []
    for sec in sorted(d.get("sections", []), key=lambda x: x.get("ordinal", 0)):
        nazev = sec.get("name", "")
        stranky.append(Stranka(nazev, sec.get("displayName", nazev), int(sec.get("width", 0)), int(sec.get("height", 0)),
                               _nacti_json_retezec(sec.get("config")).get("visibility") == 1, sec))
        for vc in sec.get("visualContainers", []):
            c = _nacti_json_retezec(vc.get("config"))
            filtry = _nacti_json_retezec(vc.get("filters"))
            sv = c.get("singleVisual") or {}
            visual = {"visualType": sv.get("visualType", "skupina" if "singleVisualGroup" in c else "?"),
                      "query": sv.get("prototypeQuery", {}), "projections": sv.get("projections", {}),
                      "objects": sv.get("objects", {}), "visualContainerObjects": sv.get("vcObjects", {})}
            data = {"name": c.get("name", ""), "visual": visual, "filters": filtry,
                    "position": {k: vc.get(k, 0) for k in ("x", "y", "z", "width", "height")}}
            if "singleVisualGroup" in c:
                data["visualGroup"] = c["singleVisualGroup"]
            if sv.get("display", {}).get("mode") == "hidden" or c.get("isHidden"):
                data["isHidden"] = True
            vizualy.append(Vizual(nazev, data["name"], _rozres_aliasy(data)))
    zalozky = []
    for b in cfg.get("bookmarks", []):
        for x in [b] + b.get("children", []):
            if "explorationState" in x:
                zalozky.append(Zalozka(x.get("name", ""), x.get("displayName", ""), x["explorationState"].get("activeSection", ""),
                                       x.get("options", {})))
    return stranky, vizualy, zalozky, {"themeCollection": cfg.get("themeCollection", {})}


# ---------------------------------------------------------------- projekt
def najdi_reporty(slozka: str | Path) -> list[Path]:
    """Všechny reporty (složky *.Report) ve složce a podsložkách."""
    return sorted(p for p in Path(slozka).rglob("*.Report") if p.is_dir() and ".git" not in p.parts)


class Projekt:
    def __init__(self, cesta: str | Path):
        self.report_dir = self._najdi_report(Path(cesta))
        self.nazev = self.report_dir.name.removesuffix(".Report")
        self.model_dir, self.model_pripojeni = self._najdi_model()
        self.format_reportu, self.format_modelu = "", ""
        self._nacti_report()
        self._nacti_model()

    # --- hledání report → model
    @staticmethod
    def _najdi_report(cesta: Path) -> Path:
        if cesta.suffix == ".Report" and cesta.is_dir():
            return cesta
        if cesta.suffix == ".pbip" and cesta.is_file():
            for a in _json(cesta).get("artifacts", []):
                if "report" in a:
                    return (cesta.parent / a["report"]["path"]).resolve()
            raise FileNotFoundError(f"{cesta.name} neodkazuje na žádný report.")
        reporty = sorted(cesta.glob("*.Report"))
        if len(reporty) == 1:
            return reporty[0]
        if not reporty:
            raise FileNotFoundError(f"V {cesta} není složka *.Report (projekt PBIP).")
        raise ValueError(f"V {cesta} je {len(reporty)} reportů ({', '.join(r.name for r in reporty)}) – zadej .pbip nebo složku "
                         f"*.Report, případně použij najdi_reporty() / audit.py --vse.")

    def _najdi_model(self) -> tuple[Path | None, str]:
        pbir = self.report_dir / "definition.pbir"
        if pbir.exists():
            ref = _json(pbir).get("datasetReference", {})
            if ref.get("byPath", {}).get("path"):
                return (self.report_dir / ref["byPath"]["path"]).resolve(), ""
            if ref.get("byConnection"):
                return None, str(ref["byConnection"].get("connectionString", "model v Power BI Service"))[:120]
        for pripona in (".SemanticModel", ".Dataset"):     # bez definition.pbir: stejnojmenná složka vedle reportu
            m = self.report_dir.with_name(self.nazev + pripona)
            if m.exists():
                return m, ""
        return None, ""

    # --- report
    def _nacti_report(self):
        pages = self.report_dir / "definition" / "pages"
        self.stranky, self.vizualy, self.zalozky = [], [], []
        if (pages / "pages.json").exists():
            self.format_reportu = "PBIR"
            poradi = _json(pages / "pages.json").get("pageOrder", []) or sorted(p.name for p in pages.iterdir() if p.is_dir())
            for st in poradi:
                if not (pages / st / "page.json").exists():
                    continue
                d = _json(pages / st / "page.json")
                self.stranky.append(Stranka(st, d.get("displayName", st), int(d.get("width", 0)), int(d.get("height", 0)),
                                            d.get("visibility") == "HiddenInViewMode", d))
                for f in sorted((pages / st / "visuals").glob("*/visual.json")):
                    self.vizualy.append(Vizual(st, f.parent.name, _json(f), f))
            for f in sorted((self.report_dir / "definition" / "bookmarks").glob("*.bookmark.json")):
                d = _json(f)
                self.zalozky.append(Zalozka(d.get("name", f.stem), d.get("displayName", ""),
                                            d.get("explorationState", {}).get("activeSection", ""), d.get("options", {})))
            rj = self.report_dir / "definition" / "report.json"
            self.report_json = _json(rj) if rj.exists() else {}
        elif (self.report_dir / "report.json").exists():
            self.format_reportu = "PBIR-Legacy (report.json)"
            self.stranky, self.vizualy, self.zalozky, self.report_json = nacti_legacy_report(self.report_dir / "report.json")
        else:
            raise FileNotFoundError(f"{self.report_dir.name}: nenalezen definition/pages ani report.json.")

    # --- model
    def _nacti_model(self):
        self.tabulky, self.sloupce, self.miry, self.vztahy, self.role = [], [], [], [], []
        if self.model_dir is None:
            self.format_modelu = f"tenký report – model není v projektu ({self.model_pripojeni})" if self.model_pripojeni else "model nenalezen"
            return
        tabulky = self.model_dir / "definition" / "tables"
        if tabulky.exists():
            self.format_modelu = "TMDL"
            for f in sorted(tabulky.glob("*.tmdl")):
                t, s, m = nacti_tmdl_tabulku(f)
                if t:
                    self.tabulky.append(t); self.sloupce += s; self.miry += m
            self.vztahy = nacti_tmdl_vztahy(self.model_dir / "definition" / "relationships.tmdl")
            self.role = [r for r in (nacti_tmdl_roli(f) for f in sorted((self.model_dir / "definition" / "roles").glob("*.tmdl"))) if r]
        elif (self.model_dir / "model.bim").exists():
            self.format_modelu = "TMSL (model.bim)"
            self.tabulky, self.sloupce, self.miry, self.vztahy, self.role = nacti_bim(self.model_dir / "model.bim")
        else:
            self.format_modelu = "model bez definice (TMDL ani model.bim)"

    # --- pomůcky
    @property
    def report_def(self) -> Path:
        """Složka definition reportu (pro skripty, které report upravují – jen PBIR)."""
        return self.report_dir / "definition"

    def stranka(self, nazev: str) -> Stranka | None:
        return next((s for s in self.stranky if s.nazev == nazev), None)

    def kde(self, v: Vizual) -> str:
        """Čitelné umístění vizuálu: „Zobrazený název stránky / titulek nebo typ (id)“."""
        st = self.stranka(v.stranka)
        jmeno = v.titulek if v.titulek and not v.titulek.startswith("=") else v.typ
        return f"{st.zobrazeny if st else v.stranka} / {jmeno} ({v.nazev[:8]})"

    def pouzita_pole(self, bez_selektoru: bool = False) -> dict[tuple[str, str], list[str]]:
        """(Tabulka, Pole) -> seznam „stránka/vizuál“, kde se pole používá."""
        out: dict[tuple[str, str], list[str]] = {}
        for v in self.vizualy:
            for p in v.pole(bez_selektoru):
                out.setdefault(p, []).append(self.kde(v))
        return out


def dax_odkazy(dax: str) -> tuple[set[str], set[tuple[str, str]]]:
    """Z DAX výrazu vytáhne odkazy na míry [Míra] a sloupce Tabulka[Sloupec] / 'Tabulka'[Sloupec]."""
    bez = re.sub(r'"(?:[^"]|"")*"', '""', dax)
    bez = re.sub(r"//[^\n]*|--[^\n]*|/\*.*?\*/", "", bez, flags=re.S)     # komentáře
    sloupce = {(_jmeno(t), c) for t, c in re.findall(r"('(?:[^']|'')+'|[A-Za-z_][\w.]*)\s*\[([^\]]+)\]", bez)}
    vse = set(re.findall(r"\[([^\]]+)\]", bez))
    return vse - {c for _, c in sloupce}, sloupce
