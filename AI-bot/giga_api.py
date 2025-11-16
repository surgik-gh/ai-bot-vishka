import requests
import json
import base64
import urllib3
import uuid
from config import Config

# Пытаемся импортировать официальный SDK GigaChat
GIGACHAT_SDK_AVAILABLE = False
try:
    from gigachat import GigaChat
    GIGACHAT_SDK_AVAILABLE = True
    print("INFO: GigaChat SDK найден и готов к использованию")
except ImportError as e:
    GIGACHAT_SDK_AVAILABLE = False
    print(f"WARNING: Официальный SDK GigaChat не установлен. Ошибка импорта: {e}")
    print("WARNING: Для установки выполните: pip install gigachat")
except Exception as e:
    GIGACHAT_SDK_AVAILABLE = False
    print(f"WARNING: Ошибка при импорте GigaChat SDK: {e}")
    print("WARNING: Используется прямой API")

# Отключаем предупреждения SSL для dev окружения
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class GigaAPI:
    def __init__(self):
        self.giga_api_key = Config.GIGA_API_KEY
        self.giga_auth_url = Config.GIGA_AUTH_URL or 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
        self.giga_chat_url = Config.GIGA_CHAT_URL or 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'
        self.kandinsky_url = Config.KANDINSKY_URL or 'https://api-key.fusionbrain.ai/key/api/v1/text2image/run'
        self.kandinsky_status_url = Config.KANDINSKY_STATUS_URL or 'https://api-key.fusionbrain.ai/key/api/v1/text2image/status'
        self.kandinsky_api_key = Config.KANDINSKY_API_KEY
        self.kandinsky_secret_key = Config.KANDINSKY_SECRET_KEY
        self.access_token = None
        self.giga_client = None
        
        # Проверка формата API ключа
        if self.giga_api_key:
            # Убираем пробелы и кавычки, если они есть
            self.giga_api_key = self.giga_api_key.strip().strip('"').strip("'")
            
            # Предупреждение, если формат не соответствует ожидаемому
            if not self.giga_api_key.startswith('R-M-'):
                print(f"WARNING: GIGA_API_KEY не начинается с 'R-M-'. Убедитесь, что это правильный Client Secret.")
                print(f"WARNING: Текущий ключ начинается с: {self.giga_api_key[:10]}...")
            
            # Используем официальный SDK, если доступен
            if GIGACHAT_SDK_AVAILABLE:
                try:
                    print(f"INFO: Попытка инициализации GigaChat SDK с ключом: {self.giga_api_key[:10]}...")
                    self.giga_client = GigaChat(credentials=self.giga_api_key)
                    # Получаем токен для проверки
                    token = self.giga_client.get_token()
                    if token:
                        print("INFO: GigaChat SDK успешно инициализирован, токен получен")
                        self.access_token = token  # Сохраняем токен для совместимости
                    else:
                        print("WARNING: SDK инициализирован, но токен не получен. Переключаемся на прямой API")
                        self._get_access_token()
                except Exception as e:
                    print(f"ERROR: Не удалось инициализировать GigaChat SDK: {e}")
                    print(f"ERROR: Тип ошибки: {type(e).__name__}")
                    import traceback
                    print(f"ERROR: Детали: {traceback.format_exc()}")
                    print("WARNING: Переключаемся на прямой API")
                    self._get_access_token()
            else:
                print("INFO: SDK недоступен, используем прямой API")
                # Используем прямой API
                self._get_access_token()
    
    def _get_access_token(self):
        """Получение токена доступа для GigaChat"""
        try:
            # Генерируем уникальный идентификатор запроса
            rq_uid = str(uuid.uuid4())
            
            headers = {
                'Authorization': f'Bearer {self.giga_api_key}',
                'RqUID': rq_uid,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'
            }
            
            # Для GigaChat scope передается в теле запроса
            data = {
                'scope': 'GIGACHAT_API_PERS'
            }
            
            response = requests.post(
                self.giga_auth_url,
                headers=headers,
                data=data,
                verify=False,  # Отключаем проверку SSL для dev окружения
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                self.access_token = result.get('access_token')
                if self.access_token:
                    print(f"INFO: Токен GigaChat успешно получен")
                return self.access_token
            else:
                error_detail = response.text
                print(f"ERROR: Не удалось получить токен GigaChat. Status: {response.status_code}")
                print(f"ERROR: Response: {error_detail}")
                
                # Дополнительная диагностика
                if response.status_code == 401:
                    print("ERROR: Проверьте правильность GIGA_API_KEY в .env файле")
                    print("ERROR: Убедитесь, что API ключ активен и имеет права GIGACHAT_API_PERS")
                
                return None
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Ошибка сети при получении токена GigaChat: {e}")
            return None
        except Exception as e:
            print(f"ERROR: Ошибка при получении токена GigaChat: {e}")
            return None
    
    def _make_request(self, prompt, system_prompt=None, temperature=0.6, max_tokens=2000):
        """Make request to GigaChat API"""
        try:
            if not self.giga_api_key:
                print("ERROR: GigaChat API ключ не настроен. Проверьте файл .env")
                return None
            
            # Используем официальный SDK, если доступен
            if self.giga_client:
                try:
                    # Формируем полный промпт с system prompt
                    full_prompt = prompt
                    if system_prompt:
                        full_prompt = f"{system_prompt}\n\n{prompt}"
                    
                    # Используем SDK для запроса
                    response = self.giga_client.chat(full_prompt)
                    return response.choices[0].message.content
                except Exception as e:
                    print(f"WARNING: Ошибка при использовании SDK: {e}")
                    print("WARNING: Переключаемся на прямой API")
                    # Продолжаем с прямым API
            
            # Используем прямой API
            # Обновляем токен, если его нет
            if not self.access_token:
                self._get_access_token()
            
            if not self.access_token:
                print("ERROR: Не удалось получить токен доступа GigaChat")
                return None
            
            # Формируем сообщения
            messages = []
            if system_prompt:
                messages.append({
                    'role': 'system',
                    'content': system_prompt
                })
            
            messages.append({
                'role': 'user',
                'content': prompt
            })
            
            # Генерируем уникальный идентификатор запроса
            rq_uid = str(uuid.uuid4())
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'RqUID': rq_uid,
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'GigaChat',
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens
            }
            
            response = requests.post(
                self.giga_chat_url,
                headers=headers,
                json=data,
                verify=False,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            elif response.status_code == 401:
                # Токен истек, получаем новый
                print("INFO: Токен истек, обновляем...")
                self._get_access_token()
                if self.access_token:
                    # Генерируем новый RqUID для повторного запроса
                    rq_uid = str(uuid.uuid4())
                    headers['Authorization'] = f'Bearer {self.access_token}'
                    headers['RqUID'] = rq_uid
                    response = requests.post(
                        self.giga_chat_url,
                        headers=headers,
                        json=data,
                        verify=False,
                        timeout=30
                    )
                    if response.status_code == 200:
                        result = response.json()
                        return result['choices'][0]['message']['content']
            
            print(f"ERROR: GigaChat API HTTP Error: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return None
            
        except requests.exceptions.Timeout:
            print("ERROR: Превышено время ожидания ответа от GigaChat API")
            return None
        except Exception as e:
            error_msg = f"GigaChat API Error: {e}"
            print(error_msg)
            return None
    
    def generate_image(self, prompt, style='default'):
        """Generate image using Kandinsky API"""
        try:
            print(f"INFO: Запрос на генерацию изображения: {prompt[:50]}...")
            if not self.kandinsky_api_key or not self.kandinsky_secret_key:
                print("ERROR: Kandinsky API ключи не настроены. Проверьте файл .env")
                print(f"ERROR: KANDINSKY_API_KEY установлен: {bool(self.kandinsky_api_key)}")
                print(f"ERROR: KANDINSKY_SECRET_KEY установлен: {bool(self.kandinsky_secret_key)}")
                return None
            
            # Шаг 1: Запускаем генерацию
            print(f"INFO: Отправка запроса в Kandinsky API: {self.kandinsky_url}")
            headers = {
                'X-Key': f'Key {self.kandinsky_api_key}',
                'X-Secret': f'Secret {self.kandinsky_secret_key}'
            }
            
            data = {
                'type': 'GENERATE',
                'numImages': 1,
                'width': 1024,
                'height': 1024,
                'generateParams': {
                    'query': prompt
                }
            }
            
            print(f"INFO: Kandinsky запрос: {json.dumps(data, ensure_ascii=False)[:200]}...")
            response = requests.post(
                self.kandinsky_url,
                headers=headers,
                json=data,
                timeout=30
            )
            
            print(f"INFO: Kandinsky ответ: Status {response.status_code}")
            if response.status_code != 200:
                print(f"ERROR: Kandinsky API HTTP Error: {response.status_code}")
                print(f"ERROR: Response: {response.text}")
                return None
            
            result = response.json()
            print(f"INFO: Kandinsky ответ получен: {json.dumps(result, ensure_ascii=False)[:200]}...")
            uuid = result.get('uuid')
            
            if not uuid:
                print(f"ERROR: Kandinsky API не вернул UUID. Response: {result}")
                return None
            
            print(f"INFO: Kandinsky UUID получен: {uuid}, ожидаем генерации...")
            # Шаг 2: Ожидаем готовности изображения
            import time
            max_attempts = 30
            for attempt in range(max_attempts):
                time.sleep(2)  # Ждем 2 секунды между запросами
                
                status_response = requests.get(
                    f"{self.kandinsky_status_url}/{uuid}",
                    headers=headers,
                    timeout=10
                )
                
                if status_response.status_code != 200:
                    print(f"WARNING: Kandinsky статус запрос вернул {status_response.status_code}, попытка {attempt + 1}/{max_attempts}")
                    continue
                
                status_result = status_response.json()
                status = status_result.get('status')
                print(f"INFO: Kandinsky статус (попытка {attempt + 1}/{max_attempts}): {status}")
                
                if status == 'DONE':
                    # Изображение готово
                    images = status_result.get('images', [])
                    if images:
                        print(f"INFO: Kandinsky изображение готово, размер base64: {len(images[0])} символов")
                        # Возвращаем base64 изображение
                        return images[0]
                    else:
                        print("ERROR: Kandinsky статус DONE, но изображения нет в ответе")
                        break
                elif status == 'FAIL':
                    error_msg = status_result.get('error', 'Unknown error')
                    print(f"ERROR: Kandinsky генерация не удалась: {error_msg}")
                    print(f"ERROR: Полный ответ: {json.dumps(status_result, ensure_ascii=False)}")
                    return None
            
            print("ERROR: Превышено время ожидания генерации изображения Kandinsky (60 секунд)")
            return None
            
        except requests.exceptions.Timeout:
            print("ERROR: Превышено время ожидания ответа от Kandinsky API")
            return None
        except Exception as e:
            print(f"Kandinsky API Error: {e}")
            return None
    
    def generate_expert(self, description):
        """Generate expert prompt and avatar using GigaChat and Kandinsky"""
        print(f"INFO: Начало генерации эксперта для описания: {description[:50]}...")
        
        system_prompt = """Ты помощник для создания образовательных экспертов. 
        Создай детальный промпт для ИИ-эксперта на основе описания администратора.
        Промпт должен описывать личность, стиль общения и экспертизу."""
        
        prompt = f"""На основе следующего описания создай детальный промпт для ИИ-эксперта:
        
        {description}
        
        Верни только промпт для эксперта, который будет использоваться для общения с учениками."""
        
        print("INFO: Генерация промпта эксперта через GigaChat...")
        expert_prompt = self._make_request(prompt, system_prompt)
        print(f"INFO: Промпт эксперта получен: {expert_prompt[:100] if expert_prompt else 'None'}...")
        
        # Generate avatar description for image generation
        avatar_prompt_text = f"""Опиши внешность аватара для эксперта: {description}
        Верни краткое описание (2-3 предложения) для генерации аватара."""
        
        print("INFO: Генерация описания аватара через GigaChat...")
        avatar_description = self._make_request(avatar_prompt_text)
        print(f"INFO: Описание аватара получено: {avatar_description[:100] if avatar_description else 'None'}...")
        
        # Generate actual avatar image using Kandinsky
        avatar_image_base64 = None
        if avatar_description:
            # Create prompt for image generation
            image_prompt = f"Профессиональный портрет преподавателя, {avatar_description}, стиль: дружелюбный и профессиональный, высокое качество"
            print(f"INFO: Запуск генерации изображения аватара через Kandinsky...")
            avatar_image_base64 = self.generate_image(image_prompt)
            if avatar_image_base64:
                print(f"INFO: Изображение аватара успешно сгенерировано, размер: {len(avatar_image_base64)} символов")
            else:
                print("WARNING: Не удалось сгенерировать изображение аватара, будет использовано текстовое описание")
        else:
            print("WARNING: Описание аватара не получено, пропускаем генерацию изображения")
        
        return expert_prompt or "Добрый и опытный преподаватель, готовый помочь в обучении.", avatar_description or "Профессиональный преподаватель", avatar_image_base64
    
    def analyze_material(self, material_text, expert_prompt=None):
        """Analyze educational material and create explanation"""
        system_prompt = expert_prompt or "Ты опытный преподаватель, который объясняет материал простым и понятным языком."
        
        prompt = f"""Проанализируй следующий учебный материал и создай понятное объяснение для ученика:
        
        {material_text}
        
        Создай структурированное объяснение материала, которое будет озвучено для ученика."""
        
        explanation = self._make_request(prompt, system_prompt)
        return explanation or "Материал проанализирован. Приступаем к изучению!"
    
    def generate_quiz(self, material_text, explanation, expert_prompt=None, num_questions=10):
        """Generate quiz based on material"""
        system_prompt = expert_prompt or "Ты опытный преподаватель, создающий интересные и полезные викторины."
        
        prompt = f"""На основе следующего учебного материала и объяснения создай викторину:
        
        Материал: {material_text}
        
        Объяснение: {explanation}
        
        Создай викторину из {num_questions} вопросов (от 5 до 15). 
        Вопросы могут быть трех типов:
        1. text - вопрос с текстовым ответом
        2. single - вопрос с выбором одного ответа
        3. multiple - вопрос с выбором нескольких ответов
        
        Верни результат ТОЛЬКО в формате JSON, без дополнительного текста:
        {{
            "questions": [
                {{
                    "question_text": "Текст вопроса",
                    "question_type": "single",
                    "options": ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4"],
                    "correct_answer": "Вариант 1"
                }}
            ]
        }}
        
        Для вопросов типа "text" не указывай options, а в correct_answer укажи правильный ответ.
        Для вопросов типа "multiple" в correct_answer укажи массив правильных ответов.
        Важно: верни ТОЛЬКО валидный JSON, без markdown разметки и дополнительных комментариев.
        """
        
        quiz_json = self._make_request(prompt, system_prompt, temperature=0.7)
        
        try:
            # Try to extract JSON from response
            if quiz_json:
                # Remove markdown code blocks if present
                quiz_json = quiz_json.strip()
                if quiz_json.startswith('```'):
                    # Remove ```json or ``` markers
                    parts = quiz_json.split('```')
                    if len(parts) > 1:
                        quiz_json = parts[1]
                        if quiz_json.startswith('json'):
                            quiz_json = quiz_json[4:]
                quiz_json = quiz_json.strip()
                
                # Try to find JSON object in the response
                start_idx = quiz_json.find('{')
                end_idx = quiz_json.rfind('}') + 1
                if start_idx != -1 and end_idx > start_idx:
                    quiz_json = quiz_json[start_idx:end_idx]
                
                quiz_data = json.loads(quiz_json)
                return quiz_data.get('questions', [])
        except json.JSONDecodeError as e:
            print(f"Failed to parse quiz JSON: {e}")
            print(f"Response was: {quiz_json[:500]}")
        
        return []
    
    def generate_lesson_summary(self, material_text, user_answers, expert_prompt=None):
        """Generate summary after quiz completion"""
        system_prompt = expert_prompt or "Ты опытный преподаватель, который дает конструктивную обратную связь."
        
        correct_count = sum(1 for ans in user_answers if ans.get('is_correct', False))
        total_count = len(user_answers)
        
        prompt = f"""Ученик прошел викторину по следующему материалу:
        
        Материал: {material_text}
        
        Результат: {correct_count} из {total_count} правильных ответов.
        
        Создай мотивирующий и конструктивный итог урока, подчеркни сильные стороны и дай рекомендации по улучшению."""
        
        summary = self._make_request(prompt, system_prompt)
        return summary or "Отличная работа! Продолжай в том же духе!"

