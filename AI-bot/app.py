from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from werkzeug.security import generate_password_hash
import os
from sqlalchemy import text, inspect
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Initialize Flask-Mail
mail = Mail(app)

# Import db from models first
from models import db

# Initialize db with app
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.session_protection = 'basic'  # Базовая защита сессии (strong может вызывать проблемы с AJAX)

# Ensure upload folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)

# Import all models (db is already initialized)
from models import *

# Import routes (must be after app initialization)
from routes import *

def migrate_database():
    """Add missing columns to existing database tables"""
    inspector = inspect(db.engine)
    
    # Check and add missing columns to user table
    try:
        # Check if user table exists
        if 'user' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('user')]
            migrations = []
            
            # Define all columns that might be missing
            if 'email_verified' not in columns:
                migrations.append(("email_verified", "BOOLEAN DEFAULT 0"))
            if 'vk_id' not in columns:
                migrations.append(("vk_id", "VARCHAR(50)"))
            if 'google_id' not in columns:
                migrations.append(("google_id", "VARCHAR(50)"))
            if 'created_at' not in columns:
                migrations.append(("created_at", "DATETIME"))
            # Рейтинговая система
            if 'rating' not in columns:
                migrations.append(("rating", "INTEGER DEFAULT 0"))
            if 'total_quizzes' not in columns:
                migrations.append(("total_quizzes", "INTEGER DEFAULT 0"))
            if 'total_correct_answers' not in columns:
                migrations.append(("total_correct_answers", "INTEGER DEFAULT 0"))
            if 'total_answers' not in columns:
                migrations.append(("total_answers", "INTEGER DEFAULT 0"))
            
            # Execute all migrations
            for col_name, col_type in migrations:
                print(f"Adding missing {col_name} column to user table...")
                db.session.execute(text(f"ALTER TABLE user ADD COLUMN {col_name} {col_type}"))
                db.session.commit()
                print(f"Successfully added {col_name} column")
            
            # Create unique indexes for vk_id and google_id if they exist
            if 'vk_id' in [col['name'] for col in inspector.get_columns('user')]:
                try:
                    db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_vk_id ON user(vk_id)"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            
            if 'google_id' in [col['name'] for col in inspector.get_columns('user')]:
                try:
                    db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_google_id ON user(google_id)"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            
            if not migrations:
                print("Database schema is up to date")
    except Exception as e:
        db.session.rollback()
        print(f"Error during migration: {e}")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Run migrations for existing databases
        migrate_database()
        # Create admin user if not exists
        from models import User
        if not User.query.filter_by(email='admin@example.com').first():
            admin = User(
                email='admin@example.com',
                password_hash=generate_password_hash('admin123'),
                first_name='Admin',
                last_name='User',
                role='administrator',
                tokens=999999
            )
            db.session.add(admin)
            db.session.commit()
        
        # Create default achievements
        from models import Achievement
        if not Achievement.query.first():
            achievements = [
                Achievement(name='Высокий интеллект', description='Пройдите викторину без ошибок', condition='perfect_quiz', icon='🏆'),
                Achievement(name='Первые шаги', description='Пройдите первую викторину', condition='first_quiz', icon='🎯'),
                Achievement(name='Мастер знаний', description='Пройдите 10 викторин', condition='ten_quizzes', icon='⭐'),
            ]
            for ach in achievements:
                db.session.add(ach)
            db.session.commit()
    
    app.run(debug=True, host='0.0.0.0', port=5000)

