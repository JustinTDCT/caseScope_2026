# 🔍 CaseScope 2026 v1.10.22

**Digital Forensics & Incident Response Platform**  
**Built from scratch with clean, modular architecture**

**Current Version**: 1.10.22 (November 2, 2025)

---

## 🎯 What is CaseScope 2026?

CaseScope 2026 is a complete rewrite of CaseScope 7.x, designed from the ground up with:
- ✅ **Zero legacy code** - Clean slate, no technical debt
- ✅ **Modular architecture** - 5-step processing pipeline
- ✅ **Production-ready** - Robust error handling, controlled concurrency
- ✅ **Powerful IOC hunting** - Searches all fields with intelligent matching
- ✅ **SIGMA detection** - Automated threat hunting with SigmaHQ + LOLRMM rules
- ✅ **Advanced search** - Full-text search with filters, tagging, and timeline views

---

## 🚀 Features

### Core Capabilities
- **Case Management** - Create and manage investigation cases with full metadata
- **File Upload** - HTTP upload + bulk folder upload with ZIP extraction and deduplication
- **Automated Processing** - 5-step modular pipeline:
  1. **Scan & Stage** - Deduplication (hash + filename)
  2. **Event Filtering** - Filter out empty/low-value events
  3. **Index** - Full-text indexing to OpenSearch with nested field support
  4. **SIGMA Detection** - 40,000+ detection rules (SigmaHQ + LOLRMM)
  5. **IOC Hunting** - Comprehensive IOC detection across all event fields
- **Real-time Progress** - Track processing status with detailed stats
- **Zero-event handling** - Automatically archive empty files

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
- **SIGMA Rule Management** - Browse, enable/disable detection rules
- **EVTX Event Descriptions** - Human-readable descriptions for Windows events
- **Export** - CSV export of search results

### Technical Stack
- **Backend**: Flask + SQLAlchemy + Celery
- **Search Engine**: OpenSearch 2.11.0
- **Queue**: Redis
- **SIGMA Engine**: Chainsaw v2.9.1
- **Format Support**: EVTX, CSV, JSON, NDJSON, EDR, ZIP
- **Detection Rules**: SigmaHQ + LOLRMM (40,000+ rules)

---

## 📦 Installation

### Prerequisites
```bash
# Ubuntu 24.04 LTS
sudo apt update
sudo apt install -y python3 python3-pip python3-venv redis-server
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

# Create systemd service
sudo nano /etc/systemd/system/opensearch.service
```

```ini
[Unit]
Description=OpenSearch
After=network.target

[Service]
Type=simple
User=root
ExecStart=/opt/opensearch/bin/opensearch
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable opensearch
sudo systemctl start opensearch
```

### Install CaseScope 2026
```bash
# Create directories
sudo mkdir -p /opt/casescope/{app,data,uploads,staging,archive,local_uploads,logs,bin,sigma_rules}
cd /opt/casescope/app

# Clone repository
git clone https://github.com/YOUR_REPO/caseScope_2026.git .

# Create virtual environment
python3 -m venv /opt/casescope/venv
source /opt/casescope/venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
flask init-db

# Download evtx_dump and chainsaw binaries
cd /opt/casescope/bin
wget https://github.com/omerbenamram/evtx/releases/download/v0.8.2/evtx_dump-v0.8.2-x86_64-unknown-linux-gnu
mv evtx_dump-v0.8.2-x86_64-unknown-linux-gnu evtx_dump
chmod +x evtx_dump

wget https://github.com/WithSecureLabs/chainsaw/releases/download/v2.9.1/chainsaw_x86_64-unknown-linux-gnu
mv chainsaw_x86_64-unknown-linux-gnu chainsaw
chmod +x chainsaw

# Clone SIGMA rules
cd /opt/casescope
git clone https://github.com/SigmaHQ/sigma.git sigma_rules_repo
ln -s /opt/casescope/sigma_rules_repo/rules /opt/casescope/sigma_rules
```

### Create Systemd Services

**CaseScope Web (main.service)**
```bash
sudo nano /etc/systemd/system/casescope.service
```

```ini
[Unit]
Description=CaseScope 2026 Web Application
After=network.target opensearch.service redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/casescope/app
Environment="PATH=/opt/casescope/venv/bin"
ExecStart=/opt/casescope/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```

**CaseScope Worker (casescope-worker.service)**
```bash
sudo nano /etc/systemd/system/casescope-worker.service
```

```ini
[Unit]
Description=CaseScope 2026 Celery Worker
After=network.target redis.service opensearch.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/casescope/app
Environment="PATH=/opt/casescope/venv/bin"
ExecStart=/opt/casescope/venv/bin/celery -A celery_app worker --loglevel=info --concurrency=2
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable and start services**
```bash
sudo systemctl daemon-reload
sudo systemctl enable casescope casescope-worker
sudo systemctl start casescope casescope-worker
```

### Create wsgi.py
```bash
cat > /opt/casescope/app/wsgi.py << 'EOF'
from main import app

if __name__ == "__main__":
    app.run()
EOF
```

---

## 🔧 Usage

### Access the Application
```
http://your-server:5000
Default credentials: admin / admin
```

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

### Add IOCs
1. Navigate to "IOC Management" in case menu
2. Click "+ Add IOC"
3. Enter IOC details (type, value, description, tags)
4. Save and trigger IOC hunt

### Search Events
1. Navigate to "Search Events" in case menu
2. Use search bar for full-text search
3. Apply filters (event type, date range, IOC/SIGMA)
4. Tag events for timeline creation
5. Export results to CSV

### Monitor Processing
```bash
# Watch worker logs
sudo journalctl -u casescope-worker -f

# Check queue
redis-cli LLEN celery

# Check OpenSearch indices
curl -X GET "localhost:9200/_cat/indices?v"
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
  Duplicate Detection
         ↓
    Queue for Processing
         ↓
┌──────────────────────────────────┐
│  Worker (configurable concurrency) │
├──────────────────────────────────┤
│ 1. duplicate_check()            │
│ 2. event_filter() (skip empty)  │
│ 3. index_file() (OpenSearch)    │
│ 4. chainsaw_file() (SIGMA)      │
│ 5. hunt_iocs() (all fields)     │
└──────────────────────────────────┘
         ↓
   Mark Completed
```

### Directory Structure
```
/opt/casescope/
├── app/              # Application code
├── data/             # SQLite database
├── uploads/          # Final uploaded files
├── staging/          # Temporary staging area
├── archive/          # 0-event files
├── local_uploads/    # Bulk upload folder
├── logs/             # Application logs
├── bin/              # Binaries (evtx_dump, chainsaw)
├── sigma_rules/      # SIGMA detection rules
└── venv/             # Python virtual environment
```

---

## 🔒 Security Notes

- **Default password**: Change the default admin password immediately
- **OpenSearch**: Currently runs without SSL (single-node dev mode)
- **Production**: Add reverse proxy (nginx) with SSL
- **Firewall**: Restrict ports 5000, 9200, 6379 to localhost

---

## 🐛 Troubleshooting

### Service not starting
```bash
# Check service status
sudo systemctl status casescope
sudo systemctl status casescope-worker
sudo systemctl status opensearch
sudo systemctl status redis

# View logs
sudo journalctl -u casescope -n 100
sudo journalctl -u casescope-worker -n 100
```

### Worker stuck
```bash
# Restart worker
sudo systemctl restart casescope-worker

# Clear queue
redis-cli FLUSHALL  # WARNING: Clears all Redis data
```

### Database locked errors
```bash
# Check if multiple workers are running
ps aux | grep celery

# Restart services
sudo systemctl restart casescope-worker
```

---

## 📝 Development

### Run locally (development mode)
```bash
cd /opt/casescope/app
source /opt/casescope/venv/bin/activate

# Terminal 1: Flask app
python main.py

# Terminal 2: Celery worker
celery -A celery_app worker --loglevel=debug

# Terminal 3: Monitor
watch -n 1 redis-cli LLEN celery
```

---

## 🎯 Version History

- ✅ v1.10.22 - Fixed date range filters (custom & relative)
- ✅ v1.10.21 - Hide ioc_count metadata field
- ✅ v1.10.20 - Added 2+ and 3+ IOC event filters
- ✅ v1.10.19 - Phrase matching for simple command IOCs
- ✅ v1.10.18 - Added command_complex IOC type
- ✅ v1.10.17 - Distinctive terms strategy for complex IOCs
- ✅ v1.10.15 - Multi-line truncation for IOC display
- ✅ v1.10.14 - IOC edit functionality
- ✅ v1.10.11 - Fixed IOC re-hunt (clear OpenSearch flags)
- ✅ v1.10.10 - Fixed bulk import processing
- ✅ v1.10.9 - Added LOLRMM SIGMA rules
- ✅ v1.10.8 - IOC hunting searches all fields by default
- ✅ v1.10.7 - Fixed IOC hunting (nested fields, special chars, scroll API)
- ✅ v1.0.0 - Core MVP

See `APP_MAP.md` for detailed changelog and fixes.

---

## 📄 License

MIT License - See LICENSE file

---

## 🤝 Contributing

This is a complete rewrite. Contributions welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

---

## 📚 Additional Documentation

- **APP_MAP.md** - Detailed changelog, bug fixes, and technical details
- **INSTALL.md** - Quick installation guide
- **DEPLOYMENT_GUIDE.md** - Production deployment guide
- **QUICK_REFERENCE.md** - Command reference and troubleshooting
- **UI_SYSTEM.md** - UI/UX documentation
- **EVTX_DESCRIPTIONS_README.md** - EVTX event descriptions system
- **FRESH_INSTALL_USAGE.md** - Fresh install / reset guide
- **REMOTE_ACCESS.md** - Remote development setup

## 📞 Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: See docs above

---

**Built with ❤️ for the DFIR community**

