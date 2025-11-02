"""System Settings Routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from main import db, opensearch_client
from models import SystemSettings

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


def admin_required(f):
    """Decorator to require administrator role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'administrator':
            flash('⛔ Administrator access required', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_setting(key, default=None):
    """Get a system setting value"""
    setting = db.session.query(SystemSettings).filter_by(setting_key=key).first()
    return setting.setting_value if setting else default


def set_setting(key, value, description=None):
    """Set a system setting value"""
    setting = db.session.query(SystemSettings).filter_by(setting_key=key).first()
    if setting:
        setting.setting_value = value
        if description:
            setting.description = description
    else:
        setting = SystemSettings(
            setting_key=key,
            setting_value=value,
            description=description
        )
        db.session.add(setting)
    db.session.commit()


@settings_bp.route('/')
@login_required
@admin_required
def index():
    """System settings page"""
    # Get DFIR-IRIS settings
    dfir_iris_enabled = get_setting('dfir_iris_enabled', 'false') == 'true'
    dfir_iris_url = get_setting('dfir_iris_url', '')
    dfir_iris_api_key = get_setting('dfir_iris_api_key', '')
    
    # Get OpenCTI settings
    opencti_enabled = get_setting('opencti_enabled', 'false') == 'true'
    opencti_url = get_setting('opencti_url', '')
    opencti_api_key = get_setting('opencti_api_key', '')
    
    # Get Logging settings
    log_level = get_setting('log_level', 'INFO')
    
    return render_template('settings.html',
                         dfir_iris_enabled=dfir_iris_enabled,
                         dfir_iris_url=dfir_iris_url,
                         dfir_iris_api_key=dfir_iris_api_key,
                         opencti_enabled=opencti_enabled,
                         opencti_url=opencti_url,
                         opencti_api_key=opencti_api_key,
                         log_level=log_level)


@settings_bp.route('/save', methods=['POST'])
@login_required
@admin_required
def save():
    """Save system settings"""
    # DFIR-IRIS settings
    dfir_iris_enabled = request.form.get('dfir_iris_enabled') == 'on'
    dfir_iris_url = request.form.get('dfir_iris_url', '').strip()
    dfir_iris_api_key = request.form.get('dfir_iris_api_key', '').strip()
    
    set_setting('dfir_iris_enabled', 'true' if dfir_iris_enabled else 'false', 
                'Enable DFIR-IRIS integration')
    set_setting('dfir_iris_url', dfir_iris_url, 
                'DFIR-IRIS instance URL')
    set_setting('dfir_iris_api_key', dfir_iris_api_key, 
                'DFIR-IRIS API key')
    
    # OpenCTI settings
    opencti_enabled = request.form.get('opencti_enabled') == 'on'
    opencti_url = request.form.get('opencti_url', '').strip()
    opencti_api_key = request.form.get('opencti_api_key', '').strip()
    
    set_setting('opencti_enabled', 'true' if opencti_enabled else 'false',
                'Enable OpenCTI integration')
    set_setting('opencti_url', opencti_url,
                'OpenCTI instance URL')
    set_setting('opencti_api_key', opencti_api_key,
                'OpenCTI API key')
    
    # Logging settings
    log_level = request.form.get('log_level', 'INFO').upper()
    if log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
        log_level = 'INFO'  # Default to INFO if invalid
    
    old_log_level = get_setting('log_level', 'INFO')
    set_setting('log_level', log_level, 'Application log level')
    
    # Update log level dynamically if changed
    if old_log_level != log_level:
        try:
            import sys
            sys.path.insert(0, '/opt/casescope/app')
            from logging_config import update_log_level
            update_log_level(log_level)
        except Exception as e:
            print(f"Warning: Could not update log level dynamically: {e}")
    
    # Audit log
    from audit_logger import log_action
    log_action('update_settings', resource_type='settings', resource_name='System Settings',
              details={
                  'dfir_iris_enabled': dfir_iris_enabled,
                  'opencti_enabled': opencti_enabled,
                  'log_level': log_level
              })
    
    flash('✓ Settings saved successfully', 'success')
    return redirect(url_for('settings.index'))


@settings_bp.route('/test_iris', methods=['POST'])
@login_required
@admin_required
def test_iris():
    """Test DFIR-IRIS connection"""
    from flask import jsonify
    from dfir_iris import DFIRIrisClient
    
    url = request.json.get('url', '').strip()
    api_key = request.json.get('api_key', '').strip()
    
    if not url or not api_key:
        return jsonify({'success': False, 'message': 'URL and API key are required'})
    
    try:
        client = DFIRIrisClient(url, api_key)
        # Try to list cases as connection test (requires cid parameter)
        result = client._request('GET', '/manage/cases/list?cid=1')
        
        if result is not None:
            # If we get any response (even empty data), connection works
            if isinstance(result, dict) and 'data' in result:
                case_count = len(result['data']) if isinstance(result['data'], list) else 0
                return jsonify({
                    'success': True,
                    'message': f'✓ Connection successful! Found {case_count} case(s)'
                })
            else:
                return jsonify({
                    'success': True,
                    'message': '✓ Connection successful! API authenticated'
                })
        else:
            return jsonify({
                'success': False,
                'message': '✗ Connection failed - No response from server'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'✗ Connection failed: {str(e)}'
        })


@settings_bp.route('/sync_now', methods=['POST'])
@login_required
@admin_required
def sync_now():
    """Force sync all cases to DFIR-IRIS"""
    from flask import jsonify
    from dfir_iris import DFIRIrisClient, sync_case_to_dfir_iris
    from models import Case
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check if DFIR-IRIS is enabled
    dfir_iris_enabled = get_setting('dfir_iris_enabled', 'false') == 'true'
    if not dfir_iris_enabled:
        return jsonify({
            'success': False,
            'message': '✗ DFIR-IRIS integration is not enabled'
        })
    
    dfir_iris_url = get_setting('dfir_iris_url', '')
    dfir_iris_api_key = get_setting('dfir_iris_api_key', '')
    
    if not dfir_iris_url or not dfir_iris_api_key:
        return jsonify({
            'success': False,
            'message': '✗ DFIR-IRIS URL and API key must be configured'
        })
    
    try:
        client = DFIRIrisClient(dfir_iris_url, dfir_iris_api_key)
        
        # Get all active cases
        active_cases = db.session.query(Case).filter_by(status='active').all()
        
        if not active_cases:
            return jsonify({
                'success': True,
                'message': '✓ No active cases to sync'
            })
        
        synced = 0
        failed = 0
        
        for case in active_cases:
            try:
                result = sync_case_to_dfir_iris(db.session, opensearch_client, case.id, client)
                if result.get('success'):
                    synced += 1
                    logger.info(f"Synced case: {case.name} (ID: {case.id})")
                else:
                    failed += 1
                    logger.error(f"Failed to sync case: {case.name} (ID: {case.id})")
            except Exception as e:
                failed += 1
                logger.error(f"Error syncing case {case.name} (ID: {case.id}): {e}")
        
        if failed == 0:
            return jsonify({
                'success': True,
                'message': f'✓ Successfully synced {synced} case(s) to DFIR-IRIS'
            })
        else:
            return jsonify({
                'success': False if synced == 0 else True,
                'message': f'⚠️ Synced {synced} case(s), {failed} failed. Check logs for details.'
            })
    
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return jsonify({
            'success': False,
            'message': f'✗ Sync failed: {str(e)}'
        })


@settings_bp.route('/test_opencti', methods=['POST'])
@login_required
@admin_required
def test_opencti():
    """Test OpenCTI connection"""
    from flask import jsonify
    from opencti import OpenCTIClient
    
    url = request.json.get('url', '').strip()
    api_key = request.json.get('api_key', '').strip()
    
    if not url or not api_key:
        return jsonify({'success': False, 'message': 'URL and API key are required'})
    
    try:
        client = OpenCTIClient(url, api_key)
        
        # Check if client initialization failed with specific error
        if client.init_error:
            return jsonify({
                'success': False,
                'message': f'✗ {client.init_error}'
            })
        
        # Test connection with ping
        if client.ping():
            return jsonify({
                'success': True,
                'message': '✓ Connection successful! OpenCTI is accessible'
            })
        else:
            return jsonify({
                'success': False,
                'message': '✗ Connection failed - Could not reach OpenCTI or invalid credentials'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'✗ Connection failed: {str(e)}'
        })


@settings_bp.route('/sync_opencti', methods=['POST'])
@login_required
@admin_required
def sync_opencti():
    """Enrich all IOCs with OpenCTI threat intelligence"""
    from flask import jsonify
    from opencti import OpenCTIClient, enrich_case_iocs
    from models import Case
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check if OpenCTI is enabled
    opencti_enabled = get_setting('opencti_enabled', 'false') == 'true'
    if not opencti_enabled:
        return jsonify({
            'success': False,
            'message': '✗ OpenCTI integration is not enabled'
        })
    
    opencti_url = get_setting('opencti_url', '')
    opencti_api_key = get_setting('opencti_api_key', '')
    
    if not opencti_url or not opencti_api_key:
        return jsonify({
            'success': False,
            'message': '✗ OpenCTI URL and API key must be configured'
        })
    
    try:
        client = OpenCTIClient(opencti_url, opencti_api_key)
        
        # Get all active cases
        active_cases = db.session.query(Case).filter_by(status='active').all()
        
        if not active_cases:
            return jsonify({
                'success': True,
                'message': '✓ No active cases to enrich'
            })
        
        total_enriched = 0
        total_found = 0
        total_not_found = 0
        failed_cases = 0
        
        for case in active_cases:
            try:
                result = enrich_case_iocs(db.session, case.id, client)
                if result.get('success'):
                    total_enriched += result.get('enriched_count', 0)
                    total_found += result.get('found_count', 0)
                    total_not_found += result.get('not_found_count', 0)
                    logger.info(f"Enriched IOCs for case: {case.name} (ID: {case.id})")
                else:
                    failed_cases += 1
                    logger.error(f"Failed to enrich case: {case.name} (ID: {case.id})")
            except Exception as e:
                failed_cases += 1
                logger.error(f"Error enriching case {case.name} (ID: {case.id}): {e}")
        
        if failed_cases == 0:
            return jsonify({
                'success': True,
                'message': f'✓ Enriched {total_enriched} IOC(s) across {len(active_cases)} case(s): {total_found} found in OpenCTI, {total_not_found} not found'
            })
        else:
            return jsonify({
                'success': False if total_enriched == 0 else True,
                'message': f'⚠️ Enriched {total_enriched} IOC(s), {failed_cases} case(s) failed. Check logs for details.'
            })
    
    except Exception as e:
        logger.error(f"OpenCTI enrichment failed: {e}")
        return jsonify({
            'success': False,
            'message': f'✗ Enrichment failed: {str(e)}'
        })

