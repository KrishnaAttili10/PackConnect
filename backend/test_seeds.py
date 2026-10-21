"""Fictional data for isolated tests; never inserted into the live app."""

def seed_students(db):
    students = [
        (
            "Alex Morgan",
            "MS Computer Science",
            "Second Year",
            "I enjoy helping students prepare for software "
            "engineering courses and team projects.",
            "Software Engineering, Web Development",
            1,
            ["CSC 510", "CSC 540"],
        ),
        (
            "Jordan Lee",
            "MS Computer Science",
            "First Year",
            "Happy to share my experience with course "
            "assignments and study strategies.",
            "AI, Databases",
            1,
            ["CSC 510", "CSC 515"],
        ),
        (
            "Taylor Kim",
            "MS Computer Science",
            "Second Year",
            "Interested in helping peers navigate "
            "graduate-level computer science courses.",
            "Machine Learning, Databases",
            1,
            ["CSC 540", "CSC 515"],
        ),
        (
            "Sam Patel",
            "MS Computer Science",
            "Second Year",
            "I can share tips about software engineering "
            "projects and working in teams.",
            "Software Engineering, Cloud Computing",
            1,
            ["CSC 510"],
        ),
    ]
    for name, program, year, bio, interests, willing, courses in students:
        student_id = db.execute(
            "INSERT INTO students (name, program, year, bio, interests, willing_to_advise, advice_topics) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (name, program, year, bio, interests, bool(willing), "Workload, Projects, Course Prep"),
        ).fetchone()["id"]
        with db.cursor() as cursor:
            cursor.executemany("INSERT INTO completed_courses (student_id, course_code) VALUES (%s, %s)",
                               [(student_id, course) for course in courses])
