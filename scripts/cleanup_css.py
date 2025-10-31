#!/usr/bin/env python
"""
Скрипт для очистки CSS файла от закомментированного кода и неиспользуемых стилей.
Создает резервную копию перед изменениями.
"""
import re
import shutil
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
css_file = BASE_DIR / 'static' / 'css' / 'input.css'


def remove_commented_css_code(content):
    """Удаляет закомментированные блоки CSS кода, сохраняя описательные комментарии."""
    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Проверяем начало многострочного комментария
        if '/*' in line and '*/' not in line:
            # Собираем весь блок комментария
            comment_block = [line]
            i += 1
            while i < len(lines) and '*/' not in lines[i]:
                comment_block.append(lines[i])
                i += 1
            if i < len(lines):
                comment_block.append(lines[i])

            block_text = '\n'.join(comment_block)

            # Проверяем, является ли это закомментированным CSS кодом
            # Признаки CSS кода:
            # 1. Содержит селекторы с фигурными скобками
            # 2. Содержит CSS свойства (property: value;)
            # 3. Не является описательным комментарием

            is_code = False

            # Ищем признаки CSS кода
            if re.search(r'/\*\s*\.[a-zA-Z-]+.*\{', block_text):  # .class {
                is_code = True
            elif re.search(r'/\*\s*#[a-zA-Z-]+.*\{', block_text):  # #id {
                is_code = True
            elif re.search(r':\s*[^;]+;', block_text) and '{' in block_text:  # property: value;
                is_code = True
            elif block_text.count('{') > 1 and block_text.count('}') > 1:
                is_code = True

            # Сохраняем только описательные комментарии
            if not is_code:
                result.extend(comment_block)
            else:
                print(f"Удален закомментированный код на строках {i-len(comment_block)+1}-{i}")

            i += 1
            continue

        # Однострочные комментарии с кодом
        if re.match(r'^\s*/\*.*\{.*\*/', line) or re.match(r'^\s*/\*.*:.*;\s*\*/', line):
            # Это закомментированная строка CSS кода
            print(f"Удалена закомментированная строка {i+1}: {line[:60]}")
            i += 1
            continue

        result.append(line)
        i += 1

    return '\n'.join(result)


def remove_empty_lines_excess(content):
    """Удаляет избыточные пустые строки (более 2 подряд)."""
    lines = content.split('\n')
    result = []
    empty_count = 0

    for line in lines:
        if not line.strip():
            empty_count += 1
            if empty_count <= 2:
                result.append(line)
        else:
            empty_count = 0
            result.append(line)

    return '\n'.join(result)


def analyze_file_structure(content):
    """Анализирует структуру файла."""
    lines = content.split('\n')

    stats = {
        'total_lines': len(lines),
        'empty_lines': sum(1 for line in lines if not line.strip()),
        'comment_lines': 0,
        'code_lines': 0,
    }

    in_comment = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if '/*' in line and '*/' not in line:
            in_comment = True
            stats['comment_lines'] += 1
        elif in_comment:
            stats['comment_lines'] += 1
            if '*/' in line:
                in_comment = False
        elif '/*' in line and '*/' in line:
            stats['comment_lines'] += 1
        else:
            stats['code_lines'] += 1

    return stats


def main():
    print("="*80)
    print("ОЧИСТКА CSS ФАЙЛА")
    print("="*80)

    # Читаем исходный файл
    with open(css_file, 'r', encoding='utf-8') as f:
        original_content = f.read()

    print(f"\nИсходный файл: {css_file}")
    original_stats = analyze_file_structure(original_content)
    print(f"Всего строк: {original_stats['total_lines']}")
    print(f"  - Код: {original_stats['code_lines']}")
    print(f"  - Комментарии: {original_stats['comment_lines']}")
    print(f"  - Пустые: {original_stats['empty_lines']}")

    # Создаем резервную копию
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = css_file.with_suffix(f'.{timestamp}.backup.css')
    shutil.copy2(css_file, backup_file)
    print(f"\n✓ Создана резервная копия: {backup_file}")

    # Очищаем файл
    print("\nОчистка файла...")
    cleaned_content = remove_commented_css_code(original_content)
    cleaned_content = remove_empty_lines_excess(cleaned_content)

    # Анализируем результат
    cleaned_stats = analyze_file_structure(cleaned_content)
    print(f"\nРезультат:")
    print(f"Всего строк: {cleaned_stats['total_lines']} (было {original_stats['total_lines']})")
    print(f"  - Код: {cleaned_stats['code_lines']} (было {original_stats['code_lines']})")
    print(f"  - Комментарии: {cleaned_stats['comment_lines']} (было {original_stats['comment_lines']})")
    print(f"  - Пустые: {cleaned_stats['empty_lines']} (было {original_stats['empty_lines']})")

    lines_removed = original_stats['total_lines'] - cleaned_stats['total_lines']
    print(f"\nУдалено строк: {lines_removed} ({lines_removed / original_stats['total_lines'] * 100:.1f}%)")

    # Сохраняем очищенный файл
    with open(css_file, 'w', encoding='utf-8') as f:
        f.write(cleaned_content)

    print(f"\n✓ Файл сохранен: {css_file}")
    print(f"\nДля отката изменений используйте:")
    print(f"  cp {backup_file} {css_file}")

    print("\n" + "="*80)


if __name__ == '__main__':
    main()
