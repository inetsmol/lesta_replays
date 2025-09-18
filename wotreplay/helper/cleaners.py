from __future__ import annotations

from typing import Any, Iterable, Mapping, Iterator
from json import JSONDecoder, dumps


class Parser:
    """
    Парсер реплея, формирующий единый словарь `replay_data` без разделения
    на 'metadata'/'battle'.

    Политика слияния:
      • dict + dict  -> рекурсивно сливаются по ключам;
      • list + list  -> конкатенируются (порядок сохранён);
      • иные типы    -> значение из более позднего объекта перезаписывает предыдущее.

    Пример использования:
        parser = Parser(file_content)
        data_dict = parser.replay_data   # единый dict
        data_json = parser.to_json()     # JSON-строка (компактная)
    """

    def __init__(self, file_content: str):
        """
        :param file_content: Исходный текст, внутри которого содержатся JSON-объекты.
        """
        self.file_content = file_content

        # Извлекаем все JSON-объекты (ТОЛЬКО объекты) из строки.
        # Если встречаются не-объекты (массивы/строки), они пропускаются.
        objects: list[dict[str, Any]] = list(self.__extract_json_objects(file_content))

        # Единая структура: глубокое слияние всех найденных объектов в один словарь.
        merged: dict[str, Any] = {}
        for obj in objects:
            self._deep_merge(merged, obj)
        self.replay_data: dict[str, Any] = merged  # <- ОДИН общий словарь

    def to_json(self) -> str:
        """
        Сериализует `replay_data` в компактную JSON-строку.
        Для высокой производительности можно заменить на `orjson.dumps(...).decode()`.
        """
        return dumps(self.replay_data, ensure_ascii=False, separators=(",", ":"))

    # -------------------- ВНУТРЕННИЕ МЕТОДЫ --------------------

    @staticmethod
    def _deep_merge(dst: dict[str, Any], src: Mapping[str, Any]) -> dict[str, Any]:
        """
        Рекурсивное слияние словаря `src` в `dst`.

        :param dst: Целевой словарь (модифицируется на месте).
        :param src: Источник, чьи значения добавляются/сливаются в `dst`.
        :return: Ссылка на модифицированный `dst`.
        """
        for key, sval in src.items():
            dval = dst.get(key)

            # Случай dict + dict: углубляемся рекурсивно
            if isinstance(sval, dict) and isinstance(dval, dict):
                Parser._deep_merge(dval, sval)

            # Случай list + list: конкатенация списков
            elif isinstance(sval, list) and isinstance(dval, list):
                dval.extend(sval)

            else:
                # Иные типы или несовпадение типов: «последний выигрывает»
                dst[key] = sval
        return dst

    @staticmethod
    def __extract_json_objects(text: str, decoder: JSONDecoder | None = None) -> Iterator[dict[str, Any]]:
        """
        Ищет и по одному отдаёт JSON-ОБЪЕКТЫ (top-level `{...}`) внутри произвольного текста.

        Ограничения:
          - Не извлекает массивы/строки/числа вне объекта.
          - Невалидные фрагменты пропускаются с продвижением на 1 символ.
        """
        decoder = decoder or JSONDecoder()
        pos = 0
        while True:
            start = text.find("{", pos)
            if start == -1:
                break
            try:
                # Пытаемся распарсить объект начиная с '{'
                result, end = decoder.raw_decode(text[start:])
                # Отфильтровываем только объекты (dict)
                if isinstance(result, dict):
                    yield result
                # Сдвигаем позицию до конца successfully распознанного блока
                pos = start + end
            except ValueError:
                # Не получилось — двигаемся на символ вперёд и пробуем снова
                pos = start + 1
