import whisper
from pathlib import Path
import logging
import os
from settings_manager import settings_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def transcribe_audio_with_faster_whisper(input_path, model_size="large-v3"):
    """
    Транскрибирует аудио с помощью Faster Whisper для улучшенного качества.
    
    Args:
        input_path (str): Путь к аудиофайлу
        model_size (str): Размер модели Faster Whisper
        
    Returns:
        str: Текст транскрипции
    """
    try:
        from faster_whisper import WhisperModel
        
        logger.info(f"Loading Faster Whisper model: {model_size}")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
        logger.info(f"Starting Faster Whisper transcription: {input_path}")
        segments, info = model.transcribe(
            input_path, 
            language="ru",
            beam_size=5,
            best_of=5,
            temperature=0.0,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        # Собираем текст с улучшенной обработкой
        transcription_parts = []
        for segment in segments:
            text = segment.text.strip()
            if text and len(text) > 1:  # Игнорируем очень короткие сегменты
                transcription_parts.append(text)
        
        transcription = " ".join(transcription_parts)
        
        logger.info(f"Faster Whisper completed. Language: {info.language} (confidence: {info.language_probability:.2f})")
        return transcription
        
    except ImportError:
        logger.warning("Faster Whisper not available, using standard Whisper")
        return transcribe_audio_standard(input_path)
    except Exception as e:
        logger.error(f"Faster Whisper error: {str(e)}, falling back to standard")
        return transcribe_audio_standard(input_path)

def transcribe_audio_standard(input_path):
    """
    Стандартная транскрипция с улучшенными параметрами.
    """
    try:
        # Получаем модель из настроек
        model_name = settings_manager.get_setting('whisper_model', 'medium')
        
        logger.info(f"Loading standard Whisper model: {model_name}")
        model = whisper.load_model(model_name)
        
        try:
            logger.info(f"Starting standard transcription: {input_path}")
            result = model.transcribe(
                input_path, 
                language="ru",
                temperature=0.0,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                condition_on_previous_text=False
            )
        finally:
            del model
            import gc
            gc.collect()
        
        return str(result["text"]).strip()
        
    except Exception as e:
        logger.error(f"Standard transcription error: {str(e)}")
        raise

def transcribe_audio(
    input_path,
    model_name: str = "medium",
    save_to_file: bool = True,
    output_path: str = "transcripts"
) -> str:
    """
    Главная функция транскрипции с автоматическим выбором лучшей модели.
    
    Параметры:
    input_path (str): Путь к входному аудиофайлу
    model_name (str): Размер модели (для совместимости)
    save_to_file (bool): Сохранить результат в файл
    output_path (str): Путь для сохранения
    
    Возвращает:
    str: Транскрибированный текст
    """
    try:
        # Проверка файла
        if not Path(input_path).exists():
            raise FileNotFoundError(f"Файл {input_path} не найден")

        # Проверяем настройки для выбора метода транскрипции
        use_turboscribe = settings_manager.get_setting('use_turboscribe_enhancement', True)
        use_advanced = settings_manager.get_setting('use_advanced_transcription', True)
        selected_model = settings_manager.get_setting('whisper_model', 'medium')
        
        if use_turboscribe:
            # Используем облегченную версию TurboScribe для стабильности
            logger.info("Using TurboScribe Lite enhancement")
            from turboscribe_lite import enhance_transcription_lite
            text = enhance_transcription_lite(input_path)
        elif use_advanced:
            # Используем Faster Whisper
            faster_models = {
                'tiny': 'tiny',
                'base': 'base', 
                'small': 'small',
                'medium': 'medium',
                'large': 'large-v3'
            }
            
            faster_model = faster_models.get(selected_model, 'large-v3')
            logger.info(f"Using advanced transcription: {faster_model}")
            text = transcribe_audio_with_faster_whisper(input_path, faster_model)
        else:
            logger.info("Using standard Whisper transcription")
            text = transcribe_audio_standard(input_path)
        
        # Сохранение результата
        if save_to_file:
            filename = f"{Path(input_path).stem}_transcript.txt"
            output_file = Path(output_path) / filename
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(text)
            logger.info(f"Transcription saved to: {output_file}")
        
        return text
        
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        raise