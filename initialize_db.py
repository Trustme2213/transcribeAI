import sqlite3
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_tables():
    """
    Создает все необходимые таблицы в базе данных.
    """
    logger.info("Creating database tables...")
    
    # Удаляем старую базу если она существует и повреждена
    if os.path.exists('bot.db'):
        try:
            conn = sqlite3.connect('bot.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]
            required_tables = ['users', 'surveys', 'questions', 'inspections', 'answers']
            
            missing_tables = [table for table in required_tables if table not in existing_tables]
            if missing_tables:
                logger.warning(f"Missing tables found: {missing_tables}. Recreating database.")
                conn.close()
                os.remove('bot.db')
            else:
                # Проверяем структуру таблицы answers
                cursor.execute("PRAGMA table_info(answers)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'user_id' in columns and 'inspection_id' not in columns:
                    logger.warning("Invalid schema for answers table. Recreating database.")
                    conn.close()
                    os.remove('bot.db')
                else:
                    conn.close()
                    return  # База данных уже в порядке
        except Exception as e:
            logger.error(f"Error checking database: {str(e)}")
            if os.path.exists('bot.db'):
                os.remove('bot.db')
    
    # Подключаемся к базе данных (или создаём её, если она не существует)
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()

    # Таблица "users"
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,  
            username TEXT,                
            first_name TEXT,              
            last_name TEXT,               
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  
            UNIQUE(user_id)    
        )           
    ''')

    # Таблица "surveys"
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS surveys (
            survey_id INTEGER PRIMARY KEY AUTOINCREMENT,  
            client_name TEXT NOT NULL,                   
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  
        )
    ''')

    # Таблица "questions"
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            question_id INTEGER PRIMARY KEY AUTOINCREMENT,  
            survey_id INTEGER NOT NULL,                   
            question_text TEXT NOT NULL,                  
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  
            FOREIGN KEY (survey_id) REFERENCES surveys (survey_id) ON DELETE CASCADE
        )
    ''')

    # Таблица "inspections"
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inspections (
            inspection_id INTEGER PRIMARY KEY AUTOINCREMENT,  
            user_id INTEGER NOT NULL,
            survey_id INTEGER NOT NULL,                       
            file_id TEXT,                               
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
            FOREIGN KEY (survey_id) REFERENCES surveys (survey_id) ON DELETE CASCADE
        )
    ''')

    # Таблица "answers" - с поддержкой inspection_id вместо user_id
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS answers (
            answer_id INTEGER PRIMARY KEY AUTOINCREMENT,  
            inspection_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,                 
            answer_text TEXT NOT NULL,                   
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  
            FOREIGN KEY (inspection_id) REFERENCES inspections (inspection_id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions (question_id) ON DELETE CASCADE,
            UNIQUE(inspection_id, question_id)
        )
    ''')

    # Создаём индексы для ускорения поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_user_id ON users (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_surveys_survey_id ON surveys (survey_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_questions_question_id ON questions (question_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_questions_survey_id ON questions (survey_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_inspections_user_id ON inspections (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_inspections_inspection_id ON inspections (inspection_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_answers_inspection_id ON answers (inspection_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_answers_answer_id ON answers (answer_id)')

    # Создаем тестовую анкету
    cursor.execute('''
        INSERT INTO surveys (survey_id, client_name) VALUES (3, 'Тестовый клиент')
    ''')
    logger.info("Created default survey with ID 3")

    # Сохраняем изменения и закрываем соединение
    conn.commit()
    conn.close()
    
    logger.info("Database tables created successfully!")

def add_test_questions():
    """
    Добавляет тестовые вопросы в анкету.
    """
    logger.info("Adding test questions to the database...")
    
    # Список тестовых вопросов
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

    # Подключаемся к базе данных
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    # Проверяем, есть ли уже вопросы
    cursor.execute('SELECT COUNT(*) FROM questions WHERE survey_id = 3')
    if cursor.fetchone()[0] > 0:
        logger.info("Questions already exist, skipping...")
        conn.close()
        return
    
    # Добавляем вопросы
    survey_id = 3  # ID тестовой анкеты
    for question_text in questions:
        cursor.execute('''
            INSERT INTO questions (survey_id, question_text)
            VALUES (?, ?)
        ''', (survey_id, question_text))
        
    conn.commit()
    conn.close()
    
    logger.info(f"Added {len(questions)} test questions to the database")

if __name__ == "__main__":
    create_tables()
    add_test_questions()
    print("Database initialized successfully!")