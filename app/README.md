# 🔍 CaseScope 2026 v1.0.0

**Digital Forensics & Incident Response Platform**  
**Built from scratch with clean, modular architecture**

---

## 🎯 What is CaseScope 2026?

CaseScope 2026 is a complete rewrite of CaseScope 7.x, designed from the ground up with:
- ✅ **Zero legacy code** - Clean slate, no technical debt
- ✅ **Modular architecture** - 4-step processing pipeline
- ✅ **Production-ready** - Robust error handling, controlled concurrency
- ✅ **Minimal codebase** - ~2,000 lines vs 20,000+ in v7.x

---

## 🚀 Features

### Core Capabilities
- **Case Management** - Create and manage investigation cases
- **File Upload** - HTTP upload + bulk folder upload with ZIP extraction
- **Automated Processing** - 4-step modular pipeline:
  1. Duplicate detection (hash + filename)
  2. EVTX indexing to OpenSearch
  3. SIGMA detection via Chainsaw
  4. IOC hunting
- **Real-time Progress** - Track processing status
- **Zero-event handling** - Automatically archive empty files

### Technical Stack
- **Backend**: Flask + SQLAlchemy + Celery
- **Search**: OpenSearch
- **Queue**: Redis
- **SIGMA Engine**: Chainsaw CLI
- **Format Support**: EVTX, JSON, NDJSON, ZIP

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
2. Click "+ Upload Files"
3. Select EVTX/JSON/ZIP files
4. Click "Upload"
5. Files process automatically through 4-step pipeline

### Bulk Upload (Server-side)
```bash
# Copy files to local upload folder
cp *.evtx /opt/casescope/local_uploads/

# Trigger bulk processing (TODO: Add admin route)
```

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
┌────────────────────────┐
│  Worker (2 concurrent) │
├────────────────────────┤
│ 1. duplicate_check()   │
│ 2. index_file()        │
│ 3. chainsaw_file()     │
│ 4. hunt_iocs()         │
└────────────────────────┘
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

## 🎯 Roadmap

- ✅ v1.0.0 - Core MVP (current)
- ⏳ v1.1.0 - Timeline view, advanced search
- ⏳ v1.2.0 - DFIR-IRIS integration
- ⏳ v1.3.0 - OpenCTI integration
- ⏳ v2.0.0 - Multi-tenant support

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

## 📞 Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Email**: support@casescope.local

---

**Built with ❤️ for the DFIR community**

