"""Vysouvací menu stránek pro libovolný PBIP report: tlačítko „☰ Stránky“ + skrytý panel se seznamem stránek + 2 záložky
na každou stránku. Přechod přes menu zachová výběr ve slicerech (záložky mají suppressData).

    python menu_stranek.py <projekt>                       # jedna skupina = všechny viditelné stránky
    python menu_stranek.py <projekt> --skupiny menu.json   # vlastní skupiny a barvy
    python menu_stranek.py <projekt> --smazat              # odstraní menu (vizuály menu* a záložky menu*)

menu.json:
    {"skupiny": [{"nazev": "Finance", "barva": "#C8322B", "stranky": [["rozpocet", "Rozpočet"], ["investice", "Investice"]]}],
     "bez_menu": ["uvod"], "kotva": "btnUvod", "pismo": "#22201C", "akcent": "#9C2F23", "podklad": "#FFFFFF"}
- kotva: název vizuálu, vedle kterého se tlačítko umístí (vlevo od něj); bez kotvy = pravý dolní roh stránky.
Před spuštěním: v Desktopu uložit a commitnout; po spuštění v Desktopu neukládat a načíst změny (zavřít bez uložení a otevřít).
"""
import argparse
import json
import shutil
from pathlib import Path

from pbip import Projekt

SV = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.13.0/schema.json"
SB = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/2.1.0/schema.json"
L = lambda v: {"expr": {"Literal": {"Value": v}}}
SOLID = lambda c: {"solid": {"color": L(f"'{c}'")}}
BEZ = {k: [{"properties": {"show": L("false")}}] for k in ("background", "border", "dropShadow", "title")}
Z0 = 20000


def uloz(p: Path, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def vizual(nazev, x, y, w, h, z, visual, skryty=True):
    d = {"$schema": SV, "name": nazev, "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}, "visual": visual}
    if skryty:
        d["isHidden"] = True
    return d


def tlacitko(text, odkaz, barva, vypln, tucne=False, velikost=10, zarovnani="left", hover="#F3EEE3"):
    return {"visualType": "actionButton", "objects": {
        "icon": [{"properties": {"show": L("false")}, "selector": {"id": "default"}}],
        "text": [{"properties": {"show": L("true")}},
                 {"properties": {"text": L("'" + text.replace("'", "''") + "'"), "fontColor": SOLID(barva), "fontSize": L(f"{velikost}D"),
                                 "bold": L("true" if tucne else "false"), "horizontalAlignment": L(f"'{zarovnani}'"), "leftMargin": L("6D")},
                  "selector": {"id": "default"}}],
        "fill": [{"properties": {"show": L("true"), "fillColor": SOLID(vypln), "transparency": L("0D")}, "selector": {"id": "default"}},
                 {"properties": {"show": L("true"), "fillColor": SOLID(hover), "transparency": L("0D")}, "selector": {"id": "hover"}}]},
        "visualContainerObjects": {**BEZ, "visualLink": [{"properties": {"show": L("true"), **odkaz}}]}, "drillFilterOtherVisuals": True}


def obdelnik(vypln, ramecek):
    return {"visualType": "shape", "objects": {
        "shape": [{"properties": {"tileShape": L("'rectangle'")}}],
        "fill": [{"properties": {"show": L("true"), "fillColor": SOLID(vypln), "transparency": L("0D")}, "selector": {"id": "default"}}],
        "outline": [{"properties": {"show": L("true"), "lineColor": SOLID(ramecek), "weight": L("1D")}}]},
        "visualContainerObjects": BEZ, "drillFilterOtherVisuals": True}


def text(runs):
    return {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": runs}]}}]},
            "visualContainerObjects": BEZ, "drillFilterOtherVisuals": True}


def smaz(p: Projekt):
    pages = p.report_def / "pages"
    for d in pages.glob("*/visuals/menu*"):
        shutil.rmtree(d)
    bm = p.report_def / "bookmarks"
    for f in bm.glob("menu*.bookmark.json"):
        f.unlink()
    meta = bm / "bookmarks.json"
    if meta.exists():
        d = json.loads(meta.read_text(encoding="utf-8"))
        d["items"] = [i for i in d.get("items", []) if not i.get("name", "").startswith("menu")]
        uloz(meta, d)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projekt")
    ap.add_argument("--skupiny")
    ap.add_argument("--smazat", action="store_true")
    a = ap.parse_args()
    p = Projekt(a.projekt)
    if p.format_reportu != "PBIR":
        raise SystemExit(f"Menu umí jen report ve formátu PBIR (tento je {p.format_reportu}). "
                         "V Desktopu zapni Preview „Formát sestavy PBIR“ a projekt ulož znovu.")
    smaz(p)
    if a.smazat:
        print("Menu odstraněno."); return
    cfg = json.loads(Path(a.skupiny).read_text(encoding="utf-8")) if a.skupiny else {}
    skupiny = cfg.get("skupiny") or [{"nazev": "Stránky", "barva": "#8C8476",
                                       "stranky": [[s.nazev, s.zobrazeny] for s in p.stranky if not s.skryta]}]
    ink, akc, pod = cfg.get("pismo", "#22201C"), cfg.get("akcent", "#9C2F23"), cfg.get("podklad", "#FFFFFF")
    bez = set(cfg.get("bez_menu", []))
    kotva = cfg.get("kotva")
    pages, zalozky = p.report_def / "pages", []
    for st in p.stranky:
        if st.nazev in bez or st.skryta:
            continue
        vis = pages / st.nazev / "visuals"
        k = vis / kotva / "visual.json" if kotva else None
        if k and k.exists():
            kp = json.loads(k.read_text(encoding="utf-8"))["position"]
            bx, by, bh = kp["x"] - 104, kp["y"], kp["height"]
        else:
            bx, by, bh = st.sirka - 112, st.vyska - 34, 26
        ote, zav = f"menuOtevrit_{st.nazev}", f"menuZavrit_{st.nazev}"
        uloz(vis / "menuTlacitko" / "visual.json", vizual("menuTlacitko", bx, by, 96, bh, 9601,
             tlacitko("☰  Stránky", {"type": L("'Bookmark'"), "bookmark": L(f"'{ote}'")}, akc, pod, velikost=9), skryty=False))
        rh, w = 22, 290
        radku = sum(1 + len(g["stranky"]) for g in skupiny)
        h = 44 + radku * rh + 8
        x, y = st.sirka - w - 12, max(8, by - h - 6)
        prvky = []

        def pridej(n, d):
            uloz(vis / n / "visual.json", d); prvky.append(n)

        pridej("menuPozadi", vizual("menuPozadi", x, y, w, h, Z0, obdelnik(pod, ink)))
        pridej("menuNadpis", vizual("menuNadpis", x + 10, y + 8, w - 60, 28, Z0 + 1,
                                    text([{"value": "Stránky reportu", "textStyle": {"fontSize": "13pt", "fontWeight": "bold", "color": ink}}])))
        pridej("menuZavrit", vizual("menuZavrit", x + w - 44, y + 8, 34, 26, Z0 + 1,
                                    tlacitko("✕", {"type": L("'Bookmark'"), "bookmark": L(f"'{zav}'")}, ink, pod, velikost=11, zarovnani="center")))
        yy = y + 44
        for i, g in enumerate(skupiny):
            pridej(f"menuSk{i}", vizual(f"menuSk{i}", x + 10, yy, w - 20, rh, Z0 + 1, text([
                {"value": "▬  ", "textStyle": {"fontSize": "9pt", "color": g.get("barva", "#8C8476"), "fontWeight": "bold"}},
                {"value": g["nazev"].upper(), "textStyle": {"fontSize": "8pt", "fontWeight": "bold", "color": "#6E675B"}}])))
            yy += rh
            for j, (kod, popisek) in enumerate(g["stranky"]):
                ted = kod == st.nazev
                n = f"menuStr_{i}_{j}"
                pridej(n, vizual(n, x + 22, yy, w - 34, rh - 2, Z0 + 1,
                                 tlacitko(("▸ " if ted else "") + popisek, {"type": L("'PageNavigation'"), "navigationSection": L(f"'{kod}'")},
                                          akc if ted else ink, pod, tucne=ted)))
                yy += rh
        for nazev, rezim in ((ote, "visible"), (zav, "hidden")):
            uloz(p.report_def / "bookmarks" / f"{nazev}.bookmark.json", {
                "$schema": SB, "displayName": ("Menu – otevřít " if rezim == "visible" else "Menu – zavřít ") + st.zobrazeny, "name": nazev,
                "options": {"targetVisualNames": prvky, "applyOnlyToTargetVisuals": True, "suppressData": True},
                "explorationState": {"version": "1.3", "activeSection": st.nazev, "sections": {st.nazev: {"visualContainers": {
                    n: {"singleVisual": {"display": {"mode": "hidden"}} if rezim == "hidden" else {}} for n in prvky}}}}})
            zalozky.append(nazev)
    meta = p.report_def / "bookmarks" / "bookmarks.json"
    d = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmarksMetadata/1.0.0/schema.json", "items": []}
    d["items"] = d.get("items", []) + [{"name": z} for z in zalozky]
    uloz(meta, d)
    print(f"Menu na {len(zalozky) // 2} stránkách ({len(zalozky)} záložek).")


if __name__ == "__main__":
    main()
