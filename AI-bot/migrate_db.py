"""
Migration script to add missing email_verified column to User table
"""
from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        # Check if column exists
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('user')]
        
        if 'email_verified' not in columns:
            print("Adding email_verified column to user table...")
            try:
                # Add the column with default value
                db.session.execute(text("ALTER TABLE user ADD COLUMN email_verified BOOLEAN DEFAULT 0"))
                db.session.commit()
                print("Successfully added email_verified column")
            except Exception as e:
                db.session.rollback()
                print(f"Error adding column: {e}")
                raise
        else:
            print("Column email_verified already exists")

if __name__ == '__main__':
    migrate()

