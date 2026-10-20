"""
NetworkX Graph Engine for Entity Resolution and Community Deduplication.
Constructs entity graphs, computes transitive closures, executes community detection,
and extracts canonical entity clusters.
"""

from typing import List, Dict, Any, Tuple, Set
import networkx as nx
from networkx.algorithms.community import louvain_communities
from backend.config import THRESHOLD_AUTO_MERGE, THRESHOLD_BORDERLINE

class EntityGraphEngine:
    def __init__(self):
        self.graph = nx.Graph()

    def build_graph(self, raw_records: List[Dict[str, Any]], similarity_edges: List[Dict[str, Any]]):
        """Constructs the undirected entity relationship graph."""
        self.graph.clear()
        
        # 1. Add Nodes
        for r in raw_records:
            rid = r["raw_id"]
            self.graph.add_node(
                rid,
                raw_id=rid,
                label=r.get("raw_full_name") or f"{r.get('raw_first_name', '')} {r.get('raw_last_name', '')}".strip(),
                source_system=r.get("source_system", "UNKNOWN"),
                source_record_id=r.get("source_record_id", ""),
                dob=r.get("raw_dob", ""),
                email=r.get("raw_email", ""),
                phone=r.get("raw_phone", ""),
                role=r.get("raw_role", "STUDENT"),
                department=r.get("raw_department", "")
            )

        # 2. Add Edges that meet minimum threshold
        for edge in similarity_edges:
            score = edge["overall_similarity"]
            u = edge["source_raw_id"]
            v = edge["target_raw_id"]
            
            if score >= THRESHOLD_BORDERLINE:
                self.graph.add_edge(
                    u, v,
                    weight=score,
                    name_sim=edge.get("name_sim", 0.0),
                    email_sim=edge.get("email_sim", 0.0),
                    dob_sim=edge.get("dob_sim", 0.0),
                    phone_sim=edge.get("phone_sim", 0.0),
                    disposition=edge.get("disposition", "CONNECTED")
                )

    def extract_entity_clusters(self, active_threshold: float = THRESHOLD_AUTO_MERGE) -> List[List[int]]:
        """
        Partitions the graph into entity clusters using connected components on edges >= active_threshold.
        Applies Louvain community detection if a connected component is overly dense or ambiguous.
        """
        # Create a view/subgraph with confident edges
        confident_edges = [
            (u, v) for u, v, data in self.graph.edges(data=True)
            if data.get("weight", 0.0) >= active_threshold or data.get("disposition") == "LLM_VERIFIED_MERGE"
        ]
        
        sub_g = nx.Graph()
        # Include all nodes so singleton entities are retained
        sub_g.add_nodes_from(self.graph.nodes(data=True))
        sub_g.add_edges_from(confident_edges)
        
        clusters = []
        for component in nx.connected_components(sub_g):
            comp_nodes = list(component)
            if len(comp_nodes) > 4:
                # Dense component: apply Louvain modularity clustering
                comp_subgraph = sub_g.subgraph(comp_nodes)
                try:
                    communities = louvain_communities(comp_subgraph, seed=42)
                    for comm in communities:
                        clusters.append(sorted(list(comm)))
                except Exception:
                    clusters.append(sorted(comp_nodes))
            else:
                clusters.append(sorted(comp_nodes))
                
        # Sort clusters by size descending, then by first id
        clusters.sort(key=lambda c: (-len(c), c[0] if c else 0))
        return clusters

    def get_borderline_edges(self) -> List[Dict[str, Any]]:
        """Returns pairs that require LLM verification or human review."""
        borderline = []
        for u, v, data in self.graph.edges(data=True):
            w = data.get("weight", 0.0)
            disp = data.get("disposition", "CONNECTED")
            if THRESHOLD_BORDERLINE <= w < THRESHOLD_AUTO_MERGE and disp != "LLM_VERIFIED_MERGE":
                u_node = self.graph.nodes[u]
                v_node = self.graph.nodes[v]
                borderline.append({
                    "u_id": u,
                    "v_id": v,
                    "u_record": u_node,
                    "v_record": v_node,
                    "similarity": w,
                    "name_sim": data.get("name_sim"),
                    "email_sim": data.get("email_sim"),
                    "dob_sim": data.get("dob_sim"),
                    "phone_sim": data.get("phone_sim")
                })
        return borderline

    def export_graph_for_visualization(self, active_threshold: float = 0.65) -> Dict[str, Any]:
        """
        Formats network graph into Vis.js / D3 compatible JSON payload.
        Light pastel color scheme compliant with user requirements.
        """
        nodes_payload = []
        # Light pastel colors for distinct source systems
        system_colors = {
            "SIS_CAMPUS_NORTH": {"background": "#e0e7ff", "border": "#6366f1"},  # Soft indigo
            "HR_CAMPUS_SOUTH": {"background": "#fef3c7", "border": "#d97706"},   # Soft amber
            "PORTAL_ONLINE_ADM": {"background": "#dcfce7", "border": "#10b981"}, # Soft emerald
            "ALUMNI_ADVANCEMENT": {"background": "#fae8ff", "border": "#c026d3"},# Soft fuchsia
            "UNKNOWN": {"background": "#f1f5f9", "border": "#64748b"}
        }

        for node_id, data in self.graph.nodes(data=True):
            sys = data.get("source_system", "UNKNOWN")
            color_cfg = system_colors.get(sys, system_colors["UNKNOWN"])
            
            tooltip = f"<b>{data.get('label')}</b><br>" \
                      f"System: {sys}<br>" \
                      f"ID: {data.get('source_record_id')}<br>" \
                      f"DOB: {data.get('dob')}<br>" \
                      f"Email: {data.get('email')}<br>" \
                      f"Role: {data.get('role')} | Dept: {data.get('department')}"
            
            nodes_payload.append({
                "id": node_id,
                "label": f"{data.get('label')}\n({sys[:6]})",
                "title": tooltip,
                "shape": "dot",
                "size": 18,
                "color": color_cfg,
                "font": {"color": "#1e293b", "size": 11, "face": "Inter, sans-serif"},
                "source_system": sys,
                "raw_data": data
            })

        edges_payload = []
        for u, v, data in self.graph.edges(data=True):
            w = data.get("weight", 0.0)
            disp = data.get("disposition", "CONNECTED")
            
            # Edge color styling based on confidence
            if disp == "LLM_VERIFIED_MERGE" or w >= THRESHOLD_AUTO_MERGE:
                edge_color = "#3b82f6"  # Confident blue
                edge_width = 3
                dashes = False
            else:
                edge_color = "#f59e0b"  # Borderline amber
                edge_width = 1.5
                dashes = True

            edges_payload.append({
                "id": f"{u}-{v}",
                "from": u,
                "to": v,
                "value": w,
                "label": f"{int(w * 100)}%",
                "title": f"Similarity: {w:.3f}<br>Name: {data.get('name_sim')}<br>Email: {data.get('email_sim')}<br>Status: {disp}",
                "color": {"color": edge_color, "highlight": "#1d4ed8"},
                "width": edge_width,
                "dashes": dashes,
                "font": {"size": 9, "color": "#475569", "background": "#ffffff"}
            })

        return {
            "nodes": nodes_payload,
            "edges": edges_payload,
            "metrics": {
                "total_nodes": self.graph.number_of_nodes(),
                "total_edges": self.graph.number_of_edges(),
                "graph_density": round(nx.density(self.graph), 4) if self.graph.number_of_nodes() > 1 else 0.0,
                "connected_components_count": nx.number_connected_components(self.graph)
            }
        }
