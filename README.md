# tools

Free tools for Power BI and data work by [Jakub Vozar](https://jakubvozar.cz). MIT licence.

🇨🇿 [Česká verze](README.cs.md)

| Tool | What it does | Download |
|---|---|---|
| [pbip_audit](pbip_audit/README.en.md) | Audit any Power BI project (PBIP) without Power BI Desktop: 58 checks of the model, report, DAX quality, AI/Copilot readiness and row-level security, AI readiness score 0–100, DAX simplification proposals, graphical HTML report, model documentation for LLMs, before/after comparison, client glossary and exceptions, baseline and exit codes for CI, bulk fixes of descriptions, hidden fields, display folders and formats in TMDL. Output in English (`--lang en`) or Czech. Pure Python 3.10+, no dependencies. | [pbip_audit.zip](https://github.com/vzr-repo/tools/releases/download/pbip-audit-latest/pbip_audit.zip) |

**Claude Code:** `/plugin marketplace add vzr-repo/tools` → `/plugin install pbip-audit@vzr-tools`.

Each tool lives in its own folder with its own README. The zip in the Download column is rebuilt automatically on
every change and always holds the latest version.
