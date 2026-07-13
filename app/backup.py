import sqlite3
import re
import json
import logging
import threading
import time
from datetime import datetime, date
from config import Config

try:
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except ImportError:
    HAS_PG = False

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
    """Sync a single table from SQLite to Supabase."""
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
        cols_str = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(columns))
        insert_sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

        count = 0
        for row in rows:
            values = [_adapt_value(row[col]) for col in columns]
            try:
                cur.execute(insert_sql, values)
                count += 1
            except Exception as e:
                logger.warning(f"Error inserting row in {table_name}: {e}")
                pg.rollback()
                pg = _get_pg_conn()
                cur = pg.cursor()

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
    for table in SUPABASE_TABLES:
        results[table] = sync_table(table)
    return results


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
    while not _auto_sync_stop.is_set():
        try:
            interval_min = _get_sync_interval()
            _auto_sync_stop.wait(interval_min * 60)
            if _auto_sync_stop.is_set():
                break

            if not _auto_sync_lock.acquire(blocking=False):
                continue

            try:
                if not HAS_PG:
                    _last_sync_result['status'] = 'error'
                    _last_sync_result['message'] = 'psycopg2 not installed'
                    continue

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
