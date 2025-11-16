# Решение проблем с GigaChat API

## Ошибка 401: "Authorization error: header is incorrect"

### Причины и решения:

#### 1. Неправильный формат API ключа

**Проблема**: API ключ должен быть Client Secret, который начинается с `R-M-`

**Решение**:
- Убедитесь, что вы используете **Client Secret**, а не Client ID
- Client Secret выглядит так: `R-M-xxxxxxxxxxxxxxxxxxxxx`
- Проверьте в GigaChat Developer Portal, что вы скопировали правильный ключ

#### 2. Кавычки в .env файле

**Проблема**: Если в `.env` файле ключ обернут в кавычки, они могут передаваться как часть ключа

**Решение**:
```env
# ✅ Правильно (без кавычек):
GIGA_API_KEY=R-M-xxxxxxxxxxxxxxxxxxxxx

# ❌ Неправильно:
GIGA_API_KEY="R-M-xxxxxxxxxxxxxxxxxxxxx"
GIGA_API_KEY='R-M-xxxxxxxxxxxxxxxxxxxxx'
```

#### 3. Пробелы в начале/конце ключа

**Проблема**: Лишние пробелы могут вызывать ошибку авторизации

**Решение**: Код автоматически убирает пробелы, но проверьте вручную:
```env
# ✅ Правильно:
GIGA_API_KEY=R-M-xxxxxxxxxxxxxxxxxxxxx

# ❌ Неправильно (пробелы):
GIGA_API_KEY= R-M-xxxxxxxxxxxxxxxxxxxxx 
GIGA_API_KEY=R-M-xxxxxxxxxxxxxxxxxxxxx 
```

#### 4. Неактивное приложение

**Проблема**: Приложение в GigaChat Developer Portal может быть неактивным

**Решение**:
1. Войдите в [GigaChat Developer Portal](https://developers.sber.ru/gigachat)
2. Проверьте статус вашего приложения
3. Убедитесь, что приложение активно
4. Проверьте, что у приложения есть права `GIGACHAT_API_PERS`

#### 5. Неправильный scope

**Проблема**: У API ключа может не быть нужных прав

**Решение**:
- Убедитесь, что при создании приложения вы указали scope `GIGACHAT_API_PERS`
- Проверьте настройки приложения в Developer Portal

### Проверка API ключа

1. Откройте файл `.env`
2. Найдите строку `GIGA_API_KEY=`
3. Убедитесь, что:
   - Ключ начинается с `R-M-`
   - Нет кавычек вокруг значения
   - Нет пробелов в начале или конце
   - Ключ скопирован полностью

### Тестирование

После исправления:
1. Установите зависимости: `pip install -r requirements.txt` (это установит официальный SDK)
2. Перезапустите приложение
3. Проверьте логи:
   - При использовании SDK: "INFO: GigaChat SDK успешно инициализирован"
   - При использовании прямого API: "INFO: Токен GigaChat успешно получен"
4. Если ошибка сохраняется, проверьте все пункты выше

### Использование официального SDK

Рекомендуется использовать официальный Python SDK GigaChat, который автоматически управляет токенами:

```bash
pip install gigachat
```

SDK упрощает работу с API и автоматически обновляет токены доступа. Код автоматически использует SDK, если он установлен, иначе переключается на прямой API.

### Альтернатива: YandexGPT

Если проблемы с GigaChat продолжаются, можно временно использовать YandexGPT:

1. Получите ключи Yandex Cloud
2. Добавьте в `.env`:
   ```env
   YANDEX_GPT_API_KEY=ваш-yandex-api-key
   YANDEX_GPT_FOLDER_ID=ваш-folder-id
   ```
3. Замените в `routes.py`:
   ```python
   from yandex_gpt import YandexGPT
   yandex_gpt = YandexGPT()
   ```

