import sqlite3
import re
from datetime import datetime

from strands_agent import generate_ai_reasoning


DATABASE_NAME = "civicflow.db"


# ============================================================
# DATABASE SETUP
# ============================================================

def setup_database():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Main cases table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT UNIQUE,
            description TEXT,
            category TEXT,
            location TEXT,
            priority TEXT,
            status TEXT DEFAULT 'OPEN',
            missing_information TEXT,
            created_at TEXT,
            department TEXT,
            recommended_action TEXT,
            response_time TEXT,
            evidence_score INTEGER DEFAULT 0,
            confidence TEXT DEFAULT 'N/A',
            evidence_reasons TEXT,
            citizen_id TEXT,
            ai_reasoning TEXT,
            agent_used TEXT DEFAULT 'RULE_ENGINE',
            duplicate_case_id TEXT,
            duplicate_similarity INTEGER DEFAULT 0,
            duplicate_explanation TEXT
        )
    """)

    # Check existing columns
    cursor.execute("PRAGMA table_info(cases)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    # Add missing columns to older databases
    columns_to_add = {
        "description": "TEXT",
        "category": "TEXT",
        "location": "TEXT",
        "priority": "TEXT",
        "status": "TEXT DEFAULT 'OPEN'",
        "missing_information": "TEXT",
        "created_at": "TEXT",
        "department": "TEXT",
        "recommended_action": "TEXT",
        "response_time": "TEXT",
        "evidence_score": "INTEGER DEFAULT 0",
        "confidence": "TEXT DEFAULT 'N/A'",
        "evidence_reasons": "TEXT",
        "citizen_id": "TEXT",
        "ai_reasoning": "TEXT",
        "agent_used": "TEXT DEFAULT 'RULE_ENGINE'",
        "duplicate_case_id": "TEXT",
        "duplicate_similarity": "INTEGER DEFAULT 0",
        "duplicate_explanation": "TEXT"
    }

    for column_name, column_type in columns_to_add.items():
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE cases ADD COLUMN {column_name} {column_type}"
            )

    # Compatibility with older version
    if "complaint" not in existing_columns:
        cursor.execute(
            "ALTER TABLE cases ADD COLUMN complaint TEXT"
        )

    # Indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cases_category
        ON cases(category)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cases_priority
        ON cases(priority)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cases_status
        ON cases(status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cases_citizen
        ON cases(citizen_id)
    """)

    # Status history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS case_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT,
            status TEXT,
            note TEXT,
            updated_at TEXT
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_updates_case
        ON case_updates(case_id)
    """)

    # Keep description and complaint synchronized
    cursor.execute("""
        UPDATE cases
        SET complaint = description
        WHERE
            (complaint IS NULL OR complaint = '')
            AND description IS NOT NULL
    """)

    cursor.execute("""
        UPDATE cases
        SET description = complaint
        WHERE
            (description IS NULL OR description = '')
            AND complaint IS NOT NULL
    """)

    conn.commit()

    # --------------------------------------------------------
    # Add AI reasoning to older cases when missing
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            category,
            location,
            priority,
            department,
            evidence_score,
            missing_information,
            ai_reasoning
        FROM cases
    """)

    old_cases = cursor.fetchall()

    for row in old_cases:

        (
            row_id,
            category,
            location,
            priority,
            department,
            evidence_score,
            missing_information,
            ai_reasoning
        ) = row

        if ai_reasoning:
            continue

        reasoning, strands_used = generate_ai_reasoning(
            category or "OTHER",
            location or "Not specified",
            priority or "LOW",
            department or "General Civic Services",
            evidence_score or 0,
            missing_information or "No major information missing"
        )

        cursor.execute("""
            UPDATE cases
            SET
                ai_reasoning = ?,
                agent_used = ?
            WHERE id = ?
        """, (
            reasoning,
            "STRANDS" if strands_used else "RULE_ENGINE",
            row_id
        ))

    # --------------------------------------------------------
    # Create initial status history for old cases
    # --------------------------------------------------------

    cursor.execute("""
        SELECT case_id, status, created_at
        FROM cases
    """)

    existing_cases = cursor.fetchall()

    for case_id, status, created_at in existing_cases:

        if not case_id:
            continue

        cursor.execute("""
            SELECT COUNT(*)
            FROM case_updates
            WHERE case_id = ?
        """, (case_id,))

        count = cursor.fetchone()[0]

        if count == 0:

            cursor.execute("""
                INSERT INTO case_updates (
                    case_id,
                    status,
                    note,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                case_id,
                status or "OPEN",
                "Initial case status",
                created_at or datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ))

    conn.commit()
    conn.close()


# ============================================================
# ISSUE CLASSIFICATION
# ============================================================

def classify_issue(complaint):

    if not complaint:
        return "OTHER"

    text = complaint.lower().strip()

    # WATER MUST COME BEFORE GARBAGE
    # This prevents words such as "wasted" from causing
    # a water complaint to become GARBAGE.

    if any(word in text for word in [
        "water",
        "water supply",
        "water problem",
        "water shortage",
        "water leakage",
        "water leak",
        "pipeline",
        "pipe",
        "leakage",
        "leak",
        "drainage",
        "drain"
    ]):
        return "WATER"

    # Streetlight
    if any(word in text for word in [
        "streetlight",
        "street light",
        "street lamp",
        "lamp post",
        "light pole",
        "road light",
        "road lighting"
    ]):
        return "STREETLIGHT"

    # Garbage
    # "waste" intentionally removed because "water is being wasted"
    # should not become GARBAGE.
    if any(word in text for word in [
        "garbage",
        "trash",
        "rubbish",
        "litter",
        "dump",
        "dumped",
        "waste collection",
        "waste disposal"
    ]):
        return "GARBAGE"

    # Road
    if any(word in text for word in [
        "pothole",
        "road",
        "street",
        "crack",
        "broken road",
        "damaged road",
        "road damage",
        "road is damaged",
        "road condition"
    ]):
        return "ROAD"

    # Public infrastructure
    if any(word in text for word in [
        "park",
        "bridge",
        "building",
        "footpath",
        "sidewalk",
        "public toilet",
        "bench",
        "gate",
        "infrastructure"
    ]):
        return "INFRASTRUCTURE"

    return "OTHER"


# ============================================================
# LOCATION EXTRACTION
# ============================================================

def extract_location(complaint):

    if not complaint:
        return "Not specified"

    patterns = [
        r"\bnear\s+(?:the\s+)?([^,.!?]+)",
        r"\bat\s+(?:the\s+)?([^,.!?]+)",
        r"\boutside\s+(?:the\s+)?([^,.!?]+)",
        r"\binside\s+(?:the\s+)?([^,.!?]+)"
    ]

    # Words that are not actual locations
    invalid_locations = {
        "night",
        "day",
        "morning",
        "evening",
        "afternoon",
        "today",
        "yesterday",
        "tomorrow",
        "home",
        "there",
        "here"
    }

    for pattern in patterns:

        match = re.search(
            pattern,
            complaint,
            re.IGNORECASE
        )

        if not match:
            continue

        location = match.group(1).strip()

        # Clean common trailing words
        location = re.sub(
            r"\s+(and|but|because|where|which|that)\s*$",
            "",
            location,
            flags=re.IGNORECASE
        )

        location = location.strip(" .")

        if not location:
            continue

        if location.lower() in invalid_locations:
            continue

        # Prevent phrases like "at night" from becoming a location
        if location.lower().startswith("night"):
            continue

        if location.lower().startswith("day"):
            continue

        return location

    return "Not specified"


# ============================================================
# PRIORITY CALCULATION
# ============================================================

def calculate_priority(complaint, category):

    if not complaint:
        return "LOW"

    text = complaint.lower()

    urgent_words = [
        "accident",
        "danger",
        "dangerous",
        "emergency",
        "injured",
        "fire",
        "life threatening",
        "life-threatening",
        "unsafe",
        "risk",
        "immediate danger",
        "serious safety"
    ]

    high_words = [
        "large",
        "major",
        "three days",
        "many people",
        "night",
        "vehicles",
        "traffic",
        "blocked",
        "serious",
        "severe",
        "huge",
        "many students",
        "students affected",
        "public affected"
    ]

    if any(word in text for word in urgent_words):
        return "URGENT"

    if any(word in text for word in high_words):
        return "HIGH"

    if category in ["ROAD", "WATER"]:
        return "MEDIUM"

    return "LOW"


# ============================================================
# DEPARTMENT ROUTING
# ============================================================

def get_department_and_action(category, priority):

    routing = {

        "STREETLIGHT": {
            "department": "Electrical Maintenance Department",
            "action": (
                "Inspect and repair the faulty streetlight."
            ),
            "response_time": "24-48 hours"
        },

        "GARBAGE": {
            "department": "Sanitation Department",
            "action": (
                "Inspect the location and arrange waste collection."
            ),
            "response_time": "Within 7 days"
        },

        "ROAD": {
            "department": "Road Maintenance Department",
            "action": (
                "Inspect the road and repair the damaged area."
            ),
            "response_time": "Within 48 hours"
        },

        "WATER": {
            "department": "Water Supply Department",
            "action": (
                "Inspect the water system and stop the source "
                "of the problem."
            ),
            "response_time": "Within 48 hours"
        },

        "INFRASTRUCTURE": {
            "department": "Public Works Department",
            "action": (
                "Inspect the damaged public infrastructure "
                "and arrange repairs."
            ),
            "response_time": "48-72 hours"
        },

        "OTHER": {
            "department": "General Civic Services",
            "action": (
                "Review the complaint and forward it to "
                "the appropriate department."
            ),
            "response_time": "48-72 hours"
        }
    }

    result = routing.get(
        category,
        routing["OTHER"]
    ).copy()

    if priority == "URGENT":

        result["action"] = (
            "Immediate inspection required. "
            + result["action"]
        )

        result["response_time"] = (
            "Immediate action - within 24 hours"
        )

    elif priority == "HIGH":

        result["response_time"] = (
            "Priority response - within 48 hours"
        )

    return (
        result["department"],
        result["action"],
        result["response_time"]
    )


# ============================================================
# MISSING INFORMATION
# ============================================================

def get_missing_information(
    complaint,
    location,
    category
):

    missing = []

    text = complaint.lower()

    # Location
    if not location or location == "Not specified":
        missing.append("Specific location")

    # Description length
    if len(complaint.split()) < 8:
        missing.append(
            "More details about the problem"
        )

    # Public impact
    impact_words = [
        "people",
        "students",
        "children",
        "vehicles",
        "traffic",
        "public",
        "affected",
        "residents",
        "commuters"
    ]

    if not any(
        word in text
        for word in impact_words
    ):
        missing.append("Public impact")

    # Issue type
    if category == "OTHER":
        missing.append("Clear issue type")

    if not missing:
        return "No major information missing"

    return ", ".join(missing)


# ============================================================
# EVIDENCE SCORE
# ============================================================

def calculate_evidence_score(
    complaint,
    category,
    location,
    priority
):

    text = complaint.lower()

    score = 0
    reasons = []

    # --------------------------------------------------------
    # Category
    # --------------------------------------------------------

    if category != "OTHER":

        score += 30

        reasons.append(
            "Issue category identified"
        )

    else:

        reasons.append(
            "Issue category is unclear"
        )

    # --------------------------------------------------------
    # Location
    # --------------------------------------------------------

    if (
        location
        and location != "Not specified"
    ):

        score += 25

        reasons.append(
            "Location provided"
        )

    else:

        reasons.append(
            "Location not provided"
        )

    # --------------------------------------------------------
    # Description detail
    # --------------------------------------------------------

    word_count = len(
        complaint.split()
    )

    if word_count >= 20:

        score += 20

        reasons.append(
            "Problem description has sufficient detail"
        )

    elif word_count >= 10:

        score += 15

        reasons.append(
            "Problem description has moderate detail"
        )

    elif word_count >= 5:

        score += 10

        reasons.append(
            "Basic problem description"
        )

    else:

        reasons.append(
            "Description is too short"
        )

    # --------------------------------------------------------
    # Impact / safety
    # --------------------------------------------------------

    impact_words = [
        "people",
        "students",
        "children",
        "vehicles",
        "traffic",
        "public",
        "danger",
        "dangerous",
        "unsafe",
        "accident",
        "risk",
        "blocked",
        "affected",
        "residents",
        "commuters"
    ]

    if any(
        word in text
        for word in impact_words
    ):

        score += 15

        reasons.append(
            "Impact or safety concern mentioned"
        )

    else:

        reasons.append(
            "Public impact not clearly specified"
        )

    # --------------------------------------------------------
    # Severity
    # --------------------------------------------------------

    severity_words = [
        "large",
        "major",
        "serious",
        "severe",
        "huge",
        "emergency",
        "urgent",
        "dangerous",
        "unsafe"
    ]

    if (
        priority == "URGENT"
        or any(
            word in text
            for word in severity_words
        )
    ):

        score += 10

        reasons.append(
            "Severity information provided"
        )

    else:

        reasons.append(
            "Severity information limited"
        )

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    if score >= 70:

        confidence = "HIGH"

    elif score >= 40:

        confidence = "MEDIUM"

    else:

        confidence = "LOW"

    return (
        score,
        confidence,
        reasons
    )


# ============================================================
# CASE ID
# ============================================================

def create_case_id():

    timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S%f"
    )

    return f"CF-{timestamp}"


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def find_possible_duplicate(
    complaint,
    category,
    location
):

    conn = sqlite3.connect(
        DATABASE_NAME
    )

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            case_id,
            description,
            category,
            location,
            priority,
            status,
            created_at
        FROM cases
        ORDER BY id DESC
        LIMIT 100
    """)

    cases = cursor.fetchall()

    conn.close()

    # --------------------------------------------------------
    # Words from new complaint
    # --------------------------------------------------------

    new_words = set(
        word.lower()
        for word in re.findall(
            r"\b[a-zA-Z]{3,}\b",
            complaint
        )
    )

    best_match = None
    best_score = 0

    # --------------------------------------------------------
    # Compare with previous cases
    # --------------------------------------------------------

    for case in cases:

        (
            case_id,
            old_description,
            old_category,
            old_location,
            old_priority,
            old_status,
            old_created_at
        ) = case

        if not old_description:
            continue

        old_words = set(
            word.lower()
            for word in re.findall(
                r"\b[a-zA-Z]{3,}\b",
                old_description
            )
        )

        if not new_words or not old_words:
            continue

        intersection = len(
            new_words.intersection(
                old_words
            )
        )

        union = len(
            new_words.union(
                old_words
            )
        )

        if union == 0:

            similarity = 0

        else:

            similarity = (
                intersection / union
            ) * 100

        # Same category bonus
        if (
            category
            and old_category
            and category == old_category
        ):

            similarity += 20

        # Same location bonus
        if (
            location
            and old_location
            and location != "Not specified"
            and old_location != "Not specified"
        ):

            new_location = location.lower()
            old_location_text = old_location.lower()

            if (
                new_location in old_location_text
                or old_location_text in new_location
            ):

                similarity += 20

        # Maximum 100
        if similarity > 100:
            similarity = 100

        if similarity > best_score:

            best_score = similarity

            best_match = {
                "case_id": case_id,
                "complaint": old_description,
                "category": old_category,
                "location": old_location,
                "priority": old_priority,
                "status": old_status,
                "created_at": old_created_at,
                "similarity": round(similarity)
            }

    # --------------------------------------------------------
    # Duplicate threshold
    # --------------------------------------------------------

    if (
        best_match
        and best_score >= 60
    ):

        same_category = (
            category
            and best_match["category"]
            and category == best_match["category"]
        )

        same_location = False

        if (
            location
            and best_match["location"]
            and location != "Not specified"
            and best_match["location"] != "Not specified"
        ):

            new_location = location.lower()
            old_location = best_match[
                "location"
            ].lower()

            same_location = (
                new_location in old_location
                or old_location in new_location
            )

        explanation_parts = []

        if same_category:
            explanation_parts.append(
                "same issue category"
            )

        if same_location:
            explanation_parts.append(
                "same or nearby location"
            )

        explanation_parts.append(
            "similar complaint description"
        )

        explanation = (
            "This complaint appears similar to an existing "
            "case because it contains "
            + ", ".join(explanation_parts)
            + "."
        )

        best_match["explanation"] = explanation

        return best_match

    return None


# ============================================================
# COMPLETE PROBLEM ANALYSIS
# ============================================================

def analyze_problem(complaint):

    # --------------------------------------------------------
    # 1. Classification
    # --------------------------------------------------------

    category = classify_issue(
        complaint
    )

    # --------------------------------------------------------
    # 2. Location
    # --------------------------------------------------------

    location = extract_location(
        complaint
    )

    # --------------------------------------------------------
    # 3. Priority
    # --------------------------------------------------------

    priority = calculate_priority(
        complaint,
        category
    )

    # --------------------------------------------------------
    # 4. Department routing
    # --------------------------------------------------------

    (
        department,
        recommended_action,
        response_time
    ) = get_department_and_action(
        category,
        priority
    )

    # --------------------------------------------------------
    # 5. Evidence score
    # --------------------------------------------------------

    (
        evidence_score,
        confidence,
        evidence_reasons
    ) = calculate_evidence_score(
        complaint,
        category,
        location,
        priority
    )

    # --------------------------------------------------------
    # 6. Missing information
    # --------------------------------------------------------

    missing_information = (
        get_missing_information(
            complaint,
            location,
            category
        )
    )

    # --------------------------------------------------------
    # 7. Strands AI reasoning
    # --------------------------------------------------------

    ai_reasoning, strands_used = (
        generate_ai_reasoning(
            category,
            location,
            priority,
            department,
            evidence_score,
            missing_information
        )
    )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    return {
        "category": category,

        "location": location,

        "priority": priority,

        "department": department,

        "recommended_action": (
            recommended_action
        ),

        "response_time": (
            response_time
        ),

        "evidence_score": (
            evidence_score
        ),

        "confidence": confidence,

        "evidence_reasons": (
            evidence_reasons
        ),

        "missing_information": (
            missing_information
        ),

        "ai_reasoning": (
            ai_reasoning
        ),

        "agent_used": (
            "STRANDS"
            if strands_used
            else "RULE_ENGINE"
        )
    }


# ============================================================
# SAVE CASE
# ============================================================

def save_case(
    complaint,
    analysis,
    citizen_id=""
):

    conn = sqlite3.connect(
        DATABASE_NAME
    )

    cursor = conn.cursor()

    # --------------------------------------------------------
    # Create case ID
    # --------------------------------------------------------

    case_id = create_case_id()

    created_at = (
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    # --------------------------------------------------------
    # Save case
    # --------------------------------------------------------

    cursor.execute("""
        INSERT INTO cases (
            case_id,
            description,
            complaint,
            category,
            location,
            priority,
            status,
            missing_information,
            created_at,
            department,
            recommended_action,
            response_time,
            evidence_score,
            confidence,
            evidence_reasons,
            citizen_id,
            ai_reasoning,
            agent_used
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (

        case_id,

        complaint,

        complaint,

        analysis["category"],

        analysis["location"],

        analysis["priority"],

        "OPEN",

        analysis[
            "missing_information"
        ],

        created_at,

        analysis[
            "department"
        ],

        analysis[
            "recommended_action"
        ],

        analysis[
            "response_time"
        ],

        analysis[
            "evidence_score"
        ],

        analysis[
            "confidence"
        ],

        ", ".join(
            analysis[
                "evidence_reasons"
            ]
        ),

        citizen_id,

        analysis[
            "ai_reasoning"
        ],

        analysis[
            "agent_used"
        ]
    ))

    # --------------------------------------------------------
    # Initial status history
    # --------------------------------------------------------

    cursor.execute("""
        INSERT INTO case_updates (
            case_id,
            status,
            note,
            updated_at
        )
        VALUES (?, ?, ?, ?)
    """, (

        case_id,

        "OPEN",

        "Complaint submitted and analyzed.",

        created_at
    ))

    conn.commit()

    conn.close()

    return case_id


# ============================================================
# OPTIONAL HELPER FUNCTIONS
# ============================================================

def get_case(case_id):

    conn = sqlite3.connect(
        DATABASE_NAME
    )

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM cases
        WHERE case_id = ?
    """, (case_id,))

    case = cursor.fetchone()

    conn.close()

    if case:
        return dict(case)

    return None


def get_case_updates(case_id):

    conn = sqlite3.connect(
        DATABASE_NAME
    )

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            case_id,
            status,
            note,
            updated_at
        FROM case_updates
        WHERE case_id = ?
        ORDER BY id ASC
    """, (case_id,))

    updates = cursor.fetchall()

    conn.close()

    return [
        dict(update)
        for update in updates
    ]


def update_case_status(
    case_id,
    new_status,
    note=""
):

    conn = sqlite3.connect(
        DATABASE_NAME
    )

    cursor = conn.cursor()

    # Check case exists
    cursor.execute("""
        SELECT id
        FROM cases
        WHERE case_id = ?
    """, (case_id,))

    case = cursor.fetchone()

    if not case:
        conn.close()
        return False

    updated_at = (
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    # Update main case
    cursor.execute("""
        UPDATE cases
        SET status = ?
        WHERE case_id = ?
    """, (
        new_status,
        case_id
    ))

    # Add status history
    if not note:
        note = (
            f"Case status changed to {new_status}."
        )

    cursor.execute("""
        INSERT INTO case_updates (
            case_id,
            status,
            note,
            updated_at
        )
        VALUES (?, ?, ?, ?)
    """, (
        case_id,
        new_status,
        note,
        updated_at
    ))

    conn.commit()

    conn.close()

    return True


# ============================================================
# INITIALIZE DATABASE
# ============================================================

if __name__ == "__main__":

    print("Initializing CivicFlow database...")

    setup_database()

    print("Database setup complete.")

    # Simple tests
    print()
    print("Testing CivicFlow backend...")
    print()

    test_water = (
        "There is a major water leakage near "
        "the college hostel. Large amounts of "
        "water are being wasted and students "
        "are affected by the problem."
    )

    print(
        "Water test:",
        classify_issue(test_water)
    )

    print(
        "Water location:",
        extract_location(test_water)
    )

    test_night = (
        "The road is dark at night because "
        "the streetlight is not working."
    )

    print(
        "Night test:",
        extract_location(test_night)
    )

    test_garbage = (
        "There is garbage near the college "
        "parking area."
    )

    print(
        "Garbage test:",
        classify_issue(test_garbage)
    )

    print(
        "Garbage location:",
        extract_location(test_garbage)
    )

    print()
    print("Backend test complete.")