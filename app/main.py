#!/usr/bin/env python3
"""
CaseScope 2026 v1.0.0 - Main Flask Application
Minimal viable product - essential routes only
"""

import os
import logging
from datetime import datetime
from flask import Flask, render_template_string, render_template, request, redirect, url_for, jsonify, session, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from opensearchpy import OpenSearch

# Import config and models
from config import Config
from models import db, User, Case, CaseFile, SigmaRule, SigmaViolation, IOC, IOCMatch, SkippedFile, SystemSettings
from celery_app import celery_app

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Disable static file caching for CSS/JS
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Cache busting timestamp for static files
import time
CACHE_BUST_TIME = str(int(time.time()))

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize OpenSearch
opensearch_client = OpenSearch(
    hosts=[{'host': app.config['OPENSEARCH_HOST'], 'port': app.config['OPENSEARCH_PORT']}],
    http_compress=True,
    use_ssl=app.config['OPENSEARCH_USE_SSL'],
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False
)

# Register blueprints
from routes.ioc import ioc_bp
app.register_blueprint(ioc_bp)
from routes.files import files_bp
from routes.cases import cases_bp
from routes.api_stats import api_stats_bp
from routes.settings import settings_bp
from routes.users import users_bp
from routes.admin import admin_bp
app.register_blueprint(files_bp)
app.register_blueprint(cases_bp)
app.register_blueprint(api_stats_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(users_bp)
app.register_blueprint(admin_bp)

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# Context processor - inject global template variables
@app.after_request
def add_header(response):
    """Add cache control headers to prevent caching"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.context_processor
def inject_global_vars():
    """Inject available_cases, current_case, and version info into all templates"""
    import json
    import os
    
    # Load version info from version.json
    version_info = {'version': 'unknown', 'name': 'CaseScope', 'release_date': '', 'build': ''}
    try:
        version_file = os.path.join(os.path.dirname(__file__), 'version.json')
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                version_info = json.load(f)
    except Exception as e:
        print(f"Error loading version.json: {e}")
    
    if current_user.is_authenticated:
        available_cases = db.session.query(Case).filter_by(status='active').order_by(Case.created_at.desc()).all()
        
        # Determine current case: URL > Session > None
        current_case = None
        
        # Priority 1: case_id in URL (set session from URL)
        if request.view_args and 'case_id' in request.view_args:
            case_id = request.view_args['case_id']
            current_case = db.session.get(Case, case_id)
            if current_case:
                session['current_case_id'] = case_id
        # Priority 2: case_id in session
        elif 'current_case_id' in session:
            current_case = db.session.get(Case, session['current_case_id'])
            # Clear session if case no longer exists
            if not current_case:
                session.pop('current_case_id', None)
        
        return {
            'available_cases': available_cases,
            'current_case': current_case,
            'db': db,
            'CaseFile': CaseFile,
            'app_version': version_info,
            'cache_bust': CACHE_BUST_TIME
        }
    return {
        'app_version': version_info,
        'cache_bust': CACHE_BUST_TIME
    }


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    # Get version info
    import json
    import os
    version_info = {'version': 'unknown'}
    try:
        version_file = os.path.join(os.path.dirname(__file__), 'version.json')
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                version_info = json.load(f)
    except:
        pass
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = db.session.query(User).filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Check if user is active
            if not user.is_active:
                # Log failed login attempt
                from audit_logger import log_action
                log_action('login_failed', resource_type='auth', resource_name=username, 
                          details='Account deactivated', status='failed')
                flash('Your account has been deactivated. Please contact an administrator.', 'error')
                return render_template('login.html', app_version=version_info, cache_bust=CACHE_BUST_TIME)
            
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Log successful login
            from audit_logger import log_action
            log_action('login', resource_type='auth', resource_name=username, status='success')
            
            return redirect(url_for('dashboard'))
        
        # Log failed login attempt
        from audit_logger import log_action
        log_action('login_failed', resource_type='auth', resource_name=username or 'unknown', 
                  details='Invalid credentials', status='failed')
        flash('Invalid username or password', 'error')
    
    return render_template('login.html', app_version=version_info, cache_bust=CACHE_BUST_TIME)

# OLD LOGIN TEMPLATE - DELETED, NOW USING templates/login.html
def _old_login_template():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>CaseScope 2026 - Login</title>
        <style>
            body { font-family: Arial; background: #1a1a1a; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .login-box { background: #2a2a2a; padding: 40px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); min-width: 350px; }
            .logo-container { text-align: center; margin-bottom: 30px; }
            .logo-main { margin-bottom: 5px; }
            .logo-text { font-size: 28px; font-weight: 700; }
            .logo-case { color: #4ade80; font-weight: 600; }
            .logo-scope { color: #fff; font-weight: 300; }
            .logo-year { color: #fff; font-weight: 300; margin-left: 8px; }
            .logo-version { color: #94a3b8; font-size: 12px; font-weight: 400; }
            input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #444; background: #333; color: #fff; border-radius: 5px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; background: #0066cc; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; margin-top: 10px; }
            button:hover { background: #0052a3; }
            .error { color: #ff4444; margin-bottom: 15px; text-align: center; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <div class="logo-container">
                <div class="logo-main">
                    <span class="logo-text">
                        <span class="logo-case">case</span><span class="logo-scope">Scope</span><span class="logo-year">2026</span>
                    </span>
                </div>
                <div class="logo-version">v{{ version }}</div>
            </div>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="error">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <form method="POST">
                <input type="text" name="username" placeholder="Username" required autofocus>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    ''', version=version_info.get('version', 'unknown'))


@app.route('/logout')
@login_required
def logout():
    """Logout"""
    # Log logout
    from audit_logger import log_action
    username = current_user.username if current_user.is_authenticated else 'unknown'
    log_action('logout', resource_type='auth', resource_name=username)
    
    logout_user()
    return redirect(url_for('login'))


# ============================================================================
# CASE SELECTION
# ============================================================================

@app.route('/select_case/<int:case_id>')
@login_required
def select_case(case_id):
    """Set the current case in session and redirect"""
    case = db.session.get(Case, case_id)
    if case:
        session['current_case_id'] = case_id
        flash(f'Case selected: {case.name}', 'success')
        return redirect(url_for('view_case', case_id=case_id))
    else:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))


@app.route('/clear_case')
@login_required
def clear_case():
    """Clear the current case selection"""
    session.pop('current_case_id', None)
    flash('Case selection cleared', 'info')
    return redirect(url_for('dashboard'))


# ============================================================================
# DASHBOARD
# ============================================================================

@app.route('/')
@login_required
def dashboard():
    """Enhanced System Dashboard with comprehensive stats"""
    from system_stats import get_system_status, get_case_files_space, get_software_versions, get_sigma_rules_info
    
    # System Status
    system_status = get_system_status()
    case_files_space_gb = get_case_files_space()
    
    # CaseScope Status
    total_cases = db.session.query(Case).filter_by(status='active').count()
    total_files = db.session.query(CaseFile).filter_by(is_deleted=False, is_hidden=False).count()
    sigma_info = get_sigma_rules_info()
    total_iocs = db.session.query(IOC).count()
    
    # Events Status
    total_events = db.session.query(CaseFile).filter_by(is_deleted=False, is_hidden=False).with_entities(
        db.func.sum(CaseFile.event_count)
    ).scalar() or 0
    total_sigma_violations = db.session.query(SigmaViolation).count()
    total_ioc_events = db.session.query(CaseFile).filter_by(is_deleted=False, is_hidden=False).with_entities(
        db.func.sum(CaseFile.ioc_event_count)
    ).scalar() or 0
    
    # Software Status
    software_versions = get_software_versions()
    
    # Recent Cases (last 10)
    recent_cases = db.session.query(Case).order_by(Case.created_at.desc()).limit(10).all()
    
    # Recent Files (last 10)
    recent_files = db.session.query(CaseFile).filter_by(
        is_deleted=False,
        is_hidden=False
    ).order_by(CaseFile.uploaded_at.desc()).limit(10).all()
    
    return render_template('dashboard_enhanced.html',
        system_status=system_status,
        case_files_space_gb=case_files_space_gb,
        total_cases=total_cases,
        total_files=total_files,
        sigma_info=sigma_info,
        total_iocs=total_iocs,
        total_events=total_events,
        total_sigma_violations=total_sigma_violations,
        total_ioc_events=total_ioc_events,
        software_versions=software_versions,
        recent_cases=recent_cases,
        recent_files=recent_files
    )


# OLD INLINE TEMPLATE - KEEPING FOR REFERENCE, CAN BE DELETED
def _old_dashboard_template():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>CaseScope 2026 - Dashboard</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: Arial; background: #1a1a1a; color: #fff; }
            .header { background: #2a2a2a; padding: 20px; border-bottom: 2px solid #0066cc; display: flex; justify-content: space-between; align-items: center; }
            .header h1 { font-size: 24px; }
            .header a { color: #0066cc; text-decoration: none; margin-left: 20px; }
            .container { padding: 30px; max-width: 1400px; margin: 0 auto; }
            .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
            .stat-card { background: #2a2a2a; padding: 20px; border-radius: 8px; text-align: center; }
            .stat-card h3 { font-size: 36px; color: #0066cc; margin-bottom: 10px; }
            .stat-card p { color: #999; }
            .section { background: #2a2a2a; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .section h2 { margin-bottom: 20px; font-size: 20px; }
            table { width: 100%; border-collapse: collapse; }
            th { background: #333; padding: 12px; text-align: left; font-weight: 600; }
            td { padding: 12px; border-bottom: 1px solid #333; }
            tr:hover { background: #333; }
            .btn { background: #0066cc; color: white; padding: 8px 16px; border-radius: 5px; text-decoration: none; display: inline-block; border: none; cursor: pointer; }
            .btn:hover { background: #0052a3; }
            .btn-sm { padding: 6px 12px; font-size: 13px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔍 CaseScope 2026</h1>
            <div>
                <a href="{{ url_for('create_case') }}" class="btn">+ New Case</a>
                <a href="{{ url_for('logout') }}">Logout ({{ current_user.username }})</a>
            </div>
        </div>
        
        <div class="container">
            <div class="stats">
                <div class="stat-card">
                    <h3>{{ total_cases }}</h3>
                    <p>Total Cases</p>
                </div>
                <div class="stat-card">
                    <h3>{{ total_files }}</h3>
                    <p>Files Indexed</p>
                </div>
                <div class="stat-card">
                    <h3>{{ total_violations }}</h3>
                    <p>SIGMA Violations</p>
                </div>
                <div class="stat-card">
                    <h3>{{ total_ioc_matches }}</h3>
                    <p>IOC Matches</p>
                </div>
            </div>
            
            <div class="section">
                <h2>Active Cases</h2>
                {% if cases %}
                <table>
                    <thead>
                        <tr>
                            <th>Case Name</th>
                            <th>Company</th>
                            <th>Files</th>
                            <th>Created</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for case in cases %}
                        <tr>
                            <td><strong>{{ case.name }}</strong></td>
                            <td>{{ case.company or 'N/A' }}</td>
                            <td>{{ case.files.count() }}</td>
                            <td>{{ case.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                            <td>
                                <a href="{{ url_for('view_case', case_id=case.id) }}" class="btn btn-sm">View</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="color: #999; text-align: center; padding: 40px;">No cases yet. Create your first case to get started.</p>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    ''', cases=cases, total_cases=total_cases, total_files=total_files, 
         total_violations=total_violations, total_ioc_matches=total_ioc_matches)


# ============================================================================
# QUEUE CLEANUP & HEALTH CHECK
# ============================================================================

@app.route('/queue/cleanup', methods=['POST'])
@login_required
def queue_cleanup_all():
    """System-wide queue cleanup (all cases)"""
    from queue_cleanup import cleanup_queue
    
    try:
        result = cleanup_queue(db, CaseFile, case_id=None)
        
        if result['status'] == 'success':
            flash(result['message'], 'success')
        else:
            flash(result['message'], 'error')
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Queue cleanup error: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


@app.route('/queue/health', methods=['GET'])
@login_required
def queue_health_check():
    """Get queue health status (system-wide)"""
    from queue_cleanup import get_queue_health
    
    try:
        health = get_queue_health(db, CaseFile, case_id=None)
        return jsonify(health)
    
    except Exception as e:
        logger.error(f"Queue health check error: {e}", exc_info=True)
        return jsonify({
            'health_status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


# ============================================================================
# CASE MANAGEMENT
# ============================================================================

@app.route('/cases')
@login_required
def case_selection():
    """Case Selection Page - List all active cases"""
    # Get all active cases, ordered by most recent first
    cases = db.session.query(Case).filter_by(status='active').order_by(Case.created_at.desc()).all()
    
    # Get file counts and other stats for each case
    case_stats = []
    for case in cases:
        file_count = db.session.query(CaseFile).filter_by(
            case_id=case.id,
            is_deleted=False,
            is_hidden=False
        ).count()
        
        total_events = db.session.query(CaseFile).filter_by(
            case_id=case.id,
            is_deleted=False,
            is_hidden=False
        ).with_entities(db.func.sum(CaseFile.event_count)).scalar() or 0
        
        case_stats.append({
            'case': case,
            'file_count': file_count,
            'total_events': total_events
        })
    
    return render_template('case_selection.html', case_stats=case_stats)


@app.route('/case/create', methods=['GET', 'POST'])
@login_required
def create_case():
    """Create new case"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        company = request.form.get('company')
        
        case = Case(
            name=name,
            description=description,
            company=company,
            created_by=current_user.id
        )
        db.session.add(case)
        db.session.commit()
        
        flash('Case created successfully', 'success')
        return redirect(url_for('view_case', case_id=case.id))
    
    return render_template('create_case.html')


@app.route('/case/<int:case_id>/status')
@login_required
def case_file_status(case_id):
    """API endpoint: Get file statuses and aggregated stats for live updates"""
    from hidden_files import get_file_stats_with_hidden
    from sqlalchemy import func
    
    files = db.session.query(CaseFile).filter_by(
        case_id=case_id, 
        is_deleted=False, 
        is_hidden=False
    ).all()
    
    # Get aggregated statistics
    stats = get_file_stats_with_hidden(db.session, case_id)
    
    return jsonify({
        'files': [{
            'id': f.id,
            'status': f.indexing_status,
            'event_count': f.event_count or 0,
            'violation_count': f.violation_count or 0,
            'ioc_event_count': f.ioc_event_count or 0
        } for f in files],
        'stats': {
            'total_events': stats['total_events'],
            'sigma_events': stats['sigma_events'],
            'ioc_events': stats['ioc_events']
        }
    })


@app.route('/case/<int:case_id>')
@login_required
def view_case(case_id):
    """Enhanced case dashboard with 3 tiles: Case Details, Case Files, Event Stats"""
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get only the 10 most recent files for display
    files = db.session.query(CaseFile).filter_by(case_id=case_id, is_deleted=False, is_hidden=False).order_by(CaseFile.uploaded_at.desc()).limit(10).all()
    
    # Count all active IOCs for this case
    total_iocs = db.session.query(IOC).filter_by(
        case_id=case_id,
        is_active=True
    ).count()
    
    return render_template('view_case_enhanced.html', case=case, files=files, total_iocs=total_iocs)


@app.route('/evtx_descriptions')
@login_required
def evtx_descriptions():
    """EVTX Event Descriptions Management"""
    from models import EventDescription
    from sqlalchemy import or_
    
    # Get search query and source filter
    search_query = request.args.get('q', '').strip()
    source_filter = request.args.get('source', '').strip()
    
    # Get statistics (for all events, not filtered by search or source)
    total_events = db.session.query(EventDescription).count()
    
    # Get counts by source (domain-based grouping)
    source_stats = {}
    
    # Count Ultimate Windows Security events
    uws_count = db.session.query(EventDescription).filter(
        EventDescription.source_url.like('%ultimatewindowssecurity%')
    ).count()
    if uws_count > 0:
        source_stats['Ultimate Windows Security'] = uws_count
    
    # Count GitHub Gist events
    github_count = db.session.query(EventDescription).filter(
        EventDescription.source_url.like('%github%')
    ).count()
    if github_count > 0:
        source_stats['GitHub Gist'] = github_count
    
    # Count Infrasos events
    infrasos_count = db.session.query(EventDescription).filter(
        EventDescription.source_url.like('%infrasos%')
    ).count()
    if infrasos_count > 0:
        source_stats['Infrasos'] = infrasos_count
    
    # Get last updated
    last_updated = db.session.query(
        db.func.max(EventDescription.last_updated)
    ).scalar()
    
    # Build query with source filter and search filter
    events_query = db.session.query(EventDescription)
    
    # Apply source filter first
    if source_filter:
        if source_filter == 'uws':
            events_query = events_query.filter(EventDescription.source_url.like('%ultimatewindowssecurity%'))
        elif source_filter == 'github':
            events_query = events_query.filter(EventDescription.source_url.like('%github%'))
        elif source_filter == 'infrasos':
            events_query = events_query.filter(EventDescription.source_url.like('%infrasos%'))
    
    # Apply search filter
    if search_query:
        # Search by event_id (exact or partial) OR title (contains)
        if search_query.isdigit():
            # If search is numeric, prioritize event_id exact match
            events_query = events_query.filter(
                or_(
                    EventDescription.event_id == int(search_query),
                    EventDescription.title.ilike(f'%{search_query}%'),
                    EventDescription.description.ilike(f'%{search_query}%')
                )
            )
        else:
            # Text search in title and description
            events_query = events_query.filter(
                or_(
                    EventDescription.title.ilike(f'%{search_query}%'),
                    EventDescription.description.ilike(f'%{search_query}%')
                )
            )
    
    events_query = events_query.order_by(EventDescription.event_id.asc())
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 50  # Show 50 events per page
    pagination = events_query.paginate(page=page, per_page=per_page, error_out=False)
    events = pagination.items
    
    return render_template(
        'evtx_descriptions.html',
        total_events=total_events,
        source_stats=source_stats,
        last_updated=last_updated,
        events=events,
        pagination=pagination,
        search_query=search_query,
        source_filter=source_filter
    )


@app.route('/evtx_descriptions/update', methods=['POST'])
@login_required
def evtx_descriptions_update():
    """Update EVTX descriptions from all sources"""
    from models import EventDescription
    from evtx_descriptions import update_all_descriptions
    
    # Admin check
    if current_user.role != 'admin':
        flash('Only administrators can update EVTX descriptions', 'error')
        return redirect(url_for('evtx_descriptions'))
    
    try:
        stats = update_all_descriptions(db, EventDescription)
        
        flash(f"Successfully updated EVTX descriptions: {stats['total_processed']} processed, "
              f"{stats['new_events']} new, {stats['updated_events']} updated", 'success')
        
        for source, count in stats['sources'].items():
            flash(f"{source}: {count} events", 'info')
            
    except Exception as e:
        flash(f'Error updating descriptions: {str(e)}', 'error')
        logger.error(f"[EVTX UPDATE] Error: {e}", exc_info=True)
    
    return redirect(url_for('evtx_descriptions'))


@app.route('/case/<int:case_id>/search')
@login_required
def search_events(case_id):
    """Advanced Event Search Page"""
    from models import SearchHistory, TimelineTag
    from search_utils import build_search_query, execute_search, extract_event_fields
    from utils import make_index_name
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get search parameters
    search_text = request.args.get('q', '')
    filter_type = request.args.get('filter', 'all')  # all, sigma, ioc, sigma_and_ioc, tagged
    date_range = request.args.get('date_range', 'all')
    file_types = request.args.getlist('file_types')  # ['EVTX', 'EDR', 'JSON', 'CSV']
    if not file_types:  # Default: all types checked
        file_types = ['EVTX', 'EDR', 'JSON', 'CSV']
    sort_field = request.args.get('sort', 'normalized_timestamp')  # Use normalized field
    sort_order = request.args.get('order', 'desc')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # If filtering by tagged events, get the list of tagged event IDs for this case
    tagged_event_ids = None
    if filter_type == 'tagged':
        from models import TimelineTag
        tagged_events = TimelineTag.query.filter_by(case_id=case_id).all()
        tagged_event_ids = [tag.event_id for tag in tagged_events]
        logger.debug(f"[SEARCH] Found {len(tagged_event_ids)} tagged events for case {case_id}")
    
    # Get column configuration from session or use defaults
    columns = session.get(f'search_columns_{case_id}', [
        'event_id', 'timestamp', 'description', 'computer_name', 'source_file'
    ])
    
    # Build index pattern for case (search ALL indices for this case)
    index_pattern = f"case_{case_id}_*"
    
    # Build query (if no search text, match all)
    if not search_text and filter_type == 'all' and date_range == 'all' and len(file_types) == 4:
        # Simple match_all for performance (only if all file types selected)
        query_dsl = {"query": {"match_all": {}}}
    else:
        query_dsl = build_search_query(
            search_text=search_text,
            filter_type=filter_type,
            date_range=date_range,
            file_types=file_types,
            tagged_event_ids=tagged_event_ids
        )
    
    # Execute search
    try:
        results, total_count, aggregations = execute_search(
            opensearch_client,
            index_pattern,
            query_dsl,
            page=page,
            per_page=per_page,
            sort_field=sort_field,
            sort_order=sort_order
        )
    except Exception as e:
        logger.error(f"[SEARCH] Search failed: {e}")
        flash(f'Search error: {str(e)}', 'error')
        results, total_count, aggregations = [], 0, {}
    
    # Extract normalized fields and enrich with IOC types
    events = []
    event_ids_to_check = []
    event_id_map = {}  # Map OpenSearch _id to event dict
    
    for result in results:
        fields = extract_event_fields(result['_source'])
        fields['_id'] = result['_id']
        fields['_index'] = result['_index']
        fields['ioc_types'] = []  # Will be populated if IOCs match
        events.append(fields)
        
        if fields.get('has_ioc'):
            event_ids_to_check.append(result['_id'])
            event_id_map[result['_id']] = fields
    
    # Batch lookup IOC types for events with matches
    if event_ids_to_check:
        # Query IOCMatch with IOC to get types
        ioc_matches = db.session.query(
            IOCMatch.event_id,
            IOC.ioc_type
        ).join(
            IOC, IOCMatch.ioc_id == IOC.id
        ).filter(
            IOCMatch.event_id.in_(event_ids_to_check)
        ).all()
        
        # Group IOC types by event_id
        from collections import defaultdict
        event_ioc_types = defaultdict(set)
        for event_id, ioc_type in ioc_matches:
            event_ioc_types[event_id].add(ioc_type)
        
        # Map IOC types back to events (as sorted lists)
        for event_id, ioc_types in event_ioc_types.items():
            if event_id in event_id_map:
                event_id_map[event_id]['ioc_types'] = sorted(ioc_types)
    
    # Calculate pagination
    total_pages = (total_count + per_page - 1) // per_page
    
    # Get tagged event IDs for this case
    tagged_ids = {tag.event_id for tag in db.session.query(TimelineTag).filter_by(case_id=case_id).all()}
    
    # Get recent searches for this user and case
    recent_searches_raw = db.session.query(SearchHistory).filter_by(
        user_id=current_user.id,
        case_id=case_id
    ).order_by(SearchHistory.last_used.desc()).limit(10).all()
    
    # Parse JSON for template
    import json
    recent_searches = []
    for search in recent_searches_raw:
        try:
            search_data = json.loads(search.search_query)
            recent_searches.append({
                'id': search.id,
                'search_text': search_data.get('search_text', ''),
                'filter_type': search.filter_type,
                'date_range': search.date_range
            })
        except:
            pass
    
    # Get favorite searches
    favorite_searches_raw = db.session.query(SearchHistory).filter_by(
        user_id=current_user.id,
        case_id=case_id,
        is_favorite=True
    ).order_by(SearchHistory.search_name.asc()).all()
    
    favorite_searches = []
    for search in favorite_searches_raw:
        try:
            search_data = json.loads(search.search_query)
            favorite_searches.append({
                'id': search.id,
                'search_name': search.search_name or 'Unnamed Search',
                'search_text': search_data.get('search_text', ''),
                'filter_type': search.filter_type,
                'date_range': search.date_range
            })
        except:
            pass
    
    # Save to history if results returned
    if total_count > 0:
        from search_utils import save_search_to_history
        save_search_to_history(
            db, SearchHistory, current_user.id, case_id,
            {
                'search_text': search_text,
                'filter_type': filter_type,
                'date_range': date_range,
                'sort_field': sort_field,
                'sort_order': sort_order,
                'column_config': columns
            },
            total_count
        )
    
    return render_template(
        'search_events.html',
        case=case,
        events=events,
        search_text=search_text,
        filter_type=filter_type,
        date_range=date_range,
        file_types=file_types,
        sort_field=sort_field,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
        columns=columns,
        tagged_ids=tagged_ids,
        recent_searches=recent_searches,
        favorite_searches=favorite_searches
    )


@app.route('/case/<int:case_id>/search/export')
@login_required
def export_search_results(case_id):
    """Export current search results as CSV"""
    from models import TimelineTag
    from search_utils import build_search_query, execute_search, extract_event_fields
    from export_utils import generate_events_csv
    from flask import make_response
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get same search parameters as search_events
    search_text = request.args.get('q', '')
    filter_type = request.args.get('filter', 'all')
    date_range = request.args.get('date_range', 'all')
    file_types = request.args.getlist('file_types')
    if not file_types:
        file_types = ['EVTX', 'EDR', 'JSON', 'CSV']
    sort_field = request.args.get('sort', 'normalized_timestamp')
    sort_order = request.args.get('order', 'desc')
    
    # Get tagged event IDs if filtering by tagged
    tagged_event_ids = None
    if filter_type == 'tagged':
        tagged_events = TimelineTag.query.filter_by(case_id=case_id).all()
        tagged_event_ids = [tag.event_id for tag in tagged_events]
    
    # Build index pattern and query (reuse same logic)
    index_pattern = f"case_{case_id}_*"
    
    if not search_text and filter_type == 'all' and date_range == 'all' and len(file_types) == 4:
        query_dsl = {"query": {"match_all": {}}}
    else:
        query_dsl = build_search_query(
            search_text=search_text,
            filter_type=filter_type,
            date_range=date_range,
            file_types=file_types,
            tagged_event_ids=tagged_event_ids
        )
    
    # Execute search - export ALL results (no pagination limit)
    try:
        results, total_count, _ = execute_search(
            opensearch_client,
            index_pattern,
            query_dsl,
            page=1,
            per_page=10000,  # Max export limit
            sort_field=sort_field,
            sort_order=sort_order
        )
    except Exception as e:
        logger.error(f"[EXPORT] Search failed: {e}")
        flash(f'Export error: {str(e)}', 'error')
        return redirect(url_for('search_events', case_id=case_id))
    
    # Extract fields
    events = [extract_event_fields(result['_source']) for result in results]
    
    # Generate CSV
    csv_content = generate_events_csv(events)
    
    # Create response with CSV
    response = make_response(csv_content)
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=case_{case_id}_events_export_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
    
    return response


@app.route('/case/<int:case_id>/search/event/<event_id>')
@login_required
def get_event_detail_route(case_id, event_id):
    """Get event detail (AJAX) with IOC list for highlighting"""
    from search_utils import get_event_detail, format_event_for_display
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'error': 'Case not found'}), 404
    
    # Get index name from query parameter
    index_name = request.args.get('index')
    if not index_name:
        return jsonify({'error': 'Index name required'}), 400
    
    # Retrieve event
    event = get_event_detail(opensearch_client, index_name, event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404
    
    # Format for display
    fields = format_event_for_display(event['_source'])
    
    # Get active IOCs for this case (for highlighting)
    iocs = db.session.query(IOC).filter_by(
        case_id=case_id,
        is_active=True
    ).all()
    
    ioc_values = [ioc.ioc_value.lower() for ioc in iocs]  # Lowercase for case-insensitive matching
    
    return jsonify({
        'event_id': event_id,
        'index': index_name,
        'fields': fields,
        'iocs': ioc_values  # Include IOCs for client-side highlighting
    })


@app.route('/case/<int:case_id>/search/tag', methods=['POST'])
@login_required
def tag_timeline_event(case_id):
    """Tag event for timeline"""
    from models import TimelineTag
    import json
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'error': 'Case not found'}), 404
    
    data = request.json
    event_id = data.get('event_id')
    index_name = data.get('index_name')
    event_data = data.get('event_data', {})
    notes = data.get('notes', '')
    tag_color = data.get('tag_color', 'blue')
    
    if not event_id or not index_name:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Check if already tagged
    existing = db.session.query(TimelineTag).filter_by(
        case_id=case_id,
        event_id=event_id,
        index_name=index_name
    ).first()
    
    if existing:
        return jsonify({'error': 'Event already tagged', 'tag_id': existing.id}), 400
    
    # Create tag
    tag = TimelineTag(
        case_id=case_id,
        user_id=current_user.id,
        event_id=event_id,
        index_name=index_name,
        event_data=json.dumps(event_data),
        tag_color=tag_color,
        notes=notes
    )
    db.session.add(tag)
    db.session.commit()
    
    logger.info(f"[TIMELINE TAG] User {current_user.id} tagged event {event_id} in case {case_id}")
    
    return jsonify({
        'success': True,
        'tag_id': tag.id,
        'created_at': tag.created_at.isoformat()
    })


@app.route('/case/<int:case_id>/search/untag', methods=['POST'])
@login_required
def untag_timeline_event(case_id):
    """Remove timeline tag"""
    from models import TimelineTag
    
    data = request.json
    event_id = data.get('event_id')
    index_name = data.get('index_name')
    
    tag = db.session.query(TimelineTag).filter_by(
        case_id=case_id,
        event_id=event_id,
        index_name=index_name
    ).first()
    
    if not tag:
        return jsonify({'error': 'Tag not found'}), 404
    
    # Only allow creator or admin to remove
    if tag.user_id != current_user.id and current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(tag)
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/case/<int:case_id>/search/columns', methods=['POST'])
@login_required
def update_search_columns(case_id):
    """Update search column configuration"""
    data = request.json
    columns = data.get('columns', [])
    
    # Save to session
    session[f'search_columns_{case_id}'] = columns
    
    return jsonify({'success': True, 'columns': columns})


@app.route('/case/<int:case_id>/search/history/<int:search_id>/favorite', methods=['POST'])
@login_required
def toggle_search_favorite(case_id, search_id):
    """Toggle search favorite status"""
    from models import SearchHistory
    
    search = db.session.get(SearchHistory, search_id)
    if not search or search.user_id != current_user.id:
        return jsonify({'error': 'Search not found'}), 404
    
    search.is_favorite = not search.is_favorite
    db.session.commit()
    
    return jsonify({'success': True, 'is_favorite': search.is_favorite})


@app.route('/case/<int:case_id>/search/add_ioc', methods=['POST'])
@login_required
def add_field_as_ioc(case_id):
    """Add event field value as IOC"""
    from models import IOC
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'error': 'Case not found'}), 404
    
    data = request.json
    ioc_value = data.get('value')
    ioc_type = data.get('type', 'other')
    threat_level = data.get('threat_level', 'medium')
    description = data.get('description', f'Added from search at {datetime.utcnow().isoformat()}')
    
    if not ioc_value:
        return jsonify({'error': 'IOC value required'}), 400
    
    if not ioc_type or ioc_type == '':
        return jsonify({'error': 'IOC type required'}), 400
    
    # Check if IOC already exists
    existing = db.session.query(IOC).filter_by(
        case_id=case_id,
        ioc_value=ioc_value
    ).first()
    
    if existing:
        return jsonify({'error': 'IOC already exists', 'ioc_id': existing.id}), 400
    
    # Create IOC
    ioc = IOC(
        case_id=case_id,
        ioc_value=ioc_value,
        ioc_type=ioc_type,
        threat_level=threat_level,
        description=description,
        created_by=current_user.id,
        is_active=True
    )
    db.session.add(ioc)
    db.session.commit()
    
    logger.info(f"[IOC] User {current_user.id} added IOC from search: {ioc_value}")
    
    return jsonify({
        'success': True,
        'ioc_id': ioc.id,
        'ioc_value': ioc_value
    })


@app.route('/sigma')
@login_required
def sigma_management():
    """SIGMA Management - View and manage SIGMA detection rules"""
    from sigma_utils import list_sigma_rules, get_sigma_stats
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search_query = request.args.get('search', '', type=str).strip()
    
    # Get SIGMA stats
    sigma_info = get_sigma_stats()
    
    # List rules with pagination
    rules_data = list_sigma_rules(page=page, per_page=per_page, search_query=search_query)
    
    return render_template('sigma_management.html', 
                         sigma_info=sigma_info,
                         rules=rules_data['rules'],
                         page=rules_data['page'],
                         per_page=rules_data['per_page'],
                         total=rules_data['total'],
                         total_pages=rules_data['total_pages'],
                         search_query=search_query)


@app.route('/sigma/update', methods=['POST'])
@login_required
def update_sigma():
    """Update SIGMA rules from GitHub"""
    from sigma_utils import update_sigma_rules
    
    result = update_sigma_rules()
    
    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(f"{result['message']}: {result['output'][:200]}", 'error')
    
    return redirect(url_for('sigma_management'))


@app.route('/files')
@login_required
def file_management():
    """Redirect to new global files page in blueprint"""
    return redirect(url_for('files.global_files'))


@app.route('/case/<int:case_id>/events')
@login_required
def event_search(case_id):
    """Event Search - Search and view events for a specific case"""
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get case files
    files = db.session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False
    ).all()
    
    # Calculate stats
    total_events = sum(f.event_count or 0 for f in files)
    sigma_violations = sum(f.violation_count or 0 for f in files)
    ioc_events = sum(f.ioc_event_count or 0 for f in files)
    indexed_files = len([f for f in files if f.indexing_status == 'Completed'])
    
    # Get recent SIGMA violations for this case (last 50)
    violations = db.session.query(SigmaViolation).join(CaseFile).filter(
        CaseFile.case_id == case_id,
        CaseFile.is_deleted == False
    ).order_by(SigmaViolation.id.desc()).limit(50).all()
    
    return render_template('event_search.html',
                         case=case,
                         total_events=total_events,
                         sigma_violations=sigma_violations,
                         ioc_events=ioc_events,
                         indexed_files=indexed_files,
                         violations=violations)


@app.route('/case/<int:case_id>/clear_files', methods=['POST'])
@login_required
def clear_all_files(case_id):
    """Clear all files for a case - removes from filesystem, database, and OpenSearch"""
    import os
    import shutil
    from utils import make_index_name
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all files for this case (including deleted/hidden)
    files = db.session.query(CaseFile).filter_by(case_id=case_id).all()
    
    deleted_count = 0
    errors = []
    
    for file in files:
        try:
            # 1. Delete from OpenSearch
            if file.opensearch_key:
                try:
                    # Generate the index name from case_id and original filename
                    index_name = make_index_name(case_id, file.original_filename)
                    
                    # Try to delete by opensearch_key
                    opensearch_client.delete_by_query(
                        index=index_name,
                        body={
                            "query": {
                                "term": {
                                    "opensearch_key.keyword": file.opensearch_key
                                }
                            }
                        },
                        conflicts='proceed',
                        ignore=[404]  # Ignore if index doesn't exist
                    )
                except Exception as e:
                    # Don't fail the whole operation if OpenSearch delete fails
                    errors.append(f"OpenSearch delete error for file {file.id}: {str(e)}")
            
            # 2. Delete physical file from filesystem
            if file.file_path and os.path.exists(file.file_path):
                try:
                    os.remove(file.file_path)
                except Exception as e:
                    errors.append(f"Filesystem delete error for {file.original_filename}: {str(e)}")
            
            # 3. Delete related records from database
            # Delete SIGMA violations
            db.session.query(SigmaViolation).filter_by(file_id=file.id).delete()
            
            # Delete IOC matches
            db.session.query(IOCMatch).filter_by(file_id=file.id).delete()
            
            # Delete the CaseFile record
            db.session.delete(file)
            
            deleted_count += 1
            
        except Exception as e:
            errors.append(f"Error deleting file {file.id}: {str(e)}")
    
    # Delete staging and archive directories for this case
    staging_dir = f'/opt/casescope/staging/{case_id}'
    archive_dir = f'/opt/casescope/archive/{case_id}'
    uploads_dir = f'/opt/casescope/uploads/{case_id}'
    
    for dir_path in [staging_dir, archive_dir, uploads_dir]:
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
            except Exception as e:
                errors.append(f"Error deleting directory {dir_path}: {str(e)}")
    
    # Commit all database changes
    try:
        db.session.commit()
        
        if errors:
            flash(f'Cleared {deleted_count} file(s) with {len(errors)} error(s)', 'warning')
            for error in errors[:5]:  # Show first 5 errors
                flash(error, 'error')
        else:
            flash(f'Successfully cleared all {deleted_count} file(s) from case', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Database error: {str(e)}', 'error')
    
    return redirect(url_for('view_case', case_id=case_id))


# @app.route('/case/<int:case_id>/files')
# @login_required
# def case_files(case_id):
#     """Dedicated Case Files Management Page with Pagination"""
#     case = db.session.get(Case, case_id)
#     if not case:
#         flash('Case not found', 'error')
#         return redirect(url_for('dashboard'))
#     
#     # Pagination parameters
#     page = request.args.get('page', 1, type=int)
#     per_page = request.args.get('per_page', 50, type=int)  # Default 50 files per page
#     
#     # Get files with pagination
#     files_query = db.session.query(CaseFile).filter_by(
#         case_id=case_id,
#         is_deleted=False,
#         is_hidden=False
#     ).order_by(CaseFile.uploaded_at.desc())
#     
#     # Use paginate for efficient pagination
#     pagination = files_query.paginate(page=page, per_page=per_page, error_out=False)
#     files = pagination.items
#     
#     # Calculate tile 1 stats: files and space (ALL files, not just current page)
#     all_files = files_query.all()
#     total_files = len(all_files)
#     total_space_bytes = sum(f.file_size or 0 for f in all_files)
#     total_space_gb = total_space_bytes / (1024**3)
#     
#     # File type breakdown (ALL files)
#     file_types = {}
#     for f in all_files:
#         ftype = f.file_type or 'UNKNOWN'
#         file_types[ftype] = file_types.get(ftype, 0) + 1
#     
#     # Calculate tile 2 stats: events (ALL files)
#     total_events = sum(f.event_count or 0 for f in all_files)
#     total_sigma_events = sum(f.violation_count or 0 for f in all_files)
#     total_ioc_events = sum(f.ioc_event_count or 0 for f in all_files)
#     
#     return render_template(
#         'case_files.html',
#         case=case,
#         files=files,
#         pagination=pagination,
#         total_files=total_files,
#         total_space_gb=total_space_gb,
#         file_types=file_types,
#         total_events=total_events,
#         total_sigma_events=total_sigma_events,
#         total_ioc_events=total_ioc_events
#     )
# 
# 
@app.route('/case/<int:case_id>/bulk_reindex', methods=['POST'])
@login_required
def bulk_reindex_route(case_id):
    """Re-index all files in a case"""
    from tasks import bulk_reindex
    from celery_health import check_workers_available
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Safety check: Ensure Celery workers are available
    workers_ok, worker_count, error_msg = check_workers_available(min_workers=1)
    if not workers_ok:
        flash(f'⚠️ Cannot start bulk operation: {error_msg}. Please check Celery workers.', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    file_count = db.session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False
    ).count()
    
    if file_count == 0:
        flash('No files found to re-index', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Queue re-index task (clears OpenSearch + DB metadata)
    bulk_reindex.delay(case_id)
    
    flash(f'✅ Re-indexing queued for {file_count} file(s) ({worker_count} worker(s) available). All data will be cleared and rebuilt.', 'success')
    return redirect(url_for('files.case_files', case_id=case_id))


@app.route('/case/<int:case_id>/bulk_rechainsaw', methods=['POST'])
@login_required
def bulk_rechainsaw_route(case_id):
    """Re-run SIGMA on all files in a case"""
    from tasks import bulk_rechainsaw
    from celery_health import check_workers_available
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Safety check: Ensure Celery workers are available
    workers_ok, worker_count, error_msg = check_workers_available(min_workers=1)
    if not workers_ok:
        flash(f'⚠️ Cannot start bulk operation: {error_msg}. Please check Celery workers.', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    file_count = db.session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_indexed=True
    ).count()
    
    if file_count == 0:
        flash('No indexed files found to re-SIGMA', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Queue re-SIGMA task (clears old violations)
    bulk_rechainsaw.delay(case_id)
    
    flash(f'✅ SIGMA re-processing queued for {file_count} file(s) ({worker_count} worker(s) available). Old violations will be cleared.', 'success')
    return redirect(url_for('files.case_files', case_id=case_id))


@app.route('/case/<int:case_id>/bulk_rehunt_iocs', methods=['POST'])
@login_required
def bulk_rehunt_iocs_route(case_id):
    """Re-hunt IOCs on all files in a case"""
    from tasks import bulk_rehunt
    from celery_health import check_workers_available
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Safety check: Ensure Celery workers are available
    workers_ok, worker_count, error_msg = check_workers_available(min_workers=1)
    if not workers_ok:
        flash(f'⚠️ Cannot start bulk operation: {error_msg}. Please check Celery workers.', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    file_count = db.session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_indexed=True
    ).count()
    
    if file_count == 0:
        flash('No indexed files found to re-hunt', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Queue re-hunt task (clears old matches)
    bulk_rehunt.delay(case_id)
    
    flash(f'✅ IOC re-hunting queued for {file_count} file(s) ({worker_count} worker(s) available). Old matches will be cleared.', 'success')
    return redirect(url_for('files.case_files', case_id=case_id))


@app.route('/case/<int:case_id>/bulk_delete_files', methods=['POST'])
@login_required
def bulk_delete_files(case_id):
    """Delete all files for a case - ADMIN ONLY"""
    import os
    import shutil
    from bulk_operations import (
        clear_case_opensearch_indices,
        clear_case_sigma_violations,
        clear_case_ioc_matches,
        get_case_files
    )
    
    # Admin check
    if current_user.role != 'admin':
        flash('Only administrators can delete all files', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all files for this case (including deleted)
    files = get_case_files(db, case_id, include_deleted=True)
    
    if not files:
        flash('No files to delete', 'info')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    deleted_count = 0
    errors = []
    
    # 1. Delete ALL OpenSearch indices for this case (entire indices, not just documents)
    try:
        indices_deleted = clear_case_opensearch_indices(opensearch_client, case_id, files)
        logger.info(f"[BULK DELETE] Deleted {indices_deleted} OpenSearch indices for case {case_id}")
    except Exception as e:
        errors.append(f"OpenSearch error: {str(e)}")
    
    # 2. Clear all SIGMA violations and IOC matches for this case
    try:
        sigma_deleted = clear_case_sigma_violations(db, case_id)
        ioc_deleted = clear_case_ioc_matches(db, case_id)
        logger.info(f"[BULK DELETE] Cleared {sigma_deleted} SIGMA violations and {ioc_deleted} IOC matches")
    except Exception as e:
        errors.append(f"Database cleanup error: {str(e)}")
    
    # 3. Delete physical files from filesystem
    for file in files:
        try:
            if file.file_path and os.path.exists(file.file_path):
                os.remove(file.file_path)
                logger.debug(f"[BULK DELETE] Deleted file: {file.file_path}")
        except Exception as e:
            errors.append(f"Filesystem error for {file.original_filename}: {str(e)}")
    
    # 4. Delete all CaseFile records from database
    try:
        for file in files:
            db.session.delete(file)
        deleted_count = len(files)
    except Exception as e:
        errors.append(f"Database delete error: {str(e)}")
    
    # 5. Delete staging and archive directories for this case
    staging_dir = f'/opt/casescope/staging/{case_id}'
    archive_dir = f'/opt/casescope/archive/{case_id}'
    uploads_dir = f'/opt/casescope/uploads/{case_id}'
    
    for dir_path in [staging_dir, archive_dir, uploads_dir]:
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
                logger.info(f"[BULK DELETE] Deleted directory: {dir_path}")
            except Exception as e:
                errors.append(f"Directory delete error: {str(e)}")
    
    # 6. Commit all database changes
    try:
        db.session.commit()
        logger.info(f"[BULK DELETE] Completed: deleted {deleted_count} file(s)")
        
        if errors:
            flash(f'Deleted {deleted_count} file(s) with {len(errors)} error(s)', 'warning')
            for error in errors[:5]:
                flash(error, 'error')
        else:
            flash(f'✓ Successfully deleted all {deleted_count} file(s) and cleared all data', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"[BULK DELETE] Database error: {str(e)}")
        flash(f'Database error: {str(e)}', 'error')
    
    return redirect(url_for('files.case_files', case_id=case_id))


@app.route('/case/<int:case_id>/rehunt_iocs', methods=['POST'])
@login_required
def rehunt_iocs(case_id):
    """Re-run IOC hunting on all completed files in a case (reusable from multiple pages)"""
    from tasks import bulk_rehunt
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all indexed files for this case
    file_count = db.session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_indexed=True
    ).count()
    
    # Determine redirect based on referer or query param
    redirect_to = request.args.get('redirect_to', request.form.get('redirect_to'))
    if not redirect_to:
        # Check referer to determine where user came from
        referer = request.referrer or ''
        if '/ioc' in referer:
            redirect_to = 'ioc_management'
        elif '/files' in referer:
            redirect_to = 'case_files'
        else:
            redirect_to = 'case_dashboard'
    
    if file_count == 0:
        flash('No indexed files found to re-hunt', 'warning')
        if redirect_to == 'ioc_management':
            return redirect(url_for('ioc.ioc_management', case_id=case_id))
        elif redirect_to == 'case_files':
            return redirect(url_for('files.case_files', case_id=case_id))
        else:
            return redirect(url_for('view_case', case_id=case_id))
    
    # Queue re-hunt task (task handles clearing)
    bulk_rehunt.delay(case_id)
    
    flash(f'IOC re-hunting queued for {file_count} file(s). Old matches will be cleared.', 'success')
    
    # Redirect back to where they came from
    if redirect_to == 'ioc_management':
        return redirect(url_for('ioc.ioc_management', case_id=case_id))
    elif redirect_to == 'case_files':
        return redirect(url_for('files.case_files', case_id=case_id))
    else:
        return redirect(url_for('view_case', case_id=case_id))


@app.route('/case/<int:case_id>/file/<int:file_id>/rehunt_iocs', methods=['POST'])
@login_required
def rehunt_single_file(case_id, file_id):
    """Re-run IOC hunting on a single file (reusable from multiple pages)"""
    from tasks import single_file_rehunt
    
    case_file = db.session.get(CaseFile, file_id)
    
    # Determine redirect based on referer or query param
    redirect_to = request.args.get('redirect_to', request.form.get('redirect_to'))
    if not redirect_to:
        # Check referer to determine where user came from
        referer = request.referrer or ''
        if '/ioc' in referer:
            redirect_to = 'ioc_management'
        elif '/files' in referer:
            redirect_to = 'case_files'
        else:
            redirect_to = 'case_dashboard'
    
    if not case_file or case_file.case_id != case_id:
        flash('File not found', 'error')
        if redirect_to == 'ioc_management':
            return redirect(url_for('ioc.ioc_management', case_id=case_id))
        elif redirect_to == 'case_files':
            return redirect(url_for('files.case_files', case_id=case_id))
        else:
            return redirect(url_for('view_case', case_id=case_id))
    
    if not case_file.is_indexed:
        flash('File must be indexed before IOC hunting', 'warning')
        if redirect_to == 'ioc_management':
            return redirect(url_for('ioc.ioc_management', case_id=case_id))
        elif redirect_to == 'case_files':
            return redirect(url_for('files.case_files', case_id=case_id))
        else:
            return redirect(url_for('view_case', case_id=case_id))
    
    # Queue single file re-hunt (task handles clearing)
    single_file_rehunt.delay(file_id)
    
    flash(f'IOC re-hunting queued for "{case_file.original_filename}". Old matches will be cleared.', 'success')
    
    # Redirect back to where they came from
    if redirect_to == 'ioc_management':
        return redirect(url_for('ioc.ioc_management', case_id=case_id))
    elif redirect_to == 'case_files':
        return redirect(url_for('files.case_files', case_id=case_id))
    else:
        return redirect(url_for('view_case', case_id=case_id))


# OLD INLINE TEMPLATE - KEEPING FOR REFERENCE, CAN BE DELETED
def _old_view_case_template():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ case.name }} - CaseScope 2026</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: Arial; background: #1a1a1a; color: #fff; }
            .header { background: #2a2a2a; padding: 20px; border-bottom: 2px solid #0066cc; display: flex; justify-content: space-between; align-items: center; }
            .header h1 { font-size: 24px; }
            .container { padding: 30px; max-width: 1400px; margin: 0 auto; }
            .case-info { background: #2a2a2a; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .case-info h2 { margin-bottom: 15px; }
            .case-info p { color: #999; margin: 5px 0; }
            .section { background: #2a2a2a; padding: 20px; border-radius: 8px; }
            table { width: 100%; border-collapse: collapse; }
            th { background: #333; padding: 12px; text-align: left; font-weight: 600; }
            td { padding: 12px; border-bottom: 1px solid #333; }
            tr:hover { background: #333; }
            .btn { background: #0066cc; color: white; padding: 8px 16px; border-radius: 5px; text-decoration: none; display: inline-block; }
            .btn:hover { background: #0052a3; }
            .status { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
            .status-completed { background: #00cc66; color: #000; }
            .status-indexing { background: #ff9800; color: #000; }
            .status-queued { background: #999; color: #000; }
            .status-failed { background: #ff4444; color: #fff; }
            .status-sigma { background: #9c27b0; color: #fff; }
            .status-ioc { background: #2196f3; color: #fff; }
            .pulsing { animation: pulse 2s ease-in-out infinite; }
            @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔍 {{ case.name }}</h1>
            <div>
                <a href="{{ url_for('upload_files', case_id=case.id) }}" class="btn">+ Upload Files</a>
                <a href="{{ url_for('dashboard') }}" class="btn" style="background: #444;">← Back</a>
            </div>
        </div>
        
        <div class="container">
            <div class="case-info">
                <h2>Case Information</h2>
                <p><strong>Company:</strong> {{ case.company or 'N/A' }}</p>
                <p><strong>Description:</strong> {{ case.description or 'No description' }}</p>
                <p><strong>Created:</strong> {{ case.created_at.strftime('%Y-%m-%d %H:%M:%S') }}</p>
                <p><strong>Total Files:</strong> {{ files|length }}</p>
            </div>
            
            <div class="section">
                <h2 style="margin-bottom: 20px;">Files</h2>
                {% if files %}
                <table>
                    <thead>
                        <tr>
                            <th>Filename</th>
                            <th>Status</th>
                            <th>Events</th>
                            <th>SIGMA</th>
                            <th>IOCs</th>
                            <th>Uploaded</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for file in files %}
                        <tr data-file-id="{{ file.id }}">
                            <td><strong>{{ file.original_filename }}</strong></td>
                            <td class="status-cell">
                                {% if file.indexing_status == 'Completed' %}
                                    <span class="status status-completed">Completed</span>
                                {% elif file.indexing_status == 'Indexing' %}
                                    <span class="status status-indexing pulsing">Indexing</span>
                                {% elif file.indexing_status == 'SIGMA Testing' %}
                                    <span class="status status-sigma pulsing">SIGMA Testing</span>
                                {% elif file.indexing_status == 'IOC Hunting' %}
                                    <span class="status status-ioc pulsing">IOC Hunting</span>
                                {% elif file.indexing_status == 'Queued' %}
                                    <span class="status status-queued">Queued</span>
                                {% else %}
                                    <span class="status status-failed">{{ file.indexing_status }}</span>
                                {% endif %}
                            </td>
                            <td class="event-count">{{ file.event_count or 0 }}</td>
                            <td class="sigma-count">{{ file.violation_count or 0 }}</td>
                            <td class="ioc-count">{{ file.ioc_event_count or 0 }}</td>
                            <td>{{ file.uploaded_at.strftime('%Y-%m-%d %H:%M') }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="color: #999; text-align: center; padding: 40px;">No files uploaded yet.</p>
                {% endif %}
            </div>
        </div>
        
        <script>
            // Auto-refresh file statuses every 3 seconds
            function updateStatuses() {
                fetch('/case/{{ case.id }}/status')
                    .then(response => response.json())
                    .then(data => {
                        data.files.forEach(file => {
                            const row = document.querySelector(`tr[data-file-id="${file.id}"]`);
                            if (!row) return;
                            
                            // Update status
                            const statusCell = row.querySelector('.status-cell');
                            const currentStatus = statusCell.textContent.trim();
                            
                            if (currentStatus !== file.status) {
                                let statusClass = 'status-failed';
                                let pulsing = '';
                                
                                if (file.status === 'Completed') {
                                    statusClass = 'status-completed';
                                } else if (file.status === 'Indexing') {
                                    statusClass = 'status-indexing';
                                    pulsing = ' pulsing';
                                } else if (file.status === 'SIGMA Testing') {
                                    statusClass = 'status-sigma';
                                    pulsing = ' pulsing';
                                } else if (file.status === 'IOC Hunting') {
                                    statusClass = 'status-ioc';
                                    pulsing = ' pulsing';
                                } else if (file.status === 'Queued') {
                                    statusClass = 'status-queued';
                                }
                                
                                statusCell.innerHTML = `<span class="status ${statusClass}${pulsing}">${file.status}</span>`;
                            }
                            
                            // Update counts
                            row.querySelector('.event-count').textContent = file.event_count;
                            row.querySelector('.sigma-count').textContent = file.violation_count;
                            row.querySelector('.ioc-count').textContent = file.ioc_event_count;
                        });
                    })
                    .catch(err => console.error('Status update failed:', err));
            }
            
            // Update every 3 seconds
            setInterval(updateStatuses, 3000);
            
            // Initial update after 1 second
            setTimeout(updateStatuses, 1000);
        </script>
    </body>
    </html>
    ''', case=case, files=files)


# ============================================================================
# FILE UPLOAD
# ============================================================================

@app.route('/case/<int:case_id>/upload', methods=['GET', 'POST'])
@login_required
def upload_files(case_id):
    """Upload files to case"""
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        from upload_integration import handle_http_upload_v96
        
        # Get uploaded files from request
        uploaded_files = request.files.getlist('files')
        if not uploaded_files:
            flash('No files selected', 'error')
            return redirect(url_for('view_case', case_id=case_id))
        
        response = handle_http_upload_v96(
            app=app,
            db=db,
            Case=Case,
            CaseFile=CaseFile,
            SkippedFile=SkippedFile,
            celery_app=celery_app,
            current_user=current_user,
            uploaded_files=uploaded_files,
            case_id=case_id
        )
        
        # handle_http_upload_v96 returns a JSON response tuple
        result_data = response[0].get_json() if isinstance(response, tuple) else response.get_json()
        
        if result_data.get('success'):
            stats = result_data.get('stats', {})
            flash(f"Upload complete: {stats.get('files_queued', 0)} files queued for processing", 'success')
        else:
            flash(f"Upload failed: {result_data.get('error', 'Unknown error')}", 'error')
        
        return redirect(url_for('view_case', case_id=case_id))
    
    return render_template('upload_files.html', case=case)

# OLD UPLOAD TEMPLATE - DELETED, NOW USING templates/upload_files.html
def _old_upload_template():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Upload Files - {{ case.name }}</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; background: #1a1a1a; color: #fff; }
            .header { background: #2a2a2a; padding: 20px; border-bottom: 2px solid #0066cc; }
            .container { padding: 30px; max-width: 900px; margin: 0 auto; }
            .upload-box { background: #2a2a2a; padding: 40px; border-radius: 8px; border: 2px dashed #444; }
            input[type="file"] { display: none; }
            .btn { background: #0066cc; color: white; padding: 12px 24px; border-radius: 5px; border: none; cursor: pointer; font-size: 16px; display: inline-block; margin: 10px; transition: all 0.3s; }
            .btn:hover { background: #0052a3; }
            .btn:disabled { background: #444; cursor: not-allowed; }
            .btn-secondary { background: #444; }
            .btn-secondary:hover { background: #555; }
            .upload-info { color: #999; margin: 20px 0; font-size: 14px; }
            .file-list { margin-top: 30px; text-align: left; }
            .file-item { background: #333; padding: 15px; border-radius: 5px; margin-bottom: 10px; }
            .file-name { font-weight: bold; margin-bottom: 5px; word-break: break-all; }
            .file-size { color: #999; font-size: 12px; margin-bottom: 8px; }
            .progress-bar { background: #222; height: 24px; border-radius: 4px; overflow: hidden; position: relative; }
            .progress-fill { background: linear-gradient(90deg, #0066cc, #0088ff); height: 100%; transition: width 0.3s; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold; }
            .progress-text { position: absolute; width: 100%; text-align: center; line-height: 24px; font-size: 12px; z-index: 1; }
            .status { display: inline-block; padding: 4px 8px; border-radius: 3px; font-size: 11px; margin-left: 10px; }
            .status-uploading { background: #0066cc; }
            .status-success { background: #28a745; }
            .status-error { background: #dc3545; }
            .upload-stats { display: flex; gap: 20px; justify-content: center; margin-top: 20px; padding: 15px; background: #333; border-radius: 5px; }
            .stat { text-align: center; }
            .stat-value { font-size: 24px; font-weight: bold; color: #0066cc; }
            .stat-label { font-size: 12px; color: #999; margin-top: 5px; }
            .alert { padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            .alert-info { background: #1f3a5f; border-left: 4px solid #0066cc; }
            .alert-warning { background: #5f471f; border-left: 4px solid #ffaa00; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔍 Upload Files - {{ case.name }}</h1>
        </div>
        
        <div class="container">
            <div id="chunkedUploadSection">
            <div class="upload-box">
                    <h2 style="margin-bottom: 20px;">⚡ Upload Files</h2>
                    <p class="upload-info">
                        Supports: EVTX, JSON, NDJSON, ZIP<br>
                        <strong>Features:</strong> Real-time progress, chunked upload for large files
                    </p>
                    
                    <input type="file" id="chunkedFileInput" multiple accept=".evtx,.json,.ndjson,.zip">
                    <label for="chunkedFileInput" class="btn">Choose Files</label>
                    <button onclick="startChunkedUpload()" class="btn" id="startUploadBtn" disabled>Start Upload</button>
                    <a href="{{ url_for('view_case', case_id=case.id) }}" class="btn btn-secondary">Cancel</a>
                </div>

                <div id="uploadStats" class="upload-stats" style="display: none;">
                    <div class="stat">
                        <div class="stat-value" id="filesCompleted">0</div>
                        <div class="stat-label">Files Completed</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="totalSize">0 MB</div>
                        <div class="stat-label">Total Size</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="uploadSpeed">0 MB/s</div>
                        <div class="stat-label">Upload Speed</div>
                    </div>
                </div>

                <div id="fileList" class="file-list"></div>
            </div>
        </div>
        
        <script>
            // Chunked upload
            let selectedFiles = [];
            let uploadQueue = [];
            let currentUploads = 0;
            const MAX_CONCURRENT = 2;
            const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB chunks
            let startTime = Date.now();

            document.getElementById('chunkedFileInput').addEventListener('change', function(e) {
                selectedFiles = Array.from(e.target.files);
                displayFileList();
                document.getElementById('startUploadBtn').disabled = selectedFiles.length === 0;
            });

            function displayFileList() {
                const fileList = document.getElementById('fileList');
                fileList.innerHTML = '';
                
                selectedFiles.forEach((file, index) => {
                    const div = document.createElement('div');
                    div.className = 'file-item';
                    div.id = `file-${index}`;
                    div.innerHTML = `
                        <div class="file-name">📄 ${file.name} <span class="status status-uploading" id="status-${index}">Queued</span></div>
                        <div class="file-size">${formatSize(file.size)}</div>
                        <div class="progress-bar">
                            <div class="progress-text" id="progress-text-${index}">0%</div>
                            <div class="progress-fill" id="progress-${index}" style="width: 0%;"></div>
                        </div>
                    `;
                    fileList.appendChild(div);
                });

                // Show stats
                document.getElementById('uploadStats').style.display = 'flex';
                const totalSize = selectedFiles.reduce((sum, f) => sum + f.size, 0);
                document.getElementById('totalSize').textContent = formatSize(totalSize);
            }

            function formatSize(bytes) {
                if (bytes < 1024) return bytes + ' B';
                if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
                if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
                return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
            }

            async function startChunkedUpload() {
                document.getElementById('startUploadBtn').disabled = true;
                startTime = Date.now();
                uploadQueue = selectedFiles.map((file, index) => ({ file, index }));
                processQueue();
            }

            function processQueue() {
                while (uploadQueue.length > 0 && currentUploads < MAX_CONCURRENT) {
                    const item = uploadQueue.shift();
                    currentUploads++;
                    uploadFileInChunks(item.file, item.index);
                }
            }

            async function uploadFileInChunks(file, fileIndex) {
                const uploadId = Date.now() + '-' + Math.random().toString(36).substr(2, 9);
                const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
                
                document.getElementById(`status-${fileIndex}`).textContent = 'Uploading';
                
                try {
                    // Upload chunks
                    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
                        const start = chunkIndex * CHUNK_SIZE;
                        const end = Math.min(start + CHUNK_SIZE, file.size);
                        const chunk = file.slice(start, end);
                        
                        const formData = new FormData();
                        formData.append('chunk', chunk);
                        formData.append('upload_id', uploadId);
                        formData.append('chunk_index', chunkIndex);
                        formData.append('total_chunks', totalChunks);
                        formData.append('filename', file.name);
                        
                        const response = await fetch('/case/{{ case.id }}/upload_chunk', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (!response.ok) throw new Error('Chunk upload failed');
                        
                        const progress = ((chunkIndex + 1) / totalChunks) * 100;
                        updateProgress(fileIndex, progress);
                    }
                    
                    // Finalize upload
                    document.getElementById(`status-${fileIndex}`).textContent = 'Finalizing';
                    const finalizeResponse = await fetch('/case/{{ case.id }}/finalize_upload', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ upload_id: uploadId, filename: file.name })
                    });
                    
                    if (!finalizeResponse.ok) throw new Error('Finalization failed');
                    
                    document.getElementById(`status-${fileIndex}`).textContent = 'Complete';
                    document.getElementById(`status-${fileIndex}`).className = 'status status-success';
                    
                    const completed = parseInt(document.getElementById('filesCompleted').textContent) + 1;
                    document.getElementById('filesCompleted').textContent = completed;
                    
                    updateSpeed();
                    
                } catch (error) {
                    console.error('Upload error:', error);
                    document.getElementById(`status-${fileIndex}`).textContent = 'Failed';
                    document.getElementById(`status-${fileIndex}`).className = 'status status-error';
                }
                
                currentUploads--;
                
                if (uploadQueue.length === 0 && currentUploads === 0) {
                    setTimeout(() => {
                        window.location.href = '/case/{{ case.id }}';
                    }, 2000);
                } else {
                    processQueue();
                }
            }

            function updateProgress(fileIndex, progress) {
                const progressBar = document.getElementById(`progress-${fileIndex}`);
                const progressText = document.getElementById(`progress-text-${fileIndex}`);
                progressBar.style.width = progress + '%';
                progressText.textContent = Math.round(progress) + '%';
            }

            function updateSpeed() {
                const elapsed = (Date.now() - startTime) / 1000;
                const completed = parseInt(document.getElementById('filesCompleted').textContent);
                const totalSize = selectedFiles.slice(0, completed).reduce((sum, f) => sum + f.size, 0);
                const speed = totalSize / elapsed / (1024 * 1024);
                document.getElementById('uploadSpeed').textContent = speed.toFixed(2) + ' MB/s';
            }
        </script>
    </body>
    </html>
    ''', case=case)


@app.route('/case/<int:case_id>/upload_chunk', methods=['POST'])
@login_required
def upload_chunk(case_id):
    """Receive individual file chunks for chunked uploads"""
    try:
        # Verify case exists
        case = db.session.get(Case, case_id)
        if not case:
            return jsonify({'success': False, 'error': 'Case not found'}), 404
        
        # Get chunk metadata
        upload_id = request.form.get('upload_id')
        chunk_index = request.form.get('chunk_index')
        total_chunks = request.form.get('total_chunks')
        filename = request.form.get('filename')
        
        if not all([upload_id, chunk_index, total_chunks, filename]):
            return jsonify({'success': False, 'error': 'Missing chunk metadata'}), 400
        
        # Get chunk data
        chunk_file = request.files.get('chunk')
        if not chunk_file:
            return jsonify({'success': False, 'error': 'No chunk data'}), 400
        
        # Create chunks directory
        chunks_dir = os.path.join('/opt/casescope/staging', f'chunks_{upload_id}')
        os.makedirs(chunks_dir, exist_ok=True)
        
        # Save chunk
        chunk_path = os.path.join(chunks_dir, f'{upload_id}_{chunk_index}')
        chunk_file.save(chunk_path)
        
        logger.info(f"[Chunk Upload] Saved chunk {chunk_index}/{total_chunks} for {filename}")
        
        return jsonify({
            'success': True,
            'chunk_index': int(chunk_index),
            'message': f'Chunk {chunk_index} received'
        })
        
    except Exception as e:
        logger.error(f"[Chunk Upload] Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/case/<int:case_id>/finalize_upload', methods=['POST'])
@login_required
def finalize_upload(case_id):
    """Finalize chunked upload - assemble chunks and process"""
    try:
        data = request.get_json()
        upload_id = data.get('upload_id')
        filename = data.get('filename')
        
        if not all([upload_id, filename]):
            return jsonify({'success': False, 'error': 'Missing upload metadata'}), 400
        
        chunks_folder = os.path.join('/opt/casescope/staging', f'chunks_{upload_id}')
        
        if not os.path.exists(chunks_folder):
            return jsonify({'success': False, 'error': 'Upload chunks not found'}), 404
        
        # Use the existing chunked upload handler
        from upload_integration import handle_chunked_upload_finalize_v96
        
        response = handle_chunked_upload_finalize_v96(
            app=app,
            db=db,
            Case=Case,
            CaseFile=CaseFile,
            SkippedFile=SkippedFile,
            celery_app=celery_app,
            current_user=current_user,
            upload_id=upload_id,
            filename=filename,
            case_id=case_id,
            chunks_folder=chunks_folder
        )
        
        return response
        
    except Exception as e:
        logger.error(f"[Finalize Upload] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

@app.cli.command('init-db')
def init_db():
    """Initialize database and create default admin user"""
    db.create_all()
    
    # Create default admin user
    admin = db.session.query(User).filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@casescope.local',
            password_hash=generate_password_hash('admin'),
            full_name='Administrator',
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print("✓ Database initialized")
        print("✓ Default admin user created (username: admin, password: admin)")
    else:
        print("✓ Database already initialized")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

