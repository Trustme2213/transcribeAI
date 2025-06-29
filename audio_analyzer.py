"""
Интеллектуальный анализатор аудио для автоматической настройки параметров шумоподавления.
Анализирует спектрограмму и характеристики шума для каждого аудио файла.
"""

import numpy as np
import librosa
import scipy.signal
from scipy import stats
import matplotlib.pyplot as plt
import logging
import os
import tempfile
from pydub import AudioSegment

logger = logging.getLogger(__name__)

class AudioAnalyzer:
    """
    Класс для анализа аудио и автоматической настройки параметров обработки.
    """
    
    def __init__(self):
        """Инициализация анализатора."""
        self.sample_rate = 16000  # Стандартная частота дискретизации
        
    def analyze_audio(self, audio_path):
        """
        Комплексный анализ аудио файла для определения оптимальных параметров.
        
        Args:
            audio_path (str): Путь к аудио файлу
            
        Returns:
            dict: Оптимальные параметры шумоподавления
        """
        try:
            logger.info(f"Starting audio analysis for: {audio_path}")
            
            # Загружаем аудио
            audio_data, sr = librosa.load(audio_path, sr=self.sample_rate)
            
            # Проводим анализ
            spectral_analysis = self._analyze_spectrum(audio_data, sr)
            noise_analysis = self._analyze_noise(audio_data, sr)
            signal_analysis = self._analyze_signal(audio_data, sr)
            
            # Определяем оптимальные параметры
            optimal_params = self._calculate_optimal_parameters(
                spectral_analysis, noise_analysis, signal_analysis
            )
            
            logger.info(f"Audio analysis completed. Optimal params: {optimal_params}")
            return optimal_params
            
        except Exception as e:
            logger.error(f"Error analyzing audio: {str(e)}")
            # Возвращаем стандартные параметры при ошибке
            return self._get_default_parameters()
    
    def _analyze_spectrum(self, audio_data, sr):
        """
        Анализ спектра аудио сигнала.
        
        Args:
            audio_data (np.array): Аудио данные
            sr (int): Частота дискретизации
            
        Returns:
            dict: Результаты спектрального анализа
        """
        # Вычисляем спектрограмму
        stft = librosa.stft(audio_data, n_fft=2048, hop_length=512)
        magnitude = np.abs(stft)
        
        # Анализируем частотные характеристики
        frequencies = librosa.fft_frequencies(sr=sr, n_fft=2048)
        
        # Находим доминирующие частоты
        avg_magnitude = np.mean(magnitude, axis=1)
        dominant_freq_idx = np.argmax(avg_magnitude)
        dominant_frequency = frequencies[dominant_freq_idx]
        
        # Анализируем распределение энергии по частотам
        low_freq_energy = np.sum(avg_magnitude[frequencies < 500])  # < 500 Hz
        mid_freq_energy = np.sum(avg_magnitude[(frequencies >= 500) & (frequencies < 4000)])  # 500-4000 Hz
        high_freq_energy = np.sum(avg_magnitude[frequencies >= 4000])  # > 4000 Hz
        
        total_energy = low_freq_energy + mid_freq_energy + high_freq_energy
        
        return {
            'dominant_frequency': dominant_frequency,
            'low_freq_ratio': low_freq_energy / total_energy if total_energy > 0 else 0,
            'mid_freq_ratio': mid_freq_energy / total_energy if total_energy > 0 else 0,
            'high_freq_ratio': high_freq_energy / total_energy if total_energy > 0 else 0,
            'spectral_centroid': np.mean(librosa.feature.spectral_centroid(y=audio_data, sr=sr)),
            'spectral_bandwidth': np.mean(librosa.feature.spectral_bandwidth(y=audio_data, sr=sr)),
            'spectral_rolloff': np.mean(librosa.feature.spectral_rolloff(y=audio_data, sr=sr))
        }
    
    def _analyze_noise(self, audio_data, sr):
        """
        Анализ шумовых характеристик.
        
        Args:
            audio_data (np.array): Аудио данные
            sr (int): Частота дискретизации
            
        Returns:
            dict: Результаты анализа шума
        """
        # Определяем тихие участки (предположительно шум)
        rms = librosa.feature.rms(y=audio_data, frame_length=2048, hop_length=512)[0]
        rms_threshold = np.percentile(rms, 20)  # 20-й процентиль как порог шума
        
        # Находим участки тишины/шума
        quiet_frames = rms < rms_threshold
        
        if np.any(quiet_frames):
            # Анализируем шумовые участки
            noise_level_db = 20 * np.log10(np.mean(rms[quiet_frames]) + 1e-10)
            noise_variance = np.var(rms[quiet_frames])
        else:
            # Если нет явных тихих участков, используем минимальный уровень
            noise_level_db = 20 * np.log10(np.min(rms) + 1e-10)
            noise_variance = np.var(rms)
        
        # Анализируем постоянство шума
        noise_consistency = 1.0 - (noise_variance / (np.mean(rms) + 1e-10))
        noise_consistency = max(0, min(1, noise_consistency))
        
        return {
            'noise_level_db': noise_level_db,
            'noise_variance': noise_variance,
            'noise_consistency': noise_consistency,
            'quiet_ratio': np.sum(quiet_frames) / len(quiet_frames)
        }
    
    def _analyze_signal(self, audio_data, sr):
        """
        Анализ полезного сигнала (речи).
        
        Args:
            audio_data (np.array): Аудио данные
            sr (int): Частота дискретизации
            
        Returns:
            dict: Результаты анализа сигнала
        """
        # Вычисляем RMS для оценки громкости
        rms = librosa.feature.rms(y=audio_data, frame_length=2048, hop_length=512)[0]
        
        # Определяем активные участки речи
        rms_threshold = np.percentile(rms, 50)  # Медиана как порог активности
        speech_frames = rms > rms_threshold
        
        # Анализируем динамический диапазон
        dynamic_range_db = 20 * np.log10(np.max(rms) / (np.min(rms) + 1e-10))
        
        # Анализируем временные характеристики
        speech_ratio = np.sum(speech_frames) / len(speech_frames)
        
        # Вычисляем zero crossing rate для анализа речевых характеристик
        zcr = librosa.feature.zero_crossing_rate(audio_data)[0]
        avg_zcr = np.mean(zcr)
        
        return {
            'dynamic_range_db': dynamic_range_db,
            'speech_ratio': speech_ratio,
            'avg_rms_db': 20 * np.log10(np.mean(rms) + 1e-10),
            'zero_crossing_rate': avg_zcr
        }
    
    def _calculate_optimal_parameters(self, spectral_analysis, noise_analysis, signal_analysis):
        """
        Вычисляет оптимальные параметры шумоподавления на основе анализа.
        
        Args:
            spectral_analysis (dict): Результаты спектрального анализа
            noise_analysis (dict): Результаты анализа шума
            signal_analysis (dict): Результаты анализа сигнала
            
        Returns:
            dict: Оптимальные параметры
        """
        # Базовые параметры
        base_params = self._get_default_parameters()
        
        # Настройка уровня шумоподавления
        noise_level = noise_analysis['noise_level_db']
        if noise_level < -30:  # Очень тихий шум
            noise_reduction = 0.3
        elif noise_level < -25:  # Тихий шум
            noise_reduction = 0.5
        elif noise_level < -20:  # Умеренный шум
            noise_reduction = 0.65
        elif noise_level < -15:  # Заметный шум
            noise_reduction = 0.8
        else:  # Сильный шум
            noise_reduction = 0.9
        
        # Корректировка на основе консистентности шума
        if noise_analysis['noise_consistency'] > 0.8:  # Постоянный шум
            noise_reduction += 0.1
        elif noise_analysis['noise_consistency'] < 0.3:  # Переменный шум
            noise_reduction -= 0.1
        
        # Настройка порога шума
        noise_floor = max(-35, min(-10, noise_level - 5))
        
        # Настройка размера окна FFT на основе спектральных характеристик
        if spectral_analysis['spectral_bandwidth'] > 3000:  # Широкий спектр
            n_fft = 4096
        elif spectral_analysis['spectral_bandwidth'] > 1500:  # Средний спектр
            n_fft = 2048
        else:  # Узкий спектр
            n_fft = 1024
        
        # Настройка времен атаки и затухания
        if signal_analysis['dynamic_range_db'] > 20:  # Большой динамический диапазон
            attack_time = 0.002  # Быстрая атака
            decay_time = 0.05   # Быстрое затухание
        elif signal_analysis['dynamic_range_db'] > 10:  # Средний динамический диапазон
            attack_time = 0.005  # Средняя атака
            decay_time = 0.07   # Среднее затухание
        else:  # Малый динамический диапазон
            attack_time = 0.01   # Медленная атака
            decay_time = 0.1    # Медленное затухание
        
        # Ограничиваем значения
        noise_reduction = max(0.1, min(1.0, noise_reduction))
        
        optimal_params = {
            'noise_reduction_level': round(noise_reduction, 2),
            'noise_floor_db': int(noise_floor),
            'n_fft': int(n_fft),
            'attack_time': round(attack_time, 3),
            'decay_time': round(decay_time, 3)
        }
        
        logger.info(f"Calculated optimal parameters: {optimal_params}")
        logger.info(f"Based on - Noise level: {noise_level:.1f}dB, "
                   f"Spectral bandwidth: {spectral_analysis['spectral_bandwidth']:.0f}Hz, "
                   f"Dynamic range: {signal_analysis['dynamic_range_db']:.1f}dB")
        
        return optimal_params
    
    def _get_default_parameters(self):
        """Возвращает параметры по умолчанию."""
        return {
            'noise_reduction_level': 0.65,
            'noise_floor_db': -22,
            'n_fft': 2048,
            'attack_time': 0.005,
            'decay_time': 0.07
        }
    
    def save_analysis_plot(self, audio_path, output_dir='temp_audio'):
        """
        Создает и сохраняет график спектрограммы для визуального анализа.
        
        Args:
            audio_path (str): Путь к аудио файлу
            output_dir (str): Директория для сохранения графика
            
        Returns:
            str: Путь к сохраненному графику или None при ошибке
        """
        try:
            # Загружаем аудио
            audio_data, sr = librosa.load(audio_path, sr=self.sample_rate)
            
            # Создаем спектрограмму
            stft = librosa.stft(audio_data, n_fft=2048, hop_length=512)
            magnitude_db = librosa.amplitude_to_db(np.abs(stft), ref=np.max)
            
            # Создаем график
            plt.figure(figsize=(12, 8))
            
            # Спектрограмма
            plt.subplot(2, 1, 1)
            librosa.display.specshow(magnitude_db, sr=sr, hop_length=512, x_axis='time', y_axis='hz')
            plt.colorbar(format='%+2.0f dB')
            plt.title('Спектрограмма')
            plt.ylabel('Частота (Hz)')
            
            # Форма волны
            plt.subplot(2, 1, 2)
            times = librosa.frames_to_time(np.arange(len(audio_data)), sr=sr)
            plt.plot(times[:len(audio_data)], audio_data)
            plt.title('Форма волны')
            plt.xlabel('Время (с)')
            plt.ylabel('Амплитуда')
            
            plt.tight_layout()
            
            # Сохраняем график
            os.makedirs(output_dir, exist_ok=True)
            filename = f"analysis_{os.path.basename(audio_path).split('.')[0]}.png"
            plot_path = os.path.join(output_dir, filename)
            plt.savefig(plot_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            logger.info(f"Analysis plot saved to: {plot_path}")
            return plot_path
            
        except Exception as e:
            logger.error(f"Error creating analysis plot: {str(e)}")
            return None