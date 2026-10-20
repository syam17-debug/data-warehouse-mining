"""
Pairwise Multi-Attribute Similarity Calculator for Entity Resolution.
Computes hybrid distance metrics: Jaro-Winkler, Levenshtein, Jaccard Token, and Domain Heuristics.
"""

from typing import Dict, Any
import jellyfish
from backend.config import SIMILARITY_WEIGHTS

NICKNAME_MAP = {
    "ellie": "eleanor", "eleanor": "ellie",
    "kathy": "katherine", "katherine": "kathy",
    "alex": "alexander", "alexander": "alex",
    "bob": "robert", "robert": "bob",
    "bill": "william", "william": "bill",
    "will": "william",
    "sophie": "sophia", "sophia": "sophie",
    "luke": "lucas", "lucas": "luke",
    "tarek": "tariq", "tariq": "tarek",
    "mohamed": "mohammed", "mohammed": "mohamed"
}

class SimilarityEngine:
    @staticmethod
    def compute_name_similarity(n1: Dict[str, Any], n2: Dict[str, Any]) -> float:
        s1 = n1.get("clean_full", "")
        s2 = n2.get("clean_full", "")
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0
        
        # Primary Jaro-Winkler
        jw = jellyfish.jaro_winkler_similarity(s1, s2)
        
        # Check nickname dictionary on first name
        f1 = n1.get("first", "")
        f2 = n2.get("first", "")
        is_nickname = False
        if f1 and f2 and (NICKNAME_MAP.get(f1) == f2 or NICKNAME_MAP.get(f2) == f1):
            is_nickname = True
            jw = max(jw, 0.88)
            
        # Token overlap (Jaccard)
        t1 = set(n1.get("tokens", []))
        t2 = set(n2.get("tokens", []))
        jaccard = len(t1 & t2) / max(len(t1 | t2), 1) if t1 and t2 else 0.0
        
        # Phonetic bonus if first or last soundex matches
        phonetic_bonus = 0.0
        if n1.get("soundex_last") and n1.get("soundex_last") == n2.get("soundex_last"):
            phonetic_bonus += 0.05
        if is_nickname or (n1.get("soundex_first") and n1.get("soundex_first") == n2.get("soundex_first")):
            phonetic_bonus += 0.05
            
        base_score = 0.7 * jw + 0.3 * jaccard + phonetic_bonus
        return min(max(base_score, 0.0), 1.0)

    @staticmethod
    def compute_dob_similarity(d1: str, d2: str) -> float:
        if not d1 or not d2:
            return 0.5  # Neutral when missing
        if d1 == d2:
            return 1.0
            
        # Check if year and month match (possible day typo)
        if len(d1) >= 7 and len(d2) >= 7 and d1[:7] == d2[:7]:
            return 0.85
            
        # Distance penalty for year differences
        try:
            y1 = int(d1[:4])
            y2 = int(d2[:4])
            diff = abs(y1 - y2)
            if diff == 0:
                return 0.70
            elif diff == 1:
                return 0.40
            else:
                return 0.0  # Significant age discrepancy
        except Exception:
            return 0.0

    @staticmethod
    def compute_email_similarity(e1: Dict[str, str], e2: Dict[str, str]) -> float:
        c1 = e1.get("clean", "")
        c2 = e2.get("clean", "")
        if not c1 or not c2:
            return 0.5
        if c1 == c2:
            return 1.0
            
        u1 = e1.get("user", "")
        u2 = e2.get("user", "")
        if u1 and u2:
            if u1 == u2:
                # Same user prefix across different domains (e.g. univ vs personal)
                return 0.88
            # Levenshtein ratio on usernames
            dist = jellyfish.levenshtein_distance(u1, u2)
            max_len = max(len(u1), len(u2))
            sim = 1.0 - (dist / max(max_len, 1))
            return max(sim, 0.0)
        return 0.0

    @staticmethod
    def compute_phone_similarity(p1: str, p2: str) -> float:
        if not p1 or not p2:
            return 0.5
        if p1 == p2:
            return 1.0
        # If last 7 digits match (local number match)
        if len(p1) >= 7 and len(p2) >= 7 and p1[-7:] == p2[-7:]:
            return 0.90
        return 0.0

    @classmethod
    def compare_records(cls, r1: Dict[str, Any], r2: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates attribute and composite similarity between two normalized records."""
        name_sim = cls.compute_name_similarity(r1["norm_name"], r2["norm_name"])
        dob_sim = cls.compute_dob_similarity(r1["norm_dob"], r2["norm_dob"])
        email_sim = cls.compute_email_similarity(r1["norm_email"], r2["norm_email"])
        phone_sim = cls.compute_phone_similarity(r1["norm_phone"], r2["norm_phone"])
        
        # Weighted composite score
        w = SIMILARITY_WEIGHTS
        composite = (
            w["name"] * name_sim +
            w["dob"] * dob_sim +
            w["email"] * email_sim +
            w["phone"] * phone_sim
        )
        
        # Homonym Safeguard: If names are similar but DOBs are known and differ by >= 3 years
        if r1["norm_dob"] and r2["norm_dob"] and dob_sim == 0.0:
            composite = composite * 0.4  # Drastic penalty to avoid merging different people
            
        # Strong Multi-Attribute Corroboration Boost (Exact DOB + strong name or exact phone)
        if (name_sim >= 0.80 and dob_sim >= 0.95) or (phone_sim >= 0.95 and dob_sim >= 0.95):
            composite = min(composite + 0.12, 1.0)
            
        return {
            "source_raw_id": r1["raw_id"],
            "target_raw_id": r2["raw_id"],
            "overall_similarity": round(composite, 4),
            "name_sim": round(name_sim, 4),
            "dob_sim": round(dob_sim, 4),
            "email_sim": round(email_sim, 4),
            "phone_sim": round(phone_sim, 4)
        }
