"""
Data Warehouse Schema Evolution Engine.
Manages schema versioning, drift detection, non-destructive migration execution,
and schema change auditing for enterprise data warehouse consolidation.
"""

from typing import Dict, Any, List
import logging
from backend.database.sqlite_manager import db_manager
from backend.database.schema_definitions import SCHEMA_V2_0_EVOLUTION_DDL, SCHEMA_V3_0_EVOLUTION_DDL

logger = logging.getLogger("dwh.schema_evolution")

class SchemaEvolutionEngine:
    def __init__(self, db=db_manager):
        self.db = db

    def get_current_version(self) -> str:
        """Retrieves the latest applied schema version code."""
        rows = self.db.execute_query(
            "SELECT version_code FROM schema_evolution_history ORDER BY id DESC LIMIT 1"
        )
        return rows[0]["version_code"] if rows else "v1.0"

    def get_evolution_history(self) -> List[Dict[str, Any]]:
        """Returns all applied schema evolution events."""
        return self.db.execute_query(
            "SELECT * FROM schema_evolution_history ORDER BY id ASC"
        )

    def detect_schema_drift(self, incoming_attributes: List[str], target_table: str) -> Dict[str, Any]:
        """
        Detects if incoming feed contains attributes not currently present in the target table schema.
        """
        existing_cols = {col["name"].lower() for col in self.db.get_table_columns(target_table)}
        missing = [attr for attr in incoming_attributes if attr.lower() not in existing_cols]
        return {
            "target_table": target_table,
            "has_drift": len(missing) > 0,
            "missing_columns": missing,
            "existing_column_count": len(existing_cols)
        }

    def apply_evolution_v2(self) -> Dict[str, Any]:
        """
        Migrates Data Warehouse Schema from v1.0 to v2.0 (Adds honors_track, residency_status, work_modality).
        """
        applied_changes = []
        for change in SCHEMA_V2_0_EVOLUTION_DDL:
            table = change["table"]
            col_name = change["sql"].split("ADD COLUMN")[1].strip().split()[0]
            existing_cols = [c["name"].lower() for c in self.db.get_table_columns(table)]
            
            if col_name.lower() not in existing_cols:
                try:
                    self.db.execute_script(change["sql"])
                    self.db.execute_non_query(
                        """
                        INSERT INTO schema_evolution_history (
                            version_code, evolution_type, target_table, change_description, ddl_executed, is_backward_compatible
                        ) VALUES ('v2.0', ?, ?, ?, ?, 1)
                        """,
                        (change["type"], table, change["description"], change["sql"])
                    )
                    applied_changes.append(change["description"])
                except Exception as e:
                    logger.error(f"Error applying evolution: {e}")
            else:
                applied_changes.append(f"Column {col_name} already exists in {table} (Skipped)")

        return {
            "status": "SUCCESS",
            "target_version": "v2.0",
            "changes_applied": applied_changes
        }

    def apply_evolution_v3(self) -> Dict[str, Any]:
        """
        Migrates Data Warehouse Schema from v2.0 to v3.0 (Adds advisor link, donor rating, hybrid delivery).
        """
        applied_changes = []
        for change in SCHEMA_V3_0_EVOLUTION_DDL:
            table = change["table"]
            col_name = change["sql"].split("ADD COLUMN")[1].strip().split()[0]
            existing_cols = [c["name"].lower() for c in self.db.get_table_columns(table)]
            
            if col_name.lower() not in existing_cols:
                try:
                    self.db.execute_script(change["sql"])
                    self.db.execute_non_query(
                        """
                        INSERT INTO schema_evolution_history (
                            version_code, evolution_type, target_table, change_description, ddl_executed, is_backward_compatible
                        ) VALUES ('v3.0', ?, ?, ?, ?, 1)
                        """,
                        (change["type"], table, change["description"], change["sql"])
                    )
                    applied_changes.append(change["description"])
                except Exception as e:
                    logger.error(f"Error applying evolution: {e}")
            else:
                applied_changes.append(f"Column {col_name} already exists in {table} (Skipped)")

        return {
            "status": "SUCCESS",
            "target_version": "v3.0",
            "changes_applied": applied_changes
        }

    def get_full_schema_catalog(self) -> Dict[str, List[Dict[str, Any]]]:
        """Returns metadata for all dimensional and fact tables."""
        tables = [
            "dim_student_scd2", "dim_faculty_scd2", "dim_department",
            "dim_course", "dim_term_semester", "fact_student_enrollment",
            "fact_research_funding", "er_resolved_entities"
        ]
        catalog = {}
        for t in tables:
            catalog[t] = self.db.get_table_columns(t)
        return catalog

schema_evolution_engine = SchemaEvolutionEngine()
