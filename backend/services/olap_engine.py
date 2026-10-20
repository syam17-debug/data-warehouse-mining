"""
OLAP Data Mart & Analytical Reporting Engine.
Provides aggregations, rollup/drilldown dimensions, duplicate impact comparisons,
and an interactive custom SQL execution engine.
"""

from typing import Dict, Any, List
from backend.database.sqlite_manager import db_manager

class OLAPEngine:
    def __init__(self, db=db_manager):
        self.db = db

    def get_summary_kpis(self) -> Dict[str, Any]:
        """Calculates high-level metrics across staging, graph resolution, and dimensional warehouse."""
        total_raw = self.db.execute_query("SELECT count(*) as cnt FROM stg_raw_records")[0]["cnt"]
        total_resolved = self.db.execute_query("SELECT count(*) as cnt FROM er_resolved_entities")[0]["cnt"]
        total_edges = self.db.execute_query("SELECT count(*) as cnt FROM er_similarity_edges WHERE overall_similarity >= 0.65")[0]["cnt"]
        
        # Deduplication savings calculation
        duplicates_removed = max(0, total_raw - total_resolved)
        dedupe_rate = (duplicates_removed / total_raw * 100) if total_raw > 0 else 0.0

        total_scd_versions = self.db.execute_query("SELECT count(*) as cnt FROM dim_student_scd2")[0]["cnt"]
        active_students = self.db.execute_query("SELECT count(*) as cnt FROM dim_student_scd2 WHERE is_current = 1")[0]["cnt"]
        
        schema_version_row = self.db.execute_query("SELECT version_code FROM schema_evolution_history ORDER BY id DESC LIMIT 1")
        current_version = schema_version_row[0]["version_code"] if schema_version_row else "v1.0"

        return {
            "total_raw_records": total_raw,
            "resolved_golden_entities": total_resolved,
            "duplicates_consolidated": duplicates_removed,
            "deduplication_rate_pct": round(dedupe_rate, 1),
            "similarity_edges_count": total_edges,
            "scd_total_row_versions": total_scd_versions,
            "active_unique_students": active_students,
            "current_schema_version": current_version
        }

    def get_enrollment_by_department(self) -> List[Dict[str, Any]]:
        """Rollup: Total enrollment count, credits, and tuition revenue grouped by department."""
        sql = """
        SELECT 
            d.department_code,
            d.department_name,
            d.school_college,
            COUNT(f.enrollment_fact_id) as total_enrollments,
            SUM(f.credits_enrolled) as total_credits,
            SUM(f.tuition_amount) as total_tuition_revenue,
            ROUND(AVG(f.grade_points), 2) as avg_gpa
        FROM fact_student_enrollment f
        JOIN dim_department d ON f.department_key = d.department_key
        GROUP BY d.department_code, d.department_name, d.school_college
        ORDER BY total_tuition_revenue DESC;
        """
        return self.db.execute_query(sql)

    def get_pre_vs_post_consolidation_impact(self) -> Dict[str, Any]:
        """
        Calculates the distortion error caused by un-deduplicated legacy records
        vs true deduplicated headcount.
        """
        raw_by_sys = self.db.execute_query(
            "SELECT source_system, count(*) as count FROM stg_raw_records GROUP BY source_system"
        )
        resolved_roles = self.db.execute_query(
            "SELECT primary_role, count(*) as count FROM er_resolved_entities GROUP BY primary_role"
        )
        return {
            "raw_distribution": raw_by_sys,
            "resolved_distribution": resolved_roles
        }

    def execute_custom_sql(self, query: str) -> Dict[str, Any]:
        """Executes safe SELECT queries for evaluation workbench."""
        clean_q = query.strip()
        if not clean_q.upper().startswith("SELECT") and not clean_q.upper().startswith("PRAGMA") and not clean_q.upper().startswith("WITH"):
            return {
                "success": False,
                "error": "Only SELECT or PRAGMA queries are allowed in the analytical console for data integrity."
            }
        try:
            results = self.db.execute_query(clean_q)
            cols = list(results[0].keys()) if results else []
            return {
                "success": True,
                "columns": cols,
                "rows": results,
                "row_count": len(results)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

olap_engine = OLAPEngine()
