import threading
import queue
import time
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict
import os

logger = logging.getLogger(__name__)

@dataclass
class AudioTask:
    """Задача обработки аудиофайла."""
    task_id: str
    user_id: int
    audio_path: str
    original_filename: str
    created_at: datetime
    status: str = "pending"  # pending, processing, completed, failed
    result_files: Optional[Dict[str, str]] = None
    error_message: Optional[str] = None
    enhanced_audio_path: Optional[str] = None

class AudioProcessingQueue:
    """Менеджер очереди для обработки аудиофайлов."""
    
    def __init__(self, max_workers=2):
        self.task_queue = queue.Queue()
        self.tasks = {}  # task_id -> AudioTask
        self.user_tasks = {}  # user_id -> list of task_ids
        self.max_workers = max_workers
        self.workers = []
        self.running = False
        self.lock = threading.Lock()
        
    def start(self):
        """Запускает обработчики очереди."""
        if self.running:
            return
            
        self.running = True
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker,
                name=f"AudioWorker-{i+1}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
            
        logger.info(f"Started {self.max_workers} audio processing workers")
    
    def stop(self):
        """Останавливает обработчики очереди."""
        self.running = False
        logger.info("Stopping audio processing workers")
    
    def add_task(self, user_id: int, audio_path: str, original_filename: str) -> str:
        """Добавляет задачу в очередь."""
        task_id = f"{user_id}_{int(time.time() * 1000)}"
        
        task = AudioTask(
            task_id=task_id,
            user_id=user_id,
            audio_path=audio_path,
            original_filename=original_filename,
            created_at=datetime.now()
        )
        
        with self.lock:
            self.tasks[task_id] = task
            
            if user_id not in self.user_tasks:
                self.user_tasks[user_id] = []
            self.user_tasks[user_id].append(task_id)
        
        self.task_queue.put(task_id)
        logger.info(f"Added task {task_id} to queue for user {user_id}")
        
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[AudioTask]:
        """Получает статус задачи."""
        with self.lock:
            return self.tasks.get(task_id)
    
    def get_user_tasks(self, user_id: int) -> List[AudioTask]:
        """Получает все задачи пользователя."""
        with self.lock:
            if user_id not in self.user_tasks:
                return []
            
            return [self.tasks[task_id] for task_id in self.user_tasks[user_id] 
                   if task_id in self.tasks]
    
    def get_queue_info(self) -> Dict:
        """Получает информацию о состоянии очереди."""
        with self.lock:
            pending_count = sum(1 for task in self.tasks.values() 
                              if task.status == "pending")
            processing_count = sum(1 for task in self.tasks.values() 
                                 if task.status == "processing")
            
            return {
                "queue_size": self.task_queue.qsize(),
                "pending_tasks": pending_count,
                "processing_tasks": processing_count,
                "total_tasks": len(self.tasks)
            }
    
    def _worker(self):
        """Рабочий поток для обработки задач."""
        try:
            from bot import process_audio_file_sync
        except ImportError:
            logger.error("Failed to import process_audio_file_sync")
            return
        
        while self.running:
            try:
                # Получаем задачу из очереди с таймаутом
                task_id = self.task_queue.get(timeout=1.0)
                
                with self.lock:
                    if task_id not in self.tasks:
                        continue
                    
                    task = self.tasks[task_id]
                    task.status = "processing"
                
                logger.info(f"Worker {threading.current_thread().name} processing task {task_id}")
                
                try:
                    # Обрабатываем аудиофайл
                    result = process_audio_file_sync(
                        task.user_id,
                        task.audio_path,
                        task.original_filename
                    )
                    
                    with self.lock:
                        task.status = "completed"
                        task.result_files = result.get("files", {})
                        task.enhanced_audio_path = result.get("enhanced_audio_path")
                        
                    logger.info(f"Task {task_id} completed successfully")
                    
                    # Отправляем результат пользователю
                    self._send_result_to_user(task)
                    
                except Exception as e:
                    logger.error(f"Error processing task {task_id}: {str(e)}")
                    
                    with self.lock:
                        task.status = "failed"
                        task.error_message = str(e)
                    
                    # Отправляем сообщение об ошибке
                    self._send_error_to_user(task)
                
                finally:
                    self.task_queue.task_done()
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker error: {str(e)}")
    
    def _send_result_to_user(self, task: AudioTask):
        """Отправляет результат обработки пользователю."""
        from bot import bot
        
        try:
            user_id = task.user_id
            
            # Отправляем файлы транскрипции
            if task.result_files:
                if "txt" in task.result_files and os.path.exists(task.result_files["txt"]):
                    with open(task.result_files["txt"], 'rb') as f:
                        bot.send_document(
                            chat_id=user_id,
                            document=f,
                            caption=f"📄 Транскрипция: {task.original_filename} (.txt)"
                        )
                
                if "doc" in task.result_files and os.path.exists(task.result_files["doc"]):
                    with open(task.result_files["doc"], 'rb') as f:
                        bot.send_document(
                            chat_id=user_id,
                            document=f,
                            caption=f"📄 Транскрипция: {task.original_filename} (.doc)"
                        )
            
            # Отправляем улучшенное аудио если есть
            if task.enhanced_audio_path and os.path.exists(task.enhanced_audio_path):
                with open(task.enhanced_audio_path, 'rb') as f:
                    bot.send_audio(
                        chat_id=user_id,
                        audio=f,
                        caption=f"🎧 Улучшенное аудио: {task.original_filename}"
                    )
            
            # Отправляем уведомление о завершении
            bot.send_message(
                user_id,
                f"✅ Обработка завершена: {task.original_filename}\n"
                f"🕐 Время обработки: {datetime.now() - task.created_at}"
            )
            
        except Exception as e:
            logger.error(f"Error sending result to user {task.user_id}: {str(e)}")
    
    def _send_error_to_user(self, task: AudioTask):
        """Отправляет сообщение об ошибке пользователю."""
        from bot import bot
        
        try:
            bot.send_message(
                task.user_id,
                f"❌ Ошибка при обработке: {task.original_filename}\n"
                f"Причина: {task.error_message}"
            )
        except Exception as e:
            logger.error(f"Error sending error message to user {task.user_id}: {str(e)}")

# Глобальный экземпляр менеджера очереди
audio_queue = AudioProcessingQueue(max_workers=2)