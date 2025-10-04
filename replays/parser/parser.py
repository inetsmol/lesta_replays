from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Tuple

from replays.parser.extractor import ExtractorV2

MAGIC = 0x11343212      # сигнатура формата в заголовке (первые 4 байта, LE)
SUPPORTED_VERSION = 2   # поддерживаемая версия файла

class ParseError(Exception):
    """Ошибка парсинга .mtreplay."""


@dataclass(frozen=True)
class HeaderV2:
    """Заголовок формата .mtreplay v2 (ровно 12 байт)."""
    magic: int        # сигнатура 0x11343212 (LE)
    version: int      # версия (ожидаем 2)
    len_first: int    # длина первого JSON-блока "{...}" в байтах (LE)

    @classmethod
    def parse(cls, data: bytes) -> "HeaderV2":
        """Разобрать первые 12 байт заголовка."""
        if len(data) < 12:
            raise ParseError("Файл слишком короткий для заголовка (ожидалось >= 12 байт).")
        magic, version, len_first = struct.unpack_from("<III", data, 0)
        # Проверки инвариантов формата
        if magic != MAGIC:
            raise ParseError(f"Неизвестная сигнатура: 0x{magic:08X} (ожидалась 0x11343212).")
        if version != SUPPORTED_VERSION:
            raise ParseError(f"Неподдерживаемая версия: {version} (поддерживается только 2).")
        if len_first == 0:
            raise ParseError("LEN_FIRST равен 0 — повреждённый файл.")
        return cls(magic=magic, version=version, len_first=len_first)


class Parser:
    """
    Простой парсер формата .mtreplay (v2).

    Файл имеет вид (смещения указаны в байтах, little-endian):
      0x00:4  MAGIC        -> 0x11343212
      0x04:4  VERSION      -> 2
      0x08:4  LEN_FIRST    -> длина первого JSON-объекта "{...}"
      0x0C:?  FIRST_JSON   -> ровно LEN_FIRST байт, начинается с '{' и заканчивается '}'
      ....:4  LEN_SECOND   -> длина второго JSON-массива "[...]"
      ....:?  SECOND_JSON  -> ровно LEN_SECOND байт, начинается с '[' и заканчивается ']'

    Результат: строка JSON строго вида:  [{...},[...]]
    Внутренние блоки возвращаются без переформатирования (байт-в-байт → через latin-1).
    """

    def parse(self, path: str | Path) -> str:
        """
        Прочитать .mtreplay и вернуть строку JSON вида:  [{...},[...]]

        :param path: путь к файлу .mtreplay
        :return: JSON-строка "пара" — первый объект и второй массив
        :raises ParseError: при несоответствии формату/длинам/краям блоков
        """
        data = Path(path).read_bytes()
        hdr = HeaderV2.parse(data)  # проверит сигнатуру/версию/len_first
        first_text, after_first = self._read_first_json(data, hdr.len_first)
        second_text, _ = self._read_second_json(data, after_first)
        # Склейка без модификации внутренних блоков
        return f"[{first_text},{second_text}]"

    # --- Вспомогательные методы ---

    @staticmethod
    def _read_first_json(data: bytes, len_first: int) -> Tuple[str, int]:
        """
        Извлечь первый JSON-объект "{...}" длиной len_first, начиная с offset=12.
        Возвращает (текст_первого_JSON, позиция_после_первого_блока).
        """
        start = 12
        end = start + len_first
        if end > len(data):
            raise ParseError("LEN_FIRST выходит за пределы файла.")
        chunk = data[start:end]
        # Быстрая валидация «краёв» без дорогого парсинга:
        if not (chunk.startswith(b"{") and chunk.endswith(b"}")):
            raise ParseError("Первый блок не выглядит как корректный JSON-объект по краям.")
        # Возвращаем текст 1:1 (latin-1 сохраняет байты без преобразований)
        return chunk.decode("latin-1"), end

    @staticmethod
    def _read_second_json(data: bytes, pos: int) -> Tuple[str, int]:
        """
        Извлечь второй JSON-массив "[...]", идущий после первых 4 байт длины.
        Возвращает (текст_второго_JSON, позиция_после_второго_блока).
        """
        if pos + 4 > len(data):
            raise ParseError("Файл обрезан — отсутствуют 4 байта LEN_SECOND.")
        (len_second,) = struct.unpack_from("<I", data, pos)
        if len_second == 0:
            raise ParseError("LEN_SECOND равен 0 — повреждённый файл.")
        start = pos + 4
        end = start + len_second
        if end > len(data):
            raise ParseError("LEN_SECOND выходит за пределы файла.")
        chunk = data[start:end]
        if not (chunk.startswith(b"[") and chunk.endswith(b"]")):
            raise ParseError("Второй блок не выглядит как корректный JSON-массив по краям.")
        return chunk.decode("latin-1"), end


# --- Пример использования ---
if __name__ == "__main__":
    file = "../../media/20251001_1833_intunion_Un04_Vickers_MBT_EXP_11_murovanka.mtreplay"
    file_name = "20251001_1833_intunion_Un04_Vickers_MBT_EXP_11_murovanka.mtreplay"
    p = Parser()
    data = p.parse(file)
    # print(data)
    replay_fields = ExtractorV2.extract_replay_fields_v2(data, file_name)
    # print(replay_fields.get('tank_tag'))
