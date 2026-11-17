"""Jazyk výstupů: čeština (výchozí) nebo angličtina. Language of the output: Czech (default) or English.

    from jazyk import L, nastav
    nastav("en")                                  # nebo proměnná prostředí PBIP_AUDIT_LANG=en / audit.py --lang en
    L("Míra nemá popis.", "Measure has no description.")   # -> text v aktuálním jazyce

Každý text je v kódu hned v obou jazycích (žádný oddělený katalog, který by se rozešel). L() vrací řetězec, který si
pamatuje i českou podobu (.cs) – stabilní id nálezu se počítá z ní, takže baseline a výjimky fungují v obou jazycích.
"""
from __future__ import annotations

import os

_JAZYK = "en" if os.environ.get("PBIP_AUDIT_LANG", "").lower().startswith("en") else "cs"
JAZYKY = ("cs", "en")


def nastav(jazyk: str | None):
    global _JAZYK
    if jazyk:
        j = jazyk.lower()[:2]
        if j not in JAZYKY:
            raise ValueError(f"Neznámý jazyk / unknown language: {jazyk} (cs, en)")
        _JAZYK = j


def aktualni() -> str:
    return _JAZYK


def en() -> bool:
    return _JAZYK == "en"


class Text(str):
    """Řetězec v aktuálním jazyce, s českou (.cs) a anglickou (.en) podobou."""
    cs: str
    en: str

    def __new__(cls, cs: str, en: str):
        o = super().__new__(cls, en if _JAZYK == "en" else cs)
        o.cs, o.en = cs, en
        return o


def volby(*nazvy: str) -> tuple:
    """Přepínače příkazové řádky: české a anglické jméno, v nápovědě první to v aktuálním jazyce. („--vystup“, „--output“)"""
    return tuple(reversed(nazvy)) if _JAZYK == "en" else nazvy


def L(cs: str, en: str) -> Text:
    return Text(cs, en)


def cesky(x) -> str:
    """Česká podoba textu (pro stabilní id); obyčejný řetězec vrátí beze změny."""
    return getattr(x, "cs", x)


class LDict(dict):
    """Slovník s hodnotami (cs, en), který při čtení vrací text v aktuálním jazyce."""

    def __getitem__(self, k):
        cs, en = super().__getitem__(k)
        return L(cs, en)

    def get(self, k, default=None):
        return self[k] if k in self else default

    def values(self):
        return [self[k] for k in self]

    def items(self):
        return [(k, self[k]) for k in self]


def tvar(n: int, jedna: str, dve: str, pet: str, en1: str, en_vic: str) -> str:
    """Číslo + slovo ve správném tvaru: 1 tabulka / 2 tabulky / 5 tabulek; 1 table / 5 tables."""
    if _JAZYK == "en":
        return f"{n} {en1 if n == 1 else en_vic}"
    return f"{n} " + (jedna if n == 1 else dve if 2 <= n <= 4 else pet)


UROVEN = LDict({"chyba": ("chyba", "error"), "varovani": ("varování", "warning"), "info": ("info", "info")})
UROVEN_MN = LDict({"chyba": ("Chyby", "Errors"), "varovani": ("Varování", "Warnings"), "info": ("Info", "Info")})
OBLAST = LDict({"model": ("Model", "Model"), "report": ("Report", "Report"), "ai": ("Připravenost pro AI", "AI readiness"),
                "rls": ("Zabezpečení (RLS / OLS)", "Security (RLS / OLS)"), "dax": ("Kvalita DAX", "DAX quality")})
SKORE = LDict({"popisy měr": ("popisy měr", "measure descriptions"),
               "popisy viditelných sloupců": ("popisy viditelných sloupců", "visible column descriptions"),
               "popisy tabulek": ("popisy tabulek", "table descriptions"),
               "skryté technické sloupce": ("skryté technické sloupce", "hidden technical columns"),
               "srozumitelné názvy": ("srozumitelné názvy", "readable names"),
               "míry ve složkách": ("míry ve složkách", "measures in display folders"),
               "označený kalendář": ("označený kalendář", "marked date table")})
# hodnoty v CSV a na příkazové řádce, které uživatel může psát anglicky
UROVEN_Z_EN = {"error": "chyba", "warning": "varovani", "none": "nic", "info": "info"}
