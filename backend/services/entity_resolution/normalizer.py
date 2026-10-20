"""
Entity Resolution Field Normalizer.
Standardizes names, emails, dates of birth, phones, and creates phonetic keys.
"""

import re
from typing import Dict, Any, Optional
import jellyfish

PREFIXES = {"dr", "prof", "mr", "ms", "mrs"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md"}

class FieldNormalizer:
    @staticmethod
    def clean_name(name: Optional[str]) -> Dict[str, Any]:
        if not name or not isinstance(name, str):
            return {"raw": "", "tokens": [], "clean_full": "", "soundex_first": "", "soundex_last": "", "metaphone_first": "", "metaphone_last": ""}
        
        # Lowercase and normalize common abbreviations (e.g. Ph.D. -> phd, Dr. -> dr)
        s = name.lower()
        s = re.sub(r"\bph\.?d\.?\b", "phd", s)
        s = re.sub(r"\bm\.?d\.?\b", "md", s)
        s = re.sub(r"\bdr\.?\b", "dr", s)
        s = re.sub(r"\bprof\.?\b", "prof", s)
        
        # Remove remaining punctuation except hyphens
        cleaned = re.sub(r"[^\w\s-]", " ", s).strip()
        raw_tokens = cleaned.split()
        tokens = [t for t in raw_tokens if t not in PREFIXES and t not in SUFFIXES]
        clean_full = " ".join(tokens)
        
        first_token = tokens[0] if tokens else ""
        last_token = tokens[-1] if tokens else ""
        
        sx_first = jellyfish.soundex(first_token) if first_token else ""
        sx_last = jellyfish.soundex(last_token) if last_token else ""
        meta_first = jellyfish.metaphone(first_token) if first_token else ""
        meta_last = jellyfish.metaphone(last_token) if last_token else ""
        
        return {
            "raw": name,
            "tokens": tokens,
            "clean_full": clean_full,
            "first": first_token,
            "last": last_token,
            "soundex_first": sx_first,
            "soundex_last": sx_last,
            "metaphone_first": meta_first,
            "metaphone_last": meta_last,
        }

    @staticmethod
    def clean_email(email: Optional[str]) -> Dict[str, str]:
        if not email or not isinstance(email, str) or "@" not in email:
            return {"raw": "", "clean": "", "user": "", "domain": ""}
        cleaned = email.strip().lower()
        parts = cleaned.split("@", 1)
        user = re.sub(r"[._-]", "", parts[0])  # Normalize separators in username
        domain = parts[1]
        return {
            "raw": email,
            "clean": cleaned,
            "user": user,
            "domain": domain
        }

    @staticmethod
    def clean_dob(dob: Optional[str]) -> str:
        if not dob or not isinstance(dob, str):
            return ""
        dob = dob.strip()
        m1 = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", dob)
        if m1:
            return f"{int(m1.group(1)):04d}-{int(m1.group(2)):02d}-{int(m1.group(3)):02d}"
        m2 = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", dob)
        if m2:
            return f"{int(m2.group(3)):04d}-{int(m2.group(1)):02d}-{int(m2.group(2)):02d}"
        return dob

    @staticmethod
    def clean_phone(phone: Optional[str]) -> str:
        if not phone or not isinstance(phone, str):
            return ""
        digits = re.sub(r"\D", "", phone)
        if len(digits) >= 10:
            return digits[-10:]
        return digits

    @classmethod
    def normalize_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a standardized feature set for comparison and blocking."""
        name_str = record.get("raw_full_name") or f"{record.get('raw_first_name', '')} {record.get('raw_last_name', '')}".strip()
        norm_name = cls.clean_name(name_str)
        norm_email = cls.clean_email(record.get("raw_email"))
        norm_dob = cls.clean_dob(record.get("raw_dob"))
        norm_phone = cls.clean_phone(record.get("raw_phone"))
        
        return {
            "raw_id": record.get("raw_id"),
            "source_system": record.get("source_system"),
            "source_record_id": record.get("source_record_id"),
            "norm_name": norm_name,
            "norm_email": norm_email,
            "norm_dob": norm_dob,
            "norm_phone": norm_phone,
            "raw_department": record.get("raw_department", ""),
            "raw_role": record.get("raw_role", "STUDENT"),
            "raw_extra": record.get("raw_extra_payload", "")
        }
