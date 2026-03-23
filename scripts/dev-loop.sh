#!/usr/bin/env bash
# ============================================================================
# vimtg Dev Loop — Autonomous Build Pipeline
# ============================================================================
#
# Builds vimtg from Phase 0 (scaffold) through Phase 10 (polish) using
# sequential claude -p calls with verification gates between each step.
#
# Usage:
#   ./scripts/dev-loop.sh                    # Run full pipeline
#   ./scripts/dev-loop.sh --resume           # Resume from last completed step
#   ./scripts/dev-loop.sh --from phase-03a   # Start from specific step
#   ./scripts/dev-loop.sh --step phase-01b   # Run single step only
#   ./scripts/dev-loop.sh --dry-run          # Print steps without executing
#
# Environment:
#   MAX_DURATION=28800     # Max runtime in seconds (default: 8h)
#   CLAUDE_MODEL=sonnet    # Model override (default: per-step routing)
#   SKIP_VERIFY=1          # Skip verification gates (not recommended)
#   SKIP_DESLOP=1          # Skip de-sloppify passes
#   VERBOSE=1              # Show claude output in terminal
#
# ============================================================================

set -uo pipefail

# === Constants ===

readonly PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
readonly SCRIPTS_DIR="$PROJECT_DIR/scripts"
readonly PROMPTS_DIR="$SCRIPTS_DIR/prompts"
readonly LOG_DIR="$PROJECT_DIR/.dev-loop/logs"
readonly STATE_FILE="$PROJECT_DIR/.dev-loop/state"
readonly PROGRESS_FILE="$PROJECT_DIR/PROGRESS.md"
readonly LOCK_FILE="$PROJECT_DIR/.dev-loop/lock"
readonly START_TIME=$(date +%s)
readonly MAX_DURATION="${MAX_DURATION:-28800}"
readonly DESLOP_PROMPT="$PROMPTS_DIR/desloppify.md"

# === Colors ===

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly DIM='\033[2m'
readonly BOLD='\033[1m'
readonly RESET='\033[0m'

# === Step Registry ===
#
# Format: "step_id|phase|model|commit_message"
# Steps execute in order. Each step: implement -> desloppify -> verify -> commit

readonly STEPS=(
    "phase-00|0|sonnet|chore: scaffold project with pyproject.toml, CI, and package structure"
    "phase-01a|1|sonnet|feat: add Card domain model with Scryfall parser and database schema"
    "phase-01b|1|sonnet|feat: add CardRepository with FTS5 search"
    "phase-01c|1|sonnet|feat: add Scryfall bulk sync, SearchService, and CLI commands"
    "phase-02a|2|sonnet|feat: add Deck domain model and format parser with round-trip fidelity"
    "phase-02b|2|sonnet|feat: add DeckService with validation and CLI commands"
    "phase-03a|3|sonnet|feat: add Buffer, Cursor, and motion system"
    "phase-03b|3|sonnet|feat: add Mode manager and key sequence parser"
    "phase-03c|3|opus|feat: add TUI widgets, MainScreen, and VimTGApp with vim navigation"
    "phase-04|4|opus|feat: add insert mode with fuzzy search and inline card expansion"
    "phase-05a|5|sonnet|feat: add ex command parser, registry, and core commands"
    "phase-05b|5|opus|feat: add operators, registers, visual mode, and marks"
    "phase-06|6|sonnet|feat: add snapshot-based undo tree with branches and checkpoints"
    "phase-07|7|sonnet|feat: add deck analytics with mana curve and stats overlay"
    "phase-08a|8|opus|feat: add global command, substitute, and filter with pipes"
    "phase-08b|8|opus|feat: add multi-buffer, dot repeat, macros, and text objects"
    "phase-09|9|sonnet|feat: add MTGO, Arena, Moxfield, and Archidekt import/export"
    "phase-10|10|opus|feat: polish help system, error handling, config, and packaging"
)

# Phase tags for git tagging (function for bash 3 compat)
get_phase_tag() {
    case "$1" in
        0)  echo "v0.0.1" ;;
        1)  echo "v0.1.0" ;;
        2)  echo "v0.2.0" ;;
        3)  echo "v0.3.0" ;;
        4)  echo "v0.4.0" ;;
        5)  echo "v0.5.0" ;;
        6)  echo "v0.6.0" ;;
        7)  echo "v0.7.0" ;;
        8)  echo "v0.8.0" ;;
        9)  echo "v0.9.0" ;;
        10) echo "v1.0.0" ;;
        *)  echo "" ;;
    esac
}

# === Utility Functions ===

log() {
    local level="$1"; shift
    local timestamp
    timestamp="$(date '+%H:%M:%S')"
    case "$level" in
        INFO)  echo -e "${DIM}[$timestamp]${RESET} ${BLUE}INFO${RESET}  $*" ;;
        OK)    echo -e "${DIM}[$timestamp]${RESET} ${GREEN}OK${RESET}    $*" ;;
        WARN)  echo -e "${DIM}[$timestamp]${RESET} ${YELLOW}WARN${RESET}  $*" ;;
        ERROR) echo -e "${DIM}[$timestamp]${RESET} ${RED}ERROR${RESET} $*" ;;
        STEP)  echo -e "${DIM}[$timestamp]${RESET} ${CYAN}${BOLD}STEP${RESET}  $*" ;;
        PHASE) echo -e "\n${DIM}[$timestamp]${RESET} ${BOLD}═══ $* ═══${RESET}\n" ;;
    esac
}

elapsed() {
    local now
    now=$(date +%s)
    echo $(( now - START_TIME ))
}

elapsed_human() {
    local secs
    secs=$(elapsed)
    printf '%dh %dm %ds' $((secs/3600)) $((secs%3600/60)) $((secs%60))
}

check_time_limit() {
    if (( $(elapsed) >= MAX_DURATION )); then
        log WARN "Time limit reached ($(elapsed_human)). Stopping gracefully."
        log INFO "Resume with: ./scripts/dev-loop.sh --resume"
        finalize
        exit 0
    fi
}

# === State Management ===

init_state() {
    mkdir -p "$LOG_DIR"
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "0" > "$STATE_FILE"
    fi
}

get_completed_count() {
    cat "$STATE_FILE" 2>/dev/null || echo "0"
}

mark_completed() {
    local step_index="$1"
    echo "$((step_index + 1))" > "$STATE_FILE"
}

get_step_field() {
    local step_entry="$1"
    local field="$2"
    echo "$step_entry" | cut -d'|' -f"$field"
}

# === Lock Management ===

acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local pid
        pid=$(cat "$LOCK_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log ERROR "Another dev-loop is running (PID $pid). Remove $LOCK_FILE to override."
            exit 1
        fi
        log WARN "Stale lock found (PID $pid not running). Removing."
        rm -f "$LOCK_FILE"
    fi
    echo $$ > "$LOCK_FILE"
    trap cleanup EXIT INT TERM
}

cleanup() {
    rm -f "$LOCK_FILE"
    log INFO "Lock released. Elapsed: $(elapsed_human)"
}

# === Progress File ===

init_progress() {
    if [[ ! -f "$PROGRESS_FILE" ]]; then
        cat > "$PROGRESS_FILE" << 'PROGRESS'
# vimtg Build Progress

> Auto-updated by dev-loop.sh. Each step records what was built.
> Claude reads this at the start of each step for cross-iteration context.

## Completed Steps

_None yet._

## Current State

- Project: not started
- Tests passing: N/A
- Coverage: N/A

## Notes

_The dev-loop populates this as it builds each phase._
PROGRESS
    fi
}

update_progress() {
    local step_id="$1"
    local phase="$2"
    local description="$3"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M')"

    # Replace "_None yet._" on first update
    if grep -q "_None yet._" "$PROGRESS_FILE"; then
        sed -i '' 's/_None yet._//' "$PROGRESS_FILE"
    fi

    # Append completion record
    sed -i '' "/^## Completed Steps/a\\
- [x] \`$step_id\` (phase $phase) — $description — $timestamp
" "$PROGRESS_FILE"

    # Update current state section
    local test_result coverage_result
    test_result=$(cd "$PROJECT_DIR" && python -m pytest --tb=no -q 2>&1 | tail -1 || echo "no tests")
    coverage_result=$(cd "$PROJECT_DIR" && python -m pytest --cov=vimtg --cov-report=term-missing --tb=no -q 2>&1 | grep "^TOTAL" | awk '{print $NF}' || echo "N/A")

    cat > /tmp/vimtg-state-update.txt << EOF
## Current State

- Project: phase $phase in progress
- Last step: \`$step_id\`
- Tests: $test_result
- Coverage: ${coverage_result:-N/A}
- Elapsed: $(elapsed_human)
EOF

    # Replace current state block
    sed -i '' '/^## Current State/,/^## Notes/{/^## Notes/!d;}' "$PROGRESS_FILE"
    sed -i '' "/^## Notes/e cat /tmp/vimtg-state-update.txt" "$PROGRESS_FILE" 2>/dev/null || true
    rm -f /tmp/vimtg-state-update.txt
}

# === Verification Gate ===

verify() {
    local step_id="$1"
    local phase="$2"
    local log_file="$LOG_DIR/${step_id}-verify.log"

    if [[ "${SKIP_VERIFY:-}" == "1" ]]; then
        log WARN "Verification skipped (SKIP_VERIFY=1)"
        return 0
    fi

    log INFO "Running verification gate..."

    cd "$PROJECT_DIR"

    # Ensure package is installed
    pip install -e ".[dev]" > "$log_file" 2>&1 || true

    local failed=0

    # Lint
    log INFO "  Lint (ruff)..."
    if ruff check src/ tests/ >> "$log_file" 2>&1; then
        log OK "  Lint passed"
    else
        log WARN "  Lint issues found — attempting auto-fix"
        ruff check --fix src/ tests/ >> "$log_file" 2>&1 || true
        if ruff check src/ tests/ >> "$log_file" 2>&1; then
            log OK "  Lint passed after auto-fix"
        else
            log ERROR "  Lint still failing"
            failed=1
        fi
    fi

    # Type check (skip for phase 0 — not enough code)
    if (( phase > 0 )); then
        log INFO "  Type check (mypy)..."
        if mypy src/ >> "$log_file" 2>&1; then
            log OK "  Type check passed"
        else
            log WARN "  Type errors found (non-blocking for now)"
        fi
    fi

    # Tests
    log INFO "  Tests (pytest)..."
    if python -m pytest --tb=short -q >> "$log_file" 2>&1; then
        log OK "  Tests passed"
    else
        log ERROR "  Tests failing"
        failed=1
    fi

    # Coverage (progressive threshold)
    local cov_threshold
    case "$phase" in
        0|1) cov_threshold=60 ;;
        2|3) cov_threshold=70 ;;
        *)   cov_threshold=80 ;;
    esac

    log INFO "  Coverage (target: ${cov_threshold}%)..."
    local cov
    cov=$(python -m pytest --cov=vimtg --cov-report=term-missing --tb=no -q 2>&1 | grep "^TOTAL" | awk '{print $NF}' | tr -d '%' || echo "0")
    if [[ -n "$cov" ]] && (( ${cov%%.*} >= cov_threshold )); then
        log OK "  Coverage: ${cov}% (>= ${cov_threshold}%)"
    else
        log WARN "  Coverage: ${cov:-unknown}% (target: ${cov_threshold}%) — non-blocking"
    fi

    if (( failed )); then
        log ERROR "Verification failed for $step_id. See $log_file"
        return 1
    fi

    return 0
}

# === Claude Execution ===

run_claude() {
    local step_id="$1"
    local model="$2"
    local prompt_file="$3"
    local purpose="$4"
    local log_file="$LOG_DIR/${step_id}-${purpose}.log"

    # Override model if env var set
    model="${CLAUDE_MODEL:-$model}"

    if [[ ! -f "$prompt_file" ]]; then
        log ERROR "Prompt file not found: $prompt_file"
        return 1
    fi

    local prompt
    prompt="$(cat "$prompt_file")"

    log INFO "Running claude ($model) for $step_id [$purpose]..."
    log INFO "  Prompt: $(wc -l < "$prompt_file") lines from $(basename "$prompt_file")"

    local exit_code=0
    if [[ "${VERBOSE:-}" == "1" ]]; then
        cd "$PROJECT_DIR" && claude -p "$prompt" --model "$model" 2>&1 | tee "$log_file" || exit_code=$?
    else
        cd "$PROJECT_DIR" && claude -p "$prompt" --model "$model" > "$log_file" 2>&1 || exit_code=$?
    fi

    if (( exit_code != 0 )); then
        log ERROR "Claude exited with code $exit_code. Log: $log_file"
        return 1
    fi

    log OK "Claude completed [$purpose]"
    return 0
}

# === Git Operations ===

git_commit() {
    local message="$1"
    cd "$PROJECT_DIR"

    # Stage all changes (excluding dev-loop artifacts)
    git add -A
    git reset -- .dev-loop/ > /dev/null 2>&1 || true
    git reset -- PROGRESS.md > /dev/null 2>&1 || true

    # Check if there are changes to commit
    if git diff --cached --quiet; then
        log WARN "No changes to commit"
        return 0
    fi

    git commit -m "$message" || {
        log ERROR "Commit failed"
        return 1
    }
    log OK "Committed: $message"
}

git_tag_phase() {
    local phase="$2"
    local tag
    tag="$(get_phase_tag "$phase")"

    if [[ -z "$tag" ]]; then
        return 0
    fi

    # Check if this is the last step of this phase
    local step_id="$1"
    local next_phase=""
    local found=0
    for entry in "${STEPS[@]}"; do
        local sid sphase
        sid=$(get_step_field "$entry" 1)
        sphase=$(get_step_field "$entry" 2)
        if (( found )); then
            next_phase="$sphase"
            break
        fi
        if [[ "$sid" == "$step_id" ]]; then
            found=1
        fi
    done

    # Only tag if next step is a different phase (or this is the last step)
    if [[ "$next_phase" != "$phase" ]]; then
        cd "$PROJECT_DIR"
        git tag -a "$tag" -m "Release $tag — Phase $phase complete" 2>/dev/null || true
        log OK "Tagged: $tag"
    fi
}

# === Step Execution ===

run_step() {
    local step_index="$1"
    local entry="${STEPS[$step_index]}"

    local step_id phase model commit_msg
    step_id=$(get_step_field "$entry" 1)
    phase=$(get_step_field "$entry" 2)
    model=$(get_step_field "$entry" 3)
    commit_msg=$(get_step_field "$entry" 4)

    local prompt_file="$PROMPTS_DIR/${step_id}.md"

    log STEP "${BOLD}[$((step_index + 1))/${#STEPS[@]}]${RESET} ${CYAN}$step_id${RESET} — $commit_msg"

    # Check time limit before starting
    check_time_limit

    # 1. Implement
    if ! run_claude "$step_id" "$model" "$prompt_file" "implement"; then
        log ERROR "Implementation failed for $step_id"
        log INFO "Attempting recovery with fix prompt..."
        run_fix_pass "$step_id" "$model"
    fi

    # 2. De-sloppify
    if [[ "${SKIP_DESLOP:-}" != "1" ]] && [[ -f "$DESLOP_PROMPT" ]]; then
        run_claude "$step_id" "sonnet" "$DESLOP_PROMPT" "desloppify" || true
    fi

    # 3. Verify
    local verify_attempts=0
    local max_verify_attempts=3
    while (( verify_attempts < max_verify_attempts )); do
        if verify "$step_id" "$phase"; then
            break
        fi
        verify_attempts=$((verify_attempts + 1))
        if (( verify_attempts < max_verify_attempts )); then
            log WARN "Verification failed (attempt $verify_attempts/$max_verify_attempts). Running fix pass..."
            run_fix_pass "$step_id" "$model"
        else
            log WARN "Verification still failing after $max_verify_attempts attempts. Proceeding anyway."
        fi
    done

    # 4. Commit
    git_commit "$commit_msg"

    # 5. Tag if phase boundary
    git_tag_phase "$step_id" "$phase"

    # 6. Update progress
    update_progress "$step_id" "$phase" "$commit_msg"

    # 7. Mark completed
    mark_completed "$step_index"

    log OK "Step $step_id complete ($(elapsed_human) elapsed)"
}

run_fix_pass() {
    local step_id="$1"
    local model="$2"
    local fix_log="$LOG_DIR/${step_id}-implement.log"

    # Build a context-aware fix prompt from the failure log
    local tail_log
    tail_log=$(tail -100 "$fix_log" 2>/dev/null || echo "no log available")

    local fix_prompt
    fix_prompt="$(cat << FIXEOF
You are fixing issues from a previous implementation step in the vimtg project.

The project is a TUI-based Magic: The Gathering deck builder using Python 3.12+ and Textual.

Read PROGRESS.md to understand what has been built so far.

The previous step failed or produced issues. Here is the tail of the log:

\`\`\`
$tail_log
\`\`\`

Fix the issues:
1. Read the error messages carefully
2. Fix the root cause (do not just suppress errors)
3. Run the tests to verify: python -m pytest --tb=short -q
4. Run lint to verify: ruff check src/ tests/
5. If lint fails, run: ruff check --fix src/ tests/

Do NOT add new features. Only fix what is broken.
FIXEOF
)"

    cd "$PROJECT_DIR" && claude -p "$fix_prompt" --model "$model" > "$LOG_DIR/${step_id}-fix.log" 2>&1 || true
}

# === Phase Banner ===

print_phase_banner() {
    local phase="$1"
    local desc
    case "$phase" in
        0)  desc="Project Scaffolding" ;;
        1)  desc="Card Database + Scryfall Sync" ;;
        2)  desc="Deck Format Parser" ;;
        3)  desc="Core TUI + Vim Navigation" ;;
        4)  desc="Insert Mode + Fuzzy Search" ;;
        5)  desc="Commands + Visual Mode" ;;
        6)  desc="History / Undo System" ;;
        7)  desc="Analytics Panel" ;;
        8)  desc="Bulk Operations + Multi-Deck" ;;
        9)  desc="Import/Export Formats" ;;
        10) desc="Polish + Packaging" ;;
        *)  desc="Unknown" ;;
    esac
    log PHASE "Phase $phase: $desc ($(get_phase_tag "$phase"))"
}

# === Main Entry Point ===

main() {
    local start_from=""
    local single_step=""
    local dry_run=0
    local resume=0

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --resume)     resume=1; shift ;;
            --from)       start_from="$2"; shift 2 ;;
            --step)       single_step="$2"; shift 2 ;;
            --dry-run)    dry_run=1; shift ;;
            --help|-h)    usage; exit 0 ;;
            *)            log ERROR "Unknown argument: $1"; usage; exit 1 ;;
        esac
    done

    # Print header
    echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║  vimtg Dev Loop — Autonomous Build Pipeline  ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}\n"
    log INFO "Project: $PROJECT_DIR"
    log INFO "Max duration: $((MAX_DURATION / 3600))h"
    log INFO "Steps: ${#STEPS[@]}"

    # Initialize
    init_state
    init_progress
    acquire_lock

    # Determine starting step
    local start_index=0
    if (( resume )); then
        start_index=$(get_completed_count)
        if (( start_index >= ${#STEPS[@]} )); then
            log OK "All steps already completed!"
            exit 0
        fi
        log INFO "Resuming from step $((start_index + 1))/${#STEPS[@]}"
    elif [[ -n "$start_from" ]]; then
        for i in "${!STEPS[@]}"; do
            local sid
            sid=$(get_step_field "${STEPS[$i]}" 1)
            if [[ "$sid" == "$start_from" ]]; then
                start_index=$i
                echo "$start_index" > "$STATE_FILE"
                break
            fi
        done
        log INFO "Starting from step $start_from (index $start_index)"
    fi

    # Single step mode
    if [[ -n "$single_step" ]]; then
        for i in "${!STEPS[@]}"; do
            local sid
            sid=$(get_step_field "${STEPS[$i]}" 1)
            if [[ "$sid" == "$single_step" ]]; then
                if (( dry_run )); then
                    echo "Would run: $single_step"
                else
                    run_step "$i"
                fi
                finalize
                exit 0
            fi
        done
        log ERROR "Step not found: $single_step"
        exit 1
    fi

    # Dry run
    if (( dry_run )); then
        echo -e "\n${BOLD}Steps to execute:${RESET}\n"
        for i in "${!STEPS[@]}"; do
            if (( i < start_index )); then
                echo -e "  ${DIM}[skip] $(get_step_field "${STEPS[$i]}" 1)${RESET}"
            else
                local sid phase model msg
                sid=$(get_step_field "${STEPS[$i]}" 1)
                phase=$(get_step_field "${STEPS[$i]}" 2)
                model=$(get_step_field "${STEPS[$i]}" 3)
                msg=$(get_step_field "${STEPS[$i]}" 4)
                echo -e "  ${CYAN}[$((i+1))]${RESET} $sid ${DIM}(phase $phase, $model)${RESET} — $msg"
            fi
        done
        echo ""
        exit 0
    fi

    # === Main Loop ===

    local current_phase=-1
    for i in "${!STEPS[@]}"; do
        if (( i < start_index )); then
            continue
        fi

        local phase
        phase=$(get_step_field "${STEPS[$i]}" 2)

        # Print phase banner on phase change
        if (( phase != current_phase )); then
            current_phase=$phase
            print_phase_banner "$phase"
        fi

        run_step "$i"
    done

    finalize
}

finalize() {
    echo ""
    log PHASE "Pipeline Complete"
    log INFO "Total time: $(elapsed_human)"
    log INFO "Logs: $LOG_DIR/"

    local completed
    completed=$(get_completed_count)
    log INFO "Steps completed: $completed/${#STEPS[@]}"

    if (( completed >= ${#STEPS[@]} )); then
        echo -e "\n${GREEN}${BOLD}  vimtg v1.0.0 is ready.${RESET}\n"
    else
        local next_step
        next_step=$(get_step_field "${STEPS[$completed]}" 1)
        log INFO "Next step: $next_step"
        log INFO "Resume: ./scripts/dev-loop.sh --resume"
    fi
}

usage() {
    cat << 'EOF'
Usage: ./scripts/dev-loop.sh [OPTIONS]

Options:
  --resume        Resume from last completed step
  --from STEP     Start from a specific step (e.g., phase-03a)
  --step STEP     Run only a single step
  --dry-run       Print step plan without executing
  --help, -h      Show this help

Environment Variables:
  MAX_DURATION    Max runtime in seconds (default: 28800 = 8h)
  CLAUDE_MODEL    Override model for all steps (default: per-step routing)
  SKIP_VERIFY     Skip verification gates (default: 0)
  SKIP_DESLOP     Skip de-sloppify passes (default: 0)
  VERBOSE         Show claude output live (default: 0)

Steps:
  phase-00        Project scaffolding
  phase-01a       Card domain model + database
  phase-01b       CardRepository + FTS5 search
  phase-01c       Scryfall sync + SearchService + CLI
  phase-02a       Deck model + format parser
  phase-02b       DeckService + CLI commands
  phase-03a       Buffer + Cursor + Motions
  phase-03b       Modes + Keymap
  phase-03c       TUI widgets + MainScreen + App
  phase-04        Insert mode + fuzzy search
  phase-05a       Ex commands + core handlers
  phase-05b       Operators + registers + visual + marks
  phase-06        History / undo system
  phase-07        Analytics panel
  phase-08a       Global command + substitute + filter
  phase-08b       Multi-buffer + dot repeat + macros
  phase-09        Import/export formats
  phase-10        Polish + packaging
EOF
}

main "$@"
