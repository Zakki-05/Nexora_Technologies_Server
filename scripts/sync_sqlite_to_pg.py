import os
import sys
import sqlite3
import psycopg2

def sync_data():
    sqlite_path = os.path.join(os.path.dirname(__file__), "..", "ems.db")
    if not os.path.exists(sqlite_path):
        print(f"SQLite file not found at {sqlite_path}")
        return

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    s_cur = sqlite_conn.cursor()

    tables = [
        "departments",
        "users",
        "employees",
        "leave_types",
        "leave_balances",
        "attendance_policies",
        "attendances",
        "attendance_sessions",
        "break_sessions",
        "leaves",
        "leave_transactions",
        "holidays",
        "salaries",
        "salary_structures",
        "notifications",
        "announcements",
        "audit_logs",
        "employee_documents"
    ]

    pg_url = os.environ.get("DATABASE_URL", "postgresql+psycopg2://postgres:root@localhost:5433/employees")
    from urllib.parse import urlparse
    parsed = urlparse(pg_url)

    try:
        pg_conn = psycopg2.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5433,
            user=parsed.username or "postgres",
            password=parsed.password or "root",
            dbname=parsed.path.lstrip("/") or "employees",
            connect_timeout=3
        )
    except Exception as e:
        print(f"Cannot connect to PostgreSQL: {e}")
        return

    pg_cur = pg_conn.cursor()
    print("Connected to PostgreSQL for sync.")

    for table in tables:
        try:
            # Query column data types from postgres
            pg_cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}';")
            col_types = {r[0]: r[1] for r in pg_cur.fetchall()}

            s_cur.execute(f"SELECT * FROM {table}")
            rows = s_cur.fetchall()
            if not rows:
                continue

            columns = [col[0] for col in s_cur.description]
            col_str = ", ".join(f'"{c}"' for c in columns)
            val_placeholders = ", ".join(["%s"] * len(columns))

            for row in rows:
                vals = []
                for c in columns:
                    val = row[c]
                    # Convert integer 0/1 to bool if Postgres expects boolean
                    if col_types.get(c) == "boolean" and val is not None:
                        val = bool(val)
                    vals.append(val)

                query = f'INSERT INTO "{table}" ({col_str}) VALUES ({val_placeholders}) ON CONFLICT ("id") DO NOTHING;'
                pg_cur.execute(query, vals)

            if "id" in columns:
                try:
                    pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), coalesce(max(id), 1), max(id) IS NOT null) FROM \"{table}\";")
                except Exception:
                    pass

            pg_conn.commit()
            print(f"Synced {table}: {len(rows)} records processed.")
        except Exception as err:
            pg_conn.rollback()
            print(f"Error syncing {table}: {err}")

    pg_conn.close()
    sqlite_conn.close()
    print("Sync completed successfully.")

if __name__ == "__main__":
    sync_data()
