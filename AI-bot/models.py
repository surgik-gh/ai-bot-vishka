from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

# db will be set from app.py before models are used
db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # Nullable for OAuth users
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # student, teacher, administrator
    tokens = db.Column(db.Integer, default=100)
    selected_expert_id = db.Column(db.Integer, db.ForeignKey('expert.id'), nullable=True)
    theme = db.Column(db.String(20), default='light')  # light, dark, base или theme_id для кастомных
    custom_theme_id = db.Column(db.Integer, db.ForeignKey('theme.id'), nullable=True)
    
    custom_theme = db.relationship('Theme', foreign_keys=[custom_theme_id], backref='users_using')
    last_daily_reward = db.Column(db.DateTime, nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    vk_id = db.Column(db.String(50), unique=True, nullable=True)
    google_id = db.Column(db.String(50), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Рейтинговая система
    rating = db.Column(db.Integer, default=0)  # Общий рейтинг (очки)
    total_quizzes = db.Column(db.Integer, default=0)  # Количество пройденных викторин
    total_correct_answers = db.Column(db.Integer, default=0)  # Всего правильных ответов
    total_answers = db.Column(db.Integer, default=0)  # Всего ответов
    
    expert = db.relationship('Expert', backref='users', foreign_keys=[selected_expert_id])
    lessons = db.relationship('Lesson', backref='user', lazy=True)
    achievements = db.relationship('UserAchievement', backref='user', lazy=True)
    token_transactions = db.relationship('TokenTransaction', backref='user', lazy=True)

class Expert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    avatar_url = db.Column(db.String(255), nullable=True)
    prompt = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    lessons = db.relationship('Lesson', backref='subject', lazy=True)

class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
    material_text = db.Column(db.Text, nullable=True)
    material_image = db.Column(db.String(255), nullable=True)
    explanation_audio = db.Column(db.String(255), nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    quiz = db.relationship('Quiz', backref='lesson', uselist=False, lazy=True)

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lesson.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    questions = db.relationship('Question', backref='quiz', lazy=True, cascade='all, delete-orphan')

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # text, single, multiple
    correct_answer = db.Column(db.Text, nullable=False)  # JSON for multiple choice
    options = db.Column(db.Text, nullable=True)  # JSON array for choices
    order = db.Column(db.Integer, default=0)
    
    answers = db.relationship('UserAnswer', backref='question', lazy=True)

class UserAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(255), nullable=True)
    condition = db.Column(db.String(50), nullable=False)  # perfect_quiz, etc.
    
    users = db.relationship('UserAchievement', backref='achievement', lazy=True)

class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'achievement_id'),)

class TokenTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False)  # initial, daily, lesson_cost, answer_reward
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmailVerificationCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

class Theme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    price = db.Column(db.Integer, default=0)  # 0 = бесплатно, 20-300 токенов
    is_approved = db.Column(db.Boolean, default=False)  # Модерация
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Цвета темы
    bg_primary = db.Column(db.String(7), nullable=False)  # HEX цвет
    bg_secondary = db.Column(db.String(7), nullable=False)
    bg_tertiary = db.Column(db.String(7), nullable=True)
    text_primary = db.Column(db.String(7), nullable=False)
    text_secondary = db.Column(db.String(7), nullable=False)
    accent = db.Column(db.String(7), nullable=False)
    accent_hover = db.Column(db.String(7), nullable=False)
    accent_dark = db.Column(db.String(7), nullable=True)
    border = db.Column(db.String(7), nullable=False)
    success = db.Column(db.String(7), nullable=False)
    error = db.Column(db.String(7), nullable=False)
    card_bg = db.Column(db.String(7), nullable=False)
    card_bg_secondary = db.Column(db.String(7), nullable=True)
    shadow = db.Column(db.String(20), nullable=True)  # rgba
    
    # Цвета для вкладок навигации
    nav_home_color = db.Column(db.String(7), nullable=True)
    nav_achievements_color = db.Column(db.String(7), nullable=True)
    nav_leaderboard_color = db.Column(db.String(7), nullable=True)
    nav_profile_color = db.Column(db.String(7), nullable=True)
    nav_settings_color = db.Column(db.String(7), nullable=True)
    
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_themes')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_themes')
    icons = db.relationship('ThemeIcon', backref='theme', lazy=True, cascade='all, delete-orphan')
    purchases = db.relationship('ThemePurchase', backref='theme', lazy=True)

class ThemeIcon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    theme_id = db.Column(db.Integer, db.ForeignKey('theme.id'), nullable=False)
    icon_name = db.Column(db.String(100), nullable=False)  # Название иконки
    usage_location = db.Column(db.String(200), nullable=False)  # Где используется
    icon_url = db.Column(db.String(500), nullable=False)  # Ссылка на SVG иконку
    order = db.Column(db.Integer, default=0)

class ThemePurchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    theme_id = db.Column(db.Integer, db.ForeignKey('theme.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    price_paid = db.Column(db.Integer, nullable=False)
    creator_received = db.Column(db.Integer, nullable=False)  # С учетом комиссии 20%
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='theme_purchases')

