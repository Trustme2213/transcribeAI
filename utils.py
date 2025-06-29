import os
import json
import logging
import sqlite3
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def ensure_dirs_exist(dirs):
    """
    Ensure that all specified directories exist.
    
    Args:
        dirs (list): List of directory paths
    """
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"Ensured directory exists: {dir_path}")

def save_transcription(text, file_path="transcripts", user_id=None, original_filename=None):
    """
    Save transcription text to a file.
    
    Args:
        text (str): Transcription text
        file_path (str): Path to save the file. If directory doesn't exist, it will be created.
        user_id (int, optional): User ID for filename
        original_filename (str, optional): Original filename to use as base for transcription file
        
    Returns:
        str: Path to the saved file
    """
    # Ensure file_path is not empty
    if not file_path:
        file_path = "transcripts"  # Use default directory if none provided
    
    # Create a timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create directory if it doesn't exist
    os.makedirs(file_path, exist_ok=True)
    
    # Use original filename as base if provided
    if original_filename:
        # Remove extension from original filename
        base_name = os.path.splitext(original_filename)[0]
        # Clean filename of invalid characters
        base_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if user_id:
            filename = f"{user_id}_{base_name}_{timestamp}_transcript.txt"
        else:
            filename = f"{base_name}_{timestamp}_transcript.txt"
    else:
        # Fallback to timestamp-based naming
        if user_id:
            filename = f"{user_id}_{timestamp}_transcript.txt"
        else:
            filename = f"{timestamp}_transcript.txt"
    
    full_path = os.path.join(file_path, filename)
    
    # Save the transcription
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(text)
    
    logger.info(f"Saved transcription to {full_path}")
    return full_path

def parse_gpt_response(response_text):
    """
    Parse JSON from YandexGPT response.
    
    Args:
        response_text (str): Response from YandexGPT
        
    Returns:
        dict: Parsed JSON data or None if parsing failed
    """
    try:
        # Clean up the response text (remove markdown code blocks if present)
        clean_text = response_text.replace("```json", "").replace("```", "").strip()
        
        # Try to parse JSON
        return json.loads(clean_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from GPT response: {str(e)}")
        logger.debug(f"Response text was: {response_text}")
        return None

def get_survey_by_id(survey_id: int) -> dict:
    """
    Get survey details by ID.
    
    Args:
        survey_id (int): Survey ID
        
    Returns:
        dict: Survey details including client name
    """
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT client_name FROM surveys WHERE survey_id = ?', (survey_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return {"survey_id": survey_id, "client_name": result[0]}
    return None

def create_inspection(user_id: int, survey_id: int) -> int:
    """
    Create a new inspection record.
    
    Args:
        user_id (int): User ID
        survey_id (int): Survey ID
        
    Returns:
        int: New inspection ID
    """
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO inspections (user_id, survey_id)
        VALUES (?, ?)
    ''', (user_id, survey_id))
    
    inspection_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    logger.info(f"Created inspection ID {inspection_id} for user {user_id} on survey {survey_id}")
    return inspection_id

def initialize_answers(inspection_id: int, question_ids: list):
    """
    Initialize all answers for an inspection with null values.
    
    Args:
        inspection_id (int): Inspection ID
        question_ids (list): List of question IDs
    """
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    # Insert null answers for all questions
    for question_id in question_ids:
        try:
            cursor.execute('''
                INSERT INTO answers (inspection_id, question_id, answer_text)
                VALUES (?, ?, "null")
            ''', (inspection_id, question_id))
        except sqlite3.IntegrityError:
            # Answer might already exist
            pass
    
    conn.commit()
    conn.close()
    
    logger.info(f"Initialized {len(question_ids)} answers for inspection {inspection_id}")

def format_duration(seconds):
    """
    Format seconds into a human-readable duration.
    
    Args:
        seconds (float): Duration in seconds
        
    Returns:
        str: Formatted duration string
    """
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"
