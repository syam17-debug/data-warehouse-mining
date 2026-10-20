"""
Groq LLM-Powered Semantic Entity Disambiguation Service.
Leverages high-speed Groq inference for borderline entity matching and rationalization.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from backend.config import GROQ_API_KEY, GROQ_DEFAULT_MODEL, GROQ_BASE_URL

logger = logging.getLogger("dwh.groq")

class GroqEntityDisambiguator:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or GROQ_API_KEY
        self.model = model or GROQ_DEFAULT_MODEL

    def evaluate_entity_pair(self, rec1: Dict[str, Any], rec2: Dict[str, Any], similarity_score: float) -> Dict[str, Any]:
        """
        Sends pair comparison to Groq LLM for semantic verification and resolution.
        """
        if not self.api_key:
            return self._heuristic_fallback(rec1, rec2, similarity_score, "No Groq API Key provided")

        prompt = f"""You are an expert Data Mining and Master Data Management (MDM) Entity Resolution system.
Analyze the following two student/employee records from different legacy university databases to determine if they represent the EXACT SAME INDIVIDUAL or TWO DIFFERENT INDIVIDUALS.

RECORD 1 (System: {rec1.get('source_system')}):
- Name: {rec1.get('raw_full_name') or rec1.get('label')}
- Date of Birth: {rec1.get('dob')}
- Email: {rec1.get('email')}
- Phone: {rec1.get('phone')}
- Role: {rec1.get('role')}
- Department: {rec1.get('department')}

RECORD 2 (System: {rec2.get('source_system')}):
- Name: {rec2.get('raw_full_name') or rec2.get('label')}
- Date of Birth: {rec2.get('dob')}
- Email: {rec2.get('email')}
- Phone: {rec2.get('phone')}
- Role: {rec2.get('role')}
- Department: {rec2.get('department')}

Algorithmic Composite Similarity Score: {similarity_score:.3f}

Carefully consider:
1. Common nicknames (e.g. Ellie/Eleanor, Kathy/Katherine, Bob/Robert).
2. Institutional email vs personal email (@north.univ.edu vs @gmail.com).
3. Typos, punctuation, name order variations.
4. Identical DOB or phone corroboration vs contradictory DOBs.

Respond ONLY with valid JSON in this exact structure:
{{
    "is_same_person": true,
    "confidence": 0.95,
    "recommended_action": "MERGE",
    "canonical_preferred_name": "Full Formal Name",
    "reasoning": "Clear concise explanation of why they match or differ"
}}
"""

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a precise JSON-only Data Warehouse Entity Resolution auditor."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 300
        }

        try:
            req = urllib.request.Request(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DWH-Graph-Resolution"
                },
                data=json.dumps(body).encode("utf-8")
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                content = res_data["choices"][0]["message"]["content"].strip()
                
                # Parse JSON from content (strip markdown backticks if any)
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()
                
                decision = json.loads(content)
                decision["provider"] = "GROQ_LLM"
                decision["model"] = self.model
                return decision

        except Exception as e:
            logger.warning(f"Groq API call encountered: {e}. Falling back to rule-based resolution.")
            return self._heuristic_fallback(rec1, rec2, similarity_score, f"LLM error: {str(e)}")

    def _heuristic_fallback(self, rec1: Dict[str, Any], rec2: Dict[str, Any], similarity_score: float, reason: str) -> Dict[str, Any]:
        """Deterministic rule fallback when LLM is unavailable."""
        is_same = similarity_score >= 0.75
        preferred_name = rec1.get("raw_full_name") or rec1.get("label") or rec2.get("raw_full_name") or rec2.get("label")
        return {
            "is_same_person": is_same,
            "confidence": similarity_score,
            "recommended_action": "MERGE" if is_same else "KEEP_SEPARATE",
            "canonical_preferred_name": preferred_name,
            "reasoning": f"Algorithmic decision based on weighted score ({similarity_score:.3f}). Reason: {reason}",
            "provider": "RULE_FALLBACK",
            "model": "deterministic"
        }

groq_disambiguator = GroqEntityDisambiguator()
