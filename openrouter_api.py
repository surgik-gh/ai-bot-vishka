import json
import time

import requests

from config import Config


class OpenRouterAPI:
    def __init__(self, api_key=None):
        # Используем жестко заданный ключ из конфигурации
        self.api_key = Config.OPENROUTER_API_KEY
        self.default_model = Config.OPENROUTER_MODEL
        self.base_url = "https://openrouter.ai/api/v1"
        self.chat_url = f"{self.base_url}/chat/completions"
    
    def get_model(self, user_model=None):
        """Получить модель для использования (всегда используем дефолтную)"""
        return self.default_model

    def _make_request(
        self,
        messages,
        model=None,
        temperature=0.7,
        max_tokens=1000,
        use_reasoning=False,
    ):
        """Отправка запроса к OpenRouter API с поддержкой reasoning"""
        # Всегда используем модель по умолчанию
        model = self.default_model
        
        if not self.api_key:
            raise ValueError("OpenRouter API key is not configured")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://your-site.com",  # Optional
            "X-Title": "AI Bot",  # Optional
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # Добавляем reasoning, если включено
        if use_reasoning:
            payload["reasoning"] = {"enabled": True}

        try:
            response = requests.post(
                self.chat_url, headers=headers, json=payload, timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"OpenRouter API error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    print(f"Error details: {error_data}")
                except:
                    print(f"Response text: {e.response.text}")
            raise

    def analyze_material(self, material_text, expert_prompt=None, model=None):
        """Анализ учебного материала"""
        model = self.default_model  # Всегда используем дефолтную модель

        prompt = f"""Проанализируйте следующий учебный материал и объясните его доступно для ученика:

{material_text}

{f"Инструкции эксперта: {expert_prompt}" if expert_prompt else ""}

Предоставьте краткое, но полное объяснение основных понятий и идей."""

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self._make_request(messages, model=model, max_tokens=1500)
            explanation = response["choices"][0]["message"]["content"].strip()
            return (
                explanation if explanation else "Не удалось проанализировать материал."
            )
        except Exception as e:
            print(f"Ошибка анализа материала: {e}")
            raise

    def generate_quiz(
        self,
        material_text,
        explanation,
        expert_prompt=None,
        num_questions=10,
        model=None,
    ):
        """Генерация вопросов для викторины"""
        model = self.default_model  # Всегда используем дефолтную модель

        prompt = f"""На основе следующего учебного материала и объяснения создайте {num_questions} вопросов для викторины.

Материал: {material_text}

Объяснение: {explanation}

{f"Инструкции эксперта: {expert_prompt}" if expert_prompt else ""}

Требования:
- Вопросы должны быть разнообразными (факты, понимание, применение)
- Каждый вопрос должен иметь правильный ответ
- Для вопросов с вариантами ответов предоставьте 4 варианта, с одним правильным
- Формат ответа: JSON массив с объектами в формате:
  {{
    "question_text": "Текст вопроса",
    "question_type": "single",  // или "multiple" или "text"
    "correct_answer": "Правильный ответ",
    "options": ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4"] // только для single/multiple
  }}

Верните только JSON массив, без дополнительного текста."""

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self._make_request(messages, model=model, max_tokens=2000, use_reasoning=True)
            content = response["choices"][0]["message"]["content"].strip()

            # Очистка от возможного markdown
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]

            questions_data = json.loads(content)
            return questions_data if isinstance(questions_data, list) else []
        except Exception as e:
            print(f"Ошибка генерации викторины: {e}")
            raise

    def generate_expert(self, expert_name, expert_description):
        """Генерация промпта для эксперта и описания аватара"""
        # Генерация промпта
        prompt_prompt = f"""Создайте инструкцию для AI-эксперта с именем "{expert_name}".

Описание эксперта: {expert_description}

Инструкция должна быть в формате промпта, который будет использоваться в запросах к AI для ролевого обучения.

Промпт должен:
- Определять роль и стиль преподавания
- Указывать уровень сложности материала
- Определять подход к объяснению (например, аналитический, практический, творческий)
- Быть кратким и четким

Верните только промпт, без дополнительного текста."""

        messages_prompt = [{"role": "user", "content": prompt_prompt}]

        try:
            response = self._make_request(messages_prompt, max_tokens=500)
            expert_prompt = response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Ошибка генерации промпта эксперта: {e}")
            raise

        # Генерация описания аватара
        avatar_prompt = f"""Создайте текстовое описание аватара для AI-эксперта с именем "{expert_name}".

Описание эксперта: {expert_description}

Описание аватара должно быть кратким и подходящим для использования в качестве текстового представления (например, emoji или текстовое описание).

Верните только описание, без дополнительного текста."""

        messages_avatar = [{"role": "user", "content": avatar_prompt}]

        try:
            response_avatar = self._make_request(messages_avatar, max_tokens=100)
            avatar_description = response_avatar["choices"][0]["message"][
                "content"
            ].strip()
        except Exception as e:
            print(f"Ошибка генерации описания аватара: {e}")
            avatar_description = "👤"  # fallback

        return expert_prompt, avatar_description, None

    def chat_with_expert(self, message, expert_prompt, conversation_history=None, model=None):
        """Чат с экспертом с поддержкой reasoning"""
        model = self.default_model  # Всегда используем дефолтную модель
        
        # Формируем системный промпт для эксперта
        system_message = {
            "role": "system",
            "content": expert_prompt if expert_prompt else "Вы - опытный преподаватель, который помогает ученикам в обучении. Отвечайте дружелюбно и понятно."
        }
        
        # Формируем историю сообщений
        messages = [system_message]
        
        # Добавляем историю разговора, если есть (с сохранением reasoning_details)
        if conversation_history:
            for msg in conversation_history:
                # Сохраняем reasoning_details, если они есть (для продолжения reasoning)
                if isinstance(msg, dict):
                    msg_copy = {
                        "role": msg.get("role"),
                        "content": msg.get("content")
                    }
                    # Добавляем reasoning_details, если они есть
                    if "reasoning_details" in msg:
                        msg_copy["reasoning_details"] = msg["reasoning_details"]
                    messages.append(msg_copy)
                else:
                    messages.append(msg)
        
        # Добавляем текущее сообщение пользователя
        messages.append({
            "role": "user",
            "content": message
        })
        
        try:
            # Используем reasoning для лучших ответов
            response = self._make_request(messages, model=model, max_tokens=1000, temperature=0.7, use_reasoning=True)
            response_data = response["choices"][0]["message"]
            
            # Извлекаем ответ и reasoning_details
            reply = response_data.get("content", "").strip()
            reasoning_details = response_data.get("reasoning_details")
            
            # Возвращаем reply и reasoning_details для сохранения в истории
            # reasoning_details будут сохранены в routes.py
            result = {
                "reply": reply if reply else "Извините, не удалось получить ответ.",
                "reasoning_details": reasoning_details
            }
            return result
        except Exception as e:
            print(f"Ошибка чата с экспертом: {e}")
            raise

    def generate_lesson_summary(self, material_text, quiz_answers, model=None):
        """Генерация сводки урока на основе ответов ученика"""
        model = self.default_model  # Всегда используем дефолтную модель

        prompt = f"""На основе учебного материала и ответов ученика в викторине создайте персонализированную сводку урока.

Материал: {material_text}

Ответы викторины: {json.dumps(quiz_answers, ensure_ascii=False)}

Сводка должна:
- Подвести итоги изученного
- Отметить сильные стороны ученика
- Указать на темы, требующие дополнительного внимания
- Дать рекомендации для дальнейшего изучения

Будьте поощрительны и конструктивны."""

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self._make_request(messages, model=model, max_tokens=1000)
            summary = response["choices"][0]["message"]["content"].strip()
            return summary
        except Exception as e:
            print(f"Ошибка генерации сводки: {e}")
            raise
