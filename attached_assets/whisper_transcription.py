import whisper
from pathlib import Path

def transcribe_audio(
    input_path,
    model_name: str = "medium",
    save_to_file: bool = True,
    output_path: str = "/Users/grigoryarzamastsev/Documents/Work/shopper-main/files"
) -> str:
    """
    Транскрибирует аудиофайл в текст с помощью Whisper.
    
    Параметры:
    input_path (str): Путь к входному аудиофайлу (mp3, wav и др.)
    model_name (str): Выбор модели (tiny, base, small, medium, large). По умолчанию 'base'
    save_to_file (bool): Сохранить ли результат в текстовый файл
    output_path (str): Путь для сохранения результата (если не указан, будет создан рядом с входным файлом)
    
    Возвращает:
    str: Транскрибированный текст
    """
    # Проверка существования файла
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Файл {input_path} не найден")

    # Загрузка модели
    model = whisper.load_model(model_name)

    # Загрузка и транскрипция аудио
    result = model.transcribe(input_path,  language="ru")

    # Получение текста
    text = str(result["text"])

    # Сохранение в файл при необходимости
    if save_to_file:
        output_path = f"{Path(output_path).stem}_transcript.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Транскрипция сохранена в: {output_path}")

    return text
