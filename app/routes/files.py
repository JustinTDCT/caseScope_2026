"""
Files Blueprint - Case file management routes
Handles file listing, hidden files, bulk operations
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import logging

logger = logging.getLogger(__name__)

files_bp = Blueprint('files', __name__)


@files_bp.route('/files/global')
@login_required
def global_files():
    """Global File Management - All files across all cases"""
    from main import db, Case, CaseFile
    from sqlalchemy import func, or_
    
    # Pagination and search
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '', type=str).strip()
    per_page = 50
    
    # Base query: all visible files
    files_query = db.session.query(CaseFile).filter_by(
        is_deleted=False,
        is_hidden=False
    )
    
    # Apply search filter
    if search_term:
        search_filter = or_(
            CaseFile.original_filename.ilike(f'%{search_term}%'),
            CaseFile.file_hash.ilike(f'%{search_term}%')
        )
        files_query = files_query.filter(search_filter)
    
    files_query = files_query.order_by(CaseFile.uploaded_at.desc())
    pagination = files_query.paginate(page=page, per_page=per_page, error_out=False)
    files = pagination.items
    
    # Global stats
    all_visible = db.session.query(CaseFile).filter_by(is_deleted=False, is_hidden=False)
    total_files = all_visible.count()
    hidden_files = db.session.query(CaseFile).filter_by(is_deleted=False, is_hidden=True).count()
    
    total_space_bytes = db.session.query(func.sum(CaseFile.file_size)).filter_by(
        is_deleted=False, is_hidden=False
    ).scalar() or 0
    
    total_events = db.session.query(func.sum(CaseFile.event_count)).filter_by(
        is_deleted=False, is_hidden=False
    ).scalar() or 0
    
    sigma_events = db.session.query(func.sum(CaseFile.violation_count)).filter_by(
        is_deleted=False, is_hidden=False
    ).scalar() or 0
    
    ioc_events = db.session.query(func.sum(CaseFile.ioc_event_count)).filter_by(
        is_deleted=False, is_hidden=False
    ).scalar() or 0
    
    # File type breakdown
    file_types = {}
    for f in all_visible.all():
        ft = f.file_type or 'Unknown'
        file_types[ft] = file_types.get(ft, 0) + 1
    
    # Processing state counts
    known_statuses = ['Completed', 'Indexing', 'SIGMA Testing', 'IOC Hunting', 'Queued']
    files_completed = all_visible.filter_by(indexing_status='Completed').count()
    files_queued = all_visible.filter_by(indexing_status='Queued').count()
    files_indexing = all_visible.filter_by(indexing_status='Indexing').count()
    files_sigma = all_visible.filter_by(indexing_status='SIGMA Testing').count()
    files_ioc_hunting = all_visible.filter_by(indexing_status='IOC Hunting').count()
    files_failed = all_visible.filter(~CaseFile.indexing_status.in_(known_statuses)).count()
    
    return render_template('global_files.html',
                          files=files,
                          pagination=pagination,
                          search_term=search_term,
                          total_files=total_files,
                          hidden_files=hidden_files,
                          total_space_gb=total_space_bytes / (1024**3),
                          file_types=file_types,
                          total_events=total_events,
                          total_sigma_events=sigma_events,
                          total_ioc_events=ioc_events,
                          files_completed=files_completed,
                          files_queued=files_queued,
                          files_indexing=files_indexing,
                          files_sigma=files_sigma,
                          files_ioc_hunting=files_ioc_hunting,
                          files_failed=files_failed)


@files_bp.route('/case/<int:case_id>/files')
@login_required
def case_files(case_id):
    """Case Files Management Page with Pagination and Search"""
    from main import db, Case, CaseFile
    from hidden_files import get_hidden_files_count, get_file_stats_with_hidden
    from sqlalchemy import func, or_
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Pagination and search
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '', type=str).strip()
    per_page = 50
    
    # Get visible files only (exclude hidden and deleted)
    files_query = db.session.query(CaseFile).filter_by(
        case_id=case_id,
        is_deleted=False,
        is_hidden=False
    )
    
    # Apply search filter if provided
    if search_term:
        search_filter = or_(
            CaseFile.original_filename.ilike(f'%{search_term}%'),
            CaseFile.file_hash.ilike(f'%{search_term}%')
        )
        files_query = files_query.filter(search_filter)
    
    files_query = files_query.order_by(CaseFile.uploaded_at.desc())
    
    pagination = files_query.paginate(page=page, per_page=per_page, error_out=False)
    files = pagination.items
    
    # Get comprehensive stats (includes hidden count)
    stats = get_file_stats_with_hidden(db.session, case_id)
    
    # File type breakdown (visible files only)
    all_visible_files = files_query.all()
    file_types = {}
    for f in all_visible_files:
        ft = f.file_type or 'Unknown'
        file_types[ft] = file_types.get(ft, 0) + 1
    
    return render_template('case_files.html',
                          case=case,
                          files=files,
                          pagination=pagination,
                          search_term=search_term,
                          total_files=stats['visible_files'],
                          hidden_files=stats['hidden_files'],
                          total_space_gb=stats['total_space_bytes'] / (1024**3),
                          file_types=file_types,
                          total_events=stats['total_events'],
                          total_sigma_events=stats['sigma_events'],
                          total_ioc_events=stats['ioc_events'],
                          files_completed=stats.get('files_completed', 0),
                          files_queued=stats.get('files_queued', 0),
                          files_indexing=stats.get('files_indexing', 0),
                          files_sigma=stats.get('files_sigma', 0),
                          files_ioc_hunting=stats.get('files_ioc_hunting', 0),
                          files_failed=stats.get('files_failed', 0))


@files_bp.route('/case/<int:case_id>/hidden_files')
@login_required
def view_hidden_files(case_id):
    """View hidden files (0-event files)"""
    from main import db, Case
    from hidden_files import get_hidden_files, get_hidden_files_count
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    pagination = get_hidden_files(db.session, case_id, page, per_page)
    hidden_count = get_hidden_files_count(db.session, case_id)
    
    return render_template('hidden_files.html',
                          case=case,
                          files=pagination.items,
                          pagination=pagination,
                          hidden_count=hidden_count)


@files_bp.route('/case/<int:case_id>/file/<int:file_id>/toggle_hidden', methods=['POST'])
@login_required
def toggle_file_hidden(case_id, file_id):
    """Toggle file hidden status"""
    from main import db
    from hidden_files import toggle_file_visibility
    
    result = toggle_file_visibility(db.session, file_id, current_user.id)
    
    if result['success']:
        flash(f"File marked as {result['action']}", 'success')
    else:
        flash(result['error'], 'error')
    
    return redirect(request.referrer or url_for('files.case_files', case_id=case_id))


@files_bp.route('/case/<int:case_id>/bulk_unhide', methods=['POST'])
@login_required
def bulk_unhide(case_id):
    """Bulk unhide files"""
    from main import db
    from hidden_files import bulk_unhide_files
    
    file_ids = request.form.getlist('file_ids', type=int)
    
    if not file_ids:
        flash('No files selected', 'warning')
        return redirect(url_for('files.view_hidden_files', case_id=case_id))
    
    result = bulk_unhide_files(db.session, case_id, file_ids, current_user.id)
    
    if result['success']:
        flash(f"✓ Unhid {result['count']} file(s)", 'success')
    else:
        flash(result['error'], 'error')
    
    return redirect(url_for('files.view_hidden_files', case_id=case_id))


@files_bp.route('/case/<int:case_id>/file/<int:file_id>/status')
@login_required
def file_status(case_id, file_id):
    """Get file processing status (AJAX endpoint)"""
    from main import db, CaseFile
    
    file = db.session.get(CaseFile, file_id)
    
    if not file or file.case_id != case_id:
        return jsonify({'error': 'File not found'}), 404
    
    return jsonify({
        'status': file.indexing_status,
        'is_indexed': file.is_indexed,
        'is_hidden': file.is_hidden,
        'event_count': file.event_count,
        'sigma_event_count': file.sigma_event_count,
        'ioc_event_count': file.ioc_event_count
    })


@files_bp.route('/case/<int:case_id>/bulk_import/scan')
@login_required
def bulk_import_scan(case_id):
    """
    Scan bulk import directory and return file counts
    GET endpoint for status check
    """
    from bulk_import import get_bulk_import_stats
    
    stats = get_bulk_import_stats()
    return jsonify(stats)


@files_bp.route('/case/<int:case_id>/bulk_import/start', methods=['POST'])
@login_required
def bulk_import_start(case_id):
    """
    Start bulk import process from local directory
    POST endpoint to trigger Celery task
    """
    from main import db, Case
    from tasks import bulk_import_directory
    
    # Verify case exists
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'error': 'Case not found'}), 404
    
    # Trigger Celery task
    task = bulk_import_directory.delay(case_id)
    
    logger.info(f"[BULK IMPORT] Started task {task.id} for case {case_id}")
    
    return jsonify({
        'status': 'started',
        'task_id': task.id,
        'message': 'Bulk import started'
    })


@files_bp.route('/case/<int:case_id>/bulk_import/status/<task_id>')
@login_required
def bulk_import_status(case_id, task_id):
    """
    Check status of bulk import task
    GET endpoint for progress updates
    """
    from celery.result import AsyncResult
    
    task = AsyncResult(task_id)
    
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Waiting to start...'
        }
    elif task.state == 'PROGRESS':
        response = {
            'state': task.state,
            'status': task.info.get('stage', 'Processing...'),
            'progress': task.info.get('progress', 0),
            'details': task.info
        }
    elif task.state == 'SUCCESS':
        response = {
            'state': task.state,
            'status': 'Complete',
            'progress': 100,
            'result': task.info
        }
    elif task.state == 'FAILURE':
        response = {
            'state': task.state,
            'status': 'Failed',
            'error': str(task.info)
        }
    else:
        response = {
            'state': task.state,
            'status': str(task.state)
        }
    
    return jsonify(response)


@files_bp.route('/case/<int:case_id>/file/<int:file_id>/reindex', methods=['POST'])
@login_required
def reindex_single_file(case_id, file_id):
    """Re-index a single file (clears all data and rebuilds)"""
    from main import db, CaseFile, opensearch_client
    from bulk_operations import clear_file_sigma_violations, clear_file_ioc_matches
    from tasks import process_file
    
    case_file = db.session.get(CaseFile, file_id)
    
    if not case_file or case_file.case_id != case_id:
        flash('File not found', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Clear OpenSearch index for this file
    if case_file.opensearch_key:
        try:
            # IMPORTANT: Use make_index_name() to ensure consistent index name generation
            # (handles lowercase, spaces->underscores, etc.)
            from utils import make_index_name
            index_name = make_index_name(case_id, case_file.original_filename)
            opensearch_client.indices.delete(index=index_name, ignore=[400, 404])
            logger.info(f"[REINDEX SINGLE] Deleted index {index_name}")
        except Exception as e:
            logger.warning(f"[REINDEX SINGLE] Could not delete index: {e}")
    
    # Clear SIGMA and IOC data
    clear_file_sigma_violations(db, file_id)
    clear_file_ioc_matches(db, file_id)
    
    # Reset file metadata
    case_file.event_count = 0
    case_file.violation_count = 0
    case_file.ioc_event_count = 0
    case_file.is_indexed = False
    case_file.indexing_status = 'Queued'
    case_file.opensearch_key = None
    
    db.session.commit()
    
    # Queue for full reprocessing
    process_file.delay(file_id)
    
    flash(f'Re-indexing queued for "{case_file.original_filename}". All data will be cleared and rebuilt.', 'success')
    return redirect(url_for('files.case_files', case_id=case_id))


@files_bp.route('/case/<int:case_id>/file/<int:file_id>/rechainsaw', methods=['POST'])
@login_required
def rechainsaw_single_file(case_id, file_id):
    """Re-run SIGMA on a single file"""
    from main import db, CaseFile
    from bulk_operations import clear_file_sigma_violations
    from file_processing import chainsaw_file
    from models import SigmaRule, SigmaViolation
    
    case_file = db.session.get(CaseFile, file_id)
    
    if not case_file or case_file.case_id != case_id:
        flash('File not found', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    if not case_file.is_indexed:
        flash('File must be indexed before SIGMA testing', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Clear existing violations
    clear_file_sigma_violations(db, file_id)
    case_file.violation_count = 0
    case_file.indexing_status = 'SIGMA Testing'
    db.session.commit()
    
    # Run chainsaw synchronously (fast operation)
    try:
        from main import opensearch_client
        result = chainsaw_file(
            db=db,
            opensearch_client=opensearch_client,
            CaseFile=CaseFile,
            SigmaRule=SigmaRule,
            SigmaViolation=SigmaViolation,
            file_id=file_id
        )
        
        if result['status'] == 'success':
            flash(f'SIGMA re-processing complete for "{case_file.original_filename}". Found {result.get("violations_found", 0)} violations.', 'success')
        else:
            flash(f'SIGMA re-processing failed: {result.get("message")}', 'error')
    except Exception as e:
        logger.error(f"[RECHAINSAW SINGLE] Error: {e}", exc_info=True)
        flash(f'SIGMA re-processing failed: {str(e)}', 'error')
    
    return redirect(url_for('files.case_files', case_id=case_id))


@files_bp.route('/case/<int:case_id>/file/<int:file_id>/details')
@login_required
def file_details(case_id, file_id):
    """View detailed information about a specific file"""
    from main import db, CaseFile, Case
    
    case = db.session.get(Case, case_id)
    case_file = db.session.get(CaseFile, file_id)
    
    if not case or not case_file or case_file.case_id != case_id:
        flash('File not found', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    return render_template('file_details.html',
                          case=case,
                          file=case_file)


@files_bp.route('/case/<int:case_id>/bulk_reindex_selected', methods=['POST'])
@login_required
def bulk_reindex_selected(case_id):
    """Re-index selected files (clears all data and rebuilds)"""
    from main import db, CaseFile, opensearch_client
    from bulk_operations import clear_file_sigma_violations, clear_file_ioc_matches, reset_file_metadata, queue_file_processing
    from tasks import process_file
    from celery_health import check_workers_available
    
    # Safety check: Ensure Celery workers are available
    workers_ok, worker_count, error_msg = check_workers_available(min_workers=1)
    if not workers_ok:
        flash(f'⚠️ Cannot start bulk operation: {error_msg}. Please check Celery workers.', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    file_ids = request.form.getlist('file_ids', type=int)
    
    if not file_ids:
        flash('No files selected', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Get all selected files
    files = db.session.query(CaseFile).filter(
        CaseFile.id.in_(file_ids),
        CaseFile.case_id == case_id,
        CaseFile.is_deleted == False
    ).all()
    
    if not files:
        flash('No valid files found', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Process each file
    for file in files:
        # Clear OpenSearch index
        if file.opensearch_key:
            try:
                # IMPORTANT: Use make_index_name() to ensure consistent index name generation
                from utils import make_index_name
                index_name = make_index_name(case_id, file.original_filename)
                opensearch_client.indices.delete(index=index_name, ignore=[400, 404])
            except Exception as e:
                logger.warning(f"[BULK REINDEX SELECTED] Could not delete index for file {file.id}: {e}")
        
        # Clear SIGMA and IOC data
        clear_file_sigma_violations(db, file.id)
        clear_file_ioc_matches(db, file.id)
        
        # Reset file metadata
        reset_file_metadata(file, reset_opensearch_key=True)
    
    db.session.commit()
    
    # Queue for full reprocessing
    queue_file_processing(process_file, files, operation='full')
    
    flash(f'Re-indexing queued for {len(files)} selected file(s). All data will be cleared and rebuilt.', 'success')
    return redirect(url_for('files.case_files', case_id=case_id))


@files_bp.route('/case/<int:case_id>/bulk_rechainsaw_selected', methods=['POST'])
@login_required
def bulk_rechainsaw_selected(case_id):
    """Re-run SIGMA on selected files"""
    from main import db, CaseFile
    from bulk_operations import clear_file_sigma_violations, queue_file_processing
    from tasks import process_file
    from celery_health import check_workers_available
    
    # Safety check: Ensure Celery workers are available
    workers_ok, worker_count, error_msg = check_workers_available(min_workers=1)
    if not workers_ok:
        flash(f'⚠️ Cannot start bulk operation: {error_msg}. Please check Celery workers.', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    file_ids = request.form.getlist('file_ids', type=int)
    
    if not file_ids:
        flash('No files selected', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Get all selected files that are indexed
    files = db.session.query(CaseFile).filter(
        CaseFile.id.in_(file_ids),
        CaseFile.case_id == case_id,
        CaseFile.is_deleted == False,
        CaseFile.is_indexed == True
    ).all()
    
    if not files:
        flash('No valid indexed files found', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Clear SIGMA data for each file and set to Queued status
    for file in files:
        clear_file_sigma_violations(db, file.id)
        file.violation_count = 0
        file.indexing_status = 'Queued'
        file.celery_task_id = None
    
    db.session.commit()
    
    # Queue for SIGMA reprocessing
    queue_file_processing(process_file, files, operation='chainsaw_only')
    
    flash(f'SIGMA re-processing queued for {len(files)} selected file(s). Old violations will be cleared.', 'success')
    return redirect(url_for('files.case_files', case_id=case_id))


@files_bp.route('/case/<int:case_id>/bulk_rehunt_selected', methods=['POST'])
@login_required
def bulk_rehunt_selected(case_id):
    """Re-hunt IOCs on selected files"""
    from main import db, CaseFile
    from bulk_operations import clear_file_ioc_matches, queue_file_processing
    from tasks import process_file
    from celery_health import check_workers_available
    
    # Safety check: Ensure Celery workers are available
    workers_ok, worker_count, error_msg = check_workers_available(min_workers=1)
    if not workers_ok:
        flash(f'⚠️ Cannot start bulk operation: {error_msg}. Please check Celery workers.', 'error')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    file_ids = request.form.getlist('file_ids', type=int)
    
    if not file_ids:
        flash('No files selected', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Get all selected files that are indexed
    files = db.session.query(CaseFile).filter(
        CaseFile.id.in_(file_ids),
        CaseFile.case_id == case_id,
        CaseFile.is_deleted == False,
        CaseFile.is_indexed == True
    ).all()
    
    if not files:
        flash('No valid indexed files found', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Clear IOC data for each file and set to Queued status
    for file in files:
        clear_file_ioc_matches(db, file.id)
        file.ioc_event_count = 0
        file.indexing_status = 'Queued'
        file.celery_task_id = None
    
    db.session.commit()
    
    # Queue for IOC reprocessing
    queue_file_processing(process_file, files, operation='ioc_only')
    
    flash(f'IOC re-hunting queued for {len(files)} selected file(s). Old matches will be cleared.', 'success')
    return redirect(url_for('files.case_files', case_id=case_id))


@files_bp.route('/case/<int:case_id>/bulk_hide_selected', methods=['POST'])
@login_required
def bulk_hide_selected(case_id):
    """Hide selected files"""
    from main import db, CaseFile
    
    file_ids = request.form.getlist('file_ids', type=int)
    
    if not file_ids:
        flash('No files selected', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Get all selected files
    files = db.session.query(CaseFile).filter(
        CaseFile.id.in_(file_ids),
        CaseFile.case_id == case_id,
        CaseFile.is_deleted == False
    ).all()
    
    if not files:
        flash('No valid files found', 'warning')
        return redirect(url_for('files.case_files', case_id=case_id))
    
    # Hide all selected files
    for file in files:
        file.is_hidden = True
    
    db.session.commit()
    
    flash(f'Hidden {len(files)} selected file(s). View them on the Hidden Files page.', 'success')
    return redirect(url_for('files.case_files', case_id=case_id))

@files_bp.route('/case/<int:case_id>/queue/cleanup', methods=['POST'])
@login_required
def queue_cleanup_case(case_id):
    """Per-case queue cleanup"""
    from main import db, Case, CaseFile
    from queue_cleanup import cleanup_queue
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'status': 'error', 'message': 'Case not found'}), 404
    
    try:
        result = cleanup_queue(db, CaseFile, case_id=case_id)
        
        if result['status'] == 'success':
            flash(result['message'], 'success')
        else:
            flash(result['message'], 'error')
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Queue cleanup error (case {case_id}): {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


@files_bp.route('/case/<int:case_id>/queue/health')
@login_required
def queue_health_case(case_id):
    """Get queue health status for specific case"""
    from main import db, Case, CaseFile
    from queue_cleanup import get_queue_health
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'status': 'error', 'message': 'Case not found'}), 404
    
    try:
        health = get_queue_health(db, CaseFile, case_id=case_id)
        return jsonify(health)
    
    except Exception as e:
        logger.error(f"Queue health check error (case {case_id}): {e}", exc_info=True)
        return jsonify({
            'health_status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


@files_bp.route('/case/<int:case_id>/file-stats')
@login_required
def file_stats_case(case_id):
    """Get file statistics for auto-refresh"""
    from main import db, Case, CaseFile
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'status': 'error', 'message': 'Case not found'}), 404
    
    try:
        # Count by status
        completed = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status == 'Completed',
            CaseFile.is_deleted == False
        ).count()
        
        queued = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status == 'Queued',
            CaseFile.is_deleted == False
        ).count()
        
        indexing = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status == 'Indexing',
            CaseFile.is_deleted == False
        ).count()
        
        sigma = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status == 'SIGMA Testing',
            CaseFile.is_deleted == False
        ).count()
        
        ioc_hunting = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status == 'SIGMA Hunting',
            CaseFile.is_deleted == False
        ).count()
        
        failed = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status.like('Failed%'),
            CaseFile.is_deleted == False
        ).count()
        
        return jsonify({
            'status': 'success',
            'completed': completed,
            'queued': queued,
            'indexing': indexing,
            'sigma': sigma,
            'ioc_hunting': ioc_hunting,
            'failed': failed
        })
    
    except Exception as e:
        logger.error(f"File stats error (case {case_id}): {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


@files_bp.route('/case/<int:case_id>/queue/status')
@login_required
def queue_status_case(case_id):
    """Get detailed queue status including file lists"""
    from main import db, Case, CaseFile
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'status': 'error', 'message': 'Case not found'}), 404
    
    try:
        # Get queued files
        queued_files = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status == 'Queued',
            CaseFile.is_deleted == False
        ).order_by(CaseFile.id).limit(100).all()
        
        # Get failed files (not hidden)
        failed_files = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status.like('Failed%'),
            CaseFile.is_hidden == False,
            CaseFile.is_deleted == False
        ).count()
        
        # Get actively processing
        processing = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status.in_(['Indexing', 'SIGMA Testing', 'SIGMA Hunting']),
            CaseFile.is_deleted == False
        ).all()
        
        return jsonify({
            'status': 'success',
            'queued': [{
                'id': f.id,
                'filename': f.original_filename,
                'status': f.indexing_status
            } for f in queued_files],
            'queued_count': len(queued_files),
            'failed_count': failed_files,
            'processing': [{
                'id': f.id,
                'filename': f.original_filename,
                'status': f.indexing_status
            } for f in processing],
            'processing_count': len(processing)
        })
    
    except Exception as e:
        logger.error(f"Queue status error (case {case_id}): {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


@files_bp.route('/case/<int:case_id>/queue/requeue-failed', methods=['POST'])
@login_required
def requeue_failed_files(case_id):
    """Requeue all failed files that are not hidden"""
    from main import db, Case, CaseFile
    from celery_app import celery_app
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'status': 'error', 'message': 'Case not found'}), 404
    
    try:
        # Find all failed files that are NOT hidden
        failed_files = db.session.query(CaseFile).filter(
            CaseFile.case_id == case_id,
            CaseFile.indexing_status.like('Failed%'),
            CaseFile.is_hidden == False,
            CaseFile.is_deleted == False
        ).all()
        
        if not failed_files:
            return jsonify({
                'status': 'success',
                'message': 'No failed files to requeue',
                'requeued': 0
            })
        
        requeued = 0
        errors = 0
        
        for case_file in failed_files:
            try:
                # Submit task to Celery
                task = celery_app.send_task(
                    'tasks.process_file',
                    args=[case_file.id]
                )
                
                # Update database
                case_file.indexing_status = 'Queued'
                case_file.celery_task_id = task.id
                db.session.commit()
                
                requeued += 1
                
            except Exception as e:
                errors += 1
                logger.error(f"Error requeueing file {case_file.id}: {e}")
                db.session.rollback()
        
        message = f'✅ Requeued {requeued} failed file(s)'
        if errors > 0:
            message += f' (⚠️ {errors} error(s))'
        
        return jsonify({
            'status': 'success',
            'message': message,
            'requeued': requeued,
            'errors': errors
        })
    
    except Exception as e:
        logger.error(f"Requeue failed files error (case {case_id}): {e}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500
