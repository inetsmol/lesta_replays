#!/usr/bin/env python
"""
Скрипт для поиска закомментированных блоков кода в CSS.
"""
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
css_file = BASE_DIR / 'static' / 'css' / 'input.css'

with open(css_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

in_comment = False
comment_start = None
comment_blocks = []
current_block = []

for i, line in enumerate(lines, 1):
    if '/*' in line:
        in_comment = True
        comment_start = i
        current_block = [line]
    elif in_comment:
        current_block.append(line)
        if '*/' in line:
            in_comment = False
            # Проверяем, есть ли код в комментарии
            block_text = ''.join(current_block)
            # Ищем признаки CSS кода
            if ('{' in block_text and '}' in block_text) or \
               re.search(r'\.[a-zA-Z-]+\s*\{', block_text) or \
               re.search(r'#[a-zA-Z-]+\s*\{', block_text):
                comment_blocks.append({
                    'start': comment_start,
                    'end': i,
                    'lines': len(current_block),
                    'preview': ''.join(current_block[:3])
                })
            current_block = []

print(f"Найдено закомментированных блоков с кодом: {len(comment_blocks)}\n")

total_commented_lines = 0
for block in comment_blocks:
    total_commented_lines += block['lines']
    print(f"Строки {block['start']}-{block['end']} ({block['lines']} строк):")
    print(block['preview'][:200])
    print("-" * 80)

print(f"\nВсего закомментированных строк с кодом: {total_commented_lines}")
print(f"Это {total_commented_lines / len(lines) * 100:.1f}% от всего файла")
