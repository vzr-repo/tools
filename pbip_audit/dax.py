"""Malý statický rozbor DAX: najde volání funkcí a jejich argumenty bez plného parseru (řetězce, komentáře, 'tabulky'
a [sloupce] se nejdřív zamaskují, aby čárky a závorky v nich nerozbily strukturu) + mechanické přepisy pro kontroly D…

    from dax import volani, prepis
    for v in volani("CALCULATE ( [Tržby], FILTER ( Prodej, Prodej[Kč] > 0 ) )"):
        v.nazev, v.argumenty                    # 'CALCULATE', ['[Tržby]', 'FILTER ( Prodej, Prodej[Kč] > 0 )']

Přepisy vrací nový text celé míry. „Přesný“ přepis dává stejný výsledek (refaktoring), „přibližný“ mění chování
v okrajových případech nebo opravuje chybu – ten je potřeba ověřit v Desktopu.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

ITERATORY = {"SUMX", "AVERAGEX", "MINX", "MAXX", "COUNTX", "COUNTAX", "PRODUCTX", "CONCATENATEX", "RANKX", "FILTER",
             "ADDCOLUMNS", "SELECTCOLUMNS", "SUMMARIZE", "SUMMARIZECOLUMNS", "GENERATE", "GENERATEALL", "TOPN",
             "MAXX", "MEDIANX", "PERCENTILEX.INC", "PERCENTILEX.EXC", "STDEVX.P", "STDEVX.S", "VARX.P", "VARX.S",
             "GEOMEANX", "AVERAGEX", "FIRSTNONBLANK", "LASTNONBLANK", "COUNTROWS"}
MENI_KONTEXT = {"CALCULATE", "CALCULATETABLE"} | ITERATORY
CASOVE = {"TOTALYTD", "TOTALQTD", "TOTALMTD", "DATESYTD", "DATESQTD", "DATESMTD", "SAMEPERIODLASTYEAR", "DATEADD",
          "PARALLELPERIOD", "PREVIOUSYEAR", "PREVIOUSQUARTER", "PREVIOUSMONTH", "PREVIOUSDAY", "NEXTYEAR", "NEXTQUARTER",
          "NEXTMONTH", "NEXTDAY", "DATESINPERIOD", "DATESBETWEEN", "OPENINGBALANCEYEAR", "OPENINGBALANCEQUARTER",
          "OPENINGBALANCEMONTH", "CLOSINGBALANCEYEAR", "CLOSINGBALANCEQUARTER", "CLOSINGBALANCEMONTH", "STARTOFYEAR",
          "STARTOFQUARTER", "STARTOFMONTH", "ENDOFYEAR", "ENDOFQUARTER", "ENDOFMONTH", "FIRSTDATE", "LASTDATE"}
AGREGACE_X = {"SUMX": "SUM", "AVERAGEX": "AVERAGE", "MINX": "MIN", "MAXX": "MAX", "COUNTX": "COUNT"}


# ------------------------------------------------------------------ maskování a volání
def maska(dax: str) -> str:
    """Stejně dlouhý text: obsah "řetězců", 'tabulek' a [sloupců] nahrazený „_“, komentáře mezerami."""
    out, i, n = list(dax), 0, len(dax)
    while i < n:
        c = dax[i]
        if dax.startswith("//", i) or dax.startswith("--", i):
            j = dax.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = " " * (j - i); i = j; continue
        if dax.startswith("/*", i):
            j = dax.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out[i:j] = [" " if ch != "\n" else "\n" for ch in dax[i:j]]; i = j; continue
        if c in "\"'":
            j = i + 1
            while j < n:
                if dax[j] == c:
                    if j + 1 < n and dax[j + 1] == c:
                        j += 2; continue
                    break
                j += 1
            out[i + 1:j] = "_" * (j - i - 1); i = j + 1; continue
        if c == "[":
            j = dax.find("]", i)
            j = n if j < 0 else j
            out[i + 1:j] = "_" * (j - i - 1); i = j + 1; continue
        i += 1
    return "".join(out)


@dataclass
class Volani:
    nazev: str                      # velkými písmeny
    zacatek: int                    # index prvního znaku názvu funkce
    konec: int                      # index za uzavírací závorkou
    argumenty: list = field(default_factory=list)       # texty argumentů (oříznuté)
    rozsahy: list = field(default_factory=list)         # (od, do) argumentů v původním textu
    hloubka: int = 0


def _zavorka(m: str, otevrena: int) -> int:
    h = 0
    for k in range(otevrena, len(m)):
        if m[k] in "({":
            h += 1
        elif m[k] in ")}":
            h -= 1
            if h == 0:
                return k
    return len(m) - 1


def volani(dax: str, nazvy: set | None = None) -> list[Volani]:
    """Všechna volání funkcí (nebo jen funkcí z `nazvy`) v pořadí výskytu, s argumenty rozdělenými na nejvyšší úrovni."""
    m = maska(dax)
    out = []
    for r in re.finditer(r"(?<![\w.'\]])([A-Za-z][A-Za-z0-9_.]*)\s*\(", m):
        nazev = r.group(1).upper()
        if nazvy and nazev not in nazvy:
            continue
        otevrena = r.end() - 1
        zavrena = _zavorka(m, otevrena)
        rozsahy, h, od = [], 0, otevrena + 1
        for k in range(otevrena + 1, zavrena):
            if m[k] in "({":
                h += 1
            elif m[k] in ")}":
                h -= 1
            elif m[k] == "," and h == 0:
                rozsahy.append((od, k)); od = k + 1
        if dax[otevrena + 1:zavrena].strip() or rozsahy:
            rozsahy.append((od, zavrena))
        rozsahy = [(a + len(dax[a:b]) - len(dax[a:b].lstrip()), b - (len(dax[a:b]) - len(dax[a:b].rstrip()))) for a, b in rozsahy]
        out.append(Volani(nazev, r.start(1), zavrena + 1, [dax[a:b] for a, b in rozsahy], rozsahy, m[:r.start(1)].count("(") - m[:r.start(1)].count(")")))
    return out


def je_cele(text: str, v: Volani, posun: int = 0) -> bool:
    """Je argument `text` celý tvořený tímto voláním (např. arg == „FILTER ( … )“)?"""
    return v.zacatek - posun == 0 and v.konec - posun == len(text)


def jedine_volani(text: str, nazev: str) -> Volani | None:
    t = text.strip()
    vv = volani(t, {nazev})
    return vv[0] if vv and je_cele(t, vv[0]) else None


def odkazy(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Odkazy na sloupce Tabulka[Sloupec] / 'Tabulka'[Sloupec] a holé [X] (míra nebo nekvalifikovaný sloupec)."""
    m = maska(text)
    sloupce, hole = [], []
    for r in re.finditer(r"('[_]+'|(?<![\w.])[A-Za-z_][\w.]*)?\[([_]*)\]", m):
        jm = text[r.start(2):r.end(2)]
        if r.group(1):
            t = text[r.start(1):r.end(1)]
            t = t[1:-1].replace("''", "'") if t.startswith("'") else t
            sloupce.append((t, jm))
        else:
            hole.append(jm)
    return sloupce, hole


def holy_odkaz(text: str) -> str | None:
    """„[Míra]“ -> „Míra“, jinak None."""
    t = text.strip()
    return t[1:-1] if re.fullmatch(r"\[[^\]]+\]", t) else None


def tabulka_odkaz(text: str) -> str | None:
    """Holý název tabulky („Prodej“ / „'Moje tabulka'“) -> název, jinak None."""
    t = text.strip()
    if re.fullmatch(r"'(?:[^']|'')+'", t):
        return t[1:-1].replace("''", "'")
    return t if re.fullmatch(r"[A-Za-z_][\w.]*", t) and t.upper() not in ("TRUE", "FALSE", "BLANK") else None


def sloupec_odkaz(text: str) -> tuple[str, str] | None:
    t = text.strip()
    s, h = odkazy(t)
    if len(s) == 1 and not h and re.fullmatch(r"(?:'(?:[^']|'')+'|[A-Za-z_][\w.]*)\s*\[[^\]]+\]", t):
        return s[0]
    return None


def hloubka(dax: str) -> int:
    m, h, mx = maska(dax), 0, 0
    for c in m:
        if c == "(":
            h += 1; mx = max(mx, h)
        elif c == ")":
            h -= 1
    return mx


def operatory_nahore(text: str) -> list[str]:
    """Binární operátory na nejvyšší úrovni (mimo závorky)."""
    m, h, out, k = maska(text), 0, [], 0
    while k < len(m):
        c = m[k]
        if c in "({":
            h += 1
        elif c in ")}":
            h -= 1
        elif h == 0:
            for op in ("&&", "||", "<>", "<=", ">=", "=", "<", ">", "+", "-", "*", "/", "&"):
                if m.startswith(op, k):
                    if op == "-" and not m[:k].strip():
                        break                                        # unární minus na začátku
                    out.append(op); k += len(op) - 1
                    break
            else:
                if re.match(r"\bIN\b", m[k:k + 3], re.I) and (k == 0 or not m[k - 1].isalnum()):
                    out.append("IN")
        k += 1
    return out


def rozdel_operator(text: str, op: str) -> tuple[str, str] | None:
    """„A / B“ s jediným operátorem op na nejvyšší úrovni -> (A, B)."""
    m, h = maska(text), 0
    for k, c in enumerate(m):
        if c in "({":
            h += 1
        elif c in ")}":
            h -= 1
        elif h == 0 and m.startswith(op, k):
            return text[:k].strip(), text[k + len(op):].strip()
    return None


def je_porovnani(text: str) -> bool:
    return any(o in ("=", "<>", "<", ">", "<=", ">=", "IN") for o in operatory_nahore(text))


# ------------------------------------------------------------------ přepisy
@dataclass
class Navrh:
    kod: str
    presny: bool                     # True = stejný výsledek (refaktoring); False = ověřit v Desktopu
    popis: str
    dax: str                         # celý nový text míry


def _nahrad(dax: str, od: int, do: int, novy: str) -> str:
    return dax[:od] + novy + dax[do:]


def _jednoducha_podminka(cond: str, tabulka: str, miry: set) -> bool:
    """Podmínka jen nad sloupci jedné tabulky, bez měr a bez volání tabulkových funkcí."""
    s, h = odkazy(cond)
    if h or not s or any(t != tabulka for t, _ in s):
        return False
    return not volani(cond, MENI_KONTEXT | {"ALL", "VALUES", "RELATED", "RELATEDTABLE", "LOOKUPVALUE"})


def navrhy(dax: str, kontext: dict) -> list[Navrh]:
    """Všechny použitelné přepisy na původním textu (každý zvlášť). kontext: miry (set názvů), sloupce {(t, c)},
    typy {(t, c): dataType}, kalendare (set tabulek s dataCategory Time), vztahy [(z_t, z_c, do_t, do_c, aktivni)]."""
    miry = kontext.get("miry", set())
    out: list[Navrh] = []
    vv = volani(dax)

    for v in vv:
        # D05 CALCULATE([Míra]) bez filtrů
        if v.nazev == "CALCULATE" and len(v.argumenty) == 1 and holy_odkaz(v.argumenty[0]) in miry:
            out.append(Navrh("D05", True, "CALCULATE bez filtrů kolem míry nic nedělá (odkaz na míru už CALCULATE obsahuje).",
                             _nahrad(dax, v.zacatek, v.konec, v.argumenty[0].strip())))
        # D03 SUMX(T, T[c]) -> SUM(T[c])
        if v.nazev in AGREGACE_X and len(v.argumenty) == 2:
            t, sl = tabulka_odkaz(v.argumenty[0]), sloupec_odkaz(v.argumenty[1])
            if t and sl and sl[0] == t:
                out.append(Navrh("D03", True, f"{v.nazev} přes jediný sloupec je {AGREGACE_X[v.nazev]}.",
                                 _nahrad(dax, v.zacatek, v.konec, f"{AGREGACE_X[v.nazev]} ( {v.argumenty[1].strip()} )")))
        # D01 FILTER jako filtr v CALCULATE
        if v.nazev in ("CALCULATE", "CALCULATETABLE"):
            for (a, b), arg in zip(v.rozsahy[1:], v.argumenty[1:]):
                f = jedine_volani(arg, "FILTER")
                if not f or len(f.argumenty) != 2:
                    continue
                zdroj, cond = f.argumenty
                t = tabulka_odkaz(zdroj)
                vse = jedine_volani(zdroj, "ALL") or jedine_volani(zdroj, "VALUES")
                if t and _jednoducha_podminka(cond, t, miry):
                    out.append(Navrh("D01", False, f"FILTER přes celou tabulku {t} jako filtr CALCULATE – stačí podmínka na sloupci "
                                     "(KEEPFILTERS zachová stávající filtry jako FILTER).",
                                     _nahrad(dax, a, b, f"KEEPFILTERS ( {cond.strip()} )")))
                elif vse and vse.nazev == "ALL" and len(vse.argumenty) == 1 and sloupec_odkaz(vse.argumenty[0]):
                    sl = sloupec_odkaz(vse.argumenty[0])
                    s, h = odkazy(cond)
                    if not h and s and all(x == sl for x in s) and not volani(cond, MENI_KONTEXT):
                        out.append(Navrh("D01", True, "FILTER ( ALL ( sloupec ), podmínka ) je totéž co samotná podmínka.",
                                         _nahrad(dax, a, b, cond.strip())))
        # D04 COUNTROWS(FILTER(T, podmínka))
        if v.nazev == "COUNTROWS" and len(v.argumenty) == 1:
            f = jedine_volani(v.argumenty[0], "FILTER")
            if f and len(f.argumenty) == 2:
                t = tabulka_odkaz(f.argumenty[0])
                if t and _jednoducha_podminka(f.argumenty[1], t, miry):
                    zdroj = f.argumenty[0].strip()
                    out.append(Navrh("D04", False, f"COUNTROWS ( FILTER ( {zdroj}, … ) ) iteruje celou tabulku – rychlejší je CALCULATE s filtrem.",
                                     _nahrad(dax, v.zacatek, v.konec,
                                             f"CALCULATE ( COUNTROWS ( {zdroj} ), KEEPFILTERS ( {f.argumenty[1].strip()} ) )")))
        # D02 IFERROR ( a / b [, alt] )
        if v.nazev == "IFERROR" and len(v.argumenty) in (1, 2):
            d = rozdel_operator(v.argumenty[0], "/")
            if d and operatory_nahore(v.argumenty[0]) == ["/"]:
                alt = f", {v.argumenty[1].strip()}" if len(v.argumenty) == 2 and v.argumenty[1].strip().upper() not in ("BLANK()", "BLANK ( )") else ""
                out.append(Navrh("D02", True, "IFERROR kolem dělení – DIVIDE ošetří nulu sám a je rychlejší.",
                                 _nahrad(dax, v.zacatek, v.konec, f"DIVIDE ( {d[0]}, {d[1]}{alt} )")))
        # D02 IF ( b = 0, alt, a / b ) / IF ( b <> 0, a / b, alt )
        if v.nazev == "IF" and len(v.argumenty) in (2, 3):
            c = v.argumenty[0]
            for op, kladna in (("=", False), ("<>", True)):
                cc = rozdel_operator(c, op)
                if not cc or operatory_nahore(c) != [op] or cc[1].replace(" ", "").upper() not in ("0", "BLANK()"):
                    continue
                vetev_deleni = v.argumenty[1] if kladna else (v.argumenty[2] if len(v.argumenty) == 3 else "")
                vetev_alt = (v.argumenty[2] if len(v.argumenty) == 3 else "") if kladna else v.argumenty[1]
                d = rozdel_operator(vetev_deleni, "/") if operatory_nahore(vetev_deleni) == ["/"] else None
                if d and re.sub(r"\s", "", d[1]) == re.sub(r"\s", "", cc[0]):
                    alt = vetev_alt.strip()
                    alt = "" if not alt or alt.replace(" ", "").upper() == "BLANK()" else f", {alt}"
                    out.append(Navrh("D02", True, "Ruční ošetření dělení nulou přes IF – DIVIDE dělá totéž.",
                                     _nahrad(dax, v.zacatek, v.konec, f"DIVIDE ( {d[0]}, {d[1]}{alt} )")))
        # D06 IF ( c1, v1, IF ( c2, v2, IF ( … ) ) ) -> SWITCH ( TRUE (), … )
        if v.nazev == "IF" and len(v.argumenty) == 3 and not any(
                o.nazev == "IF" and o.zacatek < v.zacatek < o.konec and len(o.argumenty) == 3 and
                o.rozsahy[2][0] <= v.zacatek < o.rozsahy[2][1] and je_cele(o.argumenty[2], v, o.rozsahy[2][0]) for o in vv):
            dvojice, akt, jinak = [], v, None
            while akt and len(akt.argumenty) in (2, 3):
                dvojice.append((akt.argumenty[0].strip(), akt.argumenty[1].strip()))
                zbytek = akt.argumenty[2] if len(akt.argumenty) == 3 else None
                dalsi = jedine_volani(zbytek, "IF") if zbytek else None
                if not dalsi:
                    jinak = zbytek.strip() if zbytek else None
                    break
                akt = dalsi
            if len(dvojice) >= 3:
                zac = dax.rfind("\n", 0, v.zacatek) + 1
                odsaz = re.match(r"[ \t]*", dax[zac:]).group(0)
                vn = odsaz + "    "
                radky = f",\n{vn}".join(f"{c}, {h}" for c, h in dvojice) + (f",\n{vn}{jinak}" if jinak else "")
                out.append(Navrh("D06", True, f"{len(dvojice)} vnořených IF – SWITCH ( TRUE (), … ) je čitelnější.",
                                 _nahrad(dax, v.zacatek, v.konec, f"SWITCH (\n{vn}TRUE (),\n{vn}{radky}\n{odsaz})")))
        # D11 časová funkce nad datem z faktové tabulky
        if v.nazev in CASOVE:
            for t, c in odkazy(dax[v.zacatek:v.konec])[0]:
                if kontext.get("typy", {}).get((t, c), "").lower() not in ("datetime", "date") or t in kontext.get("kalendare", set()):
                    continue
                cil = next(((dt, dc) for zt, zc, dt, dc, akt in kontext.get("vztahy", []) if (zt, zc) == (t, c) and akt), None)
                je_cil = any((dt, dc) == (t, c) for _, _, dt, dc, _ in kontext.get("vztahy", []))
                if je_cil:
                    break                                               # sloupec je cílem vztahu = kalendářní dimenze
                novy = dax
                if cil:
                    vzor = re.compile(r"(?:'" + re.escape(t.replace("'", "''")) + r"'|" + re.escape(t) + r")\s*\[" + re.escape(c) + r"\]")
                    usek = vzor.sub(lambda _m: f"'{cil[0]}'[{cil[1]}]", dax[v.zacatek:v.konec])
                    novy = _nahrad(dax, v.zacatek, v.konec, usek)
                out.append(Navrh("D11", False, f"{v.nazev} nad {t}[{c}] (datum z faktové tabulky) – časové funkce potřebují "
                                 "souvislou tabulku kalendáře, jinak vrací chybné nebo prázdné výsledky."
                                 + (f" Použij {cil[0]}[{cil[1]}]." if cil else " Napoj fakt na tabulku kalendáře."),
                                 novy if cil else ""))
                break

    # D02 celá míra je A / B
    d = rozdel_operator(dax, "/")
    if d and operatory_nahore(dax) == ["/"] and not dax.strip().upper().startswith("VAR") \
            and not re.fullmatch(r"\(?\s*\d+(\.\d+)?\s*\)?", d[1]):                  # / 1000 = převod jednotek, ne riziko
        out.append(Navrh("D02", True, "Dělení operátorem / – při nule ve jmenovateli vrátí chybu nebo nekonečno; DIVIDE vrátí prázdno.",
                         f"DIVIDE ( {d[0]}, {d[1]} )"))

    # D07 stejná míra 3× a víc – do proměnné (jen když žádný výskyt není uvnitř funkce měnící kontext)
    m = maska(dax)
    vyskyty = {}
    for r in re.finditer(r"(?<![\w'\]])\[([_]+)\]", m):
        nazev = dax[r.start(1):r.end(1)]
        if nazev in miry:
            vyskyty.setdefault(nazev, []).append((r.start(1) - 1, r.end(1) + 1))
    existujici = set(re.findall(r"\bVAR\s+([A-Za-z_]\w*)", dax, re.I))
    for nazev, pos in vyskyty.items():
        if len(pos) < 3:
            continue
        bezpecne = not any(o.nazev in MENI_KONTEXT | CASOVE and any(o.zacatek < a < o.konec for a, _ in pos) for o in vv)
        if not bezpecne:
            continue
        jm = "_" + re.sub(r"\W+", "", unicodedata.normalize("NFKD", nazev).encode("ascii", "ignore").decode()) or "_Mira"
        while jm in existujici:
            jm += "_"
        telo = dax
        for a, b in reversed(pos):
            telo = _nahrad(telo, a, b, jm)
        out.append(Navrh("D07", True, f"[{nazev}] se počítá {len(pos)}× – ulož ji do proměnné (VAR), spočítá se jednou.",
                         f"VAR {jm} = [{nazev}]\nRETURN\n" + "\n".join("    " + r if r.strip() else r for r in telo.strip().splitlines())
                         if not telo.lstrip().upper().startswith("VAR")
                         else f"VAR {jm} = [{nazev}]\n{telo.strip()}"))

    # D13 nekvalifikovaný sloupec / kvalifikovaná míra
    sloupce = kontext.get("sloupce", set())
    nazvy_sl = {}
    for t, c in sloupce:
        nazvy_sl.setdefault(c, []).append(t)
    pojmenovane = set(re.findall(r'"([^"]+)"\s*,', dax))
    for r in re.finditer(r"('[_]+'|(?<![\w.])[A-Za-z_][\w.]*)?\[([_]+)\]", m):
        jm = dax[r.start(2):r.end(2)]
        if r.group(1):
            t = dax[r.start(1):r.end(1)]
            t = t[1:-1].replace("''", "'") if t.startswith("'") else t
            if jm in miry and (t, jm) not in sloupce:
                out.append(Navrh("D13", True, f"Míra [{jm}] zapsaná s tabulkou ({t}[{jm}]) – vypadá jako sloupec; piš míry bez tabulky.",
                                 _nahrad(dax, r.start(1), r.end(2) + 1, f"[{jm}]")))
        elif jm not in miry and jm not in pojmenovane and not re.fullmatch(r"Value\d*", jm) and len(nazvy_sl.get(jm, [])) == 1:
            t = nazvy_sl[jm][0]
            tt = t if re.fullmatch(r"[A-Za-z_]\w*", t) else "'" + t.replace("'", "''") + "'"
            out.append(Navrh("D13", True, f"Sloupec [{jm}] bez tabulky – vypadá jako míra; piš sloupce vždy s tabulkou ({t}[{jm}]).",
                             _nahrad(dax, r.start(2) - 1, r.end(2) + 1, f"{tt}[{jm}]")))
    return out


def zjednodus(dax: str, kontext: dict, jen_presne: bool = True, kroku: int = 20) -> tuple[str, list[str]]:
    """Opakovaně aplikuje přepisy (jen přesné, nebo všechny s návrhem) -> (nový text, použité kódy)."""
    pouzite = []
    for _ in range(kroku):
        n = next((x for x in navrhy(dax, kontext) if x.dax and (x.presny or not jen_presne)), None)
        if not n or n.dax == dax:
            break
        dax = n.dax
        pouzite.append(n.kod)
    return dax, pouzite


def slozitost(dax: str) -> dict:
    vv = volani(dax)
    return {"znaky": len(re.sub(r"\s", "", maska(dax))), "hloubka": hloubka(dax),
            "calculate": sum(1 for v in vv if v.nazev in ("CALCULATE", "CALCULATETABLE")),
            "volani": len(vv), "var": bool(re.search(r"\bVAR\b", maska(dax), re.I))}
