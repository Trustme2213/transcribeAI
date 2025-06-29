"""
Облегченная версия TurboScribe-системы для работы в ограниченной среде.
Фокус на постобработке и умеренной предобработке аудио.
"""

import logging
import os
import numpy as np
import librosa
from pathlib import Path
from typing import Optional, Dict
import re
import unicodedata

logger = logging.getLogger(__name__)

class TurboScribeLite:
    """
    Облегченная версия TurboScribe с фокусом на постобработку.
    """
    
    def __init__(self):
        """Инициализация облегченной системы."""
        self.common_errors = {
            'што': 'что', 'када': 'когда', 'тада': 'тогда',
            'така': 'такая', 'етот': 'этот', 'ета': 'эта',
            'ето': 'это', 'шо': 'что', 'чо': 'что', 'чё': 'что',
            'тож': 'тоже', 'щас': 'сейчас', 'ваще': 'вообще',
            'канешна': 'конечно', 'кароче': 'короче', 'нада': 'надо'
        }
        
        self.context_rules = [
            (r'\bи\s+то\b', 'итак'),
            (r'\bв\s+общем\b', 'в общем'),
            (r'\bпо\s+этому\b', 'поэтому'),
            (r'\bтак\s+же\b', 'также'),
            (r'\bчто\s+бы\b', 'чтобы')
        ]
    
    def lite_audio_enhancement(self, audio_path: str) -> str:
        """
        Облегченная предобработка аудио - только самое необходимое.
        """
        try:
            logger.info(f"Lite audio enhancement: {audio_path}")
            
            # Загружаем аудио
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
            
            # Простая нормализация громкости
            y = y / np.max(np.abs(y)) * 0.95
            
            # Сохраняем улучшенное аудио
            output_path = audio_path.replace('.', '_lite_enhanced.')
            if not output_path.endswith('.wav'):
                output_path = output_path.rsplit('.', 1)[0] + '.wav'
            
            import soundfile as sf
            sf.write(output_path, y, sr)
            
            logger.info(f"Lite enhanced audio saved: {output_path}")
            return output_path
            
        except Exception as e:
            logger.warning(f"Lite audio enhancement failed: {str(e)}")
            return audio_path
    
    def transcribe_with_lite_enhancement(self, audio_path: str) -> str:
        """
        Транскрипция с облегченными улучшениями TurboScribe.
        """
        try:
            # Легкая предобработка
            enhanced_audio = self.lite_audio_enhancement(audio_path)
            
            # Используем стандартный Whisper с оптимальными параметрами
            import whisper
            logger.info("Loading tiny Whisper model for lite enhancement (memory optimized)")
            
            model = whisper.load_model("tiny")
            result = model.transcribe(enhanced_audio, language="ru", temperature=0.0, fp16=False)
            
            raw_text = result.get('text', '')
            
            # Применяем постобработку TurboScribe
            enhanced_text = self.post_process_transcription(raw_text)
            
            # Очищаем временный файл
            if enhanced_audio != audio_path and os.path.exists(enhanced_audio):
                os.remove(enhanced_audio)
            
            logger.info("Lite TurboScribe enhancement completed")
            return enhanced_text
            
        except Exception as e:
            logger.error(f"Lite TurboScribe enhancement failed: {str(e)}")
            # Fallback к базовой транскрипции
            try:
                import whisper
                model = whisper.load_model("tiny")
                result = model.transcribe(audio_path, language="ru")
                return self.post_process_transcription(result.get('text', ''))
            except:
                return "Ошибка транскрипции"
    
    def post_process_transcription(self, text: str) -> str:
        """
        Постобработка транскрипции - основная сила TurboScribe.
        """
        try:
            logger.info("Applying TurboScribe lite post-processing")
            
            # 1. Нормализация Unicode
            text = unicodedata.normalize('NFKC', text)
            
            # 2. Исправление частых ошибок
            for wrong, correct in self.common_errors.items():
                pattern = r'\b' + re.escape(wrong) + r'\b'
                text = re.sub(pattern, correct, text, flags=re.IGNORECASE)
            
            # 3. Контекстные правила
            for pattern, replacement in self.context_rules:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            
            # 4. Финальная очистка
            text = self._final_cleanup(text)
            
            logger.info("Post-processing completed")
            return text
            
        except Exception as e:
            logger.error(f"Post-processing failed: {str(e)}")
            return text
    
    def _final_cleanup(self, text: str) -> str:
        """Финальная очистка текста."""
        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text)
        
        # Исправляем пробелы перед знаками препинания
        text = re.sub(r'\s+([,.!?])', r'\1', text)
        
        # Исправляем пробелы после знаков препинания
        text = re.sub(r'([,.!?])([^\s])', r'\1 \2', text)
        
        # Убираем повторяющиеся знаки препинания
        text = re.sub(r'([,.!?])\1+', r'\1', text)
        
        # Первая буква заглавная
        if text:
            text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
        
        return text.strip()

# Главная функция для интеграции
def enhance_transcription_lite(audio_path: str) -> str:
    """
    Облегченная версия улучшения транскрипции в стиле TurboScribe.
    """
    enhancer = TurboScribeLite()
    return enhancer.transcribe_with_lite_enhancement(audio_path)