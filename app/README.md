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

### Prerequisites
```bash
# Ubuntu 24.04 LTS
sudo apt update
sudo apt install -y python3 python3-pip python3-venv redis-server postgresql postgresql-contrib
```

### Install PostgreSQL
```bash
# PostgreSQL should be installed from prerequisites
# Create database and user
sudo -u postgres psql << EOF
CREATE DATABASE casescope;
CREATE USER casescope WITH PASSWORD 'casescope_secure_2026';
GRANT ALL PRIVILEGES ON DATABASE casescope TO casescope;
\c casescope
GRANT ALL ON SCHEMA public TO casescope;
ALTER DATABASE casescope OWNER TO casescope;
EOF

# Verify connection
psql -U casescope -d casescope -c "SELECT version();"
```

### Install OpenSearch
```bash
# Download and install OpenSearch
wget https://artifacts.opensearch.org/releases/bundle/opensearch/2.11.0/opensearch-2.11.0-linux-x64.tar.gz
tar -xzf opensearch-2.11.0-linux-x64.tar.gz
sudo mv opensearch-2.11.0 /opt/opensearch

# Configure
echo "discovery.type: single-node" | sudo tee -a /opt/opensearch/config/opensearch.yml
echo "plugins.security.disabled: true" | sudo tee -a /opt/opensearch/config/opensearch.yml

# Set heap size to 8GB
sudo sed -i 's/-Xms[0-9]*[gGmM]/-Xms8g/' /opt/opensearch/config/jvm.options
sudo sed -i 's/-Xmx[0-9]*[gGmM]/-Xmx8g/' /opt/opensearch/config/jvm.options

# Increase circuit breaker limit
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "indices.breaker.total.limit": "95%"
  }
}'

# Create opensearch user and set permissions
sudo useradd -r -s /bin/bash opensearch
sudo chown -R opensearch:opensearch /opt/opensearch

# Create systemd service
sudo tee /etc/systemd/system/opensearch.service > /dev/null << 'EOF'
[Unit]
Description=OpenSearch
After=network.target

[Service]
Type=simple
User=opensearch
Group=opensearch
ExecStart=/opt/opensearch/bin/opensearch
Restart=on-failure
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable opensearch
sudo systemctl start opensearch
```

### Install CaseScope 2026
```bash
# Create casescope user and group
sudo useradd -r -s /bin/bash -m -d /home/casescope casescope

# Create directories
sudo mkdir -p /opt/casescope/{app,data,uploads,staging,archive,local_uploads,logs,bin,sigma_rules}
sudo chown -R casescope:casescope /opt/casescope

# Switch to casescope user
sudo -u casescope bash

# Clone repository
cd /opt/casescope/app
git clone https://github.com/YOUR_REPO/caseScope_2026.git .

# Create virtual environment
python3 -m venv /opt/casescope/venv
source /opt/casescope/venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure database connection
cat > /opt/casescope/app/config.py << 'CONFIGEOF'
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # PostgreSQL Configuration
    SQLALCHEMY_DATABASE_URI = 'postgresql://casescope:casescope_secure_2026@localhost/casescope'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,          # 10 persistent connections
        'max_overflow': 20,        # +20 on-demand connections
        'pool_pre_ping': True,     # Health check before use
        'pool_recycle': 3600       # Recycle after 1 hour
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Celery Configuration
    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
    
    # Upload Configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 * 1024  # 16GB max upload
    UPLOAD_FOLDER = '/opt/casescope/uploads'
CONFIGEOF

# Initialize database
python << 'PYEOF'
from main import app, db
with app.app_context():
    db.create_all()
    print("Database tables created successfully")
PYEOF

# Create admin user
python << 'PYEOF'
from main import app, db, User
import bcrypt

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        hashed = bcrypt.hashpw('admin'.encode('utf-8'), bcrypt.gensalt())
        admin = User(
            username='admin',
            password_hash=hashed.decode('utf-8'),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin user created: admin/admin")
    else:
        print("Admin user already exists")
PYEOF

# Download evtx_dump and chainsaw binaries
cd /opt/casescope/bin
wget https://github.com/omerbenamram/evtx/releases/download/v0.8.2/evtx_dump-v0.8.2-x86_64-unknown-linux-gnu
mv evtx_dump-v0.8.2-x86_64-unknown-linux-gnu evtx_dump
chmod +x evtx_dump

wget https://github.com/WithSecureLabs/chainsaw/releases/download/v2.13.1/chainsaw_x86_64-unknown-linux-gnu.tar.gz
tar -xzf chainsaw_x86_64-unknown-linux-gnu.tar.gz
mv chainsaw/chainsaw_x86_64-unknown-linux-gnu chainsaw
chmod +x chainsaw
rm -rf chainsaw_x86_64-unknown-linux-gnu.tar.gz chainsaw/

# Clone SIGMA rules
cd /opt/casescope
git clone https://github.com/SigmaHQ/sigma.git sigma_rules_repo

# Exit casescope user
exit
```

### Create Systemd Services

**CaseScope Web (casescope.service)**
```bash
sudo tee /etc/systemd/system/casescope.service > /dev/null << 'EOF'
[Unit]
Description=CaseScope 2026 Web Application
After=network.target opensearch.service redis.service postgresql.service

[Service]
Type=simple
User=casescope
Group=casescope
WorkingDirectory=/opt/casescope/app
Environment="PATH=/opt/casescope/venv/bin"
ExecStart=/opt/casescope/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 --timeout 300 wsgi:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

**CaseScope Worker (casescope-worker.service)**
```bash
sudo tee /etc/systemd/system/casescope-worker.service > /dev/null << 'EOF'
[Unit]
Description=CaseScope 2026 Celery Worker
After=network.target redis.service opensearch.service postgresql.service

[Service]
Type=simple
User=casescope
Group=casescope
WorkingDirectory=/opt/casescope/app
Environment="PATH=/opt/casescope/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/opt/casescope/app"
ExecStart=/opt/casescope/venv/bin/celery -A celery_app worker --loglevel=info --concurrency=4
Restart=always
RestartSec=10

# Memory Limits (adjust based on available RAM)
MemoryHigh=10G
MemoryMax=12G

[Install]
WantedBy=multi-user.target
EOF
```

**Enable and start services**
```bash
sudo systemctl daemon-reload
sudo systemctl enable casescope casescope-worker
sudo systemctl start casescope casescope-worker
```

### Create wsgi.py
```bash
sudo -u casescope tee /opt/casescope/app/wsgi.py > /dev/null << 'EOF'
from main import app

if __name__ == "__main__":
    app.run()
EOF
```

### Optional: Install Ollama for AI Reports
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull default model
ollama pull phi3:mini

# Create systemd service
sudo tee /etc/systemd/system/ollama.service > /dev/null << 'EOF'
[Unit]
Description=Ollama Service
After=network.target

[Service]
Type=simple
User=ollama
Group=ollama
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl start ollama
```

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
├── app/              # Application code
│   ├── main.py       # Flask application
│   ├── models.py     # SQLAlchemy models
│   ├── tasks.py      # Celery tasks
│   ├── config.py     # Configuration
│   ├── routes/       # Route blueprints
│   ├── templates/    # Jinja2 templates
│   └── static/       # CSS, JS, images
├── data/             # Application data
├── uploads/          # Final uploaded files (by case_id)
├── staging/          # Temporary staging area
├── archive/          # 0-event files (hidden)
├── local_uploads/    # Bulk upload folder
├── logs/             # Application logs
│   ├── app.log       # Main application logs
│   ├── workers.log   # Celery worker logs
│   ├── api.log       # API request logs
│   └── files.log     # File processing logs
├── bin/              # Binaries (evtx_dump, chainsaw)
├── sigma_rules_repo/ # SIGMA detection rules repository
└── venv/             # Python virtual environment
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

- **APP_MAP.md** - Comprehensive changelog, bug fixes, and technical details (12,000+ lines)
- **DEPLOYMENT_GUIDE.md** - Production deployment guide
- **QUICK_REFERENCE.md** - Command reference and troubleshooting  
- **UI_SYSTEM.md** - UI/UX documentation
- **EVTX_DESCRIPTIONS_README.md** - EVTX event descriptions system
- **FRESH_INSTALL_USAGE.md** - Fresh install / reset guide
- **AI_RESOURCE_LOCKING_SUMMARY.md** - AI training auto-deployment system

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
