# pbip_audit – Python tools for any Power BI report (PBIP)

Audit a report and its semantic model, get it ready for Copilot / AI agents, check row-level security and apply bulk
fixes – without Power BI Desktop, straight from the project files. Built while developing the
[Obec v grafu](https://obecvgrafu.cz) report; nothing is tied to that report.

🇨🇿 [Česká verze](README.md) · MIT licence · Author: Jakub Vozar

> **Language:** add `--lang en` to any script (or set the environment variable `PBIP_AUDIT_LANG=en` once) and every
> output is in English – findings, recommendations, Markdown, CSV, the HTML report, the fix template and the help.
> Without it the output is Czech. Options have English names (`--output`, `--write`, `--template` …); the Czech
> ones work too. Finding ids are the same in both languages, so baselines and exceptions carry over.

## Download

- **Zip (always the latest version):** [pbip_audit.zip](https://github.com/vzr-repo/tools/releases/download/pbip-audit-latest/pbip_audit.zip)
  – unzip anywhere and run the scripts from the unzipped folder.
- Or the whole repo: `git clone https://github.com/vzr-repo/tools.git`.
- All you need is Python 3.10+ (`python --version`, on Windows possibly `py`). No extra packages, no AI, no Power BI Desktop.

## Supported formats

| Part | Format | Audit | AI documentation | Page menu |
|---|---|---|---|---|
| report | PBIR (`definition/pages/…/visual.json`) | ✔ | ✔ | ✔ |
| report | PBIR-Legacy (single `report.json`) | ✔ | ✔ | – (convert to PBIR) |
| model | TMDL (`definition/tables/*.tmdl`) | ✔ | ✔ | – |
| model | TMSL (`model.bim`), `*.SemanticModel` and older `*.Dataset` folders | ✔ | ✔ | – |
| model | thin report connected to a model in the Power BI Service | report checks only | pages only | ✔ |

- The report is matched to its model via `definition.pbir` (datasetReference), so several reports over one model work.
- The path can be a `.pbip` file, a `*.Report` folder or a folder with one report; many reports at once: `audit.py <folder> --all`.
- `oprav.py` (bulk fixes) writes TMDL only.

**Tested** (versions up to 11/2026) on 66 public PBIP projects from GitHub (Microsoft / community: PBIR and PBIR-Legacy,
TMDL and model.bim, calculation groups, hierarchies, several reports over one model). The newer checks (M12–M24, R14,
S01–S08), `porovnej.py` and `oprav.py` are so far verified on a Contoso demo model ("before" and "after" versions plus
a copy with roles) and on synthetic tests. Tests: `python -m pytest pbip_audit/tests`.

## Tools

| Script | What it does | Output |
|---|---|---|
| `audit.py <project> [--all] [--html]` | 58 checks of the model, report, DAX quality, AI readiness and security (RLS/OLS) + AI readiness score 0–100; measure rewrite proposals; graphical HTML report; optional client settings, baseline and exit codes for CI | `audit_<name>.md`, `.csv` |
| `ai_dokumentace.py <project>` | the whole model (tables, columns, measures with DAX, Power Query, relationships, roles) and report pages with their fields in one Markdown file – context for an LLM | `model_<name>.md` |
| `porovnej.py <before> <after>` | compare two states: AI score per component, findings per check, resolved / new errors and warnings | `porovnani_<a>_<b>.md` |
| `oprav.py <project> --template f.csv` → `oprav.py <project> f.csv [--write]` | fix template from findings → fill in values (by hand or with AI) → preview → write into TMDL: descriptions, hiding, display folders, format strings, measure expressions (DAX) | edits `*.tmdl` |
| `menu_stranek.py <project>` | slide-out "☰ Pages" menu on every page (bookmarks that keep slicer selections) | edits the project |
| `pbip.py` | library: `Projekt(path)` → pages, visuals, bookmarks, tables, columns, measures, relationships, roles | – |
| `kontroly.py` | the individual checks (a new check = a new function decorated with `@kontrola`) | – |
| `dax.py` | static DAX analysis (function calls, arguments) and mechanical rewrites for checks D01–D13 | – |
| `html_report.py` | graphical HTML report (called by `audit.py --html`) | – |

Run the commands below from the folder **above** `pbip_audit` (repo root / unzipped zip). If you are already inside
`pbip_audit`, drop the `pbip_audit/` prefix – i.e. `python audit.py …`.

```bash
python pbip_audit/audit.py "path/to/MyReport.pbip" --output audit --lang en # audit into folder ./audit
python pbip_audit/audit.py "path/to/MyReport.pbip" --output audit --html --lang en # + graphical report audit_MyReport.html
python pbip_audit/audit.py "path/to/MyReport.pbip" --output audit --settings client.json --baseline audit/audit_MyReport.csv --fail-on error --lang en
python pbip_audit/ai_dokumentace.py "path/to/MyReport.pbip" --output audit --no-m --lang en # docs without Power Query
python pbip_audit/porovnej.py "backup/MyReport.pbip" "path/to/MyReport.pbip" --output audit --lang en
python pbip_audit/oprav.py "path/to/MyReport.pbip" --template fixes.csv --lang en # then fill in column "value"
python pbip_audit/oprav.py "path/to/MyReport.pbip" fixes.csv --lang en # preview (diff)
python pbip_audit/oprav.py "path/to/MyReport.pbip" fixes.csv --write --lang en # write (close Desktop first!)
python pbip_audit/menu_stranek.py "path/to/MyReport.pbip" --groups menu.json --lang en
```

### Bulk fixes (`oprav.py`)

The template CSV (`;`-separated, UTF-8 with BOM – opens directly in Excel) has columns
`object;type;action;value;finding;context` (type `table` / `column` / `measure`; context = DAX of the measure).
With `--lang en` the template is written in English; `oprav.py` reads a template in either language. Actions:

| `action` | Writes | Value |
|---|---|---|
| `description` | `/// description` above the object | the description text |
| `hide` | `isHidden` | `yes` / `no` – pre-filled `yes` for unused and technical columns |
| `folder` | `displayFolder` | folder name, e.g. `01 Sales` |
| `format` | `formatString` | e.g. `#,0`, `0.0%` |
| `dax` | the measure expression | new DAX – the template pre-fills exact rewrites only; rewrites to verify are in `context` |

Rows with an empty value are skipped. `oprav.py` keeps the BOM, line endings (CRLF) and the property order Power BI
Desktop uses (dataType, isHidden, formatString, displayFolder, lineageTag); running it again with the same CSV changes
nothing. After writing it reloads the project and checks that the table / column / measure counts still match.
It deliberately does **not** rename objects – a rename also has to fix references in DAX and visuals.

## Claude Code skill

`skill/SKILL.md` + the scripts = the **pbip-audit** skill. In Claude Code just say e.g. "audit my report in
C:\…\Sales.pbip" or "get my model ready for Copilot" – Claude asks for the path, runs the audit and documentation,
summarises the result and offers next steps (description proposals, hiding fields) – it changes nothing without your
consent. Install / update after changing the scripts: `python pbip_audit/instaluj_skill.py`. When you write to Claude in English, the skill runs the scripts with `--lang en`
(copies into `~/.claude/skills/pbip-audit`).

Tested on public projects: [RuiRomano/pbip-demo](https://github.com/RuiRomano/pbip-demo),
[RuiRomano/pbip-demo-agentic](https://github.com/RuiRomano/pbip-demo-agentic),
[ProdataSQL/FinancialModelling](https://github.com/ProdataSQL/FinancialModelling),
[pbi-tools/sales-sample](https://github.com/pbi-tools/sales-sample),
[data-goblin/powerbi-macguyver-toolbox](https://github.com/data-goblin/powerbi-macguyver-toolbox).

## Checks (audit.py)

Levels: `chyba` = error (broken / will misbehave), `varovani` = warning (hurts usability or performance),
`info` = worth considering. Areas: model, report, AI readiness, RLS.

| Code | Area | What it finds |
|---|---|---|
| M01 | AI | measures without a description |
| M02 | AI | visible columns without a description |
| M03 | AI | tables without a description |
| M04 | model | numeric measures without a format string |
| M05 | AI / model | unused fields (no visual, measure, relationship or sort-by) – candidates for hiding |
| M06 | AI | visible technical columns (keys, codes, sort helpers) |
| M07 | model | auto date/time enabled (LocalDateTable) |
| M08 | model | bidirectional and inactive relationships |
| M09 | AI | technical names (underscores, camelCase) of columns, tables (tbl_, Dim/Fact) and measures (abbreviations like AOV) |
| M10 | model | name collisions (measure = column, duplicate measure names) – Desktop won't open the project |
| M11 | model | DAX references a non-existent measure / column |
| M12 | AI | no table is marked as a date table (dataCategory Time) |
| M13 | AI | generic and versioned names (Measure 23, Col1, _FINAL, v2, _old …) of measures, columns and tables |
| M14 | AI | a table with 8+ measures, most of them outside display folders |
| M15 | model | table without any relationship (orphan dimension); DAX parameter tables (GENERATESERIES, DATATABLE) info only |
| M16 | model | percentage measures (%, perc, pct …) without a % format – shows 0.42 instead of 42 % |
| M17 | model | duplicate measures (same DAX ignoring whitespace) and measures that only wrap another measure |
| M18 | model | many-to-many relationships |
| M19 | model | calculated columns on a fact table |
| M20 | model | different data types on the two ends of a relationship (error) |
| M21 | model | text key on the one side of a relationship (info; fine for currency / country codes) |
| M22 | model | circular measure dependency ([A] → [B] → [A]) |
| M23 | AI | inconsistent terms according to the client glossary ("CC" instead of "Cost Center") – only with `--settings` |
| M24 | model | incomplete measure family ("Sales Actual" exists, "Sales Budget" is missing) – only with `--settings` |
| R01 | report | data visuals without a title |
| R02 | report | colours hard-coded in a visual instead of the theme |
| R03 | report | hidden pages |
| R04 | report | visual extends beyond the page canvas |
| R05 | report | overlapping data visuals |
| R06 | report | too many visuals on a page / too many fields in a visual (performance) |
| R08 | report | slicers with a saved default selection |
| R09 | report | bookmarks that change filters |
| R10 | AI | visuals without alt text |
| R11 | report | visuals reference a non-existent field (the visual shows an error) |
| R12 | report | report without a custom theme |
| R13 | report | orphaned formatting (colour for a value of a deleted field) – harmless, just clutter |
| R14 | report | slicer on a table without an active relationship (the selection filters nothing) |
| S01 | RLS | role filter / OLS references a non-existent table or column |
| S02 | RLS | **the role filter never reaches a data table** – users of the role see the whole table; the reason is given per table (no relationship / against the filter direction / inactive relationship) |
| S03 | RLS | relationship applies the security filter in both directions (securityFilteringBehavior) |
| S04 | RLS | role without any row filter or OLS (sees everything) |
| S05 | RLS | OLS hides a field that a visual or measure uses – it breaks for users of the role |
| S06 | RLS | USERNAME() instead of USERPRINCIPALNAME() |
| S07 | RLS | RLS filter directly on a fact table (slower, doesn't filter dimensions) |
| S08 | RLS | dimension outside the reach of the role filter (info – make sure it holds no sensitive data) |

M05 for measures doesn't say "delete": the audit sees only this report, not other reports, Excel or XMLA queries over
the same model. Check Lineage / Impact analysis in the Service before deleting.

### Client settings, exceptions, baseline, exit codes

`--settings client.json` (template: `settings_example.json`, plain JSON, standard library only):

- `terms` – preferred name → variants (M23). Matches whole words including camelCase, so "CC" finds
  "TotalCC" and "CC Costs" but not "Account".
- `families` – measure suffixes / prefixes that should exist together, e.g. `["Actual", "Budget"]` (M24).
- `exceptions` – suppressed findings: `{"id": "…"}` (id is the last CSV column) or
  `{"code": "M21", "object": "*Currency*"}` (pattern with `*` and `?`). **A reason (`reason`) is required** – an
  exception without one stops the audit. The summary shows how many findings were suppressed.

Every finding has a **stable id** (code + object + description without numbers), so "12 of 14 measures" → "11 of 14"
is still the same finding. `--baseline audit_X.csv` (a previous run; it may even be the file being overwritten) adds
new errors / warnings and the number of resolved findings to the summary. Works with older CSVs without the id column
too. `porovnej.py` matches findings by the same id.

`--fail-on none | error | warning` (default `none`; Czech `nic | chyba | varovani` work too) – exit code: 0 OK, 1 warnings, 2 errors,
**3 the project can't be loaded or the parser failed**. Parser safeguard: when the model has tables and relationships
but 0 columns, or more than half of the relationship ends are missing from the loaded model, the audit says so at the
top of the Markdown and returns 3 – instead of a silently "clean" result.

| Code | Area | What it finds |
|---|---|---|
| D01 | DAX | FILTER over a whole table as a CALCULATE filter → column predicate (with KEEPFILTERS) |
| D02 | DAX | division with `/`, `IF ( b = 0 … )` or `IFERROR ( a / b … )` → DIVIDE |
| D03 | DAX | `SUMX ( T, T[c] )` (also AVERAGEX, MINX, MAXX, COUNTX) → SUM / AVERAGE / … |
| D04 | DAX | `COUNTROWS ( FILTER ( T, … ) )` → `CALCULATE ( COUNTROWS ( T ), … )` |
| D05 | DAX | `CALCULATE ( [Measure] )` without filters → `[Measure]` |
| D06 | DAX | 3+ nested IFs → `SWITCH ( TRUE (), … )` |
| D07 | DAX | the same measure 3+ times in one expression → variable (VAR) |
| D08 | DAX | CALCULATE filter compares only measures (`[Sales] > 0`) – Desktop rejects it (error) |
| D09 | DAX | EARLIER / EARLIEST → variable |
| D10 | DAX | USERELATIONSHIP between columns without a relationship (error) or on the active one (no effect) |
| D11 | DAX | time-intelligence function (TOTALYTD, SAMEPERIODLASTYEAR …) on a date from a fact table → date table column |
| D12 | DAX | complex measure (nesting depth ≥ 7, 4+ CALCULATE, or > 500 characters without VAR) |
| D13 | DAX | column without its table (`[Amount]`) / measure with a table (`Sales[Revenue]`) |

### DAX quality and rewrite proposals

Checks D01–D13 read DAX statically (no Desktop, no data) and, where a pattern can be rewritten mechanically, propose
the new expression of the whole measure – in `dax_<name>.md` (before / after) and in the HTML report:

- an **exact rewrite** returns the same result (D03, D05, D06, D07, D13, D01 with `ALL ( column )`, D02 – returns blank
  instead of an error on division by zero). `oprav.py --template` pre-fills it in a row with action `dax`;
- a **rewrite to verify** changes behaviour, usually because it fixes a bug (D01 FILTER → KEEPFILTERS, D04, D11 fact
  date → date table). It is only in the `context` column – compare the numbers in Desktop, then copy it to `value`.

The analysis knows neither the data nor the visual context: it can't tell whether a measure returns the "right" number
in business terms, and it doesn't rewrite complex measures (D12). That's a job for an AI over `model_<name>.md` – it can
explain what a measure does and propose a rewrite with reasoning; write the result back with `oprav.py` (action `dax`).

### HTML report (`--html`)

`audit_<name>.html` is a single file with no external resources (open it in a browser, e-mail it, print to PDF):
status metrics, AI score per component, findings by area and severity (filters and search), a recommendation for each
group, DAX before / after and **Next steps** – an order of work derived by rules from the findings (errors → model
warnings → RLS → DAX → weakest AI score components → report → re-run with `--baseline`). Light and dark mode follow
the system. The report is in English with `--lang en`, otherwise in Czech.

The one thing Python can't write meaningfully is the **narrative summary for the client** (what the numbers mean for
their reporting). Without it the HTML shows a ready-made AI prompt; add the AI's text (or your own, Markdown) with
`--summary summary.md`.

**How the RLS check computes reach:** a role filter travels only along active relationships, from the one side to the
many side (for many-to-many from the "to" side to the "from" side); the other way only for 1:1 relationships or with
*Apply security filter in both directions*. RLS never uses USERELATIONSHIP or bidirectional cross-filtering without the
security setting. The check is static – it doesn't know role members or data, so it can't prove the filter returns the
right rows; it proves the filter gets everywhere it needs to.

**AI readiness score** = weighted average (`VAHY_AI` in `audit.py`): measure descriptions 25 %, visible column
descriptions 20 %, table descriptions 15 %, hidden technical columns 15 %, readable names 10 %, measures in display
folders 10 %, marked date table 5 %. Copilot and AI agents over the model read exactly these names, descriptions and
structure. (Until 11/2026 the score had only the first four components – older audits aren't directly comparable.)

## Recommended workflow for auditing someone else's report

1. Save the report as PBIP (PBIR + TMDL) into its own folder and put it under git – every change can be reverted.
2. `audit.py --html` → errors first (M10, M11, M20, M22, R11, S01, S05, D08, D10), then warnings (for RLS mainly S02).
   If the client has its own terminology, prepare `client.json` (glossary, measure families) and run with `--settings`.
3. `oprav.py --template` + `ai_dokumentace.py` → give an AI both the documentation and the template and let it fill in
   descriptions, folders and formats; review, then `oprav.py … --write` – the fastest way to an AI score above 80.
4. Do renames (M09, M13) in Desktop or Tabular Editor – references in DAX and visuals must be fixed too.
5. `porovnej.py backup/… current/…` → a before/after summary for the client; final `audit.py --html --summary summary.md` as the deliverable.
