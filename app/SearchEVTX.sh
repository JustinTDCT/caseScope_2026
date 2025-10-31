#!/usr/bin/env bash
set -euo pipefail

# SearchEVTX.sh — grep JSONL exports for a keyword (case-insensitive)
# Supports literal quoted strings and JSON key/value pairs.
#
# Usage:
#   ./SearchEVTX.sh <folder-with-jsonl> "<query>"
#   ./SearchEVTX.sh <folder-with-jsonl> --literal '"EventID":5145'
#   ./SearchEVTX.sh <folder-with-jsonl> --json 'EventID=5145'
#   ./SearchEVTX.sh <folder-with-jsonl> '"EventID":5145'        # auto-detects JSON pair
#
# Notes:
# - Default behavior is LITERAL (-F) unless we auto-detect a JSON pair:
#     1) "Key":Value      (quotes optional; value can be number or string)
#     2) Key=Value
#   In JSON mode we match optional whitespace:  "Key"\s*:\s*Value
# - Wrap queries that contain double quotes in single quotes when calling:
#     './SearchEVTX.sh ./out '"EventID":5145''

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <folder-with-jsonl> [--literal|--json] \"<query>\"" >&2
  exit 1
fi

SRC_DIR="$1"
shift

MODE="auto"
if [[ "${1:-}" == "--literal" || "${1:-}" == "--json" ]]; then
  MODE="${1#--}"
  shift
fi

KEYWORD="${1:-}"

if [[ -z "$KEYWORD" ]]; then
  echo "ERROR: missing query" >&2
  exit 1
fi

if [[ ! -d "$SRC_DIR" ]]; then
  echo "ERROR: not a directory: $SRC_DIR" >&2
  exit 2
fi

# Output folder name derived from the query (safe)
SAFE_KEYWORD="$(echo "$KEYWORD" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/_/g')"
OUT_DIR="$(pwd)/${SAFE_KEYWORD}"
mkdir -p "$OUT_DIR"

echo "[*] Source folder: $SRC_DIR"
echo "[*] Query:         $KEYWORD"
echo "[*] Mode:          $MODE (auto switches to 'json' if query looks like a JSON pair)"
echo "[*] Output folder: $OUT_DIR"

# Decide effective mode if auto
if [[ "$MODE" == "auto" ]]; then
  # Looks like "Key":Value  OR Key:Value  OR Key=Value
  if [[ "$KEYWORD" =~ ^\"?[A-Za-z0-9_.-]+\"?[[:space:]]*:[[:space:]]*.+$ || "$KEYWORD" =~ ^[A-Za-z0-9_.-]+[[:space:]]*=[[:space:]]*.+$ ]]; then
    MODE="json"
  else
    MODE="literal"
  fi
fi

# Build pattern and grep args
GREP_ARGS=(-i --)
PATTERN="$KEYWORD"
if [[ "$MODE" == "literal" ]]; then
  # Fixed-string search (quotes are matched literally)
  GREP_ARGS=(-i -F --)
elif [[ "$MODE" == "json" ]]; then
  # Convert Key=Value to "Key":Value for uniform handling
  if [[ "$KEYWORD" =~ ^([A-Za-z0-9_.-]+)[[:space:]]*=[[:space:]]*(.+)$ ]]; then
    KEY="${BASH_REMATCH[1]}"
    VAL="${BASH_REMATCH[2]}"
    # If value looks like a bare word/number, leave as is; else keep it as typed
    :
  elif [[ "$KEYWORD" =~ ^\"?([A-Za-z0-9_.-]+)\"?[[:space:]]*:[[:space:]]*(.+)$ ]]; then
    KEY="${BASH_REMATCH[1]}"
    VAL="${BASH_REMATCH[2]}"
  else
    # Fallback: treat literally
    GREP_ARGS=(-i -F --)
    MODE="literal"
  fi

  if [[ "$MODE" == "json" ]]; then
    # Build a whitespace-tolerant regex:  "Key"\s*:\s*Value
    # Keep VAL as typed, but if it's a bare word without quotes/spaces, match either quoted or bare.
    # Examples it will match:
    #   "EventID":5145
    #   "EventID" : 5145
    #   "Host":"example"
    VAL_TRIM="$(echo "$VAL" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"

    # If VAL is bare alnum/._- (no quotes, no spaces), allow optional quotes in pattern
    if [[ "$VAL_TRIM" =~ ^[A-Za-z0-9_.-]+$ ]]; then
      PATTERN="\"$KEY\"[[:space:]]*:[[:space:]]*\"?${VAL_TRIM}\"?"
    else
      # Use as-is (user can include quotes/regex)
      # Escape backslashes in VAL to keep regex sane
      VAL_ESCAPED="$(printf '%s' "$VAL_TRIM" | sed 's/\\/\\\\/g')"
      PATTERN="\"$KEY\"[[:space:]]*:[[:space:]]*$VAL_ESCAPED"
    fi
    GREP_ARGS=(-i -E --)
  fi
fi

count=0
matched=0

shopt -s nullglob
files=("$SRC_DIR"/*.jsonl)
if [[ ${#files[@]} -eq 0 ]]; then
  echo "No .jsonl files found in: $SRC_DIR"
  exit 0
fi

for src in "${files[@]}"; do
  base="$(basename "$src")"
  stem="${base%.jsonl}"
  out="${OUT_DIR}/${stem}_${SAFE_KEYWORD}.jsonl"

  echo "➡️  Checking: $base"

  tmp="$(mktemp)"
  if grep "${GREP_ARGS[@]}" "$PATTERN" "$src" > "$tmp"; then
    matches=$(wc -l < "$tmp" || echo 0)
    if [[ $matches -gt 0 ]]; then
      mv "$tmp" "$out"
      echo "   [✓] matches: $matches → $out"
      matched=$((matched+1))
    else
      rm -f "$tmp"
      echo "   [–] no matches"
    fi
  else
    rc=$?
    rm -f "$tmp"
    if [[ $rc -eq 1 ]]; then
      echo "   [–] no matches"
    else
      echo "   [!] grep error (rc=$rc), skipping"
    fi
  fi

  count=$((count+1))
done

echo "✔ Done. Processed $count files. Matches in $matched file(s). Results: $OUT_DIR"
