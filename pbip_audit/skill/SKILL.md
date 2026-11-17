---
name: pbip-audit
description: Audit libovolného Power BI reportu uloženého jako PBIP a příprava modelu pro AI – 58 kontrol modelu, reportu, kvality DAX (s návrhem zjednodušení měr), připravenosti pro Copilot a zabezpečení (dojde filtr RLS ke všem datům?), skóre AI 0–100, grafický HTML report, dokumentace modelu pro AI, porovnání před/po a hromadné opravy v TMDL (popisy, skrytí, složky, formáty, DAX). Použij vždy, když uživatel chce auditovat, zkontrolovat nebo „projet“ Power BI report či sémantický model, najít chyby, nepoužitá pole, chybějící popisy, zbytečně složité nebo chybné míry, zkontrolovat RLS, připravit model pro Copilot / AI, zdokumentovat model, vygenerovat report auditu, nebo zmíní .pbip, PBIR, TMDL, model.bim – i bez slova „audit“ (např. „mrkni mi na tenhle report“, „co je špatně v mém modelu“). Audit an arbitrary Power BI PBIP project (any language request).
---

# Audit Power BI projektu (PBIP)

Skripty ve složce `scripts/` (vedle tohoto souboru) čtou projekt PBIP přímo ze souborů – bez Power BI Desktopu, bez
připojení a bez instalace balíčků (stačí Python 3.10+). Audit nic nemění; jediný skript, který report upravuje, je
`menu_stranek.py` a `oprav.py --zapsat` – ty pouštěj jen na výslovné přání.

Podporované formáty: report PBIR (`definition/pages`) i starší `report.json`; model TMDL i `model.bim`
(`*.SemanticModel` i `*.Dataset`); tenký report napojený na model v Service (pak jen kontroly reportu);
víc reportů v jedné složce (párují se s modelem podle `definition.pbir`).

## Postup

### 1. Zjisti, co auditovat
Když uživatel cestu nezadal, zeptej se jednou otázkou (AskUserQuestion, pokud je k dispozici): cesta k souboru
`.pbip`, ke složce `*.Report`, nebo ke složce, kde je víc reportů. Když zná jen přibližné místo, najdi kandidáty sám:

```powershell
Get-ChildItem -Path "<složka>" -Recurse -Filter *.pbip | Select-Object FullName
```

Pokud má uživatel jen soubor `.pbix`: audit ho neumí (je binární). Vysvětli, že v Power BI Desktopu stačí
Soubor → Uložit jako → *Soubory projektu Power BI (*.pbip)*, a počkej na cestu k projektu.

Když složka obsahuje víc reportů, zeptej se, jestli auditovat jeden (který) nebo všechny (`--vse`).

### 2. Spusť audit a dokumentaci
Python najdi příkazem `python --version` (na Windows případně `py --version`). Výstupy ukládej do složky
`audit_<název reportu>` ve stejné složce, kde leží soubor `.pbip` (ne dovnitř `*.Report` / `*.SemanticModel`),
pokud uživatel neřekne jinak; skript ji vytvoří sám. Když ve stejné složce leží i další reporty, zmiň je v shrnutí
jednou větou a nabídni jejich audit (`--vse`). `<SKILL>` je složka tohoto souboru.

```powershell
python "<SKILL>/scripts/audit.py" "<cesta k .pbip nebo složce>" --vystup "<výstup>" --html    # jeden report + HTML
python "<SKILL>/scripts/audit.py" "<složka>" --vse --vystup "<výstup>"                         # všechny reporty
python "<SKILL>/scripts/audit.py" "<cesta>" --vystup "<výstup>" --nastaveni "<klient.json>" --baseline "<výstup>/audit_<název>.csv"
python "<SKILL>/scripts/ai_dokumentace.py" "<cesta>" --vystup "<výstup>" --bez-m                 # dokumentace pro AI
```

Výstupy: `audit_<název>.md` (souhrn, skóre AI, nálezy podle oblastí s doporučením), `audit_<název>.csv` (všechny
nálezy, otevřeš v Excelu), `audit_<název>.html` (grafický report pro klienta), `dax_<název>.md` (navržené přepisy měr
před / po, jsou-li), `model_<název>.md` (celý model a stránky pro AI), u `--vse` navíc `audit_souhrn.md`.

**Slovní shrnutí do HTML** je část, kterou skript nenapíše – napiš ji ty: 5–8 vět + 3 odrážky priorit pro vedoucího
týmu, jen z `audit_<název>.md` a `model_<název>.md`, bez vymyšlených čísel. Ulož jako `<výstup>/shrnuti.md` a spusť
audit znovu s `--html --shrnuti "<výstup>/shrnuti.md"`. Nabídni to, nedělej to bez souhlasu.

Nastavení klienta (`--nastaveni`, vzor `<SKILL>/scripts/nastaveni_priklad.json`): glosář termínů (M23), rodiny měr
(M24) a výjimky s povinným důvodem. Použij ho, když uživatel zmíní firemní terminologii nebo opakovaný audit; výjimky
přidávej jen na jeho výslovné přání. `--baseline` = předchozí CSV téhož reportu (smí být i tentýž soubor).
Exit kód 3 a sekce „Model se nenačetl správně“ znamenají, že parser model nepřečetl – výsledky modelu pak nepoužívej,
řekni to uživateli a nehádej.

**Jazyk:** píše-li uživatel anglicky (nebo chce výstupy pro anglicky mluvícího klienta), přidej ke všem skriptům
`--lang en` – nálezy, MD, CSV, HTML i šablona oprav budou anglicky (šablona má pak hlavičku object;type;action;value…).
Shrnutí pak piš v jazyce uživatele. Vzor nastavení klienta s anglickými klíči je `settings_example.json`.

Když skript skončí chybou, přečti hlášku – je psaná pro člověka (např. „report není PBIR“, „víc reportů – zadej .pbip“)
a podle ní pokračuj; nepřepisuj kvůli tomu skripty.

### 3. Shrň výsledek uživateli
Přečti `audit_<název>.md` a napiš krátké shrnutí v jazyce uživatele:
- formát projektu a velikost (stránky, vizuály, tabulky, míry),
- **skóre AI připravenosti** a z čeho je nízké,
- **chyby** (M10, M11, M20, M22, R11, S01, S05, D08, D10) konkrétně – co a kde; ty mají přednost,
- **kvalita DAX** (D…): kolik měr jde zjednodušit přesně a kolik je k ověření (hlavně D11 časové funkce nad datem
  z faktu a D01 FILTER přes tabulku – ty mohou dávat jiná čísla, než uživatel čeká),
- má-li model role: **prochází RLS všude?** – S02 (tabulky s daty, ke kterým filtr role nedojde, i s důvodem),
  S06; když role nejsou, řekni to jednou větou,
- 3–5 nejužitečnějších dalších kroků (typicky: popsat míry a tabulky, skrýt technická a nepoužitá pole, titulky vizuálů),
- cesty k výstupním souborům.
Nevypisuj stovky „info“ nálezů; odkaž na CSV. Čísla ber ze souboru, nedomýšlej je.

### 4. Nabídni navazující kroky (nic nedělej bez souhlasu)
Zakonči shrnutí krátkou nabídkou, např.: „Můžu navrhnout popisy pro N měr a M tabulek, připravit seznam polí ke skrytí,
nebo audit spustit na dalších reportech ve složce. Co z toho chceš?“ Umístění nálezů ve výstupu jsou ve tvaru
„Stránka / titulek nebo typ vizuálu (id)“ – v shrnutí je používej tak, jak jsou.
- **Návrh popisů, složek, formátů a skrytí (jen TMDL):**
  1. `python "<SKILL>/scripts/oprav.py" "<cesta>" --sablona "<výstup>/navrh.csv"` – řádky z nálezů M01–M03
     (popis), M05/M06 (skrytí, předvyplněno „ano“), M14 (složka), M04/M16 (formát); sloupec `kontext` má DAX.
  2. Doplň sloupec `hodnota` z `model_<název>.md` (popis = co měří, jednotka, období, jazyk podle modelu). Řádky,
     kde si nejsi jistý, nech prázdné. Ukaž uživateli souhrn (počty, pár příkladů) a cestu k CSV k revizi.
  3. Náhled `oprav.py "<cesta>" "<navrh.csv>"` (diff), po výslovném souhlasu `--zapsat`. Předtím: projekt v gitu
     nebo záloha a Power BI Desktop zavřený (při uložení by soubory přepsal). Přejmenování oprav.py nedělá.
- **Úpravy DAX:** přesné přepisy `oprav.py --sablona` předvyplní (řádky s akcí `dax`); úpravy k ověření jsou ve
  sloupci `kontext` – převezmi je jen po souhlasu uživatele a s doporučením porovnat čísla v Desktopu. U složitých
  měr (D12) můžeš navrhnout přepis sám z `model_<název>.md`: vysvětli, co míra dělá, a nový výraz dej do `hodnota`.
- **Porovnání před/po:** zálohu (kopie složky / jiný commit) a aktuální stav porovnej
  `python "<SKILL>/scripts/porovnej.py" "<před>" "<po>" --vystup "<výstup>"` a shrň změnu skóre a vyřešené nálezy.
- **Menu stránek** (jen PBIR, jen na přání): `python "<SKILL>/scripts/menu_stranek.py" "<cesta>"`. Před spuštěním
  uložit v Desktopu a zálohovat; po spuštění v Desktopu neukládat, zavřít bez uložení a otevřít znovu.

## Co jednotlivé kontroly znamenají
Kódy a doporučení jsou přímo ve výstupu. Rychlý přehled: M01–M03 chybějící popisy (AI), M04 míry bez formátu,
M05 nepoužitá pole, M06 viditelné technické sloupce, M07 automatické datum, M08 obousměrné/neaktivní vztahy,
M09 technické názvy, M10 kolize názvů (Desktop projekt neotevře), M11 rozbité odkazy v DAX, R01 vizuály bez titulku,
R02 barvy mimo theme, R03 skryté stránky, R04 mimo plátno, R05 překryvy, R06 výkon, R08 uložený výběr slicerů,
R09 záložky měnící filtry, R10 alt text, R11 vizuál odkazuje na neexistující pole, R12 bez theme, R13 osiřelé formátování,
M12 neoznačený kalendář, M13 generické/verzované názvy, M14 míry bez složek, M15 tabulka bez vztahu, M16 procenta bez %,
M17 duplicitní míry, M18 vztah n:n, M19 počítané sloupce na faktu, R14 slicer z tabulky bez vztahu;
RLS: S01 rozbitý filtr/OLS, S02 filtr nedojde k tabulce s daty, S03 bezpečnostní filtr oběma směry, S04 role bez filtru,
S05 OLS skrývá použité pole, S06 USERNAME, S07 filtr na faktu, S08 dimenze mimo dosah (info);
M20 různé typy na koncích vztahu, M21 textový klíč (info), M22 cyklus měr, M23 nejednotné termíny podle glosáře,
M24 neúplná rodina měr (M23/M24 jen s --nastaveni);
DAX: D01 FILTER přes tabulku v CALCULATE, D02 dělení bez DIVIDE, D03 iterátor přes jeden sloupec, D04 COUNTROWS(FILTER),
D05 zbytečný CALCULATE, D06 vnořené IF, D07 opakovaná míra → VAR, D08 filtr jen z měr (chyba), D09 EARLIER,
D10 USERELATIONSHIP bez vztahu, D11 časová funkce nad datem z faktu, D12 složitá míra, D13 kvalifikace odkazů. M05 u měr = nepoužívá je tento report; jiné reporty / Excel
nad modelem audit nevidí, proto nikdy netvrď, že je míru bezpečné smazat.
RLS kontrola je statická (nezná členy rolí ani data): řekne, kam filtr dojde, ne že vrací správné řádky.
Skóre AI = popisy měr 25 % + sloupců 20 % + tabulek 15 % + skryté technické sloupce 15 % + srozumitelné názvy 10 %
+ míry ve složkách 10 % + označený kalendář 5 %.
