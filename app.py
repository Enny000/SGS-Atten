from flask import Flask, render_template, session, redirect, url_for, request, flash
import sqlite3
import json
from datetime import datetime, timedelta

# Create the Flask app and set a secret key for session handling.
app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"

# Database filename used by sqlite3.
DATABASE = "database.db"


def get_db():
    """Open a database connection and return it."""
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the required tables and insert hard-coded accounts."""
    conn = get_db()
    cursor = conn.cursor()

    # Table for teacher login accounts.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tutors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            name TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            name TEXT
        )
        """
    )

        # Table for attendance submissions.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS student_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            timetable_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL,
            notes TEXT
        )
        """
    )

    # Table for attendance submissions.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tutor_id INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            class_running INTEGER NOT NULL,
            student_count INTEGER,
            notes TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tutor_id) REFERENCES tutors(id)
        )
        """
    )

    # Table for admin login accounts.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
        """
    )

        # Table for classes.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS classes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id TEXT NOT NULL UNIQUE,
            class_name TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS timetable(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id TEXT NOT NULL UNIQUE,  
        students TEXT[] NOT NULL,
        teacher_id TEXT NOT NULL,
        start_time TIMESTAMP NOT NULL,
        end_time TIMESTAMP NOT NULL
    )
        """
    )

    # Add example hard-coded teacher accounts.
    cursor.execute(
        "INSERT OR IGNORE INTO tutors (staff_id, password, name) VALUES (?, ?, ?)",
        ("teacher1", "pass123", "Alice Teacher"),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO tutors (staff_id, password, name) VALUES (?, ?, ?)",
        ("teacher2", "hello456", "Bob Tutor"),
    )

    # Add one example admin account.
    cursor.execute(
        "INSERT OR IGNORE INTO admin (admin_id, password) VALUES (?, ?)",
        ("admin1", "adminpass"),
    )

    cursor.execute(
        "INSERT OR IGNORE INTO students (student_id, password, name) VALUES (?, ?, ?)",
        ("student1", "studentpass", "Timothy"),
    )

    cursor.execute(
        "INSERT OR IGNORE INTO classes (class_id, class_name) VALUES (?, ?)",
        ("B101", "Maths"),
    )

    cursor.execute(
        "INSERT OR IGNORE INTO timetable (class_id, students, teacher_id, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
        ("B101", "[student1]", "teacher1", datetime.now(), datetime.now() + timedelta(minutes=30)),
    )


    # # Add one example student account.
    # cursor.execute(
    #     "INSERT OR IGNORE INTO admin (admin_id, password) VALUES (?, ?)",
    #     ("admin1", "adminpass"),
    # )

    conn.commit()
    conn.close()


def find_teacher(staff_id, password):
    """Return the teacher row if credentials match."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM tutors WHERE staff_id = ? AND password = ?",
        (staff_id, password),
    )
    teacher = cursor.fetchone()
    conn.close()
    return teacher


def find_admin(admin_id, password):
    """Return the admin row if credentials match."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM admin WHERE admin_id = ? AND password = ?",
        (admin_id, password),
    )
    admin = cursor.fetchone()
    conn.close()
    return admin


def find_student(student_id, password):
    """Return the student row if credentials match."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM students WHERE student_id = ? AND password = ?",
        (student_id, password),
    )
    student = cursor.fetchone()
    conn.close()
    return student


@app.route('/')
def home():
    """Show the home page with role selection."""
    return render_template('home.html')


@app.route('/teacher', methods=['GET', 'POST'])
def teacher():
    """Teacher login page and login handling."""
    error = None
    if request.method == 'POST':
        staff_id = request.form.get('staff_id', '').strip()
        password = request.form.get('password', '').strip()
        teacher_record = find_teacher(staff_id, password)

        if teacher_record:
            session['teacher_id'] = teacher_record['id']
            session['teacher_name'] = teacher_record['name']
            return redirect(url_for('teacher_dashboard'))

        error = 'Invalid teacher ID or password.'

    return render_template('T_Login.html', error=error)

@app.route('/student', methods=['GET', 'POST'])
def student():
    """Student login page and login handling."""
    error = None
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        password = request.form.get('password', '').strip()
        student_record = find_student(student_id, password)

        if student_record:
            session['student_id'] = student_record['id']
            session['student_text_id'] = student_record['student_id']
            session['student_name'] = student_record['name']
            return redirect(url_for('student_dashboard'))

        error = 'Invalid student ID or password.'

    return render_template('S_Login.html', error=error)


@app.route('/student/dashboard', methods=['GET', 'POST'])
def student_dashboard():
    """Student dashboard page with active classes."""
    if 'student_id' not in session:
        return redirect(url_for('student'))

    if request.method == 'POST':
        timetable_id = request.form.get('timetable_id', '').strip()
        attendance = request.form.get('attendance', 'absent').strip()
        notes = request.form.get('notes', '').strip()

        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO student_records (student_id, timetable_id, status, notes) VALUES (?, ?, ?, ?)",
            (session['student_id'], timetable_id, attendance, notes),
        )
        conn.commit()
        conn.close()

        return redirect(url_for('student_dashboard'))

    # Fetch all classes where this student is enrolled
    conn = get_db()
    cursor = conn.execute(
        "SELECT id, class_id, students, teacher_id, start_time, end_time FROM timetable"
    )
    all_timetables = cursor.fetchall()
    conn.close()

    # Filter classes where student is enrolled
    current_time = datetime.now()
    active_classes = []
    no_active_classes = True

    for timetable in all_timetables:
        # Check if student is in the students list
        student_text_id = session.get('student_text_id', '')
        try:
            students_list = json.loads(timetable['students'])
        except (json.JSONDecodeError, TypeError):
            # If JSON parsing fails, try simple string matching
            students_list = [s.strip("'\"[]") for s in timetable['students'].replace('[', '').replace(']', '').split(',')]
        
        if student_text_id in students_list:
            try:
                start_time = datetime.fromisoformat(timetable['start_time'])
                end_time = datetime.fromisoformat(timetable['end_time'])
            except (ValueError, TypeError):
                # If datetime parsing fails, treat as string comparison
                start_time = timetable['start_time']
                end_time = timetable['end_time']
                is_active = False
            else:
                is_active = start_time <= current_time <= end_time

            active_classes.append({
                'timetable_id': timetable['id'],
                'class_id': timetable['class_id'],
                'teacher_id': timetable['teacher_id'],
                'start_time': timetable['start_time'],
                'end_time': timetable['end_time'],
                'is_active': is_active
            })
            if is_active:
                no_active_classes = False

    return render_template(
        'student_dashboard.html',
        name=session.get('student_name', 'Student'),
        active_classes=active_classes,
        no_active_classes=no_active_classes,
        current_time=current_time.strftime('%Y-%m-%d %H:%M:%S')
    )

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    """Admin login page and login handling."""
    error = None
    if request.method == 'POST':
        admin_id = request.form.get('admin_id', '').strip()
        password = request.form.get('password', '').strip()
        admin_record = find_admin(admin_id, password)

        if admin_record:
            session['admin_id'] = admin_record['id']
            return redirect(url_for('admin_menu'))

        error = 'Invalid admin ID or password.'

    return render_template('A_Login.html', error=error)


@app.route('/admin/menu')
def admin_menu():
    """Admin menu page with options."""
    if 'admin_id' not in session:
        return redirect(url_for('admin'))

    return render_template('admin_menu.html')


@app.route('/admin/student-overview')
def student_overview():
    """Student overview page (placeholder)."""
    if 'admin_id' not in session:
        return redirect(url_for('admin'))

    # Placeholder: for now, just show a message
    return render_template('student_overview.html')


@app.route('/teacher/dashboard', methods=['GET', 'POST'])
def teacher_dashboard():
    """Teacher attendance submission page."""
    if 'teacher_id' not in session:
        return redirect(url_for('teacher'))

    success = None
    if request.method == 'POST':
        class_name = request.form.get('class_name', '').strip()
        class_running = 1 if request.form.get('class_running') == 'yes' else 0
        student_count = request.form.get('student_count', '0').strip()
        notes = request.form.get('notes', '').strip()

        try:
            student_count = int(student_count)
        except ValueError:
            student_count = 0

        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO attendance_records (tutor_id, class_name, class_running, student_count, notes) VALUES (?, ?, ?, ?, ?)",
            (session['teacher_id'], class_name, class_running, student_count, notes),
        )
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return redirect(url_for('teacher_summary', record_id=record_id))

    return render_template(
        'teacher_dashboard.html',
        name=session.get('teacher_name', 'Teacher'),
        success=success,
    )


@app.route('/teacher/summary/<int:record_id>')
def teacher_summary(record_id):
    """Summary page after a teacher submits attendance."""
    if 'teacher_id' not in session:
        return redirect(url_for('teacher'))

    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM attendance_records WHERE id = ? AND tutor_id = ?",
        (record_id, session['teacher_id']),
    )
    record = cursor.fetchone()
    conn.close()

    if record is None:
        return redirect(url_for('teacher_dashboard'))

    return render_template(
        'teacher_summary.html',
        name=session.get('teacher_name', 'Teacher'),
        record=record,
    )


@app.route('/admin/dashboard')
def admin_dashboard():
    """Admin dashboard showing all attendance records."""
    if 'admin_id' not in session:
        return redirect(url_for('admin'))

    conn = get_db()
    cursor = conn.execute(
        "SELECT a.id, t.name AS tutor_name, a.class_name, a.class_running, a.student_count, a.notes, a.timestamp"
        " FROM attendance_records a"
        " JOIN tutors t ON a.tutor_id = t.id"
        " ORDER BY a.timestamp DESC"
    )
    records = cursor.fetchall()
    conn.close()

    return render_template('admin_dashboard.html', records=records)


@app.route('/logout')
def logout():
    """Log out the current user and clear the session."""
    session.clear()
    return redirect(url_for('home'))


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)


