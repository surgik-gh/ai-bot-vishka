# Инструкция по развертыванию

## Важные замечания

Это Flask приложение требует серверной части и **не может быть развернуто напрямую на GitHub Pages**, так как GitHub Pages поддерживает только статические сайты.

## Варианты развертывания

### 1. Render (Рекомендуется)

1. Зарегистрируйтесь на [Render.com](https://render.com)
2. Подключите ваш GitHub репозиторий
3. Создайте новый Web Service
4. Настройки:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Environment Variables**: Добавьте переменные из `.env.example`
5. Нажмите "Create Web Service"

### 2. Railway

1. Зарегистрируйтесь на [Railway.app](https://railway.app)
2. Создайте новый проект из GitHub репозитория
3. Railway автоматически определит Flask приложение
4. Добавьте переменные окружения в настройках проекта
5. Деплой произойдет автоматически

### 3. Heroku

1. Установите [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)
2. Создайте файл `Procfile`:
   ```
   web: gunicorn app:app
   ```
3. Создайте файл `runtime.txt`:
   ```
   python-3.11.0
   ```
4. Выполните:
   ```bash
   heroku create your-app-name
   heroku config:set SECRET_KEY=your-secret-key
   heroku config:set DATABASE_URL=sqlite:///ai_bot.db
   git push heroku main
   ```

### 4. PythonAnywhere

1. Зарегистрируйтесь на [PythonAnywhere.com](https://www.pythonanywhere.com)
2. Загрузите код через Git или файловый менеджер
3. Настройте Web App:
   - Source code: `/home/username/mysite`
   - WSGI configuration file: `/var/www/username_pythonanywhere_com_wsgi.py`
4. Добавьте переменные окружения в файле WSGI
5. Перезагрузите приложение

## Переменные окружения

Создайте файл `.env` или добавьте переменные в настройках хостинга:

```env
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///ai_bot.db
OPENROUTER_API_KEY=your-openrouter-api-key
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
```

## Дополнительные зависимости

Для production развертывания добавьте в `requirements.txt`:

```
gunicorn==21.2.0
```

## База данных

При первом запуске приложение автоматически создаст базу данных и выполнит миграции. Убедитесь, что у приложения есть права на запись в директорию проекта.

## Проверка развертывания

После развертывания проверьте:
1. Главная страница загружается
2. Регистрация и вход работают
3. Создание уроков работает
4. Викторины отображаются и отправляются
5. История уроков сохраняется

