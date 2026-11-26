"""Nainstaluje skill pbip-audit pro Claude Code: ~/.claude/skills/pbip-audit (SKILL.md + scripts/ s aktuálními skripty).
Spusť po každé změně skriptů:  python pbip_audit/instaluj_skill.py"""
import shutil
from pathlib import Path

ZDROJ = Path(__file__).resolve().parent
CIL = Path.home() / ".claude" / "skills" / "pbip-audit"
(CIL / "scripts").mkdir(parents=True, exist_ok=True)
shutil.copy2(ZDROJ / "skills" / "pbip-audit" / "SKILL.md", CIL / "SKILL.md")
for f in ("pbip.py", "kontroly.py", "audit.py", "ai_dokumentace.py", "menu_stranek.py", "porovnej.py", "oprav.py", "dax.py", "html_report.py", "jazyk.py", "nastaveni_priklad.json", "settings_example.json"):
    shutil.copy2(ZDROJ / f, CIL / "scripts" / f)
print(f"Skill nainstalován: {CIL}")
