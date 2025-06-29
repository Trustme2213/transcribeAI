import os

from flask import Flask
from models import db

def create_app():
    """
    Создание и настройка экземпляра Flask-приложения.
    """
    app = Flask(__name__)
    
    # Настройка секретного ключа для сессий
    app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_development")
    
    # Настройка подключения к PostgreSQL
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Инициализация базы данных
    db.init_app(app)
    
    return app

# Создаём приложение
app = create_app()

# Создаём контекст приложения при импорте
with app.app_context():
    db.create_all()