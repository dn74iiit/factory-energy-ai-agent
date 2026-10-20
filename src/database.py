"""
DuckDB Database Manager.
Stores structured tables: meter_15min, tariff, production, weather, and execution traces.
Provides fast querying and transactional loading.
"""

import os
import json
import duckdb
import pandas as pd
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from src.config import DB_PATH, DATA_DIR

class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DB_PATH)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        try:
            self._con = duckdb.connect(self.db_path)
            self._init_db()
            self.ensure_loaded()
        except Exception:
            try:
                self._con = duckdb.connect(self.db_path, read_only=True)
            except Exception:
                # In-memory fallback if file is locked
                self._con = duckdb.connect(":memory:")
                self._init_db()

    def get_connection(self):
        """Returns a cursor to the DuckDB database with auto-reconnect."""
        try:
            return self._con.cursor()
        except Exception:
            try:
                self._con = duckdb.connect(self.db_path)
            except Exception:
                self._con = duckdb.connect(self.db_path, read_only=True)
            return self._con.cursor()

    def ensure_loaded(self):
        """Ensures that tables have data loaded from CSV files, completely free of circular imports."""
        try:
            with self.get_connection() as con:
                count = con.execute("SELECT COUNT(*) FROM meter_15min").fetchone()[0]
        except Exception:
            count = 0

        if count == 0:
            import pandas as pd
            from src.config import DATA_DIR
            data_dir = str(DATA_DIR)
            for table_name in ["meter_15min", "tariff", "production", "weather"]:
                csv_path = os.path.join(data_dir, f"{table_name}.csv")
                if os.path.exists(csv_path):
                    try:
                        df = pd.read_csv(csv_path)
                        self.load_table_from_df(table_name, df, replace=True)
                    except Exception as e:
                        print(f"Auto-load error for {table_name}: {e}")

    def _init_db(self):
        """Initializes tables if they do not exist."""
        with self.get_connection() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS meter_15min (
                    meter_id VARCHAR,
                    ts TIMESTAMP WITH TIME ZONE,
                    kwh DOUBLE
                );
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS tariff (
                    valid_from TIMESTAMP WITH TIME ZONE,
                    valid_to TIMESTAMP WITH TIME ZONE,
                    period VARCHAR,
                    price_per_kwh DOUBLE
                );
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS production (
                    date DATE,
                    product VARCHAR,
                    units INTEGER,
                    shift_pattern VARCHAR,
                    is_holiday BOOLEAN
                );
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS weather (
                    date DATE,
                    avg_temp_c DOUBLE,
                    cooling_degree_days DOUBLE,
                    heating_degree_days DOUBLE
                );
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    run_id VARCHAR PRIMARY KEY,
                    question VARCHAR,
                    answer_type VARCHAR,
                    response_json VARCHAR,
                    trace_json VARCHAR,
                    created_at TIMESTAMP
                );
            """)

    def load_table_from_df(self, table_name: str, df: pd.DataFrame, replace: bool = True) -> int:
        """Loads a pandas DataFrame into the designated DuckDB table."""
        valid_tables = ["meter_15min", "tariff", "production", "weather"]
        if table_name not in valid_tables:
            raise ValueError(f"Invalid table: {table_name}. Expected one of {valid_tables}")

        # Ensure correct column types
        df_copy = df.copy()
        if table_name == "meter_15min":
            df_copy["ts"] = pd.to_datetime(df_copy["ts"], utc=True)
            df_copy["kwh"] = pd.to_numeric(df_copy["kwh"], errors="coerce").fillna(0.0)
            df_copy["meter_id"] = df_copy["meter_id"].astype(str)
        elif table_name == "tariff":
            df_copy["valid_from"] = pd.to_datetime(df_copy["valid_from"], utc=True)
            df_copy["valid_to"] = pd.to_datetime(df_copy["valid_to"], utc=True)
            df_copy["price_per_kwh"] = pd.to_numeric(df_copy["price_per_kwh"], errors="coerce").fillna(0.0)
            df_copy["period"] = df_copy["period"].astype(str)
        elif table_name == "production":
            df_copy["date"] = pd.to_datetime(df_copy["date"]).dt.date
            df_copy["units"] = pd.to_numeric(df_copy["units"], errors="coerce").fillna(0).astype(int)
            df_copy["product"] = df_copy["product"].astype(str)
            df_copy["shift_pattern"] = df_copy["shift_pattern"].astype(str)
            df_copy["is_holiday"] = df_copy["is_holiday"].astype(bool)
        elif table_name == "weather":
            df_copy["date"] = pd.to_datetime(df_copy["date"]).dt.date
            df_copy["avg_temp_c"] = pd.to_numeric(df_copy["avg_temp_c"], errors="coerce").fillna(25.0)
            df_copy["cooling_degree_days"] = pd.to_numeric(df_copy["cooling_degree_days"], errors="coerce").fillna(0.0)
            df_copy["heating_degree_days"] = pd.to_numeric(df_copy["heating_degree_days"], errors="coerce").fillna(0.0)

        with self.get_connection() as con:
            if replace:
                con.execute(f"DELETE FROM {table_name}")
            con.register("incoming_df", df_copy)
            con.execute(f"INSERT INTO {table_name} SELECT * FROM incoming_df")
            con.unregister("incoming_df")
            count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        return count

    def get_table(self, table_name: str) -> pd.DataFrame:
        """Retrieves a table as a pandas DataFrame."""
        with self.get_connection() as con:
            return con.execute(f"SELECT * FROM {table_name}").fetchdf()

    def query(self, sql: str, params: Optional[List[Any]] = None) -> pd.DataFrame:
        """Executes arbitrary SQL query and returns results as DataFrame."""
        with self.get_connection() as con:
            if params:
                return con.execute(sql, params).fetchdf()
            return con.execute(sql).fetchdf()

    def record_trace(self, run_id: str, question: str, answer_type: str, 
                     response_dict: Dict[str, Any], trace_dict: Dict[str, Any]):
        """Persists an execution audit trace."""
        with self.get_connection() as con:
            con.execute("""
                INSERT OR REPLACE INTO traces (run_id, question, answer_type, response_json, trace_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                run_id,
                question,
                answer_type,
                json.dumps(response_dict),
                json.dumps(trace_dict),
                datetime.now(timezone.utc)
            ])

    def get_trace(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an execution audit trace by run_id."""
        with self.get_connection() as con:
            res = con.execute("SELECT trace_json FROM traces WHERE run_id = ?", [run_id]).fetchone()
            if res and res[0]:
                return json.loads(res[0])
            return None

    def get_counts(self) -> Dict[str, int]:
        """Returns row counts for all tables."""
        with self.get_connection() as con:
            return {
                "meter_15min": con.execute("SELECT COUNT(*) FROM meter_15min").fetchone()[0],
                "tariff": con.execute("SELECT COUNT(*) FROM tariff").fetchone()[0],
                "production": con.execute("SELECT COUNT(*) FROM production").fetchone()[0],
                "weather": con.execute("SELECT COUNT(*) FROM weather").fetchone()[0],
                "traces": con.execute("SELECT COUNT(*) FROM traces").fetchone()[0],
            }

# Singleton instance
db = DatabaseManager()
