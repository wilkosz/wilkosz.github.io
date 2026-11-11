#!/bin/zsh
# Runs one site routine headless, alternating by hour (launchd fires this every 6 hours).
#   05:07 and 17:07 -> market-research
#   11:07 and 23:07 -> asset-hunt
# Override: scripts/routine.sh asset-hunt
set -u
REPO="$HOME/GitHub/wilkosz.github.io"
LOG="$HOME/Library/Logs/wilkosz-routines.log"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

skill="${1:-}"
if [[ -z "$skill" ]]; then
  case $(date +%H) in
    04|05|06|16|17|18) skill=market-research ;;
    *)                 skill=asset-hunt ;;
  esac
fi

# one run at a time: a slow hunt must not overlap the next research pass
LOCK="/tmp/wilkosz-routine.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date '+%F %T') skip $skill: previous run still going" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK"' EXIT

cd "$REPO" || exit 1
echo "$(date '+%F %T') start $skill" >> "$LOG"
prompt="/$skill"
if [[ "$skill" == asset-hunt ]]; then
  # unattended runs cut corners unless told otherwise
  prompt="/asset-hunt Full unattended run. Re-open every live find and update or mark it sold. Search every source in the skill's table in Chrome, for every want with status hunting, plus each want's own sources. Do not stop early or skip sources to save time; list any source that failed in notes."
fi
claude -p "$prompt" --chrome --permission-mode bypassPermissions >> "$LOG" 2>&1
echo "$(date '+%F %T') end $skill (exit $?)" >> "$LOG"
