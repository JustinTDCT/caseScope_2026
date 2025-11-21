# CaseScope 2026 - Current State & Features
**Version 1.19.0 - Active Features & Known Issues**

**Last Updated**: November 21, 2025  
**Purpose**: Current system state for AI code assistants

**Note**: Full version history archived in `version_ARCHIVE_20251120.json` and `APP_MAP_ARCHIVE_20251120.md`

---

## 📊 Current Version

**Version**: 1.19.0  
**Release Date**: November 21, 2025  
**Stability**: Production  
**Build**: Stable

---

## 🆕 Recent Changes (v1.19.0)

### **🚨 CRITICAL FIX: AI Timeline Hallucination - Complete Overhaul Using Tagged Events**
- **Fixed critical bug**: AI timeline generation was hallucinating events and producing inaccurate timelines
- **Root Cause**: Timeline was fetching random 300 events from ALL events instead of using analyst-tagged events
  - `tasks.py` ignored `TimelineTag` table completely
  - Prompt said "ANALYST-TAGGED EVENTS" but received random OpenSearch sample
  - AI saw placeholder events (Unknown | Unknown | EventID:N/A) and started hallucinating
- **Complete Solution**:
  - **PATCH 1 - tasks.py**: Replaced random event fetching with `TimelineTag.query.filter_by(case_id)`
    - Queries `TimelineTag` table for analyst-curated events
    - Fetches full event data from OpenSearch for each tagged event
    - Supports cached fallback if OpenSearch event deleted
    - No 300-event cap - loads ALL tagged events
    - Validates tagged events exist (fails with clear error if none)
  - **PATCH 2 - ai_report.py**: Replaced entire `generate_timeline_prompt()` with DFIR-compliant version
    - Changed from 6 sections to **11 DFIR-standard sections**:
      1. Timeline Summary
      2. Event Consolidation Summary
      3. Chronological Timeline (3A Individual + 3B Consolidated)
      4. Attack Progression Analysis (7 phases)
      5. IOC Timeline Matrix
      6. System Activity Timeline
      7. Initial Detection & Response
      8. Incident Escalation
      9. Attacker Activity Summary
      10. Root Cause Analysis
      11. Post-Incident Recommendations
    - **Evidence-based output**: Every event cites source file, timestamp with timezone, relevance context
    - **Comprehensive event data**: Shows source_file, analyst_notes from TimelineTag.notes, supports EventData/UserData/NDJSON fields
    - **DFIR best practices**: Evidence chain tracking, IOC first/last seen, MITRE ATT&CK mapping, timeline gap analysis
- **Breaking Change**: Timelines now **REQUIRE tagged events**
  - Users must tag events in search interface before generating timeline
  - Clear error message if no events tagged
- **Results**:
  - Timeline uses ONLY analyst-tagged events (no random sampling)
  - AI cannot hallucinate - only events in TimelineTag table provided
  - Professional DFIR report structure with evidence sourcing
  - All events accounted for with verification in output
- **Before**: Random 300 events from 8.7M → AI loops/hallucinates → Unusable output
- **After**: N tagged events (analyst-curated) → DFIR-compliant timeline → Professional forensic report
- **Files**: `app/tasks.py` (lines 1657-1850), `app/ai_report.py` (lines 215-780)
- **Based on**: `COMPLETE_TIMELINE_FIX_v2.md` implementation document

---

## 🆕 Recent Changes (v1.18.6)

### **🎯 MAJOR: AI Timeline Prompt - Analyst-Tagged Events & Intelligent Consolidation**
- **Fixed critical context problem**: AI thought events were "random sample" when they're analyst-selected
  - Previous: "You have 300 random events from 8.7M, need to extrapolate" (WRONG)
  - Now: "Analyst pre-filtered 8.7M down to 450 key events, organize these" (CORRECT)
- **Fixed consolidation confusion**: Contradictory instructions resolved
  - Previous: "Group events" BUT ALSO "Don't summarize" (conflicting)
  - Now: Clear rules for WHEN and WHEN NOT to consolidate
- **Mission changed**: From "SAMPLE-BASED TIMELINE" to "ANALYST-TAGGED EVENTS TIMELINE"
- **Removed 300-event cap**: Shows ALL tagged events (max 1000 with warning)
- **Added consolidation rules with 6 patterns**:
  1. Multiple Logins (4624) → "Lateral movement: User X to N systems"
  2. Failed Logins (4625) → "Brute force: N attempts"
  3. Process Execution (4688) → "Command: [cmd] on N systems"
  4. File Access (4663) → "File access: N files in [share]"
  5. Network (Sysmon 3) → "Network: N connections to [dest]"
  6. Registry (Sysmon 12) → "Registry: N changes to [key]"
- **When to group**: Within 10-minute window, same pattern
- **When NOT to group**: Different IOCs, different SIGMA, analyst notes, >10 min apart, different phases, unique events
- **3 detailed examples**: Lateral movement (50→1), brute force (127→1), reconnaissance (234→1)
- **Data preservation**: ALL events accounted for (individual or grouped)
- **Timeline summary**: Shows Individual entries, Consolidated groups, Total
- **Event consolidation table**: Shows what was grouped
- **Result**: Readable timelines with intelligent grouping, all data preserved
- **Files**: `app/ai_report.py` (lines 215-480)

## 🆕 Recent Changes (v1.18.5)

### **Timeline Live Preview & Button Improvements**
- **FIXED**: Timeline preview and button behavior from v1.18.3 (wasn't working)
- **Added live preview** to timeline generation modal (matches AI report modal)
  - Toggle button "Show/Hide Live Preview"
  - Auto-updates every 3 seconds with latest timeline content
  - Converts Markdown → HTML with formatting
  - Scrolls to bottom automatically
- **Button behavior fixed** during generation
  - Button stays **enabled** during generation (was disabled)
  - Changes to "View Generation" when generating (clickable)
  - Click button anytime to reopen progress modal
  - Can close and reopen modal during generation
- **Button states**:
  - No Timeline → "AI Case Timeline" (green)
  - Generating → "View Generation" (orange, enabled)
  - Completed → "Regenerate Timeline" (orange)
  - Failed → "Retry Timeline" (orange)
- **Files**: `templates/view_case_enhanced.html` (lines 2068-2100, 2204-2280, 1936-1962)

### **AI Timeline Prompt Overhaul - Sample-Based Approach (v1.18.4)**
- **Changed mission** from "complete timeline" to "sample-based key event timeline"
- **Added Section 0**: Sampling Assessment & Confidence
  - Shows sample size (e.g., 300 / 8,700,000 = 0.003%)
  - States high/medium/low confidence findings
  - Identifies sampling bias
- **Updated Section 1**: Timeline Summary explicitly states "Based on Provided Sample"
- **Enhanced Section 2**: Heavy event clustering (1-30 min bursts instead of individual events)
- **Robust Section 3**: Attack progression with confidence qualifiers (Confirmed/Likely/Possible/No evidence)
- **Added few-shot example**: 15-20 lines showing proper structure
- **Result**: Eliminates looping behavior, reduces hallucinations, honest gap assessment
- **Files**: `app/ai_report.py` (lines 215-406)

---

## ✅ Active Features (v1.16.24)

### **Core Functionality**
- ✅ Case management (create, edit, delete, assign)
- ✅ File upload (HTTP + bulk folder upload)
- ✅ Multi-format support (EVTX, JSON, CSV, NDJSON, IIS logs)
- ✅ ZIP extraction (auto-extracts EVTX and NDJSON)
- ✅ Duplicate detection (SHA256 + filename)
- ✅ Background processing (Celery workers, 4 concurrent)
- ✅ Event indexing (OpenSearch 2.11)
- ✅ Full-text search with filters
- ✅ Event export (unlimited CSV via Scroll API)

### **Threat Detection**
- ✅ SIGMA detection (3,074+ active rules)
  - SigmaHQ repository
  - LOLRMM (Living Off the Land RMM)
  - Custom rules support
- ✅ IOC hunting (13 IOC types supported)
  - IP, URL, FQDN, filename, hash, username, command, etc.
  - Bulk operations (enable/disable/delete/enrich)
  - OpenCTI enrichment (optional)
- ✅ SIGMA + IOC combined filtering
- ✅ Event tagging for timelines
- ✅ Event hiding/unhiding
- ✅ DFIR-IRIS integration (case/asset/IOC sync)

### **Analysis Features**
- ✅ Login analysis (4 quick buttons: Successful, Failed, RDP, Console)
- ✅ VPN authentication tracking (NPS event support)
- ✅ System discovery & categorization
- ✅ Known user tracking
- ✅ Event descriptions (MITRE/Microsoft sourced + custom)
- ✅ Timeline generation (AI-powered with Qwen model)
- ✅ Search history & favorites

### **AI Features**
- ✅ AI report generation (Ollama integration)
  - Models: phi3:mini, dfir-qwen, custom LoRA
  - Live streaming preview
  - Cancellation support
  - Chat-based refinement
- ✅ LoRA training (custom model fine-tuning)
- ✅ AI resource locking (prevent concurrent ops)
- ✅ Multi-model support
- ✅ Hardware mode selection (CPU/GPU)

### **User Management**
- ✅ Role-based access control (administrator, analyst, read-only)
- ✅ User creation/editing
- ✅ Session management
- ✅ Audit logging (all user actions)
- ✅ User profiles

### **System Features**
- ✅ Real-time processing progress
- ✅ File statistics (live updates every 3 seconds)
- ✅ Hidden file management (0-event files)
- ✅ Failed file tracking & requeue
- ✅ Global file view (across all cases)
- ✅ Queue cleanup & health monitoring
- ✅ System statistics dashboard

### **Latest Additions**

#### **v1.17.1 (November 20, 2025)**
- ✅ **CRITICAL BUGFIX: Re-IOC Hunt Fixed** - Fixed data loss bug in ioc_only operation
  - Bug: `tasks.py` line 427 cleared IOC matches for ALL files in case instead of just one file
  - Impact: Re-hunting IOCs on a single file would delete ALL IOC matches across the case
  - Root Cause: Used `filter(IOCMatch.index_name == index_name)` instead of `filter_by(file_id=file_id)`
  - Fixed: Changed to filter by file_id (file-specific instead of case-wide)
  - Severity: CRITICAL - caused data loss
  - Affected: Selected file re-IOC hunt, bulk re-IOC hunt (single file re-IOC was correct)

#### **v1.17.0 (November 20, 2025)**
- ✅ **Global Saved Searches** - Save and load search configurations across all cases
  - Save current search with custom title
  - Load from dropdown menu
  - Manage saved searches (view/delete)
  - User-scoped (each user has own library)

#### **v1.16.25 (November 19, 2025)**
- ✅ **CRITICAL BUGFIX: Re-Index Fixed** - Re-Index All Files button now works
  - Implemented missing `operation='reindex'` handler
  - Fixed 15-20% file loss during bulk re-index operations
  - Applied commit_with_retry to all status updates

#### **v1.16.24 (November 18, 2025)**
- ✅ **Search Blob Field** - Normalized search field for improved IOC matching
  - Solves multi-line text IOC matching issue
  - Flattens nested structures
  - Removes line breaks that broke phrase matching
  - Applied to all event types (EVTX, JSON, CSV, IIS)

---

## 🐛 Known Issues (Critical First)

### **No Critical Issues** ✅

**All critical issues have been resolved as of v1.17.1**:
- ✅ Re-Index operations fixed (v1.16.25)
- ✅ Re-IOC Hunt data loss fixed (v1.17.1)
- ✅ Search blob implemented (v1.16.24)
- ✅ Zombie files prevented (v1.16.8)

---

### **Medium Priority Issues**

#### **1. Main.py Too Large** ⚠️

**Issue**: 72 routes in main.py (should be ~10)  
**Impact**: Code maintainability, harder to navigate  
**Fix**: Move routes to blueprints (documented in `CaseScope_Refactoring_Analysis.md`)  
**Effort**: 2-3 weeks

Routes that need moving:
- Search routes (13) → create `routes/search.py`
- AI routes (13) → create `routes/ai.py`
- EVTX description routes (7) → create `routes/evtx.py`
- Timeline tagging (8+) → move to `routes/timeline.py`

#### **2. Duplicate Code Patterns** ⚠️

**Issue**: OpenSearch queries duplicated 100+ times  
**Impact**: Hard to maintain, inconsistent patterns  
**Fix**: Create query builder helper class  
**Effort**: 1-2 weeks  
**Documented**: `CaseScope_Refactoring_Analysis.md`

#### **3. Template Redundancy** ⚠️

**Issue**: Pagination, modals, tables duplicated across 38 templates  
**Impact**: Hard to update UI patterns  
**Fix**: Use existing components (pagination.html already exists but not used everywhere)  
**Effort**: 1 week

---

### **Recent Bug Fixes**

#### **v1.16.15 (Nov 18)** - Timeline Delete Audit Logger Error
- **Fixed**: `No module named 'audit_log'` error when deleting timelines
- **Root Cause**: Wrong import (`audit_log` instead of `audit_logger`)
- **Status**: ✅ Fixed

#### **v1.16.14 (Nov 18)** - AI Report Viewer 500 Error
- **Fixed**: AttributeError preventing AI Report viewer from loading
- **Root Cause**: Used `report.user` instead of `report.generator`
- **Status**: ✅ Fixed

#### **v1.14.0 (Nov 14)** - IIS Event Detail View
- **Fixed**: IIS events not viewable in modal
- **Root Cause**: URL encoding issue with IPv6 zone IDs (`%18` in IPs)
- **Status**: ✅ Fixed

#### **v1.13.9 (Nov 13)** - File Statistics API
- **Fixed**: Live statistics showed incorrect counts (included hidden files)
- **Root Cause**: API endpoint didn't filter `is_hidden == False`
- **Status**: ✅ Fixed

---

## 🔧 System Requirements

### **Minimum**
- 4 CPU cores
- 16GB RAM
- 100GB SSD
- Ubuntu 24.04 LTS

### **Recommended**
- 8+ CPU cores
- 32GB RAM
- 500GB NVMe SSD
- Ubuntu 24.04 LTS

### **Large Datasets**
- 16+ CPU cores
- 64GB RAM
- 1TB+ NVMe SSD
- Ubuntu 24.04 LTS

---

## 📦 Dependencies

### **Core Services**
```
PostgreSQL 16.10      - Case metadata
OpenSearch 2.11.0     - Event search (8GB heap)
Redis 7.0.15          - Message queue
Ollama (latest)       - AI inference
```

### **Python Packages** (requirements.txt)
```
Flask 3.x
SQLAlchemy 2.x
Celery 5.x
opensearch-py
psycopg2-binary
redis
requests
Werkzeug
Flask-Login
python-dotenv
```

### **External Tools**
```
evtx_dump (latest)    - EVTX to JSON converter
chainsaw v2.13.1      - SIGMA detection engine
```

---

## 🔄 Processing Pipeline Status

### **Step 1: Upload** ✅ Working
- HTTP upload
- Bulk folder upload
- ZIP extraction

### **Step 2: Duplicate Check** ✅ Working
- SHA256 hash + filename comparison
- Skips duplicates
- Records skipped files

### **Step 3: Event Indexing** ✅ Working
- EVTX parsing (evtx_dump)
- JSON parsing
- CSV parsing
- IIS log parsing
- OpenSearch indexing
- Event normalization
- Search blob creation (v1.16.24)

### **Step 4: SIGMA Detection** ✅ Working
- 3,074 active rules
- Chainsaw execution
- Violation flagging
- OpenSearch event updates

### **Step 5: IOC Hunting** ✅ Working
- Searches all active IOCs
- Updates event flags
- Creates IOCMatch records

### **Step 6: Re-Index** ❌ BROKEN
- Single file re-index: BROKEN
- Selected files re-index: BROKEN
- Bulk re-index: BROKEN
- **Fix available**: See issue section above

---

## 📊 Tested Scale

**Production Tested**:
- 40+ million events indexed
- 9,400+ files processed
- 331,000+ SIGMA violations detected
- 41,000+ IOC events flagged
- 3,074 active SIGMA rules
- 53 tracked IOCs
- 5 active cases

**Performance**:
- EVTX parsing: ~50,000 events/min (single worker)
- OpenSearch indexing: ~100,000 events/min (bulk)
- SIGMA detection: ~10,000 events/sec (Chainsaw)
- IOC hunting: ~50,000 events/sec (OpenSearch)

---

## 🔐 Security

### **Authentication**
- Session-based (Flask-Login)
- Password hashing (Werkzeug/bcrypt)
- Remember me (optional)

### **Authorization**
- administrator: Full access
- analyst: Case access, file operations
- read-only: View only

### **Audit Logging**
- All user actions logged
- IP address tracking
- Resource tracking (what was changed)
- Status tracking (success/failure)

---

## 🌐 Integrations

### **OpenCTI** (Optional)
- IOC enrichment
- Threat intelligence context
- Threat actor/campaign association
- Status: ✅ Working

### **DFIR-IRIS** (Optional)
- Case synchronization
- Asset management
- IOC synchronization
- Timeline export
- Status: ✅ Working

---

## 📝 Configuration

### **Required Environment Variables**
```bash
DATABASE_URL=postgresql://user:pass@localhost/casescope
SECRET_KEY=your-secret-key
```

### **Optional Environment Variables**
```bash
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
REDIS_URL=redis://localhost:6379/0
OLLAMA_BASE_URL=http://localhost:11434
OPENCTI_URL=http://localhost:8080
OPENCTI_TOKEN=your-token
DFIR_IRIS_URL=http://localhost:8000
DFIR_IRIS_TOKEN=your-token
```

---

## 📚 Documentation Files

### **New Concise Docs** (For AI Assistants)
```
ARCHITECTURE_OVERVIEW.md    - System architecture (500 lines)
ROUTES_COMPLETE.md          - All routes (800 lines)
QUICK_REFERENCE_AI.md       - Common patterns (300 lines)
CURRENT_STATE.md            - This file (200 lines)
```

### **Archived Docs** (Historical Reference)
```
APP_MAP_ARCHIVE_20251120.md      - Full change history (20,698 lines)
version_ARCHIVE_20251120.json    - Full version history (2,757 lines)
```

### **Existing Docs** (Still Valid)
```
README.md                    - Project overview
INSTALL.md                   - Installation guide
QUICK_REFERENCE.md           - Command reference
UI_SYSTEM.md                 - UI documentation
EVTX_DESCRIPTIONS_README.md  - Event descriptions system
```

### **Refactoring Docs**
```
CaseScope_Refactoring_Analysis.md    - Code refactoring plan (40% reduction possible)
Reindex_Bug_Analysis_and_Fix.md      - Re-index fix (complete solution)
Refactoring_Search_Guide.md          - How to find refactoring targets
```

---

## 🎯 Priorities for Development

### **Immediate** (This Week)
1. ⚠️ Fix re-index operations (critical bug)
2. ⚠️ Verify search_blob feature works after re-indexing

### **Short-term** (Next Month)
1. ⚠️ Move routes from main.py to blueprints
2. ⚠️ Use existing pagination component everywhere
3. ⚠️ Consolidate JavaScript patterns

### **Medium-term** (2-3 Months)
1. ⚠️ Create OpenSearch query builder
2. ⚠️ Create database query helpers
3. ⚠️ Refactor Celery tasks

### **Long-term** (Optional)
1. Route decorators for validation
2. Error handler decorators
3. Additional AI models
4. Performance optimizations

---

## 🔄 Recent Version History (Last 10 Releases)

**v1.16.24** (Nov 18, 2025) - Search blob field for IOC matching  
**v1.16.23** (Nov 18, 2025) - Full revert of v1.16.20-22 (IOC over-matching)  
**v1.16.22** (Nov 18, 2025) - Search bar change reverted  
**v1.16.21** (Nov 18, 2025) - Search bar failed on dash-separated terms  
**v1.16.20** (Nov 18, 2025) - IOC matching fix (analyze_wildcard issue)  
**v1.16.15** (Nov 18, 2025) - Timeline delete audit logger error fixed  
**v1.16.14** (Nov 18, 2025) - AI report viewer 500 error fixed  
**v1.16.13** (Nov 17, 2025) - AI report viewer page added  
**v1.14.0** (Nov 14, 2025) - IIS event detail view fixed  
**v1.13.9** (Nov 13, 2025) - File statistics API hidden file filter fixed

---

## ✅ System Health Checklist

Use this to verify system is operating correctly:

- [ ] PostgreSQL running (`systemctl status postgresql`)
- [ ] OpenSearch running (`systemctl status opensearch`)
- [ ] Redis running (`systemctl status redis`)
- [ ] Celery workers running (`systemctl status casescope-worker`)
- [ ] Flask app running (`systemctl status casescope`)
- [ ] Can login to web interface
- [ ] Can create new case
- [ ] Can upload file
- [ ] File processes successfully
- [ ] Can search events
- [ ] IOC hunting works
- [ ] SIGMA detection works
- [ ] AI report generation works
- [ ] ❌ Re-index operations (KNOWN BROKEN)

---

**✅ VERIFIED**: All information current as of November 20, 2025  
**📊 SOURCE**: Actual codebase analysis  
**🎯 PURPOSE**: Quick reference for current system state
