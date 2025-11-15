import google.generativeai as genai
import json
import base64
import requests
from config import Config

class GeminiAPI:
    def __init__(self):
        self.api_key = Config.GEMINI_API_KEY
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        self.imagen_api_key = Config.GEMINI_API_KEY  # Imagen использует тот же API ключ
    
    def _make_request(self, prompt, system_prompt=None, temperature=0.6, max_tokens=2000):
        """Make request to Gemini API"""
        try:
            if not self.api_key:
                print("ERROR: Gemini API ключ не настроен. Проверьте файл .env")
                return None
            
            # Combine system prompt and user prompt
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            
            # Configure generation settings
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            
            response = self.model.generate_content(
                full_prompt,
                generation_config=generation_config
            )
            
            return response.text
        except Exception as e:
            error_msg = f"Gemini API Error: {e}"
            print(error_msg)
            return None
    
    def generate_image(self, prompt, style='default'):
        """Generate image using Imagen API via Vertex AI"""
        try:
            if not self.api_key:
                print("ERROR: Gemini API ключ не настроен для генерации изображений")
                return None
            
            # Note: Imagen API requires Vertex AI project setup
            # For now, we return None and use text description as fallback
            # To enable image generation, you need to:
            # 1. Set up a Google Cloud project with Vertex AI enabled
            # 2. Install google-cloud-aiplatform package
            # 3. Configure authentication (service account or user credentials)
            # 4. Use Vertex AI Imagen API
            
            # For basic setup, we'll return None and the system will use text description
            print(f"INFO: Image generation requested for: {prompt}")
            print("INFO: Imagen API requires Vertex AI setup. Using text description as fallback.")
            return None
            
        except Exception as e:
            print(f"Imagen API Error: {e}")
            return None
    
    def generate_expert(self, description):
        """Generate expert prompt and avatar using Gemini"""
        system_prompt = """Ты помощник для создания образовательных экспертов. 
        Создай детальный промпт для ИИ-эксперта на основе описания администратора.
        Промпт должен описывать личность, стиль общения и экспертизу."""
        
        prompt = f"""На основе следующего описания создай детальный промпт для ИИ-эксперта:
        
        {description}
        
        Верни только промпт для эксперта, который будет использоваться для общения с учениками."""
        
        expert_prompt = self._make_request(prompt, system_prompt)
        
        # Generate avatar description for image generation
        avatar_prompt_text = f"""Опиши внешность аватара для эксперта: {description}
        Верни краткое описание (2-3 предложения) для генерации аватара."""
        
        avatar_description = self._make_request(avatar_prompt_text)
        
        # Generate actual avatar image using Imagen
        avatar_image_base64 = None
        if avatar_description:
            # Create prompt for image generation
            image_prompt = f"Профессиональный портрет преподавателя, {avatar_description}, стиль: дружелюбный и профессиональный, высокое качество"
            avatar_image_base64 = self.generate_image(image_prompt)
        
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

