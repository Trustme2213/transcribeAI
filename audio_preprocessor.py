import os
import tempfile
import logging
from pydub import AudioSegment
from pydub.effects import normalize, compress_dynamic_range
from pydub.silence import split_on_silence
import subprocess
from settings_manager import settings_manager
from audio_analyzer import AudioAnalyzer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AudioPreprocessor:
    """
    Class for preprocessing audio files to improve transcription quality.
    """
    
    def __init__(self, temp_dir='temp_audio'):
        """
        Initialize the audio preprocessor.
        
        Args:
            temp_dir (str): Directory to store temporary files
        """
        self.temp_dir = temp_dir
        self.analyzer = AudioAnalyzer()
        os.makedirs(temp_dir, exist_ok=True)
        
    def preprocess_audio(self, audio_path, output_path=None):
        """
        Apply multiple preprocessing steps to improve audio quality.
        
        Args:
            audio_path (str): Path to the input audio file
            output_path (str): Path for the preprocessed audio file (optional)
            
        Returns:
            str: Path to the preprocessed audio file
        """
        # Get current settings
        config = settings_manager.get_audio_processing_config()
        
        # If preprocessing is disabled, return original path
        if not config['enabled']:
            logger.info("Audio preprocessing is disabled in settings")
            return audio_path
            
        try:
            logger.info(f"Starting audio preprocessing for: {audio_path}")
            logger.info(f"Preprocessing config: {config}")
            
            # Generate output path if not provided
            if output_path is None:
                base_name = os.path.splitext(os.path.basename(audio_path))[0]
                output_path = os.path.join(self.temp_dir, f"{base_name}_preprocessed.wav")
            
            # Load audio
            audio = AudioSegment.from_file(audio_path)
            logger.info(f"Original audio duration: {len(audio)/1000:.2f} seconds")
            
            # Step 1: Convert to mono and standardize sample rate (always applied)
            audio = self._standardize_format(audio)
            
            # Step 2: Noise reduction using ffmpeg (conditional)
            if config['noise_reduction']:
                # Check if intelligent analysis is enabled
                intelligent_enabled = settings_manager.get_setting('intelligent_analysis_enabled', True)
                
                if intelligent_enabled:
                    # Use intelligent analysis to determine optimal parameters
                    noise_params = self._get_intelligent_noise_params(audio_path)
                else:
                    # Use manual settings from admin panel
                    noise_params = {
                        'noise_reduction': settings_manager.get_setting('noise_reduction_level', 0.65),
                        'noise_floor': settings_manager.get_setting('noise_floor_db', -22),
                        'n_fft': settings_manager.get_setting('n_fft', 2048),
                        'attack': settings_manager.get_setting('attack_time', 0.005),
                        'decay': settings_manager.get_setting('decay_time', 0.07)
                    }
                
                audio = self._reduce_noise_ffmpeg(audio, noise_params)
            
            # Step 3: Normalize volume (conditional)
            if config['volume_normalization']:
                audio = self._normalize_volume(audio)
            
            # Step 4: Apply dynamic range compression (conditional)
            if config['compression']:
                audio = self._apply_compression(audio)
            
            # Step 5: Remove silence and optimize for speech (conditional)
            if config['speech_optimization']:
                audio = self._optimize_for_speech(audio)
            
            # Export the preprocessed audio
            audio.export(output_path, format="wav", parameters=["-ac", "1", "-ar", "16000"])
            logger.info(f"Preprocessed audio saved to: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error preprocessing audio: {str(e)}")
            # Return original path if preprocessing fails
            return audio_path
    
    def _standardize_format(self, audio):
        """
        Convert audio to mono and standardize sample rate.
        
        Args:
            audio (AudioSegment): Input audio segment
            
        Returns:
            AudioSegment: Standardized audio
        """
        logger.info("Standardizing audio format")
        
        # Convert to mono
        if audio.channels > 1:
            audio = audio.set_channels(1)
            logger.info("Converted to mono")
        
        # Set sample rate to 16kHz (optimal for speech recognition)
        if audio.frame_rate != 16000:
            audio = audio.set_frame_rate(16000)
            logger.info("Set sample rate to 16kHz")
            
        return audio
    
    def _reduce_noise_ffmpeg(self, audio, noise_params=None):
        """
        Apply noise reduction using ffmpeg filters with configurable parameters.
        
        Args:
            audio (AudioSegment): Input audio segment
            noise_params (dict): Noise reduction parameters
            
        Returns:
            AudioSegment: Noise-reduced audio
        """
        # Set default parameters if not provided
        if noise_params is None:
            noise_params = {
                'noise_reduction': 0.65,
                'noise_floor': -22,
                'n_fft': 2048,
                'attack': 0.005,
                'decay': 0.07
            }
        
        logger.info(f"Applying noise reduction with params: {noise_params}")
        
        temp_input_name = None
        temp_output_name = None
        
        try:
            # Create temporary files
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_input:
                temp_input_name = temp_input.name
                
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_output:
                temp_output_name = temp_output.name
                    
            # Export audio to temporary file
            audio.export(temp_input_name, format="wav")
            
            # Build advanced noise reduction filter chain
            # Using afftdn (FFT denoiser) with configurable parameters
            noise_reduction_strength = noise_params.get('noise_reduction_level', noise_params.get('noise_reduction', 0.65))
            noise_floor_db = noise_params.get('noise_floor_db', noise_params.get('noise_floor', -22))
            n_fft = noise_params.get('n_fft', 2048)
            attack_time = noise_params.get('attack_time', noise_params.get('attack', 0.005))
            decay_time = noise_params.get('decay_time', noise_params.get('decay', 0.07))
            
            # Advanced noise reduction with multiple stages
            filter_chain = [
                f"highpass=f=80",  # Remove low-frequency noise
                f"lowpass=f=12000",  # Remove high-frequency noise
                f"afftdn=nr={noise_reduction_strength}:nf={noise_floor_db}:nt=w:om=o:tn=1",  # FFT denoiser
                f"compand=attacks={attack_time}:decays={decay_time}:points=-80/-80|-45/-15|-27/-9|0/-7|20/-7",  # Dynamic range compression
                "volume=1.0"  # Normalize volume
            ]
            
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", temp_input_name,
                "-af", ",".join(filter_chain),
                "-ar", "16000", "-ac", "1",
                temp_output_name
            ]
            
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Load the processed audio
                processed_audio = AudioSegment.from_wav(temp_output_name)
                logger.info("Noise reduction applied successfully")
                return processed_audio
            else:
                logger.warning(f"FFmpeg noise reduction failed: {result.stderr}")
                return audio
                        
        except Exception as e:
            logger.warning(f"Error applying noise reduction: {str(e)}")
            return audio
        finally:
            # Cleanup temporary files
            try:
                if temp_input_name and os.path.exists(temp_input_name):
                    os.unlink(temp_input_name)
                if temp_output_name and os.path.exists(temp_output_name):
                    os.unlink(temp_output_name)
            except:
                pass
    
    def _normalize_volume(self, audio):
        """
        Normalize audio volume.
        
        Args:
            audio (AudioSegment): Input audio segment
            
        Returns:
            AudioSegment: Volume-normalized audio
        """
        logger.info("Normalizing volume")
        
        # Apply normalization
        normalized = normalize(audio)
        
        # Gentle gain adjustment if needed
        if normalized.dBFS < -25:
            # Boost only very quiet audio
            gain_adjustment = -25 - normalized.dBFS
            normalized = normalized + min(gain_adjustment, 6)  # Cap at 6dB boost
            logger.info(f"Applied gentle gain boost: {min(gain_adjustment, 6):.1f}dB")
        
        return normalized
    
    def _apply_compression(self, audio):
        """
        Apply dynamic range compression to even out volume levels.
        
        Args:
            audio (AudioSegment): Input audio segment
            
        Returns:
            AudioSegment: Compressed audio
        """
        logger.info("Applying dynamic range compression")
        
        try:
            # Apply gentle compression
            compressed = compress_dynamic_range(
                audio,
                threshold=-20.0,  # Higher threshold for gentler compression
                ratio=2.0,        # Lower compression ratio
                attack=10.0,      # Slower attack time
                release=100.0     # Longer release time
            )
            return compressed
        except Exception as e:
            logger.warning(f"Error applying compression: {str(e)}")
            return audio
    
    def _optimize_for_speech(self, audio):
        """
        Optimize audio for speech recognition by removing long silences.
        
        Args:
            audio (AudioSegment): Input audio segment
            
        Returns:
            AudioSegment: Speech-optimized audio
        """
        logger.info("Optimizing for speech")
        
        try:
            # Split on silence to identify speech segments
            chunks = split_on_silence(
                audio,
                min_silence_len=1000,    # Minimum silence length in ms
                silence_thresh=-40,      # Silence threshold in dBFS
                keep_silence=500         # Keep some silence for natural flow
            )
            
            if chunks:
                # Rejoin chunks with reduced silence
                optimized = AudioSegment.empty()
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        # Add short pause between chunks
                        optimized += AudioSegment.silent(duration=200)
                    optimized += chunk
                
                logger.info(f"Optimized speech: {len(chunks)} segments, "
                           f"duration reduced from {len(audio)/1000:.1f}s to {len(optimized)/1000:.1f}s")
                return optimized
            else:
                logger.info("No speech segments detected, keeping original")
                return audio
                
        except Exception as e:
            logger.warning(f"Error optimizing for speech: {str(e)}")
            return audio
    
    def preprocess_batch(self, audio_paths):
        """
        Preprocess multiple audio files.
        
        Args:
            audio_paths (list): List of paths to audio files
            
        Returns:
            list: List of paths to preprocessed audio files
        """
        preprocessed_paths = []
        
        for i, audio_path in enumerate(audio_paths):
            logger.info(f"Preprocessing audio {i+1}/{len(audio_paths)}: {audio_path}")
            try:
                preprocessed_path = self.preprocess_audio(audio_path)
                preprocessed_paths.append(preprocessed_path)
            except Exception as e:
                logger.error(f"Failed to preprocess {audio_path}: {str(e)}")
                # Use original file if preprocessing fails
                preprocessed_paths.append(audio_path)
                
        return preprocessed_paths
    
    def cleanup_preprocessed_files(self, file_paths):
        """
        Clean up preprocessed temporary files.
        
        Args:
            file_paths (list): List of file paths to clean up
        """
        for file_path in file_paths:
            try:
                if os.path.exists(file_path) and self.temp_dir in file_path:
                    os.remove(file_path)
                    logger.info(f"Cleaned up preprocessed file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up file {file_path}: {str(e)}")
    
    def _get_intelligent_noise_params(self, audio_path):
        """
        Анализирует аудио файл и определяет оптимальные параметры шумоподавления.
        
        Args:
            audio_path (str): Путь к аудио файлу
            
        Returns:
            dict: Оптимальные параметры шумоподавления
        """
        try:
            # Проводим интеллектуальный анализ аудио
            optimal_params = self.analyzer.analyze_audio(audio_path)
            
            # Логируем результаты анализа
            logger.info(f"Intelligent analysis results for {os.path.basename(audio_path)}:")
            logger.info(f"  - Noise reduction level: {optimal_params['noise_reduction_level']}")
            logger.info(f"  - Noise floor: {optimal_params['noise_floor_db']} dB")
            logger.info(f"  - FFT window size: {optimal_params['n_fft']}")
            logger.info(f"  - Attack time: {optimal_params['attack_time']} s")
            logger.info(f"  - Decay time: {optimal_params['decay_time']} s")
            
            return optimal_params
            
        except Exception as e:
            logger.error(f"Error in intelligent analysis, using fallback settings: {str(e)}")
            # Возвращаем настройки из админки как fallback
            from settings_manager import settings_manager
            return {
                'noise_reduction': settings_manager.get_setting('noise_reduction_level', 0.65),
                'noise_floor': settings_manager.get_setting('noise_floor_db', -22),
                'n_fft': settings_manager.get_setting('n_fft', 2048),
                'attack': settings_manager.get_setting('attack_time', 0.005),
                'decay': settings_manager.get_setting('decay_time', 0.07)
            }