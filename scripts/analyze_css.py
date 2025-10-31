#!/usr/bin/env python
"""
Скрипт для анализа CSS файла и поиска неиспользуемых стилей.
"""
import re
import sys
from pathlib import Path
from collections import defaultdict

# Добавляем корневую директорию проекта в путь
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def extract_css_selectors(css_content):
    """Извлекает CSS селекторы из файла."""
    selectors = set()

    # Удаляем комментарии
    css_content = re.sub(r'/\*.*?\*/', '', css_content, flags=re.DOTALL)

    # Ищем все селекторы (упрощенная версия)
    # Находим все блоки вида "селектор { ... }"
    pattern = r'([.#][\w-]+(?:\s*[>+~,]\s*[.#]?[\w-]+)*)\s*\{'
    matches = re.findall(pattern, css_content)

    for match in matches:
        # Разбиваем составные селекторы
        parts = re.split(r'[,\s>+~]+', match)
        for part in parts:
            if part and (part.startswith('.') or part.startswith('#')):
                selectors.add(part)

    return selectors


def extract_html_classes_and_ids(html_content):
    """Извлекает классы и ID из HTML шаблонов."""
    classes = set()
    ids = set()

    # Находим все class="..."
    class_matches = re.findall(r'class=["\']([^"\']+)["\']', html_content)
    for match in class_matches:
        classes.update(match.split())

    # Находим все id="..."
    id_matches = re.findall(r'id=["\']([^"\']+)["\']', html_content)
    for match in id_matches:
        ids.add(match)

    return classes, ids


def analyze_css_usage(css_file, template_dirs):
    """Анализирует использование CSS в HTML шаблонах."""
    print(f"Анализ файла: {css_file}")

    # Читаем CSS
    with open(css_file, 'r', encoding='utf-8') as f:
        css_content = f.read()

    css_selectors = extract_css_selectors(css_content)
    print(f"Найдено CSS селекторов: {len(css_selectors)}")

    # Собираем все HTML шаблоны
    html_files = []
    for template_dir in template_dirs:
        html_files.extend(Path(template_dir).rglob('*.html'))

    print(f"Найдено HTML файлов: {len(html_files)}")

    # Собираем классы и ID из всех HTML файлов
    all_classes = set()
    all_ids = set()

    for html_file in html_files:
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
                classes, ids = extract_html_classes_and_ids(html_content)
                all_classes.update(classes)
                all_ids.update(ids)
        except Exception as e:
            print(f"Ошибка при чтении {html_file}: {e}")

    print(f"Найдено уникальных классов в HTML: {len(all_classes)}")
    print(f"Найдено уникальных ID в HTML: {len(all_ids)}")

    # Проверяем какие селекторы не используются
    unused_selectors = set()
    used_selectors = set()

    for selector in css_selectors:
        if selector.startswith('.'):
            class_name = selector[1:]  # Убираем точку
            if class_name not in all_classes:
                unused_selectors.add(selector)
            else:
                used_selectors.add(selector)
        elif selector.startswith('#'):
            id_name = selector[1:]  # Убираем #
            if id_name not in all_ids:
                unused_selectors.add(selector)
            else:
                used_selectors.add(selector)

    return {
        'css_selectors': css_selectors,
        'used_selectors': used_selectors,
        'unused_selectors': unused_selectors,
        'html_classes': all_classes,
        'html_ids': all_ids,
    }


def analyze_css_structure(css_file):
    """Анализирует структуру CSS файла."""
    with open(css_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    stats = {
        'total_lines': len(lines),
        'comment_lines': 0,
        'empty_lines': 0,
        'layer_sections': defaultdict(int),
        'commented_code_blocks': [],
    }

    in_comment_block = False
    comment_start = None

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Пустые строки
        if not stripped:
            stats['empty_lines'] += 1
            continue

        # Многострочные комментарии
        if '/*' in line:
            in_comment_block = True
            comment_start = i
            stats['comment_lines'] += 1
            continue

        if '*/' in line:
            in_comment_block = False
            if comment_start:
                # Проверяем, закомментирован ли код
                block_lines = lines[comment_start-1:i]
                block_text = ''.join(block_lines)
                if '{' in block_text and '}' in block_text:
                    stats['commented_code_blocks'].append((comment_start, i))
            comment_start = None
            stats['comment_lines'] += 1
            continue

        if in_comment_block:
            stats['comment_lines'] += 1
            continue

        # Однострочные комментарии
        if stripped.startswith('//'):
            stats['comment_lines'] += 1
            continue

        # @layer директивы
        if '@layer' in line:
            match = re.search(r'@layer\s+(\w+)', line)
            if match:
                stats['layer_sections'][match.group(1)] += 1

    return stats


def main():
    css_file = BASE_DIR / 'static' / 'css' / 'input.css'
    template_dirs = [
        BASE_DIR / 'templates',
        BASE_DIR / 'replays' / 'templates',
    ]

    print("="*80)
    print("АНАЛИЗ СТРУКТУРЫ CSS")
    print("="*80)

    structure = analyze_css_structure(css_file)
    print(f"\nОбщие статистики:")
    print(f"  Всего строк: {structure['total_lines']}")
    print(f"  Комментариев: {structure['comment_lines']}")
    print(f"  Пустых строк: {structure['empty_lines']}")
    print(f"  Код: {structure['total_lines'] - structure['comment_lines'] - structure['empty_lines']}")

    print(f"\n@layer секции:")
    for layer, count in structure['layer_sections'].items():
        print(f"  @layer {layer}: {count} вхождений")

    if structure['commented_code_blocks']:
        print(f"\nНайдено закомментированных блоков кода: {len(structure['commented_code_blocks'])}")
        print("  Строки:", structure['commented_code_blocks'][:5])
        if len(structure['commented_code_blocks']) > 5:
            print(f"  ... и еще {len(structure['commented_code_blocks']) - 5}")

    print("\n" + "="*80)
    print("АНАЛИЗ ИСПОЛЬЗОВАНИЯ CSS")
    print("="*80)

    usage = analyze_css_usage(css_file, template_dirs)

    print(f"\nИспользуемые селекторы: {len(usage['used_selectors'])}")
    print(f"Неиспользуемые селекторы: {len(usage['unused_selectors'])}")

    if usage['unused_selectors']:
        print(f"\nПримеры неиспользуемых селекторов (первые 20):")
        for selector in sorted(list(usage['unused_selectors']))[:20]:
            print(f"  {selector}")

    # Классы из HTML, для которых нет стилей
    html_classes_set = {f".{c}" for c in usage['html_classes']}
    classes_without_styles = html_classes_set - usage['css_selectors']

    if classes_without_styles:
        print(f"\nКлассы в HTML без стилей в CSS (первые 20):")
        for cls in sorted(list(classes_without_styles))[:20]:
            print(f"  {cls}")

    print("\n" + "="*80)


if __name__ == '__main__':
    main()
