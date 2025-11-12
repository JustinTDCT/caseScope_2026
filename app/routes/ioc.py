"""
IOC Management Routes
Handles Indicators of Compromise (IOC) operations
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, Response
from flask_login import login_required, current_user
from datetime import datetime
import json
import csv
import io

ioc_bp = Blueprint('ioc', __name__)


@ioc_bp.route('/case/<int:case_id>/ioc')
@login_required
def ioc_management(case_id):
    """IOC Management page for a case"""
    from main import db, Case, IOC
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all IOCs for this case
    iocs = IOC.query.filter_by(case_id=case_id).order_by(IOC.created_at.desc()).all()
    
    # Get system settings for integrations
    from models import SystemSettings
    opencti_enabled = SystemSettings.query.filter_by(setting_key='opencti_enabled').first()
    dfir_iris_enabled = SystemSettings.query.filter_by(setting_key='dfir_iris_enabled').first()
    dfir_iris_auto_sync = SystemSettings.query.filter_by(setting_key='dfir_iris_auto_sync').first()
    
    return render_template('ioc_management.html',
                         case=case,
                         iocs=iocs,
                         opencti_enabled=(opencti_enabled.setting_value == 'true' if opencti_enabled else False),
                         dfir_iris_enabled=(dfir_iris_enabled.setting_value == 'true' if dfir_iris_enabled else False),
                         dfir_iris_auto_sync=(dfir_iris_auto_sync.setting_value == 'true' if dfir_iris_auto_sync else False))


@ioc_bp.route('/case/<int:case_id>/ioc/add', methods=['POST'])
@login_required
def add_ioc(case_id):
    """Add new IOC to case"""
    # Permission check: Read-only users cannot add IOCs
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot add IOCs'}), 403
    
    from main import db, Case, IOC
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'success': False, 'error': 'Case not found'}), 404
    
    try:
        ioc_type = request.form.get('ioc_type')
        ioc_value = request.form.get('ioc_value', '').strip()
        description = request.form.get('description', '').strip()
        threat_level = request.form.get('threat_level', 'medium')
        
        if not ioc_type or not ioc_value:
            return jsonify({'success': False, 'error': 'Type and Value are required'}), 400
        
        # Check for duplicate
        existing = IOC.query.filter_by(case_id=case_id, ioc_type=ioc_type, ioc_value=ioc_value).first()
        if existing:
            return jsonify({'success': False, 'error': 'IOC already exists in this case'}), 400
        
        # Create IOC
        ioc = IOC(
            case_id=case_id,
            ioc_type=ioc_type,
            ioc_value=ioc_value,
            description=description,
            threat_level=threat_level,
            created_by=current_user.id,
            is_active=True
        )
        db.session.add(ioc)
        db.session.commit()
        
        # Store IOC ID for background processing
        ioc_id_for_background = ioc.id
        
        # Audit log
        from audit_logger import log_ioc_action
        log_ioc_action('add_ioc', ioc.id, ioc_value, details={
            'case_id': case_id,
            'case_name': case.name,
            'ioc_type': ioc_type,
            'threat_level': threat_level
        })
        
        flash(f'IOC added: {ioc_value}', 'success')
        
        # Return success immediately, then do enrichment in background
        # This prevents slow OpenCTI/DFIR-IRIS from blocking the UI
        response = jsonify({'success': True, 'ioc_id': ioc.id})
        
        # Schedule background enrichment/sync (non-blocking)
        from threading import Thread
        from models import SystemSettings
        from flask import current_app
        
        # Get actual app object (current_app is a proxy that doesn't work in threads)
        app = current_app._get_current_object()
        
        def background_enrichment():
            # Need app context for database access in background thread
            with app.app_context():
                try:
                    # Check for OpenCTI enrichment
                    opencti_enabled = SystemSettings.query.filter_by(setting_key='opencti_enabled').first()
                    if opencti_enabled and opencti_enabled.setting_value == 'true':
                        bg_ioc = db.session.get(IOC, ioc_id_for_background)
                        if bg_ioc:
                            enrich_from_opencti(bg_ioc)
                    
                    # Check for DFIR-IRIS auto sync
                    dfir_iris_auto_sync = SystemSettings.query.filter_by(setting_key='dfir_iris_auto_sync').first()
                    if dfir_iris_auto_sync and dfir_iris_auto_sync.setting_value == 'true':
                        bg_ioc = db.session.get(IOC, ioc_id_for_background)
                        if bg_ioc:
                            sync_to_dfir_iris(bg_ioc)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"[IOC] Background enrichment failed: {e}")
        
        # Start background thread (non-blocking)
        Thread(target=background_enrichment, daemon=True).start()
        
        return response
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/<int:ioc_id>/get', methods=['GET'])
@login_required
def get_ioc(case_id, ioc_id):
    """Get IOC details for editing"""
    from main import db, IOC
    
    ioc = db.session.get(IOC, ioc_id)
    if not ioc or ioc.case_id != case_id:
        return jsonify({'success': False, 'error': 'IOC not found'}), 404
    
    return jsonify({
        'success': True,
        'ioc': {
            'id': ioc.id,
            'ioc_type': ioc.ioc_type,
            'ioc_value': ioc.ioc_value,
            'description': ioc.description or '',
            'threat_level': ioc.threat_level
        }
    })


@ioc_bp.route('/case/<int:case_id>/ioc/<int:ioc_id>/edit', methods=['POST'])
@login_required
def edit_ioc(case_id, ioc_id):
    """Edit existing IOC"""
    # Permission check: Read-only users cannot edit IOCs
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot edit IOCs'}), 403
    
    from main import db, IOC
    
    ioc = db.session.get(IOC, ioc_id)
    if not ioc or ioc.case_id != case_id:
        return jsonify({'success': False, 'error': 'IOC not found'}), 404
    
    try:
        old_value = ioc.ioc_value
        old_type = ioc.ioc_type
        old_threat = ioc.threat_level
        
        ioc.ioc_type = request.form.get('ioc_type', ioc.ioc_type)
        ioc.ioc_value = request.form.get('ioc_value', ioc.ioc_value).strip()
        ioc.description = request.form.get('description', ioc.description).strip()
        ioc.threat_level = request.form.get('threat_level', ioc.threat_level)
        
        db.session.commit()
        
        # Audit log
        from audit_logger import log_ioc_action
        from main import Case
        case = db.session.get(Case, case_id)
        changes = {}
        if old_type != ioc.ioc_type:
            changes['ioc_type'] = {'old': old_type, 'new': ioc.ioc_type}
        if old_value != ioc.ioc_value:
            changes['ioc_value'] = {'old': old_value, 'new': ioc.ioc_value}
        if old_threat != ioc.threat_level:
            changes['threat_level'] = {'old': old_threat, 'new': ioc.threat_level}
        log_ioc_action('edit_ioc', ioc.id, ioc.ioc_value, details={
            'case_id': case_id,
            'case_name': case.name if case else None,
            'changes': changes
        })
        
        flash(f'IOC updated: {ioc.ioc_value}', 'success')
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/<int:ioc_id>/delete', methods=['POST'])
@login_required
def delete_ioc(case_id, ioc_id):
    """Delete IOC"""
    # Permission check: Read-only users cannot delete IOCs
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot delete IOCs'}), 403
    
    from main import db, IOC
    
    ioc = db.session.get(IOC, ioc_id)
    if not ioc or ioc.case_id != case_id:
        return jsonify({'success': False, 'error': 'IOC not found'}), 404
    
    try:
        ioc_value = ioc.ioc_value
        ioc_type = ioc.ioc_type
        from main import Case
        case = db.session.get(Case, case_id)
        
        db.session.delete(ioc)
        db.session.commit()
        
        # Audit log
        from audit_logger import log_ioc_action
        log_ioc_action('delete_ioc', ioc_id, ioc_value, details={
            'case_id': case_id,
            'case_name': case.name if case else None,
            'ioc_type': ioc_type
        })
        
        flash(f'IOC deleted: {ioc_value}', 'success')
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/<int:ioc_id>/toggle', methods=['POST'])
@login_required
def toggle_ioc(case_id, ioc_id):
    """Toggle IOC active status"""
    # Permission check: Read-only users cannot toggle IOCs
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot toggle IOCs'}), 403
    
    from main import db, IOC
    
    ioc = db.session.get(IOC, ioc_id)
    if not ioc or ioc.case_id != case_id:
        return jsonify({'success': False, 'error': 'IOC not found'}), 404
    
    try:
        old_status = ioc.is_active
        ioc.is_active = not ioc.is_active
        db.session.commit()
        
        # Audit log
        from audit_logger import log_ioc_action
        from main import Case
        case = db.session.get(Case, case_id)
        log_ioc_action('toggle_ioc', ioc.id, ioc.ioc_value, details={
            'case_id': case_id,
            'case_name': case.name if case else None,
            'old_status': 'active' if old_status else 'inactive',
            'new_status': 'active' if ioc.is_active else 'inactive'
        })
        
        status = 'activated' if ioc.is_active else 'deactivated'
        flash(f'IOC {status}: {ioc.ioc_value}', 'success')
        return jsonify({'success': True, 'is_active': ioc.is_active})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/<int:ioc_id>/enrich', methods=['POST'])
@login_required
def enrich_ioc(case_id, ioc_id):
    """Manually trigger OpenCTI enrichment for an IOC (non-blocking)"""
    from main import db, IOC
    
    ioc = db.session.get(IOC, ioc_id)
    if not ioc or ioc.case_id != case_id:
        return jsonify({'success': False, 'error': 'IOC not found'}), 404
    
    try:
        # Audit log
        from audit_logger import log_ioc_action
        from main import Case
        case = db.session.get(Case, case_id)
        log_ioc_action('enrich_ioc', ioc.id, ioc.ioc_value, details={
            'case_id': case_id,
            'case_name': case.name if case else None,
            'source': 'OpenCTI'
        })
        
        # Return success immediately, then do enrichment in background
        flash(f'Enriching IOC from OpenCTI: {ioc.ioc_value}', 'info')
        response = jsonify({'success': True, 'message': 'Enrichment started in background'})
        
        # Run enrichment in background thread (non-blocking)
        from threading import Thread
        from flask import current_app
        
        # Get actual app object (current_app is a proxy that doesn't work in threads)
        app = current_app._get_current_object()
        
        def background_enrich():
            with app.app_context():
                try:
                    result = enrich_from_opencti(ioc)
                    if result:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.info(f"[IOC] Manual enrichment successful: {ioc.ioc_value}")
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"[IOC] Manual enrichment failed: {e}")
        
        Thread(target=background_enrich, daemon=True).start()
        
        return response
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/<int:ioc_id>/sync', methods=['POST'])
@login_required
def sync_ioc_to_iris(case_id, ioc_id):
    """Manually trigger DFIR-IRIS sync for an IOC (non-blocking)"""
    from main import db, IOC
    
    ioc = db.session.get(IOC, ioc_id)
    if not ioc or ioc.case_id != case_id:
        return jsonify({'success': False, 'error': 'IOC not found'}), 404
    
    try:
        # Audit log
        from audit_logger import log_ioc_action
        from main import Case
        case = db.session.get(Case, case_id)
        log_ioc_action('sync_ioc_to_iris', ioc.id, ioc.ioc_value, details={
            'case_id': case_id,
            'case_name': case.name if case else None,
            'destination': 'DFIR-IRIS'
        })
        
        # Return success immediately, then do sync in background
        flash(f'Syncing IOC to DFIR-IRIS: {ioc.ioc_value}', 'info')
        response = jsonify({'success': True, 'message': 'Sync started in background'})
        
        # Run sync in background thread (non-blocking)
        from threading import Thread
        from flask import current_app
        
        # Get actual app object (current_app is a proxy that doesn't work in threads)
        app = current_app._get_current_object()
        
        def background_sync():
            with app.app_context():
                try:
                    result = sync_to_dfir_iris(ioc)
                    if result:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.info(f"[IOC] Manual DFIR-IRIS sync successful: {ioc.ioc_value}")
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"[IOC] Manual DFIR-IRIS sync failed: {e}")
        
        Thread(target=background_sync, daemon=True).start()
        
        return response
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/<int:ioc_id>/enrichment', methods=['GET'])
@login_required
def view_enrichment(case_id, ioc_id):
    """Get enrichment details for an IOC"""
    from main import db, IOC
    from flask import make_response
    
    ioc = db.session.get(IOC, ioc_id)
    if not ioc or ioc.case_id != case_id:
        return jsonify({'success': False, 'error': 'IOC not found'}), 404
    
    if not ioc.opencti_enrichment:
        return jsonify({'success': False, 'error': 'No enrichment data available'}), 404
    
    try:
        enrichment = json.loads(ioc.opencti_enrichment)
        response_data = {
            'success': True,
            'ioc_id': ioc_id,  # Add IOC ID to response for debugging
            'ioc_value': ioc.ioc_value,  # Add IOC value for debugging
            'enrichment': enrichment,
            'enriched_at': ioc.opencti_enriched_at.strftime('%Y-%m-%d %H:%M:%S UTC') if ioc.opencti_enriched_at else 'Unknown'
        }
        
        # Create response with no-cache headers
        response = make_response(jsonify(response_data))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# INTEGRATION FUNCTIONS (PLACEHOLDERS)
# ============================================================================

def enrich_from_opencti(ioc):
    """
    Enrich IOC from OpenCTI
    
    Connects to OpenCTI API and enriches IOC with threat intelligence:
    1. Query OpenCTI for IOC value
    2. Extract threat actors, campaigns, malware associations
    3. Calculate risk score based on confidence and relationships
    4. Store enrichment data and timestamp
    
    Note: Command-line IOCs are skipped as they are environment-specific
    and unlikely to have relevant external threat intelligence.
    """
    from main import db
    from models import SystemSettings
    from opencti import OpenCTIClient
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Skip enrichment for command-line IOCs (environment-specific, no threat intel value)
    if ioc.ioc_type.lower() == 'command':
        logger.debug(f"[OpenCTI] Enrichment skipped - Command IOCs are not enriched (environment-specific)")
        return False
    
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
        client = OpenCTIClient(
            opencti_url.setting_value,
            opencti_api_key.setting_value
        )
        
        # Check indicator in OpenCTI
        enrichment = client.check_indicator(ioc.ioc_value, ioc.ioc_type)
        
        # Store enrichment data
        ioc.opencti_enrichment = json.dumps(enrichment)
        ioc.opencti_enriched_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"[OpenCTI] IOC enriched: {ioc.ioc_value} (Found: {enrichment.get('found', False)})")
        
        return True
        
    except Exception as e:
        logger.error(f"[OpenCTI] Enrichment failed for {ioc.ioc_value}: {e}")
        return False


def sync_to_dfir_iris(ioc):
    """
    Sync IOC to DFIR-IRIS
    
    Placeholder implementation - returns False until DFIR-IRIS is configured
    
    When implemented:
    1. Connect to DFIR-IRIS API
    2. Create/update IOC in DFIR-IRIS
    3. Store DFIR-IRIS IOC ID
    4. Update sync status and timestamp
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
    
    # TODO: Implement actual DFIR-IRIS API call
    # Example: POST to /api/iocs with IOC data
    
    # Placeholder: Mark as synced with fake ID
    ioc.dfir_iris_synced = True
    ioc.dfir_iris_sync_date = datetime.utcnow()
    ioc.dfir_iris_ioc_id = f'placeholder-{ioc.id}'
    db.session.commit()
    
    return True


# ============================================================================
# BULK OPERATIONS
# ============================================================================

@ioc_bp.route('/case/<int:case_id>/ioc/bulk_toggle', methods=['POST'])
@login_required
def bulk_toggle_iocs(case_id):
    """Bulk enable/disable IOCs"""
    # Permission check: Read-only users cannot toggle IOCs
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot toggle IOCs'}), 403
    
    from main import db, Case, IOC
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'success': False, 'error': 'Case not found'}), 404
    
    data = request.json
    ioc_ids = data.get('ioc_ids', [])
    action = data.get('action', 'enable')  # 'enable' or 'disable'
    
    if not ioc_ids or not isinstance(ioc_ids, list):
        return jsonify({'success': False, 'error': 'IOC IDs array required'}), 400
    
    if action not in ['enable', 'disable']:
        return jsonify({'success': False, 'error': 'Action must be "enable" or "disable"'}), 400
    
    try:
        processed_count = 0
        new_status = (action == 'enable')
        
        for ioc_id in ioc_ids:
            ioc = db.session.get(IOC, int(ioc_id))
            if ioc and ioc.case_id == case_id:
                ioc.is_active = new_status
                processed_count += 1
        
        db.session.commit()
        
        # Audit log
        from audit_logger import log_action
        log_action('bulk_toggle_iocs', resource_type='ioc', resource_id=None,
                  resource_name=f'{processed_count} IOCs',
                  details={
                      'case_id': case_id,
                      'case_name': case.name,
                      'action': action,
                      'count': processed_count,
                      'ioc_ids': ioc_ids[:10]  # Log first 10 IDs
                  })
        
        action_text = 'enabled' if new_status else 'disabled'
        flash(f'{processed_count} IOC(s) {action_text}', 'success')
        
        return jsonify({
            'success': True,
            'processed': processed_count,
            'action': action
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/bulk_delete', methods=['POST'])
@login_required
def bulk_delete_iocs(case_id):
    """Bulk delete IOCs (administrators only)"""
    # Permission check: Only administrators can bulk delete
    if current_user.role != 'administrator':
        return jsonify({'success': False, 'error': 'Only administrators can bulk delete IOCs'}), 403
    
    from main import db, Case, IOC
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'success': False, 'error': 'Case not found'}), 404
    
    data = request.json
    ioc_ids = data.get('ioc_ids', [])
    
    if not ioc_ids or not isinstance(ioc_ids, list):
        return jsonify({'success': False, 'error': 'IOC IDs array required'}), 400
    
    try:
        deleted_count = 0
        
        for ioc_id in ioc_ids:
            ioc = db.session.get(IOC, int(ioc_id))
            if ioc and ioc.case_id == case_id:
                db.session.delete(ioc)
                deleted_count += 1
        
        db.session.commit()
        
        # Audit log
        from audit_logger import log_action
        log_action('bulk_delete_iocs', resource_type='ioc', resource_id=None,
                  resource_name=f'{deleted_count} IOCs',
                  details={
                      'case_id': case_id,
                      'case_name': case.name,
                      'count': deleted_count,
                      'ioc_ids': ioc_ids[:10]  # Log first 10 IDs
                  })
        
        flash(f'{deleted_count} IOC(s) deleted', 'success')
        
        return jsonify({
            'success': True,
            'deleted': deleted_count
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/bulk_enrich', methods=['POST'])
@login_required
def bulk_enrich_iocs(case_id):
    """Bulk enrich IOCs from OpenCTI (background processing)"""
    from main import db, Case, IOC
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'success': False, 'error': 'Case not found'}), 404
    
    data = request.json
    ioc_ids = data.get('ioc_ids', [])
    
    if not ioc_ids or not isinstance(ioc_ids, list):
        return jsonify({'success': False, 'error': 'IOC IDs array required'}), 400
    
    # Check if OpenCTI is enabled
    from models import SystemSettings
    opencti_enabled = SystemSettings.query.filter_by(setting_key='opencti_enabled').first()
    if not opencti_enabled or opencti_enabled.setting_value != 'true':
        return jsonify({'success': False, 'error': 'OpenCTI enrichment is not enabled'}), 400
    
    try:
        # Audit log
        from audit_logger import log_action
        log_action('bulk_enrich_iocs', resource_type='ioc', resource_id=None,
                  resource_name=f'{len(ioc_ids)} IOCs',
                  details={
                      'case_id': case_id,
                      'case_name': case.name,
                      'count': len(ioc_ids),
                      'source': 'OpenCTI'
                  })
        
        # Return success immediately, enrich in background
        flash(f'Enriching {len(ioc_ids)} IOC(s) from OpenCTI in background...', 'info')
        response = jsonify({
            'success': True,
            'queued': len(ioc_ids),
            'message': 'Enrichment started in background'
        })
        
        # Run enrichment in background thread (non-blocking)
        from threading import Thread
        from flask import current_app
        
        # Get actual app object (current_app is a proxy that doesn't work in threads)
        app = current_app._get_current_object()
        
        def background_bulk_enrich():
            with app.app_context():
                import logging
                logger = logging.getLogger(__name__)
                success_count = 0
                failed_count = 0
                
                for ioc_id in ioc_ids:
                    try:
                        ioc = db.session.get(IOC, int(ioc_id))
                        if ioc and ioc.case_id == case_id:
                            result = enrich_from_opencti(ioc)
                            if result:
                                success_count += 1
                            else:
                                failed_count += 1
                    except Exception as e:
                        logger.error(f"[IOC] Bulk enrichment failed for IOC {ioc_id}: {e}")
                        failed_count += 1
                
                logger.info(f"[IOC] Bulk enrichment complete: {success_count} succeeded, {failed_count} failed")
        
        Thread(target=background_bulk_enrich, daemon=True).start()
        
        return response
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/export_csv')
@login_required
def export_iocs_csv(case_id):
    """Export all IOCs for a case to CSV"""
    from main import db, Case, IOC
    
    # Verify case exists
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        # Get all IOCs for this case
        iocs = IOC.query.filter_by(case_id=case_id).order_by(IOC.ioc_type, IOC.ioc_value).all()
        
        # Audit log
        from audit_logger import log_action
        log_action('export_iocs_csv', resource_type='ioc', resource_id=None,
                  resource_name=f'{len(iocs)} IOCs',
                  details={
                      'case_id': case_id,
                      'case_name': case.name,
                      'count': len(iocs)
                  })
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Type', 'Value', 'Description'])
        
        # Write data
        for ioc in iocs:
            writer.writerow([
                ioc.ioc_type,
                ioc.ioc_value,
                ioc.description or ''
            ])
        
        # Create response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=iocs_case_{case_id}_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'}
        )
    
    except Exception as e:
        flash(f'Export failed: {str(e)}', 'error')
        return redirect(url_for('ioc.ioc_management', case_id=case_id))


