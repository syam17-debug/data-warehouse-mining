"""
Multi-Pass Blocking Engine for Scalable Entity Resolution.
Reduces O(N^2) search space to candidate pairs sharing high-probability blocking keys.
"""

from typing import List, Dict, Tuple, Set, Any
from collections import defaultdict

class MultiPassBlocking:
    def __init__(self):
        self.blocks = defaultdict(set)

    def generate_candidate_pairs(self, normalized_records: List[Dict[str, Any]]) -> Set[Tuple[int, int]]:
        """
        Generates unique candidate pairs (id1, id2) where id1 < id2 using multi-pass blocking keys.
        """
        candidate_pairs = set()
        
        # Block Pass 1: Phonetic Soundex Last Name + First Name Initial
        # Block Pass 2: Exact DOB (YYYY-MM-DD)
        # Block Pass 3: Normalized Phone (if at least 7 digits)
        # Block Pass 4: Normalized Email Username
        # Block Pass 5: Metaphone First + Last Initial
        
        pass1 = defaultdict(list)
        pass2 = defaultdict(list)
        pass3 = defaultdict(list)
        pass4 = defaultdict(list)
        pass5 = defaultdict(list)

        for rec in normalized_records:
            rid = rec["raw_id"]
            name = rec["norm_name"]
            dob = rec["norm_dob"]
            phone = rec["norm_phone"]
            email = rec["norm_email"]
            
            # Key 1
            if name["soundex_last"] and name["first"]:
                k1 = f"SX_{name['soundex_last']}_{name['first'][0]}"
                pass1[k1].append(rid)
                
            # Key 2: DOB
            if dob and len(dob) >= 7:
                k2 = f"DOB_{dob[:7]}"  # Year-Month
                pass2[k2].append(rid)
                
            # Key 3: Phone
            if phone and len(phone) >= 7:
                k3 = f"PH_{phone[-7:]}"
                pass3[k3].append(rid)
                
            # Key 4: Email Username prefix
            if email["user"] and len(email["user"]) >= 4:
                k4 = f"EM_{email['user'][:5]}"
                pass4[k4].append(rid)
                
            # Key 5: Metaphone First Name
            if name["metaphone_first"] and name["last"]:
                k5 = f"MF_{name['metaphone_first']}_{name['last'][0]}"
                pass5[k5].append(rid)

        # Collect candidate pairs from all passes
        all_passes = [pass1, pass2, pass3, pass4, pass5]
        for p in all_passes:
            for key, rids in p.items():
                if len(rids) > 1 and len(rids) < 200:  # Avoid pathological blocks (e.g. empty/generic)
                    for i in range(len(rids)):
                        for j in range(i + 1, len(rids)):
                            u, v = rids[i], rids[j]
                            if u != v:
                                candidate_pairs.add((min(u, v), max(u, v)))
                                
        return candidate_pairs
