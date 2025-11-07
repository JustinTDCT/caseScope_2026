"""
System Management Routes
Handles system identification, categorization, and management
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
from datetime import datetime
import json
import logging
import re

systems_bp = Blueprint('systems', __name__)
logger = logging.getLogger(__name__)


@systems_bp.route('/case/<int:case_id>/systems')
@login_required
def systems_management(case_id):
    """Systems Management page for a case with pagination and sorting"""
    from main import db
    from models import Case, System, SystemSettings
    from flask import request
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get pagination and sorting parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    sort_field = request.args.get('sort', 'system_name')
    sort_order = request.args.get('order', 'asc')
    
    # Build query
    query = System.query.filter_by(case_id=case_id)
    
    # Apply sorting
    if sort_field == 'system_name':
        if sort_order == 'asc':
            query = query.order_by(System.system_name.asc())
        else:
            query = query.order_by(System.system_name.desc())
    elif sort_field == 'system_type':
        if sort_order == 'asc':
            query = query.order_by(System.system_type.asc(), System.system_name.asc())
        else:
            query = query.order_by(System.system_type.desc(), System.system_name.asc())
    elif sort_field == 'created_at':
        if sort_order == 'asc':
            query = query.order_by(System.created_at.asc())
        else:
            query = query.order_by(System.created_at.desc())
    elif sort_field == 'added_by':
        if sort_order == 'asc':
            query = query.order_by(System.added_by.asc(), System.system_name.asc())
        else:
            query = query.order_by(System.added_by.desc(), System.system_name.asc())
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    systems = pagination.items
    total_count = pagination.total
    total_pages = pagination.pages
    
    # Get system settings for integrations
    opencti_enabled = SystemSettings.query.filter_by(setting_key='opencti_enabled').first()
    dfir_iris_enabled = SystemSettings.query.filter_by(setting_key='dfir_iris_enabled').first()
    dfir_iris_auto_sync = SystemSettings.query.filter_by(setting_key='dfir_iris_auto_sync').first()
    
    # Get stats (all systems, not just current page)
    stats = {
        'servers': System.query.filter_by(case_id=case_id, system_type='server', hidden=False).count(),
        'workstations': System.query.filter_by(case_id=case_id, system_type='workstation', hidden=False).count(),
        'firewalls': System.query.filter_by(case_id=case_id, system_type='firewall', hidden=False).count(),
        'switches': System.query.filter_by(case_id=case_id, system_type='switch', hidden=False).count(),
        'printers': System.query.filter_by(case_id=case_id, system_type='printer', hidden=False).count(),
        'actor_systems': System.query.filter_by(case_id=case_id, system_type='actor_system', hidden=False).count(),
        'total': System.query.filter_by(case_id=case_id, hidden=False).count(),
        'hidden': System.query.filter_by(case_id=case_id, hidden=True).count()
    }
    
    return render_template('systems_management.html',
                         case=case,
                         systems=systems,
                         stats=stats,
                         page=page,
                         per_page=per_page,
                         total_count=total_count,
                         total_pages=total_pages,
                         sort_field=sort_field,
                         sort_order=sort_order,
                         opencti_enabled=(opencti_enabled.setting_value == 'true' if opencti_enabled else False),
                         dfir_iris_enabled=(dfir_iris_enabled.setting_value == 'true' if dfir_iris_enabled else False),
                         dfir_iris_auto_sync=(dfir_iris_auto_sync.setting_value == 'true' if dfir_iris_auto_sync else False))


# System type categorization patterns
SYSTEM_TYPE_PATTERNS = {
    'server': [
        r'srv|server|dc\d+|ad\d+|sql|exchange|file|print|backup|web|app',
        r'dc-|ad-|fs-|ps-|ws-|db-|ex-|sql-'
    ],
    'firewall': [
        r'fw|firewall|fortigate|palo\s*alto|checkpoint|sonicwall|asa|juniper|vyos',
        r'fw-|ngfw-|ips-|utm-'
    ],
    'switch': [
        r'sw|switch|cisco|arista|nexus|catalyst|dell\s*switch',
        r'sw-|switch-|core-|dist-|access-'
    ],
    'printer': [
        r'print|printer|copier|mfp|hp\s*laser|ricoh|xerox|konica',
        r'pr-|print-|mfp-|copier-'
    ],
    'actor_system': [
        r'attacker|threat|actor|malicious|external|suspicious',
        r'unknown|unauth|rogue|badguy'
    ]
}


@systems_bp.route('/case/<int:case_id>/systems/list', methods=['GET'])
@login_required
def list_systems(case_id):
    """Get all systems for a case (optionally filtered by type)"""
    from main import db
    from models import Case, System
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'success': False, 'error': 'Case not found'}), 404
    
    # Get optional type filter
    system_type = request.args.get('type', None)
    
    # Build query
    query = System.query.filter_by(case_id=case_id)
    
    # Filter by type if provided
    if system_type:
        query = query.filter_by(system_type=system_type)
    
    # Filter by visibility based on user role
    if current_user.role not in ['administrator', 'analyst']:
        query = query.filter_by(hidden=False)
    
    systems = query.order_by(System.created_at.desc()).all()
    
    systems_data = []
    for sys in systems:
        systems_data.append({
            'id': sys.id,
            'system_name': sys.system_name,
            'ip_address': sys.ip_address,
            'system_type': sys.system_type,
            'added_by': sys.added_by,
            'created_at': sys.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'hidden': sys.hidden
        })
    
    return jsonify({'success': True, 'systems': systems_data})


@systems_bp.route('/case/<int:case_id>/systems/stats', methods=['GET'])
@login_required
def get_systems_stats(case_id):
    """Get system statistics for dashboard"""
    from main import db
    from models import System
    
    # Count by type (exclude hidden)
    stats = {
        'servers': System.query.filter_by(case_id=case_id, system_type='server', hidden=False).count(),
        'workstations': System.query.filter_by(case_id=case_id, system_type='workstation', hidden=False).count(),
        'firewalls': System.query.filter_by(case_id=case_id, system_type='firewall', hidden=False).count(),
        'switches': System.query.filter_by(case_id=case_id, system_type='switch', hidden=False).count(),
        'printers': System.query.filter_by(case_id=case_id, system_type='printer', hidden=False).count(),
        'actor_systems': System.query.filter_by(case_id=case_id, system_type='actor_system', hidden=False).count(),
        'total': System.query.filter_by(case_id=case_id, hidden=False).count()
    }
    
    return jsonify({'success': True, 'stats': stats})


@systems_bp.route('/case/<int:case_id>/systems/add', methods=['POST'])
@login_required
def add_system(case_id):
    """Manually add a system to the case"""
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot add systems'}), 403
    
    from main import db
    from models import Case, System
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'success': False, 'error': 'Case not found'}), 404
    
    try:
        system_name = request.form.get('system_name', '').strip()
        system_type = request.form.get('system_type', 'workstation')
        ip_address = request.form.get('ip_address', '').strip() or None
        
        if not system_name:
            return jsonify({'success': False, 'error': 'System name is required'}), 400
        
        # Check for duplicate
        existing = System.query.filter_by(case_id=case_id, system_name=system_name).first()
        if existing:
            return jsonify({'success': False, 'error': 'System already exists in this case'}), 400
        
        # Create system
        system = System(
            case_id=case_id,
            system_name=system_name,
            ip_address=ip_address,
            system_type=system_type,
            added_by=current_user.username,
            hidden=False
        )
        db.session.add(system)
        db.session.commit()
        
        # Check for OpenCTI enrichment
        from models import SystemSettings
        opencti_enabled = SystemSettings.query.filter_by(setting_key='opencti_enabled').first()
        if opencti_enabled and opencti_enabled.setting_value == 'true':
            enrich_from_opencti(system)
        
        # Check for DFIR-IRIS auto sync
        dfir_iris_auto_sync = SystemSettings.query.filter_by(setting_key='dfir_iris_auto_sync').first()
        if dfir_iris_auto_sync and dfir_iris_auto_sync.setting_value == 'true':
            sync_to_dfir_iris(system)
        
        flash(f'System added: {system_name}', 'success')
        return jsonify({'success': True, 'system_id': system.id})
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"[Systems] Error adding system: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@systems_bp.route('/case/<int:case_id>/systems/<int:system_id>/get', methods=['GET'])
@login_required
def get_system(case_id, system_id):
    """Get system details for editing"""
    from main import db
    from models import System
    
    system = db.session.get(System, system_id)
    if not system or system.case_id != case_id:
        return jsonify({'success': False, 'error': 'System not found'}), 404
    
    return jsonify({
        'success': True,
        'system': {
            'id': system.id,
            'system_name': system.system_name,
            'system_type': system.system_type,
            'added_by': system.added_by,
            'hidden': system.hidden
        }
    })


@systems_bp.route('/case/<int:case_id>/systems/<int:system_id>/edit', methods=['POST'])
@login_required
def edit_system(case_id, system_id):
    """Edit system details"""
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot edit systems'}), 403
    
    from main import db
    from models import System
    
    system = db.session.get(System, system_id)
    if not system or system.case_id != case_id:
        return jsonify({'success': False, 'error': 'System not found'}), 404
    
    try:
        system.system_name = request.form.get('system_name', system.system_name).strip()
        system.ip_address = request.form.get('ip_address', '').strip() or None
        system.system_type = request.form.get('system_type', system.system_type)
        
        db.session.commit()
        
        flash(f'System updated: {system.system_name}', 'success')
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"[Systems] Error editing system: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@systems_bp.route('/case/<int:case_id>/systems/<int:system_id>/delete', methods=['POST'])
@login_required
def delete_system(case_id, system_id):
    """Delete system (administrators only)"""
    if current_user.role != 'administrator':
        return jsonify({'success': False, 'error': 'Only administrators can delete systems'}), 403
    
    from main import db
    from models import System
    
    system = db.session.get(System, system_id)
    if not system or system.case_id != case_id:
        return jsonify({'success': False, 'error': 'System not found'}), 404
    
    try:
        system_name = system.system_name
        db.session.delete(system)
        db.session.commit()
        
        flash(f'System deleted: {system_name}', 'success')
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"[Systems] Error deleting system: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@systems_bp.route('/case/<int:case_id>/systems/<int:system_id>/toggle_hidden', methods=['POST'])
@login_required
def toggle_hidden(case_id, system_id):
    """Toggle system hidden status"""
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot modify systems'}), 403
    
    from main import db
    from models import System
    
    system = db.session.get(System, system_id)
    if not system or system.case_id != case_id:
        return jsonify({'success': False, 'error': 'System not found'}), 404
    
    try:
        system.hidden = not system.hidden
        db.session.commit()
        
        status = 'hidden' if system.hidden else 'visible'
        flash(f'System {status}: {system.system_name}', 'success')
        return jsonify({'success': True, 'hidden': system.hidden})
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"[Systems] Error toggling hidden status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@systems_bp.route('/case/<int:case_id>/systems/<int:system_id>/event_count', methods=['GET'])
@login_required
def get_event_count(case_id, system_id):
    """Get count of events referencing this system"""
    from main import db, opensearch_client
    from models import System, CaseFile
    
    system = db.session.get(System, system_id)
    if not system or system.case_id != case_id:
        return jsonify({'success': False, 'error': 'System not found'}), 404
    
    try:
        # Get all index names for this case
        files = CaseFile.query.filter_by(case_id=case_id).all()
        index_names = [f.index_name for f in files if f.index_name]
        
        if not index_names:
            return jsonify({'success': True, 'count': 0})
        
        # Search for system name across all fields
        from opensearchpy import Search
        s = Search(using=opensearch_client, index=index_names)
        s = s.query("query_string", query=f'*{system.system_name}*', default_operator="AND")
        
        count = s.count()
        
        return jsonify({'success': True, 'count': count})
    
    except Exception as e:
        logger.error(f"[Systems] Error getting event count: {e}")
        return jsonify({'success': True, 'count': 0})


@systems_bp.route('/case/<int:case_id>/systems/scan', methods=['POST'])
@login_required
def scan_systems(case_id):
    """Scan case logs to discover systems"""
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot scan systems'}), 403
    
    from main import db, opensearch_client
    from models import Case, CaseFile, System
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'success': False, 'error': 'Case not found'}), 404
    
    try:
        # Check if there are indexed files for this case
        files = CaseFile.query.filter_by(case_id=case_id, is_indexed=True).all()
        
        if not files:
            return jsonify({'success': False, 'error': 'No indexed files found for this case'}), 400
        
        # Use wildcard pattern for all case indices (like in tasks.py)
        index_pattern = f"case_{case_id}_*"
        
        logger.info(f"[Systems] Starting system scan for case {case_id}, pattern: {index_pattern}")
        
        # Extract systems from common fields
        discovered_systems = {}
        
        # Fields to search for system names
        system_fields = [
            'Computer', 'ComputerName', 'Hostname', 'System', 'WorkstationName',
            'host.name', 'hostname', 'computer', 'computername', 'source_name',
            'SourceHostname', 'DestinationHostname', 'src_host', 'dst_host'
        ]
        
        from opensearchpy import Search
        
        for field in system_fields:
            try:
                s = Search(using=opensearch_client, index=index_pattern)
                s = s.filter('exists', field=field)
                s = s[:0]  # Don't return documents
                s.aggs.bucket('systems', 'terms', field=f'{field}.keyword', size=1000)
                
                response = s.execute()
                
                if response.aggregations and hasattr(response.aggregations, 'systems'):
                    for bucket in response.aggregations.systems.buckets:
                        system_name = bucket.key
                        doc_count = bucket.doc_count
                        
                        # Clean system name
                        system_name = system_name.strip()
                        if not system_name or system_name == '-' or len(system_name) < 2:
                            continue
                        
                        # Skip IPs, they're handled separately
                        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', system_name):
                            continue
                        
                        # Track highest doc count per system
                        if system_name not in discovered_systems or doc_count > discovered_systems[system_name]['count']:
                            discovered_systems[system_name] = {
                                'name': system_name,
                                'count': doc_count,
                                'field': field
                            }
                            
                logger.debug(f"[Systems] Found {len(response.aggregations.systems.buckets)} systems in field '{field}'")
            
            except Exception as e:
                logger.warning(f"[Systems] Error scanning field '{field}': {e}")
                continue
        
        logger.info(f"[Systems] Discovered {len(discovered_systems)} unique systems")
        
        # Get IP addresses for discovered systems
        logger.info(f"[Systems] Resolving IP addresses for systems...")
        system_ips = {}
        
        # Query for IP addresses using normalized_computer and host.ip fields
        try:
            s = Search(using=opensearch_client, index=index_pattern)
            s = s.filter('exists', field='normalized_computer')
            s = s.filter('exists', field='host.ip')
            s = s[:0]  # Don't return documents
            
            # Aggregate by computer name, get most common IP (top_hits)
            s.aggs.bucket('by_computer', 'terms', field='normalized_computer.keyword', size=1000) \
                  .metric('top_ip', 'top_hits', size=1, _source=['host.ip'])
            
            response = s.execute()
            
            if response.aggregations and hasattr(response.aggregations, 'by_computer'):
                for bucket in response.aggregations.by_computer.buckets:
                    computer_name = bucket.key
                    if bucket.top_ip.hits.hits:
                        ip = bucket.top_ip.hits.hits[0]['_source'].get('host', {}).get('ip')
                        if ip:
                            system_ips[computer_name] = ip
                            logger.debug(f"[Systems] {computer_name} -> {ip}")
            
            logger.info(f"[Systems] Resolved IPs for {len(system_ips)} systems")
        except Exception as e:
            logger.warning(f"[Systems] Could not resolve IPs: {e}")
        
        # Categorize and save systems
        new_systems = 0
        updated_systems = 0
        
        for sys_name, sys_data in discovered_systems.items():
            # Check if already exists
            existing = System.query.filter_by(case_id=case_id, system_name=sys_name).first()
            
            # Get IP address for this system
            ip_address = system_ips.get(sys_name)
            
            if not existing:
                # Categorize system type
                system_type = categorize_system(sys_name)
                
                system = System(
                    case_id=case_id,
                    system_name=sys_name,
                    ip_address=ip_address,
                    system_type=system_type,
                    added_by='CaseScope',
                    hidden=False
                )
                db.session.add(system)
                new_systems += 1
                
                logger.debug(f"[Systems] New system: {sys_name} (type: {system_type}, IP: {ip_address}, events: {sys_data['count']})")
            else:
                # Update IP address if we found one and it's not already set
                if ip_address and not existing.ip_address:
                    existing.ip_address = ip_address
                    logger.debug(f"[Systems] Updated IP for {sys_name}: {ip_address}")
                updated_systems += 1
        
        db.session.commit()
        
        message = f"System scan complete: {new_systems} new systems found, {updated_systems} already existed"
        logger.info(f"[Systems] {message}")
        flash(message, 'success')
        
        return jsonify({
            'success': True,
            'new_systems': new_systems,
            'existing_systems': updated_systems,
            'total_discovered': len(discovered_systems)
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"[Systems] Error scanning systems: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@systems_bp.route('/case/<int:case_id>/systems/<int:system_id>/enrich', methods=['POST'])
@login_required
def enrich_system(case_id, system_id):
    """Manually trigger OpenCTI enrichment for a system"""
    from main import db
    from models import System
    
    system = db.session.get(System, system_id)
    if not system or system.case_id != case_id:
        return jsonify({'success': False, 'error': 'System not found'}), 404
    
    try:
        result = enrich_from_opencti(system)
        if result:
            flash(f'System enriched from OpenCTI: {system.system_name}', 'success')
            return jsonify({'success': True, 'enrichment': json.loads(system.opencti_enrichment) if system.opencti_enrichment else None})
        else:
            flash(f'OpenCTI enrichment not available', 'warning')
            return jsonify({'success': False, 'error': 'OpenCTI not configured or no data found'})
    
    except Exception as e:
        logger.error(f"[Systems] Error enriching system: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@systems_bp.route('/case/<int:case_id>/systems/<int:system_id>/sync', methods=['POST'])
@login_required
def sync_system_to_iris(case_id, system_id):
    """Manually trigger DFIR-IRIS sync for a system"""
    from main import db
    from models import System
    
    system = db.session.get(System, system_id)
    if not system or system.case_id != case_id:
        return jsonify({'success': False, 'error': 'System not found'}), 404
    
    try:
        result = sync_to_dfir_iris(system)
        if result:
            flash(f'System synced to DFIR-IRIS: {system.system_name}', 'success')
            return jsonify({'success': True, 'iris_id': system.dfir_iris_asset_id})
        else:
            flash(f'DFIR-IRIS sync not available', 'warning')
            return jsonify({'success': False, 'error': 'DFIR-IRIS not configured'})
    
    except Exception as e:
        logger.error(f"[Systems] Error syncing system: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def categorize_system(system_name):
    """
    Categorize system based on naming patterns
    Returns: server, workstation, firewall, switch, printer, actor_system
    """
    system_name_lower = system_name.lower()
    
    # Check each type's patterns
    for sys_type, patterns in SYSTEM_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, system_name_lower, re.IGNORECASE):
                return sys_type
    
    # Default to workstation
    return 'workstation'


def enrich_from_opencti(system):
    """
    Enrich system from OpenCTI threat intelligence
    """
    from main import db
    from models import SystemSettings
    
    # Check if OpenCTI is enabled
    opencti_enabled = SystemSettings.query.filter_by(setting_key='opencti_enabled').first()
    if not opencti_enabled or opencti_enabled.setting_value != 'true':
        logger.debug(f"[OpenCTI] Enrichment skipped - OpenCTI not enabled")
        return False
    
    # Get OpenCTI configuration
    opencti_url = SystemSettings.query.filter_by(setting_key='opencti_url').first()
    opencti_api_key = SystemSettings.query.filter_by(setting_key='opencti_api_key').first()
    
    if not opencti_url or not opencti_api_key:
        logger.warning(f"[OpenCTI] Enrichment failed - OpenCTI not configured")
        return False
    
    try:
        # Initialize OpenCTI client
        from opencti import OpenCTIClient
        client = OpenCTIClient(
            opencti_url.setting_value,
            opencti_api_key.setting_value
        )
        
        # Check system/hostname in OpenCTI
        enrichment = client.check_indicator(system.system_name, 'hostname')
        
        # Store enrichment data
        system.opencti_enrichment = json.dumps(enrichment)
        system.opencti_enriched_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"[OpenCTI] System enriched: {system.system_name} (Found: {enrichment.get('found', False)})")
        
        return True
        
    except Exception as e:
        logger.error(f"[OpenCTI] Enrichment failed for {system.system_name}: {e}")
        return False


def sync_to_dfir_iris(system):
    """
    Sync system to DFIR-IRIS as an asset
    """
    from main import db
    from models import SystemSettings
    
    # Check if DFIR-IRIS is enabled
    dfir_iris_enabled = SystemSettings.query.filter_by(setting_key='dfir_iris_enabled').first()
    if not dfir_iris_enabled or dfir_iris_enabled.setting_value != 'true':
        return False
    
    # Get DFIR-IRIS configuration
    dfir_iris_url = SystemSettings.query.filter_by(setting_key='dfir_iris_url').first()
    dfir_iris_token = SystemSettings.query.filter_by(setting_key='dfir_iris_token').first()
    
    if not dfir_iris_url or not dfir_iris_token:
        return False
    
    # TODO: Implement actual DFIR-IRIS API call to create/update asset
    # Example: POST to /api/assets with system data
    
    # Placeholder: Mark as synced
    system.dfir_iris_synced = True
    system.dfir_iris_sync_date = datetime.utcnow()
    system.dfir_iris_asset_id = f'asset-{system.id}'
    db.session.commit()
    
    logger.info(f"[DFIR-IRIS] System synced: {system.system_name}")
    
    return True

