import os
import logging
from yandex_cloud_ml_sdk import YCloudML

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default credentials (can be overridden with environment variables)
DEFAULT_FOLDER_ID = os.environ.get("YANDEX_FOLDER_ID", "b1g7chuh6anjq5op0j2f")
DEFAULT_API_KEY = os.environ.get("YANDEX_API_KEY", "AQVN0qBlkT8mXWUftoFvng5VemxBTIA73V8M2G-R")

def ya_request_1(text):
    """
    Первый запрос к YandexGPT: форматирование диалога.
    
    Args:
        text (str): Исходный текст транскрипции
        
    Returns:
        str: Отформатированный диалог
    """
    try:
        logger.info("Making first YandexGPT request for dialog formatting")
        
        sdk = YCloudML(
            folder_id=DEFAULT_FOLDER_ID, 
            auth=DEFAULT_API_KEY
        )

        model = sdk.models.completions("yandexgpt", model_version="rc")
        model = model.configure(temperature=0.12)
        
        result = model.run(
            [
                {"role": "system", "text": "Тебе передана транскрипция диалога. Преобразуй в диалог вида : Продавец: ... Покупатель ...). Исправь очевидные ошибки транскрипции. Уточни реплики для улучшения читаемости, без изменения смысла."},
                {
                    "role": "user",
                    "text": text,
                },
            ]
        )
        
        # Обрабатываем структуру ответа YandexGPT
        if hasattr(result, 'result') and result.result.alternatives:
            first_alternative = result.result.alternatives[0]
            if hasattr(first_alternative, 'message'):
                return first_alternative.message.text
        elif hasattr(result, 'text'):
            return result.text

        return "Не удалось обработать ответ"
        
    except Exception as e:
        logger.error(f"Error in first YandexGPT request: {str(e)}")
        return f"Ошибка обработки: {str(e)}"

def ya_request_2(text):
    """
    Второй запрос к YandexGPT: дополнительный анализ диалога.
    
    Args:
        text (str): Отформатированный диалог
        
    Returns:
        str: Результат анализа диалога
    """
    try:
        logger.info("Making second YandexGPT request for dialog analysis")
        
        sdk = YCloudML(
            folder_id=DEFAULT_FOLDER_ID, 
            auth=DEFAULT_API_KEY
        )

        model = sdk.models.completions("yandexgpt", model_version="rc")
        model = model.configure(temperature=0.2)
        
        # Если текст слишком длинный, обрежем его
        max_length = 30000  # Примерное ограничение токенов
        if len(text) > max_length:
            logger.warning(f"Request text too long ({len(text)} chars), truncating to {max_length}")
            text = text[:max_length]
        
        result = model.run(
            [
                {"role": "system", "text": 
                """
                Тебе передан отформатированный диалог между продавцом и покупателем. 
                Проанализируй диалог и выдели основные моменты: 
                1. Качество обслуживания
                2. Соблюдение скриптов продаж/обслуживания
                3. Выявление потребностей клиента
                4. Работа с возражениями
                5. Общее впечатление от диалога
                
                Старайся быть объективным и рассматривать ситуацию с разных сторон.
                """},
                {
                    "role": "user",
                    "text": text,
                },
            ]
        )

        # Обрабатываем структуру ответа YandexGPT
        if hasattr(result, 'result') and result.result.alternatives:
            first_alternative = result.result.alternatives[0]
            if hasattr(first_alternative, 'message'):
                return first_alternative.message.text
        elif hasattr(result, 'text'):
            return result.text

        return "Не удалось обработать ответ"
        
    except Exception as e:
        logger.error(f"Error in second YandexGPT request: {str(e)}")
        return f"Ошибка обработки: {str(e)}"

def process_text_in_chunks_for_formatting(text, chunk_size=5000, overlap=500):
    """
    Обрабатывает большой текст по частям для форматирования через YandexGPT.
    
    Args:
        text (str): Исходная транскрипция для форматирования
        chunk_size (int): Размер каждого куска текста
        overlap (int): Размер перекрытия между кусками
        
    Returns:
        str: Отформатированный текст, объединенный из всех частей
    """
    logger.info(f"Processing text in chunks for formatting (total length: {len(text)} chars)")
    
    # Разбиваем текст на части
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Ищем конец предложения в диапазоне перекрытия
        if end < len(text) and end - start > overlap:
            # Пытаемся найти точку, окончание предложения
            for sentence_end in ['. ', '! ', '? ']:
                last_sentence = text[end-overlap:end].rfind(sentence_end)
                if last_sentence != -1:
                    end = end - overlap + last_sentence + 2  # +2 для включения знака и пробела
                    break
        
        chunks.append(text[start:end])
        start = end - overlap if end - start > overlap else end
    
    logger.info(f"Text split into {len(chunks)} chunks for formatting")
    
    # Обрабатываем каждую часть
    formatted_chunks = []
    
    for i, chunk in enumerate(chunks, 1):
        logger.info(f"Formatting chunk {i}/{len(chunks)}")
        
        # Форматируем часть текста
        formatted_chunk = ya_request_1(chunk)
        formatted_chunks.append(formatted_chunk)
    
    # Объединяем отформатированные части
    result = ""
    
    for i, chunk in enumerate(formatted_chunks):
        # Для первого куска берем всё
        if i == 0:
            result = chunk
        else:
            # Для последующих кусков ищем место, где они начинают перекрываться
            # с предыдущим результатом, чтобы избежать дублирования реплик
            
            # Ищем последние две реплики предыдущего куска
            prev_parts = result.split("\n")
            last_roles = []
            
            for j in range(len(prev_parts) - 1, -1, -1):
                line = prev_parts[j].strip()
                if line and ("Продавец:" in line or "Покупатель:" in line or "Клиент:" in line or "Оператор:" in line):
                    last_roles.append(line)
                    if len(last_roles) >= 2:
                        break
            
            # Ищем эти же реплики в текущем куске
            for role in last_roles:
                # Получаем только начало реплики (роль + первые несколько слов)
                role_start = role.split(":")
                if len(role_start) >= 2:
                    role_prefix = role_start[0] + ":" + role_start[1][:20]
                    if role_prefix in chunk:
                        # Нашли перекрытие, обрезаем текущий кусок до этого места
                        overlap_index = chunk.find(role_prefix)
                        chunk = chunk[overlap_index:]
                        break
            
            # Добавляем обработанный кусок к результату
            result += "\n" + chunk
    
    return result

# Сохраняем этот метод на случай, если захотим использовать его в будущем
def process_text_in_chunks(text, chunk_size=5000, overlap=500):
    """
    Обрабатывает большой текст по частям для анализа YandexGPT.
    
    Args:
        text (str): Полный текст для анализа
        chunk_size (int): Размер каждого куска текста
        overlap (int): Размер перекрытия между кусками
        
    Returns:
        str: Объединенные результаты анализа
    """
    logger.info(f"Processing text in chunks (total length: {len(text)} chars)")
    
    # Разбиваем текст на части
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Ищем конец предложения в диапазоне перекрытия
        if end < len(text) and end - start > overlap:
            # Пытаемся найти точку, окончание предложения
            for sentence_end in ['. ', '! ', '? ']:
                last_sentence = text[end-overlap:end].rfind(sentence_end)
                if last_sentence != -1:
                    end = end - overlap + last_sentence + 2  # +2 для включения знака и пробела
                    break
        
        chunks.append(text[start:end])
        start = end - overlap if end - start > overlap else end
    
    logger.info(f"Text split into {len(chunks)} chunks")
    
    # Обрабатываем каждую часть
    all_text = []
    
    for i, chunk in enumerate(chunks, 1):
        logger.info(f"Processing chunk {i}/{len(chunks)}")
        
        # Анализируем часть текста
        result = ya_request_2(chunk)
        all_text.append(result)
    
    # Объединяем все части
    return "\n\n".join(all_text)