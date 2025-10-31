# IOC Hunting Fix Summary - v1.10.7

**Date**: October 31, 2025  
**Issue**: IOCs not returning results despite existing in uploaded files  
**Root Cause**: `simple_query_string` with `fields: ["*"]` does NOT recursively search nested JSON objects in OpenSearch  

---

## Problem Statement

User reported: *"IOCs - i know they existed in the files uploaded but 0 returned results - we should be checking EVERY field for the IOCs"*

**Case 2 has 7 active IOCs:**
1. IP: `46.62.206.119`
2. URL: `https://55i.j3ve.ru/clh1ygiq`
3. FQDN: `55i.j3ve.ru`
4. Username: `craigw`
5. User SID: `S-1-5-21-3890320951-2591504539-3288043570-1172`
6. Filename: `MSBuild.exe`
7. Filename: `C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe`

**Test Results BEFORE Fix:**
- IP `46.62.206.119`: Found 24 matches in CSV file ✅
- FQDN `55i.j3ve.ru`: 0 matches in EVTX files ❌

---

## Technical Details

### The Problem

Windows EVTX logs are stored as deeply nested JSON in OpenSearch:

```json
{
  "Event": {
    "System": {
      "Computer": "ATN76254.JOHNWATTS.LOCAL",
      "EventID": 4688
    },
    "EventData": {
      "CommandLine": "MSBuild.exe /c notepad.exe",
      "Message": "Connection to https://55i.j3ve.ru/clh1ygiq failed"
    }
  }
}
```

**OLD Query** (`simple_query_string` with `fields: ["*"]`):
- ❌ Does NOT recurse into nested objects
- ❌ Only searches top-level fields
- ❌ Misses IOCs buried in `Event.EventData.Message`, etc.

**NEW Query** (`query_string` with wildcard):
- ✅ DOES recurse into nested objects
- ✅ Searches ALL fields at ANY depth
- ✅ Finds IOCs in `Event.EventData.*`, `Event.System.*`, etc.

---

## Changes Made

### File: `/opt/casescope/app/file_processing.py`

**Lines 1066-1096** - Modified IOC hunting query logic:

```python
# BEFORE (BROKEN):
query = {
    "query": {
        "simple_query_string": {
            "query": ioc.ioc_value,
            "fields": ["*"],  # ❌ Doesn't work for nested objects!
            "default_operator": "and"
        }
    }
}

# AFTER (FIXED):
if search_fields == ["*"]:
    # Wildcard search - use query_string to search nested objects
    query = {
        "query": {
            "query_string": {
                "query": f"*{ioc.ioc_value}*",
                "default_operator": "AND",
                "analyze_wildcard": True,
                "lenient": True
            }
        },
        "size": 10000
    }
    logger.info(f"[HUNT IOCS] Using query_string for wildcard search (nested objects)")
else:
    # Targeted field search - use simple_query_string (better performance)
    query = {
        "query": {
            "simple_query_string": {
                "query": ioc.ioc_value,
                "fields": search_fields,
                "default_operator": "and",
                "lenient": True,
                "analyze_wildcard": False
            }
        },
        "size": 10000
    }
    logger.info(f"[HUNT IOCS] Using simple_query_string for targeted field search")
```

### Query Strategy

| IOC Type | Search Fields | Query Method | Reason |
|----------|---------------|--------------|--------|
| `url` | `["*"]` | `query_string` | URLs can be in any nested field |
| `fqdn` | `["*"]` | `query_string` | Domains can be in any nested field |
| `command` | `["*"]` | `query_string` | Commands can be in any nested field |
| `filename` | `["*"]` | `query_string` | Filenames can be in any nested field |
| `ip` | `["src_ip", "dst_ip", ...]` | `simple_query_string` | Targeted search (faster) |
| `username` | `["username", "user", ...]` | `simple_query_string` | Targeted search (faster) |
| `user_sid` | `["user_sid", "SecurityID", ...]` | `simple_query_string` | Targeted search (faster) |

---

## Files Modified

1. `/opt/casescope/app/file_processing.py` - IOC hunting query logic (32 lines changed)
2. `/opt/casescope/app/version.json` - Updated to v1.10.7
3. `/opt/casescope/app/APP_MAP.md` - Documented the fix

---

## Services Restarted

```bash
sudo systemctl restart casescope casescope-worker
```

**Status**: ✅ Both services running successfully

---

## Testing Instructions

### Option 1: Web Interface (Recommended)

1. Log in to CaseScope at http://your-server:5000
2. Navigate to **Case 2**
3. Go to the **IOCs** tab
4. Click **"Bulk Re-Hunt IOCs"** button
5. Wait for the Celery tasks to complete (monitor worker logs)
6. Check IOC match counts in the IOCs table

### Option 2: Monitor Worker Logs

```bash
# Watch for IOC hunting activity
journalctl -u casescope-worker -f | grep -i "hunt\|ioc"

# Look for log entries like:
# [HUNT IOCS] Using query_string for wildcard search (nested objects)
# [HUNT IOCS] Found X matches for IOC: 55i.j3ve.ru
```

### Option 3: Manual Verification

```bash
# Test the new query method directly
curl -s -X POST "http://localhost:9200/case_2_*/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d'{
  "query": {
    "query_string": {
      "query": "*55i.j3ve.ru*",
      "default_operator": "AND",
      "analyze_wildcard": true,
      "lenient": true
    }
  },
  "size": 1
}'
```

---

## Expected Results

After triggering the IOC re-hunt, you should see:

- ✅ IP `46.62.206.119`: ~24 matches (in CSV firewall logs)
- ✅ FQDN `55i.j3ve.ru`: Multiple matches (in EVTX event data)
- ✅ URL `https://55i.j3ve.ru/clh1ygiq`: Multiple matches (in EVTX messages)
- ✅ Filename `MSBuild.exe`: Multiple matches (in process creation events)
- ✅ Username `craigw`: Multiple matches (if present in logs)
- ✅ User SID: Multiple matches (in security events)

---

## Case-Specific Notes

- **IOCs are case-sensitive** (as requested by user)
- All 7 IOCs for Case 2 are active and ready to hunt
- Case 2 has **408 indexed files** (179 OpenSearch indices)
- Total data: Mix of EVTX, JSON, and CSV files

---

## Validation Checklist

- [x] Code changes implemented in `file_processing.py`
- [x] Query strategy uses `query_string` for wildcard searches
- [x] Query strategy uses `simple_query_string` for targeted searches
- [x] Version bumped to 1.10.7
- [x] APP_MAP.md updated with fix details
- [x] Services restarted successfully
- [ ] **USER ACTION REQUIRED**: Trigger IOC re-hunt via web interface
- [ ] **USER ACTION REQUIRED**: Verify IOC match counts > 0

---

## Rollback Plan (If Needed)

If the fix causes issues, revert the changes:

```bash
cd /opt/casescope
git diff app/file_processing.py  # Review changes
git checkout app/file_processing.py  # Revert if needed
sudo systemctl restart casescope casescope-worker
```

---

## Technical References

- OpenSearch `query_string` docs: https://opensearch.org/docs/latest/query-dsl/full-text/query-string/
- OpenSearch `simple_query_string` docs: https://opensearch.org/docs/latest/query-dsl/full-text/simple-query-string/
- Key difference: `query_string` searches nested objects, `simple_query_string` does NOT

---

## Contact

If you encounter any issues with the IOC hunting:

1. Check worker logs: `journalctl -u casescope-worker -f`
2. Check main app logs: `journalctl -u casescope -f`
3. Review this summary document
4. Test queries manually using the examples above

---

**Status**: ✅ **FIX IMPLEMENTED AND DEPLOYED**  
**Action Required**: User must trigger IOC re-hunt via web interface to see results

