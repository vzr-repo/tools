# pbip_audit – Python nástroje pro libovolný Power BI report (PBIP)

Audit reportu a modelu, příprava pro AI a hromadné úpravy – bez Power BI Desktopu, jen nad soubory projektu.
Vzniklo při stavbě reportu [Obec v grafu](https://obecvgrafu.cz); nic není vázané na tento report.

🇬🇧 [English version](README.en.md) · Licence MIT · Autor: Jakub Vozar

## Stažení

- **Zip (vždy poslední verze):** [pbip_audit.zip](https://github.com/vzr-repo/tools/releases/download/pbip-audit-latest/pbip_audit.zip) – rozbal kamkoli a spouštěj skripty z rozbalené složky.
- Nebo celé repo: `git clone https://github.com/vzr-repo/tools.git`.
- Potřebuješ jen Python 3.10+ (`python --version`, na Windows případně `py`). Žádné další balíčky, žádné AI, žádný Power BI Desktop.

## Podporované formáty

| Část | Formát | Audit | Dokumentace pro AI | Menu stránek |
|---|---|---|---|---|
| report | PBIR (`definition/pages/…/visual.json`) | ✔ | ✔ | ✔ |
| report | PBIR-Legacy (jeden `report.json`) | ✔ | ✔ | – (převeď na PBIR) |
| model | TMDL (`definition/tables/*.tmdl`) | ✔ | ✔ | – |
| model | TMSL (`model.bim`), složka `*.SemanticModel` i starší `*.Dataset` | ✔ | ✔ | – |
| model | tenký report napojený na model v Power BI Service | jen kontroly reportu | jen stránky | ✔ |

- Report se s modelem páruje podle `definition.pbir` (datasetReference), takže funguje i víc reportů nad jedním modelem.
- Cesta může být soubor `.pbip`, složka `*.Report` nebo složka s jedním reportem; víc reportů najednou: `audit.py <složka> --vse`.
- Python 3.10+, žádné další balíčky.

**Ověřeno** (verze do 11/2026) na 66 veřejných projektech PBIP z GitHubu (Microsoft/komunita: PBIR i PBIR-Legacy, TMDL i model.bim,
výpočetní skupiny, hierarchie, víc reportů nad jedním modelem) a na reportu Obec v grafu. Parser TMDL načetl všechny
míry, sloupce a tabulky (kontrola počtů proti souborům). Nové kontroly (M12–M19, R14, S01–S08), `porovnej.py` a `oprav.py` jsou zatím
ověřené na demo modelu (Contoso, verze „před“ a „po“ + kopie s rolemi) a syntetickými testy.
Testy: `python -m pytest pbip_audit/tests`.

## Nástroje

| Skript | Co dělá | Výstup |
|---|---|---|
| `audit.py <projekt> [--vse]` | 40 kontrol modelu, reportu, připravenosti pro AI a zabezpečení (RLS/OLS) + skóre AI 0–100 | `audit_<nazev>.md`, `.csv` |
| `ai_dokumentace.py <projekt>` | celý model (tabulky, sloupce, míry s DAX, Power Query, vztahy, role) a stránky s poli v jednom Markdownu | `model_<nazev>.md` |
| `porovnej.py <před> <po>` | porovnání dvou stavů: skóre AI po složkách, nálezy podle kontrol, vyřešené / nové chyby a varování | `porovnani_<a>_<b>.md` |
| `oprav.py <projekt> --sablona n.csv` → `oprav.py <projekt> n.csv [--zapsat]` | návrh oprav z nálezů → doplnit hodnoty (ručně / AI) → náhled → zápis do TMDL: popisy, skrytí, složky měr, formáty | úprava `*.tmdl` |
| `menu_stranek.py <projekt>` | vysouvací menu „☰ Stránky“ na všech stránkách (záložky bez změny filtrů) | úprava projektu |
| `pbip.py` | knihovna: `Projekt(cesta)` → stránky, vizuály, záložky, tabulky, sloupce, míry, vztahy | – |
| `kontroly.py` | jednotlivé kontroly (nová kontrola = nová funkce s `@kontrola`) | – |

```bash
python pbip_audit/audit.py "cesta/k/MujReport" --vystup audit
python pbip_audit/ai_dokumentace.py "cesta/k/MujReport" --vystup audit --bez-m
python pbip_audit/menu_stranek.py "cesta/k/MujReport" --skupiny menu.json
python pbip_audit/porovnej.py "zaloha/MujReport.pbip" "cesta/k/MujReport.pbip" --vystup audit
python pbip_audit/oprav.py "cesta/k/MujReport.pbip" --sablona navrh.csv     # pak doplň sloupec hodnota
python pbip_audit/oprav.py "cesta/k/MujReport.pbip" navrh.csv              # náhled (git diff styl)
python pbip_audit/oprav.py "cesta/k/MujReport.pbip" navrh.csv --zapsat     # zápis (Desktop zavřený!)
```

`oprav.py` zachovává BOM, konce řádků (CRLF) a pořadí vlastností jako Desktop (dataType, isHidden, formatString,
displayFolder, lineageTag); opakované spuštění se stejným návrhem nic nezmění. Po zápisu projekt znovu načte a ověří,
že počty tabulek / sloupců / měr sedí. Přejmenování záměrně neumí (musí se opravit i odkazy v DAX a vizuálech).

## Skill pro Claude Code

`skill/SKILL.md` + skripty = skill **pbip-audit**: v Claude Code stačí napsat např. „zkontroluj mi report v C:\…\Sales.pbip“
nebo „připrav můj model pro Copilota“ – Claude se zeptá na cestu, spustí audit a dokumentaci, shrne výsledek a nabídne
další kroky (návrh popisů, skrytí polí) – nic nemění bez souhlasu. Instalace / aktualizace po změně skriptů:
`python pbip_audit/instaluj_skill.py` (zkopíruje do `~/.claude/skills/pbip-audit`).

Ověřeno na veřejných projektech: [RuiRomano/pbip-demo](https://github.com/RuiRomano/pbip-demo),
[RuiRomano/pbip-demo-agentic](https://github.com/RuiRomano/pbip-demo-agentic),
[ProdataSQL/FinancialModelling](https://github.com/ProdataSQL/FinancialModelling),
[pbi-tools/sales-sample](https://github.com/pbi-tools/sales-sample),
[data-goblin/powerbi-macguyver-toolbox](https://github.com/data-goblin/powerbi-macguyver-toolbox).

## Kontroly (audit.py)

| Kód | Oblast | Co hledá |
|---|---|---|
| M01 | AI | míry bez popisu |
| M02 | AI | viditelné sloupce bez popisu |
| M03 | AI | tabulky bez popisu |
| M04 | model | číselné míry bez formátu |
| M05 | AI / model | nepoužitá pole (žádný vizuál, míra, vztah ani řazení) – kandidáti ke skrytí |
| M06 | AI | viditelné technické sloupce (klíče, kódy, pořadí) |
| M07 | model | automatické datum a čas (LocalDateTable) |
| M08 | model | obousměrné a neaktivní vztahy |
| M09 | AI | technické názvy (podtržítka, camelCase) |
| M10 | model | kolize názvů (míra = sloupec, duplicitní míry) – Desktop pak projekt neotevře |
| M11 | model | DAX odkazuje na neexistující míru / sloupec |
| R01 | report | datové vizuály bez titulku |
| R02 | report | barvy zapsané přímo ve vizuálu místo theme |
| R03 | report | skryté stránky |
| R04 | report | vizuál přesahuje plátno |
| R05 | report | překrývající se datové vizuály |
| R06 | report | moc vizuálů na stránce / moc polí ve vizuálu (výkon) |
| R08 | report | slicery s uloženým výchozím výběrem |
| R09 | report | záložky, které mění filtry |
| R10 | AI | vizuály bez alternativního textu |
| R11 | report | vizuály odkazují na neexistující pole (vizuál ukáže chybu) |
| R12 | report | report bez vlastního theme |
| R13 | report | osiřelé formátování (barva pro hodnotu ze smazaného pole) – neškodí, jen zbytečné |
| M12 | AI | žádná tabulka není označená jako kalendář (dataCategory Time) |
| M13 | AI | generické a verzované názvy (Measure 23, Col1, _FINAL, v2, _old …) u měr, sloupců a tabulek |
| M14 | AI | tabulka s 8+ měrami, většina mimo složky (display folder) |
| M15 | model | tabulka bez vztahu (osiřelá dimenze); DAX parametry (GENERATESERIES, DATATABLE) jen info |
| M16 | model | procentní míry (%, perc, podíl …) bez formátu % – zobrazí 0,42 místo 42 % |
| M17 | model | duplicitní míry (stejný DAX bez ohledu na mezery) a míry, které jen obalují jinou míru |
| M18 | model | vztahy mnoho:mnoho |
| M19 | model | počítané sloupce na faktové tabulce |
| R14 | report | slicer z tabulky bez aktivního vztahu (výběr nic nefiltruje) |
| S01 | RLS | filtr role / OLS odkazuje na neexistující tabulku nebo sloupec |
| S02 | RLS | **filtr role nedojde k tabulce s daty** – uživatel ji uvidí celou; u každé tabulky důvod (žádný vztah / proti směru / neaktivní vztah) |
| S03 | RLS | vztah posílá bezpečnostní filtr oběma směry (securityFilteringBehavior) |
| S04 | RLS | role bez filtru i bez OLS (vidí vše) |
| S05 | RLS | OLS skrývá pole, které používá vizuál nebo míra – uživateli role se rozbije |
| S06 | RLS | USERNAME() místo USERPRINCIPALNAME() |
| S07 | RLS | RLS filtr přímo na faktové tabulce (pomalejší, nefiltruje dimenze) |
| S08 | RLS | dimenze mimo dosah filtru role (info – ověř, že neobsahuje citlivá data) |

M09 (technické názvy) nově kontroluje i tabulky (tbl_, Dim/Fact, podtržítka) a míry (podtržítka, zkratky typu AOV).

**Jak RLS kontrola počítá dosah:** filtr role jde jen aktivními vztahy, ze strany 1 na stranu N (u n:n ze strany
„do“ na „z“); opačně jen u vztahu 1:1 nebo s *Apply security filter in both directions*. USERELATIONSHIP ani
obousměrné křížové filtrování bez bezpečnostního nastavení RLS nepoužije. Kontrola je statická – nezná členy rolí ani
data, takže neověří, že filtr vrací správné řádky; ověří, že se filtr dostane všude, kam má.

**Skóre AI připravenosti** = vážený průměr (`VAHY_AI` v `audit.py`): popisy měr 25 %, popisy viditelných sloupců 20 %,
popisy tabulek 15 %, skryté technické sloupce 15 %, srozumitelné názvy 10 %, míry ve složkách 10 %, označený
kalendář 5 %. Copilot i AI agenti nad modelem čtou právě názvy, popisy a strukturu. (Do 11/2026 mělo skóre jen první
čtyři složky – starší audity nejsou přímo srovnatelné; demo model „před“ 2 → 10.)

## Doporučený postup auditu cizího reportu

1. Ulož report jako PBIP (PBIR + TMDL) do samostatné složky a dej ji do gitu – každá úprava jde vrátit.
2. `audit.py` → projdi nejdřív chyby (M10, M11, R11, S01, S05), pak varování (u RLS hlavně S02).
3. `oprav.py --sablona` + `ai_dokumentace.py` → dej AI dokumentaci i šablonu a nech ji doplnit popisy, složky a formáty;
   zkontroluj, pak `oprav.py … --zapsat` – nejrychlejší cesta ke skóre AI nad 80.
4. Přejmenování (M09, M13) dělej v Desktopu nebo Tabular Editoru – musí se opravit i odkazy v DAX a vizuálech.
5. `porovnej.py zaloha/… aktualni/…` → před/po pro klienta.
