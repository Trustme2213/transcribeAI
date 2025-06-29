#!/usr/bin/env python3
"""
Test script for audio preprocessing functionality.
"""

import os
import logging
from audio_preprocessor import AudioPreprocessor
from audio_chunker import AudioChunker

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_audio_preprocessing():
    """
    Test the audio preprocessing functionality.
    """
    # Test parameters
    test_audio_file = "test_audio.wav"  # You would need to provide this
    temp_dir = "temp_audio_test"
    
    # Create test directory
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # Test 1: Basic audio preprocessor
        logger.info("=== Testing Audio Preprocessor ===")
        preprocessor = AudioPreprocessor(temp_dir=temp_dir)
        
        # Create a simple test audio file if it doesn't exist
        if not os.path.exists(test_audio_file):
            logger.info("Creating test audio file...")
            from pydub import AudioSegment
            from pydub.generators import Sine
            
            # Generate a 10-second sine wave at 440Hz for testing
            test_tone = Sine(440).to_audio_segment(duration=10000)
            test_tone.export(test_audio_file, format="wav")
            logger.info(f"Created test audio file: {test_audio_file}")
        
        # Test preprocessing
        if os.path.exists(test_audio_file):
            preprocessed_file = preprocessor.preprocess_audio(test_audio_file)
            logger.info(f"Preprocessing successful: {preprocessed_file}")
            
            # Test 2: Audio chunker with preprocessing
            logger.info("=== Testing Audio Chunker with Preprocessing ===")
            chunker = AudioChunker(
                chunk_size_ms=5000,  # 5 seconds for testing
                overlap_ms=500,      # 0.5 seconds overlap
                temp_dir=temp_dir,
                enable_preprocessing=True
            )
            
            chunk_paths = chunker.split_audio(test_audio_file)
            logger.info(f"Created {len(chunk_paths)} chunks")
            
            # Test 3: Audio chunker without preprocessing
            logger.info("=== Testing Audio Chunker without Preprocessing ===")
            chunker_no_preprocess = AudioChunker(
                chunk_size_ms=5000,
                overlap_ms=500,
                temp_dir=temp_dir,
                enable_preprocessing=False
            )
            
            chunk_paths_no_preprocess = chunker_no_preprocess.split_audio(test_audio_file)
            logger.info(f"Created {len(chunk_paths_no_preprocess)} chunks without preprocessing")
            
            # Cleanup
            chunker.cleanup_chunks(chunk_paths)
            chunker_no_preprocess.cleanup_chunks(chunk_paths_no_preprocess)
            
            if os.path.exists(preprocessed_file):
                os.remove(preprocessed_file)
            
            logger.info("=== All tests completed successfully ===")
            
        else:
            logger.error(f"Test audio file not found: {test_audio_file}")
            
    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup test files
        if os.path.exists(test_audio_file):
            os.remove(test_audio_file)
        
        # Remove test directory if empty
        try:
            os.rmdir(temp_dir)
        except:
            pass

def test_ffmpeg_availability():
    """
    Test if ffmpeg is available and working.
    """
    import subprocess
    
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("FFmpeg is available")
            return True
        else:
            logger.error("FFmpeg is not working properly")
            return False
    except FileNotFoundError:
        logger.error("FFmpeg is not installed or not in PATH")
        return False

if __name__ == "__main__":
    logger.info("Starting audio preprocessing tests...")
    
    # Test ffmpeg availability first
    if test_ffmpeg_availability():
        test_audio_preprocessing()
    else:
        logger.error("Cannot run tests without ffmpeg")