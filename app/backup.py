import sqlite3
import re
import json
import logging
import threading
import queue
import time
import os
import gzip
import base64
from datetime import datetime, date
from config import Config

try:
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except ImportError:
    HAS_PG = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger(__name__)

SUPABASE_TABLES = [
    'system_config', 'audit_logs',
    'users', 'departments', 'insurance_providers',
    'patients', 'patient_allergies', 'patient_medical_history', 'patient_medications',
    'patient_insurance',
    'appointments', 'consultations', 'vital_signs', 'medical_examinations', 'diagnoses',
    'prescription_orders', 'prescriptions', 'prescription_refills',
    'pharmacy_inventory', 'pharmacy_dispensing',
    'lab_test_catalog', 'lab_tests', 'lab_test_results',
    'billing', 'billing_items',
    'insurance_claims', 'claim_items', 'claim_status_history',
    'insurance_authorization_rules', 'medical_certificates',
    'packages', 'package_services',
    'procedures', 'referrals', 'messages', 'notifications',
    'radiology_orders', 'radiology_results',
    'telemedicine_sessions', 'telemedicine_messages', 'telemedicine_payments', 'telemedicine_recordings',
    'short_stay_beds', 'short_stay_drip_stations', 'short_stay_admissions',
    'drug_scheme_prices', 'lab_invoices', 'lab_invoice_items', 'suppliers',
]


def _get_pg_type(col_type):
    col_type = col_type.upper()
    if 'INT' in col_type:
        return 'BIGINT'
    elif 'REAL' in col_type or 'FLOAT' in col_type or 'DOUBLE' in col_type:
        return 'DOUBLE PRECISION'
    elif 'TEXT' in col_type or 'VARCHAR' in col_type or 'CHAR' in col_type:
        return 'TEXT'
    elif 'BLOB' in col_type:
        return 'BYTEA'
    elif 'BOOL' in col_type:
        return 'BOOLEAN'
    elif 'DATE' in col_type and 'TIME' not in col_type:
        return 'DATE'
    elif 'TIMESTAMP' in col_type:
        return 'TIMESTAMP'
    elif 'NUMERIC' in col_type or 'DECIMAL' in col_type:
        return 'NUMERIC'
    else:
        return 'TEXT'


def _get_pg_conn():
    if not HAS_PG:
        raise RuntimeError('psycopg2 not installed. Run: pip install psycopg2-binary')
    try:
        return psycopg2.connect(Config.SUPABASE_DB_URL)
    except Exception:
        return psycopg2.connect(
            host=Config.SUPABASE_DB_HOST,
            port=Config.SUPABASE_DB_PORT,
            dbname='postgres',
            user=Config.SUPABASE_DB_USER,
            password=Config.SUPABASE_DB_PASSWORD,
            sslmode='require'
        )


def _get_unique_constraints(table_name):
    """Get unique constraint columns for a table from PostgreSQL."""
    try:
        pg = _get_pg_conn()
        cur = pg.cursor()
        cur.execute('''
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = %s
                AND tc.table_schema = 'public'
                AND tc.constraint_type = 'UNIQUE'
            ORDER BY tc.constraint_name, kcu.ordinal_position
        ''', (table_name,))
        cols = [row[0] for row in cur.fetchall()]
        cur.close()
        pg.close()
        return cols
    except Exception:
        return []


def _get_primary_key(table_name):
    """Get primary key columns for a table from PostgreSQL."""
    try:
        pg = _get_pg_conn()
        cur = pg.cursor()
        cur.execute('''
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = %s
                AND tc.table_schema = 'public'
                AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        ''', (table_name,))
        cols = [row[0] for row in cur.fetchall()]
        cur.close()
        pg.close()
        return cols
    except Exception:
        return []


def _adapt_value(val):
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, bytes):
        return val.hex()
    if isinstance(val, bool):
        return int(val)
    return val


def init_supabase_tables():
    """Create all tables in Supabase PostgreSQL."""
    try:
        pg = _get_pg_conn()
        cur = pg.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS _sync_log (
                id SERIAL PRIMARY KEY,
                table_name TEXT NOT NULL,
                operation TEXT NOT NULL,
                synced_at TIMESTAMP DEFAULT NOW()
            )
        """)

        sqlite_db = sqlite3.connect(Config.DATABASE, timeout=30)
        sqlite_db.row_factory = sqlite3.Row

        for table_name in SUPABASE_TABLES:
            try:
                schema = sqlite_db.execute(
                    f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'"
                ).fetchone()
                if not schema or not schema['sql']:
                    continue

                create_sql = schema['sql']

                create_sql = re.sub(
                    r'\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b',
                    'SERIAL PRIMARY KEY', create_sql, flags=re.IGNORECASE
                )
                create_sql = re.sub(
                    r'\bINTEGER\s+PRIMARY\s+KEY\b',
                    'SERIAL PRIMARY KEY', create_sql, flags=re.IGNORECASE
                )
                create_sql = re.sub(r'\bAUTOINCREMENT\b', '', create_sql, flags=re.IGNORECASE)
                create_sql = re.sub(r'\bAUTO_INCREMENT\b', '', create_sql, flags=re.IGNORECASE)

                create_sql = re.sub(r'(?<!\w)INTEGER(?!\s+PRIMARY)', 'BIGINT', create_sql)
                create_sql = re.sub(r'(?<!\w)REAL(?!\w)', 'DOUBLE PRECISION', create_sql)
                create_sql = re.sub(r'(?<!\w)BLOB(?!\w)', 'BYTEA', create_sql)

                create_sql = re.sub(r',\s*FOREIGN KEY[^,)]*\([^)]*\)\s*REFERENCES[^,)]*\([^)]*\)(?:\s*ON DELETE[^,)]*)?', '', create_sql, flags=re.IGNORECASE)
                create_sql = re.sub(r'\bREFERENCES\s+\w+\s*\([^)]*\)(?:\s*ON DELETE[^,)]*)?', '', create_sql, flags=re.IGNORECASE)

                cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                cur.execute(create_sql)
                logger.info(f"Created/updated table: {table_name}")

            except Exception as e:
                logger.warning(f"Error creating table {table_name}: {e}")
                pg.rollback()
                pg = _get_pg_conn()
                cur = pg.cursor()
                continue

        pg.commit()
        sqlite_db.close()
        cur.close()
        pg.close()
        logger.info("Supabase tables initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize Supabase tables: {e}")
        return False


def sync_table(table_name):
    """Sync a single table from SQLite to Supabase using UPSERT."""
    try:
        pg = _get_pg_conn()
        cur = pg.cursor()

        sqlite_db = sqlite3.connect(Config.DATABASE, timeout=30)
        sqlite_db.row_factory = sqlite3.Row

        rows = sqlite_db.execute(f"SELECT * FROM {table_name}").fetchall()
        if not rows:
            sqlite_db.close()
            cur.close()
            pg.close()
            return 0

        columns = list(rows[0].keys())
        
        # Exclude 'id' column - let Supabase auto-generate it
        if 'id' in columns:
            columns = [c for c in columns if c != 'id']
        
        cols_str = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(columns))
        
        # Use primary key as conflict target
        pk_cols = _get_primary_key(table_name)
        if not pk_cols:
            pk_cols = ['id'] if 'id' in columns else [columns[0]]
        
        update_cols = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col not in pk_cols])
        pk_cols_str = ', '.join(pk_cols)

        if not update_cols:
            upsert_sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        else:
            upsert_sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders}) ON CONFLICT ({pk_cols_str}) DO UPDATE SET {update_cols}"

        count = 0
        batch_size = 100
        batch = []
        for row in rows:
            values = [_adapt_value(row[col]) for col in columns]
            batch.append(values)
            if len(batch) >= batch_size:
                try:
                    cur.executemany(upsert_sql, batch)
                    count += len(batch)
                    pg.commit()
                except Exception as e:
                    logger.warning(f"Batch error in {table_name}: {e}")
                    pg.rollback()
                    pg = _get_pg_conn()
                    cur = pg.cursor()
                batch = []

        # Process remaining batch
        if batch:
            try:
                cur.executemany(upsert_sql, batch)
                count += len(batch)
                pg.commit()
            except Exception as e:
                logger.warning(f"Final batch error in {table_name}: {e}")
                pg.rollback()

        cur.execute(
            "INSERT INTO _sync_log (table_name, operation, synced_at) VALUES (%s, %s, NOW())",
            (table_name, 'sync')
        )
        pg.commit()
        sqlite_db.close()
        cur.close()
        pg.close()
        logger.info(f"Synced {count} rows from {table_name}")
        return count

    except Exception as e:
        logger.error(f"Failed to sync table {table_name}: {e}")
        return -1


def sync_all():
    """Sync all tables from SQLite to Supabase."""
    results = {}
    
    # First, get row counts for all tables in one query
    sqlite_db = sqlite3.connect(Config.DATABASE, timeout=10)
    counts = {}
    for table in SUPABASE_TABLES:
        try:
            cnt = sqlite_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if cnt > 0:
                counts[table] = cnt
        except Exception:
            pass
    sqlite_db.close()
    
    # Only sync tables that have data
    for table in SUPABASE_TABLES:
        if table in counts:
            results[table] = sync_table(table)
        else:
            results[table] = 0
    return results


def sync_table_fast(table_name):
    """Fast sync a single table to Supabase (for Vercel after writes).
    Uses UPSERT to handle both inserts and updates."""
    try:
        pg = _get_pg_conn()
        cur = pg.cursor()

        sqlite_db = sqlite3.connect(Config.DATABASE, timeout=10)
        sqlite_db.row_factory = sqlite3.Row

        rows = sqlite_db.execute(f"SELECT * FROM {table_name}").fetchall()
        if not rows:
            sqlite_db.close()
            cur.close()
            pg.close()
            return 0

        columns = list(rows[0].keys())
        cols_str = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(columns))
        
        # Use unique constraints as conflict target (better for tables like patients with unique patient_id)
        unique_cols = _get_unique_constraints(table_name)
        if not unique_cols:
            pk_cols = _get_primary_key(table_name)
            if not pk_cols:
                pk_cols = ['id'] if 'id' in columns else [columns[0]]
        else:
            pk_cols = unique_cols
        
        update_cols = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col not in pk_cols])
        pk_cols_str = ', '.join(pk_cols)

        if not update_cols:
            upsert_sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        else:
            upsert_sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders}) ON CONFLICT ({pk_cols_str}) DO UPDATE SET {update_cols}"

        count = 0
        for row in rows:
            values = [_adapt_value(row[col]) for col in columns]
            try:
                cur.execute(upsert_sql, values)
                count += 1
            except Exception as e:
                logger.warning(f"Error upserting row in {table_name}: {e}")
                pg.rollback()
                pg = _get_pg_conn()
                cur = pg.cursor()

        pg.commit()
        sqlite_db.close()
        cur.close()
        pg.close()
        logger.info(f"Fast synced {count} rows from {table_name}")
        return count

    except Exception as e:
        logger.error(f"Failed to fast sync table {table_name}: {e}")
        return -1


def restore_table(table_name):
    """Restore a single table from Supabase to SQLite (non-destructive: preserves local data)."""
    try:
        pg = _get_pg_conn()
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(f"SELECT * FROM {table_name}")
        rows = cur.fetchall()
        if not rows:
            cur.close()
            pg.close()
            return 0

        sqlite_db = sqlite3.connect(Config.DATABASE, timeout=30)

        columns = list(rows[0].keys())
        cols_str = ', '.join(columns)
        placeholders = ', '.join(['?'] * len(columns))
        # INSERT OR IGNORE preserves local data that hasn't been synced yet
        insert_sql = f"INSERT OR IGNORE INTO {table_name} ({cols_str}) VALUES ({placeholders})"

        count = 0
        for row in rows:
            values = [row[col] for col in columns]
            try:
                sqlite_db.execute(insert_sql, values)
                count += 1
            except Exception as e:
                logger.warning(f"Error restoring row in {table_name}: {e}")

        sqlite_db.commit()
        sqlite_db.close()
        cur.close()
        pg.close()
        is_empty_before = count == len(rows)
        logger.info(f"Restored {count} rows to {table_name} (inserted missing rows from Supabase)")
        return count

    except Exception as e:
        logger.error(f"Failed to restore table {table_name}: {e}")
        return -1


def restore_all():
    """Restore all tables from Supabase to SQLite."""
    results = {}
    for table in SUPABASE_TABLES:
        results[table] = restore_table(table)
    return results


def get_sync_status():
    """Get sync status from Supabase."""
    try:
        pg = _get_pg_conn()
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM _sync_log ORDER BY synced_at DESC LIMIT 20")
        logs = cur.fetchall()
        cur.close()
        pg.close()
        return [dict(log) for log in logs]
    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        return []


# ── Auto-sync background thread ──────────────────────────────────────────────

_auto_sync_lock = threading.Lock()
_auto_sync_thread = None
_auto_sync_stop = threading.Event()
_last_sync_result = {'time': None, 'status': 'idle', 'message': ''}

# Vercel write-behind queue
_vercel_sync_queue = queue.Queue()
_vercel_sync_thread = None
_vercel_sync_stop = threading.Event()


def _get_sync_interval():
    """Read sync interval from local system_config (minutes)."""
    try:
        db = sqlite3.connect(Config.DATABASE, timeout=10)
        row = db.execute(
            "SELECT value FROM system_config WHERE key='auto_sync_interval'"
        ).fetchone()
        db.close()
        if row:
            return max(1, int(row[0]))
    except Exception:
        pass
    return 5  # default 5 minutes


def _set_last_sync_time():
    """Record last sync timestamp in local system_config."""
    try:
        db = sqlite3.connect(Config.DATABASE, timeout=10)
        db.execute(
            "INSERT OR REPLACE INTO system_config (key, value, updated_at) VALUES ('last_sync_time', ?, CURRENT_TIMESTAMP)",
            (datetime.now().isoformat(),)
        )
        db.commit()
        db.close()
    except Exception as e:
        logger.warning(f"Failed to record sync time: {e}")


def get_last_sync_info():
    """Return last sync info dict from the in-memory result."""
    return dict(_last_sync_result)


def _auto_sync_worker(app):
    """Background worker: periodically syncs all tables to Supabase."""
    logger.info("Auto-sync worker started")
    first_run = True
    while not _auto_sync_stop.is_set():
        try:
            if not first_run:
                interval_min = _get_sync_interval()
                _auto_sync_stop.wait(interval_min * 60)
                if _auto_sync_stop.is_set():
                    break
            else:
                # Small delay on first run to let the app finish starting up
                _auto_sync_stop.wait(5)
                if _auto_sync_stop.is_set():
                    break
            first_run = False

            if not _auto_sync_lock.acquire(blocking=False):
                continue

            try:
                if not HAS_PG:
                    _last_sync_result['status'] = 'error'
                    _last_sync_result['message'] = 'psycopg2 not installed'
                    continue

                # Update status to syncing before starting
                _last_sync_result['status'] = 'syncing'
                _last_sync_result['message'] = 'Sync in progress...'
                _last_sync_result['time'] = datetime.now().isoformat()

                logger.info("Auto-sync: starting sync_all")
                results = sync_all()
                total = sum(1 for v in results.values() if v >= 0)
                failed = sum(1 for v in results.values() if v < 0)
                synced = sum(v for v in results.values() if v > 0)
                _last_sync_result['time'] = datetime.now().isoformat()
                _last_sync_result['status'] = 'ok' if failed == 0 else 'partial'
                _last_sync_result['message'] = f'{synced} rows synced across {total} tables' + (f', {failed} failed' if failed else '')
                _set_last_sync_time()
                logger.info(f"Auto-sync complete: {_last_sync_result['message']}")

                # Notify admin users
                try:
                    notif_db = sqlite3.connect(Config.DATABASE, timeout=10)
                    admin_ids = notif_db.execute(
                        "SELECT id FROM users WHERE role='admin' AND is_active=1"
                    ).fetchall()
                    if admin_ids:
                        notif_msg = _last_sync_result['message']
                        for (uid,) in admin_ids:
                            notif_db.execute(
                                "INSERT INTO notifications (user_id, title, message, type, reference_url, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
                                (uid, 'Cloud Sync Complete', notif_msg, 'success' if failed == 0 else 'warning', '/backup')
                            )
                        notif_db.commit()
                    notif_db.close()
                except Exception as ne:
                    logger.warning(f"Failed to create sync notification: {ne}")

            except Exception as e:
                _last_sync_result['time'] = datetime.now().isoformat()
                _last_sync_result['status'] = 'error'
                _last_sync_result['message'] = str(e)
                logger.error(f"Auto-sync failed: {e}")
            finally:
                _auto_sync_lock.release()

        except Exception as e:
            logger.error(f"Auto-sync worker error: {e}")

    logger.info("Auto-sync worker stopped")


def start_auto_sync(app):
    """Start the background auto-sync thread."""
    global _auto_sync_thread
    if _auto_sync_thread and _auto_sync_thread.is_alive():
        logger.info("Auto-sync already running")
        return
    _auto_sync_stop.clear()
    _auto_sync_thread = threading.Thread(
        target=_auto_sync_worker, args=(app,), daemon=True
    )
    _auto_sync_thread.start()
    logger.info("Auto-sync thread launched")


def stop_auto_sync():
    """Signal the background thread to stop."""
    _auto_sync_stop.set()
    logger.info("Auto-sync stop signal sent")


# ── Vercel write-behind queue worker ───────────────────────────────────────────

def _vercel_sync_worker():
    """Background worker: processes queued table syncs for Vercel."""
    logger.info("Vercel sync queue worker started")
    while not _vercel_sync_stop.is_set():
        try:
            # Wait for work with timeout to check stop event
            try:
                table_name = _vercel_sync_queue.get(timeout=1)
            except queue.Empty:
                continue

            if table_name is None:  # Shutdown signal
                break

            try:
                if HAS_PG:
                    sync_table_fast(table_name)
            except Exception as e:
                logger.warning(f"Vercel queue sync failed for {table_name}: {e}")
            finally:
                _vercel_sync_queue.task_done()

        except Exception as e:
            logger.error(f"Vercel sync worker error: {e}")

    logger.info("Vercel sync queue worker stopped")


def start_vercel_sync_queue():
    """Start the Vercel background sync queue worker."""
    global _vercel_sync_thread
    if _vercel_sync_thread and _vercel_sync_thread.is_alive():
        return
    _vercel_sync_stop.clear()
    _vercel_sync_thread = threading.Thread(target=_vercel_sync_worker, daemon=True)
    _vercel_sync_thread.start()
    logger.info("Vercel sync queue worker launched")


def stop_vercel_sync_queue():
    """Stop the Vercel background sync queue worker."""
    _vercel_sync_stop.set()
    _vercel_sync_queue.put(None)  # Wake up worker
    logger.info("Vercel sync queue stop signal sent")


# ── OneDrive Backup ────────────────────────────────────────────────────────────

_onedrive_token_cache = {'access_token': None, 'expires_at': 0}


def _get_onedrive_access_token():
    """Get or refresh OneDrive access token using refresh token."""
    global _onedrive_token_cache
    
    now = time.time()
    if _onedrive_token_cache['access_token'] and _onedrive_token_cache['expires_at'] > now + 60:
        return _onedrive_token_cache['access_token']
    
    if not HAS_REQUESTS:
        logger.error("requests library not installed. Run: pip install requests")
        return None
    
    if not Config.ONEDRIVE_CLIENT_ID or not Config.ONEDRIVE_CLIENT_SECRET or not Config.ONEDRIVE_REFRESH_TOKEN:
        logger.error("OneDrive credentials not configured")
        return None
    
    try:
        token_url = f"https://login.microsoftonline.com/{Config.ONEDRIVE_TENANT_ID}/oauth2/v2.0/token"
        data = {
            'client_id': Config.ONEDRIVE_CLIENT_ID,
            'client_secret': Config.ONEDRIVE_CLIENT_SECRET,
            'refresh_token': Config.ONEDRIVE_REFRESH_TOKEN,
            'grant_type': 'refresh_token',
            'scope': 'https://graph.microsoft.com/.default'
        }
        resp = requests.post(token_url, data=data, timeout=30)
        resp.raise_for_status()
        token_data = resp.json()
        
        _onedrive_token_cache['access_token'] = token_data['access_token']
        _onedrive_token_cache['expires_at'] = now + token_data.get('expires_in', 3600)
        
        # Update refresh token if provided
        if 'refresh_token' in token_data:
            Config.ONEDRIVE_REFRESH_TOKEN = token_data['refresh_token']
            logger.info("OneDrive refresh token updated")
        
        return _onedrive_token_cache['access_token']
    except Exception as e:
        logger.error(f"Failed to get OneDrive access token: {e}")
        return None


def _onedrive_api_request(method, url, **kwargs):
    """Make authenticated request to Microsoft Graph API."""
    token = _get_onedrive_access_token()
    if not token:
        return None
    
    headers = kwargs.pop('headers', {})
    headers['Authorization'] = f'Bearer {token}'
    headers['Content-Type'] = 'application/json'
    
    try:
        resp = requests.request(method, url, headers=headers, timeout=60, **kwargs)
        if resp.status_code == 401:
            # Token expired, clear cache and retry once
            _onedrive_token_cache['access_token'] = None
            token = _get_onedrive_access_token()
            if token:
                headers['Authorization'] = f'Bearer {token}'
                resp = requests.request(method, url, headers=headers, timeout=60, **kwargs)
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.error(f"OneDrive API request failed: {e}")
        return None


def _ensure_onedrive_folder(folder_path):
    """Ensure backup folder exists in OneDrive, create if needed."""
    # Split path and create each folder
    parts = [p for p in folder_path.split('/') if p]
    current_path = 'root'
    
    for part in parts:
        # Check if folder exists
        search_url = f"https://graph.microsoft.com/v1.0/me/drive/{current_path}:/'{part}':"
        resp = _onedrive_api_request('GET', search_url)
        
        if resp and resp.status_code == 200:
            folder = resp.json()
            current_path = f"items/{folder['id']}"
        else:
            # Create folder
            create_url = f"https://graph.microsoft.com/v1.0/me/drive/{current_path}:/children"
            data = {'name': part, 'folder': {}, '@microsoft.graph.conflictBehavior': 'rename'}
            resp = _onedrive_api_request('POST', create_url, json=data)
            if resp and resp.status_code in (200, 201):
                folder = resp.json()
                current_path = f"items/{folder['id']}"
            else:
                logger.error(f"Failed to create OneDrive folder: {part}")
                return None
    return current_path


def backup_to_onedrive():
    """Create compressed SQLite backup and upload to OneDrive."""
    try:
        if not HAS_REQUESTS:
            logger.error("requests library not installed. Run: pip install requests")
            return False, "requests library not installed"
        
        if not os.path.exists(Config.DATABASE):
            return False, "Database file not found"
        
        # Get access token
        token = _get_onedrive_access_token()
        if not token:
            return False, "Failed to authenticate with OneDrive"
        
        # Ensure backup folder exists
        folder_id = _ensure_onedrive_folder(Config.ONEDRIVE_BACKUP_FOLDER)
        if not folder_id:
            return False, "Failed to create/access backup folder"
        
        # Create compressed backup
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"kayange_backup_{timestamp}.db.gz"
        
        logger.info(f"Creating backup: {backup_filename}")
        with open(Config.DATABASE, 'rb') as f_in:
            compressed = gzip.compress(f_in.read())
        
        # Upload to OneDrive
        upload_url = f"https://graph.microsoft.com/v1.0/me/drive/{folder_id}:/{backup_filename}:/content"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/gzip'
        }
        
        resp = requests.put(upload_url, headers=headers, data=compressed, timeout=120)
        if resp.status_code in (200, 201):
            logger.info(f"OneDrive backup uploaded: {backup_filename}")
            return True, f"Backup uploaded: {backup_filename}"
        else:
            logger.error(f"OneDrive upload failed: {resp.status_code} - {resp.text}")
            return False, f"Upload failed: {resp.status_code}"
            
    except Exception as e:
        logger.error(f"OneDrive backup failed: {e}")
        return False, str(e)


def restore_from_onedrive(filename=None):
    """Download and restore database from OneDrive backup."""
    try:
        if not HAS_REQUESTS:
            return False, "requests library not installed"
        
        token = _get_onedrive_access_token()
        if not token:
            return False, "Failed to authenticate with OneDrive"
        
        folder_id = _ensure_onedrive_folder(Config.ONEDRIVE_BACKUP_FOLDER)
        if not folder_id:
            return False, "Backup folder not found"
        
        # List backups
        list_url = f"https://graph.microsoft.com/v1.0/me/drive/{folder_id}/children"
        resp = _onedrive_api_request('GET', list_url)
        if not resp:
            return False, "Failed to list backups"
        
        files = resp.json().get('value', [])
        backup_files = [f for f in files if f['name'].startswith('kayange_backup_') and f['name'].endswith('.db.gz')]
        
        if not backup_files:
            return False, "No backup files found"
        
        # Sort by name (timestamp) descending, get latest or specified
        backup_files.sort(key=lambda x: x['name'], reverse=True)
        target_file = None
        
        if filename:
            target_file = next((f for f in backup_files if f['name'] == filename), None)
        else:
            target_file = backup_files[0]  # Latest
        
        if not target_file:
            return False, f"Backup file not found: {filename}"
        
        # Download backup
        download_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{target_file['id']}/content"
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.get(download_url, headers=headers, timeout=120)
        resp.raise_for_status()
        
        # Decompress and restore
        decompressed = gzip.decompress(resp.content)
        
        # Backup current database first
        backup_current = f"{Config.DATABASE}.pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        import shutil
        shutil.copy2(Config.DATABASE, backup_current)
        
        # Write restored database
        with open(Config.DATABASE, 'wb') as f:
            f.write(decompressed)
        
        logger.info(f"Database restored from OneDrive: {target_file['name']}")
        return True, f"Restored from {target_file['name']} (previous DB backed up)"
        
    except Exception as e:
        logger.error(f"OneDrive restore failed: {e}")
        return False, str(e)


def list_onedrive_backups():
    """List available backups on OneDrive."""
    try:
        if not HAS_REQUESTS:
            return []
        
        token = _get_onedrive_access_token()
        if not token:
            return []
        
        folder_id = _ensure_onedrive_folder(Config.ONEDRIVE_BACKUP_FOLDER)
        if not folder_id:
            return []
        
        list_url = f"https://graph.microsoft.com/v1.0/me/drive/{folder_id}/children"
        resp = _onedrive_api_request('GET', list_url)
        if not resp:
            return []
        
        files = resp.json().get('value', [])
        backup_files = [f for f in files if f['name'].startswith('kayange_backup_') and f['name'].endswith('.db.gz')]
        backup_files.sort(key=lambda x: x['name'], reverse=True)
        
        return [{
            'name': f['name'],
            'size': f.get('size', 0),
            'created': f.get('createdDateTime'),
            'modified': f.get('lastModifiedDateTime'),
            'id': f['id']
        } for f in backup_files]
        
    except Exception as e:
        logger.error(f"Failed to list OneDrive backups: {e}")
        return []


def get_onedrive_status():
    """Check OneDrive configuration and connectivity."""
    configured = bool(Config.ONEDRIVE_CLIENT_ID and Config.ONEDRIVE_CLIENT_SECRET and Config.ONEDRIVE_REFRESH_TOKEN)
    
    if not configured:
        return {
            'configured': False,
            'connected': False,
            'message': 'OneDrive credentials not configured'
        }
    
    if not HAS_REQUESTS:
        return {
            'configured': True,
            'connected': False,
            'message': 'requests library not installed'
        }
    
    token = _get_onedrive_access_token()
    if token:
        # Test API call
        resp = _onedrive_api_request('GET', 'https://graph.microsoft.com/v1.0/me/drive/root')
        if resp and resp.status_code == 200:
            return {
                'configured': True,
                'connected': True,
                'message': 'OneDrive connected',
                'user_email': Config.ONEDRIVE_USER_EMAIL
            }
    
    return {
        'configured': True,
        'connected': False,
        'message': 'Failed to connect to OneDrive'
    }


def queue_vercel_sync(table_name):
    """Queue a table for background sync (non-blocking)."""
    if table_name in SUPABASE_TABLES:
        _vercel_sync_queue.put(table_name)
