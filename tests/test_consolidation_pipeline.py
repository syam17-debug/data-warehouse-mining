"""
Automated Unit and Integration Tests for University Data Warehouse Consolidation.
Validates Field Normalization, Multi-Pass Blocking, Similarity Scoring, Graph Louvain Partitioning,
SCD Type 1/2/3 Versioning, Time-Travel Queries, and Schema Evolution.
"""

import unittest
from backend.services.entity_resolution.normalizer import FieldNormalizer
from backend.services.entity_resolution.blocking import MultiPassBlocking
from backend.services.entity_resolution.similarity import SimilarityEngine
from backend.services.entity_resolution.graph_engine import EntityGraphEngine
from backend.services.entity_resolution.canonical_synthesizer import CanonicalSynthesizer
from backend.services.pipeline_orchestrator import pipeline_orchestrator
from backend.services.scd_engine import scd_engine
from backend.services.schema_evolution_engine import schema_evolution_engine
from backend.database.sqlite_manager import db_manager

class TestDWHConsolidationPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Initialize fresh test database
        pipeline_orchestrator.initialize_warehouse(force_reset=True)

    def test_01_normalization(self):
        """Tests name stripping, phone normalization, and phonetic hashing."""
        sample = {
            "raw_id": 1,
            "raw_full_name": "Dr. Eleanor S. Vance, Ph.D.",
            "raw_dob": "04/14/1999",
            "raw_email": "e.vance@north.univ.edu",
            "raw_phone": "(555) 019-2831",
            "source_system": "SIS_CAMPUS_NORTH"
        }
        norm = FieldNormalizer.normalize_record(sample)
        self.assertEqual(norm["norm_dob"], "1999-04-14")
        self.assertEqual(norm["norm_phone"], "5550192831")
        self.assertEqual(norm["norm_name"]["clean_full"], "eleanor s vance")
        self.assertTrue(len(norm["norm_name"]["soundex_first"]) > 0)
        self.assertTrue(len(norm["norm_name"]["metaphone_last"]) > 0)

    def test_02_similarity_and_homonym_safeguard(self):
        """Verifies duplicate scoring and checks that homonyms with disparate DOBs are penalized."""
        rec1 = FieldNormalizer.normalize_record({
            "raw_id": 1, "raw_full_name": "David Smith", "raw_dob": "1998-07-19",
            "raw_email": "d.smith@north.univ.edu", "raw_phone": "555-011-3322"
        })
        # Same name, different person born in 1995
        rec2 = FieldNormalizer.normalize_record({
            "raw_id": 2, "raw_full_name": "David Smith", "raw_dob": "1995-03-11",
            "raw_email": "d.smith.hr@south.univ.edu", "raw_phone": "555-099-7744"
        })
        sim = SimilarityEngine.compare_records(rec1, rec2)
        # Should be penalized below auto-merge threshold due to DOB discrepancy
        self.assertLess(sim["overall_similarity"], 0.70)

        # True duplicate with nickname: Eleanor Vance vs Ellie Vance
        rec3 = FieldNormalizer.normalize_record({
            "raw_id": 3, "raw_full_name": "Ellie Vance", "raw_dob": "1999-04-14",
            "raw_email": "ellie.vance@gmail.com", "raw_phone": "555-019-2831"
        })
        rec4 = FieldNormalizer.normalize_record({
            "raw_id": 4, "raw_full_name": "Eleanor Vance", "raw_dob": "1999-04-14",
            "raw_email": "e.vance@north.univ.edu", "raw_phone": "555-019-2831"
        })
        sim_true = SimilarityEngine.compare_records(rec3, rec4)
        self.assertGreaterEqual(sim_true["overall_similarity"], 0.75)

    def test_03_end_to_end_consolidation(self):
        """Executes full pipeline and verifies golden entities, mappings, and facts."""
        result = pipeline_orchestrator.run_full_consolidation_pipeline(enable_groq_llm=False)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertGreater(result["golden_entities_resolved"], 5)
        self.assertGreater(len(result["deduplication_clusters"]), 0)

        # Verify fact table populated
        facts = db_manager.execute_query("SELECT count(*) as cnt FROM fact_student_enrollment")
        self.assertGreater(facts[0]["cnt"], 0)

    def test_04_scd_evolution_and_time_travel(self):
        """Verifies SCD Type 1 overwrite, SCD Type 2 row versioning, and time-travel query."""
        # Find Eleanor Vance canonical ID dynamically
        eleanor = db_manager.execute_query(
            "SELECT canonical_id FROM er_resolved_entities WHERE resolved_name LIKE '%Eleanor%' OR resolved_name LIKE '%Ellie%'"
        )
        self.assertTrue(len(eleanor) > 0)
        cid = eleanor[0]["canonical_id"]

        history_before = scd_engine.get_entity_history(cid)
        self.assertEqual(len(history_before), 1)
        self.assertEqual(history_before[0]["version_num"], 1)
        self.assertEqual(history_before[0]["department_code"], "CS")

        # Apply Wave 2 evolution
        wave2_res = pipeline_orchestrator.trigger_evolution_wave_2()
        self.assertEqual(wave2_res["status"], "SUCCESS")

        # Eleanor Vance should now have 2 versions
        history_after = scd_engine.get_entity_history(cid)
        self.assertEqual(len(history_after), 2)
        v1 = history_after[0]
        v2 = history_after[1]

        self.assertEqual(v1["is_current"], 0)
        self.assertEqual(v1["valid_to"], "2025-01-14")
        self.assertEqual(v1["department_code"], "CS")

        self.assertEqual(v2["is_current"], 1)
        self.assertEqual(v2["valid_from"], "2025-01-15")
        self.assertEqual(v2["valid_to"], "9999-12-31")
        self.assertEqual(v2["department_code"], "MATH")
        self.assertEqual(v2["prev_department_code"], "CS")

        # Time Travel Test: As of 2024-10-01, Eleanor was in CS!
        hist_rec = scd_engine.query_as_of_date(cid, "2024-10-01")
        self.assertIsNotNone(hist_rec)
        self.assertEqual(hist_rec["department_code"], "CS")

        # As of 2025-03-01, Eleanor was in MATH!
        curr_rec = scd_engine.query_as_of_date(cid, "2025-03-01")
        self.assertIsNotNone(curr_rec)
        self.assertEqual(curr_rec["department_code"], "MATH")

    def test_05_schema_evolution_migration(self):
        """Verifies schema drift detection and non-destructive DDL evolution to v3.0."""
        # Drift check
        drift = schema_evolution_engine.detect_schema_drift(["assigned_advisor_faculty_id"], "dim_student_scd2")
        self.assertTrue(drift["has_drift"])

        # Apply Wave 3
        wave3_res = pipeline_orchestrator.trigger_evolution_wave_3()
        self.assertEqual(wave3_res["status"], "SUCCESS")

        # Drift should now be resolved
        drift_after = schema_evolution_engine.detect_schema_drift(["assigned_advisor_faculty_id"], "dim_student_scd2")
        self.assertFalse(drift_after["has_drift"])

        # Schema version should be v3.0
        self.assertEqual(schema_evolution_engine.get_current_version(), "v3.0")

if __name__ == "__main__":
    unittest.main()
