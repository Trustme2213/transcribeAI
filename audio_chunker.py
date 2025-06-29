import os
import math
from pydub import AudioSegment
import logging
from audio_preprocessor import AudioPreprocessor
from settings_manager import settings_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AudioChunker:
    """
    Class for processing large audio files by splitting them into smaller chunks.
    """
    def __init__(self, chunk_size_ms=None, overlap_ms=None, temp_dir='temp_audio', enable_preprocessing=None):
        """
        Initialize the audio chunker.
        
        Args:
            chunk_size_ms (int): Size of each chunk in milliseconds (uses database settings if None)
            overlap_ms (int): Overlap between chunks in milliseconds (uses database settings if None)
            temp_dir (str): Directory to store temporary files
            enable_preprocessing (bool): Enable audio preprocessing (uses database settings if None)
        """
        # Get settings from database
        config = settings_manager.get_audio_processing_config()
        
        # Use database settings or provided values
        self.chunk_size_ms = chunk_size_ms or config['chunk_size_ms']
        self.overlap_ms = overlap_ms or config['overlap_ms']
        self.temp_dir = temp_dir
        self.enable_preprocessing = enable_preprocessing if enable_preprocessing is not None else config['enabled']
        
        logger.info(f"AudioChunker initialized with chunk_size={self.chunk_size_ms}ms, overlap={self.overlap_ms}ms, preprocessing={'enabled' if self.enable_preprocessing else 'disabled'}")
        
        # Create temp directory if it doesn't exist
        os.makedirs(temp_dir, exist_ok=True)
        
        # Initialize audio preprocessor if enabled
        if self.enable_preprocessing:
            self.preprocessor = AudioPreprocessor(temp_dir=temp_dir)
            logger.info("Audio preprocessing enabled")
        else:
            self.preprocessor = None
            logger.info("Audio preprocessing disabled")
        
    def split_audio(self, audio_path):
        """
        Split an audio file into multiple chunks with optional preprocessing.
        
        Args:
            audio_path (str): Path to the audio file
            
        Returns:
            tuple: (list of chunk paths, preprocessed_full_audio_path or None)
        """
        try:
            logger.info(f"Loading audio file: {audio_path}")
            
            # Load the audio file using pydub (automatically handles various formats)
            audio = AudioSegment.from_file(audio_path)
            
            # Get total duration of the audio
            total_duration_ms = len(audio)
            logger.info(f"Audio duration: {total_duration_ms / 1000:.2f} seconds")
            
            # Calculate number of chunks needed
            num_chunks = math.ceil(total_duration_ms / (self.chunk_size_ms - self.overlap_ms))
            
            # Create full preprocessed version for comparison if preprocessing is enabled
            preprocessed_full_path = None
            if self.enable_preprocessing and self.preprocessor:
                try:
                    base_filename = os.path.splitext(os.path.basename(audio_path))[0]
                    preprocessed_full_path = os.path.join(self.temp_dir, f"{base_filename}_enhanced.wav")
                    preprocessed_full_path = self.preprocessor.preprocess_audio(audio_path, preprocessed_full_path)
                    logger.info(f"Created full enhanced audio file: {preprocessed_full_path}")
                except Exception as e:
                    logger.warning(f"Failed to create full enhanced audio: {e}")
                    preprocessed_full_path = None
            
            if num_chunks <= 1:
                logger.info("Audio file is small enough to process as is")
                # For single file, use preprocessed version for transcription if available
                if self.enable_preprocessing and self.preprocessor and preprocessed_full_path:
                    try:
                        return ([preprocessed_full_path], preprocessed_full_path)
                    except Exception as e:
                        logger.warning(f"Preprocessing failed for single file: {e}")
                        return ([audio_path], preprocessed_full_path)
                return ([audio_path], preprocessed_full_path)
                
            logger.info(f"Splitting audio into {num_chunks} chunks")
            
            chunk_paths = []
            
            # Generate base filename for chunks
            base_filename = os.path.splitext(os.path.basename(audio_path))[0]
            
            # Split the audio into chunks with overlap
            for i in range(num_chunks):
                start_ms = max(0, i * (self.chunk_size_ms - self.overlap_ms))
                end_ms = min(total_duration_ms, start_ms + self.chunk_size_ms)
                
                chunk = audio[start_ms:end_ms]
                chunk_path = os.path.join(self.temp_dir, f"{base_filename}_chunk_{i+1}.mp3")
                
                # Export the chunk as MP3
                chunk.export(chunk_path, format="mp3")
                
                logger.info(f"Created chunk {i+1}/{num_chunks}: {chunk_path}")
                
                # Apply preprocessing to chunk if enabled
                if self.enable_preprocessing and self.preprocessor:
                    try:
                        preprocessed_path = self.preprocessor.preprocess_audio(chunk_path)
                        chunk_paths.append(preprocessed_path)
                        logger.info(f"Preprocessed chunk {i+1}/{num_chunks}")
                    except Exception as e:
                        logger.warning(f"Preprocessing failed for chunk {i+1}: {e}")
                        chunk_paths.append(chunk_path)
                else:
                    chunk_paths.append(chunk_path)
                
            return (chunk_paths, preprocessed_full_path)
            
        except Exception as e:
            logger.error(f"Error splitting audio: {str(e)}")
            raise
            
    def combine_transcriptions(self, transcriptions):
        """
        Combine multiple transcriptions into one coherent text.
        
        Args:
            transcriptions (list): List of transcription texts
            
        Returns:
            str: Combined transcription text
        """
        if not transcriptions:
            return ""
            
        if len(transcriptions) == 1:
            return transcriptions[0]
            
        # Simple concatenation - could be improved with NLP techniques
        # to better handle sentence boundaries between chunks
        combined_text = ""
        
        for i, text in enumerate(transcriptions):
            if i > 0:
                # Try to avoid duplicate sentences at chunk boundaries
                # by using a simple heuristic - this could be improved
                overlap_chars = min(100, len(combined_text), len(text))
                last_part = combined_text[-overlap_chars:] if overlap_chars > 0 else ""
                
                # Find the longest common substring at the boundary
                # This is a simple approach - more sophisticated NLP could be used
                common_part = self._find_overlap(last_part, text[:overlap_chars])
                
                if common_part and len(common_part) > 10:  # Only if meaningful overlap found
                    # Append text without the overlapping part
                    combined_text += text[len(common_part):]
                else:
                    # No significant overlap, just add a space
                    combined_text += " " + text
            else:
                combined_text = text
                
        return combined_text
    
    def _find_overlap(self, s1, s2):
        """
        Find the longest overlapping substring between the end of s1 and start of s2.
        
        Args:
            s1 (str): First string
            s2 (str): Second string
            
        Returns:
            str: The longest overlapping substring
        """
        max_overlap = ""
        min_length = min(len(s1), len(s2))
        
        # Try different overlap lengths, starting from the longest possible
        for i in range(min_length, 0, -1):
            if s1[-i:] == s2[:i]:
                max_overlap = s1[-i:]
                break
                
        return max_overlap
    
    def cleanup_chunks(self, chunk_paths):
        """
        Delete temporary chunk files and preprocessed files.
        
        Args:
            chunk_paths (list): List of paths to the chunked audio files
        """
        for path in chunk_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"Deleted temporary file: {path}")
                    
                    # Also try to delete the original chunk if this is a preprocessed file
                    if "_preprocessed" in path:
                        original_path = path.replace("_preprocessed.wav", ".mp3")
                        if os.path.exists(original_path):
                            os.remove(original_path)
                            logger.info(f"Deleted original chunk file: {original_path}")
                            
            except Exception as e:
                logger.warning(f"Failed to delete file {path}: {str(e)}")
                
        # Clean up any remaining preprocessed files if preprocessor is enabled
        if self.enable_preprocessing and self.preprocessor:
            try:
                self.preprocessor.cleanup_preprocessed_files(chunk_paths)
            except Exception as e:
                logger.warning(f"Failed to cleanup preprocessed files: {str(e)}")
