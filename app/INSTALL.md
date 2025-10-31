# 🚀 CaseScope 2026 v1.0.0 - Quick Install

## Prerequisites
- Ubuntu 24.04 LTS server
- Root or sudo access
- Internet connection

## 1️⃣ Install Dependencies

```bash
# System packages
sudo apt update
sudo apt install -y python3 python3-pip python3-venv redis-server git

# Start Redis
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

## 2️⃣ Install OpenSearch

```bash
# Download OpenSearch 2.11.0
cd /tmp
wget https://artifacts.opensearch.org/releases/bundle/opensearch/2.11.0/opensearch-2.11.0-linux-x64.tar.gz
tar -xzf opensearch-2.11.0-linux-x64.tar.gz
sudo mv opensearch-2.11.0 /opt/opensearch

# Configure (single-node, no security)
echo "discovery.type: single-node" | sudo tee -a /opt/opensearch/config/opensearch.yml
echo "plugins.security.disabled: true" | sudo tee -a /opt/opensearch/config/opensearch.yml

# Create systemd service
sudo tee /etc/systemd/system/opensearch.service > /dev/null <<EOF
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
EOF

# Start OpenSearch
sudo systemctl daemon-reload
sudo systemctl enable opensearch
sudo systemctl start opensearch

# Wait for it to start (30 seconds)
sleep 30

# Verify
curl -X GET "localhost:9200/_cluster/health?pretty"
```

## 3️⃣ Clone CaseScope 2026

```bash
# Create directory structure
sudo mkdir -p /opt/casescope/{data,uploads,staging,archive,local_uploads,logs,bin}

# Clone from GitHub
cd /opt/casescope
sudo git clone https://github.com/YOUR_USERNAME/caseScope_2026.git app

cd /opt/casescope/app
```

## 4️⃣ Setup Python Environment

```bash
# Create virtual environment
cd /opt/casescope
sudo python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
cd /opt/casescope/app
pip install -r requirements.txt
```

## 5️⃣ Initialize Database

```bash
cd /opt/casescope/app
source /opt/casescope/venv/bin/activate
flask init-db
```

**Output:**
```
✓ Database initialized
✓ Default admin user created (username: admin, password: admin)
```

## 6️⃣ Download Forensic Tools

```bash
# evtx_dump (EVTX parser)
cd /opt/casescope/bin
sudo wget https://github.com/omerbenamram/evtx/releases/download/v0.8.2/evtx_dump-v0.8.2-x86_64-unknown-linux-gnu
sudo mv evtx_dump-v0.8.2-x86_64-unknown-linux-gnu evtx_dump
sudo chmod +x evtx_dump

# Chainsaw (SIGMA engine)
sudo wget https://github.com/WithSecureLabs/chainsaw/releases/download/v2.9.1/chainsaw_x86_64-unknown-linux-gnu
sudo mv chainsaw_x86_64-unknown-linux-gnu chainsaw
sudo chmod +x chainsaw

# Get Chainsaw mappings
cd /opt/casescope
sudo mkdir -p chainsaw/mappings
cd chainsaw/mappings
sudo wget https://raw.githubusercontent.com/WithSecureLabs/chainsaw/master/mappings/sigma-event-logs-all.yml

# Verify
/opt/casescope/bin/evtx_dump --version
/opt/casescope/bin/chainsaw --version
```

## 7️⃣ Setup SIGMA Rules

```bash
# Clone SIGMA rules repository
cd /opt/casescope
sudo git clone https://github.com/SigmaHQ/sigma.git sigma_rules_repo

# Create symlink
sudo ln -s /opt/casescope/sigma_rules_repo/rules /opt/casescope/sigma_rules

# Verify
ls -la /opt/casescope/sigma_rules | head -20
```

## 8️⃣ Create Systemd Services

### CaseScope Web Service

```bash
sudo tee /etc/systemd/system/casescope.service > /dev/null <<EOF
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
EOF
```

### CaseScope Worker Service

```bash
sudo tee /etc/systemd/system/casescope-worker.service > /dev/null <<EOF
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
EOF
```

## 9️⃣ Start CaseScope

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services (start on boot)
sudo systemctl enable casescope
sudo systemctl enable casescope-worker

# Start services
sudo systemctl start casescope
sudo systemctl start casescope-worker

# Check status
sudo systemctl status casescope
sudo systemctl status casescope-worker
```

## 🎉 Access CaseScope

**Open your browser:**
```
http://YOUR_SERVER_IP:5000
```

**Login:**
- Username: `admin`
- Password: `admin`

**⚠️ IMPORTANT: Change the default password immediately!**

---

## ✅ Verify Installation

```bash
# Check all services
sudo systemctl status opensearch --no-pager
sudo systemctl status redis --no-pager
sudo systemctl status casescope --no-pager
sudo systemctl status casescope-worker --no-pager

# Check logs
sudo journalctl -u casescope -n 50
sudo journalctl -u casescope-worker -n 50

# Check queue (should be 0 when idle)
redis-cli LLEN celery

# Check OpenSearch
curl -X GET "localhost:9200/_cat/indices?v"
```

---

## 🧪 Test Upload

1. Login to CaseScope
2. Click "+ New Case"
3. Enter case details, click "Create"
4. Click "+ Upload Files"
5. Select a small EVTX file
6. Watch it process: Queued → Indexing → SIGMA → IOC → Completed

**Monitor processing:**
```bash
# Watch worker logs
sudo journalctl -u casescope-worker -f

# Watch queue
watch -n 1 'redis-cli LLEN celery'
```

---

## 🔧 Common Issues

### OpenSearch won't start
```bash
# Check logs
sudo journalctl -u opensearch -n 100

# Increase memory if needed
sudo nano /opt/opensearch/config/jvm.options
# Change -Xms1g -Xmx1g to available memory
```

### Worker not processing
```bash
# Check worker status
sudo systemctl status casescope-worker

# Restart worker
sudo systemctl restart casescope-worker

# Check for errors
sudo journalctl -u casescope-worker -n 100
```

### Database locked errors
```bash
# Check for multiple processes
ps aux | grep celery

# Kill and restart
sudo systemctl restart casescope-worker
```

---

## 📚 Next Steps

1. **Security**
   - Change admin password
   - Setup firewall (ufw)
   - Add nginx reverse proxy with SSL

2. **Configuration**
   - Create user accounts
   - Import IOC lists
   - Configure SIGMA rules

3. **Documentation**
   - Read `README.md` for features
   - Read `DEPLOYMENT_GUIDE.md` for advanced setup

---

## 🆘 Need Help?

**Logs:**
```bash
# Web application
sudo journalctl -u casescope -f

# Worker
sudo journalctl -u casescope-worker -f

# OpenSearch
sudo journalctl -u opensearch -f

# All errors
sudo journalctl --since "1 hour ago" | grep ERROR
```

**Health Checks:**
```bash
# Web
curl http://localhost:5000

# OpenSearch
curl localhost:9200/_cluster/health

# Redis
redis-cli ping

# Queue
redis-cli LLEN celery
```

---

**Installation Time: ~20 minutes**  
**CaseScope 2026 v1.0.0 - Built for the DFIR Community** 🔍

