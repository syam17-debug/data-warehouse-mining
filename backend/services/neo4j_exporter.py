"""
Neo4j Graph Integration & Cypher Export Engine.
Generates production-grade Cypher scripts for Neo4j import and provides optional
live connection bridge via neo4j Bolt driver when available.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from backend.config import NEO4J_EXPORT_PATH

class Neo4jGraphExporter:
    @staticmethod
    def generate_cypher_script(
        raw_records: List[Dict[str, Any]],
        resolved_entities: List[Dict[str, Any]],
        mappings: List[Dict[str, Any]],
        similarity_edges: List[Dict[str, Any]],
        output_path: Optional[Path] = None
    ) -> str:
        """
        Generates Cypher DDL and DML to load the entity resolution graph into Neo4j.
        """
        lines = [
            "// =================================================================",
            "// Neo4j Cypher Export: University Data Warehouse Entity Resolution",
            "// =================================================================",
            "",
            "// 1. Constraints & Indexes",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:RawRecord) REQUIRE r.raw_id IS UNIQUE;",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (g:GoldenEntity) REQUIRE g.canonical_id IS UNIQUE;",
            "CREATE INDEX IF NOT EXISTS FOR (r:RawRecord) ON (r.email);",
            "",
            "// 2. Load Raw Records",
        ]

        # Insert Raw Records
        for r in raw_records:
            rid = r.get("raw_id")
            sys = r.get("source_system", "UNKNOWN")
            name = (r.get("raw_full_name") or f"{r.get('raw_first_name', '')} {r.get('raw_last_name', '')}").replace("'", "\\'")
            email = (r.get("raw_email") or "").replace("'", "\\'")
            dob = r.get("raw_dob") or ""
            role = r.get("raw_role") or "STUDENT"
            dept = r.get("raw_department") or ""

            lines.append(
                f"MERGE (r:RawRecord {{raw_id: {rid}}}) "
                f"ON CREATE SET r.name = '{name}', r.source_system = '{sys}', "
                f"r.email = '{email}', r.dob = '{dob}', r.role = '{role}', r.department = '{dept}';"
            )

        lines.append("\n// 3. Load Golden Resolved Entities")
        for g in resolved_entities:
            cid = g.get("canonical_id")
            name = (g.get("resolved_name") or "").replace("'", "\\'")
            email = (g.get("resolved_primary_email") or "").replace("'", "\\'")
            role = g.get("primary_role") or "STUDENT"
            conf = g.get("confidence_score", 1.0)

            lines.append(
                f"MERGE (g:GoldenEntity {{canonical_id: '{cid}'}}) "
                f"ON CREATE SET g.name = '{name}', g.primary_email = '{email}', "
                f"g.role = '{role}', g.confidence = {conf};"
            )

        lines.append("\n// 4. Create RESOLVED_TO Relationships (RawRecord -> GoldenEntity)")
        for m in mappings:
            rid = m.get("raw_id")
            cid = m.get("canonical_id")
            sim = m.get("similarity_score", 1.0)
            lines.append(
                f"MATCH (r:RawRecord {{raw_id: {rid}}}), (g:GoldenEntity {{canonical_id: '{cid}'}}) "
                f"MERGE (r)-[:RESOLVED_TO {{similarity: {sim}}}]->(g);"
            )

        lines.append("\n// 5. Create SIMILAR_TO Undirected Graph Edges")
        for e in similarity_edges:
            u = e.get("source_raw_id")
            v = e.get("target_raw_id")
            w = e.get("overall_similarity", 0.0)
            if w >= 0.65:
                lines.append(
                    f"MATCH (a:RawRecord {{raw_id: {u}}}), (b:RawRecord {{raw_id: {v}}}) "
                    f"MERGE (a)-[:SIMILAR_TO {{weight: {w}}}]-(b);"
                )

        cypher_text = "\n".join(lines)
        
        target = output_path or NEO4J_EXPORT_PATH
        with open(target, "w", encoding="utf-8") as f:
            f.write(cypher_text)
            
        return cypher_text

    @staticmethod
    def test_live_connection(uri: str = "neo4j://localhost:7687", auth: tuple = ("neo4j", "password")) -> Dict[str, Any]:
        """Tests live bolt connection if Neo4j driver is installed."""
        try:
            import neo4j
            driver = neo4j.GraphDatabase.driver(uri, auth=auth)
            with driver.session() as session:
                result = session.run("RETURN 1 as ping").single()
                driver.close()
                return {"connected": True, "ping": result["ping"]}
        except ImportError:
            return {"connected": False, "message": "neo4j Python package not installed (optional). Cypher export available."}
        except Exception as e:
            return {"connected": False, "message": f"Connection failed: {str(e)}"}

neo4j_exporter = Neo4jGraphExporter()
