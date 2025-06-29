from yandex_cloud_ml_sdk import YCloudML

def ya_request_1(text):
    sdk = YCloudML(
        folder_id="b1g7chuh6anjq5op0j2f", auth="AQVN0qBlkT8mXWUftoFvng5VemxBTIA73V8M2G-R"
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

def ya_request_2(text, questions):
    sdk = YCloudML(
        folder_id="b1g7chuh6anjq5op0j2f", auth="AQVN0qBlkT8mXWUftoFvng5VemxBTIA73V8M2G-R"
    )

    model = sdk.models.completions("yandexgpt", model_version="rc")
    model = model.configure(temperature=0.2)
    full_text = text + questions
    print(full_text)
    result = model.run(
        [
            {"role": "system", "text": 
            """
            У меня есть готовый диалог и список вопросов. Твоя задача на основании диалога вернуть развернутые ответы на вопросы в формате json. Ключ - id вопроса, значение - ответ на вопрос.
            Пример: 
            {
            "133224414": "Да, говорит здравствуйте", 
            "123321223": "Нет, он был вежлив"
            }
            Если ты не можешь дать ответ из контекста - нужно прислать в значении null
            """},
            {
                "role": "user",
                "text": full_text,
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