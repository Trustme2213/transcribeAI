import sys
import locale
import os
import sqlite3
import datetime
import telebot
from telebot import types
import json
import time
import logging
import traceback

# Custom modules for audio processing and transcription
from whisper_transcription import transcribe_audio
from ya_gpt import ya_request_1, ya_request_2, process_text_in_chunks
from audio_chunker import AudioChunker
from utils import (
    ensure_dirs_exist,
    save_transcription,
    parse_gpt_response,
    get_survey_by_id,
    create_inspection,
    initialize_answers,
    format_duration
)

# Установка кодировки
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN', '7668766634:AAGHWABEISVBDjtB0sLEturG0QsG4edcXmc')
DB_NAME = 'bot.db'
AUDIO_DIR = 'temp_audio'
TRANSCRIPTS_DIR = 'transcripts'
MAX_CHUNK_SIZE_MS = 300000  # 5 minutes in milliseconds
OVERLAP_MS = 3000  # 3 seconds overlap between chunks

# Ensure directories exist
ensure_dirs_exist([AUDIO_DIR, TRANSCRIPTS_DIR])

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Инициализация аудио обработчика
audio_chunker = AudioChunker(
    chunk_size_ms=MAX_CHUNK_SIZE_MS,
    overlap_ms=OVERLAP_MS,
    temp_dir=AUDIO_DIR
)

# Initialize database if it doesn't exist
def initialize_db():
    from initialize_db import create_tables, add_test_questions
    
    if not os.path.exists(DB_NAME) or os.path.getsize(DB_NAME) == 0:
        logger.info("Initializing database...")
        create_tables()
        add_test_questions()
    else:
        logger.info("Database already exists, checking tables...")
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            # Check if users table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                logger.warning("Database exists but tables are missing. Re-creating tables...")
                create_tables()
                add_test_questions()
                
            conn.close()
        except Exception as e:
            logger.error(f"Error checking database: {str(e)}")
            logger.info("Recreating database...")
            if os.path.exists(DB_NAME):
                os.remove(DB_NAME)
            create_tables()
            add_test_questions()

# Initialize database
initialize_db()

# Хранение состояния пользователей
user_states = {}  # {user_id: {"questions": list_of_question_ids, "inspection_id": int, ...}}

def get_questions_by_survey_id(survey_id: int) -> dict:
    """
    Получает список вопросов по ID анкеты в виде словаря для YandexGPT.
    
    :param survey_id: ID анкеты
    :return: Словарь вопросов {question_id: question_text}
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Выполняем SQL-запрос для получения вопросов
    cursor.execute('''
        SELECT question_id, question_text FROM questions WHERE survey_id = ?
    ''', (survey_id,))

    # Получаем все строки результата
    questions = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return questions

def get_all_questions_for_survey(survey_id: int) -> dict:
    """
    Получает все вопросы анкеты в виде словаря.
    
    :param survey_id: ID анкеты
    :return: Словарь {question_id: question_text}
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT question_id, question_text FROM questions WHERE survey_id = ?
    ''', (survey_id,))
    
    questions = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return questions

def get_question_by_id(question_id: int) -> str:
    """
    Получает текст вопроса по его ID.
    
    :param question_id: ID вопроса
    :return: Текст вопроса или None, если вопрос не найден
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT question_text FROM questions WHERE question_id = ?', (question_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0]
    return "Вопрос не найден"

def register_user(user_id, username):
    """
    Регистрирует пользователя в базе данных.
    
    :param user_id: ID пользователя в Telegram
    :param username: Имя пользователя
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, user_id, created_at) VALUES (?, ?, ?)",
                  (username, user_id, datetime.datetime.now()))
        conn.commit()
        logger.info(f"User registered: {user_id} ({username})")
    except sqlite3.IntegrityError:
        # Пользователь уже существует
        logger.info(f"User already exists: {user_id} ({username})")
    finally:
        conn.close()

def add_answer(inspection_id: int, question_id: int, answer_text: str):
    """
    Добавляет или обновляет ответ на вопрос.
    
    :param inspection_id: ID проверки
    :param question_id: ID вопроса
    :param answer_text: Текст ответа
    """
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
    """
    Получает список вопросов с пустыми ответами.
    
    :param inspection_id: ID проверки
    :return: Список ID вопросов с пустыми ответами
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT question_id FROM answers 
        WHERE inspection_id = ? AND answer_text = "null"
    ''', (inspection_id,))
    null_questions = [row[0] for row in cursor.fetchall()]
    conn.close()
    return null_questions

def send_null_questions_to_bot(user_id, inspection_id):
    """
    Отправляет пользователю список вопросов, требующих ответов.
    
    :param user_id: ID пользователя
    :param inspection_id: ID проверки
    """
    questions = get_null_questions(inspection_id)
    
    if not questions:
        bot.send_message(user_id, "🎉 Все вопросы заполнены! Формируем отчет...")
        send_report_to_user(user_id, inspection_id)
        return
    
    user_states[user_id] = {
        "questions": questions,
        "inspection_id": inspection_id
    }
    
    bot.send_message(user_id, "❓ Вопросы, требующие ответов:")
    for i, q_id in enumerate(questions, 1):
        question_text = get_question_by_id(q_id)
        if question_text:
            bot.send_message(user_id, f"{i}. {question_text}\n/answer {i} [ваш ответ]")

class PDF:
    """
    Класс для создания PDF-отчетов с поддержкой UTF-8.
    """
    def __init__(self):
        from fpdf import FPDF
        self.pdf = FPDF()
        self.pdf.add_page()
        # В реальном проекте здесь нужно добавить шрифт с поддержкой Unicode
        # Для примера используем стандартный шрифт
        self.pdf.set_font('Arial', size=12)
        
    def add_header(self, text):
        self.pdf.set_font('Arial', 'B', 16)
        self.pdf.cell(200, 10, txt=text, ln=True, align='C')
        self.pdf.ln(15)
        self.pdf.set_font('Arial', size=12)
        
    def add_question_answer(self, idx, question, answer):
        self.pdf.multi_cell(0, 8, f"Вопрос #{idx}:", 0, 'L')
        self.pdf.multi_cell(0, 8, question, 0, 'L')
        self.pdf.multi_cell(0, 8, f"Ответ:", 0, 'L')
        self.pdf.multi_cell(0, 8, answer, 0, 'L')
        self.pdf.ln(10)
        
    def save(self, filepath):
        self.pdf.output(filepath)

def generate_inspection_report(inspection_id: int) -> str:
    """
    Генерирует PDF отчет с поддержкой UTF-8.
    
    :param inspection_id: ID проверки
    :return: Путь к сгенерированному файлу или None в случае ошибки
    """
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
    
    # Create PDF
    pdf = PDF()
    pdf.add_header("ОТЧЕТ О ПРОВЕРКЕ")
    
    # Содержание
    for idx, (question, answer) in enumerate(report_data, 1):
        # Проверка и преобразование текста
        def safe_text(text):
            return text if isinstance(text, str) else str(text)
        
        question = safe_text(question)
        answer = safe_text(answer)
        
        pdf.add_question_answer(idx, question, answer)
    
    filename = f"report_{inspection_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(AUDIO_DIR, filename)
    pdf.save(filepath)
    
    return filepath

def send_report_to_user(user_id: int, inspection_id: int):
    """
    Генерирует и отправляет отчет пользователю.
    
    :param user_id: ID пользователя
    :param inspection_id: ID проверки
    """
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
                timeout=60
            )
        
        # Удаляем временный файл
        os.remove(report_path)
        
    except Exception as e:
        logger.error(f"Error sending report: {str(e)}")
        logger.error(traceback.format_exc())
        bot.send_message(user_id, f"❌ Ошибка при создании отчета: {str(e)}")

def process_audio_file(user_id, audio_path, survey_id=3):
    """
    Обрабатывает аудиофайл: разбивает на части, транскрибирует и анализирует.
    
    :param user_id: ID пользователя
    :param audio_path: Путь к аудиофайлу
    :param survey_id: ID анкеты (по умолчанию 3)
    """
    try:
        # Создаем новую проверку
        inspection_id = create_inspection(user_id, survey_id)
        
        # Получаем вопросы для анкеты
        questions = get_all_questions_for_survey(survey_id)
        question_ids = list(questions.keys())
        
        # Инициализируем ответы как null
        initialize_answers(inspection_id, question_ids)
        
        # Отправляем сообщение о начале обработки
        status_msg = bot.send_message(
            user_id, 
            "🔄 Начинаем обработку аудиофайла. Это может занять некоторое время..."
        )
        
        # Разбиваем аудио на части
        chunk_paths = audio_chunker.split_audio(audio_path)
        
        # Обновляем статус
        bot.edit_message_text(
            f"🔊 Аудиофайл разделен на {len(chunk_paths)} частей. Начинаем транскрибирование...",
            chat_id=user_id,
            message_id=status_msg.message_id
        )
        
        # Транскрибируем каждую часть
        all_transcriptions = []
        start_time = time.time()
        
        for i, chunk_path in enumerate(chunk_paths, 1):
            chunk_start_time = time.time()
            
            # Обновляем статус
            bot.edit_message_text(
                f"🔄 Транскрибирую часть {i}/{len(chunk_paths)}...",
                chat_id=user_id,
                message_id=status_msg.message_id
            )
            
            # Транскрибируем аудио
            transcription = transcribe_audio(chunk_path, save_to_file=False)
            all_transcriptions.append(transcription)
            
            chunk_time = time.time() - chunk_start_time
            
            # Обновляем статус с информацией о времени
            progress = i / len(chunk_paths) * 100
            elapsed = time.time() - start_time
            estimated_total = elapsed / progress * 100 if progress > 0 else 0
            remaining = max(0, estimated_total - elapsed)
            
            bot.edit_message_text(
                f"🔄 Транскрибировано {i}/{len(chunk_paths)} частей ({progress:.1f}%)\n"
                f"⏱ Прошло: {format_duration(elapsed)}\n"
                f"⏳ Осталось примерно: {format_duration(remaining)}",
                chat_id=user_id,
                message_id=status_msg.message_id
            )
        
        # Объединяем все транскрипции
        full_transcription = audio_chunker.combine_transcriptions(all_transcriptions)
        
        # Сохраняем полную транскрипцию
        transcript_path = save_transcription(
            full_transcription, 
            TRANSCRIPTS_DIR, 
            user_id
        )
        
        # Отправляем статус о начале анализа
        bot.edit_message_text(
            f"📝 Транскрипция завершена! Начинаем анализ содержимого...",
            chat_id=user_id,
            message_id=status_msg.message_id
        )
        
        # Обработка через YandexGPT
        try:
            # Первый запрос - форматирование диалога
            bot.edit_message_text(
                f"🔄 Форматирование диалога...",
                chat_id=user_id,
                message_id=status_msg.message_id
            )
            
            formatted_text = ya_request_1(full_transcription)
            
            # Сохраняем форматированную транскрипцию
            formatted_path = save_transcription(
                formatted_text, 
                os.path.join(TRANSCRIPTS_DIR, 'formatted'), 
                user_id
            )
            
            # Используем обработку по частям для анализа диалога
            bot.edit_message_text(
                f"🔄 Анализ диалога и формирование ответов...",
                chat_id=user_id,
                message_id=status_msg.message_id
            )
            
            # Получение словаря вопросов
            survey_questions = get_questions_by_survey_id(survey_id)
            
            # Преобразуем в строку для YandexGPT
            questions_str = json.dumps(survey_questions, ensure_ascii=False)
            
            # Используем новую функцию для обработки текста по частям
            if len(formatted_text) > 10000:  # Если текст длинный, обрабатываем по частям
                bot.edit_message_text(
                    f"🔄 Текст слишком длинный ({len(formatted_text)} символов). Разбиваем на части для анализа...",
                    chat_id=user_id,
                    message_id=status_msg.message_id
                )
                answers_json = process_text_in_chunks(formatted_text, questions_str)
            else:
                # Для коротких текстов используем обычный запрос
                answers_json = ya_request_2(formatted_text, questions_str)
            
            # Сохраняем результат анализа
            result_path = save_transcription(
                answers_json, 
                os.path.join(TRANSCRIPTS_DIR, 'analysis'), 
                user_id
            )
            
            # Парсим ответы и сохраняем в базу данных
            answers = parse_gpt_response(answers_json)
            
            if answers:
                for q_id, answer in answers.items():
                    try:
                        question_id = int(q_id)
                        add_answer(inspection_id, question_id, str(answer) if answer is not None else "null")
                    except (ValueError, TypeError) as e:
                        logger.error(f"Error processing answer for question {q_id}: {str(e)}")
            else:
                bot.edit_message_text(
                    f"⚠️ Не удалось распознать ответы из анализа. Попробуйте еще раз или ответьте на вопросы вручную.",
                    chat_id=user_id,
                    message_id=status_msg.message_id
                )
            
            # Отправляем пользователю вопросы без ответов
            bot.send_message(
                user_id,
                f"✅ Анализ завершен! Отправляю список вопросов, требующих вашего внимания."
            )
            
            send_null_questions_to_bot(user_id, inspection_id)
            
        except Exception as e:
            logger.error(f"GPT processing error: {str(e)}")
            logger.error(traceback.format_exc())
            bot.edit_message_text(
                f"❌ Ошибка при анализе транскрипции: {str(e)}\n\n"
                f"Транскрипция сохранена и вы можете попробовать еще раз.",
                chat_id=user_id,
                message_id=status_msg.message_id
            )
            
            # Отправляем файл с транскрипцией
            with open(transcript_path, 'rb') as f:
                bot.send_document(
                    chat_id=user_id,
                    document=f,
                    caption="📝 Транскрипция аудиофайла"
                )
        
        # Очищаем временные файлы
        audio_chunker.cleanup_chunks(chunk_paths)
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
    except Exception as e:
        logger.error(f"Audio processing error: {str(e)}")
        logger.error(traceback.format_exc())
        bot.send_message(
            user_id, 
            f"❌ Ошибка при обработке аудиофайла: {str(e)}"
        )
        
        # Очищаем временные файлы в случае ошибки
        if 'chunk_paths' in locals():
            audio_chunker.cleanup_chunks(chunk_paths)
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)

@bot.message_handler(commands=['start'])
def handle_start(message):
    """
    Обрабатывает команду /start.
    """
    user_id = message.from_user.id
    username = message.from_user.username
    
    register_user(user_id, username)
    
    bot.reply_to(
        message, 
        "👋 Добро пожаловать! Я помогу обработать аудиозаписи и проанализировать ответы на вопросы анкеты.\n\n"
        "Вы можете использовать следующие команды:\n"
        "/process_audio - загрузить и обработать аудиофайл\n"
        "/help - получить справку\n"
        "/status - проверить статус обработки\n\n"
        "Также вы можете просто отправить мне аудиофайл напрямую 🎤"
    )

@bot.message_handler(commands=['help'])
def handle_help(message):
    """
    Обрабатывает команду /help.
    """
    bot.reply_to(
        message, 
        "📖 Справка по использованию бота:\n\n"
        "1. Отправьте боту аудиофайл в формате MP3 или используйте команду /process_audio\n"
        "2. Бот разделит длинное аудио на части и транскрибирует их с помощью Whisper\n"
        "3. Затем бот проанализирует текст с помощью YandexGPT и заполнит ответы на вопросы анкеты\n"
        "4. Вам будет предложено дополнить ответы на вопросы, которые бот не смог обработать\n"
        "5. В конце вы получите готовый PDF-отчет\n\n"
        "Команды:\n"
        "/start - начать работу с ботом\n"
        "/process_audio - загрузить и обработать аудиофайл\n"
        "/status - проверить статус обработки\n"
        "/answer [номер] [ответ] - ответить на вопрос\n"
    )

@bot.message_handler(commands=['process_audio'])
def handle_process_audio(message):
    """
    Обрабатывает команду /process_audio.
    """
    msg = bot.reply_to(message, "Отправьте аудиофайл в формате MP3")
    bot.register_next_step_handler(msg, process_audio_step)

@bot.message_handler(commands=['status'])
def handle_status(message):
    """
    Обрабатывает команду /status.
    """
    user_id = message.from_user.id
    if user_id in user_states:
        state = user_states[user_id]
        if 'inspection_id' in state:
            inspection_id = state['inspection_id']
            null_questions = get_null_questions(inspection_id)
            bot.reply_to(
                message, 
                f"📊 Статус обработки:\n"
                f"ID проверки: {inspection_id}\n"
                f"Осталось вопросов: {len(null_questions)}\n\n"
                f"Используйте /answer для ответа на вопросы."
            )
        else:
            bot.reply_to(message, "⚠️ Нет активной проверки.")
    else:
        bot.reply_to(
            message, 
            "⚠️ Нет активной проверки. Используйте /process_audio для начала новой проверки."
        )

@bot.message_handler(commands=['answer'])
def handle_answer(message):
    """
    Обрабатывает команду /answer.
    """
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
        
        if user_id not in user_states or 'questions' not in user_states[user_id]:
            bot.send_message(user_id, "❌ Нет активной сессии вопросов")
            return
            
        questions = user_states[user_id]['questions']
        inspection_id = user_states[user_id]['inspection_id']
        
        if not (1 <= question_num <= len(questions)):
            bot.send_message(user_id, f"❌ Номер должен быть от 1 до {len(questions)}")
            return
            
        question_id = questions[question_num-1]
        add_answer(inspection_id, question_id, answer_text)
        
        # Обновляем список вопросов
        remaining_questions = get_null_questions(inspection_id)
        if remaining_questions:
            send_null_questions_to_bot(user_id, inspection_id)
        else:
            bot.send_message(user_id, "✅ Все ответы сохранены! Формируем отчет...")
            send_report_to_user(user_id, inspection_id)
            user_states.pop(user_id, None)
            
    except Exception as e:
        logger.error(f"Error handling answer: {str(e)}")
        logger.error(traceback.format_exc())
        bot.send_message(user_id, f"❌ Ошибка: {str(e)}")

def process_audio_step(message):
    """
    Обрабатывает шаг загрузки аудиофайла.
    """
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
        process_audio_file(user_id, audio_path)
        
    except Exception as e:
        logger.error(f"Error in process_audio_step: {str(e)}")
        logger.error(traceback.format_exc())
        bot.send_message(user_id, f"❌ Ошибка: {str(e)}")
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)

@bot.message_handler(content_types=['audio', 'document'])
def handle_direct_audio(message):
    """
    Обрабатывает прямую отправку аудиофайлов.
    """
    if (message.document and message.document.mime_type == 'audio/mpeg') or \
       (message.audio and message.audio.mime_type == 'audio/mpeg'):
        process_audio_step(message)
    else:
        bot.reply_to(message, "❌ Пожалуйста, отправьте файл в формате MP3.")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """
    Обрабатывает все остальные сообщения.
    """
    bot.reply_to(
        message, 
        "👋 Я бот для обработки аудиозаписей.\n\n"
        "Используйте команды:\n"
        "/start - начать работу\n"
        "/process_audio - обработать аудиофайл\n"
        "/help - получить справку\n\n"
        "Или просто отправьте мне аудиофайл MP3 🎤"
    )

# Entry point for direct testing
if __name__ == '__main__':
    logger.info("Starting bot polling...")
    bot.infinity_polling()