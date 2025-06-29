import sys
import os
import logging
import telebot
from telebot import types
import random
import string
import secrets
from datetime import datetime
import json

from main import db, User, Survey, Question, AdminUser, AuthRequest, Inspection, Answer, app
from audio_chunker import AudioChunker
from whisper_transcription import transcribe_audio
from ya_gpt import ya_request_1, ya_request_2, process_text_in_chunks, process_text_in_chunks_for_formatting
from utils import ensure_dirs_exist, save_transcription, parse_gpt_response, format_duration

# Ensure directories exist
AUDIO_DIR = 'temp_audio'
TRANSCRIPTS_DIR = 'transcripts'
ensure_dirs_exist([AUDIO_DIR, TRANSCRIPTS_DIR])

# Настройка кодировки
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
MAX_CHUNK_SIZE_MS = 300000  # 5 minutes in milliseconds
OVERLAP_MS = 3000  # 3 seconds overlap between chunks

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Инициализация аудио обработчика
audio_chunker = AudioChunker(
    chunk_size_ms=MAX_CHUNK_SIZE_MS,
    overlap_ms=OVERLAP_MS,
    temp_dir=AUDIO_DIR
)

# Хранение состояния пользователей
user_states = {}  # {user_id: {"questions": list_of_question_ids, "inspection_id": int, ...}}

# Хранение авторизационных кодов
auth_codes = {}   # {code: {"user_id": user_id, "expires_at": datetime}}

def initialize_test_data():
    """
    Инициализирует тестовые данные в базе данных.
    """
    with app.app_context():
        # Проверяем наличие тестовой анкеты
        survey = Survey.query.filter_by(survey_id=3).first()
        if not survey:
            survey = Survey(survey_id=3, client_name='Тестовый клиент')
            db.session.add(survey)
            db.session.commit()
            logger.info("Created default survey with ID 3")

        # Проверяем наличие вопросов
        if Question.query.filter_by(survey_id=3).count() == 0:
            questions = [
                "Продавец здоровается отчетливо, громко, приветливым тоном?",
                "Продавец выясняет имя клиента и обращается к нему по имени?",
                "Продавец выясняет город клиента до начала презентации?",
                "Продавец демонстрирует уверенность в диалоге?",
                "Продавец ведет диалог вежливо и предлагает помощь?",
                "Продавец использует чистую и грамотную речь, избегает слов-паразитов?",
                "Продавец объясняет терминологию и аббревиатуры, если это необходимо?",
                "Продавец грамотно строит фразы и предложения?",
                "Продавец показывает, что услышал возражение клиента?",
                "Продавец проясняет суть возражения клиента?",
                "Продавец делает минимум одну попытку отработать возражение?",
                "Продавец предлагает альтернативные решения, если это необходимо?",
                "Продавец уточняет, какие характеристики можно скорректировать под запросы клиента?",
                "Продавец предлагает варианты увеличения бюджета (например, trade-in, целевые программы)?",
                "Продавец подчеркивает не менее 6 ключевых УТП проекта?",
                "Продавец презентует решение от главного к второстепенному, структурировано?",
                "Продавец озвучивает выгоды и преимущества решения?",
                "Продавец подтверждает выгоды аргументами (свойствами продукта)?",
                "Продавец выясняет источник финансирования покупки?",
                "Продавец предлагает рассчитать платеж по ипотеке или рассрочке?"
            ]
            
            for question_text in questions:
                question = Question(survey_id=3, question_text=question_text)
                db.session.add(question)
            
            db.session.commit()
            logger.info(f"Added {len(questions)} test questions to the database")
        
        # Проверяем наличие супер-администратора
        if AdminUser.query.filter_by(is_superadmin=True).count() == 0:
            # Проверим наличие пользователя-владельца в базе (создадим, если его нет)
            admin_user_id = 123456789  # Установите здесь ID пользователя Telegram, который будет суперадмином
            admin_user = User.query.filter_by(user_id=admin_user_id).first()
            if not admin_user:
                admin_user = User(
                    user_id=admin_user_id,
                    username="admin",
                    is_authorized=True
                )
                db.session.add(admin_user)
                db.session.commit()
            
            # Создаем супер-администратора
            superadmin = AdminUser(
                user_id=admin_user_id,
                is_superadmin=True
            )
            db.session.add(superadmin)
            db.session.commit()
            logger.info(f"Created superadmin with user_id {admin_user_id}")

def is_user_authorized(user_id):
    """
    Проверяет, авторизован ли пользователь для использования бота.
    
    :param user_id: ID пользователя в Telegram
    :return: True, если пользователь авторизован
    """
    with app.app_context():
        user = User.query.filter_by(user_id=user_id).first()
        return user and user.is_authorized

def is_user_admin(user_id):
    """
    Проверяет, является ли пользователь администратором.
    
    :param user_id: ID пользователя в Telegram
    :return: True, если пользователь является администратором
    """
    with app.app_context():
        admin = AdminUser.query.filter_by(user_id=user_id).first()
        return admin is not None

def register_user(user_id, username=None, first_name=None, last_name=None):
    """
    Регистрирует пользователя в базе данных.
    
    :param user_id: ID пользователя в Telegram
    :param username: Имя пользователя
    :param first_name: Имя
    :param last_name: Фамилия
    :return: Объект пользователя
    """
    with app.app_context():
        # Проверяем, существует ли пользователь
        user = User.query.filter_by(user_id=user_id).first()
        
        if user:
            # Обновляем данные пользователя, если он уже существует
            if username:
                user.username = username
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name
        else:
            # Создаем нового пользователя
            user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            db.session.add(user)
        
        db.session.commit()
        logger.info(f"User registered: {user_id} ({username})")
        return user

def create_auth_request(user_id):
    """
    Создает запрос на авторизацию для пользователя.
    
    :param user_id: ID пользователя в Telegram
    :return: Код авторизации
    """
    with app.app_context():
        # Генерируем уникальный код
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Проверяем, есть ли уже активный запрос для этого пользователя
        existing_request = AuthRequest.query.filter_by(user_id=user_id, status='pending').first()
        if existing_request:
            existing_request.code = code
            db.session.commit()
            return code
        
        # Создаем новый запрос
        auth_request = AuthRequest(
            user_id=user_id,
            code=code,
            status='pending'
        )
        db.session.add(auth_request)
        db.session.commit()
        
        return code

def get_questions_by_survey_id(survey_id: int) -> dict:
    """
    Получает список вопросов по ID анкеты в виде словаря для YandexGPT.
    
    :param survey_id: ID анкеты
    :return: Словарь вопросов {question_id: question_text}
    """
    with app.app_context():
        questions = Question.query.filter_by(survey_id=survey_id).all()
        return {q.question_id: q.question_text for q in questions}

def get_all_questions_for_survey(survey_id: int) -> dict:
    """
    Получает все вопросы анкеты в виде словаря.
    
    :param survey_id: ID анкеты
    :return: Словарь {question_id: question_text}
    """
    with app.app_context():
        questions = Question.query.filter_by(survey_id=survey_id).all()
        return {q.question_id: q.question_text for q in questions}

def get_question_by_id(question_id: int) -> str:
    """
    Получает текст вопроса по его ID.
    
    :param question_id: ID вопроса
    :return: Текст вопроса или None, если вопрос не найден
    """
    with app.app_context():
        question = Question.query.filter_by(question_id=question_id).first()
        return question.question_text if question else "Вопрос не найден"

def add_answer(inspection_id: int, question_id: int, answer_text: str):
    """
    Добавляет или обновляет ответ на вопрос.
    
    :param inspection_id: ID проверки
    :param question_id: ID вопроса
    :param answer_text: Текст ответа
    """
    with app.app_context():
        answer = Answer.query.filter_by(
            inspection_id=inspection_id, 
            question_id=question_id
        ).first()
        
        if answer:
            answer.answer_text = answer_text
            answer.updated_at = datetime.utcnow()
        else:
            answer = Answer(
                inspection_id=inspection_id,
                question_id=question_id,
                answer_text=answer_text
            )
            db.session.add(answer)
        
        db.session.commit()

def get_null_questions(inspection_id: int) -> list:
    """
    Получает список вопросов с пустыми ответами.
    
    :param inspection_id: ID проверки
    :return: Список ID вопросов с пустыми ответами
    """
    with app.app_context():
        null_answers = Answer.query.filter_by(
            inspection_id=inspection_id, 
            answer_text="null"
        ).all()
        
        return [answer.question_id for answer in null_answers]

def send_null_questions_to_bot(user_id, inspection_id):
    """
    Отправляет пользователю список вопросов, требующих ответов.
    
    :param user_id: ID пользователя
    :param inspection_id: ID проверки
    """
    questions_ids = get_null_questions(inspection_id)
    
    if not questions_ids:
        bot.send_message(user_id, "🎉 Все вопросы заполнены! Формируем отчет...")
        send_report_to_user(user_id, inspection_id)
        return
    
    user_states[user_id] = {
        "questions": questions_ids,
        "inspection_id": inspection_id
    }
    
    bot.send_message(user_id, "❓ Вопросы, требующие ответов:")
    for i, q_id in enumerate(questions_ids, 1):
        question_text = get_question_by_id(q_id)
        if question_text:
            bot.send_message(user_id, f"{i}. {question_text}\n/answer {i} [ваш ответ]")

def send_report_to_user(user_id: int, inspection_id: int):
    """
    Генерирует и отправляет отчет пользователю.
    
    :param user_id: ID пользователя
    :param inspection_id: ID проверки
    """
    try:
        with app.app_context():
            # Получаем все ответы на вопросы для данной проверки
            answers = db.session.query(Question.question_text, Answer.answer_text)\
                .join(Answer, Question.question_id == Answer.question_id)\
                .filter(Answer.inspection_id == inspection_id)\
                .all()
            
            if not answers:
                bot.send_message(user_id, "❌ Не удалось сформировать отчет: нет ответов")
                return
            
            # Создаем PDF отчет
            from fpdf import FPDF
            
            class PDF(FPDF):
                def __init__(self):
                    super().__init__()
                    self.add_page()
                    self.set_font('Arial', size=12)
                    
                def add_header(self, text):
                    self.set_font('Arial', 'B', 16)
                    self.cell(200, 10, txt=text, ln=True, align='C')
                    self.ln(15)
                    self.set_font('Arial', size=12)
                    
                def add_question_answer(self, idx, question, answer):
                    self.multi_cell(0, 8, f"Вопрос #{idx}:", 0, 'L')
                    self.multi_cell(0, 8, question, 0, 'L')
                    self.multi_cell(0, 8, f"Ответ:", 0, 'L')
                    self.multi_cell(0, 8, answer, 0, 'L')
                    self.ln(10)
            
            # Создаем PDF
            pdf = PDF()
            pdf.add_header("ОТЧЕТ О ПРОВЕРКЕ")
            
            # Содержание
            for idx, (question, answer) in enumerate(answers, 1):
                # Проверка и преобразование текста
                if not isinstance(question, str):
                    question = str(question)
                if not isinstance(answer, str):
                    answer = str(answer)
                    
                if answer == "null":
                    answer = "Нет ответа"
                    
                pdf.add_question_answer(idx, question, answer)
            
            # Сохраняем PDF в файл
            filename = f"report_{inspection_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
            filepath = os.path.join(AUDIO_DIR, filename)
            pdf.output(filepath)
            
            # Отмечаем проверку как завершенную
            inspection = Inspection.query.get(inspection_id)
            if inspection:
                inspection.completed_at = datetime.utcnow()
                db.session.commit()
            
            # Отправляем файл пользователю
            with open(filepath, 'rb') as report_file:
                bot.send_document(
                    chat_id=user_id,
                    document=report_file,
                    caption=f"📄 Отчет по проверке #{inspection_id}",
                    timeout=60
                )
            
            # Удаляем временный файл
            os.remove(filepath)
        
    except Exception as e:
        logger.error(f"Error sending report: {str(e)}")
        bot.send_message(user_id, f"❌ Ошибка при создании отчета: {str(e)}")

def create_inspection(user_id: int, survey_id: int) -> int:
    """
    Создает новую проверку.
    
    :param user_id: ID пользователя
    :param survey_id: ID анкеты
    :return: ID созданной проверки
    """
    with app.app_context():
        inspection = Inspection(
            user_id=user_id,
            survey_id=survey_id
        )
        db.session.add(inspection)
        db.session.commit()
        
        logger.info(f"Created inspection ID {inspection.inspection_id} for user {user_id} on survey {survey_id}")
        return inspection.inspection_id

def initialize_answers(inspection_id: int, question_ids: list):
    """
    Инициализирует ответы на вопросы значениями null.
    
    :param inspection_id: ID проверки
    :param question_ids: Список ID вопросов
    """
    with app.app_context():
        for question_id in question_ids:
            answer = Answer(
                inspection_id=inspection_id,
                question_id=question_id,
                answer_text="null"
            )
            db.session.add(answer)
        
        db.session.commit()
        logger.info(f"Initialized {len(question_ids)} answers for inspection {inspection_id}")

def process_audio_file_sync(user_id, audio_path, original_filename=None, survey_id=3):
    """
    Обрабатывает аудиофайл: разбивает на части, транскрибирует и форматирует.
    
    :param user_id: ID пользователя
    :param audio_path: Путь к аудиофайлу
    :param survey_id: ID анкеты (по умолчанию 3) - не используется в этой версии
    :param original_filename: Оригинальное имя файла для именования транскрипции
    """
    try:
        # Создаем новую проверку (оставляем для совместимости)
        inspection_id = create_inspection(user_id, survey_id)
        
        with app.app_context():
            # Сохраняем путь к аудио в базе данных
            inspection = Inspection.query.get(inspection_id)
            inspection.audio_path = audio_path
            db.session.commit()
        
        # Получаем вопросы для анкеты (оставляем для совместимости)
        questions = get_all_questions_for_survey(survey_id)
        question_ids = list(questions.keys())
        
        # Инициализируем ответы как null (оставляем для совместимости)
        initialize_answers(inspection_id, question_ids)
        
        # Отправляем сообщение о начале обработки
        status_msg = bot.send_message(
            user_id, 
            "🔄 Начинаем обработку аудиофайла. Это может занять некоторое время..."
        )
        
        # Разбиваем аудио на части и получаем улучшенную версию
        chunk_paths, enhanced_audio_path = audio_chunker.split_audio(audio_path)
        
        # Обновляем статус
        bot.edit_message_text(
            f"🔊 Аудиофайл разделен на {len(chunk_paths)} частей. Начинаем транскрибирование...",
            chat_id=user_id,
            message_id=status_msg.message_id
        )
        
        # Транскрибируем каждую часть
        all_transcriptions = []
        start_time = datetime.now().timestamp()
        
        for i, chunk_path in enumerate(chunk_paths, 1):
            chunk_start_time = datetime.now().timestamp()
            
            # Обновляем статус
            bot.edit_message_text(
                f"🔄 Транскрибирую часть {i}/{len(chunk_paths)}...",
                chat_id=user_id,
                message_id=status_msg.message_id
            )
            
            # Получаем модель Whisper из настроек
            from settings_manager import settings_manager
            whisper_model = settings_manager.get_setting('whisper_model', 'medium')
            
            # Транскрибируем аудио
            transcription = transcribe_audio(chunk_path, model_name=whisper_model, save_to_file=False)
            all_transcriptions.append(transcription)
            
            chunk_time = datetime.now().timestamp() - chunk_start_time
            
            # Обновляем статус с информацией о времени
            progress = i / len(chunk_paths) * 100
            elapsed = datetime.now().timestamp() - start_time
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
            user_id,
            original_filename
        )
        
        with app.app_context():
            # Сохраняем путь к транскрипции в базе данных
            inspection = Inspection.query.get(inspection_id)
            inspection.transcript_path = transcript_path
            db.session.commit()
        
        # Отправляем статус о завершении
        bot.edit_message_text(
            f"✅ Транскрипция завершена! Отправляю результат...",
            chat_id=user_id,
            message_id=status_msg.message_id
        )
        
        # Используем исходную транскрипцию без YandexGPT обработки
        formatted_text = full_transcription
        
        # Создаем имена файлов на основе оригинального имени
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if original_filename:
            base_name = os.path.splitext(original_filename)[0]
            base_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            file_base = f"{user_id}_{base_name}_{timestamp}"
        else:
            file_base = f"{user_id}_{timestamp}"
        
        # Создаем текстовый файл с транскрипцией в TXT формате
        txt_file_path = os.path.join(TRANSCRIPTS_DIR, f'formatted/txt/{file_base}_transcript.txt')
        os.makedirs(os.path.dirname(txt_file_path), exist_ok=True)
        
        with open(txt_file_path, 'w', encoding='utf-8') as txt_file:
            txt_file.write(formatted_text)
        
        # Создаем DOC файл (просто переименовываем копию TXT файла, так как содержимое одинаковое)
        doc_file_path = os.path.join(TRANSCRIPTS_DIR, f'formatted/doc/{file_base}_transcript.doc')
        os.makedirs(os.path.dirname(doc_file_path), exist_ok=True)
        
        with open(txt_file_path, 'r', encoding='utf-8') as src_file:
            with open(doc_file_path, 'w', encoding='utf-8') as doc_file:
                doc_file.write(src_file.read())
        
        # Возвращаем пути к файлам для использования в очереди
        result = {
            "files": {
                "txt": txt_file_path,
                "doc": doc_file_path
            },
            "enhanced_audio_path": enhanced_audio_path,
            "transcript_path": transcript_path
        }
        
        # Очищаем временные файлы
        audio_chunker.cleanup_chunks(chunk_paths)
        
        return result
        
    except Exception as e:
        logger.error(f"Audio processing error: {str(e)}")
        
        # Очищаем временные файлы в случае ошибки
        if 'chunk_paths' in locals():
            audio_chunker.cleanup_chunks(chunk_paths)
        
        raise e

# Обработчики команд бота

@bot.message_handler(commands=['start'])
def handle_start(message):
    """
    Обрабатывает команду /start.
    """
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # Регистрируем пользователя в базе данных
    user = register_user(user_id, username, first_name, last_name)
    
    if is_user_authorized(user_id):
        bot.reply_to(
            message, 
            f"👋 Добро пожаловать, {first_name if first_name else username}! Ваш аккаунт авторизован.\n\n"
            "Вы можете использовать следующие команды:\n"
            "/process_audio - загрузить и обработать аудиофайл\n"
            "/help - получить справку\n"
            "/status - проверить статус обработки\n\n"
            "Также вы можете просто отправить мне аудиофайл напрямую 🎤"
        )
    else:
        # Создаем запрос на авторизацию, если пользователь не авторизован
        auth_code = create_auth_request(user_id)
        
        bot.reply_to(
            message, 
            f"👋 Добро пожаловать, {first_name if first_name else username}!\n\n"
            "Для использования бота вам необходимо получить авторизацию. Ваш код авторизации:\n\n"
            f"<code>{auth_code}</code>\n\n"
            "Передайте этот код администратору для получения доступа к боту.\n\n"
            "После авторизации вы получите уведомление и сможете пользоваться ботом.",
            parse_mode="HTML"
        )
        
        # Уведомляем администраторов о новом запросе авторизации
        with app.app_context():
            admins = AdminUser.query.all()
            for admin in admins:
                try:
                    bot.send_message(
                        admin.user_id,
                        f"📢 Новый запрос на авторизацию!\n\n"
                        f"Пользователь: {username} ({first_name} {last_name})\n"
                        f"ID: {user_id}\n"
                        f"Код: {auth_code}\n\n"
                        f"Используйте /authorize {auth_code} для подтверждения."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin.user_id}: {str(e)}")

@bot.message_handler(commands=['authorize'])
def handle_authorize(message):
    """
    Обрабатывает команду /authorize для администраторов.
    """
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if not is_user_admin(user_id):
        bot.reply_to(message, "⛔ У вас нет прав для авторизации пользователей.")
        return
    
    # Проверяем, правильный ли формат команды
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(
            message, 
            "❌ Неверный формат команды. Используйте: /authorize [код]"
        )
        return
    
    auth_code = args[1].strip().upper()
    
    # Проверяем наличие кода в базе
    with app.app_context():
        auth_request = AuthRequest.query.filter_by(code=auth_code, status='pending').first()
        if not auth_request:
            bot.reply_to(
                message, 
                "❌ Неверный код авторизации или запрос уже обработан."
            )
            return
        
        # Авторизуем пользователя
        user = User.query.filter_by(user_id=auth_request.user_id).first()
        if user:
            user.is_authorized = True
            user.authorized_by = user_id
            user.auth_date = datetime.utcnow()
            
            auth_request.status = 'approved'
            auth_request.admin_id = user_id
            
            db.session.commit()
            
            bot.reply_to(
                message, 
                f"✅ Пользователь с ID {user.user_id} успешно авторизован!"
            )
            
            # Уведомляем пользователя об авторизации
            try:
                bot.send_message(
                    user.user_id,
                    "🎉 Ваш аккаунт был авторизован администратором! Теперь вы можете использовать бота.\n\n"
                    "Доступные команды:\n"
                    "/process_audio - загрузить и обработать аудиофайл\n"
                    "/help - получить справку\n"
                    "/status - проверить статус обработки"
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user.user_id} about authorization: {str(e)}")
        else:
            bot.reply_to(
                message, 
                "❌ Пользователь не найден. Возможно, он был удален."
            )

@bot.message_handler(commands=['reject'])
def handle_reject(message):
    """
    Обрабатывает команду /reject для администраторов.
    """
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if not is_user_admin(user_id):
        bot.reply_to(message, "⛔ У вас нет прав для отклонения запросов.")
        return
    
    # Проверяем, правильный ли формат команды
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(
            message, 
            "❌ Неверный формат команды. Используйте: /reject [код]"
        )
        return
    
    auth_code = args[1].strip().upper()
    
    # Проверяем наличие кода в базе
    with app.app_context():
        auth_request = AuthRequest.query.filter_by(code=auth_code, status='pending').first()
        if not auth_request:
            bot.reply_to(
                message, 
                "❌ Неверный код авторизации или запрос уже обработан."
            )
            return
        
        # Отклоняем запрос
        auth_request.status = 'rejected'
        auth_request.admin_id = user_id
        db.session.commit()
        
        bot.reply_to(
            message, 
            f"❌ Запрос на авторизацию с кодом {auth_code} отклонен."
        )
        
        # Уведомляем пользователя об отклонении запроса
        try:
            bot.send_message(
                auth_request.user_id,
                "⛔ Ваш запрос на авторизацию был отклонен администратором."
            )
        except Exception as e:
            logger.error(f"Failed to notify user {auth_request.user_id} about rejection: {str(e)}")

@bot.message_handler(commands=['help'])
def handle_help(message):
    """
    Обрабатывает команду /help.
    """
    user_id = message.from_user.id
    
    # Проверяем авторизацию пользователя
    if not is_user_authorized(user_id):
        bot.reply_to(
            message, 
            "⛔ Вы не авторизованы для использования этой команды. Используйте /start для получения кода авторизации."
        )
        return
    
    help_text = """🤖 *Бот для транскрипции аудио*

📋 *Доступные команды:*

🎵 /process\\_audio - Загрузить аудиофайл для транскрипции
📊 /queue\\_status - Проверить статус очереди обработки
📈 /my\\_tasks - Посмотреть ваши задачи в очереди
📊 /status - Проверить статус бота и базы данных  
❓ /help - Показать это сообщение

📝 *Как использовать:*
1\\. Используйте команду /process\\_audio
2\\. Отправьте аудиофайл в формате MP3
3\\. Файл добавится в очередь обработки
4\\. Получите уведомление когда обработка завершится

⚙️ *Возможности:*
• Пакетная обработка файлов
• Очередь для множественных загрузок
• Поддержка длинных аудиофайлов
• Автоматическое разбиение на части
• Высокое качество транскрипции
• Форматы вывода: TXT и DOC

🔒 Для использования требуется авторизация администратора\\."""
    
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['queue_status'])
def handle_queue_status(message):
    """
    Показывает статус очереди обработки.
    """
    user_id = message.from_user.id
    
    if not is_user_authorized(user_id):
        bot.reply_to(
            message, 
            "⛔ Вы не авторизованы для использования этой команды. Используйте /start для получения кода авторизации."
        )
        return
    
    from persistent_queue import persistent_audio_queue
    
    queue_info = persistent_audio_queue.get_queue_info()
    
    status_text = f"""📊 *Статус очереди обработки:*

⏳ В очереди: {queue_info['pending_tasks']} задач
🔄 Обрабатывается: {queue_info['processing_tasks']} задач
📋 Всего задач: {queue_info['total_tasks']}

🎵 Используйте /my\\_tasks для просмотра ваших задач"""
    
    bot.reply_to(message, status_text, parse_mode='Markdown')

@bot.message_handler(commands=['my_tasks'])
def handle_my_tasks(message):
    """
    Показывает задачи пользователя в очереди.
    """
    user_id = message.from_user.id
    
    if not is_user_authorized(user_id):
        bot.reply_to(
            message, 
            "⛔ Вы не авторизованы для использования этой команды. Используйте /start для получения кода авторизации."
        )
        return
    
    from persistent_queue import persistent_audio_queue
    
    user_tasks = persistent_audio_queue.get_user_tasks(user_id)
    
    if not user_tasks:
        bot.reply_to(message, "📭 У вас нет задач в очереди.")
        return
    
    tasks_text = "📋 *Ваши задачи:*\n\n"
    
    for task in user_tasks[-10:]:  # Показываем последние 10 задач
        status_emoji = {
            "pending": "⏳",
            "processing": "🔄", 
            "completed": "✅",
            "failed": "❌"
        }.get(task['status'], "❓")
        
        elapsed_time = datetime.now() - task['created_at']
        
        tasks_text += f"{status_emoji} `{task['task_id'][:12]}...`\n"
        tasks_text += f"📁 {task['original_filename']}\n"
        tasks_text += f"🕐 {elapsed_time.total_seconds():.0f}с назад\n\n"
    
    if len(user_tasks) > 10:
        tasks_text += f"... и еще {len(user_tasks) - 10} задач"
    
    bot.reply_to(message, tasks_text, parse_mode='Markdown')

@bot.message_handler(commands=['process_audio'])
def handle_process_audio(message):
    """
    Обрабатывает команду /process_audio.
    """
    user_id = message.from_user.id
    
    # Проверяем авторизацию пользователя
    if not is_user_authorized(user_id):
        bot.reply_to(
            message, 
            "⛔ Вы не авторизованы для использования этой команды. Используйте /start для получения кода авторизации."
        )
        return
    
    help_msg = """🎵 *Загрузка аудиофайлов*

📤 Отправьте один или несколько аудиофайлов в формате MP3
⚡ Файлы будут добавлены в очередь обработки
📊 Используйте /queue\\_status для проверки прогресса
📝 Результаты будут отправлены автоматически при готовности

*Поддерживаемые форматы:* MP3, WAV, M4A, FLAC
*Максимальный размер файла:* 50 МБ"""
    
    bot.reply_to(message, help_msg, parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def handle_status(message):
    """
    Обрабатывает команду /status.
    """
    user_id = message.from_user.id
    
    # Проверяем авторизацию пользователя
    if not is_user_authorized(user_id):
        bot.reply_to(
            message, 
            "⛔ Вы не авторизованы для использования этой команды. Используйте /start для получения кода авторизации."
        )
        return
    
    # Проверяем наличие проверок в базе
    with app.app_context():
        inspections = Inspection.query.filter_by(
            user_id=user_id
        ).order_by(Inspection.created_at.desc()).limit(5).all()
        
        if inspections:
            bot.reply_to(
                message, 
                f"📊 Последние аудиозаписи, обработанные вами:\n\n" +
                "\n".join([f"ID: {insp.inspection_id}, Дата: {insp.created_at.strftime('%Y-%m-%d %H:%M')}" 
                          for insp in inspections])
            )
        else:
            bot.reply_to(
                message, 
                "ℹ️ Вы еще не обрабатывали аудиофайлы. Используйте /process_audio для начала обработки."
            )

# Команда continue больше не нужна, но оставляем заглушку для обратной совместимости
@bot.message_handler(commands=['continue'])
def handle_continue(message):
    """
    Заглушка для /continue (больше не используется).
    """
    user_id = message.from_user.id
    
    # Проверяем авторизацию пользователя
    if not is_user_authorized(user_id):
        bot.reply_to(
            message, 
            "⛔ Вы не авторизованы для использования этой команды. Используйте /start для получения кода авторизации."
        )
        return
    
    bot.reply_to(
        message, 
        "ℹ️ Эта команда больше не используется. Отправьте новый аудиофайл через /process_audio."
    )

# Команда answer больше не нужна, но оставляем заглушку для обратной совместимости
@bot.message_handler(commands=['answer'])
def handle_answer(message):
    """
    Заглушка для /answer (больше не используется).
    """
    user_id = message.from_user.id
    
    # Проверяем авторизацию пользователя
    if not is_user_authorized(user_id):
        bot.reply_to(
            message, 
            "⛔ Вы не авторизованы для использования этой команды. Используйте /start для получения кода авторизации."
        )
        return
    
    bot.reply_to(
        message, 
        "ℹ️ Эта команда больше не используется в текущей версии бота."
    )

def process_audio_step(message):
    """
    Обрабатывает шаг загрузки аудиофайла.
    """
    try:
        user_id = message.from_user.id
        
        # Проверяем авторизацию пользователя
        if not is_user_authorized(user_id):
            bot.reply_to(
                message, 
                "⛔ Вы не авторизованы для использования этой функции. Используйте /start для получения кода авторизации."
            )
            return
        
        # Скачивание и сохранение аудио
        original_filename = None
        if message.document and message.document.mime_type == 'audio/mpeg':
            file_id = message.document.file_id
            original_filename = message.document.file_name
        elif message.audio and message.audio.mime_type == 'audio/mpeg':
            file_id = message.audio.file_id
            original_filename = getattr(message.audio, 'file_name', None) or f"audio_{user_id}.mp3"
        else:
            bot.send_message(user_id, "❌ Требуется MP3 файл!")
            return
            
        file_info = bot.get_file(file_id)
        audio_path = os.path.join(AUDIO_DIR, f"{user_id}_{datetime.now().timestamp()}.mp3")
        
        with open(audio_path, 'wb') as f:
            f.write(bot.download_file(file_info.file_path))
        
        # Добавляем задачу в очередь
        from persistent_queue import persistent_audio_queue
        task_id = persistent_audio_queue.add_task(user_id, audio_path, original_filename)
        
        bot.send_message(
            user_id,
            f"📥 Файл {original_filename} добавлен в очередь обработки!\n"
            f"🆔 ID задачи: {task_id}\n"
            f"📊 Используйте /queue_status для проверки статуса очереди"
        )
        
    except Exception as e:
        logger.error(f"Error in process_audio_step: {str(e)}")
        bot.send_message(user_id, f"❌ Ошибка: {str(e)}")
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)

@bot.message_handler(content_types=['audio', 'document'])
def handle_direct_audio(message):
    """
    Обрабатывает прямую отправку аудиофайлов.
    """
    user_id = message.from_user.id
    
    # Проверяем авторизацию пользователя
    if not is_user_authorized(user_id):
        bot.reply_to(
            message, 
            "⛔ Вы не авторизованы для использования этой функции. Используйте /start для получения кода авторизации."
        )
        return
    
    try:
        # Определяем тип файла и получаем информацию
        file_id = None
        original_filename = None
        
        if message.document:
            # Проверяем mime-type для аудиофайлов
            if message.document.mime_type and message.document.mime_type.startswith('audio/'):
                file_id = message.document.file_id
                original_filename = message.document.file_name or f"audio_{user_id}_{int(datetime.now().timestamp())}.mp3"
            else:
                bot.reply_to(message, "❌ Поддерживаются только аудиофайлы. Отправьте файл в формате MP3, WAV, M4A или FLAC.")
                return
        elif message.audio:
            file_id = message.audio.file_id
            original_filename = getattr(message.audio, 'file_name', None) or f"audio_{user_id}_{int(datetime.now().timestamp())}.mp3"
        else:
            bot.reply_to(message, "❌ Отправьте аудиофайл для обработки.")
            return
        
        # Получаем информацию о файле
        file_info = bot.get_file(file_id)
        
        # Проверяем размер файла (ограничение Telegram API - 20MB, но лучше проверить заранее)
        if file_info.file_size and file_info.file_size > 50 * 1024 * 1024:  # 50MB
            bot.reply_to(message, "❌ Файл слишком большой. Максимальный размер: 50 МБ.")
            return
        
        # Создаем уникальный путь для файла
        timestamp = int(datetime.now().timestamp())
        file_extension = os.path.splitext(original_filename)[1] or '.mp3'
        audio_path = os.path.join(AUDIO_DIR, f"{user_id}_{timestamp}{file_extension}")
        
        # Скачиваем файл
        if file_info.file_path:
            with open(audio_path, 'wb') as f:
                f.write(bot.download_file(file_info.file_path))
        else:
            bot.reply_to(message, "❌ Не удалось получить файл.")
            return
        
        # Добавляем задачу в очередь
        from persistent_queue import persistent_audio_queue
        task_id = persistent_audio_queue.add_task(user_id, audio_path, original_filename)
        
        # Получаем размер файла для отображения
        file_size_mb = (file_info.file_size / (1024*1024)) if file_info.file_size else 0
        
        # Отправляем подтверждение
        confirmation_msg = f"""✅ *Файл добавлен в очередь\\!*

📁 *Файл:* `{original_filename}`
🆔 *ID задачи:* `{task_id[:12]}...`
📊 *Размер:* {file_size_mb:.1f} МБ

⏳ Файл обрабатывается в фоновом режиме
📱 Вы получите уведомление когда обработка завершится
📊 Используйте /queue\\_status для проверки очереди"""
        
        bot.reply_to(message, confirmation_msg, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in handle_direct_audio: {str(e)}")
        bot.reply_to(message, f"❌ Ошибка при обработке файла: {str(e)}")
        
        # Очищаем файл при ошибке
        if 'audio_path' in locals() and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except:
                pass
    else:
        bot.reply_to(message, "❌ Пожалуйста, отправьте файл в формате MP3.")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """
    Обрабатывает все остальные сообщения.
    """
    user_id = message.from_user.id
    
    # Если пользователь не авторизован, предложить авторизацию
    if not is_user_authorized(user_id):
        # Проверяем, есть ли у пользователя активные запросы на авторизацию
        with app.app_context():
            auth_request = AuthRequest.query.filter_by(
                user_id=user_id, 
                status='pending'
            ).first()
            
            if auth_request:
                bot.reply_to(
                    message, 
                    f"⏳ Ваш запрос на авторизацию находится на рассмотрении.\n\n"
                    f"Код авторизации: <code>{auth_request.code}</code>\n\n"
                    f"Передайте этот код администратору для получения доступа к боту.",
                    parse_mode="HTML"
                )
            else:
                # Создаем новый запрос авторизации
                auth_code = create_auth_request(user_id)
                
                bot.reply_to(
                    message, 
                    f"⛔ Вы не авторизованы для использования бота.\n\n"
                    f"Ваш код авторизации: <code>{auth_code}</code>\n\n"
                    f"Передайте этот код администратору для получения доступа к боту.\n\n"
                    f"После авторизации вы получите уведомление и сможете пользоваться ботом.",
                    parse_mode="HTML"
                )
        
        return
    
    # Если пользователь авторизован, показать справку
    bot.reply_to(
        message, 
        "👋 Я бот для обработки аудиозаписей.\n\n"
        "Используйте команды:\n"
        "/process_audio - обработать аудиофайл\n"
        "/help - получить справку\n"
        "/status - проверить статус обработки\n\n"
        "Или просто отправьте мне аудиофайл MP3 🎤"
    )