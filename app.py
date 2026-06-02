from flask import Flask, render_template, session, redirect, url_for, request, flash, make_response
import sqlite3
import json
from datetime import datetime, timedelta
import os
import io
from werkzeug.security import generate_password_hash, check_password_hash
from csv import writer

# Create the Flask app and set a secret key for session handling.
app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"

# Database filename used by sqlite3.
DATABASE = "database.db"
TIMETABLE_JSON = "static/timetable.json"


def get_db():
    """Open a database connection and return it."""
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def query_db(query, args=(), one=False):
    conn = get_db()
    cursor = conn.execute(query, args)
    rows = cursor.fetchall()
    conn.close()
    if one:
        return rows[0] if rows else None
    return rows


def load_timetable():
    """Load timetable data from JSON file."""
    try:
        if os.path.exists(TIMETABLE_JSON):
            with open(TIMETABLE_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading timetable from JSON: {e}")
    return []


def parse_timetable_datetime(value):
    """Parse timetable datetime string with or without fractional seconds."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def parse_students_list(value):
    """Normalize students stored as JSON, string, or Python-like list."""
    if isinstance(value, list):
        return value
    if not value:
        return []

    if isinstance(value, str):
        value = value.strip()
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            normalized = value.replace("'", '"')
            try:
                return json.loads(normalized)
            except json.JSONDecodeError:
                return [item.strip() for item in value.strip('[]').split(',') if item.strip()]

    return []


def normalize_timetable():
    """Return all timetable entries with parsed times and student membership."""
    raw_timetable = load_timetable()
    now = datetime.now()
    normalized = []

    for row in raw_timetable:
        start_time = parse_timetable_datetime(row.get('start_time'))
        end_time = parse_timetable_datetime(row.get('end_time'))
        students = parse_students_list(row.get('students', []))

        normalized.append({
            'id': row.get('id'),
            'class_id': row.get('class_id'),
            'class_name': row.get('class_name', ''),
            'teacher_id': row.get('teacher_id', ''),
            'teacher_name': row.get('teacher_name', ''),
            'start_time': row.get('start_time', ''),
            'end_time': row.get('end_time', ''),
            'start_time_obj': start_time,
            'end_time_obj': end_time,
            'students': students,
            'is_active': bool(start_time and end_time and start_time <= now <= end_time)
        })

    return normalized


def get_student_timetable(student_text_id):
    student_classes = []
    for row in normalize_timetable():
        if student_text_id in row['students']:
            student_classes.append(row)
    return student_classes


def get_timetable_record(timetable_id):
    timetable_id = str(timetable_id)
    for row in normalize_timetable():
        if str(row.get('id')) == timetable_id:
            return row
    return None


def get_class_options():
    rows = query_db("SELECT class_id, class_name FROM classes ORDER BY class_id")
    if rows:
        return [{'class_id': row['class_id'], 'class_name': row['class_name']} for row in rows]
    return [
        {'class_id': '2003', 'class_name': 'Maths'},
        {'class_id': '2074', 'class_name': 'English'},
        {'class_id': '2752', 'class_name': 'Science'},
        {'class_id': '2932', 'class_name': 'History'},
    ]


def get_student_attendance_summary(student_id):
    rows = query_db(
        "SELECT status, COUNT(*) AS total FROM student_records WHERE student_id = ? GROUP BY status",
        (student_id,)
    )
    counts = {'present': 0, 'absent': 0, 'late': 0}
    total = 0
    for row in rows:
        counts[row['status']] = row['total']
        total += row['total']

    recent_records = query_db(
        "SELECT * FROM student_records WHERE student_id = ? ORDER BY timestamp DESC LIMIT 5",
        (student_id,)
    )
    return counts, total, recent_records


def get_teacher_dashboard_data(teacher_id):
    records = query_db(
        "SELECT * FROM attendance_records WHERE tutor_id = ? ORDER BY timestamp DESC LIMIT 5",
        (teacher_id,)
    )
    totals = query_db(
        "SELECT COUNT(*) AS count, AVG(student_count) AS avg_present FROM attendance_records WHERE tutor_id = ?",
        (teacher_id,),
        one=True
    )
    stats = {
        'total_submissions': totals['count'] if totals else 0,
        'average_present': round(totals['avg_present'] or 0, 1) if totals else 0,
        'recent_records': records,
    }
    return stats


def hash_password(password):
    return generate_password_hash(password)


def verify_password(stored_password, candidate_password):
    if not stored_password or not candidate_password:
        return False
    if check_password_hash(stored_password, candidate_password):
        return True
    # Support existing plain-text passwords from earlier database versions.
    return stored_password == candidate_password


def init_db():
    """Create the required tables and insert hard-coded accounts."""
    conn = get_db()
    cursor = conn.cursor()

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

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
        """
    )

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
            class_id TEXT NOT NULL,
            students TEXT NOT NULL,
            teacher_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        "INSERT OR IGNORE INTO tutors (staff_id, password, name) VALUES (?, ?, ?)",
        ("teacher1", hash_password("pass123"), "Alice Teacher"),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO tutors (staff_id, password, name) VALUES (?, ?, ?)",
        ("teacher2", hash_password("hello456"), "Bob Tutor"),
    )

    cursor.execute(
        "INSERT OR IGNORE INTO admin (admin_id, password) VALUES (?, ?)",
        ("admin1", hash_password("adminpass")),
    )

    cursor.execute(
        "INSERT OR IGNORE INTO students (student_id, password, name) VALUES (?, ?, ?)",
        ("student1", hash_password("studentpass"), "Timothy"),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO students (student_id, password, name) VALUES (?, ?, ?)",
        ("student2", hash_password("pass456"), "Sarah"),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO students (student_id, password, name) VALUES (?, ?, ?)",
        ("student3", hash_password("pass789"), "Michael"),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO students (student_id, password, name) VALUES (?, ?, ?)",
        ("student4", hash_password("passabc"), "Jessica"),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO students (student_id, password, name) VALUES (?, ?, ?)",
        ("student5", hash_password("passdef"), "David"),
    )

    class_rows = [
        ("2003", "Maths"),
        ("2074", "English"),
        ("2752", "Science"),
        ("2932", "History"),
    ]
    for class_id, class_name in class_rows:
        cursor.execute(
            "INSERT OR IGNORE INTO classes (class_id, class_name) VALUES (?, ?)",
            (class_id, class_name),
        )

    cursor.execute(
        "INSERT OR IGNORE INTO timetable (class_id, students, teacher_id, start_time, end_time) VALUES (?, ?, ?, ?, ?)",
        ("2003", json.dumps(["student1", "student2"]), "teacher1", datetime.now().strftime('%Y-%m-%d %H:%M:%S'), (datetime.now() + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')),
    )

    conn.commit()
    conn.close()


def find_teacher(staff_id, password):
    """Return the teacher row if credentials match."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM tutors WHERE staff_id = ?",
        (staff_id,),
    )
    teacher = cursor.fetchone()
    conn.close()
    if teacher and verify_password(teacher['password'], password):
        return teacher
    return None


def find_admin(admin_id, password):
    """Return the admin row if credentials match."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM admin WHERE admin_id = ?",
        (admin_id,),
    )
    admin = cursor.fetchone()
    conn.close()
    if admin and verify_password(admin['password'], password):
        return admin
    return None


def find_student(student_id, password):
    """Return the student row if credentials match."""
    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM students WHERE student_id = ?",
        (student_id,),
    )
    student = cursor.fetchone()
    conn.close()
    if student and verify_password(student['password'], password):
        return student
    return None


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

    student_text_id = session.get('student_text_id', '')
    current_time = datetime.now()

    if request.method == 'POST':
        timetable_id = request.form.get('timetable_id', '').strip()
        attendance = request.form.get('attendance', 'absent').strip()
        notes = request.form.get('notes', '').strip()

        conn = get_db()
        conn.execute(
            "INSERT INTO student_records (student_id, timetable_id, status, notes) VALUES (?, ?, ?, ?)",
            (session['student_id'], timetable_id, attendance, notes),
        )
        conn.commit()
        conn.close()

        class_details = get_timetable_record(timetable_id) or {}
        session['submission'] = {
            'class_id': class_details.get('class_id', ''),
            'class_name': class_details.get('class_name', ''),
            'teacher_name': class_details.get('teacher_name', ''),
            'start_time': class_details.get('start_time', ''),
            'end_time': class_details.get('end_time', ''),
            'attendance': attendance,
            'notes': notes,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        return redirect(url_for('attendance_summary'))

    student_classes = get_student_timetable(student_text_id)
    active_classes = [cls for cls in student_classes if cls['is_active']]
    upcoming_classes = sorted(
        [cls for cls in student_classes if cls['start_time_obj'] and cls['start_time_obj'] > current_time],
        key=lambda cls: cls['start_time_obj']
    )
    next_class = upcoming_classes[0] if upcoming_classes else None
    attendance_counts, attendance_total, recent_records = get_student_attendance_summary(session['student_id'])

    return render_template(
        'student_dashboard.html',
        name=session.get('student_name', 'Student'),
        active_classes=active_classes,
        student_classes=student_classes,
        next_class=next_class,
        attendance_counts=attendance_counts,
        attendance_total=attendance_total,
        recent_records=recent_records,
        current_time=current_time.strftime('%Y-%m-%d %H:%M:%S')
    )

@app.route('/student/attendance_summary')
def attendance_summary():
    """Attendance summary page showing the submitted attendance."""
    if 'student_id' not in session:
        return redirect(url_for('student'))
    
    submission = session.pop('submission', None)
    
    if not submission:
        return redirect(url_for('student_dashboard'))
    
    return render_template(
        'attendance_summary.html',
        name=session.get('student_name', 'Student'),
        submission=submission
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


@app.route('/info')
def info_page():
    """Info page with About, Contact, and Help sections."""
    return render_template('info_page.html')


@app.route('/admin/student-overview')
def student_overview():
    """Student overview page displaying all student attendance records."""
    if 'admin_id' not in session:
        return redirect(url_for('admin'))

    conn = get_db()
    cursor = conn.execute(
        """
        SELECT sr.id, s.student_id, s.name as student_name, sr.timetable_id, sr.status, sr.notes, sr.timestamp
        FROM student_records sr
        JOIN students s ON sr.student_id = s.id
        ORDER BY sr.timestamp DESC
        """
    )
    records = cursor.fetchall()
    conn.close()

    # Load timetable data to enrich records with class information
    all_timetables = load_timetable()
    timetable_map = {t['id']: t for t in all_timetables}

    # Enhance records with class information from timetable
    enriched_records = []
    for record in records:
        class_info = timetable_map.get(record['timetable_id'], {})
        enriched_records.append({
            'id': record['id'],
            'student_id': record['student_id'],
            'student_name': record['student_name'],
            'class_id': class_info.get('class_id', 'N/A'),
            'class_name': class_info.get('class_name', 'N/A'),
            'teacher_name': class_info.get('teacher_name', 'N/A'),
            'status': record['status'],
            'notes': record['notes'],
            'timestamp': record['timestamp']
        })

    return render_template('student_overview.html', records=enriched_records)


@app.route('/teacher/dashboard', methods=['GET', 'POST'])
def teacher_dashboard():
    """Teacher attendance submission page."""
    if 'teacher_id' not in session:
        return redirect(url_for('teacher'))

    class_options = get_class_options()
    stats = get_teacher_dashboard_data(session['teacher_id'])

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
        class_options=class_options,
        stats=stats,
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

    records = query_db(
        "SELECT a.id, t.name AS tutor_name, a.class_name, a.class_running, a.student_count, a.notes, a.timestamp "
        "FROM attendance_records a "
        "JOIN tutors t ON a.tutor_id = t.id "
        "ORDER BY a.timestamp DESC"
    )
    totals = query_db("SELECT COUNT(*) AS total FROM attendance_records", (), one=True)
    students = query_db("SELECT COUNT(*) AS total FROM students", (), one=True)
    tutors = query_db("SELECT COUNT(*) AS total FROM tutors", (), one=True)

    return render_template(
        'admin_dashboard.html',
        records=records,
        attendance_total=totals['total'] if totals else 0,
        student_total=students['total'] if students else 0,
        tutor_total=tutors['total'] if tutors else 0,
    )


@app.route('/admin/export-attendance')
def admin_export_attendance():
    if 'admin_id' not in session:
        return redirect(url_for('admin'))

    records = query_db(
        "SELECT a.id, t.name AS tutor_name, a.class_name, a.class_running, a.student_count, a.notes, a.timestamp "
        "FROM attendance_records a "
        "JOIN tutors t ON a.tutor_id = t.id "
        "ORDER BY a.timestamp DESC"
    )

    output = io.StringIO()
    csv_writer = writer(output)
    csv_writer.writerow(['ID', 'Tutor', 'Class', 'Running', 'Students Present', 'Notes', 'Timestamp'])
    for record in records:
        csv_writer.writerow([
            record['id'],
            record['tutor_name'],
            record['class_name'],
            'Yes' if record['class_running'] == 1 else 'No',
            record['student_count'],
            record['notes'] or '',
            record['timestamp'],
        ])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=attendance_records.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response


@app.route('/logout')
def logout():
    """Log out the current user and clear the session."""
    session.clear()
    return redirect(url_for('home'))


@app.route('/api/timetable')
def api_get_timetable():
    """API endpoint to get timetable data for the logged-in student."""
    if 'student_id' not in session:
        return {'error': 'Not authenticated'}, 401
    
    all_timetables = load_timetable()
    student_text_id = session.get('student_text_id', '')
    
    # Filter classes for the current student
    student_classes = []
    for timetable in all_timetables:
        students_list = timetable.get('students', [])
        if isinstance(students_list, str):
            try:
                students_list = json.loads(students_list)
            except json.JSONDecodeError:
                pass
        
        if student_text_id in students_list:
            student_classes.append(timetable)
    
    return json.dumps(student_classes), 200, {'Content-Type': 'application/json'}


@app.route('/api/timetable/all')
def api_get_all_timetable():
    """API endpoint to get all timetable data (admin/teacher access)."""
    if 'teacher_id' not in session and 'admin_id' not in session:
        return {'error': 'Not authorized'}, 403
    
    all_timetables = load_timetable()
    return json.dumps(all_timetables), 200, {'Content-Type': 'application/json'}


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)


