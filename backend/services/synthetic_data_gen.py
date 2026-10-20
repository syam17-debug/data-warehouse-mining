"""
Synthetic Multi-Campus University Dataset Generator.
Generates realistic heterogeneous enterprise datasets with intentional duplicates,
phonetic variations, cross-system overlaps, and temporal changes across 3 waves.
Total raw records target: 50 to 60 records.
"""

import random
from typing import Dict, List, Any

# Deterministic seed for reproducible evaluation
RANDOM_SEED = 42

DEPARTMENTS = [
    {"code": "CS", "name": "Computer Science & AI", "college": "College of Computing & Informatics", "division": "STEM"},
    {"code": "EE", "name": "Electrical & Computer Eng", "college": "College of Engineering", "division": "STEM"},
    {"code": "BUS", "name": "Business Administration", "college": "School of Management", "division": "Business"},
    {"code": "MED", "name": "Biomedical Informatics", "college": "School of Medicine & Health", "division": "Healthcare"},
    {"code": "MATH", "name": "Data Science & Statistics", "college": "College of Sciences", "division": "STEM"},
    {"code": "HUM", "name": "Digital Humanities & Comm", "college": "College of Liberal Arts", "division": "Humanities"}
]

COURSES = [
    {"code": "CS-101", "title": "Intro to Data Engineering", "credits": 4, "dept": "CS"},
    {"code": "CS-520", "title": "Advanced Data Warehousing & Mining", "credits": 3, "dept": "CS"},
    {"code": "CS-640", "title": "Graph Algorithms & Knowledge Graphs", "credits": 3, "dept": "CS"},
    {"code": "EE-201", "title": "Signal Processing & IoT", "credits": 4, "dept": "EE"},
    {"code": "BUS-310", "title": "Enterprise Information Systems", "credits": 3, "dept": "BUS"},
    {"code": "MATH-401", "title": "Applied Statistical Learning", "credits": 3, "dept": "MATH"},
    {"code": "MED-510", "title": "Clinical Informatics & Analytics", "credits": 3, "dept": "MED"}
]

TERMS = [
    {"code": "2024-FALL", "year": 2024, "season": "Fall", "start": "2024-08-25", "end": "2024-12-18"},
    {"code": "2025-SPRING", "year": 2025, "season": "Spring", "start": "2025-01-15", "end": "2025-05-10"},
    {"code": "2025-FALL", "year": 2025, "season": "Fall", "start": "2025-08-26", "end": "2025-12-19"},
    {"code": "2026-SPRING", "year": 2026, "season": "Spring", "start": "2026-01-14", "end": "2026-05-09"}
]

# Canonical entity templates with cross-source duplicate manifestations
PERSON_TEMPLATES = [
    {
        "id_base": "1001",
        "canonical_name": "Eleanor Sophia Vance",
        "dob": "1999-04-14",
        "phone": "+1-555-019-2831",
        "clean_email": "e.vance@north.univ.edu",
        "dept": "CS",
        "role": "STUDENT",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-STU-9921",
                "first": "Eleanor", "last": "Vance", "full": "Eleanor S. Vance",
                "dob": "1999-04-14", "email": "e.vance@north.univ.edu", "phone": "555-019-2831",
                "dept": "CS", "role": "STUDENT"
            },
            {
                "source": "PORTAL_ONLINE_ADM",
                "source_id": "ADM-2023-881",
                "first": "Eleanor", "last": "Vance", "full": "Eleanor Vance",
                "dob": "1999-04-14", "email": "ellie.vance@gmail.com", "phone": "(555) 019-2831",
                "dept": "CS", "role": "STUDENT"
            },
            {
                "source": "HR_CAMPUS_SOUTH",
                "source_id": "S-TA-4412",
                "first": "Ellie", "last": "Vance", "full": "Ellie Vance",
                "dob": "1999-04-14", "email": "evance@south.univ.edu", "phone": "5550192831",
                "dept": "CS", "role": "TEACHING_ASST"
            }
        ]
    },
    {
        "id_base": "1002",
        "canonical_name": "Dr. Marcus Aurelius Thorne",
        "dob": "1978-11-23",
        "phone": "+1-555-082-9912",
        "clean_email": "m.thorne@south.univ.edu",
        "dept": "CS",
        "role": "FACULTY",
        "variants": [
            {
                "source": "HR_CAMPUS_SOUTH",
                "source_id": "S-FAC-1088",
                "first": "Marcus", "last": "Thorne", "full": "Dr. Marcus A. Thorne",
                "dob": "1978-11-23", "email": "m.thorne@south.univ.edu", "phone": "555-082-9912",
                "dept": "CS", "role": "FACULTY", "rank": "Associate Professor"
            },
            {
                "source": "ALUMNI_ADVANCEMENT",
                "source_id": "ALU-2005-012",
                "first": "Marcus", "last": "Thorne", "full": "Marcus Thorne",
                "dob": "1978-11-23", "email": "m.thorne.phd@alum.univ.edu", "phone": "555-082-9912",
                "dept": "CS", "role": "ALUMNI", "donations": 12500
            }
        ]
    },
    {
        "id_base": "1003",
        "canonical_name": "Katherine Margaret Chen",
        "dob": "2001-08-30",
        "phone": "+1-555-034-7721",
        "clean_email": "kchen@north.univ.edu",
        "dept": "EE",
        "role": "STUDENT",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-STU-8832",
                "first": "Katherine", "last": "Chen", "full": "Katherine M. Chen",
                "dob": "2001-08-30", "email": "kchen@north.univ.edu", "phone": "555-034-7721",
                "dept": "EE", "role": "STUDENT"
            },
            {
                "source": "PORTAL_ONLINE_ADM",
                "source_id": "ADM-2024-904",
                "first": "Kathy", "last": "Chen", "full": "Kathy Chen",
                "dob": "2001-08-30", "email": "kathy.chen.music@yahoo.com", "phone": "555.034.7721",
                "dept": "EE", "role": "STUDENT"
            }
        ]
    },
    {
        "id_base": "1004",
        "canonical_name": "Dr. Rajesh K. Patel",
        "dob": "1983-02-17",
        "phone": "+1-555-071-4455",
        "clean_email": "rpatel@north.univ.edu",
        "dept": "MED",
        "role": "FACULTY",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-FAC-0491",
                "first": "Rajesh", "last": "Patel", "full": "Rajesh K Patel",
                "dob": "1983-02-17", "email": "rpatel@north.univ.edu", "phone": "555-071-4455",
                "dept": "MED", "role": "FACULTY"
            },
            {
                "source": "HR_CAMPUS_SOUTH",
                "source_id": "S-FAC-0312",
                "first": "Rajesh", "last": "Patel", "full": "Prof. Rajesh Patel",
                "dob": "1983-02-17", "email": "r.patel@south.univ.edu", "phone": "555-071-4455",
                "dept": "MED", "role": "FACULTY", "rank": "Full Professor"
            }
        ]
    },
    {
        "id_base": "1005",
        "canonical_name": "Tariq Abdul-Rahman",
        "dob": "2000-12-05",
        "phone": "+1-555-063-8890",
        "clean_email": "t.rahman@north.univ.edu",
        "dept": "BUS",
        "role": "STUDENT",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-STU-7721",
                "first": "Tariq", "last": "Abdul-Rahman", "full": "Tariq Abdul-Rahman",
                "dob": "2000-12-05", "email": "t.rahman@north.univ.edu", "phone": "555-063-8890",
                "dept": "BUS", "role": "STUDENT"
            },
            {
                "source": "PORTAL_ONLINE_ADM",
                "source_id": "ADM-2024-118",
                "first": "Tarek", "last": "Abdul Rahman", "full": "Tarek Abdul Rahman",
                "dob": "2000-12-05", "email": "tariq.rahman@hotmail.com", "phone": "+1 555 063 8890",
                "dept": "BUS", "role": "STUDENT"
            }
        ]
    },
    {
        "id_base": "1006",
        "canonical_name": "David Alexander Smith",
        "dob": "1998-07-19",
        "phone": "+1-555-011-3322",
        "clean_email": "d.smith@north.univ.edu",
        "dept": "MATH",
        "role": "STUDENT",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-STU-3301",
                "first": "David", "last": "Smith", "full": "David A. Smith",
                "dob": "1998-07-19", "email": "d.smith@north.univ.edu", "phone": "555-011-3322",
                "dept": "MATH", "role": "STUDENT"
            }
        ]
    },
    {
        "id_base": "1007",
        "canonical_name": "David Brandon Smith",  # INTENTIONAL HOMONYM NON-DUPLICATE
        "dob": "1995-03-11",
        "phone": "+1-555-099-7744",
        "clean_email": "d.smith.hr@south.univ.edu",
        "dept": "BUS",
        "role": "STAFF",
        "variants": [
            {
                "source": "HR_CAMPUS_SOUTH",
                "source_id": "S-STF-9941",
                "first": "David", "last": "Smith", "full": "David B. Smith",
                "dob": "1995-03-11", "email": "d.smith.hr@south.univ.edu", "phone": "555-099-7744",
                "dept": "BUS", "role": "STAFF"
            }
        ]
    },
    {
        "id_base": "1008",
        "canonical_name": "Elena Maria Rodriguez-Gomez",
        "dob": "2002-05-18",
        "phone": "+1-555-045-8123",
        "clean_email": "erodriguez@north.univ.edu",
        "dept": "CS",
        "role": "STUDENT",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-STU-4521",
                "first": "Elena", "last": "Rodriguez", "full": "Elena M. Rodriguez",
                "dob": "2002-05-18", "email": "erodriguez@north.univ.edu", "phone": "555-045-8123",
                "dept": "CS", "role": "STUDENT"
            },
            {
                "source": "PORTAL_ONLINE_ADM",
                "source_id": "ADM-2024-633",
                "first": "Elena Maria", "last": "Rodriguez Gomez", "full": "Elena Maria Rodriguez Gomez",
                "dob": "2002-05-18", "email": "elena.rodriguez2002@gmail.com", "phone": "555 045 8123",
                "dept": "CS", "role": "STUDENT"
            }
        ]
    },
    {
        "id_base": "1009",
        "canonical_name": "Dr. Sarah Elizabeth Jenkins",
        "dob": "1980-09-14",
        "phone": "+1-555-055-6677",
        "clean_email": "s.jenkins@south.univ.edu",
        "dept": "EE",
        "role": "FACULTY",
        "variants": [
            {
                "source": "HR_CAMPUS_SOUTH",
                "source_id": "S-FAC-2099",
                "first": "Sarah", "last": "Jenkins", "full": "Dr. Sarah Jenkins",
                "dob": "1980-09-14", "email": "s.jenkins@south.univ.edu", "phone": "555-055-6677",
                "dept": "EE", "role": "FACULTY", "rank": "Associate Professor"
            },
            {
                "source": "ALUMNI_ADVANCEMENT",
                "source_id": "ALU-2007-881",
                "first": "Sarah", "last": "Jenkins", "full": "Sarah E. Jenkins",
                "dob": "1980-09-14", "email": "sjenkins.phd@alum.univ.edu", "phone": "555.055.6677",
                "dept": "EE", "role": "ALUMNI", "donations": 8000
            }
        ]
    },
    {
        "id_base": "1010",
        "canonical_name": "Liam Connor O'Sullivan",
        "dob": "2000-01-22",
        "phone": "+1-555-022-7711",
        "clean_email": "losullivan@north.univ.edu",
        "dept": "HUM",
        "role": "STUDENT",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-STU-1099",
                "first": "Liam", "last": "OSullivan", "full": "Liam C. OSullivan",
                "dob": "2000-01-22", "email": "losullivan@north.univ.edu", "phone": "555-022-7711",
                "dept": "HUM", "role": "STUDENT"
            },
            {
                "source": "PORTAL_ONLINE_ADM",
                "source_id": "ADM-2023-302",
                "first": "Liam", "last": "O'Sullivan", "full": "Liam Connor O'Sullivan",
                "dob": "2000-01-22", "email": "liam.osullivan99@gmail.com", "phone": "(555) 022-7711",
                "dept": "HUM", "role": "STUDENT"
            }
        ]
    },
    # --- Additional Templates to enrich deduplication & cross-system graph matching ---
    {
        "id_base": "1011",
        "canonical_name": "Sophia Isabella Martinez",
        "dob": "2001-11-09",
        "phone": "+1-555-077-3311",
        "clean_email": "s.martinez@north.univ.edu",
        "dept": "CS",
        "role": "STUDENT",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-STU-5521",
                "first": "Sophia", "last": "Martinez", "full": "Sophia I. Martinez",
                "dob": "2001-11-09", "email": "s.martinez@north.univ.edu", "phone": "555-077-3311",
                "dept": "CS", "role": "STUDENT"
            },
            {
                "source": "PORTAL_ONLINE_ADM",
                "source_id": "ADM-2024-442",
                "first": "Sophie", "last": "Martinez", "full": "Sophie Martinez",
                "dob": "2001-11-09", "email": "sophie.martinez2001@gmail.com", "phone": "(555) 077-3311",
                "dept": "CS", "role": "STUDENT"
            },
            {
                "source": "HR_CAMPUS_SOUTH",
                "source_id": "S-TA-8812",
                "first": "Sophia", "last": "Martinez", "full": "Sophia Martinez",
                "dob": "2001-11-09", "email": "smartinez@south.univ.edu", "phone": "5550773311",
                "dept": "CS", "role": "TEACHING_ASST"
            }
        ]
    },
    {
        "id_base": "1012",
        "canonical_name": "William James MacLeod",
        "dob": "1997-06-25",
        "phone": "+1-555-088-2244",
        "clean_email": "wmacleod@north.univ.edu",
        "dept": "EE",
        "role": "STUDENT",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-STU-6612",
                "first": "William", "last": "MacLeod", "full": "William J. MacLeod",
                "dob": "1997-06-25", "email": "wmacleod@north.univ.edu", "phone": "555-088-2244",
                "dept": "EE", "role": "STUDENT"
            },
            {
                "source": "ALUMNI_ADVANCEMENT",
                "source_id": "ALU-2019-331",
                "first": "Will", "last": "Macleod", "full": "Will McLeod",
                "dob": "1997-06-25", "email": "will.mcleod@alum.univ.edu", "phone": "555.088.2244",
                "dept": "EE", "role": "ALUMNI", "donations": 4500
            }
        ]
    },
    {
        "id_base": "1013",
        "canonical_name": "Dr. Ananya Sharma",
        "dob": "1982-04-18",
        "phone": "+1-555-066-9922",
        "clean_email": "a.sharma@south.univ.edu",
        "dept": "MATH",
        "role": "FACULTY",
        "variants": [
            {
                "source": "HR_CAMPUS_SOUTH",
                "source_id": "S-FAC-3311",
                "first": "Ananya", "last": "Sharma", "full": "Dr. Ananya Sharma",
                "dob": "1982-04-18", "email": "a.sharma@south.univ.edu", "phone": "555-066-9922",
                "dept": "MATH", "role": "FACULTY", "rank": "Assistant Professor"
            },
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-FAC-0822",
                "first": "Ananya", "last": "Sharma", "full": "Prof. Ananya Sharma",
                "dob": "1982-04-18", "email": "asharma@north.univ.edu", "phone": "555-066-9922",
                "dept": "MATH", "role": "FACULTY"
            }
        ]
    },
    {
        "id_base": "1014",
        "canonical_name": "Lucas Oliver Taylor",
        "dob": "2002-10-12",
        "phone": "+1-555-033-6655",
        "clean_email": "ltaylor@north.univ.edu",
        "dept": "BUS",
        "role": "STUDENT",
        "variants": [
            {
                "source": "SIS_CAMPUS_NORTH",
                "source_id": "N-STU-4402",
                "first": "Lucas", "last": "Taylor", "full": "Lucas O. Taylor",
                "dob": "2002-10-12", "email": "ltaylor@north.univ.edu", "phone": "555-033-6655",
                "dept": "BUS", "role": "STUDENT"
            },
            {
                "source": "PORTAL_ONLINE_ADM",
                "source_id": "ADM-2024-551",
                "first": "Luke", "last": "Taylor", "full": "Luke Taylor",
                "dob": "2002-10-12", "email": "luke.taylor2002@outlook.com", "phone": "555 033 6655",
                "dept": "BUS", "role": "STUDENT"
            }
        ]
    },
    {
        "id_base": "1015",
        "canonical_name": "Mei-Ling Zhou",
        "dob": "2000-08-04",
        "phone": "+1-555-044-1188",
        "clean_email": "m.zhou@south.univ.edu",
        "dept": "CS",
        "role": "STUDENT",
        "variants": [
            {
                "source": "HR_CAMPUS_SOUTH",
                "source_id": "S-TA-5591",
                "first": "Mei-Ling", "last": "Zhou", "full": "Mei-Ling Zhou",
                "dob": "2000-08-04", "email": "m.zhou@south.univ.edu", "phone": "555-044-1188",
                "dept": "CS", "role": "TEACHING_ASST"
            },
            {
                "source": "PORTAL_ONLINE_ADM",
                "source_id": "ADM-2023-921",
                "first": "Meiling", "last": "Zhou", "full": "Meiling Zhou",
                "dob": "2000-08-04", "email": "meiling.zhou@gmail.com", "phone": "(555) 044-1188",
                "dept": "CS", "role": "STUDENT"
            }
        ]
    }
]

# Temporal SCD Evolutions (Simulates Changes in wave 2 & wave 3)
SCD_EVOLUTION_EVENTS = [
    {
        "target_name_match": "Eleanor",
        "canonical_id": "UNI-ENT-01001",
        "wave": 2,
        "effective_date": "2025-01-15",
        "reason": "ACADEMIC_MAJOR_TRANSFER_AND_PHONE_UPDATE",
        "scd1_changes": {"phone": "+1-555-019-9999"},
        "scd2_changes": {
            "department_code": "MATH",
            "academic_standing": "HONORS"
        },
        "scd3_changes": {
            "prev_department_code": "CS",
            "dept_change_date": "2025-01-15"
        }
    },
    {
        "target_name_match": "Chen",
        "canonical_id": "UNI-ENT-01003",
        "wave": 2,
        "effective_date": "2025-08-26",
        "reason": "INTERDISCIPLINARY_PROGRAM_TRANSFER",
        "scd1_changes": {"phone": "+1-555-034-0000"},
        "scd2_changes": {
            "department_code": "CS",
            "academic_standing": "HONORS"
        },
        "scd3_changes": {
            "prev_department_code": "EE",
            "dept_change_date": "2025-08-26"
        }
    },
    {
        "target_name_match": "Thorne",
        "canonical_id": "UNI-ENT-01002",
        "wave": 2,
        "effective_date": "2025-08-01",
        "reason": "FACULTY_TENURE_AND_PROMOTION",
        "scd1_changes": {"office_location": "Turing Science Tower 502"},
        "scd2_changes": {
            "academic_rank": "Full Professor",
            "salary_band": "TIER_1_SENIOR"
        }
    },
    {
        "target_name_match": "Patel",
        "canonical_id": "UNI-ENT-01004",
        "wave": 3,
        "effective_date": "2026-01-14",
        "reason": "FACULTY_CHAIR_APPOINTMENT",
        "scd1_changes": {"office_location": "Biomedical Quad Suite 100"},
        "scd2_changes": {
            "academic_rank": "Department Chair & Professor",
            "salary_band": "EXECUTIVE_CHAIR"
        }
    }
]

def generate_multi_campus_dataset() -> Dict[str, Any]:
    """Generates all source system records, reference tables, and fact records."""
    random.seed(RANDOM_SEED)
    raw_records = []
    
    # 1. Generate records from templates (now 15 templates with cross-campus duplicates)
    for person in PERSON_TEMPLATES:
        for var in person["variants"]:
            raw_records.append({
                "source_system": var["source"],
                "source_record_id": var["source_id"],
                "raw_first_name": var.get("first", ""),
                "raw_last_name": var.get("last", ""),
                "raw_full_name": var.get("full", ""),
                "raw_dob": var.get("dob", ""),
                "raw_email": var.get("email", ""),
                "raw_phone": var.get("phone", ""),
                "raw_department": var.get("dept", ""),
                "raw_role": var.get("role", "STUDENT"),
                "raw_extra_payload": str({
                    "rank": var.get("rank"),
                    "donations": var.get("donations")
                }),
                "ingestion_batch": "WAVE_1_INITIAL"
            })
            
    # 2. Add 14 diverse students with controlled duplicates to hit exactly 54-58 total records
    first_names = ["James", "Aaliyah", "Benjamin", "Chloe", "Devon", "Fatima", "Gabriel", "Hanna", "Ian", "Jasmine", "Kevin", "Lila", "Mateo", "Nora"]
    last_names = ["Becker", "Castillo", "Dubois", "El-Hashem", "Fischer", "Gupta", "Huang", "Ivanov", "Johansson", "Kowalski", "Lopez", "Miller", "Novak", "O'Connor"]
    depts = ["CS", "EE", "BUS", "MED", "MATH", "HUM"]
    
    for i in range(len(first_names)):
        fn = first_names[i]
        ln = last_names[i]
        dob = f"200{random.randint(0, 3)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
        phone = f"555-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
        dept = random.choice(depts)
        
        # Primary SIS record
        raw_records.append({
            "source_system": "SIS_CAMPUS_NORTH",
            "source_record_id": f"N-STU-3{i:03d}",
            "raw_first_name": fn,
            "raw_last_name": ln,
            "raw_full_name": f"{fn} {ln}",
            "raw_dob": dob,
            "raw_email": f"{fn.lower()}.{ln.lower()}@north.univ.edu",
            "raw_phone": phone,
            "raw_department": dept,
            "raw_role": "STUDENT",
            "raw_extra_payload": "{}",
            "ingestion_batch": "WAVE_1_INITIAL"
        })
        
        # 8 of them also have an online admissions duplicate record
        if i % 2 == 0 or i == 1 or i == 5:
            raw_records.append({
                "source_system": "PORTAL_ONLINE_ADM",
                "source_record_id": f"ADM-2024-{i:03d}",
                "raw_first_name": fn,
                "raw_last_name": ln,
                "raw_full_name": f"{fn} {ln}",
                "raw_dob": dob,
                "raw_email": f"{fn.lower()}{random.randint(10, 99)}@gmail.com",
                "raw_phone": f"({phone[4:7]}) {phone[8:12]}",
                "raw_department": dept,
                "raw_role": "STUDENT",
                "raw_extra_payload": "{}",
                "ingestion_batch": "WAVE_1_INITIAL"
            })

    return {
        "departments": DEPARTMENTS,
        "courses": COURSES,
        "terms": TERMS,
        "raw_records": raw_records,
        "scd_evolution_events": SCD_EVOLUTION_EVENTS,
        "person_templates": PERSON_TEMPLATES
    }
