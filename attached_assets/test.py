import json
import sqlite3

  
def create_tables():
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
            FOREIGN KEY (survey_id) REFERENCES surveys (survey_id) ON DELETE CASCADE,
            UNIQUE(question_id, survey_id)  
        )
    ''')

    # Таблица "inspections"
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inspections (
            inspection_id INTEGER PRIMARY KEY AUTOINCREMENT,  
            user_id INTEGER NOT NULL,
            survey_id INTEGER NOT NULL,                       
            file_id INTEGER,                               
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
            FOREIGN KEY (survey_id) REFERENCES surveys (survey_id) ON DELETE CASCADE
        )
    ''')

    # Таблица "answers"
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS answers (
            answer_id INTEGER PRIMARY KEY AUTOINCREMENT,  
            user_id INTEGER NOT NULL,                     
            question_id INTEGER NOT NULL,                 
            answer_text TEXT NOT NULL,                   
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions (question_id) ON DELETE CASCADE,
            UNIQUE(user_id, question_id)  
        )
    ''')

    # Создаём индексы для ускорения поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_user_id ON users (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_surveys_survey_id ON surveys (survey_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_questions_question_id ON questions (question_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_inspections_inspection_id ON inspections (inspection_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_answers_answer_id ON answers (answer_id)')

    # Сохраняем изменения и закрываем соединение
    conn.commit()
    conn.close()

# Вызываем функцию для создания таблиц
create_tables()

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
"Продавец предлагает рассчитать платеж по ипотеке или рассрочке?",
"Продавец помогает клиенту сравнить разные варианты платежей?",
"Продавец предлагает специальные программы (например, trade-in, целевые программы)?",
"Продавец доброжелательно прощается с клиентом?",
"Продавец резюмирует диалог и проговоривает итоговое решение (встреча, перезвон)?",
"Продавец предлагает отправить информацию в WhatsApp или SMS?",
"Продавец подтверждает номер телефона клиента?",
"Продавец просит оценку качества своей работы?",
"Продавец предлагает целевое действие (встреча, бронь, избранное, ОЗ)?",
"Продавец мотивирует клиента к оплате бронирования (если применимо)?",
"Продавец предлагает наиболее приоритетное действие (например, встреча в офисе продаж)?",
"Продавец повышает ценность визита через выгоды?",
"Продавец получает явное согласие клиента на встречу?",
"Продавец предлагает такси при приглашении в офис продаж?",
"Продавец сообщает об ограничениях (например, 1 поездка на такси)?",
"Продавец учитывает, в каких проектах доступен заказ такси?",
"Продавец мотивирует клиента на встречу в ближайшие 1-2 дня?",
"Продавец озвучивает минимум 1 аргумент в пользу срочности?"]

# Создаём словарь с вопросами
questions_dict = {i + 1: question for i, question in enumerate(questions)}

# Выводим словарь для проверки
print(questions_dict)

# Функция для добавления вопроса в базу данных
def add_question(survey_id: int, question_text: str):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO questions (survey_id, question_text)
        VALUES (?, ?)
    ''', (survey_id, question_text))

    conn.commit()
    conn.close()

# Пример использования
survey_id = 3  # ID анкеты, к которой относятся вопросы

# Добавляем каждый вопрос из словаря в базу данных
for question_id, question_text in questions_dict.items():
    add_question(survey_id, question_text)
    print(f"Добавлен вопрос {question_id}: {question_text}")

print("Все вопросы добавлены в базу данных.")


# def add_inspection(user_id: int, survey_id: int = None) -> int:
#     conn = sqlite3.connect('bot.db')
#     cursor = conn.cursor()

#     cursor.execute('''
#         INSERT INTO inspections (user_id, survey_id)
#         VALUES (?, ?)
#     ''', (user_id, survey_id))

#     inspection_id = cursor.lastrowid  # Получаем ID созданной проверки
#     conn.commit()
#     conn.close()
#     return inspection_id

# add_inspection(554526841, 1)