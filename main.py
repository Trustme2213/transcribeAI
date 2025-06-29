import os
import logging
import threading
import time
import json
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_required, current_user, login_user, logout_user, UserMixin
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import random
import string
import secrets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create and configure the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_development")

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions
db = SQLAlchemy(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
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
    
    def get_id(self):
        return str(self.user_id)

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
        return f"<AdminUser {self.user_id}>"

class AudioTaskDB(db.Model):
    """
    Модель задачи обработки аудио в базе данных.
    """
    __tablename__ = 'audio_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    audio_path = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    result_txt_path = db.Column(db.String(255), nullable=True)
    result_doc_path = db.Column(db.String(255), nullable=True)
    enhanced_audio_path = db.Column(db.String(255), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref='audio_tasks')
    
    def __repr__(self):
        return f'<AudioTaskDB {self.task_id} for user {self.user_id}>'

class SystemSettings(db.Model):
    """
    Модель настроек системы.
    """
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<SystemSettings {self.setting_key}: {self.setting_value}>"

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

# Create all tables
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Route definitions
@app.route('/')
def dashboard():
    """Главная страница - панель транскрипций."""
    try:
        transcriptions = Transcription.query.order_by(Transcription.created_at.desc()).all()
        return render_template('dashboard.html', transcriptions=transcriptions)
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        return render_template('dashboard.html', transcriptions=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        auth_code = request.form.get('auth_code')
        
        if not user_id or not auth_code:
            flash('Пожалуйста, заполните все поля', 'danger')
            return render_template('login.html')
        
        try:
            user_id = int(user_id)
        except ValueError:
            flash('Telegram ID должен быть числом', 'danger')
            return render_template('login.html')
        
        # Проверяем существование пользователя и его права
        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            flash('Пользователь не найден', 'danger')
            return render_template('login.html')
        
        # Проверяем наличие прав администратора
        admin = AdminUser.query.filter_by(user_id=user_id).first()
        if not admin:
            flash('У вас нет прав администратора', 'danger')
            return render_template('login.html')
        
        # Проверяем код авторизации 
        # Для администраторов с user_id 554526841 разрешаем вход с любым кодом
        if user_id == 554526841:
            # Автоматически авторизуем главного администратора
            pass
        elif auth_code != "admin123":  
            flash('Неверный код авторизации', 'danger')
            return render_template('login.html')
        
        # Все проверки пройдены, логиним пользователя
        login_user(user)
        flash('Вы успешно вошли в систему', 'success')
        return redirect(url_for('admin_panel'))
    
    return render_template('login.html')

@app.route('/test-admin')
def test_admin():
    """Test admin interface without authentication"""
    users = User.query.all()
    auth_requests = AuthRequest.query.filter_by(status='pending').all()
    
    return render_template('admin.html', 
                         users=users, 
                         auth_requests=auth_requests,
                         current_user_admin=True)

@app.route('/status')
def status():
    try:
        # Avoid bot import to prevent timeouts
        bot_username = 'AudioTranscribeBot'
        
        users_count = User.query.count()
        authorized_users = User.query.filter_by(is_authorized=True).count()
        admins_count = AdminUser.query.count()
            
        return jsonify({
            'status': 'online',
            'bot_username': bot_username,
            'server_time': time.strftime("%Y-%m-%d %H:%M:%S"),
            'users_count': users_count,
            'authorized_users': authorized_users,
            'admins_count': admins_count
        })
    except Exception as e:
        logger.error(f"Error in status endpoint: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'server_time': time.strftime("%Y-%m-%d %H:%M:%S")
        }), 500

@app.route('/admin')
def admin_panel():
    # Check if user is logged in
    if not current_user.is_authenticated:
        # If not logged in, try auto-login for main admin
        user = User.query.filter_by(user_id=554526841).first()
        if user:
            admin = AdminUser.query.filter_by(user_id=554526841).first()
            if admin:
                login_user(user)
                flash(f'Автоматический вход для администратора {user.username}', 'success')
            else:
                flash('Access denied. You are not an administrator.', 'danger')
                return redirect(url_for('login'))
        else:
            flash('Access denied. Please log in.', 'danger')
            return redirect(url_for('login'))
    
    # Check if current user is admin
    admin = AdminUser.query.filter_by(user_id=current_user.user_id).first()
    if not admin:
        flash('Access denied. You are not an administrator.', 'danger')
        return redirect(url_for('index'))
    
    users = User.query.all()
    auth_requests = AuthRequest.query.filter_by(status='pending').all()
    
    return render_template('admin.html', 
                          users=users, 
                          auth_requests=auth_requests, 
                          is_superadmin=admin.is_superadmin)

@app.route('/admin/authorize/<int:user_id>', methods=['POST'])
@login_required
def authorize_user(user_id):
    # Check if current user is admin
    admin = AdminUser.query.filter_by(user_id=current_user.user_id).first()
    if not admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    user.is_authorized = True
    user.authorized_by = current_user.user_id
    user.auth_date = datetime.utcnow()
    db.session.commit()
    
    flash(f'User {user.username} (ID: {user.user_id}) has been authorized.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/deauthorize/<int:user_id>', methods=['POST'])
@login_required
def deauthorize_user(user_id):
    # Check if current user is admin
    admin = AdminUser.query.filter_by(user_id=current_user.user_id).first()
    if not admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    user.is_authorized = False
    db.session.commit()
    
    flash(f'User {user.username} (ID: {user.user_id}) has been deauthorized.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/make_admin/<int:user_id>', methods=['POST'])
@login_required
def make_admin(user_id):
    # Check if current user is superadmin
    admin = AdminUser.query.filter_by(user_id=current_user.user_id).first()
    if not admin or not admin.is_superadmin:
        flash('Access denied. Only superadmins can create new admins.', 'danger')
        return redirect(url_for('admin_panel'))
    
    user = User.query.get_or_404(user_id)
    
    # Check if already admin
    existing_admin = AdminUser.query.filter_by(user_id=user_id).first()
    if existing_admin:
        flash(f'User {user.username} is already an admin.', 'info')
        return redirect(url_for('admin_panel'))
    
    # Make user an admin
    new_admin = AdminUser(user_id=user_id)
    db.session.add(new_admin)
    
    # Ensure user is also authorized
    user.is_authorized = True
    user.authorized_by = current_user.user_id
    user.auth_date = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'User {user.username} has been made an admin.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/revoke_admin/<int:user_id>', methods=['POST'])
@login_required
def revoke_admin(user_id):
    # Check if current user is superadmin
    admin = AdminUser.query.filter_by(user_id=current_user.user_id).first()
    if not admin or not admin.is_superadmin:
        flash('Access denied. Only superadmins can revoke admin status.', 'danger')
        return redirect(url_for('admin_panel'))
    
    # Cannot revoke own admin status
    if int(user_id) == current_user.user_id:
        flash('You cannot revoke your own admin status.', 'danger')
        return redirect(url_for('admin_panel'))
    
    admin_to_revoke = AdminUser.query.filter_by(user_id=user_id).first()
    if admin_to_revoke:
        db.session.delete(admin_to_revoke)
        db.session.commit()
        flash('Admin status has been revoked.', 'success')
    else:
        flash('This user is not an admin.', 'warning')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/approve_request/<int:request_id>', methods=['POST'])
@login_required
def approve_request(request_id):
    # Check if current user is admin
    admin = AdminUser.query.filter_by(user_id=current_user.user_id).first()
    if not admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    auth_request = AuthRequest.query.get_or_404(request_id)
    auth_request.status = 'approved'
    auth_request.admin_id = current_user.user_id
    
    # Authorize the user
    user = User.query.get(auth_request.user_id)
    if user:
        user.is_authorized = True
        user.authorized_by = current_user.user_id
        user.auth_date = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'Request approved and user {user.username if user else auth_request.user_id} has been authorized.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/reject_request/<int:request_id>', methods=['POST'])
@login_required
def reject_request(request_id):
    # Check if current user is admin
    admin = AdminUser.query.filter_by(user_id=current_user.user_id).first()
    if not admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    auth_request = AuthRequest.query.get_or_404(request_id)
    auth_request.status = 'rejected'
    auth_request.admin_id = current_user.user_id
    db.session.commit()
    
    flash('Request has been rejected.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/settings')
def admin_settings():
    # For testing purposes, allow direct access to settings
    # In production, this should have proper authentication
    
    # Get current settings
    settings = {
        'audio_preprocessing_enabled': get_setting('audio_preprocessing_enabled', True),
        'chunk_size_ms': get_setting('chunk_size_ms', 180000),
        'overlap_ms': get_setting('overlap_ms', 2000),
        'noise_reduction_enabled': get_setting('noise_reduction_enabled', True),
        'volume_normalization_enabled': get_setting('volume_normalization_enabled', True),
        'compression_enabled': get_setting('compression_enabled', True),
        'speech_optimization_enabled': get_setting('speech_optimization_enabled', True),
        'whisper_model': get_setting('whisper_model', 'medium'),
        'noise_reduction_level': get_setting('noise_reduction_level', 0.65),
        'noise_floor_db': get_setting('noise_floor_db', -22),
        'n_fft': get_setting('n_fft', 2048),
        'attack_time': get_setting('attack_time', 0.005),
        'decay_time': get_setting('decay_time', 0.07),
        'intelligent_analysis_enabled': get_setting('intelligent_analysis_enabled', True),
        'use_advanced_transcription': get_setting('use_advanced_transcription', True),
        'use_turboscribe_enhancement': get_setting('use_turboscribe_enhancement', True)
    }
    
    return render_template('admin_settings.html', settings=settings)

# Веб-интерфейс для транскрипций

@app.route('/upload', methods=['POST'])
def upload_audio():
    """Загрузка аудиофайла для транскрипции."""
    try:
        if 'audio_file' not in request.files:
            return jsonify({'success': False, 'error': 'Файл не выбран'})
        
        file = request.files['audio_file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Файл не выбран'})
        
        # Проверяем тип файла
        allowed_extensions = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.webm'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'error': 'Неподдерживаемый формат файла'})
        
        # Безопасное имя файла
        filename = secure_filename(file.filename)
        
        # Создаем уникальное имя файла
        timestamp = str(int(time.time() * 1000))
        unique_filename = f"{timestamp}_{filename}"
        
        # Путь для сохранения
        upload_folder = 'temp_audio'
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, unique_filename)
        
        # Сохраняем файл
        file.save(file_path)
        
        # Получаем информацию о файле
        file_size = os.path.getsize(file_path)
        
        # Пытаемся получить длительность аудио
        duration = None
        try:
            import librosa
            y, sr = librosa.load(file_path, sr=None)
            duration = len(y) / sr
        except Exception as e:
            logger.warning(f"Could not get audio duration: {str(e)}")
        
        # Создаем запись в базе данных
        transcription = Transcription(
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            duration=duration,
            status='pending'
        )
        
        db.session.add(transcription)
        db.session.commit()
        
        # Запускаем обработку в фоне
        thread = threading.Thread(target=process_transcription_async, args=(transcription.id,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True, 
            'transcription_id': transcription.id,
            'message': 'Файл успешно загружен и поставлен в очередь на обработку'
        })
        
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        return jsonify({'success': False, 'error': 'Ошибка при загрузке файла'})

@app.route('/transcription/<int:transcription_id>')
def transcription_detail(transcription_id):
    """Детальная страница транскрипции."""
    try:
        transcription = Transcription.query.get(transcription_id)
        if not transcription:
            flash('Транскрипция не найдена', 'error')
            return redirect(url_for('dashboard'))
        
        return render_template('transcription_detail.html', transcription=transcription)
    except Exception as e:
        logger.error(f"Error loading transcription detail: {str(e)}")
        flash('Ошибка при загрузке транскрипции', 'error')
        return redirect(url_for('dashboard'))

@app.route('/transcription/<int:transcription_id>/download/<format>')
def download_transcription(transcription_id, format):
    """Скачивание транскрипции в различных форматах."""
    try:
        transcription = Transcription.query.get(transcription_id)
        if not transcription or not transcription.text:
            return jsonify({'error': 'Транскрипция не найдена или еще не готова'})
        
        if format == 'txt':
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(transcription.text)
                temp_path = f.name
            
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f'transcription_{transcription_id}.txt',
                mimetype='text/plain'
            )
        
        elif format == 'pdf':
            from fpdf import FPDF
            import tempfile
            
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font('Arial', '', 12)
            
            # Заголовок
            pdf.set_font('Arial', 'B', 16)
            title = f'Transcription: {transcription.filename or "Audio File"}'
            pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True)
            pdf.ln(5)
            
            # Информация
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 8, f'Created: {transcription.created_at.strftime("%d.%m.%Y %H:%M")}', ln=True)
            if transcription.duration:
                pdf.cell(0, 8, f'Duration: {transcription.duration:.1f} sec', ln=True)
            pdf.ln(5)
            
            # Текст (упрощенная версия для кодировки)
            pdf.set_font('Arial', '', 12)
            text_lines = transcription.text.split('\n')
            for line in text_lines:
                # Кодируем в latin-1 с заменой неподдерживаемых символов
                encoded_line = line.encode('latin-1', 'replace').decode('latin-1')
                pdf.cell(0, 8, encoded_line, ln=True)
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                temp_path = f.name
            
            pdf.output(temp_path)
            
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f'transcription_{transcription_id}.pdf',
                mimetype='application/pdf'
            )
        
        else:
            return jsonify({'error': 'Неподдерживаемый формат'})
            
    except Exception as e:
        logger.error(f"Error downloading transcription: {str(e)}")
        return jsonify({'error': 'Ошибка при скачивании файла'})

@app.route('/api/transcriptions')
def api_transcriptions():
    """API для получения списка транскрипций."""
    try:
        transcriptions = Transcription.query.order_by(Transcription.created_at.desc()).all()
        return jsonify([t.to_dict() for t in transcriptions])
    except Exception as e:
        logger.error(f"Error getting transcriptions: {str(e)}")
        return jsonify({'error': 'Ошибка при получении транскрипций'})

def process_transcription_async(transcription_id):
    """Асинхронная обработка транскрипции."""
    try:
        with app.app_context():
            transcription = Transcription.query.get(transcription_id)
            if not transcription:
                return
            
            # Обновляем статус
            transcription.status = 'processing'
            transcription.started_at = datetime.utcnow()
            db.session.commit()
            
            start_time = time.time()
            
            try:
                # Определяем метод транскрипции
                use_turboscribe = get_setting('use_turboscribe_enhancement', True)
                use_advanced = get_setting('use_advanced_transcription', True)
                
                if use_turboscribe:
                    from turboscribe_lite import enhance_transcription_lite
                    text = enhance_transcription_lite(transcription.file_path)
                    transcription.model_used = 'TurboScribe Lite'
                    transcription.enhancement_used = 'Постобработка + улучшения'
                elif use_advanced:
                    from whisper_transcription import transcribe_audio_with_faster_whisper
                    model_name = get_setting('whisper_model', 'medium')
                    text = transcribe_audio_with_faster_whisper(transcription.file_path, model_name)
                    transcription.model_used = f'Faster Whisper ({model_name})'
                    transcription.enhancement_used = 'Faster Whisper'
                else:
                    from whisper_transcription import transcribe_audio_standard
                    text = transcribe_audio_standard(transcription.file_path)
                    model_name = get_setting('whisper_model', 'medium')
                    transcription.model_used = f'Standard Whisper ({model_name})'
                    transcription.enhancement_used = 'Стандартная обработка'
                
                # Сохраняем результат
                transcription.text = text
                transcription.status = 'completed'
                transcription.completed_at = datetime.utcnow()
                transcription.processing_time = time.time() - start_time
                
                logger.info(f"Transcription {transcription_id} completed successfully")
                
            except Exception as e:
                logger.error(f"Error processing transcription {transcription_id}: {str(e)}")
                transcription.status = 'error'
                transcription.error_message = str(e)
                transcription.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            # Очистка файла через час
            def cleanup_file():
                time.sleep(3600)
                try:
                    if os.path.exists(transcription.file_path):
                        os.remove(transcription.file_path)
                        logger.info(f"Cleaned up file: {transcription.file_path}")
                except Exception as e:
                    logger.warning(f"Could not cleanup file {transcription.file_path}: {str(e)}")
            
            cleanup_thread = threading.Thread(target=cleanup_file)
            cleanup_thread.daemon = True
            cleanup_thread.start()
            
    except Exception as e:
        logger.error(f"Critical error in transcription processing: {str(e)}")

@app.route('/admin/settings', methods=['POST'])
def update_settings():
    # For testing purposes, allow direct access to settings updates
    # In production, this should have proper authentication
    
    try:
        # Update audio preprocessing settings
        set_setting('audio_preprocessing_enabled', 'audio_preprocessing_enabled' in request.form)
        set_setting('chunk_size_ms', int(request.form.get('chunk_size_ms', 180000)))
        set_setting('overlap_ms', int(request.form.get('overlap_ms', 2000)))
        set_setting('noise_reduction_enabled', 'noise_reduction_enabled' in request.form)
        set_setting('volume_normalization_enabled', 'volume_normalization_enabled' in request.form)
        set_setting('compression_enabled', 'compression_enabled' in request.form)
        set_setting('speech_optimization_enabled', 'speech_optimization_enabled' in request.form)
        set_setting('whisper_model', request.form.get('whisper_model', 'medium'))
        set_setting('noise_reduction_level', float(request.form.get('noise_reduction_level', 0.65)))
        set_setting('noise_floor_db', int(request.form.get('noise_floor_db', -22)))
        set_setting('n_fft', int(request.form.get('n_fft', 2048)))
        set_setting('attack_time', float(request.form.get('attack_time', 0.005)))
        set_setting('decay_time', float(request.form.get('decay_time', 0.07)))
        set_setting('intelligent_analysis_enabled', 'intelligent_analysis_enabled' in request.form)
        set_setting('use_advanced_transcription', 'use_advanced_transcription' in request.form)
        set_setting('use_turboscribe_enhancement', 'use_turboscribe_enhancement' in request.form)
        
        # Invalidate settings cache to apply changes immediately
        from settings_manager import settings_manager
        settings_manager.invalidate_cache()
        
        flash('Settings updated successfully!', 'success')
    except ValueError as e:
        flash(f'Invalid value provided: {str(e)}', 'danger')
    except Exception as e:
        flash(f'Error updating settings: {str(e)}', 'danger')
    
    return redirect(url_for('admin_settings'))

# Generate auth code helper
def generate_auth_code(length=6):
    """Generate a random authentication code."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# System settings helper functions
def get_setting(key, default_value=None):
    """Get a system setting value."""
    setting = SystemSettings.query.filter_by(setting_key=key).first()
    if setting:
        # Try to parse JSON for complex values
        try:
            return json.loads(setting.setting_value)
        except (json.JSONDecodeError, TypeError):
            return setting.setting_value
    return default_value

def set_setting(key, value, description=None):
    """Set a system setting value."""
    setting = SystemSettings.query.filter_by(setting_key=key).first()
    
    # Convert value to JSON string if it's not a string
    if isinstance(value, (dict, list, bool, int, float)):
        value_str = json.dumps(value)
    else:
        value_str = str(value)
    
    if setting:
        setting.setting_value = value_str
        if description:
            setting.description = description
        setting.updated_at = datetime.utcnow()
    else:
        setting = SystemSettings(
            setting_key=key,
            setting_value=value_str,
            description=description or f"System setting: {key}"
        )
        db.session.add(setting)
    
    db.session.commit()
    return setting

def initialize_default_settings():
    """Initialize default system settings."""
    defaults = {
        'audio_preprocessing_enabled': {
            'value': True,
            'description': 'Enable audio preprocessing for quality improvement'
        },
        'chunk_size_ms': {
            'value': 180000,
            'description': 'Audio chunk size in milliseconds (default: 3 minutes)'
        },
        'overlap_ms': {
            'value': 2000,
            'description': 'Audio chunk overlap in milliseconds (default: 2 seconds)'
        },
        'noise_reduction_enabled': {
            'value': True,
            'description': 'Enable noise reduction in audio preprocessing'
        },
        'volume_normalization_enabled': {
            'value': True,
            'description': 'Enable volume normalization in audio preprocessing'
        },
        'compression_enabled': {
            'value': True,
            'description': 'Enable dynamic range compression in audio preprocessing'
        },
        'speech_optimization_enabled': {
            'value': True,
            'description': 'Enable speech optimization (silence removal) in audio preprocessing'
        },
        'whisper_model': {
            'value': 'medium',
            'description': 'Whisper model for transcription (tiny, base, small, medium, large)'
        },
        'noise_reduction_level': {
            'value': 0.65,
            'description': 'Noise reduction strength (0.0 - 1.0, higher = more aggressive)'
        },
        'noise_floor_db': {
            'value': -22,
            'description': 'Noise floor threshold in dB (typical range: -30 to -15)'
        },
        'n_fft': {
            'value': 2048,
            'description': 'FFT window size for spectral analysis (512, 1024, 2048, 4096)'
        },
        'attack_time': {
            'value': 0.005,
            'description': 'Attack time for noise gate in seconds (0.001 - 0.1)'
        },
        'decay_time': {
            'value': 0.07,
            'description': 'Decay time for noise gate in seconds (0.01 - 0.5)'
        },
        'intelligent_analysis_enabled': {
            'value': True,
            'description': 'Enable intelligent audio analysis for automatic parameter tuning'
        },
        'use_advanced_transcription': {
            'value': True,
            'description': 'Use advanced transcription models (Faster Whisper) for better quality'
        },
        'use_turboscribe_enhancement': {
            'value': True,
            'description': 'Use TurboScribe-style enhancement techniques for maximum quality'
        }
    }
    
    for key, config in defaults.items():
        if not SystemSettings.query.filter_by(setting_key=key).first():
            set_setting(key, config['value'], config['description'])

# Initialize test data
def initialize_test_data():
    """
    Инициализирует тестовые данные в базе данных.
    """
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
        admin_user_id = 554526841  # Ваш ID пользователя Telegram как суперадмин
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
    
    # Initialize default system settings
    initialize_default_settings()
    logger.info("Initialized default system settings")

# Initialize test data after all tables are created
with app.app_context():
    initialize_test_data()

# Bot polling thread
def bot_polling():
    # Import here to avoid circular imports
    from bot import bot
    from persistent_queue import persistent_audio_queue
    
    # Initialize and start the persistent audio processing queue
    persistent_audio_queue.start()
    logger.info("Persistent audio processing queue started")
    
    logger.info("Starting Telegram bot polling...")
    bot.remove_webhook()
    time.sleep(1)  # To ensure webhook is fully removed
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

# Start server when run directly
if __name__ == '__main__':
    # Start bot polling in a separate thread
    bot_thread = threading.Thread(target=bot_polling)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)
else:
    # When running with Gunicorn, start the bot polling thread
    if not os.environ.get('BOT_WEBHOOK_MODE'):
        bot_thread = threading.Thread(target=bot_polling)
        bot_thread.daemon = True
        bot_thread.start()
        logger.info("Bot polling thread started in Gunicorn mode")