"""Testy nástrojů pbip_audit na malých syntetických projektech PBIP (vytvoří se v tmp_path):
PBIR + TMDL s nastraženými chybami, starý report.json + model.bim, tenký report a dva reporty nad jedním modelem."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kontroly import spust  # noqa: E402
from pbip import Projekt, dax_odkazy, najdi_reporty  # noqa: E402


def zapis(p: Path, obsah):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obsah if isinstance(obsah, str) else json.dumps(obsah, ensure_ascii=False), encoding="utf-8")


def sloupec_ref(tab, pole, klic="Column"):
    return {klic: {"Expression": {"SourceRef": {"Entity": tab}}, "Property": pole}}


TMDL_PRODEJ = """/// Prodeje, 1 řádek = položka objednávky.
table Prodej
\tlineageTag: a

\t/// Tržby v Kč.
\tmeasure Tržby = SUM ( Prodej[Částka] )
\t\tformatString: #,0

\tmeasure 'Tržby bez popisu' =
\t\t\tVAR x = [Tržby]
\t\t\tRETURN x * 2
\t\tformatString: #,0

\tmeasure Rozbitá = [Neexistující míra] + Prodej[Neexistující sloupec]

\tmeasure Částka = 1

\tmeasure Konstruktor = SUMX ( { ( 1, 2 ) }, [Value1] + [Value2] )
\t\tformatString: 0

\tmeasure Blok = ```
\t\t\tVAR a = 1
\t\t\tRETURN a
\t\t\t```
\t\tformatString: 0

\tcolumn Částka
\t\tdataType: double
\t\tsourceColumn: Částka

\tcolumn ProduktKey
\t\tdataType: int64
\t\tsourceColumn: ProduktKey

\tcolumn Nepoužitý
\t\tdataType: string
\t\tsourceColumn: Nepoužitý

\t\tvariation Variace
\t\t\tisDefault
\t\t\trelationship: abc

\thierarchy H
\t\tlevel L
\t\t\tcolumn: Částka

\tpartition Prodej = m
\t\tmode: import
\t\tsource =
\t\t\t\tlet
\t\t\t\t    Zdroj = 1
\t\t\t\tin
\t\t\t\t    Zdroj
"""

TMDL_PRODUKT = """table Produkt

\tcolumn ProduktKey
\t\tdataType: int64
\t\tisHidden
\t\tsourceColumn: ProduktKey

\tcolumn Název
\t\tdataType: string
\t\tsourceColumn: Název
"""


def pbir_projekt(koren: Path, nazev="Mini", model="Mini"):
    rep = koren / f"{nazev}.Report"
    zapis(koren / f"{nazev}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": f"{nazev}.Report"}}]})
    zapis(rep / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{model}.SemanticModel"}}})
    zapis(rep / "definition" / "report.json", {"themeCollection": {"baseTheme": {"name": "x"}}})
    zapis(rep / "definition" / "pages" / "pages.json", {"pageOrder": ["s1"]})
    zapis(rep / "definition" / "pages" / "s1" / "page.json", {"name": "s1", "displayName": "Strana", "width": 1280, "height": 720})
    graf = {"name": "graf", "position": {"x": 0, "y": 0, "z": 0, "width": 600, "height": 300},
            "visual": {"visualType": "clusteredBarChart",
                       "query": {"queryState": {"Category": {"projections": [{"field": sloupec_ref("Produkt", "Název")}]},
                                                "Y": {"projections": [{"field": sloupec_ref("Prodej", "Tržby", "Measure")}]}}},
                       "objects": {"dataPoint": [{"properties": {}, "selector": {"data": [{"scopeId": {"Comparison": {
                           "Left": sloupec_ref("Produkt", "Smazaný"), "Right": {"Literal": {"Value": "'A'"}}}}}]}}]}}}
    rozbity = {"name": "rozbity", "position": {"x": 0, "y": 400, "z": 1, "width": 300, "height": 200},
               "visual": {"visualType": "tableEx", "query": {"queryState": {"Values": {"projections": [{"field": sloupec_ref("Prodej", "Zmizelý")}]}}}}}
    slicer = {"name": "slicer", "position": {"x": 700, "y": 0, "z": 2, "width": 200, "height": 60},
              "visual": {"visualType": "slicer", "objects": {"general": [{"properties": {"filter": {"filter": {"Where": [
                  {"Condition": {"In": {"Values": [[{"Literal": {"Value": "'Praha'"}}]]}}}]}}}}]}}}
    for v in (graf, rozbity, slicer):
        zapis(rep / "definition" / "pages" / "s1" / "visuals" / v["name"] / "visual.json", v)
    zapis(rep / "definition" / "bookmarks" / "b1.bookmark.json",
          {"name": "b1", "displayName": "Záložka", "options": {}, "explorationState": {"activeSection": "s1"}})
    md = koren / f"{model}.SemanticModel" / "definition"
    zapis(md / "tables" / "Prodej.tmdl", TMDL_PRODEJ)
    zapis(md / "tables" / "Produkt.tmdl", TMDL_PRODUKT)
    zapis(md / "relationships.tmdl", "relationship r1\n\tfromColumn: Prodej.ProduktKey\n\ttoColumn: Produkt.ProduktKey\n\tcrossFilteringBehavior: bothDirections\n")
    return koren / f"{nazev}.pbip"


def legacy_projekt(koren: Path):
    rep = koren / "Stary.Report"
    zapis(rep / "definition.pbir", {"version": "1.0", "datasetReference": {"byPath": {"path": "../Stary.Dataset"}}})
    dotaz_a = {"From": [{"Name": "s", "Entity": "Prodej", "Type": 0}],
               "Select": [{"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Tržby"}}]}
    filtr_b = [{"filter": {"From": [{"Name": "s", "Entity": "Kategorie", "Type": 0}],
                           "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Typ"}}]}}}]}}]
    cfg = {"name": "v1", "singleVisual": {"visualType": "card", "prototypeQuery": dotaz_a}}
    zapis(rep / "report.json", {"config": json.dumps({"themeCollection": {}}), "sections": [{
        "name": "ReportSection1", "displayName": "Přehled", "ordinal": 0, "width": 1280, "height": 720,
        "visualContainers": [{"x": 0, "y": 0, "z": 0, "width": 200, "height": 100, "config": json.dumps(cfg), "filters": json.dumps(filtr_b)}]}]})
    zapis(koren / "Stary.Dataset" / "model.bim", {"model": {"tables": [
        {"name": "Prodej", "description": ["Prodeje"], "columns": [{"name": "Částka", "dataType": "double"}],
         "measures": [{"name": "Tržby", "expression": ["SUM ( Prodej[Částka] )"], "formatString": "#,0"}],
         "partitions": [{"source": {"type": "m", "expression": ["let", "x = 1", "in x"]}}]},
        {"name": "Kategorie", "columns": [{"name": "Typ", "dataType": "string"}]}],
        "relationships": [{"fromTable": "Prodej", "fromColumn": "Částka", "toTable": "Kategorie", "toColumn": "Typ", "isActive": False}]}})
    return rep


# ------------------------------------------------------------------ testy
def test_pbir_tmdl_nacteni(tmp_path):
    p = Projekt(pbir_projekt(tmp_path))
    assert (p.format_reportu, p.format_modelu) == ("PBIR", "TMDL")
    assert [t.nazev for t in p.tabulky] == ["Prodej", "Produkt"]
    miry = {m.nazev: m for m in p.miry}
    assert set(miry) == {"Tržby", "Tržby bez popisu", "Rozbitá", "Částka", "Konstruktor", "Blok"}
    assert miry["Tržby"].popis == "Tržby v Kč." and miry["Tržby"].format == "#,0"
    assert "RETURN x * 2" in miry["Tržby bez popisu"].dax
    assert miry["Blok"].dax == "VAR a = 1\nRETURN a"                       # bez ```
    sl = {s.nazev: s for s in p.sloupce}
    assert sl["Nepoužitý"].vypocet == ""                                    # variation se nepočítá do výrazu
    assert p.tabulky[0].popis.startswith("Prodeje") and "Zdroj = 1" in p.tabulky[0].m_vyraz
    assert p.vztahy[0].smer == "bothDirections"


def test_kontroly_najdou_nastrazene_chyby(tmp_path):
    kody = {}
    for n in spust(Projekt(pbir_projekt(tmp_path))):
        kody.setdefault(n.kod, []).append(n)
    popisy = " | ".join(n.popis for n in kody.get("M11", []))
    assert "[Neexistující míra]" in popisy and "Prodej[Neexistující sloupec]" in popisy
    assert "Value1" not in popisy and "[x]" not in popisy                  # proměnné a implicitní sloupce nejsou chyby
    assert any("stejný název jako sloupec" in n.popis for n in kody["M10"])
    assert any(n.objekt == "Prodej[ProduktKey]" for n in kody["M06"])
    assert any(n.objekt == "Prodej[Nepoužitý]" for n in kody["M05"])
    assert any("Prodej[Zmizelý]" in n.popis for n in kody["R11"])
    assert not any("Smazaný" in n.popis for n in kody["R11"])               # osiřelý selektor není chyba …
    assert any("Smazaný" in n.popis for n in kody["R13"])                   # … ale info
    assert "M08" in kody and "R08" in kody and "R09" in kody and "R12" in kody


def test_legacy_report_a_model_bim(tmp_path):
    p = Projekt(legacy_projekt(tmp_path))
    assert p.format_reportu.startswith("PBIR-Legacy") and p.format_modelu.startswith("TMSL")
    assert p.stranky[0].zobrazeny == "Přehled"
    # stejný alias „s“ ve dvou dotazech = dvě různé tabulky
    assert p.vizualy[0].pole() == {("Prodej", "Tržby"), ("Kategorie", "Typ")}
    assert p.miry[0].dax == "SUM ( Prodej[Částka] )" and p.tabulky[0].popis == "Prodeje"
    assert p.vztahy[0].aktivni is False
    chyby = [n for n in spust(p) if n.uroven == "chyba"]
    assert [n.kod for n in chyby] == ["M20"]                                 # fixture spojuje double × string – M20 ho najde


def test_tenky_report(tmp_path):
    rep = tmp_path / "Tenky.Report"
    zapis(rep / "definition.pbir", {"version": "4.0", "datasetReference": {"byConnection": {"connectionString": "Data Source=powerbi://x"}}})
    zapis(rep / "definition" / "pages" / "pages.json", {"pageOrder": []})
    p = Projekt(rep)
    assert p.model_dir is None and p.format_modelu.startswith("tenký report") and p.tabulky == []
    spust(p)                                                                # kontroly modelu se přeskočí bez chyby


def test_vic_reportu_nad_jednim_modelem(tmp_path):
    pbir_projekt(tmp_path, "R1", "Spolecny")
    pbir_projekt(tmp_path, "R2", "Spolecny")
    with pytest.raises(ValueError):
        Projekt(tmp_path)                                                   # nejednoznačné – víc reportů
    reporty = najdi_reporty(tmp_path)
    assert [r.name for r in reporty] == ["R1.Report", "R2.Report"]
    assert Projekt(tmp_path / "R2.pbip").model_dir.name == "Spolecny.SemanticModel"


def test_dax_odkazy():
    miry, sloupce = dax_odkazy("CALCULATE ( [Tržby], 'Moje tabulka'[Rok] = 2024, Prodej[Kč] > 0 ) // [Komentář]\n\"[ne]\"")
    assert miry == {"Tržby"} and sloupce == {("Moje tabulka", "Rok"), ("Prodej", "Kč")}


# ------------------------------------------------------------------ nové kontroly modelu, RLS, skóre, porovnání, opravy
TMDL_FAKT = "table Fakt\n" + "".join(
    f"\n\tmeasure 'Ukazatel {chr(65 + i)}' = SUM ( Fakt[Částka] ) * {i}\n\t\tformatString: #,0\n" for i in range(8)) + """
\tmeasure 'Measure 23' = SUM ( Fakt[Částka] )
\t\tformatString: #,0

\tmeasure Trzby = SUM(Fakt[Částka])
\t\tformatString: #,0

\tmeasure Obal = [Trzby]
\t\tformatString: #,0

\tmeasure 'Marže %' = DIVIDE ( 1, 2 )
\t\tformatString: 0.00

\tcolumn Částka
\t\tdataType: double
\t\tsourceColumn: Částka

\tcolumn Datum
\t\tdataType: dateTime
\t\tsourceColumn: Datum

\tcolumn ZakaznikKey
\t\tdataType: int64
\t\tisHidden
\t\tsourceColumn: ZakaznikKey

\tcolumn Mena
\t\tdataType: string
\t\tisHidden
\t\tsourceColumn: Mena

\tcolumn Dvojnasobek = Fakt[Částka] * 2
\t\tdataType: double
"""
TMDL_DIM = {
    "Kalendar": "table Kalendar\n\n\tcolumn Datum\n\t\tdataType: dateTime\n\t\tisKey\n\t\tsourceColumn: Datum\n",
    "Zakaznik": "table Zakaznik\n\n\tcolumn ZakaznikKey\n\t\tdataType: int64\n\t\tisHidden\n\t\tsourceColumn: ZakaznikKey\n\n"
                "\tcolumn Region\n\t\tdataType: string\n\t\tsourceColumn: Region\n\n\tcolumn Email\n\t\tdataType: string\n\t\tsourceColumn: Email\n",
    "Kurzy": "table Kurzy\n\n\tcolumn Mena\n\t\tdataType: string\n\t\tsourceColumn: Mena\n\n\tcolumn Kurz\n\t\tdataType: double\n\t\tsourceColumn: Kurz\n",
    "Osirela": "table Osirela\n\n\tcolumn 'Kód měny'\n\t\tdataType: string\n\t\tsourceColumn: K\n\n\tpartition Osirela = m\n\t\tsource = Csv.Document(1)\n",
    "Parametr": "table Parametr\n\n\tcolumn Hodnota\n\t\tdataType: int64\n\t\tsourceColumn: [Value]\n\n"
                "\tpartition Parametr = calculated\n\t\tsource = GENERATESERIES ( 1, 10 )\n",
}
VZTAHY = """relationship r1
\tfromColumn: Fakt.Datum
\ttoColumn: Kalendar.Datum

relationship r2
\tfromColumn: Fakt.ZakaznikKey
\ttoColumn: Zakaznik.ZakaznikKey

relationship r3
\ttoCardinality: many
\tfromColumn: Fakt.Mena
\ttoColumn: Kurzy.Mena
"""


def model_projekt(koren: Path, role: dict | None = None, vztahy: str = VZTAHY) -> Path:
    """PBIR report se slicerem na odpojené tabulce + model se zakázanými vzory a volitelně rolemi."""
    pbir_projekt(koren, "Novy", "Novy")
    md = koren / "Novy.SemanticModel" / "definition"
    for f in md.joinpath("tables").glob("*.tmdl"):
        f.unlink()
    zapis(md / "tables" / "Fakt.tmdl", TMDL_FAKT)
    for n, t in TMDL_DIM.items():
        zapis(md / "tables" / f"{n}.tmdl", t)
    zapis(md / "relationships.tmdl", vztahy)
    for n, t in (role or {}).items():
        zapis(md / "roles" / f"{n}.tmdl", t)
    vis = koren / "Novy.Report" / "definition" / "pages" / "s1" / "visuals"
    for v in vis.iterdir():
        for f in v.iterdir():
            f.unlink()
        v.rmdir()
    zapis(vis / "sl" / "visual.json", {"name": "sl", "position": {"x": 0, "y": 0, "z": 0, "width": 100, "height": 50},
                                       "visual": {"visualType": "slicer", "query": {"queryState": {"Values": {"projections": [
                                           {"field": sloupec_ref("Osirela", "Kód měny")}]}}}}})
    zapis(vis / "graf" / "visual.json", {"name": "graf", "position": {"x": 200, "y": 0, "z": 1, "width": 300, "height": 200},
                                         "visual": {"visualType": "columnChart", "query": {"queryState": {
                                             "Category": {"projections": [{"field": sloupec_ref("Zakaznik", "Email")}]},
                                             "Y": {"projections": [{"field": sloupec_ref("Fakt", "Trzby", "Measure")}]}}}}})
    return koren / "Novy.pbip"


def nalezy_podle_kodu(p):
    kody = {}
    for n in spust(p):
        kody.setdefault(n.kod, []).append(n)
    return kody


def test_nove_kontroly_modelu(tmp_path):
    p = Projekt(model_projekt(tmp_path))
    k = nalezy_podle_kodu(p)
    assert k["M12"][0].objekt == "Kalendar"                                 # datum jako cíl vztahu, kalendář neoznačen
    assert {n.objekt for n in k["M13"]} == {"Fakt[Measure 23]"}
    assert k["M14"][0].objekt == "Fakt" and "12 z 12" in k["M14"][0].popis
    assert [n.objekt for n in k["M15"] if n.uroven == "varovani"] == ["Osirela"]
    assert not any(n.objekt == "Parametr" and n.uroven == "varovani" for n in k["M15"])  # GENERATESERIES = parametr
    assert [n.objekt for n in k["M16"]] == ["Fakt[Marže %]"]
    dup = [n for n in k["M17"] if n.uroven == "varovani"]
    assert len(dup) == 1 and "[Measure 23]" in dup[0].objekt and "[Trzby]" in dup[0].objekt   # bílé znaky se ignorují
    assert any(n.objekt == "Fakt[Obal]" for n in k["M17"] if n.uroven == "info")
    assert len(k["M18"]) == 1 and [n.objekt for n in k["M19"]] == ["Fakt[Dvojnasobek]"]
    assert "Osirela[Kód měny]" in k["R14"][0].popis
    assert not any(n.objekt.startswith("Fakt[Marže") for n in k.get("M04", []))   # procenta řeší M16, ne M04
    assert "S01" not in k and "S02" not in k                                # bez rolí žádné RLS nálezy


def test_kalendar_oznaceny_bez_nalezu(tmp_path):
    TMDL = TMDL_DIM["Kalendar"].replace("table Kalendar\n", "table Kalendar\n\tdataCategory: Time\n")
    projekt = model_projekt(tmp_path)
    zapis(tmp_path / "Novy.SemanticModel" / "definition" / "tables" / "Kalendar.tmdl", TMDL)
    p = Projekt(projekt)
    assert next(t for t in p.tabulky if t.nazev == "Kalendar").kategorie == "Time"
    assert "M12" not in nalezy_podle_kodu(p)


ROLE = {
    "Region": "role Region\n\tmodelPermission: read\n\n\ttablePermission Zakaznik = [Region] = \"Morava\"\n",
    "Kurzy": "role 'Jen kurzy'\n\tmodelPermission: read\n\n\ttablePermission Kurzy =\n\t\t\tVAR u = USERNAME()\n"
             "\t\t\tRETURN Kurzy[Mena] = u && Kurzy[Neni] = 1\n",
    "Fakt": "role Fakt\n\ttablePermission Fakt = Fakt[Částka] > 0\n\n\ttablePermission Zakaznik\n\t\tcolumnPermission Email = none\n",
    "Vse": "role Vse\n\tmodelPermission: read\n",
}


def test_rls(tmp_path):
    p = Projekt(model_projekt(tmp_path, ROLE))
    role = {r.nazev: r for r in p.role}
    assert set(role) == {"Region", "Jen kurzy", "Fakt", "Vse"}
    assert role["Jen kurzy"].filtry["Kurzy"].startswith("VAR u = USERNAME()\nRETURN")
    assert role["Fakt"].ols_sloupce == {("Zakaznik", "Email")}
    k = nalezy_podle_kodu(p)
    # Region: filtr na dimenzi dojde k faktu (1:N); k Osirela ne – tabulka s daty bez vztahu
    region = {n.objekt.split(" → ")[1] for n in k["S02"] if n.objekt.startswith("role Region")}
    assert "Fakt" not in region and "Osirela" in region
    assert any(n.objekt == "role Region → Kalendar" for n in k["S08"])       # dimenze = jen info
    # n:n vztah s jedním směrem filtruje ze strany „do“ (Kurzy) na Fakt: filtr na Kurzy k faktu dojde, opačně ne
    assert not any(n.objekt == "role Jen kurzy → Fakt" for n in k.get("S02", []))
    assert any(n.objekt == "role Fakt → Kurzy" and "proti směru" in n.popis for n in k["S02"])
    assert any("Kurzy[Neni]" in n.popis for n in k["S01"])
    assert any(n.objekt.startswith("role Jen kurzy") for n in k["S06"])
    assert any(n.objekt.startswith("role Fakt") for n in k["S07"])           # filtr přímo na faktu
    assert any("Zakaznik[Email]" in n.popis and n.uroven == "chyba" for n in k["S05"])   # OLS pole ve vizuálu
    assert [n.objekt for n in k["S04"]] == ["role Vse"]


def test_rls_bezpecnost_obema_smery(tmp_path):
    vztahy = VZTAHY.replace("\ttoCardinality: many\n", "\ttoCardinality: many\n\tcrossFilteringBehavior: bothDirections\n"
                                                      "\tsecurityFilteringBehavior: bothDirections\n")
    p = Projekt(model_projekt(tmp_path, {"Fakt": ROLE["Fakt"]}, vztahy))
    k = nalezy_podle_kodu(p)
    assert not any(n.objekt == "role Fakt → Kurzy" for n in k.get("S02", []))      # teď filtr dojde i ke Kurzům
    assert len(k["S03"]) == 1


def test_rls_model_bim(tmp_path):
    legacy_projekt(tmp_path)
    bim = tmp_path / "Stary.Dataset" / "model.bim"
    d = json.loads(bim.read_text(encoding="utf-8"))
    d["model"]["relationships"][0]["isActive"] = True
    d["model"]["roles"] = [{"name": "R", "modelPermission": "read", "members": [{"memberName": "a@b.cz"}],
                            "tablePermissions": [{"name": "Prodej", "filterExpression": "Prodej[Částka] > 0",
                                                  "columnPermissions": [{"name": "Částka", "metadataPermission": "none"}]}]}]
    d["model"]["tables"][1]["dataCategory"] = "Time"
    zapis(bim, d)
    p = Projekt(tmp_path / "Stary.Report")
    assert p.role[0].clenove == 1 and p.role[0].ols_sloupce == {("Prodej", "Částka")}
    assert p.tabulky[1].kategorie == "Time"
    k = nalezy_podle_kodu(p)
    assert any("Prodej[Částka]" in n.popis for n in k["S05"])                # míra Tržby používá pole skryté OLS


def test_skore_ai(tmp_path):
    from audit import VAHY_AI, skore_ai
    assert abs(sum(VAHY_AI.values()) - 1) < 1e-9
    sk = skore_ai(Projekt(model_projekt(tmp_path)))
    assert sk["označený kalendář"] == 0 and sk["míry ve složkách"] == 0
    assert set(sk) == {"skore", *VAHY_AI} and 0 <= sk["skore"] <= 100


def test_porovnej(tmp_path, monkeypatch):
    import porovnej
    pred = model_projekt(tmp_path / "a")
    po = model_projekt(tmp_path / "b")
    zapis(tmp_path / "b" / "Novy.SemanticModel" / "definition" / "tables" / "Kalendar.tmdl",
          TMDL_DIM["Kalendar"].replace("table Kalendar\n", "table Kalendar\n\tdataCategory: Time\n"))
    monkeypatch.setattr(sys, "argv", ["porovnej.py", str(pred), str(po), "--vystup", str(tmp_path / "out")])
    porovnej.main()
    md = (tmp_path / "out" / "porovnani_Novy_Novy.md").read_text(encoding="utf-8")
    assert "| označený kalendář | 5 % | 0 | 100 | +100 |" in md and "| M12 |" in md
    assert "Vyřešené chyby a varování (1)" in md


def test_oprav_sablona_a_zapis(tmp_path):
    import csv
    from oprav import nacti_navrh, proved, sablona
    projekt = model_projekt(tmp_path)
    fakt = tmp_path / "Novy.SemanticModel" / "definition" / "tables" / "Fakt.tmdl"
    fakt.write_bytes(b"\xef\xbb\xbf" + fakt.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))  # BOM + CRLF
    p = Projekt(projekt)
    navrh = tmp_path / "navrh.csv"
    sablona(p, navrh)
    radky = nacti_navrh(navrh)
    assert {r["akce"] for r in radky} >= {"popis", "slozka", "format"}
    assert any(r["objekt"] == "Fakt[Marže %]" and r["akce"] == "format" and r["hodnota"] == "0.0%" for r in radky)
    for r in radky:
        r["hodnota"] = r["hodnota"] or {"popis": "Popis s 'apostrofem'.", "slozka": "01 Prodej", "format": "#,0", "skryt": "ano"}[r["akce"]]
    radky.append({"objekt": "Zakaznik[Region]", "typ": "", "akce": "skryt", "hodnota": "ano"})
    radky.append({"objekt": "Neni[Nic]", "typ": "", "akce": "popis", "hodnota": "x"})
    with open(navrh, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["objekt", "typ", "akce", "hodnota", "nalez", "kontext"], delimiter=";", extrasaction="ignore")
        w.writeheader(); w.writerows(radky)
    pred = fakt.read_bytes()
    proved(p, nacti_navrh(navrh), zapsat=False)
    assert fakt.read_bytes() == pred                                         # náhled nic nemění
    proved(p, nacti_navrh(navrh), zapsat=True)
    surove = fakt.read_bytes()
    assert surove.startswith(b"\xef\xbb\xbf") and b"\r\n" in surove and b"\n" not in surove.replace(b"\r\n", b"")
    q = Projekt(projekt)
    miry = {m.nazev: m for m in q.miry}
    assert miry["Measure 23"].popis == "Popis s 'apostrofem'." and miry["Measure 23"].slozka == "01 Prodej"
    assert miry["Marže %"].format == "0.0%" and miry["Trzby"].dax == "SUM(Fakt[Částka])"
    assert next(s for s in q.sloupce if s.plny == "Zakaznik[Region]").skryty
    assert (len(q.miry), len(q.sloupce), len(q.tabulky)) == (len(p.miry), len(p.sloupce), len(p.tabulky))
    k = nalezy_podle_kodu(q)
    assert "M01" not in k and "M14" not in k and "M16" not in k
    po = fakt.read_bytes()
    proved(q, nacti_navrh(navrh), zapsat=True)                              # podruhé: nic nového
    assert fakt.read_bytes() == po


# ------------------------------------------------------------------ M20–M24, id, nastavení, baseline, exit kódy, pojistka parseru
def test_typy_ve_vztazich(tmp_path):
    vztahy = VZTAHY + "\nrelationship r4\n\tfromColumn: Fakt.Datum\n\ttoColumn: Zakaznik.ZakaznikKey\n" \
                      "\nrelationship r5\n\tfromColumn: Fakt.Mena\n\ttoColumn: Osirela.'Kód měny'\n"
    k = nalezy_podle_kodu(Projekt(model_projekt(tmp_path, vztahy=vztahy)))
    assert [n.objekt for n in k["M20"]] == ["Fakt.Datum → Zakaznik.ZakaznikKey"] and "dateTime × int64" in k["M20"][0].popis
    assert [n.objekt for n in k["M21"]] == ["Fakt.Mena → Osirela.'Kód měny'"]  # n:n Fakt→Kurzy (text) se nehlásí


def test_cyklus_mer(tmp_path):
    projekt = model_projekt(tmp_path)
    f = tmp_path / "Novy.SemanticModel" / "definition" / "tables" / "Fakt.tmdl"
    f.write_text(f.read_text(encoding="utf-8") + "\n\tmeasure Ax = [Bx] + 1\n\n\tmeasure Bx = [Cx]\n\n\tmeasure Cx = [Ax] * 2\n"
                 "\n\tmeasure Sama = [Sama]\n", encoding="utf-8")
    k = nalezy_podle_kodu(Projekt(projekt))
    popisy = sorted(n.popis for n in k["M22"])
    assert len(popisy) == 2                                                  # každý cyklus jednou
    assert any("[Ax] → [Bx] → [Cx] → [Ax]" in x for x in popisy) and any("[Sama] → [Sama]" in x for x in popisy)


def test_glosar_a_rodiny(tmp_path):
    projekt = model_projekt(tmp_path)
    f = tmp_path / "Novy.SemanticModel" / "definition" / "tables" / "Fakt.tmdl"
    f.write_text(f.read_text(encoding="utf-8") + "\n\tmeasure 'Tržby Skutečnost' = 1\n\n\tmeasure 'Náklady Skutečnost' = 1\n"
                 "\n\tmeasure 'Náklady Plán' = 1\n\n\tmeasure 'Account Total' = 1\n\n\tmeasure 'Total CC' = 1\n"
                 "\n\tmeasure 'Náklady CostCenter' = 1\n", encoding="utf-8")
    p = Projekt(projekt)
    assert "M23" not in nalezy_podle_kodu(p) and "M24" not in nalezy_podle_kodu(p)      # bez nastavení se nekontroluje
    p.nastaveni = {"terminy": {"Nákladové středisko": ["Cost Center", "CC"], "Oblast": ["Region"]},
                   "rodiny": [["Skutečnost", "Plán"]]}
    k = nalezy_podle_kodu(p)
    assert sorted(n.objekt for n in k["M23"]) == ["Fakt[Náklady CostCenter]", "Fakt[Total CC]", "Zakaznik[Region]"]
    assert [(n.objekt, n.popis) for n in k["M24"]] == [("Fakt[Tržby Skutečnost]", "V rodině Skutečnost / Plán chybí [Tržby Plán].")]


def test_id_nalezu_stabilni():
    from kontroly import Nalez
    a = Nalez("M14", "varovani", "ai", "Fakt", "12 z 14 měr není v žádné složce.")
    assert a.id == Nalez("M14", "varovani", "ai", "Fakt", "11 z 14 měr není v žádné složce.", "jiné doporučení").id
    assert a.id != Nalez("M14", "varovani", "ai", "Prodej", "12 z 14 měr není v žádné složce.").id
    assert len(a.id) == 10


def spust_audit(monkeypatch, *argv):
    import audit
    monkeypatch.setattr(sys, "argv", ["audit.py", *map(str, argv)])
    with pytest.raises(SystemExit) as e:
        audit.main()
    return e.value.code


def test_audit_nastaveni_vyjimky_baseline_exit(tmp_path, monkeypatch):
    projekt, out = model_projekt(tmp_path / "p"), tmp_path / "out"
    assert spust_audit(monkeypatch, projekt, "--vystup", out) == 0             # výchozí --fail-on nic
    assert spust_audit(monkeypatch, projekt, "--vystup", out, "--fail-on", "varovani") == 1
    csv_soubor = out / "audit_Novy.csv"
    hlavicka = csv_soubor.read_text(encoding="utf-8-sig").splitlines()[0]
    assert hlavicka.endswith(";id")
    # glosář přidá nález, výjimka bez důvodu = chyba nastavení, výjimka s důvodem nález potlačí
    nast = tmp_path / "klient.json"
    zapis(nast, {"terminy": {"Oblast": ["Region"]}, "vyjimky": [{"kod": "M12", "objekt": "*"}]})
    assert spust_audit(monkeypatch, projekt, "--vystup", out, "--nastaveni", nast) == 3
    zapis(nast, {"terminy": {"Oblast": ["Region"]},
                 "vyjimky": [{"kod": "M12", "objekt": "Kal*", "duvod": "kalendář označí klient"}]})
    assert spust_audit(monkeypatch, projekt, "--vystup", out, "--nastaveni", nast, "--baseline", csv_soubor) == 0
    md = (out / "audit_Novy.md").read_text(encoding="utf-8")
    assert "### M23" in md and "### M12" not in md and "1 potlačeno výjimkou" in md
    assert "Nové chyby a varování: 1" in md and "Zakaznik[Region]" in md.split("## Proti baseline")[1]
    assert "Vyřešené nálezy (všech úrovní): 1" in md                          # M12 potlačený = zmizel
    # baseline = tentýž soubor, do kterého se zapisuje: čte se před zápisem, podruhé tedy 0 nových
    assert spust_audit(monkeypatch, projekt, "--vystup", out, "--nastaveni", nast, "--baseline", csv_soubor) == 0
    assert "Nové chyby a varování: 0" in (out / "audit_Novy.md").read_text(encoding="utf-8")


def test_baseline_ze_stareho_csv_bez_id(tmp_path, monkeypatch):
    projekt, out = model_projekt(tmp_path / "p"), tmp_path / "out"
    spust_audit(monkeypatch, projekt, "--vystup", out)
    stary = tmp_path / "stary.csv"
    radky = (out / "audit_Novy.csv").read_text(encoding="utf-8-sig").splitlines()
    stary.write_text("\n".join(r.rsplit(";", 1)[0] for r in radky), encoding="utf-8-sig")    # CSV před zavedením id
    spust_audit(monkeypatch, projekt, "--vystup", out, "--baseline", stary)
    md = (out / "audit_Novy.md").read_text(encoding="utf-8")
    assert "Nové chyby a varování: 0" in md and "Vyřešené nálezy (všech úrovní): 0" in md


def test_pojistka_parseru(tmp_path, monkeypatch):
    from audit import kontrola_nacteni
    projekt = model_projekt(tmp_path)
    assert kontrola_nacteni(Projekt(projekt)) == []
    tabulky = tmp_path / "Novy.SemanticModel" / "definition" / "tables"
    for f in tabulky.glob("*.tmdl"):                                         # sloupce, které parser „nepřečte“
        f.write_text(f.read_text(encoding="utf-8").replace("\tcolumn ", "\tneznamyBlok "), encoding="utf-8")
    problemy = kontrola_nacteni(Projekt(projekt))
    assert problemy and "0 sloupců" in problemy[0]
    assert spust_audit(monkeypatch, projekt, "--vystup", tmp_path / "out") == 3
    assert "Model se nenačetl správně" in (tmp_path / "out" / "audit_Novy.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ kvalita DAX (D…), oprav.py akce dax, HTML report
DAX_CTX = {"miry": {"Tržby", "Náklady", "Marže"}, "sloupce": {("Prodej", "Kč"), ("Prodej", "Datum"), ("Prodej", "Typ"), ("Kalendář", "Datum")},
           "typy": {("Prodej", "Datum"): "dateTime", ("Kalendář", "Datum"): "dateTime"}, "kalendare": {"Kalendář"},
           "vztahy": [("Prodej", "Datum", "Kalendář", "Datum", True)]}


@pytest.mark.parametrize("dax, kod, presny, po", [
    ("CALCULATE ( [Tržby] )", "D05", True, "[Tržby]"),
    ("SUMX ( Prodej, Prodej[Kč] )", "D03", True, "SUM ( Prodej[Kč] )"),
    ('CALCULATE ( [Tržby], FILTER ( Prodej, Prodej[Typ] = "A" ) )', "D01", False, 'CALCULATE ( [Tržby], KEEPFILTERS ( Prodej[Typ] = "A" ) )'),
    ('CALCULATE ( [Tržby], FILTER ( ALL ( Prodej[Typ] ), Prodej[Typ] = "A" ) )', "D01", True, 'CALCULATE ( [Tržby], Prodej[Typ] = "A" )'),
    ("COUNTROWS ( FILTER ( Prodej, Prodej[Kč] > 100 ) )", "D04", False, "CALCULATE ( COUNTROWS ( Prodej ), KEEPFILTERS ( Prodej[Kč] > 100 ) )"),
    ("IFERROR ( [Marže] / [Tržby], 0 )", "D02", True, "DIVIDE ( [Marže], [Tržby], 0 )"),
    ("IF ( [Tržby] = 0, BLANK (), [Marže] / [Tržby] )", "D02", True, "DIVIDE ( [Marže], [Tržby] )"),
    ("IF ( [Tržby] <> 0, [Marže] / [Tržby], 0 )", "D02", True, "DIVIDE ( [Marže], [Tržby], 0 )"),
    ("[Marže] / [Tržby]", "D02", True, "DIVIDE ( [Marže], [Tržby] )"),
    ("TOTALYTD ( [Tržby], Prodej[Datum] )", "D11", False, "TOTALYTD ( [Tržby], 'Kalendář'[Datum] )"),
    ("SUM ( [Kč] )", "D13", True, "SUM ( Prodej[Kč] )"),
    ("'Prodej'[Tržby] * 2", "D13", True, "[Tržby] * 2"),
])
def test_dax_navrhy(dax, kod, presny, po):
    import dax as daxlib
    n = next(x for x in daxlib.navrhy(dax, DAX_CTX) if x.kod == kod)
    assert n.presny is presny and n.dax == po


@pytest.mark.parametrize("dax", [
    "[Tržby] / 1000",                                            # převod jednotek
    "DIVIDE ( [Marže], [Tržby] )",
    "SUMX ( Prodej, Prodej[Kč] * 2 )",                            # opravdový iterátor
    "CALCULATE ( [Tržby], Prodej[Typ] = \"A, (B)\" ) // [Náklady] ( ,",   # čárky a závorky v řetězci a komentáři
    "TOTALYTD ( [Tržby], 'Kalendář'[Datum] )",                    # správný kalendář
    "VAR x = [Tržby] RETURN x",
    "SUMX ( GENERATESERIES ( 1, 3 ), [Value] )",                  # implicitní sloupec
    "IF ( [Tržby] > 0, [Tržby] * 2, CALCULATE ( [Tržby], ALL ( Prodej ) ) )",   # opakování uvnitř CALCULATE -> žádné VAR
])
def test_dax_bez_falesnych_nalezu(dax):
    import dax as daxlib
    assert [n.kod for n in daxlib.navrhy(dax, DAX_CTX)] == []


def test_dax_switch_a_var_skladani():
    import dax as daxlib
    puv = 'IF ( [Tržby] > 100, "A", IF ( [Tržby] > 50, "B", IF ( [Tržby] > 10, "C", "D" ) ) )'
    novy, kody = daxlib.zjednodus(puv, DAX_CTX)
    assert set(kody) == {"D06", "D07"} and novy.startswith("VAR _Trzby = [Tržby]\nRETURN")
    assert "SWITCH (" in novy and novy.count("_Trzby >") == 3 and "[Tržby] >" not in novy
    assert daxlib.zjednodus(novy, DAX_CTX) == (novy, [])                          # podruhé už nic


TMDL_DAX = """table Prodej

\tmeasure Tržby = SUM ( Prodej[Kč] )
\t\tformatString: #,0

\tmeasure Celkem = CALCULATE ( [Tržby] )
\t\tformatString: #,0

\tmeasure Třída =
\t\t\tIF ( [Tržby] > 100, "A",
\t\t\t\tIF ( [Tržby] > 50, "B",
\t\t\t\t\tIF ( [Tržby] > 10, "C", "D" ) ) )

\tmeasure Velké = CALCULATE ( [Tržby], FILTER ( Prodej, Prodej[Kč] > 1000 ) )
\t\tformatString: #,0

\tmeasure Špatně = CALCULATE ( [Tržby], [Tržby] > 0 )

\tmeasure Vztah = CALCULATE ( [Tržby], USERELATIONSHIP ( Prodej[Kč], Prodej[Datum] ) )

\tcolumn Kč
\t\tdataType: double
\t\tsourceColumn: Kč

\tcolumn Datum
\t\tdataType: dateTime
\t\tsourceColumn: Datum
"""


def dax_projekt(koren: Path) -> Path:
    zapis(koren / "D.Report" / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": "../D.SemanticModel"}}})
    zapis(koren / "D.Report" / "definition" / "pages" / "pages.json", {"pageOrder": []})
    zapis(koren / "D.SemanticModel" / "definition" / "tables" / "Prodej.tmdl", TMDL_DAX)
    return koren / "D.Report"


def test_dax_kontroly_v_auditu(tmp_path):
    k = nalezy_podle_kodu(Projekt(dax_projekt(tmp_path)))
    assert {n.objekt for n in k["D05"]} == {"Prodej[Celkem]"} and k["D05"][0].presny
    assert k["D01"][0].objekt == "Prodej[Velké]" and not k["D01"][0].presny and "KEEPFILTERS" in k["D01"][0].navrh
    assert {n.kod for n in k["D06"] + k["D07"]} == {"D06", "D07"}
    assert k["D08"][0].uroven == "chyba" and k["D08"][0].objekt == "Prodej[Špatně]"
    assert k["D10"][0].uroven == "chyba"                                          # mezi Kč a Datum není vztah


def test_oprav_dax_zapis(tmp_path):
    import csv
    from oprav import nacti_navrh, proved, sablona
    rep = dax_projekt(tmp_path)
    p = Projekt(rep)
    navrh = tmp_path / "n.csv"
    sablona(p, navrh)
    dax_radky = [r for r in nacti_navrh(navrh) if r["akce"] == "dax"]
    podle = {r["objekt"]: r for r in dax_radky}
    assert podle["Prodej[Celkem]"]["hodnota"] == "[Tržby]"                       # přesné předvyplněné
    assert podle["Prodej[Velké]"]["hodnota"] == "" and "KEEPFILTERS" in podle["Prodej[Velké]"]["kontext"]   # k ověření ne
    podle["Prodej[Velké]"]["hodnota"] = podle["Prodej[Velké]"]["kontext"].split(": ", 1)[1]
    with open(navrh, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["objekt", "typ", "akce", "hodnota", "nalez", "kontext"], delimiter=";", extrasaction="ignore")
        w.writeheader(); w.writerows(dax_radky)
    proved(p, nacti_navrh(navrh), zapsat=True)
    q = Projekt(rep)
    miry = {m.nazev: m for m in q.miry}
    assert miry["Celkem"].dax == "[Tržby]" and miry["Celkem"].format == "#,0"
    assert miry["Třída"].dax.startswith("VAR _Trzby = [Tržby]") and "SWITCH (" in miry["Třída"].dax
    assert miry["Velké"].dax == "CALCULATE ( [Tržby], KEEPFILTERS ( Prodej[Kč] > 1000 ) )" and miry["Velké"].format == "#,0"
    assert len(q.miry) == len(p.miry)
    k = nalezy_podle_kodu(q)
    assert not {"D01", "D05", "D06", "D07"} & set(k)
    pred = (tmp_path / "D.SemanticModel" / "definition" / "tables" / "Prodej.tmdl").read_bytes()
    proved(q, nacti_navrh(navrh), zapsat=True)                                    # idempotentní
    assert (tmp_path / "D.SemanticModel" / "definition" / "tables" / "Prodej.tmdl").read_bytes() == pred


def test_html_report(tmp_path, monkeypatch):
    import audit
    rep = dax_projekt(tmp_path / "p")
    (tmp_path / "shrnuti.md").write_text("Model je **malý**.\n\n- první priorita\n- druhá", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["audit.py", str(rep), "--vystup", str(tmp_path / "out"), "--html",
                                      "--shrnuti", str(tmp_path / "shrnuti.md")])
    with pytest.raises(SystemExit) as konec:
        audit.main()
    assert konec.value.code == 0
    h = (tmp_path / "out" / "audit_D.html").read_text(encoding="utf-8")
    assert h.startswith("<!DOCTYPE html>") and "http" not in h.split("<footer>")[0].replace("http-equiv", "")   # bez externích zdrojů
    assert "Jak pokračovat" in h and "Kvalita DAX" in h and "<strong>malý</strong>" in h and "<li>první priorita</li>" in h
    assert "KEEPFILTERS ( Prodej[Kč] &gt; 1000 )" in h and "1 tabulka" in h
    assert (tmp_path / "out" / "dax_D.md").exists()


# ------------------------------------------------------------------ angličtina (--lang en)
CESKA_SLOVA = re.compile(r"Doporučení|Souhrn|Nálezy|nemá popis|Míra|Tabulka|chyb |varování|Připravenost|Původní|Přesná|Zabezpečení|"
                         r"Jak pokračovat|Stav v číslech|Před|objekt;typ|ověřit")


@pytest.fixture
def anglicky():
    import jazyk
    jazyk.nastav("en")
    yield
    jazyk.nastav("cs")


def test_anglicke_vystupy(tmp_path, monkeypatch):
    import audit
    rep = dax_projekt(tmp_path / "p")
    try:
        monkeypatch.setattr(sys, "argv", ["audit.py", str(rep), "--output", str(tmp_path / "out"), "--html", "--lang", "en"])
        with pytest.raises(SystemExit):
            audit.main()
    finally:
        import jazyk
        jazyk.nastav("cs")
    for soubor in ("audit_D.md", "audit_D.csv", "audit_D.html", "dax_D.md"):
        text = (tmp_path / "out" / soubor).read_text(encoding="utf-8-sig")
        assert not CESKA_SLOVA.search(text), (soubor, CESKA_SLOVA.search(text).group(0))
    md = (tmp_path / "out" / "audit_D.md").read_text(encoding="utf-8")
    assert "## Summary" in md and "## DAX quality" in md and "Recommendation:" in md
    assert (tmp_path / "out" / "audit_D.csv").read_text(encoding="utf-8-sig").startswith("code;level;area;object;description")
    assert "<html lang='en'>" in (tmp_path / "out" / "audit_D.html").read_text(encoding="utf-8") and "Next steps" in \
        (tmp_path / "out" / "audit_D.html").read_text(encoding="utf-8")


def test_id_stejne_v_obou_jazycich(tmp_path, anglicky):
    import jazyk
    p = Projekt(model_projekt(tmp_path, ROLE))
    en = sorted(n.id for n in spust(p))
    jazyk.nastav("cs")
    cs = sorted(n.id for n in spust(Projekt(model_projekt(tmp_path / "b", ROLE))))
    assert en == cs and len(en) > 20


def test_oprav_anglicka_sablona_a_nastaveni(tmp_path, anglicky):
    import csv
    from audit import je_vyjimka, nacti_nastaveni
    from oprav import nacti_navrh, proved, sablona
    rep = dax_projekt(tmp_path)
    p = Projekt(rep)
    navrh = tmp_path / "fixes.csv"
    sablona(p, navrh)
    with open(navrh, encoding="utf-8-sig") as f:
        radky = list(csv.DictReader(f, delimiter=";"))
    assert list(radky[0]) == ["object", "type", "action", "value", "finding", "context"]
    assert {r["action"] for r in radky} >= {"description", "dax"} and {r["type"] for r in radky} <= {"table", "column", "measure"}
    proved(p, nacti_navrh(navrh), zapsat=True)                                    # anglická šablona se načte a zapíše
    assert next(m for m in Projekt(rep).miry if m.nazev == "Celkem").dax == "[Tržby]"
    zapis(tmp_path / "client.json", {"terms": {"Revenue": ["Rev"]}, "exceptions": [{"code": "D08", "object": "Prodej*", "reason": "known"}]})
    nast = nacti_nastaveni(tmp_path / "client.json")
    assert nast["terminy"] == {"Revenue": ["Rev"]} and nast["vyjimky"][0] == {"kod": "D08", "objekt": "Prodej*", "duvod": "known"}
    d08 = next(n for n in spust(p) if n.kod == "D08")
    assert je_vyjimka(d08, nast["vyjimky"])
    zapis(tmp_path / "bad.json", {"exceptions": [{"code": "D08"}]})
    with pytest.raises(ValueError, match="reason"):
        nacti_nastaveni(tmp_path / "bad.json")
