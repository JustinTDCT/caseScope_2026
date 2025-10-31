#!/usr/bin/env python3
"""
CaseScope 2026 v1.0.0 - Configuration
"""

import os

class Config:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'casescope-2026-change-in-production'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:////opt/casescope/data/casescope.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # OpenSearch
    OPENSEARCH_HOST = os.environ.get('OPENSEARCH_HOST') or 'localhost'
    OPENSEARCH_PORT = int(os.environ.get('OPENSEARCH_PORT') or 9200)
    OPENSEARCH_USE_SSL = os.environ.get('OPENSEARCH_USE_SSL', 'false').lower() == 'true'
    
    # Celery
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0'
    
    # File paths
    UPLOAD_FOLDER = '/opt/casescope/uploads'
    STAGING_FOLDER = '/opt/casescope/staging'
    ARCHIVE_FOLDER = '/opt/casescope/archive'
    LOCAL_UPLOAD_FOLDER = '/opt/casescope/local_uploads'
    
    # Processing
    MAX_WORKERS = 2  # Process 2 files at a time
    EVTX_DUMP_PATH = '/opt/casescope/bin/evtx_dump'
    CHAINSAW_PATH = '/opt/casescope/bin/chainsaw'
    CHAINSAW_RULES = '/opt/casescope/sigma_rules'
    CHAINSAW_MAPPING = '/opt/casescope/chainsaw/mappings/sigma-event-logs-all.yml'

