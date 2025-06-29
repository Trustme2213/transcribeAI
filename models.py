from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

db = SQLAlchemy()

class User(db.Model):
    """
    Модель пользователя Telegram.
    """
    __tablename__ = 'users'
    
    user_id = db.Column(db.BigInteger, primary_key=True)
    username = db.Column(db.String(255))
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_authorized = db.Column(db.Boolean, default=False)  # Поле для авторизации
    authorized_by = db.Column(db.BigInteger, db.ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True)
    auth_date = db.Column(db.DateTime, nullable=True)

    # Отношения
    inspections = db.relationship('Inspection', backref='user', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.user_id} ({self.username})>"

class Survey(db.Model):
    """
    Модель анкеты (опроса).
    """
    __tablename__ = 'surveys'
    
    survey_id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Отношения
    questions = db.relationship('Question', backref='survey', lazy=True, cascade="all, delete-orphan")
    inspections = db.relationship('Inspection', backref='survey', lazy=True)
    
    def __repr__(self):
        return f"<Survey {self.survey_id}: {self.client_name}>"

class Question(db.Model):
    """
    Модель вопроса анкеты.
    """
    __tablename__ = 'questions'
    
    question_id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('surveys.survey_id', ondelete='CASCADE'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Отношения
    answers = db.relationship('Answer', backref='question', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Question {self.question_id}: {self.question_text[:30]}...>"

class Inspection(db.Model):
    """
    Модель проверки (сессии заполнения анкеты).
    """
    __tablename__ = 'inspections'
    
    inspection_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    survey_id = db.Column(db.Integer, db.ForeignKey('surveys.survey_id', ondelete='CASCADE'), nullable=False)
    file_id = db.Column(db.String(255), nullable=True)  # ID файла в Telegram
    audio_path = db.Column(db.String(255), nullable=True)  # Путь к локальному файлу
    transcript_path = db.Column(db.String(255), nullable=True)  # Путь к файлу транскрипции
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Отношения
    answers = db.relationship('Answer', backref='inspection', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Inspection {self.inspection_id} by User {self.user_id}>"

class Answer(db.Model):
    """
    Модель ответа на вопрос.
    """
    __tablename__ = 'answers'
    
    answer_id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('inspections.inspection_id', ondelete='CASCADE'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.question_id', ondelete='CASCADE'), nullable=False)
    answer_text = db.Column(db.Text, nullable=False, default="null")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Answer {self.answer_id} for Question {self.question_id}>"

class AdminUser(db.Model):
    """
    Модель администратора.
    """
    __tablename__ = 'admin_users'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, unique=True)
    is_superadmin = db.Column(db.Boolean, default=False)  # Суперадмин может добавлять других админов
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Отношение к пользователю
    user = db.relationship('User', backref=db.backref('admin_data', uselist=False))
    
    def __repr__(self):
        return f"<Admin {self.user_id}>"

# Добавим таблицу для хранения временных запросов на авторизацию
class AuthRequest(db.Model):
    """
    Модель запроса на авторизацию.
    """
    __tablename__ = 'auth_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    admin_id = db.Column(db.BigInteger, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=True)
    code = db.Column(db.String(10), nullable=False, unique=True)  # Уникальный код авторизации
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    user = db.relationship('User', foreign_keys=[user_id])
    admin = db.relationship('User', foreign_keys=[admin_id])
    
    def __repr__(self):
        return f"<AuthRequest for {self.user_id}, status: {self.status}>"