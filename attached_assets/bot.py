import sys
import locale

# Автоматически определяем кодировку системы
default_encoding = locale.getpreferredencoding() 

# Устанавливаем стандартные кодировки
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr


import os
import sqlite3
import datetime
import telebot
from telebot import types
import json
from fpdf import FPDF

from whisper_transcription import transcribe_audio
from ya_gpt import ya_request_1, ya_request_2

# Конфигурация
BOT_TOKEN = '7668766634:AAGHWABEISVBDjtB0sLEturG0QsG4edcXmc'
DB_NAME = 'bot.db'
AUDIO_DIR = 'temp_audio'

# Инициализация бота и папки для аудио
bot = telebot.TeleBot(BOT_TOKEN)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Хранение состояния пользователей
user_states = {}  # {user_id: list_of_question_ids}

def get_questions_by_survey_id(survey_id: int) -> list:
    """
    Получает список вопросов по ID анкеты.
    
    :param survey_id: ID анкеты
    :return: Список вопросов (текст вопросов)
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Выполняем SQL-запрос для получения вопросов
    cursor.execute('''
        SELECT question_id, question_text FROM questions WHERE survey_id = ?
    ''', (survey_id,))

    # Получаем все строки результата
    questions = str({row[0]: row[1] for row in cursor.fetchall()})
    conn.close()
    return questions

def get_question_by_id(question_id: int) -> str:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT question_text FROM questions WHERE question_id = ?', (question_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def register_user(user_id, username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, user_id, created_at) VALUES (?, ?, ?)",
                  (username, user_id, datetime.datetime.now()))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

def add_answer(inspection_id: int, question_id: int, answer_text: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Обновляем существующую запись или вставляем новую
    cursor.execute('''
        UPDATE answers SET answer_text = ? 
        WHERE inspection_id = ? AND question_id = ?
    ''', (answer_text, inspection_id, question_id))
    
    if cursor.rowcount == 0:
        cursor.execute('''
            INSERT INTO answers (inspection_id, question_id, answer_text)
            VALUES (?, ?, ?)
        ''', (inspection_id, question_id, answer_text))
    
    conn.commit()
    conn.close()

def get_null_questions(inspection_id: int) -> list:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT question_id FROM answers 
        WHERE inspection_id = ? AND answer_text = "null"
    ''', (inspection_id,))
    null_questions = [row[0] for row in cursor.fetchall()]
    conn.close()
    return null_questions

def send_null_questions_to_bot(user_id, questions):
    if not questions:
        bot.send_message(user_id, "🎉 Все вопросы заполнены! Формируем отчет...")
        send_report_to_user(user_id, inspection_id=2)
        return

    user_states[user_id] = questions  # Сохраняем вопросы для пользователя
    
    bot.send_message(user_id, "❓ Вопросы, требующие ответов:")
    for i, q_id in enumerate(questions, 1):
        question_text = get_question_by_id(q_id)
        if question_text:
            bot.send_message(user_id, f"{i}. {question_text}\n/answer {i} [ваш ответ]")
            
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
        self.set_font('DejaVu', '', 12)
def generate_inspection_report(inspection_id: int) -> str:
    """Генерирует PDF отчет с поддержкой UTF-8"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT q.question_text, a.answer_text 
        FROM answers a
        JOIN questions q ON a.question_id = q.question_id
        WHERE a.inspection_id = ?
        ORDER BY q.question_id
    ''', (inspection_id,))
    
    report_data = cursor.fetchall()
    conn.close()
    
    if not report_data:
        return None
    
    pdf = PDF()
    pdf.add_page()
    
    # Заголовок
    pdf.set_font('DejaVu', '', 16)
    pdf.cell(200, 10, txt="ОТЧЕТ О ПРОВЕРКЕ", ln=True, align='C')
    pdf.ln(15)
    
    # Содержание
    pdf.set_font('DejaVu', '', 12)
    for idx, (question, answer) in enumerate(report_data, 1):
        # Проверка и преобразование текста
        def safe_text(text):
            return text if isinstance(text, str) else str(text, 'utf-8')
        
        question = safe_text(question)
        answer = safe_text(answer)
        
        pdf.multi_cell(0, 8, f"Вопрос #{idx}:\n{question}", 0, 'L')
        pdf.multi_cell(0, 8, f"Ответ:\n{answer}", 0, 'L')
        pdf.ln(10)
    
    filename = f"report_{inspection_id}.pdf"
    filepath = os.path.join(AUDIO_DIR, filename)
    pdf.output(filepath)
    
    return filepath

def send_report_to_user(user_id: int, inspection_id: int):
    """Генерирует и отправляет отчет пользователю"""
    try:
        report_path = generate_inspection_report(inspection_id)
        if not report_path:
            bot.send_message(user_id, "❌ Не удалось сформировать отчет")
            return
            
        with open(report_path, 'rb') as report_file:
            bot.send_document(
                chat_id=user_id,
                document=report_file,
                caption=f"📄 Отчет по проверке #{inspection_id}",
                timeout=30
            )
        
        # Удаляем временный файл
        os.remove(report_path)
        
    except Exception as e:
        bot.send_message(user_id, f"❌ Ошибка при создании отчета: {str(e)}")


@bot.message_handler(commands=['start'])
def handle_start(message):
    register_user(message.from_user.id, message.from_user.username)
    bot.reply_to(message, "Добро пожаловать! Отправьте аудио /process_audio")

@bot.message_handler(commands=['process_audio'])
def handle_process_audio(message):
    msg = bot.reply_to(message, "Отправьте аудиофайл в формате MP3")
    bot.register_next_step_handler(msg, process_audio_step)

@bot.message_handler(commands=['answer'])
def handle_answer(message):
    try:
        user_id = message.from_user.id
        args = message.text.split()
        
        if len(args) < 3:
            bot.send_message(user_id, "❌ Формат: /answer [номер] [ответ]")
            return
            
        _, num_str, *answer_parts = args
        answer_text = ' '.join(answer_parts)
        
        if not num_str.isdigit():
            bot.send_message(user_id, "❌ Номер должен быть числом")
            return
            
        question_num = int(num_str)
        questions = user_states.get(user_id, [])
        
        if not (1 <= question_num <= len(questions)):
            bot.send_message(user_id, f"❌ Номер должен быть от 1 до {len(questions)}")
            return
            
        question_id = questions[question_num-1]
        add_answer(2, question_id, answer_text)
        
        # Обновляем список вопросов
        remaining_questions = get_null_questions(2)
        if remaining_questions:
            send_null_questions_to_bot(user_id, remaining_questions)
        else:
            bot.send_message(user_id, "✅ Все ответы сохранены! Формируем отчет...")
            send_report_to_user(user_id, inspection_id=2)
            del user_states[user_id]
            
    except Exception as e:
        bot.send_message(user_id, f"❌ Ошибка: {str(e)}")

def process_audio_step(message):
    try:
        user_id = message.from_user.id
        
        # Скачивание и сохранение аудио
        if message.document and message.document.mime_type == 'audio/mpeg':
            file_id = message.document.file_id
        elif message.audio and message.audio.mime_type == 'audio/mpeg':
            file_id = message.audio.file_id
        else:
            bot.send_message(user_id, "❌ Требуется MP3 файл!")
            return
            
        file_info = bot.get_file(file_id)
        audio_path = os.path.join(AUDIO_DIR, f"{user_id}_{datetime.datetime.now().timestamp()}.mp3")
        
        with open(audio_path, 'wb') as f:
            f.write(bot.download_file(file_info.file_path))
        
        # Обработка аудио
        bot.send_message(user_id, "🔄 Обработка аудио...")
        text = transcribe_audio(audio_path)
        
        # GPT обработка
        bot.send_message(user_id, "🔄 Анализ содержания...")
        result1 = ya_request_1(text)
        with open('files/transcript1.txt', 'w', encoding='utf-8') as f:
            f.write(result1)
        bot.send_message(user_id, "🔄 Формирование ответов...")
        survey_questions = get_questions_by_survey_id(3)
        result2 = ya_request_2(result1, survey_questions)
        with open('files/transcript2.txt', 'w', encoding='utf-8') as f:
            f.write(result2)
        # Парсинг и сохранение ответов
        try:
            result2 = str(result2)
            result2 = result2.replace("```", "")
            answers = json.loads(result2)
            for q_id, answer in answers.items():
                add_answer(2, int(q_id), str(answer))
        except Exception as e:
            bot.send_message(user_id, f"❌ Ошибка парсинга ответов: {str(e)}")
            return
        
        # Отправка неотвеченных вопросов
        null_questions = get_null_questions(2)
        send_null_questions_to_bot(user_id, null_questions)
        
        os.remove(audio_path)
        
    except Exception as e:
        bot.send_message(user_id, f"❌ Ошибка: {str(e)}")
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)

if __name__ == '__main__':
    bot.polling(none_stop=True)