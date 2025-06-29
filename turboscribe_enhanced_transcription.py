"""
Продвинутая система транскрипции, основанная на техниках TurboScribe.
Включает многоэтапную обработку, улучшенное шумоподавление и постобработку.
"""

import logging
import os
import tempfile
import numpy as np
import librosa
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import re
import unicodedata
from settings_manager import settings_manager

logger = logging.getLogger(__name__)

class TurboScribeEnhancer:
    """
    Класс для улучшения качества транскрипции по методике TurboScribe.
    """
    
    def __init__(self):
        """Инициализация улучшенной системы транскрипции."""
        self.common_errors = {
            # Частые ошибки в русской речи
            'што': 'что',
            'када': 'когда', 
            'тада': 'тогда',
            'така': 'такая',
            'етот': 'этот',
            'ета': 'эта',
            'ето': 'это',
            'шо': 'что',
            'чо': 'что',
            'чё': 'что',
            'тож': 'тоже',
            'щас': 'сейчас',
            'сча': 'сейчас',
            'ваще': 'вообще',
            'канешна': 'конечно',
            'кароче': 'короче',
            'типа': 'типа',
            'нада': 'надо',
            'хочеца': 'хочется',
            'даваца': 'давайте',
        }
        
        # Контекстные правила для улучшения точности
        self.context_rules = [
            (r'\bи\s+то\b', 'итак'),
            (r'\bв\s+общем\b', 'в общем'),
            (r'\bна\s+счет\b', 'насчет'),
            (r'\bпо\s+этому\b', 'поэтому'),
            (r'\bтак\s+же\b', 'также'),
            (r'\bчто\s+бы\b', 'чтобы'),
            (r'\bкак\s+будто\b', 'как будто'),
            (r'\bпо\s+тому\s+что\b', 'потому что'),
        ]
    
    def enhance_audio_preprocessing(self, audio_path: str) -> str:
        """
        Продвинутая предобработка аудио по методике TurboScribe.
        
        Args:
            audio_path: Путь к исходному аудио
            
        Returns:
            Путь к улучшенному аудио файлу
        """
        try:
            logger.info(f"Starting TurboScribe-style audio enhancement: {audio_path}")
            
            # Загружаем аудио с высоким качеством
            y, sr = librosa.load(audio_path, sr=None, mono=False)
            
            # Конвертируем в моно если нужно
            if y.ndim > 1:
                y = librosa.to_mono(y)
            
            # Нормализуем частоту дискретизации до 16kHz (оптимально для Whisper)
            if sr != 16000:
                y = librosa.resample(y, orig_sr=sr, target_sr=16000)
                sr = 16000
            
            # Применяем адаптивное шумоподавление
            y = self._adaptive_noise_reduction(y, sr)
            
            # Динамическая нормализация громкости
            y = self._dynamic_range_compression(y)
            
            # Улучшение четкости речи
            y = self._enhance_speech_clarity(y, sr)
            
            # Сохраняем улучшенное аудио
            output_path = audio_path.replace('.', '_enhanced.')
            if not output_path.endswith('.wav'):
                output_path = output_path.rsplit('.', 1)[0] + '.wav'
            
            import soundfile as sf
            sf.write(output_path, y, sr)
            
            logger.info(f"Enhanced audio saved: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error in audio enhancement: {str(e)}")
            return audio_path
    
    def _adaptive_noise_reduction(self, y: np.ndarray, sr: int) -> np.ndarray:
        """Адаптивное шумоподавление на основе спектрального анализа."""
        try:
            # Вычисляем спектрограмму
            S = librosa.stft(y, n_fft=2048, hop_length=512)
            magnitude = np.abs(S)
            phase = np.angle(S)
            
            # Оцениваем шум по тихим участкам
            power = magnitude ** 2
            noise_profile = np.percentile(power, 10, axis=1, keepdims=True)
            
            # Адаптивное подавление шума
            alpha = 2.0  # Агрессивность подавления
            enhanced_magnitude = magnitude * (power / (power + alpha * noise_profile))
            
            # Восстанавливаем сигнал
            enhanced_S = enhanced_magnitude * np.exp(1j * phase)
            y_enhanced = librosa.istft(enhanced_S, hop_length=512)
            
            return y_enhanced
            
        except Exception as e:
            logger.warning(f"Noise reduction failed: {str(e)}")
            return y
    
    def _dynamic_range_compression(self, y: np.ndarray) -> np.ndarray:
        """Динамическое сжатие для выравнивания громкости."""
        try:
            # Вычисляем RMS энергию
            frame_length = 2048
            hop_length = 512
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            
            # Интерполируем RMS на длину сигнала
            times = librosa.frames_to_samples(np.arange(len(rms)), hop_length=hop_length)
            rms_interp = np.interp(np.arange(len(y)), times, rms)
            
            # Нормализуем с сохранением динамики
            target_rms = np.percentile(rms_interp, 70)  # Целевой уровень
            gain = target_rms / (rms_interp + 1e-8)
            gain = np.clip(gain, 0.1, 3.0)  # Ограничиваем усиление
            
            return y * gain
            
        except Exception as e:
            logger.warning(f"Dynamic range compression failed: {str(e)}")
            return y
    
    def _enhance_speech_clarity(self, y: np.ndarray, sr: int) -> np.ndarray:
        """Улучшение четкости речи через частотную фильтрацию."""
        try:
            # Применяем полосовой фильтр для речевых частот (80Hz - 8kHz)
            from scipy.signal import butter, filtfilt
            
            nyquist = sr / 2
            low = 80 / nyquist
            high = min(8000 / nyquist, 0.95)
            
            b, a = butter(4, [low, high], btype='band')
            y_filtered = filtfilt(b, a, y)
            
            # Подчеркиваем важные речевые частоты (1-4 kHz)
            mid_low = 1000 / nyquist
            mid_high = min(4000 / nyquist, 0.95)
            
            b_mid, a_mid = butter(2, [mid_low, mid_high], btype='band')
            speech_band = filtfilt(b_mid, a_mid, y)
            
            # Смешиваем с небольшим усилением речевых частот
            enhanced = y_filtered + 0.3 * speech_band
            
            return enhanced
            
        except Exception as e:
            logger.warning(f"Speech clarity enhancement failed: {str(e)}")
            return y
    
    def enhance_transcription_with_segments(self, audio_path: str) -> Tuple[str, List[Dict]]:
        """
        Улучшенная транскрипция с сегментацией по методике TurboScribe.
        
        Returns:
            Tuple of (enhanced_text, segments_info)
        """
        try:
            from faster_whisper import WhisperModel
            
            # Предварительная обработка аудио
            enhanced_audio_path = self.enhance_audio_preprocessing(audio_path)
            
            logger.info("Loading optimized Whisper model for TurboScribe enhancement")
            # Используем более легкую модель для экономии памяти
            model = WhisperModel("base", device="cpu", compute_type="int8")
            
            # Оптимизированные параметры по методике TurboScribe (совместимые)
            segments, info = model.transcribe(
                enhanced_audio_path,
                language="ru",
                beam_size=5,  # Умеренный beam search для экономии памяти
                temperature=0.0,
                compression_ratio_threshold=2.2,
                no_speech_threshold=0.5,
                condition_on_previous_text=True,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=300,
                    speech_pad_ms=300
                ),
                word_timestamps=True
            )
            
            # Собираем сегменты с детальной информацией
            segments_info = []
            transcription_parts = []
            
            for segment in segments:
                segment_info = {
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text.strip(),
                    'confidence': getattr(segment, 'avg_logprob', 0),
                    'words': getattr(segment, 'words', [])
                }
                
                if segment_info['text'] and len(segment_info['text']) > 1:
                    segments_info.append(segment_info)
                    transcription_parts.append(segment_info['text'])
            
            # Первичная сборка текста
            raw_transcription = " ".join(transcription_parts)
            
            # Применяем постобработку TurboScribe-style
            enhanced_text = self.post_process_transcription(raw_transcription, segments_info)
            
            # Очищаем временный файл
            if enhanced_audio_path != audio_path and os.path.exists(enhanced_audio_path):
                os.remove(enhanced_audio_path)
            
            logger.info(f"TurboScribe enhancement completed. Language: {info.language}")
            return enhanced_text, segments_info
            
        except ImportError:
            logger.warning("Faster Whisper not available, using standard transcription")
            return self._fallback_transcription(audio_path)
        except Exception as e:
            logger.error(f"TurboScribe enhancement failed: {str(e)}")
            return self._fallback_transcription(audio_path)
    
    def post_process_transcription(self, text: str, segments_info: List[Dict] = None) -> str:
        """
        Постобработка транскрипции по методике TurboScribe.
        """
        try:
            logger.info("Applying TurboScribe post-processing")
            
            # 1. Нормализация Unicode
            text = unicodedata.normalize('NFKC', text)
            
            # 2. Исправление частых ошибок распознавания
            text = self._fix_common_errors(text)
            
            # 3. Контекстная корректировка
            text = self._apply_context_rules(text)
            
            # 4. Улучшение пунктуации на основе пауз
            if segments_info:
                text = self._enhance_punctuation_with_timing(text, segments_info)
            
            # 5. Финальная очистка и форматирование
            text = self._final_text_cleanup(text)
            
            logger.info("Post-processing completed")
            return text
            
        except Exception as e:
            logger.error(f"Post-processing failed: {str(e)}")
            return text
    
    def _fix_common_errors(self, text: str) -> str:
        """Исправление частых ошибок распознавания речи."""
        for wrong, correct in self.common_errors.items():
            # Исправляем с учетом границ слов
            pattern = r'\b' + re.escape(wrong) + r'\b'
            text = re.sub(pattern, correct, text, flags=re.IGNORECASE)
        
        return text
    
    def _apply_context_rules(self, text: str) -> str:
        """Применение контекстных правил для улучшения точности."""
        for pattern, replacement in self.context_rules:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text
    
    def _enhance_punctuation_with_timing(self, text: str, segments_info: List[Dict]) -> str:
        """Улучшение пунктуации на основе временных пауз между сегментами."""
        try:
            enhanced_parts = []
            
            for i, segment in enumerate(segments_info):
                segment_text = segment['text'].strip()
                
                # Добавляем знаки препинания на основе пауз
                if i < len(segments_info) - 1:
                    next_segment = segments_info[i + 1]
                    pause_duration = next_segment['start'] - segment['end']
                    
                    # Длинная пауза - точка или восклицательный знак
                    if pause_duration > 1.5:
                        if not segment_text.endswith(('.', '!', '?')):
                            # Определяем тип предложения по интонации
                            if any(word in segment_text.lower() for word in ['как', 'что', 'где', 'когда', 'почему', 'зачем']):
                                segment_text += '?'
                            else:
                                segment_text += '.'
                    # Средняя пауза - запятая
                    elif pause_duration > 0.8:
                        if not segment_text.endswith((',', '.', '!', '?')):
                            segment_text += ','
                
                enhanced_parts.append(segment_text)
            
            return ' '.join(enhanced_parts)
            
        except Exception as e:
            logger.warning(f"Punctuation enhancement failed: {str(e)}")
            return text
    
    def _final_text_cleanup(self, text: str) -> str:
        """Финальная очистка и форматирование текста."""
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
    
    def _fallback_transcription(self, audio_path: str) -> Tuple[str, List[Dict]]:
        """Fallback к стандартной транскрипции с простыми параметрами."""
        try:
            import whisper
            logger.info("Using simplified Whisper fallback")
            
            model = whisper.load_model("base")  # Используем легкую модель
            result = model.transcribe(audio_path, language="ru")
            
            raw_text = result.get('text', '')
            enhanced_text = self.post_process_transcription(raw_text)
            return enhanced_text, []
        except Exception as e:
            logger.error(f"Fallback transcription failed: {str(e)}")
            return "Ошибка транскрипции", []

# Интеграция с основной системой
def enhance_transcription_quality(audio_path: str) -> str:
    """
    Главная функция для улучшения качества транскрипции.
    """
    enhancer = TurboScribeEnhancer()
    enhanced_text, segments = enhancer.enhance_transcription_with_segments(audio_path)
    return enhanced_text