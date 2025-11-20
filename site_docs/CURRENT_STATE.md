# CaseScope 2026 - Current State & Features
**Version 1.16.24 - Active Features & Known Issues**

**Last Updated**: November 20, 2025  
**Purpose**: Current system state for AI code assistants

**Note**: Full version history archived in `version_ARCHIVE_20251120.json` and `APP_MAP_ARCHIVE_20251120.md`

---

## 📊 Current Version

**Version**: 1.16.24  
**Release Date**: November 18, 2025  
**Stability**: Production (with known issues below)  
**Build**: Stable

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

### **Latest Addition (v1.16.24)**
- ✅ **Search Blob Field** - Normalized search field for improved IOC matching
  - Solves multi-line text IOC matching issue
  - Flattens nested structures
  - Removes line breaks that broke phrase matching
  - Applied to all event types (EVTX, JSON, CSV, IIS)
  - Requires re-indexing for existing events

---

## 🐛 Known Issues (Critical First)

### **CRITICAL - Re-Index Broken** ⚠️

**Status**: Documented fix available  
**Severity**: HIGH  
**Impact**: All re-index operations fail to reprocess files  
**Affected**:
- Single file re-index
- Selected files re-index
- Bulk all files re-index

**Root Cause**:  
`operation='reindex'` documented in docstring but never implemented in `tasks.process_file()`.  
All re-index functions call `operation='full'` which has safety check that skips already-indexed files.

**Fix Location**: `Reindex_Bug_Analysis_and_Fix.md` (complete solution with code)

**Workaround**: None (manual database manipulation required)

**Fix Status**: Code ready, not yet deployed

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
