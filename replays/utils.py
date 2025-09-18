import json
from typing import Optional, Dict


def extract_all_json_from_mtreplay(file_path: str) -> str:
    """Извлекает все JSON данные из .mtreplay файла и объединяет их в один JSON"""

    with open(file_path, 'rb') as f:
        content = f.read()

    # Декодируем как UTF-8 с игнорированием ошибок
    text = content.decode('utf-8', errors='ignore')

    combined_data = {}
    pos = 0

    while pos < len(text):
        # Ищем начало JSON блока
        start = text.find('{', pos)
        if start == -1:
            break

        # Подсчитываем скобки для определения конца блока
        brace_count = 0
        end = start
        in_string = False
        escape = False

        for i in range(start, len(text)):
            char = text[i]

            if escape:
                escape = False
                continue

            if char == '\\' and in_string:
                escape = True
                continue

            if char == '"' and not escape:
                in_string = not in_string
                continue

            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break

        if brace_count == 0:  # Нашли полный JSON блок
            json_text = text[start:end]
            try:
                parsed_json = json.loads(json_text)
                # Объединяем все данные в один словарь
                combined_data.update(parsed_json)
            except json.JSONDecodeError:
                pass  # Пропускаем невалидные JSON блоки

        pos = end if brace_count == 0 else start + 1

    return json.dumps(combined_data, ensure_ascii=False, indent=2)


def get_tank_info_by_type_descr(type_descr: int) -> Optional[Dict[str, str]]:
    """
    Получает информацию о танке по typeCompDescr.
    Пока заглушка - в будущем можно создать маппинг или API.
    """
    # Заглушка для определения типа танка по typeCompDescr
    # В реальном проекте здесь была бы логика сопоставления
    # с базой данных Tank или внешним API

    tank_types = {
        'lightTank': 'Лёгкий танк',
        'mediumTank': 'Средний танк',
        'heavyTank': 'Тяжёлый танк',
        'AT-SPG': 'ПТ-САУ',
        'SPG': 'САУ',
    }

    # Пока возвращаем неизвестный танк
    return {
        'name': 'Неизвестный танк',
        'type': 'unknown',
        'level': 1,
    }
