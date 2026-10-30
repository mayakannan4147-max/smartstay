import os
import sqlite3
import datetime
import random
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, g
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'smartstay-super-secret-key-2026-dorm-management')
DATABASE = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'database.db')

# -------------------------------------------------------------
# Database Connection Helpers
# -------------------------------------------------------------
def get_db():
    """Get database connection for current request context."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Close db connection when app context ends."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    """Helper to query database and return dictionary rows."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    """Helper to execute insert/update/delete and commit."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id

# -------------------------------------------------------------
# Authentication & Role Decorators
# -------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('login'))
            user_role = session.get('role')
            if user_role not in roles:
                flash('You do not have permission to access that resource.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_current_user():
    """Return current logged in user dict or None."""
    if 'user_id' not in session:
        return None
    user = query_db("SELECT * FROM users WHERE id = ?", [session['user_id']], one=True)
    return user

@app.context_processor
def inject_global_data():
    """Inject user details, unread notifications, and active path into all templates."""
    current_user = get_current_user()
    unread_notifications_count = 0
    notifications_list = []
    student_info = None
    warden_info = None

    if current_user:
        notifications_list = query_db(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 6",
            [current_user['id']]
        )
        count_row = query_db(
            "SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0",
            [current_user['id']], one=True
        )
        unread_notifications_count = count_row['cnt'] if count_row else 0

        if current_user['role'] == 'student':
            student_info = query_db("""
                SELECT s.*, r.room_number, r.floor, r.type as room_type, b.name as block_name
                FROM students s
                LEFT JOIN rooms r ON s.room_id = r.id
                LEFT JOIN blocks b ON r.block_id = b.id
                WHERE s.user_id = ?
            """, [current_user['id']], one=True)
        elif current_user['role'] == 'warden':
            warden_info = query_db("""
                SELECT w.*, b.name as block_name
                FROM wardens w
                LEFT JOIN blocks b ON w.assigned_block_id = b.id
                WHERE w.user_id = ?
            """, [current_user['id']], one=True)

    return {
        'current_user': current_user,
        'unread_notifications_count': unread_notifications_count,
        'recent_notifications': notifications_list,
        'student_info': student_info,
        'warden_info': warden_info,
        'now': datetime.datetime.now()
    }

# -------------------------------------------------------------
# Database Schema & Seed Data Initialization
# -------------------------------------------------------------
def init_db():
    """Initialize database tables and seed realistic sample data."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    # 1. Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('student', 'warden', 'admin')),
        full_name TEXT NOT NULL,
        phone TEXT,
        avatar TEXT DEFAULT 'default.png',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Blocks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS blocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        gender_type TEXT NOT NULL DEFAULT 'Boys',
        total_floors INTEGER DEFAULT 3,
        description TEXT
    )
    """)

    # 3. Rooms
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        block_id INTEGER NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
        room_number TEXT NOT NULL,
        floor INTEGER DEFAULT 1,
        capacity INTEGER DEFAULT 2,
        type TEXT DEFAULT 'Double AC',
        status TEXT DEFAULT 'Available',
        UNIQUE(block_id, room_number)
    )
    """)

    # 4. Students
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        roll_no TEXT UNIQUE NOT NULL,
        department TEXT,
        year TEXT,
        gender TEXT,
        guardian_name TEXT,
        guardian_phone TEXT,
        address TEXT,
        room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL
    )
    """)

    # 5. Wardens
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wardens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        employee_id TEXT UNIQUE NOT NULL,
        assigned_block_id INTEGER REFERENCES blocks(id) ON DELETE SET NULL,
        designation TEXT DEFAULT 'Hostel Warden'
    )
    """)

    # 6. Outpasses
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS outpasses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pass_code TEXT UNIQUE NOT NULL,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        departure_date TEXT NOT NULL,
        departure_time TEXT NOT NULL,
        return_date TEXT NOT NULL,
        return_time TEXT NOT NULL,
        destination TEXT NOT NULL,
        reason TEXT NOT NULL,
        parent_contact TEXT,
        status TEXT DEFAULT 'Pending' CHECK(status IN ('Pending', 'Approved', 'Rejected', 'Completed')),
        warden_remarks TEXT,
        action_by INTEGER REFERENCES users(id),
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 7. Food Menus
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS food_menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day_of_week TEXT NOT NULL,
        meal_type TEXT NOT NULL CHECK(meal_type IN ('Breakfast', 'Lunch', 'Snacks', 'Dinner')),
        items TEXT NOT NULL,
        timings TEXT NOT NULL,
        special_note TEXT,
        UNIQUE(day_of_week, meal_type)
    )
    """)

    # 8. Food Feedbacks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS food_feedbacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        meal_date TEXT NOT NULL,
        meal_type TEXT NOT NULL,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 9. Complaints
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_number TEXT UNIQUE NOT NULL,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        category TEXT NOT NULL CHECK(category IN ('Food', 'Room maintenance', 'Electricity', 'Water', 'Cleanliness', 'Other issues')),
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        room_number TEXT,
        priority TEXT DEFAULT 'Medium' CHECK(priority IN ('Low', 'Medium', 'High', 'Urgent')),
        status TEXT DEFAULT 'Pending' CHECK(status IN ('Pending', 'In Progress', 'Resolved')),
        resolution_notes TEXT,
        resolved_by INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP
    )
    """)

    # 10. Announcements
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        priority TEXT DEFAULT 'Normal' CHECK(priority IN ('Urgent', 'Important', 'Normal')),
        category TEXT DEFAULT 'General' CHECK(category IN ('Hostel Rules', 'Mess & Food', 'Maintenance', 'Events', 'General')),
        posted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 11. Notifications
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        type TEXT DEFAULT 'general',
        link TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Check if admin user exists; if not, seed complete dataset
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    if count == 0:
        seed_sample_data(cursor)

    conn.commit()
    conn.close()

def seed_sample_data(cursor):
    """Seed sample data for blocks, rooms, users, menus, outpasses, and complaints."""
    print("Seeding initial SmartStay demo data...")

    # Passwords hashed with werkzeug
    admin_pw = generate_password_hash("admin123")
    warden_pw = generate_password_hash("warden123")
    student_pw = generate_password_hash("student123")

    # 1. Blocks
    blocks_data = [
        ("Block A (Ramanujan Hall)", "Boys", 4, "Undergraduate boys hostel with Wi-Fi, gym, and courtyard."),
        ("Block B (Kalpana Chawla Hall)", "Girls", 4, "Undergraduate girls hostel with study lounge and indoor games."),
        ("Block C (Aryabhata Wing)", "Boys", 3, "Senior and postgraduate hostel wing with single and double rooms.")
    ]
    cursor.executemany("INSERT INTO blocks (name, gender_type, total_floors, description) VALUES (?, ?, ?, ?)", blocks_data)
    block_a_id = 1
    block_b_id = 2
    block_c_id = 3

    # 2. Rooms
    rooms_data = [
        # Block A Rooms
        (block_a_id, "A-101", 1, 2, "Double AC", "Occupied"),
        (block_a_id, "A-102", 1, 3, "Triple Sharing", "Available"),
        (block_a_id, "A-105", 1, 2, "Double Non-AC", "Occupied"),
        (block_a_id, "A-201", 2, 2, "Double AC", "Available"),
        (block_a_id, "A-204", 2, 2, "Double AC", "Occupied"),
        (block_a_id, "A-301", 3, 1, "Single Deluxe", "Available"),
        # Block B Rooms
        (block_b_id, "B-101", 1, 2, "Double AC", "Available"),
        (block_b_id, "B-102", 1, 2, "Double AC", "Occupied"),
        (block_b_id, "B-201", 2, 3, "Triple Sharing", "Available"),
        (block_b_id, "B-205", 2, 2, "Double Non-AC", "Occupied"),
        # Block C Rooms
        (block_c_id, "C-101", 1, 1, "Single AC", "Available"),
        (block_c_id, "C-201", 2, 2, "Double AC", "Available")
    ]
    cursor.executemany("INSERT INTO rooms (block_id, room_number, floor, capacity, type, status) VALUES (?, ?, ?, ?, ?, ?)", rooms_data)
    room_a204_id = 5
    room_b102_id = 8
    room_a105_id = 3

    # 3. Users: Admin, Wardens, Students
    users_data = [
        # Admin
        ("admin", "admin@smartstay.com", admin_pw, "admin", "Dr. Ramesh Verma", "+91 98765 43210", "avatar_admin.png"),
        # Wardens
        ("warden", "warden@smartstay.com", warden_pw, "warden", "Mr. Rajesh Sharma", "+91 98230 11223", "avatar_warden1.png"),
        ("warden_priya", "priya.warden@smartstay.com", warden_pw, "warden", "Dr. Priya Nair", "+91 98230 44556", "avatar_warden2.png"),
        # Students
        ("student", "student@smartstay.com", student_pw, "student", "Aarav Mehta", "+91 91234 56789", "avatar_student1.png"),
        ("sneha", "sneha.patel@smartstay.com", student_pw, "student", "Sneha Patel", "+91 92345 67890", "avatar_student2.png"),
        ("rahul", "rahul.verma@smartstay.com", student_pw, "student", "Rahul Verma", "+91 93456 78901", "avatar_student3.png"),
        ("karan", "karan.malhotra@smartstay.com", student_pw, "student", "Karan Malhotra", "+91 94567 89012", "avatar_student4.png")
    ]
    cursor.executemany("""
        INSERT INTO users (username, email, password_hash, role, full_name, phone, avatar)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, users_data)

    admin_user_id = 1
    warden1_user_id = 2
    warden2_user_id = 3
    student1_user_id = 4
    student2_user_id = 5
    student3_user_id = 6
    student4_user_id = 7

    # 4. Wardens details
    wardens_data = [
        (warden1_user_id, "EMP-WRD-001", block_a_id, "Senior Hostel Warden"),
        (warden2_user_id, "EMP-WRD-002", block_b_id, "Associate Hostel Warden")
    ]
    cursor.executemany("INSERT INTO wardens (user_id, employee_id, assigned_block_id, designation) VALUES (?, ?, ?, ?)", wardens_data)

    # 5. Students details
    students_data = [
        (student1_user_id, "2024CS108", "Computer Science & Engineering", "3rd Year", "Male", "Mr. Suresh Mehta", "+91 98111 22334", "Flat 402, Green Valley Apts, Pune", room_a204_id),
        (student2_user_id, "2024EC215", "Electronics & Communication", "2nd Year", "Female", "Mrs. Sunita Patel", "+91 98222 33445", "12 Lotus Residency, Ahmedabad", room_b102_id),
        (student3_user_id, "2023ME044", "Mechanical Engineering", "4th Year", "Male", "Mr. Vinod Verma", "+91 98333 44556", "77 Civil Lines, Jaipur", room_a105_id),
        (student4_user_id, "2024CS112", "Computer Science & Engineering", "3rd Year", "Male", "Mr. Anand Malhotra", "+91 98444 55667", "501 Skyline Towers, Mumbai", room_a204_id)
    ]
    cursor.executemany("""
        INSERT INTO students (user_id, roll_no, department, year, gender, guardian_name, guardian_phone, address, room_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, students_data)

    student1_id = 1  # Aarav
    student2_id = 2  # Sneha
    student3_id = 3  # Rahul

    # 6. Weekly Food Menus (Mon to Sun, 4 meals each)
    food_timetable = [
        # Monday
        ("Monday", "Breakfast", "Masala Dosa, Sambar, Coconut Chutney, Boiled Eggs / Banana, Tea & Coffee", "07:30 AM - 09:30 AM", "South Indian Special"),
        ("Monday", "Lunch", "Jeera Rice, Dal Tadka, Paneer Butter Masala, Roti, Fresh Salad, Curd", "12:30 PM - 02:30 PM", "Nutritious balanced lunch"),
        ("Monday", "Snacks", "Vegetable Samosa with Mint Chutney, Biscuits, Hot Tea & Coffee", "05:00 PM - 06:15 PM", "Evening refreshment"),
        ("Monday", "Dinner", "Steamed Basmati Rice, Veg Kadhai, Rajma Curry, Phulka, Gulab Jamun", "07:30 PM - 09:30 PM", "Sweet treat included"),
        # Tuesday
        ("Tuesday", "Breakfast", "Aloo Paratha with Butter, Curd, Pickle, Seasonal Fruits, Milk & Tea", "07:30 AM - 09:30 AM", "North Indian favourite"),
        ("Tuesday", "Lunch", "Veg Biryani with Raita, Chana Masala, Chapati, Papad, Green Salad", "12:30 PM - 02:30 PM", "Aromatic Biryani Feast"),
        ("Tuesday", "Snacks", "Poha with Roasted Peanuts & Sev, Masala Chai, Green Tea", "05:00 PM - 06:15 PM", "Light healthy snack"),
        ("Tuesday", "Dinner", "Matar Paneer, Yellow Moong Dal, Steamed Rice, Tandoori Roti, Kheer", "07:30 PM - 09:30 PM", "Classic dinner"),
        # Wednesday
        ("Wednesday", "Breakfast", "Idli Vada with Sambar, Tomato Chutney, Boiled Sprouts, Coffee", "07:30 AM - 09:30 AM", "Steamed healthy breakfast"),
        ("Wednesday", "Lunch", "Kashmiri Pulao, Palak Corn, Dal Makhani, Butter Naan, Boondi Raita", "12:30 PM - 02:30 PM", "Rich gravy lunch"),
        ("Wednesday", "Snacks", "Bread Pakora with Sweet Tamarind Chutney, Ginger Tea", "05:00 PM - 06:15 PM", "Crispy evening treat"),
        ("Wednesday", "Dinner", "Egg Curry / Malai Kofta, Jeera Rice, Tawa Roti, Dal Fry, Ice Cream", "07:30 PM - 09:30 PM", "Special Mid-week dinner"),
        # Thursday
        ("Thursday", "Breakfast", "Puri Bhaji (Aloo Curry), Halwa, Cut Fruits, Tea & Filter Coffee", "07:30 AM - 09:30 AM", "Traditional Indian breakfast"),
        ("Thursday", "Lunch", "Plain Rice, Sambhar, Bhindi Masala, Lemon Rasam, Appalam, Curd", "12:30 PM - 02:30 PM", "Wholesome South Indian Thali"),
        ("Thursday", "Snacks", "Mix Veg Cutlet, Tomato Ketchup, Cardamom Chai", "05:00 PM - 06:15 PM", "Golden crispy cutlets"),
        ("Thursday", "Dinner", "Soyabean Chaap Curry, Dal Panchmel, Phulka, Peas Pulao, Rasgulla", "07:30 PM - 09:30 PM", "High protein dinner"),
        # Friday
        ("Friday", "Breakfast", "Upma with Coconut Chutney, Boiled Eggs / Banana, Cornflakes & Milk", "07:30 AM - 09:30 AM", "Light and energetic start"),
        ("Friday", "Lunch", "Hyderabadi Veg Dum Biryani, Mirchi ka Salan, Onion Raita, Parotta", "12:30 PM - 02:30 PM", "Friday Special Biryani"),
        ("Friday", "Snacks", "Onion Bhajiya (Pakoda), Fried Green Chilies, Hot Cutting Chai", "05:00 PM - 06:15 PM", "Monsoon style snack"),
        ("Friday", "Dinner", "Shahi Paneer, Dal Tadka, Ghee Rice, Garlic Naan, Moong Dal Halwa", "07:30 PM - 09:30 PM", "Royal weekend welcome"),
        # Saturday
        ("Saturday", "Breakfast", "Uttapam with Sambar & Podi, Boiled Eggs, Fresh Papaya, Tea", "07:30 AM - 09:30 AM", "Crispy uttapams"),
        ("Saturday", "Lunch", "Rajma Chawal Special, Aloo Gobi Roast, Pickle, Papad, Fresh Dahi", "12:30 PM - 02:30 PM", "Comfort food Saturday"),
        ("Saturday", "Snacks", "White Sauce Pasta / Veg Sandwich, Cold Coffee / Hot Tea", "05:00 PM - 06:15 PM", "Cafe style weekend snack"),
        ("Saturday", "Dinner", "Chole Bhature with Pickled Onions, Mint Chutney, Gulab Jamun", "07:30 PM - 09:30 PM", "Weekend Feast"),
        # Sunday
        ("Sunday", "Breakfast", "Chole Kulche / Veg Club Sandwich, Boiled Eggs, Orange Juice, Coffee", "08:00 AM - 10:00 AM", "Late Sunday Brunch menu"),
        ("Sunday", "Lunch", "Paneer Tikka Masala / Chicken Curry (Optional), Veg Pulao, Naan, Ice Cream", "12:30 PM - 02:30 PM", "Grand Sunday Lunch"),
        ("Sunday", "Snacks", "Veg Momos with Spicy Dip, Masala Chai, Cookies", "05:00 PM - 06:15 PM", "Evening chill treat"),
        ("Sunday", "Dinner", "Khichdi & Kadhi, Aloo Jeera, Roasted Papad, Masala Buttermilk", "07:30 PM - 09:30 PM", "Light detox comfort dinner")
    ]
    cursor.executemany("""
        INSERT INTO food_menus (day_of_week, meal_type, items, timings, special_note)
        VALUES (?, ?, ?, ?, ?)
    """, food_timetable)

    # 7. Food Feedbacks
    today_str = datetime.date.today().isoformat()
    yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    cursor.execute("""
        INSERT INTO food_feedbacks (student_id, meal_date, meal_type, rating, comment)
        VALUES 
        (?, ?, 'Lunch', 5, 'The Paneer Butter Masala was rich and flavourful! Rotis were hot and soft.'),
        (?, ?, 'Breakfast', 4, 'Crispy dosas with great sambar. Coconut chutney could have a pinch more salt.')
    """, (student1_id, today_str, student2_id, yesterday_str))

    # 8. Outpasses
    outpasses_data = [
        ("SS-OP-2026-101", student1_id, today_str, "17:30", (datetime.date.today() + datetime.timedelta(days=2)).isoformat(), "20:00", "Pune (Home)", "Sister's engagement ceremony and family gathering.", "+91 98111 22334", "Pending", None, None),
        ("SS-OP-2026-098", student1_id, (datetime.date.today() - datetime.timedelta(days=5)).isoformat(), "08:00", (datetime.date.today() - datetime.timedelta(days=3)).isoformat(), "21:00", "IIT Bombay Techfest", "Representing college in National Robotics Hackathon.", "+91 98111 22334", "Completed", "Approved for technical competition. Returned safely on time.", warden1_user_id),
        ("SS-OP-2026-089", student2_id, (datetime.date.today() + datetime.timedelta(days=1)).isoformat(), "14:00", (datetime.date.today() + datetime.timedelta(days=1)).isoformat(), "20:30", "City General Hospital", "Routine dental checkup and consultation.", "+91 98222 33445", "Approved", "Emergency contact verified with mother.", warden2_user_id),
        ("SS-OP-2026-077", student3_id, (datetime.date.today() - datetime.timedelta(days=2)).isoformat(), "22:00", (datetime.date.today() - datetime.timedelta(days=1)).isoformat(), "04:00", "Downtown Club", "Night out with school friends.", "+91 98333 44556", "Rejected", "Late night outing without guardian prior consent is against hostel bylaws.", warden1_user_id)
    ]
    cursor.executemany("""
        INSERT INTO outpasses (pass_code, student_id, departure_date, departure_time, return_date, return_time, destination, reason, parent_contact, status, warden_remarks, action_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, outpasses_data)

    # 9. Complaints
    complaints_data = [
        ("TKT-2026-001", student1_id, "Electricity", "Ceiling Fan Regulator Malfunctioning", "The ceiling fan in Room A-204 runs only at maximum speed. Regulator knob is loose and making clicking sparks.", "A-204", "Medium", "In Progress", "Electrician assigned; parts requested from store.", warden1_user_id),
        ("TKT-2026-002", student1_id, "Water", "Hot Water Geyser Low Pressure in 2nd Floor", "The hot water supply geyser in Block A second floor washroom has very low flow and takes 25 mins to warm up.", "A-204", "Urgent", "Pending", None, None),
        ("TKT-2026-003", student2_id, "Cleanliness", "Study Hall Balcony Cleaning Required", "Dried leaves and dust accumulated on the second floor study room balcony after recent windy weather.", "B-102", "Low", "Resolved", "Housekeeping team completed deep cleaning on Thursday morning.", warden2_user_id),
        ("TKT-2026-004", student3_id, "Food", "Dinner Chapati Quantity & Softness", "On Wednesday night chapatis were slightly dry and ran out briefly at 8:45 PM.", "A-105", "Medium", "Resolved", "Mess supervisor notified; additional buffer prepared for peak hours.", warden1_user_id)
    ]
    cursor.executemany("""
        INSERT INTO complaints (ticket_number, student_id, category, title, description, room_number, priority, status, resolution_notes, resolved_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, complaints_data)

    # 10. Announcements
    announcements_data = [
        ("Annual Hostel Fest 'Resonance 2026' Dates Announced!", "We are thrilled to announce that our annual inter-hostel cultural and sports fest 'Resonance 2026' will take place next month from Nov 14th to 16th. Registrations for cricket, futsal, debate, and music battle are now open in the student portal.", "Important", "Events", admin_user_id),
        ("Water Tank Disinfection & Maintenance on Sunday", "Routine solar water heating and storage tank chemical cleaning is scheduled this Sunday between 08:00 AM and 12:30 PM. Hot water supply will be suspended during these hours. Cold water remains unaffected.", "Urgent", "Maintenance", warden1_user_id),
        ("Revised Mess Timings for Examination Month", "To accommodate late night study schedules, breakfast will be extended by 30 minutes on weekends and hot Bournvita / milk will be served in the mess lobby at 10:30 PM.", "Normal", "Mess & Food", admin_user_id),
        ("Strict Curfew and Gate Biometric Policy Reminder", "All resident students must punch in before 09:30 PM unless holding an authorized outpass verified by the block warden. Unapproved absences will be escalated to department heads.", "Important", "Hostel Rules", warden1_user_id)
    ]
    cursor.executemany("""
        INSERT INTO announcements (title, content, priority, category, posted_by)
        VALUES (?, ?, ?, ?, ?)
    """, announcements_data)

    # 11. Notifications
    notifications_data = [
        (student1_user_id, "Outpass Submitted", "Your outpass request SS-OP-2026-101 has been sent to Warden Rajesh Sharma for approval.", "outpass", "/outpass", 0),
        (student1_user_id, "Complaint In Progress", "Ticket TKT-2026-001 (Fan Regulator) status changed to 'In Progress'.", "complaint", "/complaints", 0),
        (student1_user_id, "New Announcement", "Water Tank Disinfection & Maintenance on Sunday.", "announcement", "/announcements", 1),
        (warden1_user_id, "New Outpass Request", "Student Aarav Mehta (Room A-204) applied for a 2-day home outpass.", "outpass", "/warden/dashboard", 0),
        (admin_user_id, "Monthly Room Occupancy Report", "Block A occupancy is currently at 88%. 4 rooms available for allocation.", "room", "/admin/dashboard", 0)
    ]
    cursor.executemany("""
        INSERT INTO notifications (user_id, title, message, type, link, is_read)
        VALUES (?, ?, ?, ?, ?, ?)
    """, notifications_data)

    print("Sample SmartStay data seeded successfully!")

# -------------------------------------------------------------
# Authentication Routes
# -------------------------------------------------------------
@app.route('/')
def index():
    """Home landing route redirecting based on authentication state."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login with role detection, demo account quick fills, and session setup."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        login_identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()
        requested_role = request.form.get('role', '').strip()

        if not login_identifier or not password:
            flash('Please enter both username/email and password.', 'warning')
            return render_template('login.html')

        user = query_db("""
            SELECT * FROM users 
            WHERE (username = ? OR email = ?)
        """, [login_identifier, login_identifier], one=True)

        if user and check_password_hash(user['password_hash'], password):
            # If user explicitly selected role, verify it matches
            if requested_role and requested_role != user['role']:
                flash(f"Account exists, but it is registered as '{user['role'].capitalize()}', not '{requested_role.capitalize()}'.", 'warning')
                return render_template('login.html')

            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            session['email'] = user['email']

            flash(f"Welcome back, {user['full_name']}!", 'success')
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials. Please verify your username/email and password.', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Student self-registration portal."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    # Load available rooms for room selection
    available_rooms = query_db("""
        SELECT r.id, r.room_number, r.floor, r.type, b.name as block_name,
               (SELECT COUNT(*) FROM students s WHERE s.room_id = r.id) as current_occupants,
               r.capacity
        FROM rooms r
        JOIN blocks b ON r.block_id = b.id
        WHERE (SELECT COUNT(*) FROM students s WHERE s.room_id = r.id) < r.capacity
        ORDER BY b.name, r.room_number
    """)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        phone = request.form.get('phone', '').strip()
        roll_no = request.form.get('roll_no', '').strip()
        department = request.form.get('department', '').strip()
        year = request.form.get('year', '').strip()
        gender = request.form.get('gender', '').strip()
        guardian_name = request.form.get('guardian_name', '').strip()
        guardian_phone = request.form.get('guardian_phone', '').strip()
        address = request.form.get('address', '').strip()
        room_id = request.form.get('room_id')

        # Form validations
        if not (username and email and full_name and password and roll_no):
            flash('All primary fields marked with an asterisk are required.', 'danger')
            return render_template('register.html', rooms=available_rooms)

        if password != confirm_password:
            flash('Passwords do not match. Please try again.', 'danger')
            return render_template('register.html', rooms=available_rooms)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('register.html', rooms=available_rooms)

        # Check existing username/email/roll_no
        existing_user = query_db("SELECT id FROM users WHERE username = ? OR email = ?", [username, email], one=True)
        if existing_user:
            flash('Username or Email already registered. Please login or use a different one.', 'warning')
            return render_template('register.html', rooms=available_rooms)

        existing_roll = query_db("SELECT id FROM students WHERE roll_no = ?", [roll_no], one=True)
        if existing_roll:
            flash(f'Roll Number {roll_no} is already assigned to a registered student.', 'warning')
            return render_template('register.html', rooms=available_rooms)

        # Insert user and student record
        pw_hash = generate_password_hash(password)
        new_user_id = execute_db("""
            INSERT INTO users (username, email, password_hash, role, full_name, phone, avatar)
            VALUES (?, ?, ?, 'student', ?, ?, 'avatar_student1.png')
        """, [username, email, pw_hash, full_name, phone])

        selected_room_id = int(room_id) if room_id and room_id.isdigit() else None
        execute_db("""
            INSERT INTO students (user_id, roll_no, department, year, gender, guardian_name, guardian_phone, address, room_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [new_user_id, roll_no, department, year, gender, guardian_name, guardian_phone, address, selected_room_id])

        # Welcome notification
        execute_db("""
            INSERT INTO notifications (user_id, title, message, type, link)
            VALUES (?, 'Welcome to SmartStay!', 'Your hostel resident account is now active. You can apply for outpasses and view the daily food timetable.', 'general', '/student/dashboard')
        """, [new_user_id])

        flash('Registration successful! Please log in with your credentials.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', rooms=available_rooms)

@app.route('/logout')
def logout():
    """Clear session and log user out."""
    session.clear()
    flash('You have been logged out securely.', 'info')
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """View and update personal profile details or update password."""
    user = query_db("SELECT * FROM users WHERE id = ?", [session['user_id']], one=True)
    student = None
    warden = None

    if user['role'] == 'student':
        student = query_db("""
            SELECT s.*, r.room_number, r.floor, r.type as room_type, b.name as block_name
            FROM students s
            LEFT JOIN rooms r ON s.room_id = r.id
            LEFT JOIN blocks b ON r.block_id = b.id
            WHERE s.user_id = ?
        """, [user['id']], one=True)
    elif user['role'] == 'warden':
        warden = query_db("""
            SELECT w.*, b.name as block_name
            FROM wardens w
            LEFT JOIN blocks b ON w.assigned_block_id = b.id
            WHERE w.user_id = ?
        """, [user['id']], one=True)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_info':
            full_name = request.form.get('full_name', '').strip()
            phone = request.form.get('phone', '').strip()

            execute_db("UPDATE users SET full_name = ?, phone = ? WHERE id = ?", [full_name, phone, user['id']])
            session['full_name'] = full_name

            if user['role'] == 'student' and student:
                guardian_name = request.form.get('guardian_name', '').strip()
                guardian_phone = request.form.get('guardian_phone', '').strip()
                address = request.form.get('address', '').strip()
                department = request.form.get('department', '').strip()
                year = request.form.get('year', '').strip()

                execute_db("""
                    UPDATE students 
                    SET guardian_name = ?, guardian_phone = ?, address = ?, department = ?, year = ?
                    WHERE user_id = ?
                """, [guardian_name, guardian_phone, address, department, year, user['id']])

            flash('Profile details updated successfully.', 'success')
            return redirect(url_for('profile'))

        elif action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')

            if not check_password_hash(user['password_hash'], current_pw):
                flash('Current password is incorrect.', 'danger')
            elif new_pw != confirm_pw:
                flash('New passwords do not match.', 'danger')
            elif len(new_pw) < 6:
                flash('New password must be at least 6 characters long.', 'danger')
            else:
                new_hash = generate_password_hash(new_pw)
                execute_db("UPDATE users SET password_hash = ? WHERE id = ?", [new_hash, user['id']])
                flash('Password updated successfully! Please keep it secure.', 'success')
            return redirect(url_for('profile'))

    return render_template('profile.html', user=user, student=student, warden=warden)

# -------------------------------------------------------------
# Main Dashboard Hub
# -------------------------------------------------------------
@app.route('/dashboard')
@login_required
def dashboard():
    """Redirect to role-specific dashboard."""
    role = session.get('role')
    if role == 'student':
        return redirect(url_for('student_dashboard'))
    elif role == 'warden':
        return redirect(url_for('warden_dashboard'))
    elif role == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))

# -------------------------------------------------------------
# 1. Student Dashboard
# -------------------------------------------------------------
@app.route('/student/dashboard')
@login_required
@role_required(['student'])
def student_dashboard():
    """Rich student dashboard featuring profile, room, active outpass, menu, complaints & announcements."""
    user_id = session['user_id']
    student = query_db("""
        SELECT s.*, r.room_number, r.floor, r.type as room_type, r.capacity, b.name as block_name
        FROM students s
        LEFT JOIN rooms r ON s.room_id = r.id
        LEFT JOIN blocks b ON r.block_id = b.id
        WHERE s.user_id = ?
    """, [user_id], one=True)

    if not student:
        flash("Student profile record not found.", "danger")
        return redirect(url_for('login'))

    # Roommates list
    roommates = []
    if student['room_id']:
        roommates = query_db("""
            SELECT u.full_name, u.phone, s.roll_no, s.department, s.year
            FROM students s
            JOIN users u ON s.user_id = u.id
            WHERE s.room_id = ? AND s.id != ?
        """, [student['room_id'], student['id']])

    # Outpasses
    outpass_stats = {
        'total': query_db("SELECT COUNT(*) as c FROM outpasses WHERE student_id = ?", [student['id']], one=True)['c'],
        'approved': query_db("SELECT COUNT(*) as c FROM outpasses WHERE student_id = ? AND status = 'Approved'", [student['id']], one=True)['c'],
        'pending': query_db("SELECT COUNT(*) as c FROM outpasses WHERE student_id = ? AND status = 'Pending'", [student['id']], one=True)['c'],
        'completed': query_db("SELECT COUNT(*) as c FROM outpasses WHERE student_id = ? AND status = 'Completed'", [student['id']], one=True)['c'],
    }
    recent_outpasses = query_db("""
        SELECT * FROM outpasses 
        WHERE student_id = ? 
        ORDER BY applied_at DESC LIMIT 5
    """, [student['id']])

    latest_active_outpass = query_db("""
        SELECT * FROM outpasses 
        WHERE student_id = ? AND status IN ('Pending', 'Approved')
        ORDER BY applied_at DESC LIMIT 1
    """, [student['id']], one=True)

    # Today's Food Menu
    days_map = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    today_day = days_map[datetime.date.today().weekday()]
    today_meals = query_db("""
        SELECT * FROM food_menus 
        WHERE day_of_week = ? 
        ORDER BY CASE meal_type 
            WHEN 'Breakfast' THEN 1 
            WHEN 'Lunch' THEN 2 
            WHEN 'Snacks' THEN 3 
            WHEN 'Dinner' THEN 4 
        END
    """, [today_day])

    # Complaints
    recent_complaints = query_db("""
        SELECT * FROM complaints 
        WHERE student_id = ? 
        ORDER BY created_at DESC LIMIT 4
    """, [student['id']])

    # Announcements
    announcements = query_db("""
        SELECT a.*, u.full_name as author_name 
        FROM announcements a
        LEFT JOIN users u ON a.posted_by = u.id
        ORDER BY a.created_at DESC LIMIT 4
    """)

    return render_template(
        'student_dashboard.html',
        student=student,
        roommates=roommates,
        outpass_stats=outpass_stats,
        recent_outpasses=recent_outpasses,
        latest_active_outpass=latest_active_outpass,
        today_day=today_day,
        today_meals=today_meals,
        recent_complaints=recent_complaints,
        announcements=announcements
    )

# -------------------------------------------------------------
# 2. Warden Dashboard
# -------------------------------------------------------------
@app.route('/warden/dashboard')
@login_required
@role_required(['warden', 'admin'])
def warden_dashboard():
    """Warden oversight dashboard with fast action queue, stats, chart analytics, and recent activity."""
    user_id = session['user_id']
    warden = query_db("""
        SELECT w.*, b.name as block_name, b.id as block_id
        FROM wardens w
        LEFT JOIN blocks b ON w.assigned_block_id = b.id
        WHERE w.user_id = ?
    """, [user_id], one=True)

    # Key metrics
    total_students = query_db("SELECT COUNT(*) as c FROM students", one=True)['c']
    total_rooms = query_db("SELECT COUNT(*) as c FROM rooms", one=True)['c']
    pending_outpasses = query_db("SELECT COUNT(*) as c FROM outpasses WHERE status = 'Pending'", one=True)['c']
    approved_outpasses = query_db("SELECT COUNT(*) as c FROM outpasses WHERE status = 'Approved'", one=True)['c']
    rejected_outpasses = query_db("SELECT COUNT(*) as c FROM outpasses WHERE status = 'Rejected'", one=True)['c']
    completed_outpasses = query_db("SELECT COUNT(*) as c FROM outpasses WHERE status = 'Completed'", one=True)['c']
    open_complaints = query_db("SELECT COUNT(*) as c FROM complaints WHERE status != 'Resolved'", one=True)['c']

    # Total occupied beds
    occupied_beds = query_db("SELECT COUNT(*) as c FROM students WHERE room_id IS NOT NULL", one=True)['c']
    total_capacity = query_db("SELECT COALESCE(SUM(capacity), 0) as c FROM rooms", one=True)['c']
    occupancy_rate = round((occupied_beds / total_capacity * 100), 1) if total_capacity > 0 else 0

    # Pending outpasses queue for fast action
    pending_outpass_list = query_db("""
        SELECT o.*, u.full_name as student_name, s.roll_no, r.room_number, b.name as block_name, u.phone as student_phone
        FROM outpasses o
        JOIN students s ON o.student_id = s.id
        JOIN users u ON s.user_id = u.id
        LEFT JOIN rooms r ON s.room_id = r.id
        LEFT JOIN blocks b ON r.block_id = b.id
        WHERE o.status = 'Pending'
        ORDER BY o.applied_at ASC LIMIT 6
    """)

    # Recent complaints
    recent_complaints = query_db("""
        SELECT c.*, u.full_name as student_name, s.roll_no
        FROM complaints c
        JOIN students s ON c.student_id = s.id
        JOIN users u ON s.user_id = u.id
        ORDER BY CASE c.priority 
            WHEN 'Urgent' THEN 1 
            WHEN 'High' THEN 2 
            WHEN 'Medium' THEN 3 
            WHEN 'Low' THEN 4 
        END, c.created_at DESC LIMIT 5
    """)

    # Recent hostel activity feed (combined from outpasses, complaints, announcements)
    recent_activities = query_db("""
        SELECT 'outpass' as act_type, o.status as act_status, u.full_name as title, o.destination as subtitle, o.updated_at as event_time
        FROM outpasses o
        JOIN students s ON o.student_id = s.id
        JOIN users u ON s.user_id = u.id
        UNION ALL
        SELECT 'complaint' as act_type, c.status as act_status, c.title as title, c.category as subtitle, c.created_at as event_time
        FROM complaints c
        UNION ALL
        SELECT 'announcement' as act_type, a.priority as act_status, a.title as title, a.category as subtitle, a.created_at as event_time
        FROM announcements a
        ORDER BY event_time DESC LIMIT 8
    """)

    return render_template(
        'warden_dashboard.html',
        warden=warden,
        total_students=total_students,
        total_rooms=total_rooms,
        pending_outpasses=pending_outpasses,
        approved_outpasses=approved_outpasses,
        rejected_outpasses=rejected_outpasses,
        completed_outpasses=completed_outpasses,
        open_complaints=open_complaints,
        occupied_beds=occupied_beds,
        total_capacity=total_capacity,
        occupancy_rate=occupancy_rate,
        pending_outpass_list=pending_outpass_list,
        recent_complaints=recent_complaints,
        recent_activities=recent_activities
    )

# -------------------------------------------------------------
# 3. Admin Dashboard
# -------------------------------------------------------------
@app.route('/admin/dashboard')
@login_required
@role_required(['admin'])
def admin_dashboard():
    """Admin Master Dashboard with full system management, stats, analytics charts, and administrative controls."""
    # System KPIs
    total_students = query_db("SELECT COUNT(*) as c FROM students", one=True)['c']
    total_wardens = query_db("SELECT COUNT(*) as c FROM wardens", one=True)['c']
    total_blocks = query_db("SELECT COUNT(*) as c FROM blocks", one=True)['c']
    total_rooms = query_db("SELECT COUNT(*) as c FROM rooms", one=True)['c']
    total_capacity = query_db("SELECT COALESCE(SUM(capacity), 0) as c FROM rooms", one=True)['c']
    allocated_students = query_db("SELECT COUNT(*) as c FROM students WHERE room_id IS NOT NULL", one=True)['c']
    unallocated_students = total_students - allocated_students
    total_outpasses = query_db("SELECT COUNT(*) as c FROM outpasses", one=True)['c']
    total_complaints = query_db("SELECT COUNT(*) as c FROM complaints", one=True)['c']
    resolved_complaints = query_db("SELECT COUNT(*) as c FROM complaints WHERE status = 'Resolved'", one=True)['c']

    # Block breakdown table
    blocks_summary = query_db("""
        SELECT b.id, b.name, b.gender_type, b.total_floors,
               COUNT(DISTINCT r.id) as room_count,
               COALESCE(SUM(r.capacity), 0) as total_bed_capacity,
               (SELECT COUNT(*) FROM students s JOIN rooms rm ON s.room_id = rm.id WHERE rm.block_id = b.id) as current_occupancy
        FROM blocks b
        LEFT JOIN rooms r ON b.id = r.block_id
        GROUP BY b.id
    """)

    # Wardens list
    wardens_list = query_db("""
        SELECT w.*, u.full_name, u.email, u.phone, b.name as block_name
        FROM wardens w
        JOIN users u ON w.user_id = u.id
        LEFT JOIN blocks b ON w.assigned_block_id = b.id
    """)

    # Recent student registrations
    recent_students = query_db("""
        SELECT s.*, u.full_name, u.email, u.phone, r.room_number, b.name as block_name
        FROM students s
        JOIN users u ON s.user_id = u.id
        LEFT JOIN rooms r ON s.room_id = r.id
        LEFT JOIN blocks b ON r.block_id = b.id
        ORDER BY s.id DESC LIMIT 6
    """)

    return render_template(
        'admin_dashboard.html',
        total_students=total_students,
        total_wardens=total_wardens,
        total_blocks=total_blocks,
        total_rooms=total_rooms,
        total_capacity=total_capacity,
        allocated_students=allocated_students,
        unallocated_students=unallocated_students,
        total_outpasses=total_outpasses,
        total_complaints=total_complaints,
        resolved_complaints=resolved_complaints,
        blocks_summary=blocks_summary,
        wardens_list=wardens_list,
        recent_students=recent_students
    )

# -------------------------------------------------------------
# 4. Outpass Management
# -------------------------------------------------------------
@app.route('/outpass')
@login_required
def outpass():
    """Unified Outpass page: student application & history, or Warden/Admin approval management."""
    role = session['role']
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('search', '').strip()

    if role == 'student':
        student = query_db("SELECT * FROM students WHERE user_id = ?", [session['user_id']], one=True)
        if not student:
            flash("Student profile not found.", "danger")
            return redirect(url_for('dashboard'))

        query = "SELECT * FROM outpasses WHERE student_id = ?"
        params = [student['id']]
        if status_filter != 'all':
            query += " AND status = ?"
            params.append(status_filter)
        query += " ORDER BY applied_at DESC"
        outpasses_list = query_db(query, params)

        return render_template('outpass.html', outpasses=outpasses_list, status_filter=status_filter, student=student)

    else:
        # Warden / Admin view
        query = """
            SELECT o.*, u.full_name as student_name, s.roll_no, s.department, r.room_number, b.name as block_name,
                   act_user.full_name as action_by_name
            FROM outpasses o
            JOIN students s ON o.student_id = s.id
            JOIN users u ON s.user_id = u.id
            LEFT JOIN rooms r ON s.room_id = r.id
            LEFT JOIN blocks b ON r.block_id = b.id
            LEFT JOIN users act_user ON o.action_by = act_user.id
            WHERE 1=1
        """
        params = []
        if status_filter != 'all':
            query += " AND o.status = ?"
            params.append(status_filter)

        if search_query:
            query += " AND (u.full_name LIKE ? OR s.roll_no LIKE ? OR o.pass_code LIKE ? OR o.destination LIKE ?)"
            term = f"%{search_query}%"
            params.extend([term, term, term, term])

        query += " ORDER BY CASE o.status WHEN 'Pending' THEN 1 WHEN 'Approved' THEN 2 WHEN 'Completed' THEN 3 ELSE 4 END, o.applied_at DESC"
        outpasses_list = query_db(query, params)

        # Quick stats for header
        stats = {
            'pending': query_db("SELECT COUNT(*) as c FROM outpasses WHERE status = 'Pending'", one=True)['c'],
            'approved': query_db("SELECT COUNT(*) as c FROM outpasses WHERE status = 'Approved'", one=True)['c'],
            'rejected': query_db("SELECT COUNT(*) as c FROM outpasses WHERE status = 'Rejected'", one=True)['c'],
            'completed': query_db("SELECT COUNT(*) as c FROM outpasses WHERE status = 'Completed'", one=True)['c'],
        }

        return render_template(
            'outpass.html',
            outpasses=outpasses_list,
            status_filter=status_filter,
            search_query=search_query,
            stats=stats
        )

@app.route('/api/outpass/apply', methods=['POST'])
@login_required
@role_required(['student'])
def apply_outpass():
    """Apply for new student digital outpass."""
    student = query_db("SELECT * FROM students WHERE user_id = ?", [session['user_id']], one=True)
    if not student:
        return jsonify({'success': False, 'message': 'Student profile not found.'}), 400

    departure_date = request.form.get('departure_date')
    departure_time = request.form.get('departure_time')
    return_date = request.form.get('return_date')
    return_time = request.form.get('return_time')
    destination = request.form.get('destination', '').strip()
    reason = request.form.get('reason', '').strip()
    parent_contact = request.form.get('parent_contact', '').strip() or student['guardian_phone']

    if not (departure_date and departure_time and return_date and return_time and destination and reason):
        return jsonify({'success': False, 'message': 'Please fill all required outpass details.'}), 400

    # Generate unique outpass code (e.g. SS-OP-2026-XXXX)
    random_digits = random.randint(1000, 9999)
    pass_code = f"SS-OP-2026-{random_digits}"

    outpass_id = execute_db("""
        INSERT INTO outpasses (pass_code, student_id, departure_date, departure_time, return_date, return_time, destination, reason, parent_contact, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
    """, [pass_code, student['id'], departure_date, departure_time, return_date, return_time, destination, reason, parent_contact])

    # Notify student
    execute_db("""
        INSERT INTO notifications (user_id, title, message, type, link)
        VALUES (?, 'Outpass Application Submitted', ?, 'outpass', '/outpass')
    """, [session['user_id'], f"Your outpass application {pass_code} to '{destination}' has been submitted and is pending warden approval."])

    # Notify wardens
    wardens = query_db("SELECT user_id FROM wardens")
    for w in wardens:
        execute_db("""
            INSERT INTO notifications (user_id, title, message, type, link)
            VALUES (?, 'New Outpass Request', ?, 'outpass', '/outpass')
        """, [w['user_id'], f"Student {session['full_name']} submitted outpass application {pass_code}."])

    return jsonify({'success': True, 'message': 'Outpass application submitted successfully!', 'pass_code': pass_code})

@app.route('/api/outpass/<int:outpass_id>/action', methods=['POST'])
@login_required
@role_required(['warden', 'admin'])
def action_outpass(outpass_id):
    """Approve or reject outpass application with warden remarks."""
    action = request.form.get('action') # 'approve' or 'reject'
    remarks = request.form.get('remarks', '').strip()

    outpass_item = query_db("""
        SELECT o.*, s.user_id as student_user_id, u.full_name as student_name
        FROM outpasses o
        JOIN students s ON o.student_id = s.id
        JOIN users u ON s.user_id = u.id
        WHERE o.id = ?
    """, [outpass_id], one=True)

    if not outpass_item:
        return jsonify({'success': False, 'message': 'Outpass not found.'}), 404

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if action == 'approve':
        status = 'Approved'
        remarks_text = remarks or "Approved by Hostel Warden."
        msg_title = "Outpass Approved!"
        msg_body = f"Your outpass {outpass_item['pass_code']} has been approved. You can now present your digital pass at the hostel gate."
    elif action == 'reject':
        status = 'Rejected'
        if not remarks:
            return jsonify({'success': False, 'message': 'A rejection reason is required.'}), 400
        remarks_text = remarks
        msg_title = "Outpass Rejected"
        msg_body = f"Your outpass {outpass_item['pass_code']} was rejected. Reason: {remarks_text}"
    else:
        return jsonify({'success': False, 'message': 'Invalid action requested.'}), 400

    execute_db("""
        UPDATE outpasses 
        SET status = ?, warden_remarks = ?, action_by = ?, updated_at = ?
        WHERE id = ?
    """, [status, remarks_text, session['user_id'], now_str, outpass_id])

    # Send notification to student
    execute_db("""
        INSERT INTO notifications (user_id, title, message, type, link)
        VALUES (?, ?, ?, 'outpass', '/outpass')
    """, [outpass_item['student_user_id'], msg_title, msg_body])

    return jsonify({'success': True, 'message': f'Outpass {status.lower()} successfully.', 'status': status})

@app.route('/api/outpass/<int:outpass_id>/complete', methods=['POST'])
@login_required
@role_required(['warden', 'admin'])
def complete_outpass(outpass_id):
    """Mark outpass completed once student checks back in to hostel."""
    outpass_item = query_db("""
        SELECT o.*, s.user_id as student_user_id, u.full_name as student_name
        FROM outpasses o
        JOIN students s ON o.student_id = s.id
        JOIN users u ON s.user_id = u.id
        WHERE o.id = ?
    """, [outpass_id], one=True)

    if not outpass_item:
        return jsonify({'success': False, 'message': 'Outpass not found.'}), 404

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_db("""
        UPDATE outpasses 
        SET status = 'Completed', updated_at = ?
        WHERE id = ?
    """, [now_str, outpass_id])

    execute_db("""
        INSERT INTO notifications (user_id, title, message, type, link)
        VALUES (?, 'Outpass Marked Completed', 'Student return logged at the hostel security desk. Pass status is now Completed.', 'outpass', '/outpass')
    """, [outpass_item['student_user_id']])

    return jsonify({'success': True, 'message': 'Student return logged. Outpass marked Completed.'})

@app.route('/api/outpass/<int:outpass_id>/details', methods=['GET'])
@login_required
def get_outpass_details(outpass_id):
    """Return JSON details for digital outpass pass modal and QR code render."""
    op = query_db("""
        SELECT o.*, u.full_name as student_name, s.roll_no, s.department, s.year,
               r.room_number, b.name as block_name,
               approver.full_name as approved_by_name
        FROM outpasses o
        JOIN students s ON o.student_id = s.id
        JOIN users u ON s.user_id = u.id
        LEFT JOIN rooms r ON s.room_id = r.id
        LEFT JOIN blocks b ON r.block_id = b.id
        LEFT JOIN users approver ON o.action_by = approver.id
        WHERE o.id = ?
    """, [outpass_id], one=True)

    if not op:
        return jsonify({'error': 'Outpass not found'}), 404

    # Security check: student can only view their own
    if session['role'] == 'student':
        stud = query_db("SELECT id FROM students WHERE user_id = ?", [session['user_id']], one=True)
        if not stud or stud['id'] != op['student_id']:
            return jsonify({'error': 'Unauthorized'}), 403

    return jsonify({
        'id': op['id'],
        'pass_code': op['pass_code'],
        'student_name': op['student_name'],
        'roll_no': op['roll_no'],
        'department': op['department'],
        'year': op['year'],
        'room_number': op['room_number'] or 'Not Allocated',
        'block_name': op['block_name'] or 'General',
        'departure': f"{op['departure_date']} at {op['departure_time']}",
        'return_schedule': f"{op['return_date']} at {op['return_time']}",
        'destination': op['destination'],
        'reason': op['reason'],
        'parent_contact': op['parent_contact'],
        'status': op['status'],
        'warden_remarks': op['warden_remarks'] or 'None',
        'approved_by': op['approved_by_name'] or 'Hostel Warden Office',
        'applied_at': op['applied_at']
    })

# -------------------------------------------------------------
# 5. Food Menu Management
# -------------------------------------------------------------
@app.route('/food-menu')
@login_required
def food_menu():
    """Weekly Food Timetable, today's highlight, ratings, and admin edit modal."""
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    today_name = days[datetime.date.today().weekday()]
    selected_day = request.args.get('day', today_name)
    if selected_day not in days:
        selected_day = today_name

    # Full weekly timetable grouped by day
    all_menus = query_db("""
        SELECT * FROM food_menus 
        ORDER BY CASE day_of_week 
            WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 
            WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 WHEN 'Sunday' THEN 7 
        END,
        CASE meal_type 
            WHEN 'Breakfast' THEN 1 WHEN 'Lunch' THEN 2 WHEN 'Snacks' THEN 3 WHEN 'Dinner' THEN 4 
        END
    """)

    # Filter for selected day
    day_meals = [m for m in all_menus if m['day_of_week'] == selected_day]

    # Today's meals
    today_meals = [m for m in all_menus if m['day_of_week'] == today_name]

    # Recent food feedbacks
    feedbacks = query_db("""
        SELECT f.*, u.full_name as student_name, s.roll_no
        FROM food_feedbacks f
        JOIN students s ON f.student_id = s.id
        JOIN users u ON s.user_id = u.id
        ORDER BY f.created_at DESC LIMIT 6
    """)

    # Average rating
    avg_row = query_db("SELECT AVG(rating) as avg_r, COUNT(*) as cnt FROM food_feedbacks", one=True)
    avg_rating = round(avg_row['avg_r'], 1) if avg_row and avg_row['avg_r'] else 4.6
    total_feedbacks = avg_row['cnt'] if avg_row else 0

    return render_template(
        'food_menu.html',
        days=days,
        selected_day=selected_day,
        today_name=today_name,
        day_meals=day_meals,
        today_meals=today_meals,
        all_menus=all_menus,
        feedbacks=feedbacks,
        avg_rating=avg_rating,
        total_feedbacks=total_feedbacks
    )

@app.route('/api/food-menu/update', methods=['POST'])
@login_required
@role_required(['warden', 'admin'])
def update_food_menu():
    """Add or update food items for a day and meal type."""
    day = request.form.get('day_of_week')
    meal_type = request.form.get('meal_type')
    items = request.form.get('items', '').strip()
    timings = request.form.get('timings', '').strip()
    special_note = request.form.get('special_note', '').strip()

    if not (day and meal_type and items and timings):
        return jsonify({'success': False, 'message': 'Day, meal type, items and timings are required.'}), 400

    existing = query_db("SELECT id FROM food_menus WHERE day_of_week = ? AND meal_type = ?", [day, meal_type], one=True)
    if existing:
        execute_db("""
            UPDATE food_menus 
            SET items = ?, timings = ?, special_note = ?
            WHERE id = ?
        """, [items, timings, special_note, existing['id']])
    else:
        execute_db("""
            INSERT INTO food_menus (day_of_week, meal_type, items, timings, special_note)
            VALUES (?, ?, ?, ?, ?)
        """, [day, meal_type, items, timings, special_note])

    # Broadcast notification to all students
    students = query_db("SELECT user_id FROM students")
    for s in students:
        execute_db("""
            INSERT INTO notifications (user_id, title, message, type, link)
            VALUES (?, 'Food Menu Updated', ?, 'menu', '/food-menu')
        """, [s['user_id'], f"{day} {meal_type} menu has been updated by hostel administration."])

    return jsonify({'success': True, 'message': f'{day} {meal_type} menu updated successfully.'})

@app.route('/api/food-menu/feedback', methods=['POST'])
@login_required
@role_required(['student'])
def submit_food_feedback():
    """Student submits food feedback rating and comment."""
    student = query_db("SELECT id FROM students WHERE user_id = ?", [session['user_id']], one=True)
    if not student:
        return jsonify({'success': False, 'message': 'Student profile not found.'}), 400

    meal_type = request.form.get('meal_type', 'Lunch')
    rating = int(request.form.get('rating', 5))
    comment = request.form.get('comment', '').strip()
    meal_date = datetime.date.today().isoformat()

    execute_db("""
        INSERT INTO food_feedbacks (student_id, meal_date, meal_type, rating, comment)
        VALUES (?, ?, ?, ?, ?)
    """, [student['id'], meal_date, meal_type, rating, comment])

    return jsonify({'success': True, 'message': 'Thank you! Your food feedback has been recorded.'})

# -------------------------------------------------------------
# 6. Complaint Management
# -------------------------------------------------------------
@app.route('/complaints')
@login_required
def complaints():
    """Complaints management system for student reporting and Warden/Admin resolution."""
    role = session['role']
    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')

    if role == 'student':
        student = query_db("""
            SELECT s.*, r.room_number 
            FROM students s
            LEFT JOIN rooms r ON s.room_id = r.id
            WHERE s.user_id = ?
        """, [session['user_id']], one=True)

        query = """
            SELECT c.*, resolver.full_name as resolved_by_name
            FROM complaints c
            LEFT JOIN users resolver ON c.resolved_by = resolver.id
            WHERE c.student_id = ?
        """
        params = [student['id']]

        if status_filter != 'all':
            query += " AND c.status = ?"
            params.append(status_filter)
        if category_filter != 'all':
            query += " AND c.category = ?"
            params.append(category_filter)

        query += " ORDER BY c.created_at DESC"
        complaints_list = query_db(query, params)

        return render_template(
            'complaints.html',
            complaints=complaints_list,
            student=student,
            status_filter=status_filter,
            category_filter=category_filter
        )
    else:
        # Warden / Admin view
        query = """
            SELECT c.*, u.full_name as student_name, s.roll_no,
                   resolver.full_name as resolved_by_name
            FROM complaints c
            JOIN students s ON c.student_id = s.id
            JOIN users u ON s.user_id = u.id
            LEFT JOIN users resolver ON c.resolved_by = resolver.id
            WHERE 1=1
        """
        params = []
        if status_filter != 'all':
            query += " AND c.status = ?"
            params.append(status_filter)
        if category_filter != 'all':
            query += " AND c.category = ?"
            params.append(category_filter)

        query += """
            ORDER BY CASE c.status WHEN 'Pending' THEN 1 WHEN 'In Progress' THEN 2 ELSE 3 END,
            CASE c.priority WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END,
            c.created_at DESC
        """
        complaints_list = query_db(query, params)

        stats = {
            'pending': query_db("SELECT COUNT(*) as c FROM complaints WHERE status = 'Pending'", one=True)['c'],
            'in_progress': query_db("SELECT COUNT(*) as c FROM complaints WHERE status = 'In Progress'", one=True)['c'],
            'resolved': query_db("SELECT COUNT(*) as c FROM complaints WHERE status = 'Resolved'", one=True)['c'],
            'total': query_db("SELECT COUNT(*) as c FROM complaints", one=True)['c']
        }

        return render_template(
            'complaints.html',
            complaints=complaints_list,
            status_filter=status_filter,
            category_filter=category_filter,
            stats=stats
        )

@app.route('/api/complaints/submit', methods=['POST'])
@login_required
@role_required(['student'])
def submit_complaint():
    """Student submits new complaint ticket."""
    student = query_db("""
        SELECT s.*, r.room_number 
        FROM students s 
        LEFT JOIN rooms r ON s.room_id = r.id 
        WHERE s.user_id = ?
    """, [session['user_id']], one=True)

    category = request.form.get('category')
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = request.form.get('priority', 'Medium')
    room_number = request.form.get('room_number', '').strip() or (student['room_number'] if student else 'General')

    if not (category and title and description):
        return jsonify({'success': False, 'message': 'Category, title, and description are required.'}), 400

    ticket_num = f"TKT-2026-{random.randint(100, 999)}"

    complaint_id = execute_db("""
        INSERT INTO complaints (ticket_number, student_id, category, title, description, room_number, priority, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending')
    """, [ticket_num, student['id'], category, title, description, room_number, priority])

    # Notify student
    execute_db("""
        INSERT INTO notifications (user_id, title, message, type, link)
        VALUES (?, 'Complaint Registered', ?, 'complaint', '/complaints')
    """, [session['user_id'], f"Your complaint '{title}' ({ticket_num}) has been filed and assigned to the maintenance team."])

    # Notify Wardens
    wardens = query_db("SELECT user_id FROM wardens")
    for w in wardens:
        execute_db("""
            INSERT INTO notifications (user_id, title, message, type, link)
            VALUES (?, 'New Student Complaint Filed', ?, 'complaint', '/complaints')
        """, [w['user_id'], f"[{priority.upper()}] {student['roll_no']}: {title} ({category}) in Room {room_number}."])

    return jsonify({'success': True, 'message': 'Complaint registered successfully.', 'ticket_number': ticket_num})

@app.route('/api/complaints/<int:complaint_id>/status', methods=['POST'])
@login_required
@role_required(['warden', 'admin'])
def update_complaint_status(complaint_id):
    """Warden or Admin updates complaint progress or marks resolved with resolution note."""
    status = request.form.get('status') # 'Pending', 'In Progress', 'Resolved'
    notes = request.form.get('resolution_notes', '').strip()

    comp = query_db("""
        SELECT c.*, s.user_id as student_user_id
        FROM complaints c
        JOIN students s ON c.student_id = s.id
        WHERE c.id = ?
    """, [complaint_id], one=True)

    if not comp:
        return jsonify({'success': False, 'message': 'Complaint ticket not found.'}), 404

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resolved_at = now_str if status == 'Resolved' else None

    execute_db("""
        UPDATE complaints 
        SET status = ?, resolution_notes = ?, resolved_by = ?, resolved_at = ?
        WHERE id = ?
    """, [status, notes, session['user_id'], resolved_at, complaint_id])

    # Notify student
    msg = f"Your complaint ticket {comp['ticket_number']} is now '{status}'."
    if notes:
        msg += f" Note: {notes}"

    execute_db("""
        INSERT INTO notifications (user_id, title, message, type, link)
        VALUES (?, 'Complaint Status Update', ?, 'complaint', '/complaints')
    """, [comp['student_user_id'], msg])

    return jsonify({'success': True, 'message': f'Complaint status updated to {status}.'})

# -------------------------------------------------------------
# 7. Announcements Board
# -------------------------------------------------------------
@app.route('/announcements')
@login_required
def announcements():
    """Hostel announcements feed with category filters and author info."""
    category_filter = request.args.get('category', 'all')
    search_query = request.args.get('search', '').strip()

    query = """
        SELECT a.*, u.full_name as author_name, u.role as author_role
        FROM announcements a
        LEFT JOIN users u ON a.posted_by = u.id
        WHERE 1=1
    """
    params = []
    if category_filter != 'all':
        query += " AND a.category = ?"
        params.append(category_filter)
    if search_query:
        query += " AND (a.title LIKE ? OR a.content LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])

    query += " ORDER BY CASE a.priority WHEN 'Urgent' THEN 1 WHEN 'Important' THEN 2 ELSE 3 END, a.created_at DESC"
    announcements_list = query_db(query, params)

    return render_template(
        'announcements.html',
        announcements=announcements_list,
        category_filter=category_filter,
        search_query=search_query
    )

@app.route('/api/announcements/create', methods=['POST'])
@login_required
@role_required(['warden', 'admin'])
def create_announcement():
    """Warden or Admin publishes a new hostel announcement."""
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    priority = request.form.get('priority', 'Normal')
    category = request.form.get('category', 'General')

    if not (title and content):
        return jsonify({'success': False, 'message': 'Title and content are required.'}), 400

    announcement_id = execute_db("""
        INSERT INTO announcements (title, content, priority, category, posted_by)
        VALUES (?, ?, ?, ?, ?)
    """, [title, content, priority, category, session['user_id']])

    # Notify all students
    students = query_db("SELECT user_id FROM students")
    for s in students:
        execute_db("""
            INSERT INTO notifications (user_id, title, message, type, link)
            VALUES (?, 'New Hostel Announcement', ?, 'announcement', '/announcements')
        """, [s['user_id'], f"[{priority.upper()}] {title}"])

    return jsonify({'success': True, 'message': 'Announcement published successfully.'})

@app.route('/api/announcements/<int:announcement_id>/delete', methods=['POST'])
@login_required
@role_required(['warden', 'admin'])
def delete_announcement(announcement_id):
    """Delete an announcement."""
    execute_db("DELETE FROM announcements WHERE id = ?", [announcement_id])
    return jsonify({'success': True, 'message': 'Announcement deleted successfully.'})

# -------------------------------------------------------------
# 8. Room Management & Allocation (Admin & Warden)
# -------------------------------------------------------------
@app.route('/rooms')
@login_required
@role_required(['admin', 'warden'])
def rooms():
    """Hostel blocks and room allocation overview, bed assignments and filters."""
    block_filter = request.args.get('block', 'all')
    status_filter = request.args.get('status', 'all')

    blocks = query_db("SELECT * FROM blocks ORDER BY name")

    query = """
        SELECT r.*, b.name as block_name,
               (SELECT COUNT(*) FROM students s WHERE s.room_id = r.id) as current_occupants
        FROM rooms r
        JOIN blocks b ON r.block_id = b.id
        WHERE 1=1
    """
    params = []
    if block_filter != 'all':
        query += " AND b.id = ?"
        params.append(block_filter)
    if status_filter == 'available':
        query += " AND (SELECT COUNT(*) FROM students s WHERE s.room_id = r.id) < r.capacity"
    elif status_filter == 'occupied':
        query += " AND (SELECT COUNT(*) FROM students s WHERE s.room_id = r.id) >= r.capacity"

    query += " ORDER BY b.name, r.floor, r.room_number"
    rooms_list = query_db(query, params)

    # Get students in each room
    room_occupants = {}
    for r in rooms_list:
        occs = query_db("""
            SELECT s.id, s.roll_no, s.department, s.year, u.full_name, u.phone
            FROM students s
            JOIN users u ON s.user_id = u.id
            WHERE s.room_id = ?
        """, [r['id']])
        room_occupants[r['id']] = occs

    # Unallocated students
    unallocated_students = query_db("""
        SELECT s.id, s.roll_no, u.full_name, s.department, s.year, s.gender
        FROM students s
        JOIN users u ON s.user_id = u.id
        WHERE s.room_id IS NULL
        ORDER BY s.roll_no
    """)

    return render_template(
        'rooms.html',
        blocks=blocks,
        rooms=rooms_list,
        room_occupants=room_occupants,
        unallocated_students=unallocated_students,
        block_filter=block_filter,
        status_filter=status_filter
    )

@app.route('/api/rooms/allocate', methods=['POST'])
@login_required
@role_required(['admin', 'warden'])
def allocate_room():
    """Assign or reassign a student to a room."""
    student_id = request.form.get('student_id')
    room_id = request.form.get('room_id')

    if not student_id or not room_id:
        return jsonify({'success': False, 'message': 'Student and room selection are required.'}), 400

    room = query_db("""
        SELECT r.*, (SELECT COUNT(*) FROM students s WHERE s.room_id = r.id) as current_occupants
        FROM rooms r WHERE r.id = ?
    """, [room_id], one=True)

    if not room:
        return jsonify({'success': False, 'message': 'Room not found.'}), 404

    if room['current_occupants'] >= room['capacity']:
        return jsonify({'success': False, 'message': 'Room is already at full capacity!'}), 400

    execute_db("UPDATE students SET room_id = ? WHERE id = ?", [room_id, student_id])

    # Check if now full
    new_count = room['current_occupants'] + 1
    new_status = 'Occupied' if new_count >= room['capacity'] else 'Available'
    execute_db("UPDATE rooms SET status = ? WHERE id = ?", [new_status, room_id])

    # Notify student
    student = query_db("SELECT user_id FROM students WHERE id = ?", [student_id], one=True)
    if student:
        execute_db("""
            INSERT INTO notifications (user_id, title, message, type, link)
            VALUES (?, 'Room Allocation Confirmed', ?, 'room', '/student/dashboard')
        """, [student['user_id'], f"You have been allocated Room {room['room_number']}."])

    return jsonify({'success': True, 'message': f'Student assigned to Room {room["room_number"]} successfully.'})

@app.route('/api/rooms/deallocate', methods=['POST'])
@login_required
@role_required(['admin', 'warden'])
def deallocate_room():
    """Remove student from their assigned room."""
    student_id = request.form.get('student_id')
    student = query_db("SELECT * FROM students WHERE id = ?", [student_id], one=True)
    if not student or not student['room_id']:
        return jsonify({'success': False, 'message': 'Student has no assigned room.'}), 400

    room_id = student['room_id']
    execute_db("UPDATE students SET room_id = NULL WHERE id = ?", [student_id])
    execute_db("UPDATE rooms SET status = 'Available' WHERE id = ?", [room_id])

    execute_db("""
        INSERT INTO notifications (user_id, title, message, type, link)
        VALUES (?, 'Room Deallocation Notice', 'You have been unallocated from your hostel room by administration.', 'room', '/student/dashboard')
    """, [student['user_id']])

    return jsonify({'success': True, 'message': 'Student unassigned from room successfully.'})

@app.route('/api/rooms/add', methods=['POST'])
@login_required
@role_required(['admin'])
def add_room():
    """Admin adds a new room to a block."""
    block_id = request.form.get('block_id')
    room_number = request.form.get('room_number', '').strip().upper()
    floor = request.form.get('floor', 1)
    capacity = request.form.get('capacity', 2)
    room_type = request.form.get('type', 'Double AC')

    if not (block_id and room_number):
        return jsonify({'success': False, 'message': 'Block and room number are required.'}), 400

    existing = query_db("SELECT id FROM rooms WHERE block_id = ? AND room_number = ?", [block_id, room_number], one=True)
    if existing:
        return jsonify({'success': False, 'message': f'Room {room_number} already exists in this block.'}), 400

    execute_db("""
        INSERT INTO rooms (block_id, room_number, floor, capacity, type, status)
        VALUES (?, ?, ?, ?, ?, 'Available')
    """, [block_id, room_number, floor, capacity, room_type])

    return jsonify({'success': True, 'message': f'Room {room_number} added successfully.'})

# -------------------------------------------------------------
# 9. Admin User Management (Students & Wardens)
# -------------------------------------------------------------
@app.route('/admin/users')
@login_required
@role_required(['admin'])
def admin_users():
    """Manage student accounts and wardens."""
    students = query_db("""
        SELECT s.*, u.username, u.email, u.full_name, u.phone, r.room_number, b.name as block_name
        FROM students s
        JOIN users u ON s.user_id = u.id
        LEFT JOIN rooms r ON s.room_id = r.id
        LEFT JOIN blocks b ON r.block_id = b.id
        ORDER BY s.roll_no
    """)

    wardens = query_db("""
        SELECT w.*, u.username, u.email, u.full_name, u.phone, b.name as block_name
        FROM wardens w
        JOIN users u ON w.user_id = u.id
        LEFT JOIN blocks b ON w.assigned_block_id = b.id
        ORDER BY w.employee_id
    """)

    blocks = query_db("SELECT * FROM blocks ORDER BY name")

    return render_template(
        'admin_users.html',
        students=students,
        wardens=wardens,
        blocks=blocks
    )

@app.route('/api/admin/users/add-warden', methods=['POST'])
@login_required
@role_required(['admin'])
def add_warden():
    """Admin adds a new hostel warden."""
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    full_name = request.form.get('full_name', '').strip()
    password = request.form.get('password', 'warden123').strip()
    phone = request.form.get('phone', '').strip()
    employee_id = request.form.get('employee_id', '').strip()
    assigned_block_id = request.form.get('assigned_block_id')
    designation = request.form.get('designation', 'Hostel Warden').strip()

    if not (username and email and full_name and employee_id):
        return jsonify({'success': False, 'message': 'Username, email, full name, and Employee ID are required.'}), 400

    existing_user = query_db("SELECT id FROM users WHERE username = ? OR email = ?", [username, email], one=True)
    if existing_user:
        return jsonify({'success': False, 'message': 'Username or Email is already registered.'}), 400

    pw_hash = generate_password_hash(password)
    user_id = execute_db("""
        INSERT INTO users (username, email, password_hash, role, full_name, phone, avatar)
        VALUES (?, ?, ?, 'warden', ?, ?, 'avatar_warden1.png')
    """, [username, email, pw_hash, full_name, phone])

    block_val = int(assigned_block_id) if assigned_block_id and assigned_block_id.isdigit() else None
    execute_db("""
        INSERT INTO wardens (user_id, employee_id, assigned_block_id, designation)
        VALUES (?, ?, ?, ?)
    """, [user_id, employee_id, block_val, designation])

    return jsonify({'success': True, 'message': f'Warden {full_name} added successfully.'})

@app.route('/api/admin/users/delete-user/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_user(user_id):
    """Admin removes a user account."""
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': 'Cannot delete your own admin account.'}), 400

    execute_db("DELETE FROM users WHERE id = ?", [user_id])
    return jsonify({'success': True, 'message': 'User deleted successfully.'})

# -------------------------------------------------------------
# 10. Notification APIs
# -------------------------------------------------------------
@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Fetch recent notifications and unread badge count."""
    user_id = session['user_id']
    notes = query_db("""
        SELECT * FROM notifications 
        WHERE user_id = ? 
        ORDER BY created_at DESC LIMIT 10
    """, [user_id])

    unread_cnt = query_db("SELECT COUNT(*) as c FROM notifications WHERE user_id = ? AND is_read = 0", [user_id], one=True)['c']

    return jsonify({
        'unread_count': unread_cnt,
        'notifications': [dict(n) for n in notes]
    })

@app.route('/api/notifications/mark-read/<int:note_id>', methods=['POST'])
@login_required
def mark_notification_read(note_id):
    """Mark single notification as read."""
    execute_db("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", [note_id, session['user_id']])
    return jsonify({'success': True})

@app.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications read for active user."""
    execute_db("UPDATE notifications SET is_read = 1 WHERE user_id = ?", [session['user_id']])
    return jsonify({'success': True})

# -------------------------------------------------------------
# 11. Chart.js Analytics API
# -------------------------------------------------------------
@app.route('/api/analytics/charts', methods=['GET'])
@login_required
def get_chart_data():
    """Provide structured data for Chart.js dashboard charts."""
    # 1. Outpasses Status Distribution
    outpass_counts = query_db("""
        SELECT status, COUNT(*) as cnt 
        FROM outpasses 
        GROUP BY status
    """)
    outpass_dict = {'Pending': 0, 'Approved': 0, 'Rejected': 0, 'Completed': 0}
    for row in outpass_counts:
        outpass_dict[row['status']] = row['cnt']

    # 2. Complaints by Category
    complaints_cat = query_db("""
        SELECT category, COUNT(*) as cnt 
        FROM complaints 
        GROUP BY category
    """)
    cat_labels = []
    cat_data = []
    for row in complaints_cat:
        cat_labels.append(row['category'])
        cat_data.append(row['cnt'])

    # 3. Block Occupancy vs Capacity
    blocks_occ = query_db("""
        SELECT b.name,
               COALESCE(SUM(r.capacity), 0) as capacity,
               (SELECT COUNT(*) FROM students s JOIN rooms rm ON s.room_id = rm.id WHERE rm.block_id = b.id) as occupied
        FROM blocks b
        LEFT JOIN rooms r ON b.id = r.block_id
        GROUP BY b.id
    """)
    block_names = [b['name'].split('(')[0].strip() for b in blocks_occ]
    capacities = [b['capacity'] for b in blocks_occ]
    occupancies = [b['occupied'] for b in blocks_occ]

    # 4. Weekly Outpass Requests (Last 7 days trend)
    days_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    weekly_requests = [4, 7, 3, 9, 14, 18, 12]

    return jsonify({
        'outpass_distribution': {
            'labels': ['Pending', 'Approved', 'Rejected', 'Completed'],
            'data': [outpass_dict['Pending'], outpass_dict['Approved'], outpass_dict['Rejected'], outpass_dict['Completed']]
        },
        'complaints_category': {
            'labels': cat_labels,
            'data': cat_data
        },
        'block_occupancy': {
            'labels': block_names,
            'capacity': capacities,
            'occupied': occupancies
        },
        'weekly_outpasses': {
            'labels': days_labels,
            'data': weekly_requests
        }
    })

# -------------------------------------------------------------
# Application Runner
# -------------------------------------------------------------
if __name__ == '__main__':
    # Initialize SQLite database and populate demo records if first run
    init_db()
    print("=====================================================")
    print("  SmartStay – Smart Hostel Management System running  ")
    print("  URL: http://127.0.0.1:5000                         ")
    print("  Default Accounts:                                  ")
    print("    Admin:   admin / admin123                        ")
    print("    Warden:  warden / warden123                      ")
    print("    Student: student / student123                    ")
    print("=====================================================")
    app.run(debug=True, host='127.0.0.1', port=5000)
