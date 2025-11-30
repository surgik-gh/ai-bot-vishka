import json
import os
import time
from collections import defaultdict

from flask import Flask, jsonify, request
from flask_login import LoginManager, current_user, login_required
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
from extensions import db

db.init_app(app)
mail = Mail(app)

# Ensure upload folders exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "avatars"), exist_ok=True)

# Brute-force protection
failed_attempts = defaultdict(int)
last_attempt_time = defaultdict(float)
MAX_ATTEMPTS = 5
LOCKOUT_TIME = 300  # 5 minutes

def is_locked_out(ip_address):
    """Check if IP is locked out due to too many failed attempts"""
    if failed_attempts[ip_address] >= MAX_ATTEMPTS:
        if time.time() - last_attempt_time[ip_address] < LOCKOUT_TIME:
            return True
    return False

def record_failed_attempt(ip_address):
    """Record a failed login attempt"""
    failed_attempts[ip_address] += 1
    last_attempt_time[ip_address] = time.time()

def reset_failed_attempts(ip_address):
    """Reset failed attempts for an IP after successful login"""
    failed_attempts[ip_address] = 0

# Initialize login manager
login_manager = LoginManager(app)
login_manager.login_view = "login"  # type: ignore
login_manager.session_protection = (
    "strong"  # Stronger session protection
)

# Import models after db.init_app
from models import *

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    try:
        return User.query.get(int(user_id))
    except (ValueError, TypeError):
        return None

# Import routes after app initialization
from routes import *


def migrate_database():
    """Add missing columns to existing database tables"""
    inspector = inspect(db.engine)

    # Check and add missing columns to user table
    try:
        # Check if user table exists
        if "user" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("user")]
            migrations = []

            # Define all columns that might be missing
            if "email_verified" not in columns:
                migrations.append(("email_verified", "BOOLEAN DEFAULT 0"))
            if "github_id" not in columns:
                migrations.append(("github_id", "VARCHAR(50)"))
            if "google_id" not in columns:
                migrations.append(("google_id", "VARCHAR(50)"))
            if "created_at" not in columns:
                migrations.append(("created_at", "DATETIME"))
            # Rating system
            if "rating" not in columns:
                migrations.append(("rating", "INTEGER DEFAULT 0"))
            if "total_quizzes" not in columns:
                migrations.append(("total_quizzes", "INTEGER DEFAULT 0"))
            if "total_correct_answers" not in columns:
                migrations.append(("total_correct_answers", "INTEGER DEFAULT 0"))
            if "total_answers" not in columns:
                migrations.append(("total_answers", "INTEGER DEFAULT 0"))
            if "tutorial_completed" not in columns:
                migrations.append(("tutorial_completed", "BOOLEAN DEFAULT 0"))
            if "teacher_id" not in columns:
                migrations.append(("teacher_id", "INTEGER"))

            # Execute all migrations
            for col_name, col_type in migrations:
                print(f"Adding missing {col_name} column to user table...")
                db.session.execute(
                    text(f"ALTER TABLE user ADD COLUMN {col_name} {col_type}")
                )
                db.session.commit()
                print(f"Successfully added {col_name} column")

            # Create unique indexes for github_id and google_id if they exist
            if "github_id" in [col["name"] for col in inspector.get_columns("user")]:
                try:
                    db.session.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_github_id ON user(github_id)"
                        )
                    )
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            if "google_id" in [col["name"] for col in inspector.get_columns("user")]:
                try:
                    db.session.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_google_id ON user(google_id)"
                        )
                    )
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            # Check and add api_key and selected_model columns
            if "api_key" not in columns:
                print("Adding missing api_key column to user table...")
                db.session.execute(
                    text("ALTER TABLE user ADD COLUMN api_key VARCHAR(255)")
                )
                db.session.commit()
                print("Successfully added api_key column")

            if "selected_model" not in columns:
                print("Adding missing selected_model column to user table...")
                db.session.execute(
                    text(
                        "ALTER TABLE user ADD COLUMN selected_model VARCHAR(100) DEFAULT 'x-ai/grok-4.1-fast:free'"
                    )
                )
                db.session.commit()
                print("Successfully added selected_model column")

            if not migrations and "api_key" in columns and "selected_model" in columns:
                print("Database schema is up to date")

        # Проверяем и добавляем недостающие колонки в таблицу lesson
        if "lesson" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("lesson")]
            if "uuid" not in columns:
                print("Adding missing uuid column to lesson table...")
                try:
                    db.session.execute(text("ALTER TABLE lesson ADD COLUMN uuid VARCHAR(36)"))
                    db.session.commit()
                    # Генерируем UUID для существующих записей
                    import uuid
                    lessons = db.session.execute(text("SELECT id FROM lesson WHERE uuid IS NULL OR uuid = ''")).fetchall()
                    for lesson_id in lessons:
                        db.session.execute(text(f"UPDATE lesson SET uuid = '{str(uuid.uuid4())}' WHERE id = {lesson_id[0]}"))
                    db.session.commit()
                    print("Successfully added uuid column to lesson table")
                except Exception as e:
                    db.session.rollback()
                    print(f"Error adding uuid to lesson table: {e}")

        # Проверяем и добавляем недостающие колонки в таблицу quiz
        if "quiz" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("quiz")]
            if "uuid" not in columns:
                print("Adding missing uuid column to quiz table...")
                try:
                    db.session.execute(text("ALTER TABLE quiz ADD COLUMN uuid VARCHAR(36)"))
                    db.session.commit()
                    # Генерируем UUID для существующих записей
                    import uuid
                    quizzes = db.session.execute(text("SELECT id FROM quiz WHERE uuid IS NULL OR uuid = ''")).fetchall()
                    for quiz_id in quizzes:
                        db.session.execute(text(f"UPDATE quiz SET uuid = '{str(uuid.uuid4())}' WHERE id = {quiz_id[0]}"))
                    db.session.commit()
                    print("Successfully added uuid column to quiz table")
                except Exception as e:
                    db.session.rollback()
                    print(f"Error adding uuid to quiz table: {e}")

        # Создаем таблицу quiz_attempt, если её нет
        if "quiz_attempt" not in inspector.get_table_names():
            print("Creating quiz_attempt table...")
            try:
                db.session.execute(text("""
                    CREATE TABLE quiz_attempt (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        quiz_id INTEGER NOT NULL,
                        lesson_id INTEGER NOT NULL,
                        score INTEGER DEFAULT 0,
                        total_questions INTEGER DEFAULT 0,
                        completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_first_attempt BOOLEAN DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES user (id),
                        FOREIGN KEY (quiz_id) REFERENCES quiz (id),
                        FOREIGN KEY (lesson_id) REFERENCES lesson (id)
                    )
                """))
                db.session.commit()
                print("Successfully created quiz_attempt table")
            except Exception as e:
                db.session.rollback()
                print(f"Error creating quiz_attempt table: {e}")
    except Exception as e:
        db.session.rollback()
        print(f"Error during migration: {e}")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # Run migrations for existing databases
        migrate_database()
        # Create admin user if not exists
        if not User.query.filter_by(email="admin@example.com").first():
            admin = User(
                email="admin@example.com",
                password_hash=generate_password_hash("admin123"),
                first_name="Admin",
                last_name="User",
                role="administrator",
                tokens=999999,
            )
            db.session.add(admin)
            db.session.commit()

        # Create default achievements
        if not Achievement.query.first():
            achievements = [
                Achievement(
                    name="High intelligence",
                    description="Pass a quiz without errors",
                    condition="perfect_quiz",
                    icon="🏆",
                ),
                Achievement(
                    name="First steps",
                    description="Pass your first quiz",
                    condition="first_quiz",
                    icon="🎯",
                ),
                Achievement(
                    name="Knowledge master",
                    description="Pass 10 quizzes",
                    condition="ten_quizzes",
                    icon="⭐",
                ),
            ]
            for ach in achievements:
                db.session.add(ach)
            db.session.commit()

    app.run(debug=True, host="0.0.0.0", port=5000)
