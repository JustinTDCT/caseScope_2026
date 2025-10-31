# CaseScope 2026 - Bulk Upload Fixes TODO

**Created**: 2025-10-29 03:11 UTC  
**Context**: Processing 11,590 EVTX files via bulk import revealed critical issues  
**Status**: Processing resumed with reduced workers, fixes needed for future

---

## Current Processing Status

```
Total files:    11,590
Completed:      ~91+
Processing:     7 (active)
Queued:         11,477
Failed:         4 (0.03%)
Queue size:     11,321 tasks

Workers:        2 concurrent (reduced from 8)
Memory:         Stable (~122MB)
```

---

## CRITICAL ISSUES FOUND

### Issue 1: Out of Memory (OOM) Kill - Workers Crashed

**Priority**: CRITICAL  
**Date**: 2025-10-29 02:59:18 UTC

**Problem**:
- Linux OOM killer terminated Celery workers during high-load processing
- 8 concurrent workers exceeded available system memory  
- Workers killed with SIGKILL/SIGTERM signals
- Processing interrupted, files left in inconsistent states

**Root Cause**:
- Each worker loads entire file + parses events + holds OpenSearch bulk data in memory
- 8 workers × ~100-500MB per worker = 800MB-4GB peak usage
- System has limited RAM, no swap configured

**Solution Implemented**:
✅ Reduced workers from 8 to 2 concurrent
✅ Processing resumed successfully

**Long-Term Fixes Needed**:

1. Add System Swap (Prevents OOM kills)
   - Priority: HIGH
   - File: /etc/fstab
   - Commands:
     sudo fallocate -l 8G /swapfile
     sudo chmod 600 /swapfile
     sudo mkswap /swapfile
     sudo swapon /swapfile
     echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

2. Implement Celery Memory Limits (Auto-restart workers)
   - Priority: HIGH
   - File: /opt/casescope/app/celery_app.py
   - Add: worker_max_memory_per_child = 512000  # KB (500MB limit)
   - Add: worker_max_tasks_per_child = 50  # Restart after 50 tasks
   
3. Optimize Memory Usage in Processing (Reduce footprint)
   - Priority: MEDIUM
   - File: /opt/casescope/app/file_processing.py
   - Stream large files instead of loading entirely
   - Process events in smaller batches (500 vs 5000)
   - Use OpenSearch bulk API more efficiently
   - Clear variables after processing sections

4. Add Memory Monitoring (Proactive alerting)
   - Priority: LOW
   - File: /opt/casescope/app/routes/dashboard.py
   - Add memory usage % to system dashboard
   - Alert when workers exceed 80% memory

---

### Issue 2: File Path Mismatch (Bulk Import)

**Priority**: HIGH  
**Date**: 2025-10-29 03:02:56+ UTC

**Problem**:
- Bulk import created database records with incorrect file paths
- Files were moved to archive/ (0-event files) but DB pointed to uploads/
- 168 files failed with "FileNotFoundError"

**Root Cause**:
- Bulk import workflow creates DB records with uploads/ path
- Filter step moves 0-event files to archive/
- Database path is not updated after move
- Workers try to process using stale path

**Solution Implemented**:
✅ Created script to find files in archive and update paths
✅ Fixed 164 of 168 failed files
✅ Files requeued for processing

**Long-Term Fixes Needed**:

1. Fix Bulk Import Path Handling (Prevent issue)
   - Priority: HIGH
   - Files: /opt/casescope/app/bulk_import.py
   - Files: /opt/casescope/app/upload_pipeline.py
   
   CURRENT BROKEN FLOW:
   1. Create DB record → file_path = /uploads/1/file.evtx
   2. Filter zero-event files → move to /archive/1/file.evtx
   3. Queue for processing → DB still points to /uploads/
   4. Worker tries to process → FileNotFoundError
   
   FIXED FLOW:
   1. Filter zero-event files FIRST
   2. For valid files:
      - Create DB record → file_path = /uploads/1/file.evtx
      - Queue for processing
   3. For 0-event files:
      - Create DB record → file_path = /archive/1/file.evtx
      - Set is_hidden = True, is_indexed = True
      - Don't queue for processing

2. Add File Existence Check in Worker (Defensive)
   - Priority: MEDIUM
   - File: /opt/casescope/app/tasks.py
   - Before processing, check if file exists
   - If not, check staging/archive directories
   - Update path or mark as failed with clear message

3. Create Automated Fix Script (Recovery tool)
   - Priority: LOW
   - File: /opt/casescope/app/scripts/fix_file_paths.py
   - Run periodically or on-demand to fix path mismatches

---

### Issue 3: Files Not Auto-Queued After Bulk Import

**Priority**: MEDIUM  
**Date**: 2025-10-29 03:02:56 UTC

**Problem**:
- Bulk import created 11,590 file records in database
- Files showed "Queued" status in UI
- BUT: No Celery tasks were queued
- Workers were idle, nothing in Redis queue

**Evidence**:
Database: 11,590 files with status "Queued"
Redis queue: 0 tasks
Workers: Idle

**Root Cause**:
- queue_file_processing() not called or failed silently
- Bulk import workflow created DB records but didn't trigger worker tasks

**Solution Implemented**:
✅ Manually called queue_file_processing() for all queued files
✅ Processing started immediately

**Long-Term Fixes Needed**:

1. Fix Bulk Import Queueing (Ensure tasks are queued)
   - Priority: HIGH
   - Files: /opt/casescope/app/bulk_import.py
   - Files: /opt/casescope/app/tasks.py
   - Ensure queue_file_processing() is called and verified

2. Add Queue Verification (Sanity check)
   - Priority: LOW
   - File: /opt/casescope/app/bulk_import.py
   - After queueing, verify tasks are in Redis
   - Log error if queue count doesn't match expected

---

## What We Fixed Today

1. ✅ Reduced Workers: 8 → 2 concurrent (prevents OOM)
2. ✅ Fixed File Paths: Updated 164 failed files to correct archive paths
3. ✅ Requeued Files: Manually queued 11,590 files for processing
4. ✅ Resumed Processing: System actively processing with stable memory

---

## Implementation Priority

### Phase 1: Critical (Do Before Next Bulk Upload)
1. Add system swap (8GB)
2. Implement Celery memory limits
3. Fix bulk import file path handling
4. Fix bulk import auto-queueing

### Phase 2: Important (Do Within 1 Week)
1. Add file existence check in worker
2. Optimize memory usage in file processing
3. Add memory monitoring to dashboard

### Phase 3: Nice to Have (Do When Convenient)
1. Create automated fix scripts
2. Implement task timeouts
3. Add queue verification logging
4. Create status recovery script

---

## Files to Modify

Priority HIGH:
- /opt/casescope/app/celery_app.py (Add memory limits)
- /opt/casescope/app/bulk_import.py (Fix path handling & queueing)
- /opt/casescope/app/upload_pipeline.py (Update filter logic)
- /etc/fstab (Configure swap)

Priority MEDIUM:
- /opt/casescope/app/tasks.py (Add file existence check)
- /opt/casescope/app/file_processing.py (Optimize memory usage)

Priority LOW:
- /opt/casescope/app/routes/dashboard.py (Add memory monitoring)

---

## Monitoring Commands

Watch Processing Progress:
watch -n 10 'redis-cli LLEN celery && echo "tasks in queue"'

Watch Memory Usage:
watch -n 5 'free -h'

Worker Status:
systemctl status casescope-worker

Check Failed Files:
cd /opt/casescope/app && python3 -c "from main import app, db; from models import CaseFile; app.app_context().push(); failed = CaseFile.query.filter(CaseFile.is_deleted == False, ~CaseFile.indexing_status.in_(['Completed', 'Queued', 'Indexing', 'SIGMA Testing', 'IOC Hunting'])).count(); print(f'Failed files: {failed}')"

---

**Status**: PROCESSING ACTIVE  
**Last Updated**: 2025-10-29 03:12 UTC  
**Estimated Completion**: 20-24 hours (at 2 workers)
**Current Progress**: ~0.8% complete (~91/11,590 files)

---

## Notes

- Processing currently running with 2 workers
- System stable, no memory issues
- 4 files remain failed (0.03% failure rate - acceptable)
- Monitor first 1,000 files for any new issues
- Consider increasing to 4 workers after adding swap
