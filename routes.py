# Routes file for AI Bot Flask application
# This file contains all Flask routes and logic for the application

import json
import os
import random
import string
import uuid
from datetime import datetime, timedelta
from email.header import Header
from urllib.parse import urlencode

import markdown
import requests
from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message
from pytz import timezone
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app import app, login_manager, mail, is_locked_out, record_failed_attempt, reset_failed_attempts
from config import Config
from extensions import db
from models import (
    Achievement,
    EmailVerificationCode,
    Expert,
    Lesson,
    Question,
    Quiz,
    QuizAttempt,
    Subject,
    TokenTransaction,
    User,
    UserAchievement,
    UserAnswer,
)
from openrouter_api import OpenRouterAPI

openrouter_api = OpenRouterAPI()

# Регистрация нового пользователя с валидацией
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    elif request.method == 'POST':
        data = request.get_json()
        
        # Проверка наличия данных
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
        
        # Проверка обязательных полей
        if not all([data.get('email'), data.get('password'), data.get('first_name'), data.get('last_name'), data.get('role')]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        # Проверка уникальности email
        existing_user = User.query.filter_by(email=data.get('email')).first()
        if existing_user:
            return jsonify({'success': False, 'message': 'User with this email already exists'}), 400
        
        # Создание нового пользователя
        try:
            new_user = User(
                email=data.get('email'),
                password_hash=generate_password_hash(data.get('password')),
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                role=data.get('role'),
                tokens=100,  # Начальное количество токенов
                theme='light',  # Тема по умолчанию
                tutorial_completed=False  # Обязательное обучение не пройдено
            )
            
            # Вызов валидации
            new_user.validate()
            
            db.session.add(new_user)
            db.session.commit()
            
            # Автоматический вход после регистрации
            login_user(new_user)
            
            # Перенаправление на обязательное обучение для новых пользователей
            return jsonify({
                'success': True,
                'message': 'Registration successful',
                'redirect': url_for('tutorial')
            })
        except ValueError as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 400
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Registration failed'}), 500


# API ключ и модель теперь жестко заданы в config.py, маршрут удален

# Страница управления предметами
@app.route('/admin/subjects', methods=['GET'])
@login_required
def admin_subjects():
    if current_user.role != "administrator":
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    subjects = Subject.query.all()
    return render_template('admin_subjects.html', subjects=subjects)

# Страница управления экспертами
@app.route('/admin/experts', methods=['GET'])
@login_required
def admin_experts():
    if current_user.role != "administrator":
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    experts = Expert.query.all()
    return render_template('admin_experts.html', experts=experts)

# Страница управления пользователями
@app.route('/admin/users', methods=['GET'])
@login_required
def admin_users():
    if current_user.role != "administrator":
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    users = User.query.all()
    return render_template('admin_users.html', users=users)


# API для изменения баланса пользователя
@app.route('/api/admin/user/<int:user_id>/balance', methods=['PUT'])
@login_required
def change_user_balance(user_id):
    if current_user.role != "administrator":
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    data = request.get_json()
    if not data or 'balance' not in data:
        return jsonify({"success": False, "message": "Balance is required"}), 400
    
    user = User.query.get_or_404(user_id)
    old_balance = user.tokens
    new_balance = int(data['balance'])
    
    if new_balance < 0:
        return jsonify({"success": False, "message": "Balance cannot be negative"}), 400
    
    user.tokens = new_balance
    
    # Запись транзакции
    transaction = TokenTransaction(
        user_id=user.id,
        amount=new_balance - old_balance,
        transaction_type='admin_adjustment',
        description=f'Admin balance adjustment: {old_balance} -> {new_balance}'
    )
    db.session.add(transaction)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Balance updated from {old_balance} to {new_balance}",
        "new_balance": new_balance
    })


# API для изменения роли пользователя
@app.route('/api/admin/user/<int:user_id>/role', methods=['PUT'])
@login_required
def change_user_role(user_id):
    if current_user.role != "administrator":
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    data = request.get_json()
    if not data or 'role' not in data:
        return jsonify({"success": False, "message": "Role is required"}), 400
    
    user = User.query.get_or_404(user_id)
    new_role = data['role']
    
    valid_roles = ['student', 'teacher', 'administrator', 'parent', 'expert']
    if new_role not in valid_roles:
        return jsonify({"success": False, "message": "Invalid role"}), 400
    
    if user.id == current_user.id and new_role != 'administrator':
        return jsonify({"success": False, "message": "Cannot change your own role from administrator"}), 400
    
    old_role = user.role
    user.role = new_role
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Role changed from {old_role} to {new_role}",
        "new_role": new_role
    })


# API для удаления пользователя
@app.route('/api/admin/user/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    if current_user.role != "administrator":
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        return jsonify({"success": False, "message": "Cannot delete yourself"}), 400
    
    # Удаление связанных данных
    UserAnswer.query.filter_by(user_id=user_id).delete()
    UserAchievement.query.filter_by(user_id=user_id).delete()
    TokenTransaction.query.filter_by(user_id=user_id).delete()
    
    # Удаление уроков и викторин, созданных пользователем
    lessons = Lesson.query.filter_by(created_by=user_id).all()
    for lesson in lessons:
        if lesson.quiz:
            Question.query.filter_by(quiz_id=lesson.quiz.id).delete()
            Quiz.query.filter_by(id=lesson.quiz.id).delete()
        Lesson.query.filter_by(id=lesson.id).delete()
    
    # Обнуление created_by для экспертов и предметов
    Expert.query.filter_by(created_by=user_id).update({'created_by': None})
    Subject.query.filter_by(created_by=user_id).update({'created_by': None})
    
    # Удаление пользователя
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({"success": True, "message": "User deleted successfully"})


# Страница управления достижениями
@app.route('/admin/achievements', methods=['GET'])
@login_required
def admin_achievements():
    if current_user.role != "administrator":
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    achievements = Achievement.query.all()
    return render_template('admin_achievements.html', achievements=achievements)


# API для создания достижения
@app.route('/api/admin/achievement', methods=['POST'])
@login_required
def create_achievement():
    if current_user.role != "administrator":
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Invalid data"}), 400
    
    achievement = Achievement(
        name=data.get('name'),
        description=data.get('description'),
        condition=data.get('condition'),
        icon=data.get('icon', '🏆')
    )
    
    db.session.add(achievement)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Achievement created"})


# API для удаления достижения
@app.route('/api/admin/achievement/<int:achievement_id>', methods=['DELETE'])
@login_required
def delete_achievement(achievement_id):
    if current_user.role != "administrator":
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    achievement = Achievement.query.get_or_404(achievement_id)
    
    # Удаление связей с пользователями
    UserAchievement.query.filter_by(achievement_id=achievement_id).delete()
    
    db.session.delete(achievement)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Achievement deleted"})


# Основные маршруты
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if current_user.is_authenticated:
            return redirect(url_for('main'))
        return render_template('login.html')
    elif request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400
        
        # Проверка блокировки IP
        ip_address = request.remote_addr
        if is_locked_out(ip_address):
            return jsonify({'success': False, 'message': 'Too many failed attempts. Please try again later.'}), 429
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            login_user(user)
            reset_failed_attempts(ip_address)
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'redirect': url_for('main')
            })
        else:
            record_failed_attempt(ip_address)
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/tutorial')
@login_required
def tutorial():
    """Обязательное обучение для новых пользователей"""
    if current_user.tutorial_completed:
        return redirect(url_for('main'))
    return render_template('tutorial.html')


@app.route('/api/complete_tutorial', methods=['POST'])
@login_required
def complete_tutorial():
    """Завершение обязательного обучения"""
    current_user.tutorial_completed = True
    db.session.commit()
    return jsonify({'success': True, 'redirect': url_for('main')})


@app.route('/')
@app.route('/main')
@login_required
def main():
    # Проверка обязательного обучения
    if not current_user.tutorial_completed:
        return redirect(url_for('tutorial'))
    
    subjects = Subject.query.all()
    experts = Expert.query.all()
    
    # Получаем историю уроков пользователя:
    # 1. Уроки, которые пользователь создал
    created_lessons = Lesson.query.filter_by(created_by=current_user.id).order_by(Lesson.created_at.desc()).all()
    
    # 2. Уроки, которые пользователь проходил (через викторины)
    lesson_attempts = QuizAttempt.query.filter_by(user_id=current_user.id).order_by(QuizAttempt.completed_at.desc()).all()
    
    # Объединяем оба списка
    lessons_history = {}
    
    # Добавляем созданные уроки
    for lesson in created_lessons:
        if lesson.id not in lessons_history:
            # Проверяем, есть ли попытки прохождения этого урока
            attempt = QuizAttempt.query.filter_by(user_id=current_user.id, lesson_id=lesson.id).order_by(QuizAttempt.completed_at.desc()).first()
            attempts_count = QuizAttempt.query.filter_by(user_id=current_user.id, lesson_id=lesson.id).count()
            
            lessons_history[lesson.id] = {
                'lesson': lesson,
                'last_attempt': attempt,
                'attempts_count': attempts_count,
                'is_created': True
            }
    
    # Добавляем пройденные уроки (которые пользователь не создавал)
    for attempt in lesson_attempts:
        if attempt.lesson_id not in lessons_history:
            lesson = Lesson.query.get(attempt.lesson_id)
            if lesson:
                attempts_count = QuizAttempt.query.filter_by(user_id=current_user.id, lesson_id=attempt.lesson_id).count()
                lessons_history[attempt.lesson_id] = {
                    'lesson': lesson,
                    'last_attempt': attempt,
                    'attempts_count': attempts_count,
                    'is_created': False
                }
    
    # Преобразуем в список для шаблона и сортируем по дате (сначала новые)
    lessons_history_list = list(lessons_history.values())
    def get_sort_date(item):
        if item['last_attempt']:
            return item['last_attempt'].completed_at
        return item['lesson'].created_at
    
    lessons_history_list.sort(key=get_sort_date, reverse=True)
    
    return render_template('main.html', subjects=subjects, experts=experts, lessons_history=lessons_history_list)


@app.route('/profile')
@login_required
def profile():
    experts = Expert.query.all()
    return render_template('profile.html', experts=experts)


@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')


@app.route('/leaderboard')
@login_required
def leaderboard():
    # Получаем топ пользователей по рейтингу
    top_users = User.query.order_by(User.rating.desc()).limit(100).all()
    return render_template('leaderboard.html', top_users=top_users)


@app.route('/achievements')
@login_required
def achievements():
    user_achievements = UserAchievement.query.filter_by(user_id=current_user.id).all()
    achievement_ids = [ua.achievement_id for ua in user_achievements]
    all_achievements = Achievement.query.all()
    return render_template('achievements.html', 
                         user_achievements=achievement_ids,
                         all_achievements=all_achievements)


# API маршруты для настроек
@app.route('/api/change_theme', methods=['POST'])
@login_required
def change_theme():
    data = request.get_json()
    if not data or 'theme' not in data:
        return jsonify({'success': False, 'message': 'Theme is required'}), 400
    
    theme = data.get('theme')
    if theme not in ['light', 'dark', 'base']:
        return jsonify({'success': False, 'message': 'Invalid theme'}), 400
    
    current_user.theme = theme
    db.session.commit()
    return jsonify({'success': True, 'message': 'Theme changed successfully'})


@app.route('/api/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Invalid request data'}), 400
    
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    
    if not old_password or not new_password:
        return jsonify({'success': False, 'message': 'Old and new passwords are required'}), 400
    
    if not current_user.password_hash or not check_password_hash(current_user.password_hash, old_password):
        return jsonify({'success': False, 'message': 'Invalid old password'}), 400
    
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Password changed successfully'})


# API ключ и модель теперь жестко заданы в config.py, маршрут удален


# Маршруты для загрузки файлов
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# OAuth маршруты
@app.route('/oauth/login/<provider>')
def oauth_login(provider):
    """OAuth логин для регистрации/входа"""
    if provider == 'github':
        if not Config.GITHUB_CLIENT_ID or not Config.GITHUB_CLIENT_SECRET:
            flash('GitHub OAuth не настроен', 'error')
            return redirect(url_for('login'))
        
        # Используем простой редирект на GitHub OAuth
        redirect_uri = url_for('oauth_callback', provider='github', _external=True)
        github_auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={Config.GITHUB_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&scope=user:email"
        )
        return redirect(github_auth_url)
    
    flash(f'OAuth login for {provider} is not implemented yet', 'info')
    return redirect(url_for('login'))


@app.route('/link/github')
@login_required
def link_github():
    """Привязка GitHub аккаунта к существующему пользователю"""
    if current_user.github_id:
        flash('GitHub уже привязан', 'info')
        return redirect(url_for('profile'))
    
    if not Config.GITHUB_CLIENT_ID or not Config.GITHUB_CLIENT_SECRET:
        flash('GitHub OAuth не настроен', 'error')
        return redirect(url_for('profile'))
    
    # Сохраняем в сессии, что это привязка, а не вход
    session['oauth_link'] = True
    redirect_uri = url_for('oauth_callback', provider='github', _external=True)
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={Config.GITHUB_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user:email"
    )
    return redirect(github_auth_url)


@app.route('/oauth/<provider>/callback')
def oauth_callback(provider):
    """Обработка OAuth callback"""
    if provider == 'github':
        try:
            code = request.args.get('code')
            if not code:
                flash('Ошибка авторизации: код не получен', 'error')
                return redirect(url_for('login'))
            
            # Обмениваем код на токен
            token_url = 'https://github.com/login/oauth/access_token'
            token_data = {
                'client_id': Config.GITHUB_CLIENT_ID,
                'client_secret': Config.GITHUB_CLIENT_SECRET,
                'code': code
            }
            token_response = requests.post(token_url, data=token_data, headers={'Accept': 'application/json'})
            token_json = token_response.json()
            access_token = token_json.get('access_token')
            
            if not access_token:
                flash('Ошибка получения токена', 'error')
                return redirect(url_for('login'))
            
            # Получаем информацию о пользователе
            user_response = requests.get(
                'https://api.github.com/user',
                headers={'Authorization': f'token {access_token}', 'Accept': 'application/json'}
            )
            user_info = user_response.json()
            github_id = str(user_info.get('id'))
            
            # Получаем email
            emails_response = requests.get(
                'https://api.github.com/user/emails',
                headers={'Authorization': f'token {access_token}', 'Accept': 'application/json'}
            )
            emails = emails_response.json()
            email = None
            if emails:
                primary_email = next((e for e in emails if e.get('primary')), emails[0])
                email = primary_email.get('email')
            
            # Проверяем, это привязка или вход
            is_linking = session.get('oauth_link', False)
            session.pop('oauth_link', None)
            
            if is_linking:
                # Привязка GitHub к существующему аккаунту
                if not current_user.is_authenticated:
                    flash('Необходимо войти для привязки GitHub', 'error')
                    return redirect(url_for('login'))
                
                # Проверяем, не привязан ли этот GitHub ID к другому аккаунту
                existing_user = User.query.filter_by(github_id=github_id).first()
                if existing_user and existing_user.id != current_user.id:
                    flash('Этот GitHub аккаунт уже привязан к другому пользователю', 'error')
                    return redirect(url_for('profile'))
                
                current_user.github_id = github_id
                db.session.commit()
                flash('GitHub успешно привязан!', 'success')
                return redirect(url_for('profile'))
            else:
                # Вход/регистрация через GitHub
                user = User.query.filter_by(github_id=github_id).first()
                
                if not user:
                    # Регистрация нового пользователя
                    if not email:
                        flash('Не удалось получить email из GitHub', 'error')
                        return redirect(url_for('register'))
                    
                    # Проверяем, существует ли пользователь с таким email
                    existing_user = User.query.filter_by(email=email).first()
                    if existing_user:
                        # Привязываем GitHub к существующему аккаунту
                        existing_user.github_id = github_id
                        db.session.commit()
                        login_user(existing_user)
                        flash('GitHub привязан к вашему аккаунту!', 'success')
                        return redirect(url_for('main'))
                    
                    # Создаем нового пользователя
                    name_parts = (user_info.get('name') or 'User GitHub').split()
                    user = User(
                        email=email,
                        first_name=name_parts[0] if name_parts else 'User',
                        last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else 'GitHub',
                        github_id=github_id,
                        role='student',
                        tokens=100,
                        email_verified=True,  # GitHub email считается подтвержденным
                        theme='light'
                    )
                    user.validate()
                    db.session.add(user)
                    db.session.commit()
                
                login_user(user)
                flash('Успешный вход через GitHub!', 'success')
                return redirect(url_for('main'))
        
        except Exception as e:
            print(f"OAuth error: {e}")
            import traceback
            traceback.print_exc()
            flash('Ошибка при авторизации через GitHub', 'error')
            return redirect(url_for('login'))
    
    flash(f'OAuth callback for {provider} is not implemented yet', 'info')
    return redirect(url_for('login'))


# Маршруты для уроков
@app.route('/lesson/<int:subject_id>')
@login_required
def lesson_page(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    lessons = Lesson.query.filter_by(subject_id=subject_id).all()
    return render_template('lesson.html', subject=subject, lessons=lessons)


@app.route('/teacher/create_lesson')
@login_required
def teacher_create_lesson():
    if current_user.role != 'teacher':
        flash('У вас нет прав для доступа к этой странице', 'error')
        return redirect(url_for('main'))
    subjects = Subject.query.all()
    return render_template('teacher_create_lesson.html', subjects=subjects)


@app.route('/api/create_lesson', methods=['POST'])
@login_required
def create_lesson():
    """Создание урока учителем (по аналогии с expert_chat)"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Неверные данные запроса'}), 400
    
    # Используем current_user напрямую, как в expert_chat и других маршрутах
    # ВРЕМЕННО: Проверка роли отключена для тестирования - все роли могут создавать уроки
    # Раскомментируйте следующую проверку для включения ограничения по роли:
    # user_role = str(current_user.role).strip().lower() if current_user.role else ''
    # if user_role != 'teacher':
    #     print(f"DEBUG create_lesson: User ID={current_user.id}, Email={current_user.email}, Role='{current_user.role}' (normalized='{user_role}'), Expected='teacher'")
    #     return jsonify({"success": False, "message": f"У вас нет прав для создания урока. Ваша роль: {current_user.role}"}), 403
    
    try:
        subject_id = data.get('subject_id')
        material_text = data.get('material_text', '').strip()
        material_image = data.get('material_image', '').strip()
        title = data.get('title', '').strip()
        
        # Проверка обязательных полей
        if not subject_id:
            return jsonify({'success': False, 'message': 'Не выбран предмет'}), 400
        
        if not material_text and not material_image:
            return jsonify({'success': False, 'message': 'Добавьте материал урока (текст или изображение)'}), 400
        
        # Проверка существования предмета
        subject = Subject.query.get(subject_id)
        if not subject:
            return jsonify({'success': False, 'message': 'Предмет не найден'}), 404
        
        # Генерация названия урока, если не указано
        if not title:
            title = f"Урок по {subject.name}"
        
        # Анализ материала и генерация объяснения (с reasoning, как в expert_chat)
        explanation = ""
        explanation_html = ""
        if material_text:
            try:
                explanation = openrouter_api.analyze_material(material_text)
                # Конвертируем markdown в HTML для корректного отображения
                explanation_html = markdown.markdown(explanation)
            except Exception as e:
                print(f"Ошибка анализа материала: {e}")
                explanation = "Не удалось проанализировать материал."
                explanation_html = markdown.markdown(explanation)
        
        # Проверка и списание токенов за создание урока
        if current_user.tokens < Config.LESSON_COST:
            return jsonify({'success': False, 'message': f'Недостаточно токенов. Требуется: {Config.LESSON_COST}, у вас: {current_user.tokens}'}), 400
        
        # Создание урока
        lesson = Lesson(
            title=title,
            material_text=material_text if material_text else None,
            material_image=material_image if material_image else None,
            subject_id=subject_id,
            created_by=current_user.id
        )
        db.session.add(lesson)
        db.session.flush()  # Получаем ID урока
        
        # Списываем токены за создание урока
        current_user.tokens -= Config.LESSON_COST
        transaction = TokenTransaction(
            user_id=current_user.id,
            amount=-Config.LESSON_COST,
            transaction_type='lesson_creation',
            description=f'Создание урока: {title}'
        )
        db.session.add(transaction)
        
        # Генерация викторины
        quiz_questions = []
        if material_text:
            try:
                quiz_questions = openrouter_api.generate_quiz(
                    material_text=material_text,
                    explanation=explanation,
                    num_questions=10
                )
            except Exception as e:
                print(f"Ошибка генерации викторины: {e}")
                quiz_questions = []
        
        # Создание викторины с UUID
        quiz = Quiz(
            lesson_id=lesson.id,
            title=f"Викторина: {title}",
            uuid=str(uuid.uuid4())
        )
        db.session.add(quiz)
        db.session.flush()  # Получаем ID викторины
        
        # Создание вопросов
        if quiz_questions:
            for idx, q_data in enumerate(quiz_questions):
                question = Question(
                    quiz_id=quiz.id,
                    question_text=q_data.get('question_text', ''),
                    question_type=q_data.get('question_type', 'single'),
                    correct_answer=json.dumps(q_data.get('correct_answer', ''), ensure_ascii=False),
                    options=json.dumps(q_data.get('options', []), ensure_ascii=False) if q_data.get('options') else None,
                    order=idx
                )
                db.session.add(question)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Урок создан успешно',
            'lesson_id': lesson.id,
            'quiz_id': quiz.id,
            'explanation': explanation,
            'explanation_html': explanation_html
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка создания урока: {e}")
        return jsonify({'success': False, 'message': f'Ошибка создания урока: {str(e)}'}), 500


# Маршруты для викторин
@app.route('/quiz/<int:quiz_id>')
@login_required
def quiz_page(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    # Проверяем, является ли это повторным прохождением
    is_retry = request.args.get('retry', 'false').lower() == 'true'
    previous_attempt = QuizAttempt.query.filter_by(user_id=current_user.id, quiz_id=quiz_id).first()
    # Получаем вопросы и сериализуем их для шаблона
    questions = []
    for question in quiz.questions:
        # Парсим JSON поля
        options = []
        if question.options:
            try:
                options = json.loads(question.options)
            except (json.JSONDecodeError, TypeError):
                options = []
        
        correct_answer = ""
        if question.correct_answer:
            try:
                correct_answer_data = json.loads(question.correct_answer)
                if isinstance(correct_answer_data, str):
                    correct_answer = correct_answer_data
                else:
                    correct_answer = str(correct_answer_data)
            except (json.JSONDecodeError, TypeError):
                correct_answer = str(question.correct_answer)
        
        # Формируем словарь для сериализации
        question_dict = {
            'id': question.id,
            'question_text': question.question_text or '',
            'question_type': question.question_type or 'single',
            'options': options if options else [],
            'correct_answer': correct_answer,
            'order': question.order or 0
        }
        questions.append(question_dict)
    
    # Сортируем по порядку
    questions.sort(key=lambda x: x['order'])
    
    return render_template('quiz.html', quiz=quiz, questions=questions, is_retry=is_retry, previous_attempt=previous_attempt)


@app.route('/api/submit_quiz', methods=['POST'])
@login_required
def submit_quiz():
    """Отправка результатов викторины с отслеживанием попыток"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Неверные данные запроса'}), 400
    
    quiz_id = data.get('quiz_id')
    answers = data.get('answers', {})
    is_retry = data.get('is_retry', False)  # Флаг повторного прохождения
    
    if not quiz_id:
        return jsonify({'success': False, 'message': 'ID викторины не указан'}), 400
    
    quiz = Quiz.query.get_or_404(quiz_id)
    lesson = quiz.lesson
    
    # Проверяем, была ли уже попытка прохождения
    previous_attempt = QuizAttempt.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz_id
    ).first()
    
    is_first_attempt = previous_attempt is None
    
    # Если это повторное прохождение, не даем награды
    if is_retry or not is_first_attempt:
        is_first_attempt = False
    
    try:
        # Подсчитываем правильные ответы
        correct_count = 0
        total_questions = len(quiz.questions)
        
        for question in quiz.questions:
            user_answer = answers.get(str(question.id), '')
            is_correct = False
            
            # Если ответ не дан, считаем как неправильный
            if not user_answer or (isinstance(user_answer, str) and not user_answer.strip()) or (isinstance(user_answer, list) and len(user_answer) == 0):
                # Сохраняем пустой ответ как неправильный
                user_answer_obj = UserAnswer(
                    user_id=current_user.id,
                    question_id=question.id,
                    answer='',
                    is_correct=False
                )
                db.session.add(user_answer_obj)
                continue  # Переходим к следующему вопросу, этот уже засчитан как неправильный
            
            # Парсим правильный ответ
            try:
                correct_answer_data = json.loads(question.correct_answer)
                if isinstance(correct_answer_data, str):
                    correct_answer = correct_answer_data
                else:
                    correct_answer = str(correct_answer_data)
            except:
                correct_answer = str(question.correct_answer)
            
            # Проверяем ответ
            if question.question_type == 'text':
                # Для текстовых вопросов сравниваем в нижнем регистре
                is_correct = str(user_answer).strip().lower() == correct_answer.strip().lower()
            elif question.question_type == 'single':
                is_correct = str(user_answer).strip() == correct_answer.strip()
            elif question.question_type == 'multiple':
                # Для множественного выбора сравниваем списки
                if isinstance(user_answer, list):
                    user_answers = [str(a).strip() for a in user_answer]
                    correct_answers = [str(correct_answer).strip()]
                    is_correct = set(user_answers) == set(correct_answers)
            
            # Сохраняем ответ пользователя
            user_answer_obj = UserAnswer(
                user_id=current_user.id,
                question_id=question.id,
                answer=json.dumps(user_answer, ensure_ascii=False) if isinstance(user_answer, list) else str(user_answer),
                is_correct=is_correct
            )
            db.session.add(user_answer_obj)
            
            if is_correct:
                correct_count += 1
        
        # Создаем запись о попытке
        attempt = QuizAttempt(
            user_id=current_user.id,
            quiz_id=quiz_id,
            lesson_id=lesson.id,
            score=correct_count,
            total_questions=total_questions,
            is_first_attempt=is_first_attempt
        )
        db.session.add(attempt)
        
        # Начисляем награды только за первую попытку
        tokens_earned = 0
        if is_first_attempt and not is_retry:
            # Обновляем статистику пользователя
            current_user.total_quizzes += 1
            current_user.total_answers += total_questions
            current_user.total_correct_answers += correct_count
            
            # Начисляем токены за правильные ответы
            tokens_earned = correct_count * Config.CORRECT_ANSWER_REWARD
            current_user.tokens += tokens_earned
            current_user.rating += tokens_earned
            
            # Создаем транзакцию
            transaction = TokenTransaction(
                user_id=current_user.id,
                amount=tokens_earned,
                transaction_type='quiz_reward',
                description=f'Награда за викторину: {correct_count}/{total_questions} правильных ответов'
            )
            db.session.add(transaction)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'score': correct_count,
            'total': total_questions,
            'percentage': round((correct_count / total_questions * 100) if total_questions > 0 else 0, 1),
            'is_first_attempt': is_first_attempt,
            'tokens_earned': tokens_earned,
            'message': 'Викторина завершена!' if is_first_attempt or is_retry else 'Результаты сохранены'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка отправки викторины: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'}), 500


# Маршруты для родителей
@app.route('/parent/dashboard')
@login_required
def parent_dashboard():
    if current_user.role != 'parent':
        return jsonify({"success": False, "message": "Access denied"}), 403
    children = User.query.filter_by(parent_id=current_user.id).all()
    return render_template('parent_dashboard.html', children=children)


@app.route('/parent/add_child', methods=['GET', 'POST'])
@login_required
def parent_add_child():
    if current_user.role != 'parent':
        return jsonify({"success": False, "message": "Access denied"}), 403
    
    if request.method == 'GET':
        return render_template('parent_add_child.html')
    
    # POST - добавление ребенка
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Invalid data"}), 400
    
    email = data.get('email')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    
    if not all([email, first_name, last_name]):
        return jsonify({"success": False, "message": "All fields are required"}), 400
    
    # Проверка существования пользователя
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        # Если пользователь существует, прикрепляем к родителю
        if existing_user.parent_id and existing_user.parent_id != current_user.id:
            return jsonify({"success": False, "message": "User already has a parent"}), 400
        existing_user.parent_id = current_user.id
        db.session.commit()
        return jsonify({"success": True, "message": "Child attached successfully"})
    
    # Создание нового пользователя-ребенка
    try:
        new_child = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role='student',
            parent_id=current_user.id,
            tokens=100,
            tutorial_completed=False
        )
        new_child.validate()
        db.session.add(new_child)
        db.session.commit()
        return jsonify({"success": True, "message": "Child added successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


@app.route('/parent/child/<int:child_id>/progress')
@login_required
def parent_child_progress(child_id):
    if current_user.role != 'parent':
        return jsonify({"success": False, "message": "Access denied"}), 403
    child = User.query.filter_by(id=child_id, parent_id=current_user.id).first_or_404()
    return render_template('parent_child_progress.html', child=child)


# Маршруты для выбора эксперта
@app.route('/select_expert')
@login_required
def select_expert():
    experts = Expert.query.all()
    return render_template('select_expert.html', experts=experts)


@app.route('/api/change_expert', methods=['POST'])
@login_required
def change_expert():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Неверные данные запроса'}), 400
    
    expert_id = data.get('expert_id')
    
    # Разрешаем установку None для сброса эксперта
    if expert_id is None:
        current_user.selected_expert_id = None
        db.session.commit()
        return jsonify({'success': True, 'message': 'Эксперт успешно сброшен'})
    
    # Проверяем, что expert_id - это число
    try:
        expert_id = int(expert_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Неверный ID эксперта'}), 400
    
    # Проверяем существование эксперта
    expert = Expert.query.get(expert_id)
    if not expert:
        return jsonify({'success': False, 'message': 'Эксперт не найден'}), 404
    
    # Устанавливаем эксперта
    current_user.selected_expert_id = expert_id
    db.session.commit()
    return jsonify({'success': True, 'message': 'Эксперт успешно изменен'})


# API для чата с экспертом
@app.route('/api/expert/chat', methods=['POST'])
@login_required
def expert_chat():
    """Чат с экспертом за 2 токена"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Неверные данные запроса'}), 400
    
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'success': False, 'message': 'Сообщение не может быть пустым'}), 400
    
    # Проверка наличия выбранного эксперта
    if not current_user.selected_expert_id:
        return jsonify({'success': False, 'message': 'Сначала выберите эксперта в профиле'}), 400
    
    expert = Expert.query.get(current_user.selected_expert_id)
    if not expert:
        return jsonify({'success': False, 'message': 'Эксперт не найден'}), 404
    
    # Проверка баланса токенов
    if current_user.tokens < Config.EXPERT_CHAT_COST:
        return jsonify({'success': False, 'message': f'Недостаточно токенов. Требуется {Config.EXPERT_CHAT_COST} токенов'}), 400
    
    try:
        # Получаем историю разговора из сессии (можно улучшить, сохраняя в БД)
        conversation_history = session.get('expert_conversation_history', [])
        
        # Добавляем текущее сообщение пользователя в историю
        conversation_history.append({"role": "user", "content": message})
        
        # Отправляем сообщение эксперту (с reasoning)
        result = openrouter_api.chat_with_expert(
            message=message,
            expert_prompt=expert.prompt,
            conversation_history=conversation_history
        )
        
        # Извлекаем reply и reasoning_details
        if isinstance(result, dict):
            reply = result.get("reply", "")
            reasoning_details = result.get("reasoning_details")
        else:
            # Обратная совместимость, если вернулась строка
            reply = result
            reasoning_details = None
        
        # Добавляем ответ ассистента в историю с reasoning_details
        assistant_msg = {"role": "assistant", "content": reply}
        if reasoning_details:
            assistant_msg["reasoning_details"] = reasoning_details
        conversation_history.append(assistant_msg)
        
        # Ограничиваем историю последними 20 сообщениями
        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]
        session['expert_conversation_history'] = conversation_history
        
        # Списываем токены
        current_user.tokens -= Config.EXPERT_CHAT_COST
        db.session.commit()
        
        return jsonify({
            'success': True,
            'reply': reply,
            'tokens_remaining': current_user.tokens
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка чата с экспертом: {e}")
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'}), 500


# Маршруты для верификации email
@app.route('/verify_email')
def verify_email_page():
    return render_template('verify_email.html')


@app.route('/api/verify_email', methods=['POST'])
@login_required
def verify_email():
    """Проверка кода подтверждения email"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Неверные данные запроса'}), 400
    
    email = data.get('email', current_user.email)
    code = data.get('code', '').strip()
    
    # Проверяем, что email принадлежит текущему пользователю
    if email != current_user.email:
        return jsonify({'success': False, 'message': 'Вы можете подтвердить только свой email'}), 403
    
    if not code or len(code) != 6:
        return jsonify({'success': False, 'message': 'Неверный формат кода'}), 400
    
    try:
        # Ищем код
        verification = EmailVerificationCode.query.filter_by(
            email=email,
            code=code,
            used=False
        ).first()
        
        if not verification:
            return jsonify({'success': False, 'message': 'Неверный код подтверждения'}), 400
        
        # Проверяем срок действия
        if verification.expires_at < datetime.utcnow():
            return jsonify({'success': False, 'message': 'Код истек. Запросите новый код'}), 400
        
        # Помечаем код как использованный
        verification.used = True
        
        # Подтверждаем email пользователя
        current_user.email_verified = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Email успешно подтвержден!',
            'redirect': url_for('profile')
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка верификации: {e}")
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'}), 500


@app.route('/api/send_verification_code', methods=['POST'])
@login_required
def send_verification_code():
    """Отправка кода подтверждения на email"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Неверные данные запроса'}), 400
    
    email = data.get('email', current_user.email)
    
    # Проверяем, что email принадлежит текущему пользователю
    if email != current_user.email:
        return jsonify({'success': False, 'message': 'Вы можете подтвердить только свой email'}), 403
    
    # Проверяем, не подтвержден ли уже email
    if current_user.email_verified:
        return jsonify({'success': False, 'message': 'Email уже подтвержден'}), 400
    
    try:
        # Генерируем 6-значный код
        import random
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        # Удаляем старые коды для этого email
        EmailVerificationCode.query.filter_by(email=email, used=False).delete()
        
        # Создаем новый код
        expires_at = datetime.utcnow() + timedelta(minutes=Config.VERIFICATION_CODE_EXPIRY)
        verification_code = EmailVerificationCode(
            email=email,
            code=code,
            expires_at=expires_at
        )
        db.session.add(verification_code)
        db.session.commit()
        
        # Отправляем email
        try:
            msg = Message(
                subject='Код подтверждения email - AI Бот',
                recipients=[email],
                body=f'Ваш код подтверждения: {code}\n\nКод действителен в течение {Config.VERIFICATION_CODE_EXPIRY} минут.',
                html=f'''
                <html>
                <body>
                    <h2>Код подтверждения email</h2>
                    <p>Ваш код подтверждения: <strong style="font-size: 24px; color: #667eea;">{code}</strong></p>
                    <p>Код действителен в течение {Config.VERIFICATION_CODE_EXPIRY} минут.</p>
                    <p>Если вы не запрашивали этот код, просто проигнорируйте это письмо.</p>
                </body>
                </html>
                '''
            )
            mail.send(msg)
        except Exception as e:
            print(f"Ошибка отправки email: {e}")
            # В режиме разработки возвращаем код в ответе
            return jsonify({
                'success': True,
                'message': 'Код отправлен (в режиме разработки показан ниже)',
                'code': code  # Только для разработки!
            })
        
        return jsonify({
            'success': True,
            'message': f'Код подтверждения отправлен на {email}'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка отправки кода: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'}), 500


# Маршруты для ежедневных наград
@app.route('/api/daily_reward_status')
@login_required
def daily_reward_status():
    now = datetime.utcnow()
    can_claim = False
    
    if current_user.last_daily_reward:
        time_diff = now - current_user.last_daily_reward
        can_claim = time_diff.total_seconds() >= 86400  # 24 часа
    else:
        can_claim = True
    
    return jsonify({
        'success': True,
        'can_claim': can_claim,
        'last_reward': current_user.last_daily_reward.isoformat() if current_user.last_daily_reward else None
    })


@app.route('/api/claim_daily_reward', methods=['POST'])
@login_required
def claim_daily_reward():
    now = datetime.utcnow()
    
    if current_user.last_daily_reward:
        time_diff = now - current_user.last_daily_reward
        if time_diff.total_seconds() < 86400:  # 24 часа
            return jsonify({'success': False, 'message': 'Daily reward already claimed'}), 400
    
    # Выдача награды
    current_user.tokens += Config.DAILY_TOKENS
    current_user.last_daily_reward = now
    
    # Запись транзакции
    transaction = TokenTransaction(
        user_id=current_user.id,
        amount=Config.DAILY_TOKENS,
        transaction_type='daily',
        description='Daily reward'
    )
    db.session.add(transaction)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'You received {Config.DAILY_TOKENS} tokens!',
        'tokens': current_user.tokens
    })


# Дополнительные API маршруты
@app.route('/api/switch_role', methods=['POST'])
@login_required
def switch_role():
    """Переключение роли для тестирования (только для admin@example.com)"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Неверные данные запроса'}), 400
    
    # Разрешаем переключение роли только для admin@example.com
    if current_user.email != 'admin@example.com':
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    new_role = data.get('role', '').strip().lower()
    valid_roles = ['student', 'teacher', 'administrator', 'parent', 'expert']
    
    if new_role not in valid_roles:
        return jsonify({'success': False, 'message': f'Неверная роль. Доступные роли: {", ".join(valid_roles)}'}), 400
    
    try:
        old_role = current_user.role
        current_user.role = new_role
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Роль успешно изменена с "{old_role}" на "{new_role}"',
            'new_role': new_role,
            'redirect': url_for('main')
        })
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка переключения роли: {e}")
        return jsonify({'success': False, 'message': f'Ошибка переключения роли: {str(e)}'}), 500


