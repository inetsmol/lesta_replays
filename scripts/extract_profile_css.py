#!/usr/bin/env python3
"""
Извлекает CSS-правила для профильной статистики из минифицированного main.css.
Обрабатывает обычные правила и @media блоки с вложенными правилами.
"""

import re
import os

INPUT_CSS = os.path.expanduser(
    "~/PycharmProjects/lesta_replays/tanki_su/"
    "EHoTuk_TT0Jl0CKyH — статистика игрока «Мира танков»_files/main.css"
)
OUTPUT_CSS = os.path.expanduser(
    "~/PycharmProjects/lesta_replays/static/css/tanki-su-profile.css"
)

# Все нужные префиксы классов
TARGET_PREFIXES = [
    '.stats',
    '.all-stats',
    '.ico-ranks',
    '.ico-win-rate',
    '.ico-stats',
    '.ico-dmg-per-btl',
    '.ico-exp-per-btl',
    '.profile-grid',
    '.loading',
]


def selector_matches(selector: str) -> bool:
    """Проверяет, содержит ли селектор нужные классы."""
    for prefix in TARGET_PREFIXES:
        if prefix not in selector:
            continue

        if prefix == '.loading':
            # Для .loading — только .loading и .loading__active, не .loading-screen и т.п.
            if re.search(r'\.loading(?:__active)?(?=[^a-zA-Z0-9_-]|$)', selector):
                return True
            continue

        # Для остальных — любой класс, начинающийся с этого префикса
        escaped = re.escape(prefix)
        if re.search(escaped + r'(?=[_\s,:{>+~\[\].#\-]|$)', selector):
            return True

    return False


def parse_top_level_blocks(css: str):
    """
    Парсит CSS на блоки верхнего уровня.
    Возвращает список кортежей (selector, body, full_end_index, is_at_rule).
    """
    blocks = []
    i = 0
    n = len(css)

    while i < n:
        # Пропускаем пробелы
        while i < n and css[i] in ' \t\n\r':
            i += 1
        if i >= n:
            break

        # Читаем до первой {
        brace_start = css.find('{', i)
        if brace_start == -1:
            break

        selector = css[i:brace_start].strip()

        # Находим парную }
        depth = 0
        j = brace_start
        while j < n:
            if css[j] == '{':
                depth += 1
            elif css[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1

        body = css[brace_start + 1:j]
        is_at_rule = selector.startswith('@')

        blocks.append((selector, body, is_at_rule))
        i = j + 1

    return blocks


def parse_inner_rules(body: str):
    """Парсит вложенные правила внутри @media блока."""
    rules = []
    i = 0
    n = len(body)

    while i < n:
        while i < n and body[i] in ' \t\n\r':
            i += 1
        if i >= n:
            break

        brace_start = body.find('{', i)
        if brace_start == -1:
            break

        selector = body[i:brace_start].strip()

        depth = 0
        j = brace_start
        while j < n:
            if body[j] == '{':
                depth += 1
            elif body[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1

        rule_body = body[brace_start + 1:j]
        rules.append((selector, rule_body))
        i = j + 1

    return rules


def format_rule(selector: str, body: str, indent: str = '') -> str:
    """Форматирует CSS правило с отступами."""
    props = [p.strip() for p in body.split(';') if p.strip()]
    if not props:
        return f"{indent}{selector} {{}}\n"

    lines = [f"{indent}{selector} {{"]
    for prop in props:
        lines.append(f"{indent}    {prop};")
    lines.append(f"{indent}}}")
    return '\n'.join(lines) + '\n'


def main():
    print(f"Читаю CSS файл: {INPUT_CSS}")
    with open(INPUT_CSS, 'r', encoding='utf-8') as f:
        css = f.read()

    print(f"Размер файла: {len(css):,} байт")

    blocks = parse_top_level_blocks(css)
    print(f"Найдено блоков верхнего уровня: {len(blocks)}")

    output_parts = []
    matched_rules = 0
    matched_media = 0

    for selector, body, is_at_rule in blocks:
        if is_at_rule and selector.startswith('@media'):
            inner_rules = parse_inner_rules(body)
            matching_inner = []
            for inner_sel, inner_body in inner_rules:
                if selector_matches(inner_sel):
                    matching_inner.append((inner_sel, inner_body))

            if matching_inner:
                matched_media += 1
                parts = [f"{selector} {{"]
                for inner_sel, inner_body in matching_inner:
                    parts.append(format_rule(inner_sel, inner_body, indent='    '))
                    matched_rules += 1
                parts.append("}\n")
                output_parts.append('\n'.join(parts))

        elif not is_at_rule:
            if selector_matches(selector):
                matched_rules += 1
                output_parts.append(format_rule(selector, body))

    result = '\n'.join(output_parts)

    os.makedirs(os.path.dirname(OUTPUT_CSS), exist_ok=True)
    with open(OUTPUT_CSS, 'w', encoding='utf-8') as f:
        f.write("/* Extracted from tanki.su main.css - profile stats styles */\n\n")
        f.write(result)

    print(f"\nРезультаты:")
    print(f"  Обычных правил: {matched_rules}")
    print(f"  @media блоков: {matched_media}")
    print(f"  Размер результата: {len(result):,} байт")
    print(f"  Сохранено в: {OUTPUT_CSS}")

    # Показать уникальные селекторы для проверки
    print(f"\nПримеры найденных селекторов (первые 30):")
    count = 0
    for selector, body, is_at_rule in blocks:
        if not is_at_rule and selector_matches(selector):
            print(f"  {selector[:100]}")
            count += 1
            if count >= 30:
                break


if __name__ == '__main__':
    main()
