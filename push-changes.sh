#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Стейджимо всі нові файли
git add -A

# Комітимо
git commit -m "Add custom modules and local agent files

New modules: calendar_next_event, night_light, screen_lock_state,
theme_switcher, uptime_boot_time, wallpaper_switcher.
Also include AGENTS.md, .codex and resume.sh."

# Пушимо у форк (origin -> github.com/grigorii-horos/lnxlink)
git push -u origin master
