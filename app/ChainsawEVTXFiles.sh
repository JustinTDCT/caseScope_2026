#!/bin/bash
# ------------------------------------------------------------------------------
# Chainsaw EVTX Scan Script — v1.6
# Date: 2025-08-28
#
# Version history:
# v1.6
#   - NEW: Pull and include magicsword-io/lolrmm detections (detections/sigma)
#          and merge with SigmaHQ rules each run.
#   - Rules cache rebuilt every run to ensure both repos are up to date.
# v1.5
#   - Added built-in CSV enrichment (default ON). Produces per-file *_enriched.csv
#     and a consolidated output/_all_enriched.csv with readable EventName,
#     LogonTypeName, and Summary columns. Use --no-enrich to disable.
# v1.4
#   - Print a line for every file: "(x/xx) Scanning file - <filename>"
#   - Add a second line ONLY when there's a MATCH or an ERROR
#   - Only create output folders when matches are found
# v1.3
#   - Per-file output only when MATCH/ERROR; formatted status line
# v1.2
#   - Create per-file output folders only if matches exist; temp staging; summary
# v1.1
#   - Version header & runtime echo; resilient per-file scanning and logs
# v1.0
#   - Initial directory-wide scan (stopped on bad files)
# ------------------------------------------------------------------------------

# NOTE: not using `set -e` so one bad file doesn't kill the run
set -u

SCRIPT_VERSION="1.6"

# ---- Args --------------------------------------------------------------------
ENRICH=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-enrich) ENRICH=0 ;;
    --enrich)    ENRICH=1 ;;
    *) ;; # ignore unknown for now
  esac
  shift
done

# 🧼 Clear screen
clear

# 📌 Banner
echo "🔍 Chainsaw EVTX Scan Script"
echo "🧩 Script version: $SCRIPT_VERSION  (enrich: $([[ $ENRICH -eq 1 ]] && echo ON || echo OFF))"
echo "📦 Current directory: $(pwd)"
echo ""

# 🛠 Chainsaw presence/version
if ! command -v chainsaw &>/dev/null; then
    echo "❌ Chainsaw is not installed or not in PATH."
    exit 1
fi
CHAINSAW_VERSION="$(chainsaw --version)"
echo "🛠  Using Chainsaw version: $CHAINSAW_VERSION"
echo ""

# 📁 Paths
BASE_DIR="$(pwd)"
EVTX_DIR="$BASE_DIR"
OUTPUT_DIR="$BASE_DIR/output"
RULES_CACHE="$OUTPUT_DIR/.rules-merged"   # rebuilt every run

# --- SigmaHQ canonical repo ----------------------------------------------------
SIGMA_DIR="$HOME/sigma-rules"
SIGMA_RULES="$SIGMA_DIR/rules/windows"

# --- magicsword-io/lolrmm detections -----------------------------------------
LOLRMM_DIR="$HOME/lolrmm"
LOLRMM_SIGMA="$LOLRMM_DIR/detections/sigma"

# Chainsaw mapping (adjust if yours lives elsewhere)
MAPPING_FILE="/usr/local/bin/mappings/sigma-event-logs-all.yml"

# 📥 Mapping file
if [ ! -f "$MAPPING_FILE" ]; then
    echo "❌ Mapping file not found at: $MAPPING_FILE"
    echo "➡️  Please make sure Chainsaw mappings are installed."
    exit 1
fi

# --- Helpers ------------------------------------------------------------------
clone_or_update() {
  # $1=repo_url  $2=dest_dir
  local url="$1" dest="$2"
  if [ -d "$dest/.git" ]; then
    echo "🔄 Updating repo: $dest"
    git -C "$dest" pull --quiet || { echo "  → WARN: git pull failed for $dest"; }
  elif [ -d "$dest" ]; then
    echo "📂 Repo already present (non-git): $dest"
  else
    echo "⬇️  Cloning $url → $dest"
    mkdir -p "$(dirname "$dest")"
    if command -v git >/dev/null 2>&1; then
      git clone --quiet --depth 1 "$url" "$dest" || { echo "  → ERROR: git clone failed for $url"; return 1; }
    else
      # fallback to ZIP download
      local tmpzip
      tmpzip="$(mktemp -t repo.zip.XXXXXX)"
      curl -L -o "$tmpzip" "${url/\.git//}/archive/refs/heads/master.zip" || return 1
      unzip -q "$tmpzip" -d "$(dirname "$dest")" || return 1
      mv "$(dirname "$dest")/$(basename "$dest")-master" "$dest" 2>/dev/null || true
      rm -f "$tmpzip"
    fi
  fi
}

copy_tree() {
  # copy src -> dst, preserving structure; prefer rsync if available
  # $1=src  $2=dst
  local src="$1" dst="$2"
  if [ ! -d "$src" ]; then
    return 0
  fi
  mkdir -p "$dst"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete-excluded "$src"/ "$dst"/
  else
    # portable fallback
    (cd "$src" && tar -cf - .) | (cd "$dst" && tar -xf -)
  fi
}

# --- Pull/update rule sources -------------------------------------------------
# SigmaHQ rules
clone_or_update "https://github.com/SigmaHQ/sigma.git" "$SIGMA_DIR"

# magicsword-io/lolrmm rules
clone_or_update "https://github.com/magicsword-io/lolrmm.git" "$LOLRMM_DIR"

# Validate presence of rule dirs
if [ ! -d "$SIGMA_RULES" ]; then
  echo "❌ SigmaHQ Windows rules not found at: $SIGMA_RULES"
  exit 1
fi
if [ ! -d "$LOLRMM_SIGMA" ]; then
  echo "⚠️  magicsword-io/lolrmm sigma detections not found at: $LOLRMM_SIGMA"
  echo "   (continuing with SigmaHQ rules only)"
fi

# --- Build merged rules cache each run ----------------------------------------
rm -rf "$RULES_CACHE"
mkdir -p "$RULES_CACHE"

# 1) Copy SigmaHQ Windows rules
echo "📚 Staging SigmaHQ rules → $RULES_CACHE/sigma"
copy_tree "$SIGMA_RULES" "$RULES_CACHE/sigma"

# 2) Overlay/add lolrmm detections/sigma
if [ -d "$LOLRMM_SIGMA" ]; then
  echo "🧩 Adding lolrmm detections → $RULES_CACHE/lolrmm"
  copy_tree "$LOLRMM_SIGMA" "$RULES_CACHE/lolrmm"
fi

# ✅ Output & logs
mkdir -p "$OUTPUT_DIR"
FAILED_LOG="$OUTPUT_DIR/_failed.txt"
ERROR_LOG="$OUTPUT_DIR/_errors.log"
SUMMARY_LOG="$OUTPUT_DIR/_summary.txt"
: > "$FAILED_LOG"
: > "$ERROR_LOG"
: > "$SUMMARY_LOG"

# 🔍 Discover files (recursive, case-insensitive)
TOTAL_FILES=$(find "$EVTX_DIR" -type f \( -iname "*.evtx" -o -iname "*.evt" \) | wc -l | tr -d ' ')
if [ "$TOTAL_FILES" -eq 0 ]; then
    echo "⚠️  No .evtx/.evt files found under: \"$EVTX_DIR\""
    exit 1
fi
echo "📄 Found $TOTAL_FILES event log file(s) to scan."
echo ""

# Width for left padding x in (x/xx)
PAD=${#TOTAL_FILES}

# 🚀 Scan loop
with_hits=0
total_matches=0
idx=0

while IFS= read -r -d '' file; do
    idx=$((idx + 1))
    base="$(basename "$file")"
    name="${base%.*}"

    # Always print the scanning line
    printf "(%*d/%d) Scanning file - %s\n" "$PAD" "$idx" "$TOTAL_FILES" "$base"

    # Unreadable file -> extra error line
    if [ ! -r "$file" ]; then
        echo "  → ERROR: unreadable file"
        echo "UNREADABLE: $file" >> "$FAILED_LOG"
        continue
    fi

    # Temp output dir (hidden)
    tmpdir="$(mktemp -d "$OUTPUT_DIR/.tmp.${name}.XXXXXXXX" 2>/dev/null || mktemp -d)"
    if [ ! -d "$tmpdir" ]; then
        echo "  → ERROR: could not create temporary directory"
        echo "FAILED TMPDIR: $file" >> "$FAILED_LOG"
        continue
    fi

    # Run chainsaw against merged rules cache
    if ! chainsaw hunt \
         --sigma "$RULES_CACHE" \
         --mapping "$MAPPING_FILE" \
         --output "$tmpdir" \
         --csv \
         "$file" 1>/dev/null 2>>"$ERROR_LOG"; then
        rc=$?
        echo "  → ERROR: chainsaw exit $rc"
        echo "FAILED: $file (exit $rc)" >> "$FAILED_LOG"
        rm -rf "$tmpdir"
        continue
    fi

    # Count matches across CSVs
    matches=0
    if find "$tmpdir" -type f -name "*.csv" -print0 | grep -q .; then
        while IFS= read -r -d '' csv; do
            rows=$(wc -l < "$csv" | tr -d ' ')
            [ "$rows" -gt 1 ] && matches=$((matches + rows - 1))
        done < <(find "$tmpdir" -type f -name "*.csv" -print0)
    fi

    if [ "$matches" -gt 0 ]; then
        # Promote to final output
        final="$OUTPUT_DIR/$name"
        rm -rf "$final"
        mv "$tmpdir" "$final"
        echo "  → MATCHES: $matches (saved to output/$name)"
        echo "$file,$matches" >> "$SUMMARY_LOG"
        with_hits=$((with_hits + 1))
        total_matches=$((total_matches + matches))
    else
        # No hits: remove temp dir silently (no extra line)
        rm -rf "$tmpdir"
    fi
done < <(find "$EVTX_DIR" -type f \( -iname "*.evtx" -o -iname "*.evt" \) -print0)

echo ""
echo "✅ Finished scan."
echo "   📦 Files scanned:       $TOTAL_FILES"
echo "   🎯 Files with matches:  $with_hits"
echo "   🔢 Total matches:       $total_matches"
echo "📁 Output directory: \"$OUTPUT_DIR\""
[ -s "$SUMMARY_LOG" ] && echo "🧾 Summary written to: $SUMMARY_LOG"
if [ -s "$FAILED_LOG" ]; then
    echo "❗ Some files failed or were unreadable. See:"
    echo "   - $FAILED_LOG"
    echo "   - $ERROR_LOG"
fi

# ------------------------------------------------------------------------------
# 🔤 Enrich CSVs (add EventName, LogonTypeName, Summary)
# ------------------------------------------------------------------------------
if [[ $ENRICH -eq 1 ]]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ℹ️  Skipping enrichment: python3 not found."
    exit 0
  fi

  # Are there any CSVs to enrich?
  if ! find "$OUTPUT_DIR" -type f -name "*.csv" ! -name "*_enriched.csv" -print -quit | grep -q .; then
    echo "ℹ️  No CSVs found to enrich."
    exit 0
  fi

  echo "🧪 Enriching CSVs with readable columns…"
  OUTPUT_DIR_ENV="$OUTPUT_DIR" python3 - <<'PY'
import csv, os, sys

root = os.environ.get("OUTPUT_DIR_ENV", ".")
all_out_path = os.path.join(root, "_all_enriched.csv")

EVENT_NAME = {
  4624:"Logon Success", 4625:"Logon Failure", 4634:"Logoff", 4648:"Logon Using Explicit Credentials",
  4672:"Admin Logon", 4688:"Process Created", 4697:"Service Installed", 4698:"Scheduled Task Created",
  4702:"Scheduled Task Updated", 4776:"DC Logon Attempt",
  1:"Sysmon Process Create", 3:"Sysmon Network Connect", 7:"Sysmon Image Load",
  11:"Sysmon File Create", 13:"Sysmon Registry", 22:"Sysmon DNS Query"
}
LOGON_TYPE = {
  "2":"Interactive","3":"Network","4":"Batch","5":"Service","7":"Unlock",
  "8":"NetworkCleartext","9":"NewCredentials","10":"RemoteInteractive (RDP/TS)","11":"CachedInteractive"
}

def pick(row, keys):
    for k in keys:
        if k in row and row[k]:
            return row[k]
    return ""

def int_or_none(v):
    try:
        return int(str(v).strip())
    except Exception:
        return None

# Prepare all-enriched writer
all_writer = None
all_fields = None
files_enriched = 0
rows_enriched = 0

for dirpath, dirnames, filenames in os.walk(root):
    # skip hidden temp dirs (start with .tmp.)
    dirnames[:] = [d for d in dirnames if not d.startswith(".tmp.")]
    for fn in filenames:
        if not fn.endswith(".csv") or fn.endswith("_enriched.csv"):
            continue
        in_path = os.path.join(dirpath, fn)
        out_path = in_path[:-4] + "_enriched.csv"

        with open(in_path, newline='', encoding='utf-8', errors='ignore') as f:
            r = csv.DictReader(f)
            if r.fieldnames is None:
                continue
            fields = list(r.fieldnames)
            for extra in ["EventName","LogonTypeName","Summary"]:
                if extra not in fields:
                    fields.append(extra)

            # open per-file enriched
            with open(out_path, "w", newline='', encoding='utf-8') as g:
                w = csv.DictWriter(g, fieldnames=fields)
                w.writeheader()

                # init all-enriched writer on first file with its fields
                if all_writer is None:
                    all_fields = fields
                    all_writer = csv.DictWriter(open(all_out_path, "w", newline='', encoding='utf-8'), fieldnames=all_fields)
                    all_writer.writeheader()

                for row in r:
                    eid = pick(row, ["Event ID","EventID","event_id","EventId"])
                    eid_int = int_or_none(eid)
                    row["EventName"] = EVENT_NAME.get(eid_int, "") if eid_int is not None else ""

                    lt = pick(row, ["LogonType","Logon Type","logon_type"])
                    row["LogonTypeName"] = LOGON_TYPE.get(str(lt), "")

                    ts   = pick(row, ["timestamp","Timestamp","@timestamp","TimeCreated"])
                    det  = pick(row, ["detections","Detections","rule","Rule"])
                    user = pick(row, ["TargetUserName","SubjectUserName","User","AccountName","user"])
                    ip   = pick(row, ["IpAddress","SourceIpAddress","Source IP","dst_ip","src_ip","ip"])
                    proc = pick(row, ["Image","ProcessName","NewProcessName","process","CommandLine","Process","cmd"])
                    row["Summary"] = f'{ts} {det} EID {eid} {row["EventName"]} user={user} ip={ip} proc={proc}'.strip()

                    w.writerow(row)
                    all_writer.writerow({k: row.get(k, "") for k in all_fields})
                    rows_enriched += 1

        files_enriched += 1

print(f"Enriched {files_enriched} file(s), {rows_enriched} row(s).")
PY

  echo "🧾 Enrichment complete:"
  echo "   - Per-file: *_enriched.csv alongside original CSVs"
  echo "   - Combined: $OUTPUT_DIR/_all_enriched.csv"
fi
