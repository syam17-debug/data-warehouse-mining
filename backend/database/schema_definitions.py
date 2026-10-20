"""
Database Schema Definitions for University Data Warehouse Consolidation.
Includes Staging, Entity Resolution Graph Tables, SCD Type 1/2/3 Dimensions,
Fact Tables, and Schema Evolution Version DDLs.
"""

SCHEMA_V1_0_INIT_SQL = """
-- 1. Schema Evolution Log
CREATE TABLE IF NOT EXISTS schema_evolution_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_code TEXT NOT NULL,
    evolution_type TEXT NOT NULL,
    target_table TEXT NOT NULL,
    change_description TEXT NOT NULL,
    ddl_executed TEXT,
    is_backward_compatible INTEGER DEFAULT 1,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Staging Table: Multi-source Heterogeneous Records
CREATE TABLE IF NOT EXISTS stg_raw_records (
    raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_system TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    raw_first_name TEXT,
    raw_last_name TEXT,
    raw_full_name TEXT,
    raw_dob TEXT,
    raw_email TEXT,
    raw_phone TEXT,
    raw_department TEXT,
    raw_role TEXT,
    raw_extra_payload TEXT,
    ingestion_batch TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Entity Resolution: Resolved Golden Entities
CREATE TABLE IF NOT EXISTS er_resolved_entities (
    canonical_id TEXT PRIMARY KEY,
    resolved_name TEXT NOT NULL,
    resolved_dob TEXT,
    resolved_primary_email TEXT,
    resolved_primary_phone TEXT,
    primary_role TEXT,
    cluster_size INTEGER DEFAULT 1,
    confidence_score REAL DEFAULT 1.0,
    resolution_method TEXT DEFAULT 'GRAPH_COMMUNITY',
    groq_reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Entity Resolution: Record to Golden Mapping
CREATE TABLE IF NOT EXISTS er_record_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_id INTEGER NOT NULL REFERENCES stg_raw_records(raw_id),
    canonical_id TEXT NOT NULL REFERENCES er_resolved_entities(canonical_id),
    similarity_score REAL DEFAULT 1.0,
    match_status TEXT DEFAULT 'RESOLVED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Entity Resolution: Pairwise Similarity Edges (Graph Representation)
CREATE TABLE IF NOT EXISTS er_similarity_edges (
    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_raw_id INTEGER NOT NULL REFERENCES stg_raw_records(raw_id),
    target_raw_id INTEGER NOT NULL REFERENCES stg_raw_records(raw_id),
    overall_similarity REAL NOT NULL,
    name_sim REAL,
    email_sim REAL,
    dob_sim REAL,
    phone_sim REAL,
    disposition TEXT DEFAULT 'CONNECTED',
    evaluated_by TEXT DEFAULT 'ALGORITHM',
    evaluation_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Dimension: Department
CREATE TABLE IF NOT EXISTS dim_department (
    department_key INTEGER PRIMARY KEY AUTOINCREMENT,
    department_code TEXT UNIQUE NOT NULL,
    department_name TEXT NOT NULL,
    school_college TEXT NOT NULL,
    division TEXT
);

-- 7. Dimension: Course
CREATE TABLE IF NOT EXISTS dim_course (
    course_key INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code TEXT UNIQUE NOT NULL,
    course_title TEXT NOT NULL,
    credit_hours INTEGER NOT NULL,
    department_code TEXT REFERENCES dim_department(department_code)
);

-- 8. Dimension: Academic Term / Semester
CREATE TABLE IF NOT EXISTS dim_term_semester (
    term_key INTEGER PRIMARY KEY AUTOINCREMENT,
    term_code TEXT UNIQUE NOT NULL,
    academic_year INTEGER NOT NULL,
    season TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL
);

-- 9. Dimension: Student with SCD Type 1, Type 2, and Type 3 attributes (v1.0 Baseline)
CREATE TABLE IF NOT EXISTS dim_student_scd2 (
    student_dim_key INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_student_id TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    full_name TEXT NOT NULL,
    dob TEXT,
    primary_email TEXT,
    phone TEXT, -- SCD1 (in-place overwrite)
    department_code TEXT REFERENCES dim_department(department_code), -- SCD2
    academic_standing TEXT DEFAULT 'GOOD_STANDING', -- SCD2
    degree_program TEXT,
    campus_origin TEXT,
    
    -- SCD Type 3 Tracking
    prev_department_code TEXT,
    dept_change_date DATE,
    
    -- SCD Type 2 Metadata Tracking
    valid_from DATE NOT NULL,
    valid_to DATE NOT NULL DEFAULT '9999-12-31',
    is_current INTEGER NOT NULL DEFAULT 1,
    version_num INTEGER NOT NULL DEFAULT 1,
    effective_reason TEXT DEFAULT 'INITIAL_LOAD'
);

-- 10. Dimension: Faculty with SCD Type 1 and Type 2
CREATE TABLE IF NOT EXISTS dim_faculty_scd2 (
    faculty_dim_key INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_faculty_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    primary_email TEXT NOT NULL,
    phone TEXT, -- SCD1
    office_location TEXT, -- SCD1
    academic_rank TEXT NOT NULL, -- SCD2
    department_code TEXT REFERENCES dim_department(department_code), -- SCD2
    salary_band TEXT, -- SCD2
    
    -- SCD Type 2 Metadata Tracking
    valid_from DATE NOT NULL,
    valid_to DATE NOT NULL DEFAULT '9999-12-31',
    is_current INTEGER NOT NULL DEFAULT 1,
    version_num INTEGER NOT NULL DEFAULT 1,
    effective_reason TEXT DEFAULT 'INITIAL_LOAD'
);

-- 11. Fact: Student Enrollment & Tuition
CREATE TABLE IF NOT EXISTS fact_student_enrollment (
    enrollment_fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_dim_key INTEGER NOT NULL REFERENCES dim_student_scd2(student_dim_key),
    course_key INTEGER NOT NULL REFERENCES dim_course(course_key),
    term_key INTEGER NOT NULL REFERENCES dim_term_semester(term_key),
    department_key INTEGER NOT NULL REFERENCES dim_department(department_key),
    credits_enrolled INTEGER NOT NULL,
    tuition_amount REAL NOT NULL,
    grade_points REAL,
    letter_grade TEXT,
    completion_status TEXT DEFAULT 'COMPLETED',
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. Fact: Research Funding & Grants
CREATE TABLE IF NOT EXISTS fact_research_funding (
    grant_fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_dim_key INTEGER NOT NULL REFERENCES dim_faculty_scd2(faculty_dim_key),
    department_key INTEGER NOT NULL REFERENCES dim_department(department_key),
    term_key INTEGER NOT NULL REFERENCES dim_term_semester(term_key),
    grant_title TEXT NOT NULL,
    funding_agency TEXT NOT NULL,
    awarded_amount REAL NOT NULL,
    expenditure_amount REAL NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for dimensional high-performance OLAP lookups
CREATE INDEX IF NOT EXISTS idx_student_natural ON dim_student_scd2(canonical_student_id);
CREATE INDEX IF NOT EXISTS idx_student_current ON dim_student_scd2(is_current);
CREATE INDEX IF NOT EXISTS idx_student_dates ON dim_student_scd2(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_faculty_natural ON dim_faculty_scd2(canonical_faculty_id);
CREATE INDEX IF NOT EXISTS idx_fact_enroll_sk ON fact_student_enrollment(student_dim_key);
CREATE INDEX IF NOT EXISTS idx_fact_grant_sk ON fact_research_funding(faculty_dim_key);
"""

# Schema Evolution V2.0 DDL scripts (Adds Honors Track, Residency Status, Work Modality)
SCHEMA_V2_0_EVOLUTION_DDL = [
    {
        "table": "dim_student_scd2",
        "type": "ADD_COLUMN",
        "description": "Add honors_track flag to support University Honors College integration",
        "sql": "ALTER TABLE dim_student_scd2 ADD COLUMN honors_track INTEGER DEFAULT 0;"
    },
    {
        "table": "dim_student_scd2",
        "type": "ADD_COLUMN",
        "description": "Add residency_status (In-State, Out-of-State, International) for tuition analytics",
        "sql": "ALTER TABLE dim_student_scd2 ADD COLUMN residency_status TEXT DEFAULT 'IN_STATE';"
    },
    {
        "table": "dim_faculty_scd2",
        "type": "ADD_COLUMN",
        "description": "Add work_modality (On-Campus, Hybrid, Remote) for post-consolidation workforce tracking",
        "sql": "ALTER TABLE dim_faculty_scd2 ADD COLUMN work_modality TEXT DEFAULT 'ON_CAMPUS';"
    }
]

# Schema Evolution V3.0 DDL scripts (Adds Advisor Linkage, Alumni Donor Tier, Hybrid Credit Tracking)
SCHEMA_V3_0_EVOLUTION_DDL = [
    {
        "table": "dim_student_scd2",
        "type": "ADD_COLUMN",
        "description": "Add assigned_advisor_faculty_id linking student directly to resolved faculty entity",
        "sql": "ALTER TABLE dim_student_scd2 ADD COLUMN assigned_advisor_faculty_id TEXT;"
    },
    {
        "table": "er_resolved_entities",
        "type": "ADD_COLUMN",
        "description": "Add alumni_donor_tier to classify lifetime giving upon multi-system alumni consolidation",
        "sql": "ALTER TABLE er_resolved_entities ADD COLUMN alumni_donor_tier TEXT DEFAULT 'NONE';"
    },
    {
        "table": "fact_student_enrollment",
        "type": "ADD_COLUMN",
        "description": "Add course_delivery_mode (Synchronous Online, Asynchronous, In-Person)",
        "sql": "ALTER TABLE fact_student_enrollment ADD COLUMN delivery_mode TEXT DEFAULT 'IN_PERSON';"
    }
]
