# Настройка GigaChat и Kandinsky API

Проект использует **GigaChat** (от Сбера) для текстовых запросов и **Kandinsky** (от Сбера) для генерации изображений. Оба сервиса доступны в РФ.

## Получение API ключей

### 1. GigaChat API

1. Перейдите на [GigaChat Developer Portal](https://developers.sber.ru/gigachat)
2. Зарегистрируйтесь или войдите в аккаунт
3. Создайте новое приложение
4. Получите API ключ (Client Secret)
5. Скопируйте ключ в `.env` файл

**Важно**: GigaChat использует OAuth 2.0 для аутентификации. API ключ используется для получения токена доступа.

### 2. Kandinsky API

1. Перейдите на [FusionBrain AI](https://fusionbrain.ai/)
2. Зарегистрируйтесь или войдите
3. Перейдите в раздел "API Keys"
4. Создайте новую пару ключей (API Key и Secret Key)
5. Скопируйте оба ключа в `.env` файл

## Настройка .env файла

Добавьте следующие переменные в ваш `.env` файл:

```env
# GigaChat API (Сбер) - для текстовых запросов
GIGA_API_KEY=ваш-gigachat-api-key

# Опционально: кастомные URL (если нужны)
# GIGA_AUTH_URL=https://ngw.devices.sberbank.ru:9443/api/v2/oauth
# GIGA_CHAT_URL=https://gigachat.devices.sberbank.ru/api/v1/chat/completions

# Kandinsky API (Сбер) - для генерации изображений
KANDINSKY_API_KEY=ваш-kandinsky-api-key
KANDINSKY_SECRET_KEY=ваш-kandinsky-secret-key

# Опционально: кастомные URL (если нужны)
# KANDINSKY_URL=https://api-key.fusionbrain.ai/key/api/v1/text2image/run
# KANDINSKY_STATUS_URL=https://api-key.fusionbrain.ai/key/api/v1/text2image/status
```

## Установка зависимостей

```bash
pip install -r requirements.txt
```

Это установит официальный Python SDK GigaChat (`gigachat`), который упрощает работу с API и автоматически управляет токенами доступа.

## Как это работает

### GigaChat (текстовые запросы)

**Вариант 1: Использование официального SDK (рекомендуется)**
1. При инициализации `GigaAPI` создается клиент GigaChat SDK
2. SDK автоматически управляет токенами доступа (токен действителен 30 минут)
3. SDK автоматически обновляет токен при необходимости
4. Все запросы выполняются через удобный интерфейс SDK

**Вариант 2: Прямой API (fallback)**
1. Если SDK не установлен, используется прямой API
2. При инициализации происходит запрос токена доступа через OAuth
3. Токен используется для всех последующих запросов к GigaChat API
4. Токен автоматически обновляется при истечении (401 ошибка)

**Используется для:**
- Генерации промптов экспертов
- Анализа учебного материала
- Создания викторин
- Генерации итогов уроков

### Kandinsky (генерация изображений)

1. Отправляется запрос на генерацию изображения с текстовым промптом
2. Получается UUID задачи
3. Периодически проверяется статус генерации
4. Когда изображение готово, возвращается base64 строка

**Используется для:**
- Генерации аватаров экспертов

## Альтернативные варианты

Если GigaChat/Kandinsky недоступны, можно использовать:

### Вариант 1: YandexGPT + YandexART

```env
YANDEX_GPT_API_KEY=ваш-yandex-api-key
YANDEX_GPT_FOLDER_ID=ваш-folder-id
YANDEX_GPT_MODEL=yandexgpt-pro/latest
```

И заменить импорт в `routes.py`:
```python
from yandex_gpt import YandexGPT
yandex_gpt = YandexGPT()
```

### Вариант 2: Только GigaChat (без изображений)

Если Kandinsky недоступен, можно использовать только GigaChat для текста, а изображения генерировать через другой сервис или использовать текстовые описания.

## Решение проблем

### Ошибка: "Не удалось получить токен GigaChat" (401)

**Причина**: Неправильный формат API ключа или отсутствие обязательных заголовков.

**Решение**:
1. Убедитесь, что `GIGA_API_KEY` начинается с `R-M-` (это Client Secret)
2. Проверьте, что API ключ скопирован полностью, без пробелов и лишних символов
3. Убедитесь, что в `.env` файле нет кавычек вокруг значения:
   ```env
   # Правильно:
   GIGA_API_KEY=R-M-xxxxxxxxxxxxxxxxxxxxx
   
   # Неправильно:
   GIGA_API_KEY="R-M-xxxxxxxxxxxxxxxxxxxxx"
   GIGA_API_KEY='R-M-xxxxxxxxxxxxxxxxxxxxx'
   ```
4. Проверьте, что у API ключа есть права `GIGACHAT_API_PERS`
5. Убедитесь, что приложение в GigaChat Developer Portal активно

### Ошибка: "Kandinsky генерация не удалась"

- Проверьте правильность `KANDINSKY_API_KEY` и `KANDINSKY_SECRET_KEY`
- Убедитесь, что у вас есть доступ к API генерации изображений
- Проверьте баланс на аккаунте FusionBrain

### SSL предупреждения

В dev окружении отключены предупреждения SSL. Для production рекомендуется настроить правильные SSL сертификаты.

## Документация API

- [GigaChat API Documentation](https://developers.sber.ru/gigachat/docs)
- [Kandinsky API Documentation](https://fusionbrain.ai/api/)

