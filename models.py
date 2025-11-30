import json
import uuid
from datetime import datetime

from flask_login import UserMixin

from extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # Nullable for OAuth users
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    role = db.Column(
        db.String(20), nullable=False, default="student"
    )  # student, teacher, administrator, parent, expert
    tokens = db.Column(db.Integer, default=100)
    selected_expert_id = db.Column(
        db.Integer, db.ForeignKey("expert.id"), nullable=True
    )
    theme = db.Column(db.String(20), default="light")  # light, dark, base
    last_daily_reward = db.Column(db.DateTime, nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    github_id = db.Column(db.String(50), unique=True, nullable=True)
    google_id = db.Column(db.String(50), unique=True, nullable=True)
    parent_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=True
    )  # Parent for student
    teacher_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=True
    )  # Teacher for student
    api_key = db.Column(db.String(255), nullable=True)
    selected_model = db.Column(
        db.String(100), nullable=True, default="x-ai/grok-4.1-fast:free"
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Rating system
    rating = db.Column(db.Integer, default=0)  # Total rating (points)
    total_quizzes = db.Column(db.Integer, default=0)  # Number of quizzes taken
    total_correct_answers = db.Column(db.Integer, default=0)  # Total correct answers
    total_answers = db.Column(db.Integer, default=0)  # Total answers
    # Tutorial/Onboarding
    tutorial_completed = db.Column(db.Boolean, default=False)  # Обязательное обучение пройдено

    expert = db.relationship(
        "Expert", backref="users", foreign_keys=[selected_expert_id]
    )
    lessons = db.relationship("Lesson", backref="user", lazy=True)
    achievements = db.relationship("UserAchievement", backref="user", lazy=True)
    token_transactions = db.relationship("TokenTransaction", backref="user", lazy=True)
    # Relationships for parents and children
    parent = db.relationship(
        "User", remote_side=[id], backref="children", foreign_keys=[parent_id]
    )
    # Relationships for teachers and students
    teacher = db.relationship(
        "User", remote_side=[id], backref="students", foreign_keys=[teacher_id]
    )

    def validate_email(self, email):
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    def validate_first_name(self, first_name):
        """Validate first name"""
        if not first_name or len(first_name.strip()) < 1 or len(first_name.strip()) > 50:
            return False
        return True

    def validate_last_name(self, last_name):
        """Validate last name"""
        if not last_name or len(last_name.strip()) < 1 or len(last_name.strip()) > 50:
            return False
        return True

    def validate_role(self, role):
        """Validate role"""
        valid_roles = ['student', 'teacher', 'administrator', 'parent', 'expert']
        return role in valid_roles

    def validate_theme(self, theme):
        """Validate theme"""
        valid_themes = ['light', 'dark', 'base']
        return theme in valid_themes

    def validate_tokens(self, tokens):
        """Validate tokens"""
        return isinstance(tokens, int) and tokens >= 0

    def validate(self):
        """Validate all fields"""
        if not self.validate_email(self.email):
            raise ValueError("Invalid email format")
        if not self.validate_first_name(self.first_name):
            raise ValueError("Invalid first name")
        if not self.validate_last_name(self.last_name):
            raise ValueError("Invalid last name")
        if not self.validate_role(self.role):
            raise ValueError("Invalid role")
        # Устанавливаем тему по умолчанию, если не установлена
        if not self.theme:
            self.theme = 'light'
        if not self.validate_theme(self.theme):
            raise ValueError("Invalid theme")
        if not self.validate_tokens(self.tokens):
            raise ValueError("Invalid tokens value")
        return True


class Expert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    avatar_url = db.Column(db.String(255), nullable=True)
    prompt = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lessons = db.relationship("Lesson", backref="subject", lazy=True)


class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(200), nullable=False)
    material_text = db.Column(db.Text, nullable=True)
    material_image = db.Column(db.String(255), nullable=True)
    explanation_audio = db.Column(db.String(255), nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    quiz = db.relationship("Quiz", backref="lesson", uselist=False, lazy=True)


class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    lesson_id = db.Column(db.Integer, db.ForeignKey("lesson.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship(
        "Question", backref="quiz", lazy=True, cascade="all, delete-orphan"
    )


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # text, single, multiple
    correct_answer = db.Column(db.Text, nullable=False)  # JSON for multiple choice
    options = db.Column(db.Text, nullable=True)  # JSON array for choices
    order = db.Column(db.Integer, default=0)

    answers = db.relationship("UserAnswer", backref="question", lazy=True)


class UserAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)


class QuizAttempt(db.Model):
    """Модель для отслеживания попыток прохождения викторин"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lesson.id"), nullable=False)
    score = db.Column(db.Integer, default=0)  # Количество правильных ответов
    total_questions = db.Column(db.Integer, default=0)  # Всего вопросов
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_first_attempt = db.Column(db.Boolean, default=True)  # Первая попытка (с наградами)
    
    # Relationships
    user = db.relationship("User", backref="quiz_attempts")
    quiz = db.relationship("Quiz", backref="attempts")
    lesson = db.relationship("Lesson", backref="attempts")


class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(255), nullable=True)
    condition = db.Column(db.String(50), nullable=False)  # perfect_quiz, etc.

    users = db.relationship("UserAchievement", backref="achievement", lazy=True)


class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    achievement_id = db.Column(
        db.Integer, db.ForeignKey("achievement.id"), nullable=False
    )
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "achievement_id"),)


class TokenTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(
        db.String(50), nullable=False
    )  # initial, daily, lesson_cost, answer_reward
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EmailVerificationCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    used = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("email", "code"),)
