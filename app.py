from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session
)

import sqlite3

from backend import (
    setup_database,
    analyze_problem,
    save_case,
    find_possible_duplicate
)


app = Flask(__name__)

app.secret_key = "civicflow-demo-secret-key"

DATABASE = "civicflow.db"


def get_db_connection():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


def get_smart_action(
    category,
    priority
):

    category = (category or "").upper()

    priority = (priority or "").upper()

    actions = {

        "ROAD": {
            "URGENT":
                "Immediately inspect the road and place warning signs/barriers.",

            "HIGH":
                "Dispatch Road Maintenance team for urgent inspection.",

            "MEDIUM":
                "Schedule road inspection and repair.",

            "LOW":
                "Add the issue to the routine road maintenance list."
        },

        "STREETLIGHT": {
            "URGENT":
                "Immediately inspect the streetlight and restore lighting.",

            "HIGH":
                "Dispatch electrical maintenance team.",

            "MEDIUM":
                "Schedule streetlight inspection.",

            "LOW":
                "Add to routine electrical maintenance."
        },

        "GARBAGE": {
            "URGENT":
                "Arrange immediate garbage collection and sanitation inspection.",

            "HIGH":
                "Dispatch sanitation team for cleanup.",

            "MEDIUM":
                "Schedule garbage collection.",

            "LOW":
                "Add to routine sanitation schedule."
        },

        "WATER": {
            "URGENT":
                "Immediately inspect the leakage and prevent water wastage.",

            "HIGH":
                "Dispatch water department for urgent repair.",

            "MEDIUM":
                "Schedule pipeline inspection.",

            "LOW":
                "Add to routine water maintenance."
        },

        "INFRASTRUCTURE": {
            "URGENT":
                "Immediately inspect the infrastructure issue and secure the area.",

            "HIGH":
                "Forward to the infrastructure department for urgent inspection.",

            "MEDIUM":
                "Schedule infrastructure inspection.",

            "LOW":
                "Add to routine infrastructure maintenance."
        },

        "OTHER": {
            "URGENT":
                "Immediately inspect the reported issue.",

            "HIGH":
                "Forward the complaint to the appropriate department.",

            "MEDIUM":
                "Schedule the issue for inspection.",

            "LOW":
                "Add the issue to the routine service queue."
        }
    }

    if category in actions:

        return actions[category].get(
            priority,
            "Forward the complaint to the responsible department."
        )

    return (
        "Forward the complaint to the responsible department."
    )


@app.route("/", methods=["GET", "POST"])
def index():

    message = None

    error = None

    result = None

    duplicate = None

    if request.method == "POST":

        complaint = request.form.get(
            "complaint",
            ""
        ).strip()

        if not complaint:

            error = "Please enter a complaint."

            return render_template(
                "index.html",
                message=message,
                error=error,
                result=result,
                duplicate=duplicate
            )

        try:

            result = analyze_problem(
                complaint
            )

            duplicate = find_possible_duplicate(
                complaint,
                result.get("category", ""),
                result.get("location", "")
            )

            case_id = save_case(
                complaint,
                result
            )

            result["case_id"] = case_id

            if duplicate:

                message = (
                    f"Complaint submitted successfully. "
                    f"Case ID: {case_id}. "
                    f"Possible duplicate detected: "
                    f"{duplicate.get('case_id', 'existing case')}."
                )

            else:

                message = (
                    f"Complaint submitted successfully. "
                    f"Case ID: {case_id}"
                )

        except Exception as e:

            error = (
                f"Error while submitting complaint: {str(e)}"
            )

    return render_template(
        "index.html",
        message=message,
        error=error,
        result=result,
        duplicate=duplicate
    )


@app.route(
    "/citizen/set_id",
    methods=["POST"]
)
def citizen_set_id():

    citizen_name = request.form.get(
        "citizen_name",
        ""
    ).strip()

    citizen_id = request.form.get(
        "citizen_id",
        ""
    ).strip()

    if not citizen_name:
        citizen_name = "Demo Citizen"

    if not citizen_id:
        citizen_id = "citizen-001"

    session["citizen_name"] = citizen_name

    session["citizen_id"] = citizen_id

    return redirect(
        url_for("citizen_dashboard")
    )


@app.route("/citizen")
def citizen_dashboard():

    citizen_id = session.get(
        "citizen_id"
    )

    if not citizen_id:

        return render_template(
            "citizen.html",
            logged_in=False,
            citizen_name="",
            citizen_id="",
            cases=[],
            total_cases=0,
            open_cases=0,
            resolved_cases=0
        )

    citizen_name = session.get(
        "citizen_name",
        "Demo Citizen"
    )

    conn = get_db_connection()

    cases = conn.execute(
        """
        SELECT *
        FROM cases
        WHERE citizen_id = ?
        ORDER BY id DESC
        """,
        (citizen_id,)
    ).fetchall()

    conn.close()

    total_cases = len(cases)

    resolved_cases = sum(
        1
        for case in cases
        if (case["status"] or "").upper()
        == "RESOLVED"
    )

    open_cases = (
        total_cases - resolved_cases
    )

    return render_template(
        "citizen.html",
        logged_in=True,
        citizen_name=citizen_name,
        citizen_id=citizen_id,
        cases=cases,
        total_cases=total_cases,
        open_cases=open_cases,
        resolved_cases=resolved_cases
    )


@app.route(
    "/citizen/report",
    methods=["POST"]
)
def citizen_report():

    citizen_id = session.get(
        "citizen_id"
    )

    if not citizen_id:

        return redirect(
            url_for("citizen_dashboard")
        )

    complaint = request.form.get(
        "complaint",
        ""
    ).strip()

    if not complaint:

        return redirect(
            url_for("citizen_dashboard")
        )

    try:

        result = analyze_problem(
            complaint
        )

        duplicate = find_possible_duplicate(
            complaint,
            result.get("category", ""),
            result.get("location", "")
        )

        case_id = save_case(
            complaint,
            result,
            citizen_id
        )

        if duplicate:

            conn = get_db_connection()

            conn.execute(
                """
                UPDATE cases
                SET
                    duplicate_case_id = ?,
                    duplicate_similarity = ?,
                    duplicate_explanation = ?
                WHERE case_id = ?
                """,
                (
                    duplicate.get("case_id"),
                    duplicate.get("similarity", 0),
                    duplicate.get(
                        "explanation",
                        "Similar complaint detected."
                    ),
                    case_id
                )
            )

            conn.commit()

            conn.close()

        return redirect(
            url_for(
                "citizen_case",
                case_id=case_id
            )
        )

    except Exception as e:

        return f"""
        <html>
        <head>
            <title>CivicFlow Error</title>
        </head>

        <body
            style="
                font-family:Arial;
                padding:40px;
            "
        >

            <h2>CivicFlow Error</h2>

            <p>{str(e)}</p>

            <br>

            <a href="/citizen">
                ← Back to Citizen Dashboard
            </a>

        </body>
        </html>
        """


@app.route(
    "/citizen/case/<case_id>"
)
def citizen_case(case_id):

    citizen_id = session.get(
        "citizen_id"
    )

    if not citizen_id:

        return redirect(
            url_for("citizen_dashboard")
        )

    conn = get_db_connection()

    case = conn.execute(
        """
        SELECT *
        FROM cases
        WHERE case_id = ?
        AND citizen_id = ?
        """,
        (
            case_id,
            citizen_id
        )
    ).fetchone()

    updates = conn.execute(
        """
        SELECT *
        FROM case_updates
        WHERE case_id = ?
        ORDER BY id ASC
        """,
        (case_id,)
    ).fetchall()

    conn.close()

    if not case:

        return """
        <html>

        <body
            style="
                font-family:Arial;
                padding:40px;
            "
        >

            <h2>Case not found</h2>

            <a href="/citizen">
                ← Back to Citizen Dashboard
            </a>

        </body>

        </html>
        """

    return render_template(
        "citizen_case.html",
        case=case,
        updates=updates,
        citizen_name=session.get(
            "citizen_name",
            "Demo Citizen"
        )
    )


@app.route("/citizen/logout")
def citizen_logout():

    session.pop(
        "citizen_id",
        None
    )

    session.pop(
        "citizen_name",
        None
    )

    return redirect(
        url_for("citizen_dashboard")
    )


@app.route("/cases")
def cases():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    priority = request.args.get(
        "priority",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()

    conn = get_db_connection()

    query = """
        SELECT *
        FROM cases
        WHERE 1 = 1
    """

    params = []

    if search:

        query += """
            AND (
                case_id LIKE ?
                OR description LIKE ?
                OR location LIKE ?
                OR category LIKE ?
            )
        """

        search_value = (
            f"%{search}%"
        )

        params.extend(
            [search_value] * 4
        )

    if category:

        query += (
            " AND category = ?"
        )

        params.append(category)

    if priority:

        query += (
            " AND priority = ?"
        )

        params.append(priority)

    if status:

        query += (
            " AND status = ?"
        )

        params.append(status)

    query += (
        " ORDER BY id DESC"
    )

    cases_data = conn.execute(
        query,
        params
    ).fetchall()

    all_cases = conn.execute(
        """
        SELECT *
        FROM cases
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    case_list = []

    for case in cases_data:

        case_dict = dict(case)

        case_dict["smart_action"] = (
            get_smart_action(
                case_dict.get(
                    "category",
                    ""
                ),
                case_dict.get(
                    "priority",
                    ""
                )
            )
        )

        case_list.append(
            case_dict
        )

    total_cases = len(
        all_cases
    )

    open_cases = sum(
        1
        for c in all_cases
        if (c["status"] or "").upper()
        == "OPEN"
    )

    urgent_cases = sum(
        1
        for c in all_cases
        if (c["priority"] or "").upper()
        == "URGENT"
    )

    resolved_cases = sum(
        1
        for c in all_cases
        if (c["status"] or "").upper()
        == "RESOLVED"
    )

    category_counts = {}

    for c in all_cases:

        cat = (
            c["category"]
            or "OTHER"
        )

        category_counts[cat] = (
            category_counts.get(
                cat,
                0
            ) + 1
        )

    category_stats = [
        {
            "category": cat,
            "total": count
        }

        for cat, count
        in category_counts.items()
    ]

    category_stats.sort(
        key=lambda x: x["total"],
        reverse=True
    )

    category_labels = list(
        category_counts.keys()
    )

    category_values = list(
        category_counts.values()
    )

    status_counts = {}

    for c in all_cases:

        st = (
            c["status"]
            or "OPEN"
        )

        status_counts[st] = (
            status_counts.get(
                st,
                0
            ) + 1
        )

    status_labels = list(
        status_counts.keys()
    )

    status_values = list(
        status_counts.values()
    )

    priority_counts = {}

    for c in all_cases:

        pr = (
            c["priority"]
            or "LOW"
        )

        priority_counts[pr] = (
            priority_counts.get(
                pr,
                0
            ) + 1
        )

    priority_labels = list(
        priority_counts.keys()
    )

    priority_values = list(
        priority_counts.values()
    )

    ai_insights = []

    if urgent_cases > 0:

        ai_insights.append(
            f"{urgent_cases} urgent complaint(s) "
            "require immediate attention."
        )

    high_cases = sum(
        1
        for c in all_cases
        if (c["priority"] or "").upper()
        == "HIGH"
    )

    if high_cases > 0:

        ai_insights.append(
            f"{high_cases} high-priority complaint(s) "
            "should be handled soon."
        )

    if category_counts:

        top_category = max(
            category_counts,
            key=category_counts.get
        )

        ai_insights.append(
            f"{top_category} is currently the "
            "most reported issue category."
        )

    if total_cases > 0:

        resolution_rate = (
            resolved_cases
            / total_cases
        ) * 100

        ai_insights.append(
            f"Current resolution rate is "
            f"{resolution_rate:.1f}%."
        )

    if not ai_insights:

        ai_insights.append(
            "No major AI insights available yet."
        )

    return render_template(
        "cases.html",
        cases=case_list,
        total_cases=total_cases,
        open_cases=open_cases,
        urgent_cases=urgent_cases,
        resolved_cases=resolved_cases,
        search=search,
        selected_category=category,
        selected_priority=priority,
        selected_status=status,
        category_stats=category_stats,
        category_counts=category_counts,
        category_labels=category_labels,
        category_values=category_values,
        status_counts=status_counts,
        status_labels=status_labels,
        status_values=status_values,
        priority_counts=priority_counts,
        priority_labels=priority_labels,
        priority_values=priority_values,
        ai_insights=ai_insights
    )


@app.route(
    "/update_status/<case_id>",
    methods=["POST"]
)
def update_status(case_id):

    new_status = request.form.get(
        "status",
        ""
    ).strip().upper()

    allowed_statuses = [
        "OPEN",
        "UNDER REVIEW",
        "IN PROGRESS",
        "RESOLVED"
    ]

    if new_status not in allowed_statuses:

        return redirect(
            url_for("cases")
        )

    conn = get_db_connection()

    old_case = conn.execute(
        """
        SELECT status
        FROM cases
        WHERE case_id = ?
        """,
        (case_id,)
    ).fetchone()

    conn.execute(
        """
        UPDATE cases
        SET status = ?
        WHERE case_id = ?
        """,
        (
            new_status,
            case_id
        )
    )

    now = (
        __import__("datetime")
        .datetime
        .now()
        .strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    note = (
        f"Status changed from "
        f"{old_case['status'] if old_case else 'UNKNOWN'} "
        f"to {new_status}."
    )

    conn.execute(
        """
        INSERT INTO case_updates (
            case_id,
            status,
            note,
            updated_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            case_id,
            new_status,
            note,
            now
        )
    )

    conn.commit()

    conn.close()

    return redirect(
        url_for("cases")
    )


if __name__ == "__main__":

    setup_database()

    print()

    print("=" * 60)

    print(
        "       CivicFlow - AI Community Action Platform"
    )

    print("=" * 60)

    print()

    print("Citizen Dashboard:")

    print(
        "http://127.0.0.1:5000/citizen"
    )

    print()

    print("Authority Dashboard:")

    print(
        "http://127.0.0.1:5000/cases"
    )

    print()

    print("Complaint Reporting:")

    print(
        "http://127.0.0.1:5000/"
    )

    print()

    print("=" * 60)

    app.run(
        debug=True
    )