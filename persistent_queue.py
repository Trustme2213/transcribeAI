"""
Persistent database-backed queue system for audio processing tasks.
"""

import logging
import threading
import time
import uuid
from datetime import datetime
from typing import List, Optional, Dict
from main import app, db, AudioTaskDB
import os

logger = logging.getLogger(__name__)

class PersistentAudioQueue:
    """Database-backed queue manager for audio processing tasks."""
    
    def __init__(self, max_workers=1):
        self.max_workers = max_workers
        self.running = False
        self.workers = []
        
    def start(self):
        """Start the queue processing workers."""
        if self.running:
            return
            
        self.running = True
        
        # Start worker threads
        for i in range(self.max_workers):
            worker_name = f"PersistentWorker-{i+1}"
            worker = threading.Thread(target=self._worker, name=worker_name, daemon=True)
            worker.start()
            self.workers.append(worker)
            
        logger.info(f"Started {self.max_workers} persistent audio processing workers")
        
        # Recover any interrupted tasks on startup
        self._recover_interrupted_tasks()
    
    def stop(self):
        """Stop the queue processing workers."""
        self.running = False
        logger.info("Stopped persistent audio processing workers")
    
    def add_task(self, user_id: int, audio_path: str, original_filename: str) -> str:
        """Add a new task to the persistent queue."""
        task_id = f"{user_id}_{int(datetime.now().timestamp() * 1000)}"
        
        with app.app_context():
            # Create database record
            db_task = AudioTaskDB(
                task_id=task_id,
                user_id=user_id,
                audio_path=audio_path,
                original_filename=original_filename,
                status='pending'
            )
            
            db.session.add(db_task)
            db.session.commit()
            
            logger.info(f"Added persistent task {task_id} to database for user {user_id}")
            
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get status of a specific task."""
        with app.app_context():
            task = AudioTaskDB.query.filter_by(task_id=task_id).first()
            if not task:
                return None
                
            return {
                'task_id': task.task_id,
                'user_id': task.user_id,
                'original_filename': task.original_filename,
                'status': task.status,
                'created_at': task.created_at,
                'error_message': task.error_message
            }
    
    def get_user_tasks(self, user_id: int) -> List[Dict]:
        """Get all tasks for a specific user."""
        with app.app_context():
            tasks = AudioTaskDB.query.filter_by(user_id=user_id).order_by(AudioTaskDB.created_at.desc()).all()
            
            return [{
                'task_id': task.task_id,
                'original_filename': task.original_filename,
                'status': task.status,
                'created_at': task.created_at,
                'error_message': task.error_message
            } for task in tasks]
    
    def get_queue_info(self) -> Dict:
        """Get current queue statistics."""
        with app.app_context():
            pending_count = AudioTaskDB.query.filter_by(status='pending').count()
            processing_count = AudioTaskDB.query.filter_by(status='processing').count()
            total_count = AudioTaskDB.query.count()
            
            return {
                'pending_tasks': pending_count,
                'processing_tasks': processing_count,
                'total_tasks': total_count
            }
    
    def _recover_interrupted_tasks(self):
        """Recover tasks that were interrupted during processing."""
        with app.app_context():
            from datetime import datetime, timedelta
            
            # Only recover tasks that were updated more than 10 minutes ago to avoid race conditions
            cutoff_time = datetime.utcnow() - timedelta(minutes=10)
            interrupted_tasks = AudioTaskDB.query.filter(
                AudioTaskDB.status == 'processing',
                AudioTaskDB.updated_at < cutoff_time
            ).all()
            
            for task in interrupted_tasks:
                task.status = 'pending'
                task.updated_at = datetime.utcnow()
                logger.info(f"Recovered interrupted task {task.task_id}")
            
            if interrupted_tasks:
                db.session.commit()
                logger.info(f"Recovered {len(interrupted_tasks)} interrupted tasks")
    
    def _worker(self):
        """Worker thread that processes tasks from the database."""
        worker_name = threading.current_thread().name
        logger.info(f"Started {worker_name}")
        
        while self.running:
            try:
                # Get the next pending task
                with app.app_context():
                    task = AudioTaskDB.query.filter_by(status='pending').order_by(AudioTaskDB.created_at.asc()).first()
                    
                    if not task:
                        time.sleep(2)  # No tasks available, wait
                        continue
                    
                    # Mark task as processing
                    task.status = 'processing'
                    task.updated_at = datetime.utcnow()
                    db.session.commit()
                    
                    task_info = {
                        'task_id': task.task_id,
                        'user_id': task.user_id,
                        'audio_path': task.audio_path,
                        'original_filename': task.original_filename
                    }
                
                logger.info(f"{worker_name} processing task {task_info['task_id']}")
                
                # Process the task
                try:
                    result_files = self._process_audio_task(task_info)
                    
                    # Update task as completed
                    with app.app_context():
                        task = AudioTaskDB.query.filter_by(task_id=task_info['task_id']).first()
                        if task:
                            task.status = 'completed'
                            task.updated_at = datetime.utcnow()
                            
                            if result_files:
                                task.result_txt_path = result_files.get('txt')
                                task.result_doc_path = result_files.get('doc')
                                task.enhanced_audio_path = result_files.get('enhanced_audio')
                            
                            db.session.commit()
                    
                    # Send results to user
                    self._send_result_to_user(task_info, result_files)
                    
                except Exception as e:
                    logger.error(f"Error processing task {task_info['task_id']}: {str(e)}")
                    
                    # Mark task as failed
                    with app.app_context():
                        task = AudioTaskDB.query.filter_by(task_id=task_info['task_id']).first()
                        if task:
                            task.status = 'failed'
                            task.error_message = str(e)
                            task.updated_at = datetime.utcnow()
                            db.session.commit()
                    
                    # Send error to user
                    self._send_error_to_user(task_info, str(e))
                
            except Exception as e:
                logger.error(f"{worker_name} error: {str(e)}")
                time.sleep(5)  # Wait before retrying
    
    def _process_audio_task(self, task_info: Dict) -> Optional[Dict]:
        """Process a single audio task."""
        try:
            # Import here to avoid circular imports
            from bot import process_audio_file_sync
            
            # Call the existing audio processing function
            process_audio_file_sync(
                user_id=task_info['user_id'],
                audio_path=task_info['audio_path'],
                original_filename=task_info['original_filename']
            )
            
            # Find result files by scanning the transcripts directory
            import glob
            import os
            from datetime import datetime
            
            user_id = task_info['user_id']
            result_files = {}
            
            # Look for transcription files created in the last few minutes
            transcript_pattern = f"transcripts/{user_id}_*_transcript.txt"
            
            # Find all matching transcript files
            txt_files = glob.glob(transcript_pattern)
            
            # Get the most recent file (within last 5 minutes)
            now = datetime.now()
            recent_files = []
            
            for file_path in txt_files:
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    time_diff = (now - file_time).total_seconds()
                    if time_diff < 300:  # Within 5 minutes
                        recent_files.append((file_path, file_time))
                except:
                    continue
            
            # Sort by creation time and get the most recent
            if recent_files:
                recent_files.sort(key=lambda x: x[1], reverse=True)
                newest_file = recent_files[0][0]
                result_files['txt'] = newest_file
                
                # Look for corresponding DOC file
                doc_file = newest_file.replace('.txt', '.doc')
                if os.path.exists(doc_file):
                    result_files['doc'] = doc_file
            
            # Look for enhanced audio files
            enhanced_pattern = f"temp_audio/{user_id}_*_enhanced.wav"
            enhanced_files = glob.glob(enhanced_pattern)
            
            for file_path in enhanced_files:
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    time_diff = (now - file_time).total_seconds()
                    if time_diff < 300:  # Within 5 minutes
                        result_files['enhanced_audio'] = file_path
                        break
                except:
                    continue
            
            logger.info(f"Found result files for task {task_info['task_id']}: {result_files}")
            return result_files if result_files else None
            
        except Exception as e:
            logger.error(f"Error in _process_audio_task: {str(e)}")
            raise
    
    def _send_result_to_user(self, task_info: Dict, result_files: Optional[Dict]):
        """Send processing results to user."""
        try:
            from bot import bot
            
            user_id = task_info['user_id']
            
            if result_files:
                # Send transcription files
                if 'txt' in result_files and os.path.exists(result_files['txt']):
                    with open(result_files['txt'], 'rb') as f:
                        bot.send_document(
                            chat_id=user_id,
                            document=f,
                            caption=f"✅ Транскрипция: {task_info['original_filename']} (.txt)"
                        )
                
                if 'doc' in result_files and os.path.exists(result_files['doc']):
                    with open(result_files['doc'], 'rb') as f:
                        bot.send_document(
                            chat_id=user_id,
                            document=f,
                            caption=f"✅ Транскрипция: {task_info['original_filename']} (.doc)"
                        )
                
                # Send enhanced audio if available
                if 'enhanced_audio' in result_files and os.path.exists(result_files['enhanced_audio']):
                    with open(result_files['enhanced_audio'], 'rb') as f:
                        bot.send_audio(
                            chat_id=user_id,
                            audio=f,
                            caption=f"🎵 Улучшенное аудио: {task_info['original_filename']}"
                        )
            
            # Send completion notification
            bot.send_message(
                chat_id=user_id,
                text=f"✅ Обработка завершена: {task_info['original_filename']}\n"
                     f"🆔 Задача: {task_info['task_id'][:12]}..."
            )
            
        except Exception as e:
            logger.error(f"Error sending results to user {task_info['user_id']}: {str(e)}")
    
    def _send_error_to_user(self, task_info: Dict, error_message: str):
        """Send error notification to user."""
        try:
            from bot import bot
            
            bot.send_message(
                chat_id=task_info['user_id'],
                text=f"❌ Ошибка при обработке: {task_info['original_filename']}\n"
                     f"🆔 Задача: {task_info['task_id'][:12]}...\n"
                     f"📝 Ошибка: {error_message}"
            )
            
        except Exception as e:
            logger.error(f"Error sending error notification to user {task_info['user_id']}: {str(e)}")

# Global queue instance
persistent_audio_queue = PersistentAudioQueue(max_workers=1)