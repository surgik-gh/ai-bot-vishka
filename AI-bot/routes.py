from flask import render_template, request, jsonify, redirect, url_for, flash, session, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message
from email.header import Header
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import json
import random
import string
import requests
from urllib.parse import urlencode
from pytz import timezone
from app import app, db, login_manager, mail
from models import User, Expert, Subject, Lesson, Quiz, Question, UserAnswer, Achievement, UserAchievement, TokenTransaction, EmailVerificationCode, Theme, ThemeIcon, ThemePurchase
from giga_api import GigaAPI
from config import Config

giga_api = GigaAPI()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'Отсутствуют данные'}), 400
            
            email = data.get('email')
            password = data.get('password')
            first_name = data.get('first_name')
            last_name = data.get('last_name')
            role = data.get('role', 'student')
            
            if not email or not password or not first_name or not last_name:
                return jsonify({'success': False, 'message': 'Заполните все обязательные поля'}), 400
            
            if User.query.filter_by(email=email).first():
                return jsonify({'success': False, 'message': 'Email уже зарегистрирован'}), 400
            
            # Generate verification code
            code = generate_verification_code()
            expires_at = datetime.utcnow() + timedelta(minutes=Config.VERIFICATION_CODE_EXPIRY)
            
            # Delete old codes
            EmailVerificationCode.query.filter_by(email=email, used=False).delete()
            
            # Create verification code
            verification_code = EmailVerificationCode(
                email=email,
                code=code,
                expires_at=expires_at
            )
            db.session.add(verification_code)
            
            # Create user (not verified yet)
            user = User(
                email=email,
                password_hash=generate_password_hash(password),
                first_name=first_name,
                last_name=last_name,
                role=role,
                tokens=Config.INITIAL_TOKENS if role != 'administrator' else 999999,
                email_verified=False
            )
            db.session.add(user)
            db.session.flush()
            
            # Add initial token transaction
            transaction = TokenTransaction(
                user_id=user.id,
                amount=Config.INITIAL_TOKENS if role != 'administrator' else 999999,
                transaction_type='initial',
                description='Начальные токены'
            )
            db.session.add(transaction)
            db.session.commit()
            
            # Send verification code
            send_verification_code_email(email, code)
            
            return jsonify({
                'success': True,
                'redirect': url_for('verify_email', email=email),
                'message': 'Код подтверждения отправлен на email'
            })
        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {e}")
            return jsonify({'success': False, 'message': f'Ошибка регистрации: {str(e)}'}), 500
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'success': False, 'message': 'Неверный email или пароль'}), 400
        
        # Check if user has password (not OAuth-only user)
        if not user.password_hash:
            return jsonify({'success': False, 'message': 'Этот аккаунт использует вход через социальные сети'}), 400
        
        if check_password_hash(user.password_hash, password):
            login_user(user, remember=True)  # remember=True для сохранения сессии
            
            # Check daily reward
            if user.role != 'administrator':
                check_daily_reward(user)
            
            return jsonify({'success': True, 'redirect': url_for('main')})
        else:
            return jsonify({'success': False, 'message': 'Неверный email или пароль'}), 400
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def check_daily_reward(user):
    """Check and give daily reward if eligible (deprecated - use claim_daily_reward instead)"""
    if not user.last_daily_reward or (datetime.utcnow() - user.last_daily_reward).days >= 1:
        user.tokens += Config.DAILY_TOKENS
        user.last_daily_reward = datetime.utcnow()
        
        transaction = TokenTransaction(
            user_id=user.id,
            amount=Config.DAILY_TOKENS,
            transaction_type='daily',
            description='Ежедневная награда'
        )
        db.session.add(transaction)
        db.session.commit()
        return True
    return False

def can_claim_daily_reward(user):
    """Check if user can claim daily reward at 2:15 PM Moscow time"""
    moscow_tz = timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    
    # Check if it's after 2:15 PM today
    reward_time = now_moscow.replace(hour=14, minute=15, second=0, microsecond=0)
    
    # If it's before 2:15 PM, user can't claim yet
    if now_moscow < reward_time:
        return False, reward_time
    
    # Check if user already claimed today
    if user.last_daily_reward:
        last_claim_moscow = user.last_daily_reward.replace(tzinfo=timezone('UTC')).astimezone(moscow_tz)
        if last_claim_moscow.date() == now_moscow.date():
            # Already claimed today
            next_reward = (now_moscow + timedelta(days=1)).replace(hour=14, minute=15, second=0, microsecond=0)
            return False, next_reward
    
    return True, reward_time

@app.route('/api/claim_daily_reward', methods=['POST'])
@login_required
def claim_daily_reward():
    """Claim daily reward at 2:15 PM Moscow time"""
    if current_user.role == 'administrator':
        return jsonify({'success': False, 'message': 'Администраторы не могут получать ежедневные награды'}), 400
    
    can_claim, reward_time = can_claim_daily_reward(current_user)
    
    if not can_claim:
        moscow_tz = timezone('Europe/Moscow')
        now_moscow = datetime.now(moscow_tz)
        
        if now_moscow < reward_time:
            # Before 2:15 PM
            time_until = reward_time - now_moscow
            hours = time_until.seconds // 3600
            minutes = (time_until.seconds % 3600) // 60
            return jsonify({
                'success': False, 
                'message': f'Награда будет доступна в 14:15 МСК. Осталось: {hours:02d}:{minutes:02d}',
                'next_available': reward_time.isoformat()
            }), 400
        else:
            # Already claimed today
            next_reward = (now_moscow + timedelta(days=1)).replace(hour=14, minute=15, second=0, microsecond=0)
            time_until = next_reward - now_moscow
            hours = time_until.seconds // 3600
            minutes = (time_until.seconds % 3600) // 60
            return jsonify({
                'success': False,
                'message': f'Вы уже получили награду сегодня. Следующая награда через {hours:02d}:{minutes:02d}',
                'next_available': next_reward.isoformat()
            }), 400
    
    # Give reward
    current_user.tokens += Config.DAILY_TOKENS
    current_user.last_daily_reward = datetime.utcnow()
    
    transaction = TokenTransaction(
        user_id=current_user.id,
        amount=Config.DAILY_TOKENS,
        transaction_type='daily',
        description='Ежедневная награда (14:15 МСК)'
    )
    db.session.add(transaction)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Получено {Config.DAILY_TOKENS} токенов!',
        'tokens': current_user.tokens
    })

@app.route('/api/daily_reward_status', methods=['GET'])
@login_required
def daily_reward_status():
    """Get daily reward status and time until next reward"""
    if current_user.role == 'administrator':
        return jsonify({'can_claim': False, 'message': 'Администраторы не могут получать ежедневные награды'})
    
    can_claim, reward_time = can_claim_daily_reward(current_user)
    moscow_tz = timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    
    if can_claim:
        return jsonify({
            'can_claim': True,
            'message': 'Награда доступна!'
        })
    else:
        if now_moscow < reward_time:
            # Before 2:15 PM
            time_until = reward_time - now_moscow
            hours = time_until.seconds // 3600
            minutes = (time_until.seconds % 3600) // 60
            return jsonify({
                'can_claim': False,
                'message': f'Доступно в 14:15 МСК',
                'next_available': reward_time.isoformat(),
                'time_until': {
                    'hours': hours,
                    'minutes': minutes,
                    'total_seconds': int(time_until.total_seconds())
                }
            })
        else:
            # Already claimed, next is tomorrow
            next_reward = (now_moscow + timedelta(days=1)).replace(hour=14, minute=15, second=0, microsecond=0)
            time_until = next_reward - now_moscow
            hours = time_until.seconds // 3600
            minutes = (time_until.seconds % 3600) // 60
            return jsonify({
                'can_claim': False,
                'message': 'Уже получено сегодня',
                'next_available': next_reward.isoformat(),
                'time_until': {
                    'hours': hours,
                    'minutes': minutes,
                    'total_seconds': int(time_until.total_seconds())
                }
            })

@app.route('/select_expert')
@login_required
def select_expert():
    if current_user.role != 'student' or current_user.selected_expert_id:
        return redirect(url_for('main'))
    
    experts = Expert.query.all()
    return render_template('select_expert.html', experts=experts)

@app.route('/select_expert/<int:expert_id>', methods=['POST'])
@login_required
def select_expert_post(expert_id):
    expert = Expert.query.get_or_404(expert_id)
    current_user.selected_expert_id = expert_id
    db.session.commit()
    return jsonify({'success': True, 'redirect': url_for('main')})

@app.route('/api/change_expert', methods=['POST'])
@login_required
def change_expert():
    # Allow both students and teachers to select experts/avatars
    if current_user.role not in ['student', 'teacher']:
        return jsonify({'success': False, 'message': 'Доступно только для учеников и учителей'}), 403
    
    data = request.get_json()
    expert_id = data.get('expert_id')
    
    if expert_id:
        expert = Expert.query.get(expert_id)
        if not expert:
            return jsonify({'success': False, 'message': 'Эксперт не найден'}), 404
        current_user.selected_expert_id = expert_id
    else:
        current_user.selected_expert_id = None
    
    db.session.commit()
    return jsonify({'success': True, 'message': 'Аватар успешно изменен'})

@app.route('/main')
@login_required
def main():
    subjects = Subject.query.all()
    return render_template('main.html', subjects=subjects)

@app.route('/api/subjects')
@login_required
def get_subjects():
    subjects = Subject.query.all()
    return jsonify([{'id': s.id, 'name': s.name, 'description': s.description} for s in subjects])

@app.route('/lesson/<int:subject_id>')
@login_required
def lesson_page(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    expert = current_user.expert if current_user.selected_expert_id else None
    return render_template('lesson.html', subject=subject, expert=expert)

@app.route('/api/create_lesson', methods=['POST'])
@login_required
def create_lesson():
    try:
        data = request.get_json()
        subject_id = data.get('subject_id')
        material_text = data.get('material_text', '')
        material_image = data.get('material_image', '')
        
        if not material_text and not material_image:
            return jsonify({'success': False, 'message': 'Добавьте материал для урока'}), 400
        
        # Check tokens
        if current_user.role != 'administrator' and current_user.tokens < Config.LESSON_COST:
            return jsonify({'success': False, 'message': 'Недостаточно токенов'}), 400
        
        # Check if GigaChat API is configured
        if not Config.GIGA_API_KEY:
            return jsonify({'success': False, 'message': 'GigaChat API не настроен. Обратитесь к администратору.'}), 500
        
        # Get expert prompt
        expert_prompt = None
        if current_user.selected_expert_id:
            expert = Expert.query.get(current_user.selected_expert_id)
            if expert:
                expert_prompt = expert.prompt
        
        # For image-only lessons, use a default text
        if not material_text and material_image:
            material_text = "Учебный материал на изображении"
        
        # Analyze material
        explanation = giga_api.analyze_material(material_text, expert_prompt)
        if not explanation:
            return jsonify({'success': False, 'message': 'Ошибка анализа материала. Проверьте настройки API.'}), 500
        
        # Generate quiz
        num_questions = min(max(5, len(material_text.split()) // 50), 15) if material_text else 10
        questions_data = giga_api.generate_quiz(material_text, explanation, expert_prompt, num_questions)
        
        if not questions_data or len(questions_data) == 0:
            return jsonify({'success': False, 'message': 'Ошибка генерации викторины. Проверьте настройки API или попробуйте позже.'}), 500
        
        # Create lesson
        subject = Subject.query.get(subject_id)
        if not subject:
            return jsonify({'success': False, 'message': 'Предмет не найден'}), 400
        
        lesson = Lesson(
            title=f"Урок по {subject.name}",
            material_text=material_text,
            material_image=material_image,
            subject_id=subject_id,
            created_by=current_user.id
        )
        db.session.add(lesson)
        db.session.flush()
        
        # Create quiz
        quiz = Quiz(
            lesson_id=lesson.id,
            title=f"Викторина к уроку {lesson.id}"
        )
        db.session.add(quiz)
        db.session.flush()
        
        # Create questions
        for idx, q_data in enumerate(questions_data):
            question = Question(
                quiz_id=quiz.id,
                question_text=q_data.get('question_text', ''),
                question_type=q_data.get('question_type', 'single'),
                correct_answer=json.dumps(q_data.get('correct_answer', ''), ensure_ascii=False),
                options=json.dumps(q_data.get('options', []), ensure_ascii=False) if q_data.get('options') else None,
                order=idx
            )
            db.session.add(question)
        
        # Deduct tokens
        if current_user.role != 'administrator':
            current_user.tokens -= Config.LESSON_COST
            transaction = TokenTransaction(
                user_id=current_user.id,
                amount=-Config.LESSON_COST,
                transaction_type='lesson_cost',
                description=f'Создание урока {lesson.id}'
            )
            db.session.add(transaction)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'lesson_id': lesson.id,
            'explanation': explanation,
            'quiz_id': quiz.id
        })
    except Exception as e:
        db.session.rollback()
        print(f"Lesson creation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Ошибка создания урока: {str(e)}'}), 500

@app.route('/quiz/<int:quiz_id>')
@login_required
def quiz_page(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    questions = Question.query.filter_by(quiz_id=quiz_id).order_by(Question.order).all()
    
    # Convert questions to JSON format
    questions_data = []
    for q in questions:
        q_data = {
            'id': q.id,
            'question_text': q.question_text,
            'question_type': q.question_type,
            'options': json.loads(q.options) if q.options else None
        }
        questions_data.append(q_data)
    
    return render_template('quiz.html', quiz=quiz, questions=questions_data)

@app.route('/api/submit_quiz', methods=['POST'])
@login_required
def submit_quiz():
    data = request.get_json()
    quiz_id = data.get('quiz_id')
    answers = data.get('answers', {})
    
    quiz = Quiz.query.get_or_404(quiz_id)
    questions = Question.query.filter_by(quiz_id=quiz_id).order_by(Question.order).all()
    
    user_answers = []
    correct_count = 0
    total_tokens_earned = 0
    
    for question in questions:
        user_answer = answers.get(str(question.id), '')
        correct_answer = json.loads(question.correct_answer)
        
        # Check if answer is correct
        is_correct = False
        if question.question_type == 'text':
            is_correct = str(user_answer).lower().strip() == str(correct_answer).lower().strip()
        elif question.question_type == 'single':
            is_correct = str(user_answer) == str(correct_answer)
        elif question.question_type == 'multiple':
            user_ans_list = user_answer if isinstance(user_answer, list) else [user_answer]
            correct_ans_list = correct_answer if isinstance(correct_answer, list) else [correct_answer]
            is_correct = set(user_ans_list) == set(correct_ans_list)
        
        # Save answer
        answer_obj = UserAnswer(
            user_id=current_user.id,
            question_id=question.id,
            answer=json.dumps(user_answer, ensure_ascii=False),
            is_correct=is_correct
        )
        db.session.add(answer_obj)
        user_answers.append({'is_correct': is_correct})
        
        # Обновление статистики рейтинга и подсчет правильных ответов
        if is_correct:
            correct_count += 1
        
            if current_user.role != 'administrator':
            current_user.total_answers += 1
            if is_correct:
                current_user.total_correct_answers += 1
                current_user.tokens += Config.CORRECT_ANSWER_REWARD
                total_tokens_earned += Config.CORRECT_ANSWER_REWARD
                # Начисление очков рейтинга за правильный ответ
                current_user.rating += 10  # 10 очков за правильный ответ
                transaction = TokenTransaction(
                    user_id=current_user.id,
                    amount=Config.CORRECT_ANSWER_REWARD,
                    transaction_type='answer_reward',
                    description=f'Правильный ответ на вопрос {question.id}'
                )
                db.session.add(transaction)
            else:
                # Небольшой штраф за неправильный ответ (но не отрицательный рейтинг)
                current_user.rating = max(0, current_user.rating - 1)
    
    # Обновление статистики викторин
    if current_user.role != 'administrator':
        current_user.total_quizzes += 1
        # Бонус за идеальное прохождение викторины
        if correct_count == len(questions) and len(questions) > 0:
            current_user.rating += 50  # 50 дополнительных очков за идеальную викторину
    
    # Check for achievements (исправлено: correct_count уже обновлен выше)
    if correct_count == len(questions) and len(questions) > 0:
        achievement = Achievement.query.filter_by(condition='perfect_quiz').first()
        if achievement:
            user_achievement = UserAchievement.query.filter_by(
                user_id=current_user.id,
                achievement_id=achievement.id
            ).first()
            if not user_achievement:
                user_achievement = UserAchievement(
                    user_id=current_user.id,
                    achievement_id=achievement.id
                )
                db.session.add(user_achievement)
    
    # Generate summary
    lesson = quiz.lesson
    expert_prompt = None
    if current_user.selected_expert_id:
        expert = Expert.query.get(current_user.selected_expert_id)
        if expert:
            expert_prompt = expert.prompt
    
    summary = giga_api.generate_lesson_summary(
        lesson.material_text or '',
        user_answers,
        expert_prompt
    )
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'correct_count': correct_count,
        'total_count': len(questions),
        'tokens_earned': total_tokens_earned,
        'summary': summary
    })

@app.route('/leaderboard')
@login_required
def leaderboard():
    """Страница рейтинга учеников"""
    # Получаем всех учеников, отсортированных по рейтингу
    students = User.query.filter_by(role='student').order_by(User.rating.desc(), User.total_correct_answers.desc()).all()
    
    # Находим позицию текущего пользователя
    current_user_position = None
    if current_user.role == 'student':
        for idx, student in enumerate(students, 1):
            if student.id == current_user.id:
                current_user_position = idx
                break
    
    # Вычисляем процент правильных ответов для каждого ученика
    leaderboard_data = []
    for idx, student in enumerate(students, 1):
        accuracy = 0
        if student.total_answers > 0:
            accuracy = round((student.total_correct_answers / student.total_answers) * 100, 1)
        
        leaderboard_data.append({
            'position': idx,
            'user': student,
            'rating': student.rating,
            'total_quizzes': student.total_quizzes,
            'total_correct_answers': student.total_correct_answers,
            'total_answers': student.total_answers,
            'accuracy': accuracy,
            'is_current_user': student.id == current_user.id
        })
    
    return render_template('leaderboard.html', 
                         leaderboard=leaderboard_data,
                         current_user_position=current_user_position)

@app.route('/achievements')
@login_required
def achievements():
    user_achievements = UserAchievement.query.filter_by(user_id=current_user.id).all()
    all_achievements = Achievement.query.all()
    
    earned_ids = {ua.achievement_id for ua in user_achievements}
    
    return render_template('achievements.html', 
                         earned_achievements=[ua.achievement for ua in user_achievements],
                         all_achievements=all_achievements,
                         earned_ids=earned_ids,
                         daily_tokens=Config.DAILY_TOKENS)

# Email verification functions
def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def send_verification_code_email(email, code):
    """Отправка кода подтверждения на email"""
    try:
        # Проверяем, настроена ли почта
        if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
            # Если почта не настроена, выводим в консоль (для разработки)
            print(f"⚠️ Email не настроен. Код подтверждения для {email}: {code}")
            print("💡 Для настройки email добавьте в .env файл:")
            print("   MAIL_SERVER=smtp.gmail.com")
            print("   MAIL_PORT=587")
            print("   MAIL_USE_TLS=true")
            print("   MAIL_USERNAME=ваш-email@gmail.com")
            print("   MAIL_PASSWORD=ваш-пароль-приложения")
            return True
        
        # Создаем сообщение с правильной кодировкой UTF-8
        # Кодируем тему письма для поддержки кириллицы
        subject_encoded = Header('Код подтверждения - AI Бот', 'utf-8').encode()
        msg = Message(
            subject=subject_encoded,
            recipients=[email],
            charset='utf-8'
        )
        
        # Текстовая версия письма
        msg.body = f'''Здравствуйте!

Ваш код подтверждения для регистрации в AI Бот:

{code}

Код действителен в течение {app.config['VERIFICATION_CODE_EXPIRY']} минут.

Если вы не регистрировались в AI Бот, проигнорируйте это письмо.

С уважением,
Команда AI Бот'''
        
        # HTML версия письма
        msg.html = f'''<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #007bff;">Код подтверждения</h2>
        <p>Здравствуйте!</p>
        <p>Ваш код подтверждения для регистрации в AI Бот:</p>
        <div style="background-color: #f8f9fa; border: 2px solid #007bff; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
            <h1 style="color: #007bff; font-size: 32px; margin: 0; letter-spacing: 5px;">{code}</h1>
        </div>
        <p>Код действителен в течение <strong>{app.config['VERIFICATION_CODE_EXPIRY']} минут</strong>.</p>
        <p style="color: #666; font-size: 12px; margin-top: 30px;">
            Если вы не регистрировались в AI Бот, проигнорируйте это письмо.
        </p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
        <p style="color: #999; font-size: 12px;">
            С уважением,<br>
            Команда AI Бот
        </p>
    </div>
</body>
</html>'''
        
        # Отправляем письмо
        mail.send(msg)
        print(f"✓ Код подтверждения отправлен на {email}")
        return True
        
    except Exception as e:
        # В случае ошибки выводим в консоль и продолжаем работу
        print(f"✗ Ошибка отправки email на {email}: {e}")
        print(f"⚠️ Код подтверждения для {email}: {code}")
        print("💡 Проверьте настройки email в файле .env")
        return True  # Возвращаем True, чтобы не блокировать регистрацию

@app.route('/api/send_verification_code', methods=['POST'])
def send_verification_code():
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'success': False, 'message': 'Email не указан'}), 400
    
    # Generate code
    code = generate_verification_code()
    expires_at = datetime.utcnow() + timedelta(minutes=Config.VERIFICATION_CODE_EXPIRY)
    
    # Delete old codes for this email
    EmailVerificationCode.query.filter_by(email=email, used=False).delete()
    
    # Create new code
    verification_code = EmailVerificationCode(
        email=email,
        code=code,
        expires_at=expires_at
    )
    db.session.add(verification_code)
    db.session.commit()
    
    # Send code (in production, send via email)
    send_verification_code_email(email, code)
    
    return jsonify({'success': True, 'message': 'Код отправлен на email'})

@app.route('/verify_email', methods=['GET', 'POST'])
def verify_email():
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email')
        code = data.get('code')
        
        if not email or not code:
            return jsonify({'success': False, 'message': 'Заполните все поля'}), 400
        
        # Find verification code
        verification = EmailVerificationCode.query.filter_by(
            email=email,
            code=code,
            used=False
        ).first()
        
        if not verification:
            return jsonify({'success': False, 'message': 'Неверный код'}), 400
        
        if verification.expires_at < datetime.utcnow():
            return jsonify({'success': False, 'message': 'Код истек'}), 400
        
        # Mark code as used
        verification.used = True
        
        # Verify user email
        user = User.query.filter_by(email=email).first()
        if user:
            user.email_verified = True
            db.session.commit()
            
            login_user(user, remember=True)
            return jsonify({
                'success': True,
                'redirect': url_for('select_expert') if user.role == 'student' else url_for('main')
            })
        else:
            return jsonify({'success': False, 'message': 'Пользователь не найден'}), 400
    
    email = request.args.get('email')
    if not email:
        return redirect(url_for('register'))
    
    return render_template('verify_email.html', email=email)

# OAuth routes
@app.route('/oauth/<provider>')
def oauth_login(provider):
    if provider == 'vk':
        if not Config.VK_APP_ID:
            flash('VK OAuth не настроен', 'error')
            return redirect(url_for('login'))
        
        redirect_uri = url_for('oauth_callback', provider='vk', _external=True)
        vk_auth_url = f"https://oauth.vk.com/authorize?client_id={Config.VK_APP_ID}&redirect_uri={redirect_uri}&response_type=code&scope=email"
        return redirect(vk_auth_url)
    
    elif provider == 'google':
        if not Config.GOOGLE_CLIENT_ID:
            flash('Google OAuth не настроен', 'error')
            return redirect(url_for('login'))
        
        redirect_uri = url_for('oauth_callback', provider='google', _external=True)
        google_auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={Config.GOOGLE_CLIENT_ID}&"
            f"redirect_uri={redirect_uri}&"
            f"response_type=code&"
            f"scope=openid email profile"
        )
        return redirect(google_auth_url)
    
    return redirect(url_for('login'))

@app.route('/oauth/<provider>/callback')
def oauth_callback(provider):
    code = request.args.get('code')
    if not code:
        flash('Ошибка авторизации', 'error')
        return redirect(url_for('login'))
    
    try:
        if provider == 'vk':
            # Exchange code for access token
            redirect_uri = url_for('oauth_callback', provider='vk', _external=True)
            token_response = requests.get(
                'https://oauth.vk.com/access_token',
                params={
                    'client_id': Config.VK_APP_ID,
                    'client_secret': Config.VK_APP_SECRET,
                    'redirect_uri': redirect_uri,
                    'code': code
                }
            )
            token_data = token_response.json()
            
            if 'access_token' not in token_data:
                flash('Ошибка получения токена VK', 'error')
                return redirect(url_for('login'))
            
            access_token = token_data['access_token']
            user_id = token_data['user_id']
            email = token_data.get('email')
            
            # Get user info
            user_info_response = requests.get(
                'https://api.vk.com/method/users.get',
                params={
                    'user_ids': user_id,
                    'access_token': access_token,
                    'v': '5.131',
                    'fields': 'first_name,last_name'
                }
            )
            user_info = user_info_response.json().get('response', [{}])[0]
            
            first_name = user_info.get('first_name', '')
            last_name = user_info.get('last_name', '')
            
            # Find or create user
            user = User.query.filter_by(vk_id=str(user_id)).first()
            if not user and email:
                user = User.query.filter_by(email=email).first()
            
            if not user:
                if not email:
                    flash('Не удалось получить email из VK', 'error')
                    return redirect(url_for('register'))
                
                user = User(
                    email=email,
                    password_hash=None,
                    first_name=first_name,
                    last_name=last_name,
                    role='student',
                    tokens=Config.INITIAL_TOKENS,
                    vk_id=str(user_id),
                    email_verified=True
                )
                db.session.add(user)
                db.session.flush()
                
                transaction = TokenTransaction(
                    user_id=user.id,
                    amount=Config.INITIAL_TOKENS,
                    transaction_type='initial',
                    description='Начальные токены'
                )
                db.session.add(transaction)
            else:
                if not user.vk_id:
                    user.vk_id = str(user_id)
                # Update names if they're missing or empty
                if not user.first_name and first_name:
                    user.first_name = first_name
                if not user.last_name and last_name:
                    user.last_name = last_name
                user.email_verified = True
            
            db.session.commit()
            login_user(user, remember=True)
            
            if user.role == 'student' and not user.selected_expert_id:
                return redirect(url_for('select_expert'))
            return redirect(url_for('main'))
        
        elif provider == 'google':
            # Exchange code for access token
            redirect_uri = url_for('oauth_callback', provider='google', _external=True)
            token_response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id': Config.GOOGLE_CLIENT_ID,
                    'client_secret': Config.GOOGLE_CLIENT_SECRET,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': redirect_uri
                }
            )
            token_data = token_response.json()
            
            if 'access_token' not in token_data:
                flash('Ошибка получения токена Google', 'error')
                return redirect(url_for('login'))
            
            access_token = token_data['access_token']
            
            # Get user info
            user_info_response = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {access_token}'}
            )
            user_info = user_info_response.json()
            
            google_id = user_info.get('id')
            email = user_info.get('email')
            first_name = user_info.get('given_name', '')
            last_name = user_info.get('family_name', '')
            
            # Find or create user
            user = User.query.filter_by(google_id=google_id).first()
            if not user and email:
                user = User.query.filter_by(email=email).first()
            
            if not user:
                if not email:
                    flash('Не удалось получить email из Google', 'error')
                    return redirect(url_for('register'))
                
                user = User(
                    email=email,
                    password_hash=None,
                    first_name=first_name,
                    last_name=last_name,
                    role='student',
                    tokens=Config.INITIAL_TOKENS,
                    google_id=google_id,
                    email_verified=True
                )
                db.session.add(user)
                db.session.flush()
                
                transaction = TokenTransaction(
                    user_id=user.id,
                    amount=Config.INITIAL_TOKENS,
                    transaction_type='initial',
                    description='Начальные токены'
                )
                db.session.add(transaction)
            else:
                if not user.google_id:
                    user.google_id = google_id
                # Update names if they're missing or empty
                if not user.first_name and first_name:
                    user.first_name = first_name
                if not user.last_name and last_name:
                    user.last_name = last_name
                user.email_verified = True
            
            db.session.commit()
            login_user(user, remember=True)
            
            if user.role == 'student' and not user.selected_expert_id:
                return redirect(url_for('select_expert'))
            return redirect(url_for('main'))
    
    except Exception as e:
        print(f"OAuth error: {e}")
        flash('Ошибка авторизации', 'error')
        return redirect(url_for('login'))
    
    return redirect(url_for('login'))

@app.route('/api/link_vk', methods=['POST'])
@login_required
def link_vk():
    # Redirect to VK OAuth for linking
    redirect_uri = url_for('link_vk_callback', _external=True)
    vk_auth_url = f"https://oauth.vk.com/authorize?client_id={Config.VK_APP_ID}&redirect_uri={redirect_uri}&response_type=code&scope=email"
    return jsonify({'success': True, 'redirect': vk_auth_url})

@app.route('/link_vk/callback')
@login_required
def link_vk_callback():
    code = request.args.get('code')
    if not code:
        flash('Ошибка привязки VK', 'error')
        return redirect(url_for('profile'))
    
    try:
        redirect_uri = url_for('link_vk_callback', _external=True)
        token_response = requests.get(
            'https://oauth.vk.com/access_token',
            params={
                'client_id': Config.VK_APP_ID,
                'client_secret': Config.VK_APP_SECRET,
                'redirect_uri': redirect_uri,
                'code': code
            }
        )
        token_data = token_response.json()
        
        if 'access_token' in token_data:
            user_id = token_data['user_id']
            current_user.vk_id = str(user_id)
            db.session.commit()
            flash('VK успешно привязан', 'success')
        else:
            flash('Ошибка привязки VK', 'error')
    except Exception as e:
        print(f"Link VK error: {e}")
        flash('Ошибка привязки VK', 'error')
    
    return redirect(url_for('profile'))

@app.route('/profile')
@login_required
def profile():
    # Allow both students and teachers to select experts/avatars
    experts = Expert.query.all() if current_user.role in ['student', 'teacher'] else []
    return render_template('profile.html', experts=experts)

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/api/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'success': False, 'message': 'Заполните все поля'}), 400
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Пароль должен быть не менее 6 символов'}), 400
    
    # Проверяем текущий пароль
    if not current_user.password_hash:
        # Пользователь без пароля (OAuth)
        return jsonify({'success': False, 'message': 'У вас нет пароля. Установите пароль через восстановление.'}), 400
    
    if not check_password_hash(current_user.password_hash, current_password):
        return jsonify({'success': False, 'message': 'Неверный текущий пароль'}), 400
    
    # Устанавливаем новый пароль
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Пароль успешно изменен'})

@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.role != 'administrator':
        return redirect(url_for('main'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@app.route('/api/admin/user/<int:user_id>', methods=['DELETE'])
@login_required
def admin_delete_user(user_id):
    if current_user.role != 'administrator':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    if user_id == current_user.id:
        return jsonify({'success': False, 'message': 'Нельзя удалить самого себя'}), 400
    
    user = User.query.get_or_404(user_id)
    
    # Удаляем связанные данные
    UserAnswer.query.filter_by(user_id=user_id).delete()
    UserAchievement.query.filter_by(user_id=user_id).delete()
    TokenTransaction.query.filter_by(user_id=user_id).delete()
    
    # Удаляем уроки, созданные пользователем
    lessons = Lesson.query.filter_by(created_by=user_id).all()
    for lesson in lessons:
        if lesson.quiz:
            Question.query.filter_by(quiz_id=lesson.quiz.id).delete()
            Quiz.query.filter_by(id=lesson.quiz.id).delete()
        Lesson.query.filter_by(id=lesson.id).delete()
    
    # Удаляем экспертов, созданных пользователем
    Expert.query.filter_by(created_by=user_id).update({'created_by': None})
    
    # Удаляем предметы, созданные пользователем
    Subject.query.filter_by(created_by=user_id).update({'created_by': None})
    
    # Удаляем пользователя
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Пользователь удален'})

@app.route('/api/change_theme', methods=['POST'])
@login_required
def change_theme():
    data = request.get_json()
    theme = data.get('theme')
    theme_id = data.get('theme_id')
    
    if theme_id:
        # Кастомная тема
        custom_theme = Theme.query.get(theme_id)
        if not custom_theme:
            return jsonify({'success': False, 'message': 'Тема не найдена'}), 404
        
        # Проверяем, что тема одобрена или пользователь её создатель
        if not custom_theme.is_approved and custom_theme.created_by != current_user.id:
            return jsonify({'success': False, 'message': 'Тема еще не одобрена'}), 403
        
        # Проверяем, что пользователь купил тему или она бесплатная
        if custom_theme.price > 0:
            purchase = ThemePurchase.query.filter_by(theme_id=theme_id, user_id=current_user.id).first()
            if not purchase and custom_theme.created_by != current_user.id:
                return jsonify({'success': False, 'message': 'Тема не куплена'}), 403
        
        current_user.theme = 'custom'
        current_user.custom_theme_id = theme_id
    elif theme in ['light', 'dark', 'base']:
        current_user.theme = theme
        current_user.custom_theme_id = None
    else:
        return jsonify({'success': False, 'message': 'Неверная тема'}), 400
    
        db.session.commit()
        return jsonify({'success': True})

@app.route('/api/switch_role', methods=['POST'])
@login_required
def switch_role():
    # Only allow for admin@example.com
    if current_user.email != 'admin@example.com':
        return jsonify({'success': False, 'message': 'Доступно только для администратора'}), 403
    
    data = request.get_json()
    role = data.get('role')
    if role in ['student', 'teacher', 'administrator']:
        current_user.role = role
        db.session.commit()
        return jsonify({'success': True, 'redirect': url_for('main')})
    return jsonify({'success': False, 'message': 'Неверная роль'}), 400

# Admin routes
@app.route('/admin/subjects', methods=['GET', 'POST'])
@login_required
def admin_subjects():
    if current_user.role != 'administrator':
        return redirect(url_for('main'))
    
    if request.method == 'POST':
        data = request.get_json()
        subject = Subject(
            name=data.get('name'),
            description=data.get('description'),
            created_by=current_user.id
        )
        db.session.add(subject)
        db.session.commit()
        return jsonify({'success': True, 'subject_id': subject.id})
    
    subjects = Subject.query.all()
    return render_template('admin_subjects.html', subjects=subjects)

@app.route('/api/admin/subject/<int:subject_id>', methods=['PUT', 'DELETE'])
@login_required
def admin_subject_manage(subject_id):
    if current_user.role != 'administrator':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    subject = Subject.query.get_or_404(subject_id)
    
    if request.method == 'PUT':
        data = request.get_json()
        subject.name = data.get('name', subject.name)
        subject.description = data.get('description', subject.description)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Предмет обновлен'})
    
    elif request.method == 'DELETE':
        # Проверяем, есть ли уроки по этому предмету
        if subject.lessons:
            return jsonify({'success': False, 'message': 'Нельзя удалить предмет, у которого есть уроки'}), 400
        
        db.session.delete(subject)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Предмет удален'})

@app.route('/admin/experts', methods=['GET', 'POST'])
@login_required
def admin_experts():
    if current_user.role != 'administrator':
        return redirect(url_for('main'))
    
    if request.method == 'POST':
        data = request.get_json()
        description = data.get('description')
        name = data.get('name')
        
        expert_prompt, avatar_description, avatar_image_base64 = giga_api.generate_expert(description)
        
        # Save avatar image if generated
        avatar_url = None
        if avatar_image_base64:
            import base64
            from datetime import datetime
            # Save base64 image to file
            avatar_filename = f"expert_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{name.replace(' ', '_')}.png"
            avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars')
            os.makedirs(avatar_path, exist_ok=True)
            avatar_filepath = os.path.join(avatar_path, avatar_filename)
            
            try:
                image_data = base64.b64decode(avatar_image_base64)
                with open(avatar_filepath, 'wb') as f:
                    f.write(image_data)
                avatar_url = f"uploads/avatars/{avatar_filename}"
            except Exception as e:
                print(f"Error saving avatar image: {e}")
                avatar_url = None
        
        expert = Expert(
            name=name,
            description=description,
            prompt=expert_prompt,
            avatar_url=avatar_url or avatar_description,  # Use generated image or description
            created_by=current_user.id
        )
        db.session.add(expert)
        db.session.commit()
        return jsonify({'success': True, 'expert_id': expert.id, 'avatar_generated': avatar_url is not None})
    
    experts = Expert.query.all()
    return render_template('admin_experts.html', experts=experts)

@app.route('/api/admin/expert/<int:expert_id>', methods=['PUT', 'DELETE'])
@login_required
def admin_expert_manage(expert_id):
    if current_user.role != 'administrator':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    expert = Expert.query.get_or_404(expert_id)
    
    if request.method == 'PUT':
        data = request.get_json()
        expert.name = data.get('name', expert.name)
        expert.description = data.get('description', expert.description)
        
        # Обновление промпта, если изменилось описание
        if 'description' in data and data['description'] != expert.description:
            expert_prompt, avatar_description, _ = giga_api.generate_expert(data['description'])
            if expert_prompt:
                expert.prompt = expert_prompt
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Эксперт обновлен'})
    
    elif request.method == 'DELETE':
        # Проверяем, используется ли эксперт
        users_count = User.query.filter_by(selected_expert_id=expert_id).count()
        if users_count > 0:
            return jsonify({'success': False, 'message': f'Нельзя удалить эксперта, который выбран у {users_count} пользователей'}), 400
        
        # Удаляем файл аватара, если он есть
        if expert.avatar_url and expert.avatar_url.startswith('uploads/'):
            avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], expert.avatar_url.replace('uploads/', ''))
            if os.path.exists(avatar_path):
                try:
                    os.remove(avatar_path)
                except Exception as e:
                    print(f"Error deleting avatar file: {e}")
        
        db.session.delete(expert)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Эксперт удален'})

@app.route('/api/admin/expert/<int:expert_id>/avatar', methods=['POST'])
@login_required
def admin_expert_upload_avatar(expert_id):
    if current_user.role != 'administrator':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    expert = Expert.query.get_or_404(expert_id)
    
    if 'avatar' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не загружен'}), 400
    
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Файл не выбран'}), 400
    
    # Проверяем расширение
    if file and file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
        from datetime import datetime
        filename = secure_filename(file.filename)
        avatar_filename = f"expert_{expert_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}"
        avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars')
        os.makedirs(avatar_path, exist_ok=True)
        avatar_filepath = os.path.join(avatar_path, avatar_filename)
        
        # Удаляем старый аватар, если есть
        if expert.avatar_url and expert.avatar_url.startswith('uploads/'):
            old_avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], expert.avatar_url.replace('uploads/', ''))
            if os.path.exists(old_avatar_path):
                try:
                    os.remove(old_avatar_path)
                except Exception as e:
                    print(f"Error deleting old avatar: {e}")
        
        file.save(avatar_filepath)
        expert.avatar_url = f"uploads/avatars/{avatar_filename}"
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Аватар обновлен', 'avatar_url': expert.avatar_url})
    
    return jsonify({'success': False, 'message': 'Неподдерживаемый формат файла'}), 400

# Teacher routes
@app.route('/teacher/create_lesson')
@login_required
def teacher_create_lesson():
    if current_user.role not in ['teacher', 'administrator']:
        return redirect(url_for('main'))
    
    subjects = Subject.query.all()
    return render_template('teacher_create_lesson.html', subjects=subjects)

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Support nested paths like avatars/expert_123.png
    directory = app.config['UPLOAD_FOLDER']
    return send_from_directory(directory, filename)

# Theme routes
@app.route('/themes/create', methods=['GET', 'POST'])
@login_required
def create_theme():
    if request.method == 'POST':
        data = request.get_json()
        
        # Валидация цены
        price = int(data.get('price', 0))
        if price < 0 or (price > 0 and price < 20) or price > 300:
            return jsonify({'success': False, 'message': 'Цена должна быть 0 (бесплатно) или от 20 до 300 токенов'}), 400
        
        theme = Theme(
            name=data.get('name'),
            description=data.get('description'),
            created_by=current_user.id,
            price=price,
            bg_primary=data.get('bg_primary', '#ffffff'),
            bg_secondary=data.get('bg_secondary', '#f5f5f5'),
            bg_tertiary=data.get('bg_tertiary'),
            text_primary=data.get('text_primary', '#1a1a1a'),
            text_secondary=data.get('text_secondary', '#666666'),
            accent=data.get('accent', '#007bff'),
            accent_hover=data.get('accent_hover', '#0056b3'),
            accent_dark=data.get('accent_dark'),
            border=data.get('border', '#dddddd'),
            success=data.get('success', '#28a745'),
            error=data.get('error', '#dc3545'),
            card_bg=data.get('card_bg', '#ffffff'),
            card_bg_secondary=data.get('card_bg_secondary'),
            shadow=data.get('shadow'),
            nav_home_color=data.get('nav_home_color'),
            nav_achievements_color=data.get('nav_achievements_color'),
            nav_leaderboard_color=data.get('nav_leaderboard_color'),
            nav_profile_color=data.get('nav_profile_color'),
            nav_settings_color=data.get('nav_settings_color')
        )
        db.session.add(theme)
        db.session.flush()
        
        # Добавляем иконки
        icons_data = data.get('icons', [])
        for icon_data in icons_data:
            icon = ThemeIcon(
                theme_id=theme.id,
                icon_name=icon_data.get('icon_name'),
                usage_location=icon_data.get('usage_location'),
                icon_url=icon_data.get('icon_url'),
                order=icon_data.get('order', 0)
            )
            db.session.add(icon)
        
        db.session.commit()
        return jsonify({'success': True, 'theme_id': theme.id, 'message': 'Тема создана и отправлена на модерацию'})
    
    return render_template('create_theme.html')

@app.route('/themes/market')
@login_required
def themes_market():
    # Показываем только одобренные темы
    themes = Theme.query.filter_by(is_approved=True, is_active=True).order_by(Theme.created_at.desc()).all()
    
    # Проверяем, какие темы уже куплены пользователем
    purchased_theme_ids = {p.theme_id for p in ThemePurchase.query.filter_by(user_id=current_user.id).all()}
    
    # Проверяем, какие темы созданы пользователем
    user_theme_ids = {t.id for t in Theme.query.filter_by(created_by=current_user.id).all()}
    
    themes_data = []
    for theme in themes:
        is_purchased = theme.id in purchased_theme_ids or theme.id in user_theme_ids or theme.price == 0
        themes_data.append({
            'theme': theme,
            'is_purchased': is_purchased,
            'purchases_count': len(theme.purchases)
        })
    
    return render_template('themes_market.html', themes=themes_data)

@app.route('/api/themes/purchase/<int:theme_id>', methods=['POST'])
@login_required
def purchase_theme(theme_id):
    theme = Theme.query.get_or_404(theme_id)
    
    if not theme.is_approved:
        return jsonify({'success': False, 'message': 'Тема еще не одобрена'}), 403
    
    if theme.price == 0:
        # Бесплатная тема
        current_user.theme = 'custom'
        current_user.custom_theme_id = theme_id
        db.session.commit()
        return jsonify({'success': True, 'message': 'Тема применена'})
    
    # Проверяем, не куплена ли уже тема
    existing_purchase = ThemePurchase.query.filter_by(theme_id=theme_id, user_id=current_user.id).first()
    if existing_purchase:
        current_user.theme = 'custom'
        current_user.custom_theme_id = theme_id
        db.session.commit()
        return jsonify({'success': True, 'message': 'Тема применена'})
    
    # Проверяем баланс
    if current_user.tokens < theme.price:
        return jsonify({'success': False, 'message': 'Недостаточно токенов'}), 400
    
    # Вычисляем комиссию (20%)
    creator_received = int(theme.price * 0.8)
    
    # Создаем покупку
    purchase = ThemePurchase(
        theme_id=theme_id,
        user_id=current_user.id,
        price_paid=theme.price,
        creator_received=creator_received
    )
    db.session.add(purchase)
    
    # Списываем токены у покупателя
    current_user.tokens -= theme.price
    db.session.add(TokenTransaction(
        user_id=current_user.id,
        amount=-theme.price,
        transaction_type='theme_purchase',
        description=f'Покупка темы "{theme.name}"'
    ))
    
    # Начисляем токены создателю (если это не сам пользователь)
    if theme.created_by != current_user.id:
        creator = User.query.get(theme.created_by)
        if creator:
            creator.tokens += creator_received
            db.session.add(TokenTransaction(
                user_id=creator.id,
                amount=creator_received,
                transaction_type='theme_sale',
                description=f'Продажа темы "{theme.name}"'
            ))
    
    # Применяем тему
    current_user.theme = 'custom'
    current_user.custom_theme_id = theme_id
    
    db.session.commit()
    return jsonify({'success': True, 'message': 'Тема успешно куплена и применена', 'tokens': current_user.tokens})

@app.route('/admin/themes')
@login_required
def admin_themes():
    if current_user.role != 'administrator':
        return redirect(url_for('main'))
    
    # Темы на модерации
    pending_themes = Theme.query.filter_by(is_approved=False, is_active=True).order_by(Theme.created_at.desc()).all()
    # Одобренные темы
    approved_themes = Theme.query.filter_by(is_approved=True, is_active=True).order_by(Theme.created_at.desc()).all()
    
    return render_template('admin_themes.html', pending_themes=pending_themes, approved_themes=approved_themes)

@app.route('/api/admin/theme/<int:theme_id>/approve', methods=['POST'])
@login_required
def approve_theme(theme_id):
    if current_user.role != 'administrator':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    theme = Theme.query.get_or_404(theme_id)
    theme.is_approved = True
    theme.approved_at = datetime.utcnow()
    theme.approved_by = current_user.id
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Тема одобрена'})

@app.route('/api/admin/theme/<int:theme_id>/reject', methods=['POST'])
@login_required
def reject_theme(theme_id):
    if current_user.role != 'administrator':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    theme = Theme.query.get_or_404(theme_id)
    theme.is_active = False
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Тема отклонена'})

