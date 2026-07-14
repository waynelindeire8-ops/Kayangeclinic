from flask import Blueprint, jsonify, render_template
from flask_jwt_extended import get_jwt
from app.auth import login_required
from app.backup import sync_all, restore_all, sync_table, restore_table, init_supabase_tables, get_sync_status, get_last_sync_info, SUPABASE_TABLES

backup_bp = Blueprint('backup', __name__, url_prefix='/backup')


@backup_bp.route('/', strict_slashes=False)
@login_required
def backup_page():
    current_user = get_jwt()
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    return render_template('backup/index.html')


@backup_bp.route('/sync', methods=['POST'])
@login_required
def api_sync_all():
    current_user = get_jwt()
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    results = sync_all()
    return jsonify({'message': 'Sync completed', 'results': results})


@backup_bp.route('/sync/<table_name>', methods=['POST'])
@login_required
def api_sync_table(table_name):
    current_user = get_jwt()
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    if table_name not in SUPABASE_TABLES:
        return jsonify({'error': 'Invalid table'}), 400
    count = sync_table(table_name)
    return jsonify({'message': f'Synced {count} rows', 'count': count})


@backup_bp.route('/restore', methods=['POST'])
@login_required
def api_restore_all():
    current_user = get_jwt()
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    results = restore_all()
    return jsonify({'message': 'Restore completed', 'results': results})


@backup_bp.route('/restore/<table_name>', methods=['POST'])
@login_required
def api_restore_table(table_name):
    current_user = get_jwt()
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    if table_name not in SUPABASE_TABLES:
        return jsonify({'error': 'Invalid table'}), 400
    count = restore_table(table_name)
    return jsonify({'message': f'Restored {count} rows', 'count': count})


@backup_bp.route('/init', methods=['POST'])
@login_required
def api_init_tables():
    current_user = get_jwt()
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    try:
        success = init_supabase_tables()
        if success:
            return jsonify({'message': 'Tables initialized successfully'})
        else:
            return jsonify({'error': 'Failed to initialize tables. Check Supabase connection settings.'}), 500
    except Exception as e:
        return jsonify({'error': f'Connection failed: {str(e)}'}), 500


@backup_bp.route('/status', methods=['GET'])
@login_required
def api_sync_status():
    current_user = get_jwt()
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    logs = get_sync_status()
    return jsonify(logs)


@backup_bp.route('/auto-status', methods=['GET'])
@login_required
def api_auto_status():
    current_user = get_jwt()
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    info = get_last_sync_info()
    try:
        from app.backup import HAS_PG, _get_sync_interval
        info['supabase_configured'] = HAS_PG
        info['interval_minutes'] = _get_sync_interval()
    except Exception:
        info['supabase_configured'] = False
        info['interval_minutes'] = 5
    return jsonify(info)


@backup_bp.route('/tables', methods=['GET'])
@login_required
def api_tables_list():
    current_user = get_jwt()
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    return jsonify(SUPABASE_TABLES)
