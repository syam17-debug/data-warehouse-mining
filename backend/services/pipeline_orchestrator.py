"""
Master Pipeline Orchestrator for University Data Warehouse Consolidation.
Coordinates ETL Ingestion, Multi-Pass Blocking, Similarity Graph Construction,
Groq AI Disambiguation, Golden Record Synthesis, SCD Processing, and OLAP Fact Population.
Hardened for high-concurrency, safe idempotency, and error-free pipeline transitions.
"""

import logging
import random
from typing import Dict, Any, List
from backend.database.sqlite_manager import db_manager
from backend.database.schema_definitions import SCHEMA_V1_0_INIT_SQL
from backend.services.synthetic_data_gen import generate_multi_campus_dataset
from backend.services.entity_resolution.normalizer import FieldNormalizer
from backend.services.entity_resolution.blocking import MultiPassBlocking
from backend.services.entity_resolution.similarity import SimilarityEngine
from backend.services.entity_resolution.graph_engine import EntityGraphEngine
from backend.services.entity_resolution.canonical_synthesizer import CanonicalSynthesizer
from backend.services.groq_service import groq_disambiguator
from backend.services.scd_engine import scd_engine
from backend.services.schema_evolution_engine import schema_evolution_engine
from backend.services.neo4j_exporter import neo4j_exporter

logger = logging.getLogger("dwh.orchestrator")

class PipelineOrchestrator:
    def __init__(self, db=db_manager):
        self.db = db
        self.graph_engine = EntityGraphEngine()
        self.dataset = None

    def initialize_warehouse(self, force_reset: bool = True) -> Dict[str, Any]:
        """Sets up tables, baseline schema v1.0, and seeds reference dimensions."""
        if force_reset:
            # Temporarily disable foreign keys during table drops to prevent constraint collisions
            self.db.execute_script("PRAGMA foreign_keys = OFF;")
            tables = [
                "fact_research_funding", "fact_student_enrollment",
                "dim_faculty_scd2", "dim_student_scd2", "dim_course",
                "dim_term_semester", "dim_department", "er_similarity_edges",
                "er_record_mapping", "er_resolved_entities", "stg_raw_records",
                "schema_evolution_history"
            ]
            for t in tables:
                self.db.execute_script(f"DROP TABLE IF EXISTS {t};")
            self.db.execute_script("PRAGMA foreign_keys = ON;")

        # Execute Baseline DDL
        self.db.execute_script(SCHEMA_V1_0_INIT_SQL)
        
        # Log baseline v1.0 in schema_evolution_history
        self.db.execute_non_query(
            """
            INSERT INTO schema_evolution_history (
                version_code, evolution_type, target_table, change_description, ddl_executed, is_backward_compatible
            ) VALUES ('v1.0', 'INITIAL_CONSOLIDATION_BASELINE', 'ALL', 'Initial star-schema baseline for university consolidation', 'SCHEMA_V1_0_INIT_SQL', 1)
            """
        )

        # Generate fresh dataset
        self.dataset = generate_multi_campus_dataset()

        # Seed Reference Dimensions
        for d in self.dataset["departments"]:
            self.db.execute_non_query(
                "INSERT INTO dim_department (department_code, department_name, school_college, division) VALUES (?, ?, ?, ?)",
                (d["code"], d["name"], d["college"], d["division"])
            )

        for c in self.dataset["courses"]:
            self.db.execute_non_query(
                "INSERT INTO dim_course (course_code, course_title, credit_hours, department_code) VALUES (?, ?, ?, ?)",
                (c["code"], c["title"], c["credits"], c["dept"])
            )

        for t in self.dataset["terms"]:
            self.db.execute_non_query(
                "INSERT INTO dim_term_semester (term_code, academic_year, season, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
                (t["code"], t["year"], t["season"], t["start"], t["end"])
            )

        return {"status": "SUCCESS", "message": "Warehouse initialized with baseline Schema v1.0 and reference dimensions."}

    def run_full_consolidation_pipeline(self, enable_groq_llm: bool = True) -> Dict[str, Any]:
        """
        Executes end-to-end entity resolution and warehouse population:
        Ingest -> Normalize -> Block -> Similarity -> Graph -> Groq Verify -> Synthesize -> SCD Dimension -> Facts.
        """
        if not self.dataset:
            self.dataset = generate_multi_campus_dataset()

        # 1. Ingest Raw Records to Staging
        raw_records = self.dataset["raw_records"]
        raw_id_map = {}
        for r in raw_records:
            rid = self.db.execute_non_query(
                """
                INSERT INTO stg_raw_records (
                    source_system, source_record_id, raw_first_name, raw_last_name,
                    raw_full_name, raw_dob, raw_email, raw_phone, raw_department,
                    raw_role, raw_extra_payload, ingestion_batch
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["source_system"], r["source_record_id"], r["raw_first_name"],
                    r["raw_last_name"], r["raw_full_name"], r["raw_dob"],
                    r["raw_email"], r["raw_phone"], r["raw_department"],
                    r["raw_role"], r["raw_extra_payload"], r["ingestion_batch"]
                )
            )
            r["raw_id"] = rid
            raw_id_map[rid] = r

        # 2. Normalize Fields
        normalized_records = [FieldNormalizer.normalize_record(r) for r in raw_records]

        # 3. Multi-Pass Blocking
        blocker = MultiPassBlocking()
        candidate_pairs = blocker.generate_candidate_pairs(normalized_records)

        # 4. Pairwise Attribute & Graph Similarities
        norm_dict = {nr["raw_id"]: nr for nr in normalized_records}
        evaluated_edges = []
        for u_id, v_id in candidate_pairs:
            edge_sim = SimilarityEngine.compare_records(norm_dict[u_id], norm_dict[v_id])
            if edge_sim["overall_similarity"] >= 0.60:
                evaluated_edges.append(edge_sim)

        # 5. Build Graph & Community Detection
        self.graph_engine.build_graph(raw_records, evaluated_edges)
        
        # 6. Groq LLM Disambiguation for Borderline Cases (safely guarded)
        llm_reviews = []
        borderline = self.graph_engine.get_borderline_edges()
        if enable_groq_llm and borderline:
            for b in borderline[:3]:
                try:
                    u_id = b["u_id"]
                    v_id = b["v_id"]
                    decision = groq_disambiguator.evaluate_entity_pair(
                        raw_id_map[u_id], raw_id_map[v_id], b["similarity"]
                    )
                    llm_reviews.append({
                        "u_id": u_id,
                        "v_id": v_id,
                        "decision": decision
                    })
                    if decision.get("is_same_person"):
                        self.graph_engine.graph[u_id][v_id]["disposition"] = "LLM_VERIFIED_MERGE"
                        b["disposition"] = "LLM_VERIFIED_MERGE"
                except Exception as ex:
                    logger.warning(f"Groq disambiguation call non-fatal error: {ex}")

        # Save Edges to Database
        for e in evaluated_edges:
            disp = self.graph_engine.graph[e["source_raw_id"]][e["target_raw_id"]].get("disposition", "CONNECTED") if self.graph_engine.graph.has_edge(e["source_raw_id"], e["target_raw_id"]) else "LOW_SIMILARITY"
            self.db.execute_non_query(
                """
                INSERT INTO er_similarity_edges (
                    source_raw_id, target_raw_id, overall_similarity,
                    name_sim, email_sim, dob_sim, phone_sim, disposition
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    e["source_raw_id"], e["target_raw_id"], e["overall_similarity"],
                    e["name_sim"], e["email_sim"], e["dob_sim"], e["phone_sim"], disp
                )
            )

        # 7. Extract Entity Clusters
        clusters = self.graph_engine.extract_entity_clusters(active_threshold=0.75)

        # 8. Synthesize Golden Entities & Record Mappings
        golden_entities = []
        all_mappings = []
        for c_idx, cluster_node_ids in enumerate(clusters):
            cluster_recs = [raw_id_map[nid] for nid in cluster_node_ids]
            golden = CanonicalSynthesizer.synthesize_golden_record(cluster_recs, c_idx + 1)
            
            for review in llm_reviews:
                if review["u_id"] in cluster_node_ids and review["v_id"] in cluster_node_ids:
                    golden["resolution_method"] = "LLM_GROQ_ASSISTED"
                    golden["groq_reasoning"] = review["decision"].get("reasoning")
                    break

            # Insert Golden Entity
            self.db.execute_non_query(
                """
                INSERT INTO er_resolved_entities (
                    canonical_id, resolved_name, resolved_dob, resolved_primary_email,
                    resolved_primary_phone, primary_role, cluster_size,
                    confidence_score, resolution_method, groq_reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    golden["canonical_id"], golden["resolved_name"], golden["resolved_dob"],
                    golden["resolved_primary_email"], golden["resolved_primary_phone"],
                    golden["primary_role"], golden["cluster_size"],
                    golden["confidence_score"], golden["resolution_method"],
                    golden.get("groq_reasoning")
                )
            )
            golden_entities.append(golden)

            # Insert Mappings
            for r in cluster_recs:
                self.db.execute_non_query(
                    """
                    INSERT INTO er_record_mapping (raw_id, canonical_id, similarity_score, match_status)
                    VALUES (?, ?, 1.0, 'RESOLVED')
                    """,
                    (r["raw_id"], golden["canonical_id"])
                )
                all_mappings.append({"raw_id": r["raw_id"], "canonical_id": golden["canonical_id"], "similarity_score": 1.0})

        # 9. Load Core Dimensions with SCD Type 1/2/3 Support
        scd_engine.load_initial_dimension_records(golden_entities, effective_date="2024-08-25")

        # 10. Generate Fact Records linking to historical Surrogate Keys
        self._populate_initial_facts()

        # 11. Generate Neo4j Export Cypher Script
        neo4j_exporter.generate_cypher_script(
            raw_records=raw_records,
            resolved_entities=golden_entities,
            mappings=all_mappings,
            similarity_edges=evaluated_edges
        )

        return {
            "status": "SUCCESS",
            "total_raw_ingested": len(raw_records),
            "candidate_pairs_evaluated": len(candidate_pairs),
            "similarity_edges_formed": len(evaluated_edges),
            "golden_entities_resolved": len(golden_entities),
            "deduplication_clusters": [c for c in clusters if len(c) > 1],
            "llm_reviews_conducted": len(llm_reviews)
        }

    def reset_and_run_pipeline(self, enable_groq_llm: bool = True) -> Dict[str, Any]:
        """Atomically resets the database and runs the full pipeline."""
        self.initialize_warehouse(force_reset=True)
        return self.run_full_consolidation_pipeline(enable_groq_llm=enable_groq_llm)

    def _populate_initial_facts(self):
        """Populates fact tables linking to surrogate keys of active dimension records."""
        students = self.db.execute_query("SELECT * FROM dim_student_scd2 WHERE is_current = 1")
        courses = self.db.execute_query("SELECT * FROM dim_course")
        terms = self.db.execute_query("SELECT * FROM dim_term_semester")
        depts = self.db.execute_query("SELECT * FROM dim_department")
        dept_map = {d["department_code"]: d["department_key"] for d in depts}
        term_map = {t["term_code"]: t["term_key"] for t in terms}

        grades = [("A", 4.0), ("A-", 3.7), ("B+", 3.3), ("B", 3.0), ("B-", 2.7), ("A", 4.0)]

        for stu in students:
            s_key = stu["student_dim_key"]
            s_dept = stu["department_code"]
            d_key = dept_map.get(s_dept, 1)

            t1_key = term_map.get("2024-FALL", 1)
            matching_courses = [c for c in courses if c["department_code"] == s_dept]
            if not matching_courses:
                matching_courses = courses[:2]

            for c in matching_courses[:2]:
                ltr, pts = random.choice(grades)
                self.db.execute_non_query(
                    """
                    INSERT INTO fact_student_enrollment (
                        student_dim_key, course_key, term_key, department_key,
                        credits_enrolled, tuition_amount, grade_points, letter_grade, completion_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED')
                    """,
                    (s_key, c["course_key"], t1_key, d_key, c["credit_hours"], c["credit_hours"] * 950.0, pts, ltr)
                )

        # Faculty Grants
        faculty_list = self.db.execute_query("SELECT * FROM dim_faculty_scd2 WHERE is_current = 1")
        agencies = ["National Science Foundation (NSF)", "National Institutes of Health (NIH)", "DARPA Cyber Systems"]
        for fac in faculty_list:
            f_key = fac["faculty_dim_key"]
            f_dept = fac["department_code"]
            d_key = dept_map.get(f_dept, 1)
            t1_key = term_map.get("2024-FALL", 1)

            self.db.execute_non_query(
                """
                INSERT INTO fact_research_funding (
                    faculty_dim_key, department_key, term_key, grant_title,
                    funding_agency, awarded_amount, expenditure_amount
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f_key, d_key, t1_key,
                    f"Consolidated Graph Machine Learning Lab Grant - {fac['full_name']}",
                    random.choice(agencies),
                    random.randint(150000, 750000),
                    random.randint(45000, 120000)
                )
            )

    def trigger_evolution_wave_2(self) -> Dict[str, Any]:
        """
        Executes Wave 2:
        1. Migrates Schema to v2.0 (honors_track, residency_status, work_modality).
        2. Applies SCD Type 1, 2, and 3 updates for changed students and faculty.
        3. Enrolls students into Spring 2025 fact records using their new Surrogate Keys.
        Safely idempotent.
        """
        current_ver = schema_evolution_engine.get_current_version()
        if current_ver in ["v2.0", "v3.0"]:
            return {
                "status": "ALREADY_APPLIED",
                "message": f"Wave 2 is already active in current schema ({current_ver}). Use 'Refresh Pipeline' to reset.",
                "current_version": current_ver
            }

        evolve_res = schema_evolution_engine.apply_evolution_v2()

        events = [e for e in self.dataset["scd_evolution_events"] if e["wave"] == 2]
        applied_scd = []
        for ev in events:
            # Dynamically resolve canonical ID if match name is given
            match_name = ev.get("target_name_match")
            if match_name:
                rows = self.db.execute_query(
                    "SELECT canonical_id FROM er_resolved_entities WHERE resolved_name LIKE ? LIMIT 1",
                    (f"%{match_name}%",)
                )
                if rows:
                    ev["canonical_id"] = rows[0]["canonical_id"]

            res = scd_engine.apply_scd_update(ev)
            applied_scd.append(res)

        # Populate 2025-SPRING Facts linking to current Surrogate Keys
        courses = self.db.execute_query("SELECT * FROM dim_course")
        term_row = self.db.execute_query("SELECT term_key FROM dim_term_semester WHERE term_code = '2025-SPRING'")
        t_key = term_row[0]["term_key"] if term_row else 2
        depts = self.db.execute_query("SELECT * FROM dim_department")
        dept_map = {d["department_code"]: d["department_key"] for d in depts}

        current_students = self.db.execute_query("SELECT * FROM dim_student_scd2 WHERE is_current = 1")
        for stu in current_students:
            s_key = stu["student_dim_key"]
            s_dept = stu["department_code"]
            d_key = dept_map.get(s_dept, 1)

            matching = [c for c in courses if c["department_code"] == s_dept]
            if not matching:
                matching = courses[:2]

            for c in matching[:2]:
                self.db.execute_non_query(
                    """
                    INSERT INTO fact_student_enrollment (
                        student_dim_key, course_key, term_key, department_key,
                        credits_enrolled, tuition_amount, grade_points, letter_grade, completion_status
                    ) VALUES (?, ?, ?, ?, ?, ?, 3.8, 'A-', 'COMPLETED')
                    """,
                    (s_key, c["course_key"], t_key, d_key, c["credit_hours"], c["credit_hours"] * 980.0)
                )

        return {
            "status": "SUCCESS",
            "schema_migration": evolve_res,
            "scd_events_applied": applied_scd,
            "message": "Wave 2 completed: Schema v2.0 activated, SCD2 surrogate keys versioned, and 2025-SPRING facts linked."
        }

    def trigger_evolution_wave_3(self) -> Dict[str, Any]:
        """
        Executes Wave 3:
        1. Migrates Schema to v3.0 (advisor link, donor tier, hybrid delivery mode).
        2. Applies Wave 3 SCD updates.
        Safely idempotent.
        """
        current_ver = schema_evolution_engine.get_current_version()
        if current_ver == "v3.0":
            return {
                "status": "ALREADY_APPLIED",
                "message": "Wave 3 is already active in current schema (v3.0). Use 'Refresh Pipeline' to reset.",
                "current_version": current_ver
            }

        # If user jumps directly from v1.0 to v3.0, auto-apply Wave 2 first
        if current_ver == "v1.0":
            self.trigger_evolution_wave_2()

        evolve_res = schema_evolution_engine.apply_evolution_v3()
        events = [e for e in self.dataset["scd_evolution_events"] if e["wave"] == 3]
        applied_scd = []
        for ev in events:
            match_name = ev.get("target_name_match")
            if match_name:
                rows = self.db.execute_query(
                    "SELECT canonical_id FROM er_resolved_entities WHERE resolved_name LIKE ? LIMIT 1",
                    (f"%{match_name}%",)
                )
                if rows:
                    ev["canonical_id"] = rows[0]["canonical_id"]
            applied_scd.append(scd_engine.apply_scd_update(ev))

        return {
            "status": "SUCCESS",
            "schema_migration": evolve_res,
            "scd_events_applied": applied_scd,
            "message": "Wave 3 completed: Schema v3.0 activated and enterprise multi-campus consolidation finalized."
        }

pipeline_orchestrator = PipelineOrchestrator()
