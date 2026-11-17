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
míry, sloupce a tabulky (kontrola počtů proti souborům). Nové kontroly (M12–M24, R14, S01–S08), `porovnej.py` a `oprav.py` jsou zatím
ověřené na demo modelu (Contoso, verze „před“ a „po“ + kopie s rolemi) a syntetickými testy.
Testy: `python -m pytest pbip_audit/tests`.

## Nástroje

| Skript | Co dělá | Výstup |
|---|---|---|
| `audit.py <projekt> [--vse] [--html]` | 58 kontrol modelu, reportu, kvality DAX, připravenosti pro AI a zabezpečení (RLS/OLS) + skóre AI 0–100; návrhy přepisu měr; grafický HTML report; volitelně nastavení klienta, baseline a exit kódy pro CI | `audit_<nazev>.md`, `.csv`, `.html`, `dax_<nazev>.md` |
| `ai_dokumentace.py <projekt>` | celý model (tabulky, sloupce, míry s DAX, Power Query, vztahy, role) a stránky s poli v jednom Markdownu | `model_<nazev>.md` |
| `porovnej.py <před> <po>` | porovnání dvou stavů: skóre AI po složkách, nálezy podle kontrol, vyřešené / nové chyby a varování | `porovnani_<a>_<b>.md` |
| `oprav.py <projekt> --sablona n.csv` → `oprav.py <projekt> n.csv [--zapsat]` | návrh oprav z nálezů → doplnit hodnoty (ručně / AI) → náhled → zápis do TMDL: popisy, skrytí, složky měr, formáty, výrazy měr (DAX) | úprava `*.tmdl` |
| `menu_stranek.py <projekt>` | vysouvací menu „☰ Stránky“ na všech stránkách (záložky bez změny filtrů) | úprava projektu |
| `pbip.py` | knihovna: `Projekt(cesta)` → stránky, vizuály, záložky, tabulky, sloupce, míry, vztahy | – |
| `kontroly.py` | jednotlivé kontroly (nová kontrola = nová funkce s `@kontrola`) | – |
| `dax.py` | statický rozbor DAX (volání funkcí, argumenty) a mechanické přepisy pro kontroly D01–D13 | – |
| `html_report.py` | grafický HTML report (volá ho `audit.py --html`) | – |

Příkazy níže spouštěj ze složky **nad** `pbip_audit` (kořen repa / rozbaleného zipu). Když už jsi uvnitř složky
`pbip_audit`, vynech `pbip_audit/` – tedy `python audit.py …`.

```bash
python pbip_audit/audit.py "cesta/k/MujReport" --vystup audit
python pbip_audit/audit.py "cesta/k/MujReport" --vystup audit --html                 # + grafický report audit_MujReport.html
python pbip_audit/audit.py "cesta/k/MujReport" --vystup audit --nastaveni klient.json --baseline audit/audit_MujReport.csv
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
| M20 | model | různé datové typy na koncích vztahu (chyba) |
| M21 | model | textový klíč na straně 1 vztahu (info; u kódů měn / zemí je v pořádku) |
| M22 | model | cyklická závislost měr ([A] → [B] → [A]) |
| M23 | AI | nejednotné termíny podle glosáře klienta („CC“ místo „Nákladové středisko“) – jen s `--nastaveni` |
| M24 | model | neúplná rodina měr (je „Tržby Skutečnost“, chybí „Tržby Plán“) – jen s `--nastaveni` |

| D01 | DAX | FILTER přes celou tabulku jako filtr CALCULATE → podmínka na sloupci (s KEEPFILTERS) |
| D02 | DAX | dělení `/`, `IF ( b = 0 … )` nebo `IFERROR ( a / b … )` → DIVIDE |
| D03 | DAX | `SUMX ( T, T[c] )` (i AVERAGEX, MINX, MAXX, COUNTX) → SUM / AVERAGE / … |
| D04 | DAX | `COUNTROWS ( FILTER ( T, … ) )` → `CALCULATE ( COUNTROWS ( T ), … )` |
| D05 | DAX | `CALCULATE ( [Míra] )` bez filtrů → `[Míra]` |
| D06 | DAX | 3+ vnořené IF → `SWITCH ( TRUE (), … )` |
| D07 | DAX | stejná míra 3× a víc ve výrazu → proměnná (VAR) |
| D08 | DAX | filtr CALCULATE porovnává jen míry (`[Tržby] > 0`) – Desktop ho odmítne (chyba) |
| D09 | DAX | EARLIER / EARLIEST → proměnná |
| D10 | DAX | USERELATIONSHIP mezi sloupci bez vztahu (chyba) nebo na aktivní vztah (nic nedělá) |
| D11 | DAX | časová funkce (TOTALYTD, SAMEPERIODLASTYEAR …) nad datem z faktové tabulky → sloupec kalendáře |
| D12 | DAX | složitá míra (hloubka vnoření ≥ 7, 4+ CALCULATE, nebo > 500 znaků bez VAR) |
| D13 | DAX | sloupec bez tabulky (`[Kč]`) / míra s tabulkou (`Prodej[Tržby]`) |

M05 u měr neříká „smaž“: audit vidí jen tento report, ne další reporty, Excel ani dotazy přes XMLA nad stejným modelem.
Před smazáním ověř Lineage / Impact analysis v Service.

### Kvalita DAX a návrhy přepisu

Kontroly D01–D13 čtou DAX staticky (bez Desktopu a bez dat) a u vzorů, které jdou přepsat mechanicky, rovnou navrhnou
nový výraz celé míry. Návrhy jsou v `dax_<nazev>.md` (před / po) a v HTML reportu:

- **přesná úprava** dává stejný výsledek (D03, D05, D06, D07, D13, D01 s `ALL ( sloupec )`, D02 – u dělení nulou vrátí
  prázdno místo chyby). `oprav.py --sablona` ji předvyplní do řádku s akcí `dax`;
- **úprava k ověření** mění chování, většinou proto, že opravuje chybu (D01 FILTER → KEEPFILTERS, D04, D11 datum
  z faktu → kalendář). V šabloně je jen ve sloupci `kontext` – po porovnání čísel v Desktopu ji zkopíruj do `hodnota`.

Rozbor nezná data ani kontext vizuálu: neřekne, jestli míra počítá „správné číslo“ v byznysovém smyslu, a návrhy
u složitých měr (D12) nedělá. Na to je AI nad `model_<nazev>.md` – vysvětlí, co míra dělá, a navrhne přepis s
vysvětlením; výsledek pak zapiš přes `oprav.py` (akce `dax`).

### HTML report (`--html`)

`audit_<nazev>.html` je jeden soubor bez externích zdrojů (otevřeš v prohlížeči, pošleš e-mailem, vytiskneš do PDF):
metriky stavu, skóre AI po složkách, nálezy podle oblasti a závažnosti (filtry a hledání), doporučení u každé
skupiny, DAX před / po a **Jak pokračovat** – pořadí kroků odvozené pravidly z nálezů (chyby → varování v modelu →
RLS → DAX → nejslabší složky skóre AI → report → nový audit s `--baseline`). Světlý i tmavý režim podle systému.

Jediné, co Python smysluplně nenapíše, je **slovní shrnutí pro klienta** (co čísla znamenají pro jeho reporting).
Bez něj je v HTML hotový prompt pro AI; text od AI (nebo vlastní, Markdown) přidáš `--shrnuti shrnuti.md`.

### Nastavení klienta, výjimky, baseline, exit kódy

`--nastaveni klient.json` (vzor `nastaveni_priklad.json`, jen standardní knihovna, žádný YAML):

- `terminy` – preferovaný název → varianty (M23). Shoda po celých slovech včetně camelCase, takže „CC“ najde
  „TotalCC“ i „CC Náklady“, ale ne „Account“.
- `rodiny` – přípony / předpony měr, které mají existovat společně, např. `["Skutečnost", "Plán"]` (M24).
- `vyjimky` – potlačené nálezy: `{"id": "…"}` (id je poslední sloupec CSV) nebo `{"kod": "M21", "objekt": "*Currency*"}`
  (vzor se `*` a `?`). **Důvod je povinný** – výjimka bez `duvod` audit zastaví. V souhrnu je vidět počet potlačených.

Každý nález má **stabilní id** (kód + objekt + popis bez čísel), takže „12 z 14 měr“ → „11 z 14“ je pořád tentýž nález.
`--baseline audit_X.csv` (předchozí běh; může to být i soubor, který se právě přepisuje) přidá do souhrnu nové
chyby / varování a počet vyřešených nálezů. Funguje i se starším CSV bez sloupce id. `porovnej.py` páruje podle stejného id.

`--fail-on nic | chyba | varovani` (výchozí `nic`) – exit kód: 0 v pořádku, 1 varování, 2 chyby, **3 projekt nejde
načíst nebo selhal parser**. Pojistka parseru: když model má tabulky a vztahy, ale 0 sloupců, nebo víc než polovina
konců vztahů v načteném modelu chybí, audit to napíše na začátek MD a vrátí 3 – místo tichého „čistého“ výsledku.

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
2. `audit.py --html` → projdi nejdřív chyby (M10, M11, M20, M22, R11, S01, S05, D08, D10), pak varování (u RLS hlavně S02).
   Má-li klient vlastní terminologii, připrav `klient.json` (glosář, rodiny měr) a spouštěj s `--nastaveni`.
3. `oprav.py --sablona` + `ai_dokumentace.py` → dej AI dokumentaci i šablonu a nech ji doplnit popisy, složky a formáty;
   přesné přepisy DAX jsou předvyplněné, úpravy k ověření porovnej v Desktopu; zkontroluj, pak `oprav.py … --zapsat`.
4. Přejmenování (M09, M13) dělej v Desktopu nebo Tabular Editoru – musí se opravit i odkazy v DAX a vizuálech.
5. `porovnej.py zaloha/… aktualni/…` → před/po pro klienta; finální `audit.py --html --shrnuti shrnuti.md` jako výstup.
