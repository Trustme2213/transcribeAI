"""
Модуль для работы с продвинутыми моделями транскрипции.
Поддерживает несколько современных моделей для улучшения качества распознавания речи.
"""

import logging
import os
import tempfile
from typing import Optional, Dict, Any
import requests
import json

logger = logging.getLogger(__name__)

class AdvancedTranscriptionModels:
    """
    Класс для работы с продвинутыми моделями транскрипции.
    """
    
    def __init__(self):
        """Инициализация модулей транскрипции."""
        self.available_models = {
            'whisper_large_v3': {
                'name': 'OpenAI Whisper Large v3',
                'description': 'Самая точная модель Whisper (3GB)',
                'library': 'openai-whisper',
                'quality': 'excellent',
                'speed': 'slow',
                'memory': '3GB'
            },
            'faster_whisper': {
                'name': 'Faster Whisper',
                'description': 'Оптимизированная версия Whisper (до 4x быстрее)',
                'library': 'faster-whisper',
                'quality': 'excellent',
                'speed': 'fast',
                'memory': '1-3GB'
            },
            'speech_t5': {
                'name': 'SpeechT5',
                'description': 'Microsoft SpeechT5 для русского языка',
                'library': 'transformers',
                'quality': 'very_good',
                'speed': 'medium',
                'memory': '2GB'
            },
            'wav2vec2': {
                'name': 'Wav2Vec2 Russian',
                'description': 'Facebook Wav2Vec2 специально для русского',
                'library': 'transformers',
                'quality': 'very_good',
                'speed': 'fast',
                'memory': '1GB'
            },
            'yandex_speechkit': {
                'name': 'Yandex SpeechKit',
                'description': 'API Яндекс SpeechKit (облачный)',
                'library': 'api',
                'quality': 'excellent',
                'speed': 'very_fast',
                'memory': 'minimal'
            }
        }
    
    def get_model_info(self) -> Dict[str, Any]:
        """Возвращает информацию о доступных моделях."""
        return self.available_models
    
    def install_faster_whisper(self) -> bool:
        """
        Устанавливает Faster Whisper - оптимизированную версию Whisper.
        """
        try:
            import subprocess
            import sys
            
            logger.info("Installing faster-whisper...")
            result = subprocess.run([
                sys.executable, '-m', 'pip', 'install', 
                'faster-whisper', 'ctranslate2'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("faster-whisper installed successfully")
                return True
            else:
                logger.error(f"Failed to install faster-whisper: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error installing faster-whisper: {str(e)}")
            return False
    
    def transcribe_with_faster_whisper(self, audio_path: str, model_size: str = "large-v3") -> Optional[str]:
        """
        Транскрибирует аудио с помощью Faster Whisper.
        
        Args:
            audio_path: Путь к аудио файлу
            model_size: Размер модели (tiny, base, small, medium, large-v2, large-v3)
            
        Returns:
            Текст транскрипции или None при ошибке
        """
        try:
            from faster_whisper import WhisperModel
            
            logger.info(f"Loading Faster Whisper model: {model_size}")
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            
            logger.info(f"Transcribing with Faster Whisper: {audio_path}")
            segments, info = model.transcribe(
                audio_path, 
                language="ru",
                beam_size=5,
                best_of=5,
                temperature=0.0,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                condition_on_previous_text=False
            )
            
            # Собираем текст из сегментов
            transcription = ""
            for segment in segments:
                transcription += segment.text + " "
            
            logger.info(f"Faster Whisper transcription completed. Detected language: {info.language}")
            return transcription.strip()
            
        except ImportError:
            logger.error("faster-whisper not installed. Please install it first.")
            return None
        except Exception as e:
            logger.error(f"Error in Faster Whisper transcription: {str(e)}")
            return None
    
    def transcribe_with_wav2vec2(self, audio_path: str) -> Optional[str]:
        """
        Транскрибирует аудио с помощью Wav2Vec2 для русского языка.
        """
        try:
            import torch
            from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
            import librosa
            
            # Используем предобученную модель для русского языка
            model_name = "jonatasgrosman/wav2vec2-large-xlsr-53-russian"
            
            logger.info(f"Loading Wav2Vec2 model: {model_name}")
            processor = Wav2Vec2Processor.from_pretrained(model_name)
            model = Wav2Vec2ForCTC.from_pretrained(model_name)
            
            # Загружаем аудио
            speech, rate = librosa.load(audio_path, sr=16000)
            
            # Обрабатываем аудио
            inputs = processor(speech, sampling_rate=16000, return_tensors="pt", padding=True)
            
            # Получаем предсказания
            with torch.no_grad():
                logits = model(inputs.input_values).logits
            
            # Декодируем
            predicted_ids = torch.argmax(logits, dim=-1)
            transcription = processor.batch_decode(predicted_ids)[0]
            
            logger.info("Wav2Vec2 transcription completed")
            return transcription
            
        except ImportError as e:
            logger.error(f"Required libraries not installed for Wav2Vec2: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error in Wav2Vec2 transcription: {str(e)}")
            return None
    
    def transcribe_with_yandex_speechkit(self, audio_path: str, api_key: str) -> Optional[str]:
        """
        Транскрибирует аудио через API Yandex SpeechKit.
        """
        try:
            # Читаем аудио файл
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            # Подготавливаем запрос к API
            headers = {
                'Authorization': f'Api-Key {api_key}',
                'Content-Type': 'audio/wav'
            }
            
            params = {
                'lang': 'ru-RU',
                'topic': 'general',
                'format': 'lpcm',
                'sampleRateHertz': 16000
            }
            
            url = 'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize'
            
            logger.info("Sending request to Yandex SpeechKit")
            response = requests.post(url, headers=headers, params=params, data=audio_data)
            
            if response.status_code == 200:
                result = response.json()
                transcription = result.get('result', '')
                logger.info("Yandex SpeechKit transcription completed")
                return transcription
            else:
                logger.error(f"Yandex SpeechKit API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error in Yandex SpeechKit transcription: {str(e)}")
            return None
    
    def get_best_model_recommendation(self, audio_duration: float, quality_priority: str = "high") -> str:
        """
        Рекомендует лучшую модель на основе длительности аудио и приоритетов.
        
        Args:
            audio_duration: Длительность аудио в секундах
            quality_priority: "high", "medium", "speed"
            
        Returns:
            Название рекомендуемой модели
        """
        if quality_priority == "high":
            if audio_duration < 60:  # Короткие файлы
                return "faster_whisper"  # Быстро и качественно
            else:  # Длинные файлы
                return "yandex_speechkit"  # Облачный, быстрый
        
        elif quality_priority == "speed":
            return "wav2vec2"  # Самый быстрый локальный
        
        else:  # medium
            return "faster_whisper"  # Компромисс
    
    def transcribe_with_best_model(self, audio_path: str, model_preference: str = "auto") -> tuple[Optional[str], str]:
        """
        Транскрибирует аудио, выбирая лучшую доступную модель.
        
        Returns:
            tuple: (transcription_text, used_model_name)
        """
        try:
            # Определяем длительность аудио
            import librosa
            y, sr = librosa.load(audio_path, sr=None)
            duration = len(y) / sr
            
            # Выбираем модель
            if model_preference == "auto":
                model_name = self.get_best_model_recommendation(duration, "high")
            else:
                model_name = model_preference
            
            logger.info(f"Selected model: {model_name} for {duration:.1f}s audio")
            
            # Пробуем транскрибировать с выбранной моделью
            if model_name == "faster_whisper":
                text = self.transcribe_with_faster_whisper(audio_path, "large-v3")
                if text:
                    return text, "faster_whisper_large-v3"
            
            elif model_name == "wav2vec2":
                text = self.transcribe_with_wav2vec2(audio_path)
                if text:
                    return text, "wav2vec2_russian"
            
            # Fallback к обычному Whisper
            logger.info("Falling back to standard Whisper")
            from whisper_transcription import transcribe_audio
            text = transcribe_audio(audio_path)
            return text, "whisper_medium"
            
        except Exception as e:
            logger.error(f"Error in best model transcription: {str(e)}")
            return None, "error"