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
    
    # Get AI settings
    ai_enabled = get_setting('ai_enabled', 'false') == 'true'
    ai_model_name = get_setting('ai_model_name', 'deepseek-r1:32b')
    ai_hardware_mode = get_setting('ai_hardware_mode', 'cpu')  # cpu or gpu
    ai_gpu_vram = get_setting('ai_gpu_vram', '8')  # VRAM in GB
    
    # Check AI system status
    ai_status = {'installed': False, 'running': False, 'model_available': False, 'models': []}
    all_models = []
    try:
        from ai_report import check_ollama_status, MODEL_INFO
        ai_status = check_ollama_status()
        
        # Get list of installed model names
        installed_model_names = [m['name'] for m in ai_status.get('models', [])]
        
        # Create a list of ALL models from MODEL_INFO, marking which are installed
        for model_id, model_data in MODEL_INFO.items():
            is_installed = model_id in installed_model_names
            all_models.append({
                'name': model_id,
                'display_name': model_data['name'],
                'speed': model_data['speed'],
                'quality': model_data['quality'],
                'size': model_data['size'],
                'description': model_data['description'],
                'speed_estimate': model_data['speed_estimate'],
                'time_estimate': model_data['time_estimate'],
                'recommended': model_data.get('recommended', False),
                'installed': is_installed
            })
        
        # Sort: installed first, then by recommended, then alphabetically
        all_models.sort(key=lambda x: (not x['installed'], not x['recommended'], x['display_name']))
        
    except:
        pass
    
    # Detect hardware for AI settings
    hardware_info = {'gpu': {'gpu_detected': False}, 'cpu': {'cpu_count': 0}}
    try:
        from hardware_utils import get_hardware_status
        hardware_info = get_hardware_status()
    except Exception as e:
        logger.error(f"[Settings] Hardware detection error: {e}")
    
    return render_template('settings.html',
                         dfir_iris_enabled=dfir_iris_enabled,
                         dfir_iris_url=dfir_iris_url,
                         dfir_iris_api_key=dfir_iris_api_key,
                         opencti_enabled=opencti_enabled,
                         opencti_url=opencti_url,
                         opencti_api_key=opencti_api_key,
                         log_level=log_level,
                         ai_enabled=ai_enabled,
                         ai_model_name=ai_model_name,
                         ai_hardware_mode=ai_hardware_mode,
                         ai_gpu_vram=ai_gpu_vram,
                         ai_status=ai_status,
                         all_models=all_models,
                         hardware_info=hardware_info)


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
    
    # AI settings
    ai_enabled = request.form.get('ai_enabled') == 'on'
    ai_model_name = request.form.get('ai_model_name', 'deepseek-r1:32b').strip()
    ai_hardware_mode = request.form.get('ai_hardware_mode', 'cpu').strip().lower()
    ai_gpu_vram = request.form.get('ai_gpu_vram', '8').strip()
    
    # Validate hardware mode
    if ai_hardware_mode not in ['cpu', 'gpu']:
        ai_hardware_mode = 'cpu'  # Default to CPU if invalid
    
    set_setting('ai_enabled', 'true' if ai_enabled else 'false',
                'Enable AI report generation features')
    set_setting('ai_model_name', ai_model_name,
                'AI model name for report generation')
    set_setting('ai_hardware_mode', ai_hardware_mode,
                'AI hardware mode: cpu or gpu (auto-optimizes settings)')
    set_setting('ai_gpu_vram', ai_gpu_vram,
                'GPU VRAM in GB (for model recommendations)')
    
    # Auto-setup GPU if needed
    if ai_hardware_mode == 'gpu':
        from hardware_setup import get_gpu_requirements_status
        status = get_gpu_requirements_status()
        if not status['ready']:
            flash('⚠️ GPU mode enabled but requirements not met. Please ensure NVIDIA drivers and CUDA are installed.', 'warning')
    
    # Audit log
    from audit_logger import log_action
    log_action('update_settings', resource_type='settings', resource_name='System Settings',
              details={
                  'dfir_iris_enabled': dfir_iris_enabled,
                  'opencti_enabled': opencti_enabled,
                  'log_level': log_level,
                  'ai_enabled': ai_enabled,
                  'ai_model_name': ai_model_name,
                  'ai_hardware_mode': ai_hardware_mode,
                  'ai_gpu_vram': ai_gpu_vram
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


@settings_bp.route('/update_models', methods=['POST'])
@login_required
@admin_required
def update_models():
    """Update all installed AI models (streaming progress)"""
    from flask import Response, stream_with_context
    import subprocess
    import json
    import re
    
    def generate_progress():
        """Generator function to stream progress updates"""
        try:
            # Get list of installed models
            result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
            if result.returncode != 0:
                yield f"data: {json.dumps({'error': 'Failed to get model list'})}\n\n"
                return
            
            # Parse installed models (skip header line)
            lines = result.stdout.strip().split('\n')[1:]
            models = []
            for line in lines:
                parts = line.split()
                if parts:
                    model_name = parts[0]
                    models.append(model_name)
            
            if not models:
                yield f"data: {json.dumps({'error': 'No models installed'})}\n\n"
                return
            
            total_models = len(models)
            yield f"data: {json.dumps({'total': total_models, 'models': models})}\n\n"
            
            # Update each model
            for idx, model in enumerate(models, 1):
                yield f"data: {json.dumps({'stage': 'starting', 'model': model, 'index': idx, 'total': total_models})}\n\n"
                
                # Run ollama pull with streaming output
                process = subprocess.Popen(
                    ['ollama', 'pull', model],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                last_status = None
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse progress from ollama output
                    # Format: "pulling <layer>: <percent>% ▕████▏ <size>"
                    status_match = re.search(r'(pulling|verifying|writing)\s+(\w+):\s+(\d+)%', line)
                    if status_match:
                        action = status_match.group(1)
                        layer = status_match.group(2)
                        percent = int(status_match.group(3))
                        status = f"{action.capitalize()} {layer[:8]}... {percent}%"
                        
                        # Only send if status changed (reduce spam)
                        if status != last_status:
                            yield f"data: {json.dumps({'stage': 'downloading', 'model': model, 'index': idx, 'total': total_models, 'progress': percent, 'status': status})}\n\n"
                            last_status = status
                    
                    # Check for completion messages
                    if 'success' in line.lower():
                        yield f"data: {json.dumps({'stage': 'completed', 'model': model, 'index': idx, 'total': total_models})}\n\n"
                    elif 'error' in line.lower():
                        yield f"data: {json.dumps({'stage': 'error', 'model': model, 'index': idx, 'total': total_models, 'error': line})}\n\n"
                
                process.wait()
                
                # Ensure completion message is sent
                if process.returncode == 0:
                    yield f"data: {json.dumps({'stage': 'completed', 'model': model, 'index': idx, 'total': total_models})}\n\n"
                else:
                    yield f"data: {json.dumps({'stage': 'error', 'model': model, 'index': idx, 'total': total_models, 'error': f'Exit code {process.returncode}'})}\n\n"
            
            # All done
            yield f"data: {json.dumps({'stage': 'all_complete', 'total': total_models})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(
        stream_with_context(generate_progress()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@settings_bp.route('/check_gpu_requirements', methods=['POST'])
@login_required
@admin_required
def check_gpu_requirements():
    """Check if GPU requirements are met"""
    try:
        from hardware_setup import get_gpu_requirements_status
        status = get_gpu_requirements_status()
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        logger.error(f"[Settings] GPU check error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/setup_gpu', methods=['GET'])
@login_required
@admin_required
def setup_gpu_stream():
    """Setup GPU requirements with progress streaming"""
    def generate():
        try:
            from hardware_setup import setup_gpu_requirements
            import json
            
            def progress_callback(message):
                yield f"data: {json.dumps({'status': 'progress', 'message': message})}\n\n"
            
            # Run setup
            result = setup_gpu_requirements(progress_callback)
            
            if result['success']:
                yield f"data: {json.dumps({'status': 'complete', 'result': result})}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'error', 'message': result.get('error', 'Setup failed')})}\n\n"
                
        except Exception as e:
            logger.error(f"[Settings] GPU setup error: {e}")
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

