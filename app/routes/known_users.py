"""
Known Users Management Routes
Handles legitimate/valid users in the environment (not CaseScope app users)
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
from datetime import datetime
import csv
import io

known_users_bp = Blueprint('known_users', __name__)


@known_users_bp.route('/known_users')
@login_required
def list_known_users():
    """Known Users management page"""
    from main import db
    from models import KnownUser
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search_query = request.args.get('search', '').strip()
    
    # Base query
    query = KnownUser.query
    
    # Apply search filter
    if search_query:
        query = query.filter(KnownUser.username.ilike(f'%{search_query}%'))
    
    # Get paginated results
    pagination = query.order_by(KnownUser.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    known_users = pagination.items
    
    # Calculate stats
    total_users = KnownUser.query.count()
    domain_users = KnownUser.query.filter_by(user_type='domain').count()
    local_users = KnownUser.query.filter_by(user_type='local').count()
    compromised_users = KnownUser.query.filter_by(compromised=True).count()
    
    return render_template('known_users.html',
                         known_users=known_users,
                         pagination=pagination,
                         search_query=search_query,
                         total_users=total_users,
                         domain_users=domain_users,
                         local_users=local_users,
                         compromised_users=compromised_users)


@known_users_bp.route('/known_users/add', methods=['POST'])
@login_required
def add_known_user():
    """Add new known user manually"""
    # Permission check: Read-only users cannot add
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot add known users'}), 403
    
    from main import db
    from models import KnownUser
    
    try:
        username = request.form.get('username', '').strip()
        user_type = request.form.get('user_type', '-').strip()
        compromised = request.form.get('compromised') == 'true'
        
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
        
        # Validate user_type
        if user_type not in ['domain', 'local', '-']:
            user_type = '-'
        
        # Check for duplicate
        existing = KnownUser.query.filter_by(username=username).first()
        if existing:
            return jsonify({'success': False, 'error': f'User "{username}" already exists'}), 400
        
        # Create known user
        known_user = KnownUser(
            username=username,
            user_type=user_type,
            compromised=compromised,
            added_method='manual',
            added_by=current_user.id
        )
        db.session.add(known_user)
        db.session.commit()
        
        flash(f'Known user added: {username}', 'success')
        return jsonify({'success': True, 'user_id': known_user.id})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@known_users_bp.route('/known_users/<int:user_id>/update', methods=['POST'])
@login_required
def update_known_user(user_id):
    """Update known user"""
    # Permission check: Read-only users cannot update
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot update known users'}), 403
    
    from main import db
    from models import KnownUser
    
    try:
        known_user = db.session.get(KnownUser, user_id)
        if not known_user:
            return jsonify({'success': False, 'error': 'Known user not found'}), 404
        
        # Update fields
        if 'username' in request.form:
            new_username = request.form['username'].strip()
            if not new_username:
                return jsonify({'success': False, 'error': 'Username cannot be empty'}), 400
            
            # Check for duplicate (excluding current user)
            existing = KnownUser.query.filter(
                KnownUser.username == new_username,
                KnownUser.id != user_id
            ).first()
            if existing:
                return jsonify({'success': False, 'error': f'User "{new_username}" already exists'}), 400
            
            known_user.username = new_username
        
        if 'user_type' in request.form:
            user_type = request.form['user_type'].strip()
            if user_type in ['domain', 'local', '-']:
                known_user.user_type = user_type
        
        if 'compromised' in request.form:
            known_user.compromised = request.form['compromised'] == 'true'
        
        db.session.commit()
        
        flash(f'Known user updated: {known_user.username}', 'success')
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@known_users_bp.route('/known_users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_known_user(user_id):
    """Delete known user"""
    # Permission check: Only administrators can delete
    if current_user.role not in ['administrator']:
        return jsonify({'success': False, 'error': 'Only administrators can delete known users'}), 403
    
    from main import db
    from models import KnownUser
    
    try:
        known_user = db.session.get(KnownUser, user_id)
        if not known_user:
            return jsonify({'success': False, 'error': 'Known user not found'}), 404
        
        username = known_user.username
        db.session.delete(known_user)
        db.session.commit()
        
        flash(f'Known user deleted: {username}', 'success')
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@known_users_bp.route('/known_users/upload_csv', methods=['POST'])
@login_required
def upload_csv():
    """Upload CSV file with known users"""
    # Permission check: Read-only users cannot upload
    if current_user.role == 'read-only':
        return jsonify({'success': False, 'error': 'Read-only users cannot upload CSV'}), 403
    
    from main import db
    from models import KnownUser
    
    if 'csv_file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    
    file = request.files['csv_file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'error': 'File must be a CSV'}), 400
    
    try:
        # Read CSV file (utf-8-sig handles BOM characters)
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        csv_reader = csv.DictReader(stream)
        
        # Build case-insensitive header mapping
        if not csv_reader.fieldnames:
            return jsonify({'success': False, 'error': 'CSV file is empty or invalid'}), 400
        
        header_map = {h.lower().strip(): h for h in csv_reader.fieldnames}
        
        # Validate required headers
        if 'username' not in header_map:
            return jsonify({'success': False, 'error': f'CSV must have "Username" column. Found columns: {", ".join(csv_reader.fieldnames)}'}), 400
        
        added_count = 0
        skipped_count = 0
        errors = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # start=2 because row 1 is headers
            try:
                # Extract data using case-insensitive mapping
                username_col = header_map.get('username')
                type_col = header_map.get('type')
                compromised_col = header_map.get('compromised')
                
                username = row.get(username_col, '').strip() if username_col else ''
                user_type = row.get(type_col, '-').strip().lower() if type_col else '-'
                compromised_str = row.get(compromised_col, 'false').strip().lower() if compromised_col else 'false'
                
                if not username:
                    skipped_count += 1
                    continue
                
                # Validate user_type
                if user_type not in ['domain', 'local']:
                    user_type = '-'
                
                # Parse compromised
                compromised = compromised_str in ['true', 't', 'yes', 'y', '1']
                
                # Check for duplicate
                existing = KnownUser.query.filter_by(username=username).first()
                if existing:
                    skipped_count += 1
                    continue
                
                # Create known user
                known_user = KnownUser(
                    username=username,
                    user_type=user_type,
                    compromised=compromised,
                    added_method='csv',
                    added_by=current_user.id
                )
                db.session.add(known_user)
                added_count += 1
                
            except Exception as row_error:
                errors.append(f"Row {row_num}: {str(row_error)}")
                skipped_count += 1
        
        db.session.commit()
        
        # Build result message
        message = f'CSV import complete: {added_count} users added'
        if skipped_count > 0:
            message += f', {skipped_count} skipped (duplicates or invalid)'
        
        if errors:
            message += f'. Errors: {"; ".join(errors[:5])}'  # Show first 5 errors
        
        flash(message, 'success' if added_count > 0 else 'warning')
        return jsonify({
            'success': True,
            'added': added_count,
            'skipped': skipped_count,
            'errors': errors
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'CSV processing error: {str(e)}'}), 500


@known_users_bp.route('/known_users/export_csv')
@login_required
def export_csv():
    """Export all known users to CSV"""
    from main import db
    from models import KnownUser, User
    import csv
    from flask import Response
    
    try:
        # Get all known users
        known_users = KnownUser.query.order_by(KnownUser.username).all()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Username', 'Type', 'Compromised', 'Added Method', 'Added By', 'Date Added'])
        
        # Write data
        for ku in known_users:
            creator = db.session.get(User, ku.added_by)
            creator_name = creator.username if creator else 'Unknown'
            
            writer.writerow([
                ku.username,
                ku.user_type,
                'true' if ku.compromised else 'false',
                ku.added_method,
                creator_name,
                ku.created_at.strftime('%Y-%m-%d %H:%M:%S') if ku.created_at else ''
            ])
        
        # Create response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=known_users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'}
        )
    
    except Exception as e:
        flash(f'Export failed: {str(e)}', 'error')
        return redirect(url_for('known_users.list_known_users'))

