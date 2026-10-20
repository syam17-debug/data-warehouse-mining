"""
Streamlit Cloud Deployment Application for University Data Warehouse Consolidation.
Main entry point for Streamlit Cloud (share.streamlit.io).
Delivers the exact same high-performance, executive light-themed UI with full
Vis.js interactive graph, Chart.js analytics, SCD time-travel, and Neo4j Cypher exports.
"""

import sys
import os
import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

# Configure paths
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Streamlit Page Config (Clean light palette matching executive theme)
st.set_page_config(
    page_title="University DWH Consolidation | Graph ER & SCD",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS to eliminate Streamlit frame margins and give seamless native appearance
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 0.2rem !important;
            padding-bottom: 0rem !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
            max-width: 100% !important;
        }
        header[data-testid="stHeader"] {
            display: none !important;
        }
        footer {
            display: none !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

@st.cache_resource(show_spinner="Initializing Enterprise Data Warehouse...")
def initialize_dwh():
    """Initializes and runs the consolidation pipeline once on startup."""
    from backend.database.sqlite_manager import db_manager
    from backend.services.pipeline_orchestrator import pipeline_orchestrator
    from backend.services.olap_engine import olap_engine
    from backend.services.schema_evolution_engine import schema_evolution_engine
    from backend.config import NEO4J_EXPORT_PATH

    # Initialize if table missing
    if not db_manager.table_exists("dim_student_scd2"):
        pipeline_orchestrator.initialize_warehouse(force_reset=True)
        pipeline_orchestrator.run_full_consolidation_pipeline(enable_groq_llm=False)

    # Ensure graph is populated from database if running in fresh process
    if pipeline_orchestrator.graph_engine.graph.number_of_nodes() == 0:
        raw_recs = db_manager.execute_query("SELECT * FROM stg_raw_records")
        edge_recs = db_manager.execute_query("SELECT * FROM er_similarity_edges")
        pipeline_orchestrator.graph_engine.build_graph(raw_recs, edge_recs)

    overview = olap_engine.get_summary_kpis()
    graph_data = pipeline_orchestrator.graph_engine.export_graph_for_visualization()
    
    # Query entities with mapped records
    entities = db_manager.execute_query("SELECT * FROM er_resolved_entities ORDER BY cluster_size DESC")
    for ent in entities:
        cid = ent["canonical_id"]
        mapped_rows = db_manager.execute_query(
            """
            SELECT r.*, m.similarity_score 
            FROM er_record_mapping m
            JOIN stg_raw_records r ON m.raw_id = r.raw_id
            WHERE m.canonical_id = ?
            """,
            (cid,)
        )
        ent["mapped_records"] = mapped_rows

    scd_records = db_manager.execute_query(
        """SELECT student_dim_key, canonical_student_id, full_name, department_code, 
                  prev_department_code, valid_from, valid_to, version_num, is_current 
           FROM dim_student_scd2 
           ORDER BY canonical_student_id, version_num ASC;"""
    )
    schema_history = schema_evolution_engine.get_evolution_history()
    catalog = schema_evolution_engine.get_full_schema_catalog()
    dept_data = olap_engine.get_enrollment_by_department()
    impact_data = olap_engine.get_pre_vs_post_consolidation_impact()

    cypher_content = ""
    if NEO4J_EXPORT_PATH.exists():
        with open(NEO4J_EXPORT_PATH, "r", encoding="utf-8") as f:
            cypher_content = f.read()

    # Pre-computed SQL samples
    sql_precomputed = {
        1: olap_engine.execute_custom_sql(
            """SELECT d.department_code, d.department_name, COUNT(f.enrollment_fact_id) as total_enrollments,
                      SUM(f.credits_enrolled) as total_credits, PRINTF('$%,d', CAST(SUM(f.tuition_amount) AS INT)) as tuition_revenue,
                      ROUND(AVG(f.grade_points), 2) as avg_grade_point
               FROM fact_student_enrollment f JOIN dim_department d ON f.department_key = d.department_key
               GROUP BY d.department_code, d.department_name ORDER BY SUM(f.tuition_amount) DESC;"""
        ),
        2: olap_engine.execute_custom_sql(
            """SELECT canonical_student_id, full_name, version_num, department_code as current_dept,
                      prev_department_code as previous_dept, valid_from, valid_to, is_current, effective_reason
               FROM dim_student_scd2 WHERE prev_department_code IS NOT NULL OR version_num > 1
               ORDER BY canonical_student_id, version_num;"""
        ),
        3: olap_engine.execute_custom_sql(
            """SELECT fac.full_name as faculty_pi, fac.academic_rank, fac.department_code,
                      gr.grant_title, gr.funding_agency, PRINTF('$%,d', CAST(gr.awarded_amount AS INT)) as awarded_grant
               FROM fact_research_funding gr JOIN dim_faculty_scd2 fac ON gr.faculty_dim_key = fac.faculty_dim_key
               ORDER BY gr.awarded_amount DESC;"""
        ),
        4: olap_engine.execute_custom_sql(
            """SELECT 'Raw Unconsolidated Records' as metric_category, source_system as system_or_role, COUNT(*) as record_count
               FROM stg_raw_records GROUP BY source_system
               UNION ALL
               SELECT 'Consolidated Golden Entities' as metric_category, primary_role as system_or_role, COUNT(*) as record_count
               FROM er_resolved_entities GROUP BY primary_role;"""
        )
    }

    return {
        "overview": overview,
        "graph_data": graph_data,
        "entities": entities,
        "scd_records": scd_records,
        "schema_history": schema_history,
        "catalog": catalog,
        "dept_data": dept_data,
        "impact_data": impact_data,
        "cypher_content": cypher_content,
        "sql_precomputed": sql_precomputed
    }

def main():
    dwh_data = initialize_dwh()

    # Read frontend files
    html_file = BASE_DIR / "frontend" / "index.html"
    js_file = BASE_DIR / "frontend" / "app.js"

    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    with open(js_file, "r", encoding="utf-8") as f:
        js_content = f.read()

    # Inject the serialized data and JS code inline
    serialized_json = json.dumps(dwh_data, default=str)
    injection_script = f"""
    <script>
        window.INJECTED_DWH_DATA = true;
        window.INJECTED_DATA = {serialized_json};
    </script>
    <script>
        {js_content}
    </script>
    """

    # Replace external script tag with our injected inline script
    if '<script src="/static/app.js"></script>' in html_content:
        full_html = html_content.replace('<script src="/static/app.js"></script>', injection_script)
    else:
        full_html = html_content + injection_script

    # Render exact same interactive single-page dashboard
    components.html(full_html, height=1050, scrolling=True)

    # Streamlit Sidebar Controls & Quick Downloads
    with st.sidebar:
        st.markdown("### 🏛️ University DWH Control Center")
        st.caption("Data Mining & Warehousing Major Project")
        st.divider()

        st.metric("Total Raw Records", dwh_data["overview"].get("total_raw_records", 53))
        st.metric("Golden Entities", dwh_data["overview"].get("resolved_golden_entities", 29))
        st.metric("Deduplication Rate", f"{dwh_data['overview'].get('deduplication_rate_pct', 45.3)}%")

        st.divider()
        st.markdown("**Quick Exports & Tools**")
        st.download_button(
            label="📥 Download Neo4j Cypher Script",
            data=dwh_data.get("cypher_content", ""),
            file_name="university_dwh_graph_export.cypher",
            mime="text/plain"
        )
        st.caption("Deployable on Streamlit Cloud & Localhost")

if __name__ == "__main__":
    main()
