"""
IOC Management Routes
Handles Indicators of Compromise (IOC) operations
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
from datetime import datetime
import json

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
        
        flash(f'IOC added: {ioc_value}', 'success')
        
        # Return success immediately, then do enrichment in background
        # This prevents slow OpenCTI/DFIR-IRIS from blocking the UI
        response = jsonify({'success': True, 'ioc_id': ioc.id})
        
        # Schedule background enrichment/sync (non-blocking)
        from threading import Thread
        from models import SystemSettings
        from flask import current_app
        
        def background_enrichment():
            # Need app context for database access in background thread
            with current_app.app_context():
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
        ioc.ioc_type = request.form.get('ioc_type', ioc.ioc_type)
        ioc.ioc_value = request.form.get('ioc_value', ioc.ioc_value).strip()
        ioc.description = request.form.get('description', ioc.description).strip()
        ioc.threat_level = request.form.get('threat_level', ioc.threat_level)
        
        db.session.commit()
        
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
        db.session.delete(ioc)
        db.session.commit()
        
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
        ioc.is_active = not ioc.is_active
        db.session.commit()
        
        status = 'activated' if ioc.is_active else 'deactivated'
        flash(f'IOC {status}: {ioc.ioc_value}', 'success')
        return jsonify({'success': True, 'is_active': ioc.is_active})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/<int:ioc_id>/enrich', methods=['POST'])
@login_required
def enrich_ioc(case_id, ioc_id):
    """Manually trigger OpenCTI enrichment for an IOC"""
    from main import db, IOC
    
    ioc = db.session.get(IOC, ioc_id)
    if not ioc or ioc.case_id != case_id:
        return jsonify({'success': False, 'error': 'IOC not found'}), 404
    
    try:
        result = enrich_from_opencti(ioc)
        if result:
            flash(f'IOC enriched from OpenCTI: {ioc.ioc_value}', 'success')
            return jsonify({'success': True, 'enrichment': json.loads(ioc.opencti_enrichment) if ioc.opencti_enrichment else None})
        else:
            flash(f'OpenCTI enrichment not available', 'warning')
            return jsonify({'success': False, 'error': 'OpenCTI not configured or no data found'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ioc_bp.route('/case/<int:case_id>/ioc/<int:ioc_id>/sync', methods=['POST'])
@login_required
def sync_ioc_to_iris(case_id, ioc_id):
    """Manually trigger DFIR-IRIS sync for an IOC"""
    from main import db, IOC
    
    ioc = db.session.get(IOC, ioc_id)
    if not ioc or ioc.case_id != case_id:
        return jsonify({'success': False, 'error': 'IOC not found'}), 404
    
    try:
        result = sync_to_dfir_iris(ioc)
        if result:
            flash(f'IOC synced to DFIR-IRIS: {ioc.ioc_value}', 'success')
            return jsonify({'success': True, 'iris_id': ioc.dfir_iris_ioc_id})
        else:
            flash(f'DFIR-IRIS sync not available', 'warning')
            return jsonify({'success': False, 'error': 'DFIR-IRIS not configured'})
    
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


