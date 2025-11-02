"""
Case Management Routes Blueprint
Handles case CRUD operations and administration
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
from functools import wraps
import logging

cases_bp = Blueprint('cases', __name__)
logger = logging.getLogger(__name__)


def admin_required(f):
    """Decorator to require administrator role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'administrator':
            flash('Administrator access required', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@cases_bp.route('/admin/cases')
@login_required
@admin_required
def case_management():
    """Case Management Dashboard - List all cases with admin options"""
    from main import db, Case, User, CaseFile
    
    # Get all cases with file counts
    cases = db.session.query(Case).order_by(Case.created_at.desc()).all()
    
    # Get file counts for each case
    case_data = []
    for case in cases:
        file_count = db.session.query(CaseFile).filter_by(
            case_id=case.id, is_deleted=False
        ).count()
        
        creator_name = 'Unknown'
        if case.created_by:
            creator = db.session.get(User, case.created_by)
            creator_name = creator.full_name or creator.username if creator else 'Unknown'
        
        assignee_name = 'Unassigned'
        if case.assigned_to:
            assignee = db.session.get(User, case.assigned_to)
            assignee_name = assignee.full_name or assignee.username if assignee else 'Unassigned'
        
        case_data.append({
            'case': case,
            'file_count': file_count,
            'creator_name': creator_name,
            'assignee_name': assignee_name
        })
    
    return render_template('admin_cases.html', case_data=case_data)


@cases_bp.route('/case/<int:case_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_case(case_id):
    """Edit case details (reusable page for both admin and case owner)"""
    from main import db, Case, User
    
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Check permissions: admin or case creator
    if current_user.role != 'admin' and case.created_by != current_user.id:
        flash('Permission denied', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        # Track changes for audit log
        changes = {}
        old_name = case.name
        old_description = case.description
        old_company = case.company
        old_status = case.status
        old_assigned_to = case.assigned_to
        
        case.name = request.form.get('name', case.name)
        case.description = request.form.get('description', case.description)
        case.company = request.form.get('company', case.company)
        case.status = request.form.get('status', case.status)
        
        # Track what changed
        if old_name != case.name:
            changes['name'] = {'from': old_name, 'to': case.name}
        if old_description != case.description:
            changes['description'] = 'updated'
        if old_company != case.company:
            changes['company'] = {'from': old_company, 'to': case.company}
        if old_status != case.status:
            changes['status'] = {'from': old_status, 'to': case.status}
        
        # Only admin can change assignment
        if current_user.role == 'admin':
            assigned_to = request.form.get('assigned_to')
            case.assigned_to = int(assigned_to) if assigned_to and assigned_to != '' else None
            if old_assigned_to != case.assigned_to:
                changes['assigned_to'] = {'from': old_assigned_to, 'to': case.assigned_to}
        
        db.session.commit()
        
        # Audit log
        from audit_logger import log_action
        log_action('edit_case', resource_type='case', resource_id=case_id,
                  resource_name=case.name, details=changes)
        
        flash('Case updated successfully', 'success')
        
        # Redirect back to referring page or case dashboard
        return_to = request.form.get('return_to', 'case')
        if return_to == 'admin':
            return redirect(url_for('cases.case_management'))
        else:
            return redirect(url_for('view_case', case_id=case_id))
    
    # GET: Show edit form
    users = db.session.query(User).filter_by(is_active=True).order_by(User.full_name).all()
    return render_template('case_edit.html', case=case, users=users)


@cases_bp.route('/case/<int:case_id>/toggle_status', methods=['POST'])
@login_required
@admin_required
def toggle_case_status(case_id):
    """Toggle case status between active and closed"""
    from main import db, Case
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'success': False, 'error': 'Case not found'}), 404
    
    # Toggle status
    case.status = 'closed' if case.status == 'active' else 'active'
    db.session.commit()
    
    return jsonify({'success': True, 'status': case.status})


@cases_bp.route('/case/<int:case_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_case(case_id):
    """Delete a case and all associated data (admin only)"""
    from main import db, Case, CaseFile, SigmaViolation, IOCMatch, TimelineTag, opensearch_client
    
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({'success': False, 'error': 'Case not found'}), 404
    
    try:
        # Get all files for OpenSearch cleanup
        files = db.session.query(CaseFile).filter_by(case_id=case_id).all()
        
        # Delete OpenSearch indices
        deleted_indices = 0
        for file in files:
            if file.opensearch_key:
                # IMPORTANT: Use make_index_name() to ensure consistent index name generation
                from utils import make_index_name
                index_name = make_index_name(case_id, file.original_filename)
                try:
                    if opensearch_client.indices.exists(index=index_name):
                        opensearch_client.indices.delete(index=index_name)
                        deleted_indices += 1
                except Exception as e:
                    logger.warning(f"Failed to delete index {index_name}: {e}")
        
        # Delete database records (cascade should handle most)
        db.session.query(TimelineTag).filter_by(case_id=case_id).delete()
        db.session.query(IOCMatch).filter_by(case_id=case_id).delete()
        db.session.query(SigmaViolation).filter_by(case_id=case_id).delete()
        db.session.query(CaseFile).filter_by(case_id=case_id).delete()
        
        # Store case name before deletion
        case_name = case.name
        
        # Delete the case itself
        db.session.delete(case)
        db.session.commit()
        
        # Audit log
        from audit_logger import log_action
        log_action('delete_case', resource_type='case', resource_id=case_id,
                  resource_name=case_name, 
                  details={'indices_deleted': deleted_indices, 'files_deleted': len(files)})
        
        logger.info(f"[ADMIN] Case {case_id} deleted by user {current_user.id}: {deleted_indices} indices, {len(files)} files")
        
        return jsonify({
            'success': True,
            'message': f'Case deleted: {deleted_indices} indices, {len(files)} files'
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN] Error deleting case {case_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

