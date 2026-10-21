"""
FastAPI REST API Routes for University Data Warehouse Consolidation.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from backend.services.pipeline_orchestrator import pipeline_orchestrator
from backend.services.scd_engine import scd_engine
from backend.services.schema_evolution_engine import schema_evolution_engine
from backend.services.olap_engine import olap_engine
from backend.services.groq_service import groq_disambiguator
from backend.database.sqlite_manager import db_manager
from backend.config import NEO4J_EXPORT_PATH

api_router = APIRouter(prefix="/api")

class SQLQueryRequest(BaseModel):
    query: str

class DisambiguationRequest(BaseModel):
    record1: Dict[str, Any]
    record2: Dict[str, Any]
    similarity: float = 0.72

@api_router.get("/overview")
def get_overview_metrics():
    """Returns high-level system overview and metrics."""
    return olap_engine.get_summary_kpis()

@api_router.get("/raw-records")
def get_raw_staging_records():
    """Returns all original ingested raw staging records with duplicate mapping annotations."""
    sql = """
    SELECT 
        r.raw_id,
        r.source_system,
        r.source_record_id,
        r.raw_full_name,
        r.raw_dob,
        r.raw_email,
        r.raw_phone,
        r.raw_department,
        r.raw_role,
        m.canonical_id,
        e.resolved_name,
        e.cluster_size,
        CASE WHEN e.cluster_size > 1 THEN 1 ELSE 0 END as is_duplicate
    FROM stg_raw_records r
    LEFT JOIN er_record_mapping m ON r.raw_id = m.raw_id
    LEFT JOIN er_resolved_entities e ON m.canonical_id = e.canonical_id
    ORDER BY r.raw_id ASC;
    """
    rows = db_manager.execute_query(sql)
    total = len(rows)
    duplicates = sum(1 for r in rows if r["is_duplicate"] == 1)
    singletons = total - duplicates
    return {
        "total_count": total,
        "duplicate_count": duplicates,
        "singleton_count": singletons,
        "deduplication_rate_pct": round((duplicates / total * 100), 1) if total > 0 else 0,
        "records": rows
    }

@api_router.post("/pipeline/initialize")
def initialize_warehouse(force_reset: bool = True):
    """Initializes SQLite database with Schema v1.0 and reference dimensions."""
    return pipeline_orchestrator.initialize_warehouse(force_reset=force_reset)

@api_router.post("/pipeline/reset-and-run")
def reset_and_run_pipeline(enable_groq: bool = True):
    """Atomically resets the warehouse and executes the full consolidation pipeline."""
    return pipeline_orchestrator.reset_and_run_pipeline(enable_groq_llm=enable_groq)

@api_router.post("/pipeline/run")
def run_consolidation_pipeline(enable_groq: bool = True):
    """Executes the full graph-based entity resolution and DWH load pipeline."""
    return pipeline_orchestrator.run_full_consolidation_pipeline(enable_groq_llm=enable_groq)

@api_router.post("/pipeline/wave2")
def trigger_wave_2():
    """Triggers Wave 2: Schema Evolution v2.0 and SCD mutations."""
    return pipeline_orchestrator.trigger_evolution_wave_2()

@api_router.post("/pipeline/wave3")
def trigger_wave_3():
    """Triggers Wave 3: Schema Evolution v3.0 and Final Consolidation."""
    return pipeline_orchestrator.trigger_evolution_wave_3()

@api_router.get("/graph/data")
def get_graph_data():
    """Returns Vis.js formatted nodes and edges for interactive network graph."""
    return pipeline_orchestrator.graph_engine.export_graph_for_visualization()

@api_router.get("/entities")
def get_resolved_entities():
    """Lists all resolved golden entities with mapped source records."""
    entities = db_manager.execute_query("SELECT * FROM er_resolved_entities ORDER BY cluster_size DESC")
    # Attach mapped raw records
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
    return entities

@api_router.get("/entities/{canonical_id}/history")
def get_entity_scd_history(canonical_id: str):
    """Returns full SCD history timeline for an entity."""
    history = scd_engine.get_entity_history(canonical_id)
    if not history:
        raise HTTPException(status_code=404, detail="Entity history not found")
    return {
        "canonical_id": canonical_id,
        "versions_count": len(history),
        "versions": history
    }

@api_router.get("/entities/{canonical_id}/as-of")
def get_entity_as_of_date(canonical_id: str, date: str = Query(..., description="Target date in YYYY-MM-DD")):
    """Point-in-Time Historical Query (Time-Travel)."""
    record = scd_engine.query_as_of_date(canonical_id, date)
    if not record:
        raise HTTPException(status_code=404, detail=f"No active record found for {canonical_id} as of {date}")
    return {
        "canonical_id": canonical_id,
        "as_of_date": date,
        "effective_record": record
    }

@api_router.get("/schema/evolution")
def get_schema_evolution():
    """Returns schema evolution logs and full database catalog."""
    return {
        "current_version": schema_evolution_engine.get_current_version(),
        "history": schema_evolution_engine.get_evolution_history(),
        "catalog": schema_evolution_engine.get_full_schema_catalog()
    }

@api_router.post("/groq/disambiguate")
def test_groq_disambiguation(req: DisambiguationRequest):
    """Tests Groq LLM semantic reasoning on an entity pair."""
    return groq_disambiguator.evaluate_entity_pair(req.record1, req.record2, req.similarity)

@api_router.get("/olap/enrollment-by-dept")
def get_olap_enrollment():
    """Returns enrollment and tuition rollup by department."""
    return olap_engine.get_enrollment_by_department()

@api_router.get("/olap/pre-vs-post")
def get_olap_pre_vs_post():
    """Returns pre-consolidation raw records vs post-consolidation resolved entities."""
    return olap_engine.get_pre_vs_post_consolidation_impact()

@api_router.post("/olap/sql")
def execute_sql(req: SQLQueryRequest):
    """Executes safe custom SQL query against the consolidated data warehouse."""
    return olap_engine.execute_custom_sql(req.query)

@api_router.get("/export/cypher")
def download_cypher_script():
    """Returns generated Neo4j Cypher export script."""
    if not NEO4J_EXPORT_PATH.exists():
        return {"error": "Cypher export not yet generated. Run the pipeline first."}
    with open(NEO4J_EXPORT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    return {"filename": "neo4j_graph_export.cypher", "content": content}
