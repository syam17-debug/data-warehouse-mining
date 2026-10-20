"""
Slowly Changing Dimensions (SCD) Engine.
Implements SCD Type 0 (Fixed), SCD Type 1 (In-Place Overwrite),
SCD Type 2 (Historical Tracking with Surrogate Keys, Versions, & Date Validity),
and SCD Type 3 (Current & Previous Attribute Preservation).
Includes Point-In-Time / Time-Travel Historical Querying.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from backend.database.sqlite_manager import db_manager

logger = logging.getLogger("dwh.scd")

class SCDEngine:
    def __init__(self, db=db_manager):
        self.db = db

    def load_initial_dimension_records(self, golden_entities: List[Dict[str, Any]], effective_date: str = "2024-08-25"):
        """Initial baseline load for SCD dimensions (Version 1, valid from start to 9999-12-31)."""
        for ent in golden_entities:
            role = ent.get("primary_role", "STUDENT")
            cid = ent["canonical_id"]
            name = ent["resolved_name"]
            parts = name.split()
            fn = parts[0] if parts else ""
            ln = parts[-1] if len(parts) > 1 else ""
            dob = ent.get("resolved_dob", "")
            email = ent.get("resolved_primary_email", "")
            phone = ent.get("resolved_primary_phone", "")
            dept = ent.get("department", "CS")

            if "FACULTY" in role:
                existing = self.db.execute_query(
                    "SELECT count(*) as cnt FROM dim_faculty_scd2 WHERE canonical_faculty_id = ?",
                    (cid,)
                )
                if existing[0]["cnt"] == 0:
                    self.db.execute_non_query(
                        """
                        INSERT INTO dim_faculty_scd2 (
                            canonical_faculty_id, full_name, primary_email, phone, office_location,
                            academic_rank, department_code, salary_band,
                            valid_from, valid_to, is_current, version_num, effective_reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '9999-12-31', 1, 1, 'INITIAL_CONSOLIDATION_LOAD')
                        """,
                        (cid, name, email, phone, "Campus Tower Suite 300", "Associate Professor", dept, "TIER_2_ASSOCIATE", effective_date)
                    )
            else:
                existing = self.db.execute_query(
                    "SELECT count(*) as cnt FROM dim_student_scd2 WHERE canonical_student_id = ?",
                    (cid,)
                )
                if existing[0]["cnt"] == 0:
                    self.db.execute_non_query(
                        """
                        INSERT INTO dim_student_scd2 (
                            canonical_student_id, first_name, last_name, full_name,
                            dob, primary_email, phone, department_code, academic_standing,
                            degree_program, campus_origin, prev_department_code, dept_change_date,
                            valid_from, valid_to, is_current, version_num, effective_reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GOOD_STANDING', 'B.S.', 'CONSOLIDATED', NULL, NULL, ?, '9999-12-31', 1, 1, 'INITIAL_CONSOLIDATION_LOAD')
                        """,
                        (cid, fn, ln, name, dob, email, phone, dept, effective_date)
                    )

    def apply_scd_update(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes an SCD update event containing SCD1, SCD2, and SCD3 mutations.
        """
        cid = event["canonical_id"]
        effective_date = event.get("effective_date", datetime.now().strftime("%Y-%m-%d"))
        reason = event.get("reason", "DIMENSION_UPDATE")
        scd1 = event.get("scd1_changes", {})
        scd2 = event.get("scd2_changes", {})
        scd3 = event.get("scd3_changes", {})

        # Compute prior day for closing previous version
        try:
            eff_dt = datetime.strptime(effective_date, "%Y-%m-%d")
            prev_day = (eff_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        except Exception:
            prev_day = effective_date

        # Determine table: Student or Faculty
        is_faculty = self.db.execute_query(
            "SELECT count(*) as cnt FROM dim_faculty_scd2 WHERE canonical_faculty_id = ?",
            (cid,)
        )[0]["cnt"] > 0
        
        table = "dim_faculty_scd2" if is_faculty else "dim_student_scd2"
        id_col = "canonical_faculty_id" if is_faculty else "canonical_student_id"
        sk_col = "faculty_dim_key" if is_faculty else "student_dim_key"

        # Fetch currently active record
        current_rows = self.db.execute_query(
            f"SELECT * FROM {table} WHERE {id_col} = ? AND is_current = 1",
            (cid,)
        )
        if not current_rows:
            return {"status": "ERROR", "message": f"Entity {cid} has no active current dimension record in {table}"}

        current_record = current_rows[0]
        current_sk = current_record[sk_col]
        current_version = current_record["version_num"]
        existing_cols = {c["name"] for c in self.db.get_table_columns(table)}

        # Step 1: Process SCD Type 1 (In-Place Overwrite)
        if scd1:
            valid_scd1 = {k: v for k, v in scd1.items() if k in existing_cols}
            if valid_scd1:
                set_clauses = [f"{k} = ?" for k in valid_scd1.keys()]
                values = list(valid_scd1.values()) + [cid]
                self.db.execute_non_query(
                    f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {id_col} = ?",
                    tuple(values)
                )

        # Step 2: Process SCD Type 2 & Type 3
        if scd2:
            # 2a. Expire current version
            self.db.execute_non_query(
                f"UPDATE {table} SET valid_to = ?, is_current = 0 WHERE {sk_col} = ?",
                (prev_day, current_sk)
            )

            # 2b. Prepare new record values
            new_record = dict(current_record)
            new_record.pop(sk_col, None)  # Remove old surrogate key
            
            # Apply SCD2 updates
            for k, v in scd2.items():
                if k in existing_cols:
                    new_record[k] = v
                
            # Apply SCD1 updates into new row
            for k, v in scd1.items():
                if k in existing_cols:
                    new_record[k] = v

            # Apply SCD3 updates (e.g. prev_department_code, dept_change_date)
            for k, v in scd3.items():
                if k in existing_cols:
                    new_record[k] = v

            new_record["valid_from"] = effective_date
            new_record["valid_to"] = "9999-12-31"
            new_record["is_current"] = 1
            new_record["version_num"] = current_version + 1
            new_record["effective_reason"] = reason

            cols = [c for c in new_record.keys() if c in existing_cols]
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            val_tuple = tuple(new_record[c] for c in cols)

            new_sk = self.db.execute_non_query(
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                val_tuple
            )

            return {
                "status": "SUCCESS",
                "entity_id": cid,
                "dimension_table": table,
                "previous_surrogate_key": current_sk,
                "new_surrogate_key": new_sk,
                "version": current_version + 1,
                "effective_date": effective_date,
                "scd_types_applied": ["SCD1" if scd1 else None, "SCD2", "SCD3" if scd3 else None]
            }

        return {
            "status": "SUCCESS",
            "entity_id": cid,
            "dimension_table": table,
            "version": current_version,
            "scd_types_applied": ["SCD1"]
        }

    def get_entity_history(self, canonical_id: str) -> List[Dict[str, Any]]:
        """Returns complete historical timeline of versions for an entity."""
        rows = self.db.execute_query(
            "SELECT * FROM dim_student_scd2 WHERE canonical_student_id = ? ORDER BY version_num ASC",
            (canonical_id,)
        )
        if not rows:
            rows = self.db.execute_query(
                "SELECT * FROM dim_faculty_scd2 WHERE canonical_faculty_id = ? ORDER BY version_num ASC",
                (canonical_id,)
            )
        return rows

    def query_as_of_date(self, canonical_id: str, as_of_date: str) -> Optional[Dict[str, Any]]:
        """Point-in-Time Historical Query (Time-Travel). Reconstructs exact state as of target date."""
        query_student = """
        SELECT * FROM dim_student_scd2 
        WHERE canonical_student_id = ? 
          AND ? >= valid_from AND ? <= valid_to
        """
        rows = self.db.execute_query(query_student, (canonical_id, as_of_date, as_of_date))
        if rows:
            return rows[0]

        query_faculty = """
        SELECT * FROM dim_faculty_scd2 
        WHERE canonical_faculty_id = ? 
          AND ? >= valid_from AND ? <= valid_to
        """
        rows = self.db.execute_query(query_faculty, (canonical_id, as_of_date, as_of_date))
        return rows[0] if rows else None

scd_engine = SCDEngine()
