"""
CaseScope 2026 - System Statistics Module
Provides system health monitoring and software version detection
"""

import os
import platform
import subprocess
import psutil
from pathlib import Path


def get_system_status():
    """Get system status information"""
    try:
        # CPU info
        cpu_count = psutil.cpu_count(logical=True)
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory info
        mem = psutil.virtual_memory()
        mem_total_gb = round(mem.total / (1024**3), 2)
        mem_used_gb = round(mem.used / (1024**3), 2)
        mem_percent = mem.percent
        
        # Disk info
        disk = psutil.disk_usage('/')
        disk_total_gb = round(disk.total / (1024**3), 2)
        disk_used_gb = round(disk.used / (1024**3), 2)
        disk_percent = disk.percent
        
        # OS info
        os_name = f"{platform.system()} {platform.release()}"
        
        return {
            'os_name': os_name,
            'cpu_cores': cpu_count,
            'cpu_usage': cpu_percent,
            'memory_total_gb': mem_total_gb,
            'memory_used_gb': mem_used_gb,
            'memory_percent': mem_percent,
            'disk_total_gb': disk_total_gb,
            'disk_used_gb': disk_used_gb,
            'disk_percent': disk_percent
        }
    except Exception as e:
        print(f"Error getting system status: {e}")
        return None


def get_case_files_space():
    """Calculate space consumed by case files"""
    try:
        uploads_path = '/opt/casescope/uploads'
        staging_path = '/opt/casescope/staging'
        
        total_size = 0
        
        # Calculate uploads directory size
        if os.path.exists(uploads_path):
            for dirpath, dirnames, filenames in os.walk(uploads_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
        
        # Calculate staging directory size
        if os.path.exists(staging_path):
            for dirpath, dirnames, filenames in os.walk(staging_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
        
        # Convert to GB
        total_gb = round(total_size / (1024**3), 2)
        return total_gb
    except Exception as e:
        print(f"Error calculating case files space: {e}")
        return 0


def get_software_versions():
    """Detect installed software versions"""
    versions = {}
    
    # Python version
    versions['Python'] = platform.python_version()
    
    # SQLite version
    try:
        import sqlite3
        versions['SQLite3'] = sqlite3.sqlite_version
    except:
        versions['SQLite3'] = 'Unknown'
    
    # Flask version
    try:
        import flask
        versions['Flask'] = flask.__version__
    except:
        versions['Flask'] = 'Unknown'
    
    # Celery version
    try:
        import celery
        versions['Celery'] = celery.__version__
    except:
        versions['Celery'] = 'Unknown'
    
    # Redis version
    try:
        result = subprocess.run(['redis-cli', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout:
            # Parse version from output like "redis-cli 7.0.15"
            version_line = result.stdout.strip()
            parts = version_line.split()
            if len(parts) >= 2:
                # Extract just the version number (second part)
                versions['Redis'] = parts[1].strip()
            else:
                versions['Redis'] = 'Installed'
        else:
            versions['Redis'] = 'Unknown'
    except Exception as e:
        print(f"Redis version detection error: {e}")
        versions['Redis'] = 'Unknown'
    
    # OpenSearch version
    try:
        import requests
        response = requests.get('http://localhost:9200', timeout=2)
        if response.status_code == 200:
            data = response.json()
            versions['OpenSearch'] = data.get('version', {}).get('number', 'Unknown')
        else:
            versions['OpenSearch'] = 'Running'
    except:
        versions['OpenSearch'] = 'Unknown'
    
    # evtx_dump version
    try:
        result = subprocess.run(['/opt/casescope/bin/evtx_dump', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            # Extract version from output
            version_line = result.stderr.strip() or result.stdout.strip()
            if version_line:
                versions['evtx_dump'] = version_line.split()[-1] if ' ' in version_line else version_line
            else:
                versions['evtx_dump'] = 'Installed'
        else:
            versions['evtx_dump'] = 'Installed'
    except:
        versions['evtx_dump'] = 'Not Found'
    
    # Chainsaw version
    try:
        result = subprocess.run(['/opt/casescope/bin/chainsaw', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            # Parse version like "chainsaw 2.9.1"
            version_line = result.stdout.strip()
            if ' ' in version_line:
                versions['Chainsaw'] = version_line.split()[-1]
            else:
                versions['Chainsaw'] = version_line
        else:
            versions['Chainsaw'] = 'Installed'
    except:
        versions['Chainsaw'] = 'Not Found'
    
    # Gunicorn version
    try:
        import gunicorn
        versions['Gunicorn'] = gunicorn.__version__
    except:
        versions['Gunicorn'] = 'Unknown'
    
    return versions


def get_service_status():
    """Check if critical services are running"""
    services = {}
    
    # Check systemd services
    service_names = ['casescope', 'casescope-worker', 'opensearch', 'redis']
    
    for service in service_names:
        try:
            result = subprocess.run(['systemctl', 'is-active', service], 
                                  capture_output=True, text=True, timeout=2)
            services[service] = result.stdout.strip() == 'active'
        except:
            services[service] = False
    
    return services


def get_sigma_rules_info():
    """Get SIGMA rules information"""
    try:
        sigma_path = '/opt/casescope/sigma_rules'
        
        if not os.path.exists(sigma_path):
            return {'total': 0, 'enabled': 0, 'last_updated': None}
        
        # Count .yml files
        total_rules = 0
        for root, dirs, files in os.walk(sigma_path):
            total_rules += len([f for f in files if f.endswith('.yml')])
        
        # Get last modification time
        try:
            stat = os.stat(sigma_path)
            from datetime import datetime
            last_updated = datetime.fromtimestamp(stat.st_mtime)
        except:
            last_updated = None
        
        return {
            'total': total_rules,
            'enabled': total_rules,  # All rules are enabled by default
            'last_updated': last_updated
        }
    except Exception as e:
        print(f"Error getting SIGMA rules info: {e}")
        return {'total': 0, 'enabled': 0, 'last_updated': None}

