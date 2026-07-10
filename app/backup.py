import sqlite3
import json
import logging
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
    'users', 'patients', 'patient_allergies', 'patient_medical_history',
    'patient_medications', 'departments', 'appointments', 'consultations',
    'vital_signs', 'medical_examinations', 'diagnoses', 'prescriptions',
    'prescription_orders', 'prescription_refills', 'pharmacy_inventory',
    'pharmacy_dispensing', 'lab_test_catalog', 'lab_tests', 'lab_test_results',
    'billing', 'billing_items', 'insurance_providers', 'patient_insurance',
    'insurance_claims', 'claim_items', 'claim_status_history',
    'insurance_authorization_rules', 'medical_certificates', 'packages',
    'package_services', 'procedures', 'referrals', 'messages',
    'notifications', 'system_config', 'audit_logs', 'radiology_orders',
    'radiology_results', 'telemedicine_sessions', 'telemedicine_messages',
    'telemedicine_payments', 'telemedicine_recordings', 'short_stay_beds',
    'short_stay_drip_stations', 'short_stay_admissions', 'drug_scheme_prices',
    'lab_invoices', 'lab_invoice_items', 'suppliers',
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
    return psycopg2.connect(Config.SUPABASE_DB_URL)


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
                create_sql = create_sql.replace('AUTOINCREMENT', 'SERIAL')
                create_sql = create_sql.replace('AUTO_INCREMENT', 'SERIAL')

                for keyword in ['IF NOT EXISTS', 'PRIMARY KEY', 'NOT NULL', 'DEFAULT', 'CHECK', 'UNIQUE']:
                    pass

                create_sql = create_sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
                create_sql = create_sql.replace('INTEGER PRIMARY KEY', 'SERIAL PRIMARY KEY')

                pg_type_map = {
                    'INTEGER': 'BIGINT',
                    'REAL': 'DOUBLE PRECISION',
                    'TEXT': 'TEXT',
                    'BLOB': 'BYTEA',
                    'BOOLEAN': 'BOOLEAN',
                    'DATE': 'DATE',
                    'TIMESTAMP': 'TIMESTAMP',
                    'NUMERIC': 'NUMERIC',
                }

                for sqlite_type, pg_type in pg_type_map.items():
                    create_sql = create_sql.replace(sqlite_type, pg_type)

                cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                cur.execute(create_sql)
                logger.info(f"Created/updated table: {table_name}")

            except Exception as e:
                logger.warning(f"Error creating table {table_name}: {e}")
                pg.rollback()
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
    """Restore a single table from Supabase to SQLite."""
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
        sqlite_db.execute(f"DELETE FROM {table_name}")

        columns = list(rows[0].keys())
        cols_str = ', '.join(columns)
        placeholders = ', '.join(['?'] * len(columns))
        insert_sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})"

        count = 0
        for row in rows:
            values = [row[col] for col in columns]
            sqlite_db.execute(insert_sql, values)
            count += 1

        sqlite_db.commit()
        sqlite_db.close()
        cur.close()
        pg.close()
        logger.info(f"Restored {count} rows to {table_name}")
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
