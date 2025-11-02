#!/usr/bin/env python3
"""
CaseScope 2026 v1.0.0 - Database Models
Minimal, clean schema with only essential fields
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User accounts for authentication"""
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120))
    role = db.Column(db.String(20), default='analyst')  # administrator, analyst, read-only
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    creator = db.relationship('User', remote_side=[id], backref='users_created', foreign_keys=[created_by])


class Case(db.Model):
    """Investigation cases"""
    __tablename__ = 'case'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text)
    company = db.Column(db.String(200))
    status = db.Column(db.String(20), default='active')  # active, closed, archived
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    files = db.relationship('CaseFile', back_populates='case', lazy='dynamic')
    creator = db.relationship('User', foreign_keys=[created_by], backref='cases_created')
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='cases_assigned')


class CaseFile(db.Model):
    """Files uploaded to cases"""
    __tablename__ = 'case_file'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False, index=True)
    filename = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(500), nullable=False)
    file_path = db.Column(db.String(1000), nullable=False)
    file_size = db.Column(db.BigInteger, default=0)  # bytes
    size_mb = db.Column(db.Integer, default=0)  # MB rounded
    file_hash = db.Column(db.String(64), index=True)  # SHA256
    file_type = db.Column(db.String(20))  # EVTX, JSON, NDJSON, CSV, ZIP
    mime_type = db.Column(db.String(100))
    
    # Processing status
    indexing_status = db.Column(db.String(50), default='Queued')  # Queued, Indexing, Completed, Failed
    is_indexed = db.Column(db.Boolean, default=False)
    is_hidden = db.Column(db.Boolean, default=False)  # Hide 0-event files
    is_deleted = db.Column(db.Boolean, default=False)
    
    # Event counts
    event_count = db.Column(db.Integer, default=0)
    estimated_event_count = db.Column(db.Integer, default=0)
    violation_count = db.Column(db.Integer, default=0)
    sigma_event_count = db.Column(db.Integer, default=0)
    ioc_event_count = db.Column(db.Integer, default=0)
    
    # OpenSearch integration
    opensearch_key = db.Column(db.String(200), index=True)
    
    # Task tracking
    celery_task_id = db.Column(db.String(255))
    
    # Metadata
    upload_type = db.Column(db.String(20), default='http')  # http, bulk, staging
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    case = db.relationship('Case', back_populates='files')


class SigmaRule(db.Model):
    """SIGMA detection rules"""
    __tablename__ = 'sigma_rule'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    rule_yaml = db.Column(db.Text, nullable=False)
    level = db.Column(db.String(20))  # low, medium, high, critical
    tags = db.Column(db.Text)  # JSON array
    is_enabled = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SigmaViolation(db.Model):
    """SIGMA detection matches"""
    __tablename__ = 'sigma_violation'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey('case_file.id'), nullable=False, index=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('sigma_rule.id'), nullable=False)
    event_id = db.Column(db.String(64), index=True)
    event_data = db.Column(db.Text)  # JSON
    matched_fields = db.Column(db.Text)  # JSON
    severity = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class IOC(db.Model):
    """Indicators of Compromise"""
    __tablename__ = 'ioc'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False, index=True)
    ioc_type = db.Column(db.String(50), nullable=False)  # ip, username, hostname, fqdn, command, filename, malware_name, hash, port, url, registry_key, email
    ioc_value = db.Column(db.String(500), nullable=False, index=True)
    description = db.Column(db.Text)
    threat_level = db.Column(db.String(20), default='medium')
    is_active = db.Column(db.Boolean, default=True)
    
    # User tracking
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # OpenCTI integration
    opencti_enrichment = db.Column(db.Text)  # JSON: enriched data from OpenCTI
    opencti_enriched_at = db.Column(db.DateTime)
    
    # DFIR-IRIS integration
    dfir_iris_synced = db.Column(db.Boolean, default=False)
    dfir_iris_sync_date = db.Column(db.DateTime)
    dfir_iris_ioc_id = db.Column(db.String(100))  # DFIR-IRIS IOC ID


class IOCMatch(db.Model):
    """IOC detection matches"""
    __tablename__ = 'ioc_match'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False, index=True)
    ioc_id = db.Column(db.Integer, db.ForeignKey('ioc.id'), nullable=False)
    file_id = db.Column(db.Integer, db.ForeignKey('case_file.id'), nullable=False)
    index_name = db.Column(db.String(200), index=True)
    event_id = db.Column(db.String(64))
    event_data = db.Column(db.Text)  # JSON
    matched_field = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SkippedFile(db.Model):
    """Files skipped during upload (duplicates, 0-events, etc.)"""
    __tablename__ = 'skipped_file'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False, index=True)
    filename = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.BigInteger)
    file_hash = db.Column(db.String(64))
    skip_reason = db.Column(db.String(100))  # duplicate, zero_events, error
    skip_details = db.Column(db.Text)
    upload_type = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SystemSettings(db.Model):
    """System-wide settings"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.Text)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EventDescription(db.Model):
    """Windows Event ID descriptions for friendly display"""
    __tablename__ = 'event_description'
    
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, nullable=False, index=True)
    event_source = db.Column(db.String(100))  # e.g., 'Security', 'System', 'Sysmon'
    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    source_url = db.Column(db.String(500))  # Which site it came from
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Composite unique constraint on event_id + source
    __table_args__ = (
        db.UniqueConstraint('event_id', 'event_source', name='_event_source_uc'),
    )


class SearchHistory(db.Model):
    """Search history and saved searches"""
    __tablename__ = 'search_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=True, index=True)
    search_query = db.Column(db.Text, nullable=False)  # JSON string of search parameters
    search_name = db.Column(db.String(200))  # Optional name for saved search
    is_favorite = db.Column(db.Boolean, default=False, index=True)
    filter_type = db.Column(db.String(50))  # 'all', 'sigma', 'ioc', 'sigma_and_ioc', 'tagged'
    date_range = db.Column(db.String(50))  # '24h', '7d', '30d', 'custom'
    custom_date_start = db.Column(db.DateTime)
    custom_date_end = db.Column(db.DateTime)
    column_config = db.Column(db.Text)  # JSON string of column configuration
    result_count = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    last_used = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='search_history')
    case = db.relationship('Case', backref='search_history')


class TimelineTag(db.Model):
    """Timeline tags for events (DFIR-IRIS integration)"""
    __tablename__ = 'timeline_tag'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.String(64), nullable=False, index=True)  # OpenSearch document ID
    index_name = db.Column(db.String(200), nullable=False, index=True)
    event_data = db.Column(db.Text)  # JSON snapshot of event when tagged
    tag_color = db.Column(db.String(20), default='blue')  # For visual identification
    notes = db.Column(db.Text)  # User notes about this event
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    case = db.relationship('Case', backref='timeline_tags')
    user = db.relationship('User', backref='timeline_tags')
    
    # Composite unique constraint to prevent duplicate tags
    __table_args__ = (
        db.UniqueConstraint('case_id', 'event_id', 'index_name', name='_timeline_tag_uc'),
    )


class AuditLog(db.Model):
    """Audit trail for user actions"""
    __tablename__ = 'audit_log'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)  # Nullable for system actions
    username = db.Column(db.String(80))  # Store username for historical reference
    action = db.Column(db.String(100), nullable=False, index=True)  # e.g., 'login', 'create_case', 'delete_file'
    resource_type = db.Column(db.String(50), index=True)  # e.g., 'case', 'file', 'user', 'ioc'
    resource_id = db.Column(db.Integer)  # ID of the affected resource
    resource_name = db.Column(db.String(500))  # Name/description of the resource
    details = db.Column(db.Text)  # JSON or text details about the action
    ip_address = db.Column(db.String(45))  # IPv4 or IPv6
    user_agent = db.Column(db.String(500))  # Browser/client info
    status = db.Column(db.String(20), default='success')  # success, failed, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True, nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='audit_logs', foreign_keys=[user_id])


class AIReport(db.Model):
    """AI-generated DFIR reports"""
    __tablename__ = 'ai_report'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False, index=True)
    generated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending', index=True)  # pending, generating, completed, failed
    model_name = db.Column(db.String(50), default='phi3:14b')  # AI model used
    report_title = db.Column(db.String(500))
    report_content = db.Column(db.Text)  # Full report in markdown format
    generation_time_seconds = db.Column(db.Float)  # How long it took to generate
    error_message = db.Column(db.Text)  # Error details if failed
    progress_percent = db.Column(db.Integer, default=0)  # 0-100 progress indicator
    progress_message = db.Column(db.String(200))  # Current step description
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    case = db.relationship('Case', backref='ai_reports', foreign_keys=[case_id])
    generator = db.relationship('User', backref='generated_reports', foreign_keys=[generated_by])

