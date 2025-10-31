#!/usr/bin/env python3
"""
CaseScope 2026 - Admin Routes
Audit trail and system log viewing for administrators
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
import subprocess
import os

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Require administrator role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'administrator':
            return "Administrator access required", 403
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# AUDIT TRAIL
# ============================================================================

@admin_bp.route('/audit')
@login_required
@admin_required
def audit_trail():
    """View audit trail"""
    from main import db
    from models import AuditLog, User
    
    # Get filter parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    action_filter = request.args.get('action', '')
    resource_filter = request.args.get('resource', '')
    user_filter = request.args.get('user', '')
    status_filter = request.args.get('status', '')
    days_filter = request.args.get('days', 7, type=int)
    
    # Build query
    query = AuditLog.query
    
    # Time filter
    if days_filter > 0:
        start_date = datetime.utcnow() - timedelta(days=days_filter)
        query = query.filter(AuditLog.created_at >= start_date)
    
    # Action filter
    if action_filter:
        query = query.filter(AuditLog.action.like(f'%{action_filter}%'))
    
    # Resource type filter
    if resource_filter:
        query = query.filter(AuditLog.resource_type == resource_filter)
    
    # User filter
    if user_filter:
        query = query.filter(AuditLog.username.like(f'%{user_filter}%'))
    
    # Status filter
    if status_filter:
        query = query.filter(AuditLog.status == status_filter)
    
    # Order by most recent first
    query = query.order_by(AuditLog.created_at.desc())
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get unique values for filters
    actions = db.session.query(AuditLog.action).distinct().all()
    actions = sorted([a[0] for a in actions if a[0]])
    
    resources = db.session.query(AuditLog.resource_type).distinct().all()
    resources = sorted([r[0] for r in resources if r[0]])
    
    users = db.session.query(AuditLog.username).distinct().all()
    users = sorted([u[0] for u in users if u[0]])
    
    # Statistics
    total_logs = AuditLog.query.count()
    logs_today = AuditLog.query.filter(
        AuditLog.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).count()
    
    failed_logs = AuditLog.query.filter(AuditLog.status != 'success').count()
    
    return render_template('admin_audit.html',
                         logs=pagination.items,
                         pagination=pagination,
                         actions=actions,
                         resources=resources,
                         users=users,
                         action_filter=action_filter,
                         resource_filter=resource_filter,
                         user_filter=user_filter,
                         status_filter=status_filter,
                         days_filter=days_filter,
                         total_logs=total_logs,
                         logs_today=logs_today,
                         failed_logs=failed_logs)


@admin_bp.route('/audit/<int:log_id>')
@login_required
@admin_required
def audit_detail(log_id):
    """Get detailed information about an audit log entry"""
    from main import db
    from models import AuditLog
    
    log = db.session.get(AuditLog, log_id)
    if not log:
        return jsonify({'error': 'Log not found'}), 404
    
    return jsonify({
        'id': log.id,
        'username': log.username,
        'action': log.action,
        'resource_type': log.resource_type,
        'resource_id': log.resource_id,
        'resource_name': log.resource_name,
        'details': log.details,
        'ip_address': log.ip_address,
        'user_agent': log.user_agent,
        'status': log.status,
        'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
    })


# ============================================================================
# SYSTEM LOGS
# ============================================================================

@admin_bp.route('/logs')
@login_required
@admin_required
def system_logs():
    """View system logs"""
    return render_template('admin_logs.html')


@admin_bp.route('/logs/fetch')
@login_required
@admin_required
def fetch_system_logs():
    """Fetch system logs via AJAX"""
    lines = request.args.get('lines', 100, type=int)
    level = request.args.get('level', 'all')  # all, error, warning, info
    service = request.args.get('service', 'casescope')
    
    # Limit lines to prevent abuse
    lines = min(lines, 1000)
    
    try:
        # Build journalctl command (use full path)
        cmd = ['/usr/bin/journalctl', '-u', f'{service}.service', '-n', str(lines), '--no-pager']
        
        # Add level filter if specified
        if level == 'error':
            cmd.extend(['-p', 'err'])
        elif level == 'warning':
            cmd.extend(['-p', 'warning'])
        
        # Execute command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            logs = result.stdout
            return jsonify({
                'success': True,
                'logs': logs,
                'lines': len(logs.split('\n'))
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch logs',
                'stderr': result.stderr
            }), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Log fetch timed out'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/logs/worker')
@login_required
@admin_required
def fetch_worker_logs():
    """Fetch Celery worker logs"""
    lines = request.args.get('lines', 100, type=int)
    lines = min(lines, 1000)
    
    try:
        cmd = ['/usr/bin/journalctl', '-u', 'casescope-worker.service', '-n', str(lines), '--no-pager']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'logs': result.stdout,
                'lines': len(result.stdout.split('\n'))
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch worker logs'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/logs/download/<service>')
@login_required
@admin_required
def download_logs(service):
    """Download system logs as a file"""
    from flask import send_file
    import tempfile
    
    if service not in ['casescope', 'casescope-worker']:
        return "Invalid service", 400
    
    try:
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            cmd = ['/usr/bin/journalctl', '-u', f'{service}.service', '-n', '5000', '--no-pager']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                f.write(result.stdout)
                temp_path = f.name
        
        # Send file
        filename = f'{service}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.log'
        return send_file(temp_path, as_attachment=True, download_name=filename,
                        mimetype='text/plain')
    except Exception as e:
        return f"Error downloading logs: {str(e)}", 500

