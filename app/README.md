# 🔍 CaseScope 2026 v1.12.21

**Digital Forensics & Incident Response Platform**  
**Built from scratch with clean, modular architecture**

**Current Version**: 1.12.21 (November 12, 2025)

---

## 🎯 What is CaseScope 2026?

CaseScope 2026 is a complete rewrite of CaseScope 7.x, designed from the ground up with:
- ✅ **Zero legacy code** - Clean slate, no technical debt
- ✅ **Modular architecture** - 5-step processing pipeline
- ✅ **Production-ready** - PostgreSQL 16 with connection pooling, robust error handling
- ✅ **Powerful IOC hunting** - Searches all fields with intelligent matching, bulk operations
- ✅ **SIGMA detection** - Automated threat hunting with 3,074+ active rules (SigmaHQ + LOLRMM) with rule name display
- ✅ **Advanced search** - Full-text search with filters, tagging, and timeline views
- ✅ **AI-Powered Analysis** - Ollama integration for automated case report generation
- ✅ **Systems Discovery** - Automatic system identification and categorization
- ✅ **OpenCTI Enrichment** - Threat intelligence integration for IOC context

---

## 🚀 Features

### Core Capabilities
- **Case Management** - Create and manage investigation cases with full metadata
- **File Upload** - HTTP upload + bulk folder upload with ZIP extraction and deduplication
- **Automated Processing** - 5-step modular pipeline:
  1. **Scan & Stage** - Deduplication (hash + filename)
  2. **Event Filtering** - Filter out empty/low-value events
  3. **Index** - Full-text indexing to OpenSearch with nested field support
  4. **SIGMA Detection** - 3,074 active detection rules (SigmaHQ + LOLRMM)
  5. **IOC Hunting** - Comprehensive IOC detection across all event fields
- **Real-time Progress** - Track processing status with detailed stats
- **Zero-event handling** - Automatically hide empty files
- **Hidden Files Management** - View, search, bulk unhide/delete 0-event files

### Search & Analysis
- **Advanced Event Search** - Full-text search with filters:
  - Filter by event type (EVTX, CSV, JSON, EDR)
  - Filter by date range (custom or relative to latest event)
  - Filter by IOC/SIGMA violations
  - Filter by IOC count (2+, 3+ events)
  - Tag events for timeline creation
- **IOC Management** - Add, edit, enable/disable IOCs with multiple types:
  - IP addresses, URLs, FQDNs
  - Filenames, file paths, MD5/SHA256 hashes
  - Usernames, user SIDs  
  - Commands (simple and complex/obfuscated)
  - OpenCTI enrichment with threat intelligence
  - Bulk operations (Enable/Disable/Delete/Enrich)
- **SIGMA Rule Management** - Browse, enable/disable detection rules, view violated rules in event details with purple highlighting
- **Systems Discovery** - Auto-discover and categorize systems (servers, workstations, firewalls)
- **Login Analysis** - 4 quick analysis buttons (Successful Logins, Failed Logins, RDP, Console) with LogonType classification
- **VPN Analysis** - VPN authentication tracking with NPS event support (4624/4625, 6272/6273)
- **EVTX Event Descriptions** - Human-readable descriptions for Windows events
- **AI Report Generation** - Ollama-powered analysis with live streaming, cancellation, multi-model support
- **Export** - Unlimited CSV export of search results via OpenSearch Scroll API

### Technical Stack
- **Backend**: Flask + SQLAlchemy + Celery
- **Database**: PostgreSQL 16.10 with connection pooling (10 base + 20 overflow connections)
- **Search Engine**: OpenSearch 2.11.0 (8GB heap)
- **Queue**: Redis 7.0.15
- **SIGMA Engine**: Chainsaw v2.13.1
- **AI Engine**: Ollama (phi3:mini default, supports all models)
- **Threat Intelligence**: OpenCTI integration
- **Format Support**: EVTX, CSV, JSON, NDJSON, EDR, ZIP
- **Detection Rules**: SigmaHQ + LOLRMM (3,074 active rules)

---

## 📦 Installation

**📘 For complete installation instructions, see [INSTALL.md](INSTALL.md)**

### Quick Start

```bash
# Download installation script
wget https://raw.githubusercontent.com/YOUR_REPO/caseScope_2026/main/fresh_install.sh

# Run automated installation (Ubuntu 24.04 LTS)
sudo bash fresh_install.sh
```

Installation takes ~15-20 minutes and includes:
- PostgreSQL 16 database
- OpenSearch 2.11.0 search engine  
- Redis message broker
- CaseScope application
- Forensic tools (evtx_dump, chainsaw)
- SIGMA detection rules
- System services

After installation:
```
http://YOUR_SERVER:5000
Default login: admin / admin
```

⚠️ **Change the default password immediately!**

For manual installation or troubleshooting, see the complete [Installation Guide](INSTALL.md).

---

## 🔧 Usage

### Access the Application
```
http://your-server:5000
Default credentials: admin / admin
```

**⚠️ IMPORTANT**: Change the default password immediately after first login!

### Create a Case
1. Login
2. Click "+ New Case"
3. Enter case details
4. Click "Create Case"

### Upload Files
1. Open case
2. Click "+ Upload Files" or "+ Bulk Upload"
3. Select EVTX/CSV/JSON/ZIP files (or select folder for bulk)
4. Click "Upload"
5. Files process automatically through 5-step pipeline

**Supported Formats**:
- **EVTX** - Windows Event Logs
- **JSON** - JSON event logs
- **NDJSON** - Newline-delimited JSON
- **CSV** - CSV event logs
- **ZIP** - Automatically extracts EVTX and NDJSON files

### Add IOCs
1. Navigate to "IOC Management" in case menu
2. Click "+ Add IOC"
3. Enter IOC details (type, value, description, tags)
4. Enable OpenCTI enrichment for threat intelligence context
5. Save and trigger IOC hunt

### Systems Management
1. Navigate to "Systems" in case menu
2. Click "Find Systems" for auto-discovery
3. View categorized systems (servers, workstations, firewalls, etc.)
4. Manually add/edit systems as needed
5. Systems provide context for AI report generation

### Search Events
1. Navigate to "Search Events" in case menu
2. Use search bar for full-text search
3. Apply filters (event type, date range, IOC/SIGMA)
4. Tag events for timeline creation
5. Export results to CSV

### Generate AI Reports
1. Navigate to "AI Reports" in case menu
2. Click "+ Generate Report"
3. Select model (phi3:mini default, or any Ollama model)
4. Choose hardware mode (CPU/GPU)
5. Watch live generation with streaming preview
6. Cancel anytime if needed
7. Export completed reports as PDF/Markdown

### Monitor Processing
```bash
# Watch worker logs
sudo journalctl -u casescope-worker -f

# Check queue
redis-cli LLEN celery

# Check OpenSearch indices
curl -X GET "localhost:9200/_cat/indices?v"

# Check PostgreSQL connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='casescope';"
```

---

## 🏗️ Architecture

### Processing Pipeline
```
HTTP Upload / Bulk Upload
         ↓
    Staging Area
         ↓
   ZIP Extraction (if applicable)
         ↓
  Duplicate Detection (SHA256 + filename)
         ↓
    Queue for Processing (Celery)
         ↓
┌──────────────────────────────────┐
│  Worker (4 concurrent processes)  │
├──────────────────────────────────┤
│ 1. duplicate_check()            │
│ 2. event_filter() (skip empty)  │
│ 3. index_file() (OpenSearch)    │
│ 4. chainsaw_file() (SIGMA)      │
│ 5. hunt_iocs() (all fields)     │
└──────────────────────────────────┘
         ↓
   Mark Completed / Auto-hide if 0 events
```

### Directory Structure
```
/opt/casescope/
├── app/                    # Application code
│   ├── main.py             # Flask application
│   ├── models.py           # SQLAlchemy models
│   ├── tasks.py            # Celery tasks
│   ├── celery_app.py       # Celery configuration
│   ├── config.py           # Application configuration
│   ├── file_processing.py  # File processing pipeline
│   ├── ai_report.py        # AI report generation
│   ├── ai_training.py      # AI LoRA training
│   ├── ai_resource_lock.py # AI resource locking
│   ├── routes/             # Route blueprints
│   │   ├── cases.py        # Case management routes
│   │   ├── files.py        # File management routes
│   │   ├── api.py          # API routes
│   │   ├── ioc.py          # IOC management routes
│   │   ├── systems.py      # Systems management routes
│   │   ├── known_users.py  # Known users routes
│   │   └── ...             # Additional route blueprints
│   ├── templates/          # Jinja2 templates
│   │   ├── base.html       # Base template with navigation
│   │   ├── case_files.html # Case files page
│   │   ├── search_events.html # Event search page
│   │   └── ...             # Additional templates
│   ├── static/             # CSS, JS, images
│   │   ├── css/theme.css   # Centralized theme
│   │   ├── js/app.js       # JavaScript functionality
│   │   └── favicon.svg     # Custom favicon
│   ├── migrations/         # Database migrations
│   └── version.json        # Version and changelog
├── data/                   # Application data
├── uploads/                # Final uploaded files (organized by case_id)
│   ├── 1/                  # Case 1 files
│   ├── 2/                  # Case 2 files
│   └── ...
├── staging/                # Temporary staging area for processing
│   └── .rules-merged/      # Merged SIGMA rules cache
├── archive/                # 0-event files (hidden files)
│   ├── 1/                  # Case 1 hidden files
│   ├── 2/                  # Case 2 hidden files
│   └── ...
├── local_uploads/          # Bulk upload folder (monitored directory)
├── bulk_import/            # Bulk import staging area
├── logs/                   # Application logs (rotating)
│   ├── app.log             # Main application logs
│   ├── workers.log         # Celery worker logs
│   ├── api.log             # API request logs
│   ├── files.log           # File processing logs
│   ├── cases.log           # Case management logs
│   ├── celery.log          # Celery task logs
│   ├── dfir_iris.log       # DFIR-IRIS integration logs
│   └── opencti.log         # OpenCTI integration logs
├── bin/                    # Binaries and tools
│   ├── chainsaw            # SIGMA detection engine (v2.13.1)
│   └── evtx_dump           # EVTX parsing utility
├── chainsaw/               # Chainsaw configuration
│   └── mappings/           # Event log mappings
│       └── sigma-event-logs-all.yml
├── sigma_rules_repo/       # SigmaHQ rules repository (git clone)
│   ├── rules/              # Core SIGMA rules
│   ├── rules-dfir/         # DFIR-specific rules
│   ├── rules-emerging-threats/ # Emerging threat rules
│   ├── rules-threat-hunting/   # Threat hunting rules
│   └── ...
├── lolrmm/                 # Living Off The Land RMM detection
│   ├── yaml/               # LOLRMM SIGMA rules
│   ├── detections/         # Detection definitions
│   └── bin/                # LOLRMM tools
├── ollama_profiles/        # Ollama model configurations
│   ├── dfir-qwen.Modelfile # DFIR-tuned Qwen model
│   ├── dfir-llama.Modelfile # DFIR-tuned Llama model
│   └── ...
├── lora_training/          # AI LoRA training system
│   ├── scripts/            # Training scripts
│   ├── models/             # Trained model checkpoints
│   ├── training_data/      # Training datasets
│   ├── logs/               # Training logs
│   └── venv/               # Separate Python environment
└── venv/                   # Python virtual environment (main app)
```

### Database Schema
- **PostgreSQL 16** with connection pooling
- **10 persistent connections** + 20 overflow
- **Pool pre-ping** for connection health checks
- **Auto-recycle** connections every hour
- **Zero locking** (unlike SQLite)
- **3-4x faster** bulk operations

---

## 🔒 Security Notes

- **Default password**: Change the default admin password immediately!
- **PostgreSQL**: Use strong password in production, restrict network access
- **OpenSearch**: Currently runs without SSL (single-node dev mode)
- **Production**: Add reverse proxy (nginx) with SSL/TLS
- **Firewall**: Restrict ports 5000, 9200, 6379, 5432 to localhost
- **File uploads**: Validate and scan all uploaded files
- **User management**: Create read-only users for analysts

---

## 🐛 Troubleshooting

### Service not starting
```bash
# Check service status
sudo systemctl status casescope
sudo systemctl status casescope-worker
sudo systemctl status opensearch
sudo systemctl status redis
sudo systemctl status postgresql

# View logs
sudo journalctl -u casescope -n 100
sudo journalctl -u casescope-worker -n 100

# Check permissions
ls -la /opt/casescope
# All files should be owned by casescope:casescope
```

### Worker stuck or not processing
```bash
# Check worker status
sudo systemctl status casescope-worker

# Check if workers are consuming tasks
ps aux | grep celery

# Restart worker
sudo systemctl restart casescope-worker

# Check queue length
redis-cli LLEN celery
```

### PostgreSQL connection issues
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='casescope';"

# Check connection pool settings in config.py
# Default: 10 base + 20 overflow = 30 max connections

# Restart application if needed
sudo systemctl restart casescope casescope-worker
```

### OpenSearch issues
```bash
# Check heap usage
curl -s http://localhost:9200/_nodes/stats/jvm | grep heap_used_percent

# If heap consistently > 90%, increase heap size:
sudo nano /opt/opensearch/config/jvm.options
# Change -Xms8g and -Xmx8g to higher values

# Clear caches if needed
curl -X POST "localhost:9200/_cache/clear"

# Restart OpenSearch
sudo systemctl restart opensearch
```

### Files stuck in "Queued" status
```bash
# Check if Celery workers are running
sudo systemctl status casescope-worker

# Check Redis queue
redis-cli LLEN celery

# Requeue stuck files via UI
# Go to Case → Files → "Requeue Failed" button

# Or manually via database
sudo -u casescope psql -d casescope -c "
UPDATE case_file 
SET indexing_status = 'Queued', celery_task_id = NULL 
WHERE indexing_status = 'Failed' OR indexing_status LIKE 'Failed:%';
"
```

---

## 📝 Development

### Run locally (development mode)
```bash
cd /opt/casescope/app
source /opt/casescope/venv/bin/activate

# Terminal 1: Flask app (development server)
python main.py

# Terminal 2: Celery worker (with hot reload)
watchmedo auto-restart --directory=./ --pattern=*.py --recursive -- \
  celery -A celery_app worker --loglevel=debug --concurrency=2

# Terminal 3: Monitor queue
watch -n 1 'redis-cli LLEN celery'
```

### Database migrations
```bash
# After model changes, recreate tables
cd /opt/casescope/app
source /opt/casescope/venv/bin/activate

python << 'EOF'
from main import app, db
with app.app_context():
    db.create_all()
    print("Database updated")
EOF
```

---

## 🎯 Version History

### v1.12.x - SIGMA Enhancements & Bulk Operations
- ✅ v1.12.21 - SIGMA Rule Title Extraction Fix (Chainsaw CSV 'detections' column)
- ✅ v1.12.20 - SIGMA Rule Display in Event Details (purple highlighting)
- ✅ v1.12.16 - SIGMA Event Flagging Safe JSON Parsing (removed eval())
- ✅ v1.12.15 - SIGMA Re-run Field Name Error Fix
- ✅ v1.12.14 - SIGMA Violations Filter & SIGMA+IOC AND Logic
- ✅ v1.12.13 - SIGMA Rules Update git Command Fix
- ✅ v1.12.10 - Bulk IOC Operations Missing Import Fix
- ✅ v1.12.9 - Bulk Operations for IOC Management (Enable/Disable/Delete/Enrich)
- ✅ v1.12.8 - CSV Export Full Event Payload
- ✅ v1.12.7 - Unlimited CSV Export via OpenSearch Scroll API
- ✅ v1.12.6 - NPS Event Field Mapping for VPN Analysis
- ✅ v1.12.5 - ClientIPAddress Field for NPS VPN Events
- ✅ v1.12.4 - NPS Event IDs for VPN Analysis (6272/6273)
- ✅ v1.12.3 - Custom Columns in Search Events Display Fix
- ✅ v1.12.2 - Bulk Operations for Login Analysis
- ✅ v1.12.1 - VPN Authentication Analysis
- ✅ v1.12.0 - Login Analysis Suite (4 quick analysis buttons)

### v1.11.x - PostgreSQL Migration & Dashboard Fixes  
- ✅ v1.11.20 - AI LoRA Training Auto-Deployment
- ✅ v1.11.19 - AI Resource Locking System
- ✅ v1.11.6 - Asynchronous Case Deletion with Progress Tracking
- ✅ v1.11.5 - OpenSearch Shard Limit Crisis Prevention (10K → 50K)
- ✅ v1.11.5 - Windows Logon Analysis Suite
- ✅ v1.11.2 - System Dashboard PostgreSQL Migration Issues
- ✅ v1.11.1 - PostgreSQL Decimal Formatting in JSON APIs
- ✅ v1.11.0 - **MAJOR**: SQLite → PostgreSQL 16 Migration (430,523 rows, zero data loss)

### v1.10.7x - Performance & Stability
- ✅ v1.10.79 - OpenSearch Heap Increased to 8GB
- ✅ v1.10.78 - OpenSearch Client Timeout (10s → 60s)
- ✅ v1.10.77 - OpenSearch Circuit Breaker (85% → 95%)
- ✅ v1.10.76 - IOC Hunting Crash During File Upload Fix
- ✅ v1.10.75 - OpenCTI Background Enrichment + Table Alignment
- ✅ v1.10.74 - Bulk Actions for Hidden Files
- ✅ v1.10.73 - Search Hidden Files
- ✅ v1.10.72 - File Upload Clarification (all formats, extract EVTX/NDJSON only)
- ✅ v1.10.71 - Quick Add System + Systems Management Standalone Page
- ✅ v1.10.70 - Systems Discovery & Management

### v1.10.5x-6x - AI Reports
- ✅ v1.10.59 - AI Report Generation ImportError Fix
- ✅ v1.10.58 - Real-Time Cancellation During AI Streaming
- ✅ v1.10.57 - Delete Button for Failed & Cancelled Reports
- ✅ v1.10.56 - Hardware Mode Setting (CPU vs GPU)
- ✅ v1.10.55 - Hardware Mode Configuration for Ollama
- ✅ v1.10.52 - Model Upgrade (phi3:mini) + Remove Data Truncation
- ✅ v1.10.51 - Live Preview Streaming Bug Fix
- ✅ v1.10.50 - Live Preview Feature
- ✅ v1.10.49 - Report Validation Engine
- ✅ v1.10.48 - Cancel Button + Stage Tracking
- ✅ v1.10.47 - AI Report Generation with Ollama Integration

### v1.10.0x-2x - Core Features
- ✅ v1.10.22 - Fixed date range filters (custom & relative)
- ✅ v1.10.20 - Added 2+ and 3+ IOC event filters
- ✅ v1.10.19 - Phrase matching for simple command IOCs
- ✅ v1.10.18 - Added command_complex IOC type
- ✅ v1.10.17 - Distinctive terms strategy for complex IOCs
- ✅ v1.10.14 - IOC edit functionality
- ✅ v1.10.11 - Fixed IOC re-hunt (clear OpenSearch flags)
- ✅ v1.10.10 - Fixed bulk import processing
- ✅ v1.10.9 - Added LOLRMM SIGMA rules
- ✅ v1.10.8 - IOC hunting searches all fields by default
- ✅ v1.10.7 - Fixed IOC hunting (nested fields, special chars, scroll API)
- ✅ v1.0.0 - Core MVP

See `APP_MAP.md` for detailed changelog and technical documentation (12,000+ lines).
See `version.json` for complete feature list with all bug fixes and enhancements.

---

## 📄 License

MIT License - See LICENSE file

---

## 🤝 Contributing

This is a complete rewrite. Contributions welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly (run full pipeline with test data)
5. Update APP_MAP.md with changes
6. Submit a pull request

### Code Standards
- Follow PEP 8 for Python code
- Use descriptive variable names
- Add comments for complex logic
- Update documentation
- Test with PostgreSQL (not SQLite)

---

## 📚 Additional Documentation

- **[INSTALL.md](INSTALL.md)** - Complete installation guide (automated & manual)
- **[APP_MAP.md](APP_MAP.md)** - Comprehensive changelog, bug fixes, and technical details (12,000+ lines)
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command reference and troubleshooting  
- **[UI_SYSTEM.md](UI_SYSTEM.md)** - UI/UX documentation
- **[EVTX_DESCRIPTIONS_README.md](EVTX_DESCRIPTIONS_README.md)** - EVTX event descriptions system
- **[AI_RESOURCE_LOCKING_SUMMARY.md](AI_RESOURCE_LOCKING_SUMMARY.md)** - AI training auto-deployment system

---

## 📊 Performance Notes

### Benchmarks
- **Database**: PostgreSQL 16 (3-4x faster than SQLite for bulk operations)
- **Search**: OpenSearch 2.11.0 with 8GB heap
- **Concurrency**: 4 Gunicorn workers + 4 Celery workers
- **Connection Pool**: 30 max PostgreSQL connections (10 base + 20 overflow)
- **No Database Locking**: Unlike SQLite, PostgreSQL handles 8 concurrent workers without locking

### Tested Scale
- **40+ million events** indexed and searchable
- **9,400+ files** processed
- **331,000+ SIGMA violations** detected
- **41,000+ IOC events** flagged
- **3,074 active SIGMA rules**
- **53 tracked IOCs**
- **5 active cases**

### Hardware Recommendations
- **Minimum**: 4 CPU cores, 16GB RAM, 100GB SSD
- **Recommended**: 8+ CPU cores, 32GB RAM, 500GB NVMe SSD
- **Large Datasets**: 16+ CPU cores, 64GB RAM, 1TB+ NVMe SSD

---

## 📞 Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: See docs above
- **Community**: DFIR Discord/Slack channels

---

## 🙏 Acknowledgments

- **SigmaHQ** - Detection rules
- **LOLRMM** - Remote management tool detection
- **OpenSearch Project** - Search engine
- **Chainsaw** - SIGMA detection engine
- **Ollama** - Local AI inference
- **Flask & SQLAlchemy** - Web framework
- **PostgreSQL** - Production database

---

**Built with ❤️ for the DFIR community**

**🔥 Powered by PostgreSQL 16, OpenSearch 2.11, and Ollama AI** 🔥
