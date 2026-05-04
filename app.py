from flask import Flask, render_template, session, redirect, url_for, request, flash
import sqlite3

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
            return redirect(url_for('admin_dashboard'))

        error = 'Invalid admin ID or password.'

    return render_template('A_Login.html', error=error)


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
        conn.execute(
            "INSERT INTO attendance_records (tutor_id, class_name, class_running, student_count, notes) VALUES (?, ?, ?, ?, ?)",
            (session['teacher_id'], class_name, class_running, student_count, notes),
        )
        conn.commit()
        conn.close()

        success = 'Attendance record submitted successfully.'

    return render_template(
        'teacher_dashboard.html',
        name=session.get('teacher_name', 'Teacher'),
        success=success,
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


