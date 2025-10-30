# Tailwind CSS - Быстрый старт миграции

## 📋 Краткое резюме

Этот документ содержит пошаговую инструкцию для начала работы с миграцией на Tailwind CSS.

---

## 🚀 Шаг 1: Установка и настройка (30 минут)

### 1.1 Установить Node.js зависимости

```bash
cd /Users/igor_bocharov/PycharmProjects/lesta_replays

# Создать package.json если его нет
npm init -y

# Установить Tailwind и плагины
npm install -D tailwindcss@latest
npm install -D @tailwindcss/forms @tailwindcss/typography
```

### 1.2 Создать конфигурационные файлы

**tailwind.config.js**:
```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './replays/templates/**/*.html',
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#0b0b0b',
          800: '#141414',
          700: '#1a1a1a',
        },
        accent: {
          500: '#c0392b',
          600: '#e74c3c',
        },
        gold: '#f7c76b',
        border: '#292929',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
```

**static/css/input.css**:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer components {
  .btn {
    @apply inline-flex items-center justify-center px-4 py-2 rounded-lg font-medium transition-colors;
  }
  .btn--accent {
    @apply bg-accent-500 hover:bg-accent-600 text-white;
  }
  .btn--ghost {
    @apply border border-border hover:bg-dark-700 text-gray-300 hover:text-white;
  }
  .card {
    @apply bg-dark-800 border border-border rounded-xl p-6;
  }
}
```

**package.json** (добавить scripts):
```json
{
  "scripts": {
    "build:css": "tailwindcss -i ./static/css/input.css -o ./static/css/output.css --minify",
    "watch:css": "tailwindcss -i ./static/css/input.css -o ./static/css/output.css --watch"
  }
}
```

### 1.3 Собрать CSS

```bash
# Для разработки (с watch mode)
npm run watch:css

# Для продакшна (минифицированный)
npm run build:css
```

### 1.4 Обновить base.html

```html
<!-- templates/base.html -->

<!-- УБРАТЬ эти строки: -->
<!-- <link rel="stylesheet" href="{% static 'css/site.css' %}"> -->
<!-- <link rel="stylesheet" href="{% static 'css/sidebar.css' %}"> -->
<!-- <link rel="stylesheet" href="{% static 'css/dev_banner.css' %}"> -->
<!-- <link rel="stylesheet" href="{% static 'css/alert_modal.css' %}"> -->

<!-- ДОБАВИТЬ вместо них: -->
<link rel="stylesheet" href="{% static 'css/output.css' %}">
```

✅ **Проверка**: Запусти сервер и убедись, что страница загружается без ошибок.

---

## 🎯 Шаг 2: Миграция по приоритету

### Приоритет 1: Базовые компоненты (1-2 дня)

#### ✅ Navbar уже готов
`templates/includes/_navbar.html` - уже использует Tailwind, только добавить mobile menu

#### 🔨 Задача: Добавить мобильное меню

```html
<!-- Добавить в начало <body> в base.html -->
<div x-data="{ mobileMenuOpen: false }">
  <!-- Navbar внутри этого контейнера -->
</div>
```

Подробнее: см. `TAILWIND_EXAMPLES.md`, раздел "Мобильное меню"

---

### Приоритет 2: Список реплеев (2-3 дня)

**Файл**: `replays/templates/replays/list.html`

#### Основные изменения:

1. **Удалить** подключение `wot_record_skin.css`:
```html
<!-- УБРАТЬ: -->
<!-- <link rel="stylesheet" href="{% static 'css/wot_record_skin.css' %}"> -->
```

2. **Заменить** карточки реплеев на Tailwind классы:
   - См. полный пример в `TAILWIND_EXAMPLES.md`, раздел "Карточка реплея"

3. **Сделать адаптивной** панель сортировок:
```html
<!-- До: -->
<div class="sorters grid grid-cols-5 gap-2">

<!-- После: -->
<div class="sorters grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
```

4. **Протестировать** на разных разрешениях:
   - 375px (iPhone SE)
   - 768px (iPad)
   - 1024px+ (Desktop)

✅ **Проверка**: Все карточки корректно отображаются на мобильных и десктопе

---

### Приоритет 3: Детали реплея (3-4 дня)

**Файл**: `replays/templates/replays/detail.html`

⚠️ **ВАЖНО**: Эта страница НЕ адаптивная! Только horizontal scroll.

#### Основные изменения:

1. **Удалить** подключение `replay-detail.css`:
```html
<!-- УБРАТЬ: -->
<!-- <link rel="stylesheet" href="{% static 'css/replay-detail.css' %}"> -->
```

2. **Обернуть весь контент** в fixed-width контейнер:
```html
<div class="w-screen overflow-x-auto">
  <div class="min-w-[1003px] max-w-[1003px] mx-auto px-4">
    <!-- Весь контент страницы -->
  </div>
</div>
```

3. **НЕ МЕНЯТЬ** размеры таблиц и статистики - оставить фиксированными

4. **Протестировать** горизонтальный скролл на мобильных

✅ **Проверка**: На мобильных появляется горизонтальный скролл, таблицы не ломаются

---

### Приоритет 4: Фильтры (1-2 дня)

**Файл**: `replays/templates/replays/filters.html`

#### Основные изменения:

1. **Удалить** подключение `replays_filters.css`

2. **Адаптивная сетка** полей:
```html
<!-- До: -->
<div class="form-row grid-3">

<!-- После: -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
```

3. **Touch-friendly** чекбоксы (минимум 44px)

✅ **Проверка**: Форма удобна на мобильных, все элементы кликабельны

---

## 📱 Шаг 3: Тестирование адаптивности

### Инструменты

1. **Chrome DevTools**:
   - `Cmd+Opt+I` → Device Toolbar (`Cmd+Shift+M`)
   - Тестировать на: iPhone SE, iPad, Responsive

2. **Firefox DevTools**:
   - `Cmd+Opt+M` → Responsive Design Mode

3. **Реальные устройства** (если доступны):
   - iPhone
   - iPad
   - Android телефон

### Чек-лист тестирования

Для каждой страницы:

- [ ] **375px** (iPhone SE) - все читаемо, нет overflow
- [ ] **768px** (iPad) - layout адаптирован
- [ ] **1024px+** (Desktop) - как раньше
- [ ] Все кнопки кликабельны (минимум 44x44px)
- [ ] Текст читаем (минимум 12px на мобильных)
- [ ] Изображения не искажены
- [ ] Формы заполняемы
- [ ] Модальные окна не обрезаны

---

## 🎨 Шаг 4: Удаление legacy CSS

**ТОЛЬКО ПОСЛЕ ПОЛНОЙ МИГРАЦИИ И ТЕСТИРОВАНИЯ!**

```bash
# Создать backup
mkdir -p backups/css
cp -r static/css/*.css backups/css/

# Удалить старые файлы
rm static/css/site.css
rm static/css/wot_record_skin.css
rm static/css/replay-detail.css
rm static/css/replays_filters.css
rm static/css/sidebar.css
rm static/css/dev_banner.css
rm static/css/alert_modal.css

# Оставить только:
# - static/css/input.css (исходник)
# - static/css/output.css (скомпилированный)
```

✅ **Проверка**:
```bash
# Убедись что в base.html только одна ссылка на CSS
grep -n "\.css" templates/base.html
```

---

## 📊 Метрики прогресса

### Страницы

- [ ] `base.html` - базовый layout
- [ ] `_navbar.html` - навигация
- [ ] `_sidebar.html` - боковая панель
- [ ] `_footer.html` - подвал
- [ ] `list.html` - список реплеев ⭐ **ПРИОРИТЕТ**
- [ ] `detail.html` - детали реплея ⭐ **ПРИОРИТЕТ**
- [ ] `filters.html` - фильтры
- [ ] `login.html` - вход
- [ ] `signup.html` - регистрация
- [ ] `about.html` - о проекте
- [ ] `404.html`, `500.html` - ошибки

### CSS файлы для удаления

- [ ] `site.css` - основные стили
- [ ] `wot_record_skin.css` - карточки реплеев
- [ ] `replay-detail.css` - детали реплея
- [ ] `replays_filters.css` - фильтры
- [ ] `sidebar.css` - сайдбар
- [ ] `dev_banner.css` - dev баннер
- [ ] `alert_modal.css` - модальные окна

---

## 🔧 Команды для работы

```bash
# Запустить Django сервер
python manage.py runserver

# В отдельном терминале: запустить Tailwind watch
npm run watch:css

# Собрать production CSS
npm run build:css

# Проверить размер CSS
ls -lh static/css/output.css
```

---

## 💡 Полезные ресурсы

### Документация
- [Tailwind CSS Docs](https://tailwindcss.com/docs)
- [Tailwind Cheat Sheet](https://nerdcave.com/tailwind-cheat-sheet)

### Файлы проекта
- `TAILWIND_MIGRATION_PLAN.md` - полный план миграции с чекбоксами
- `TAILWIND_EXAMPLES.md` - примеры кода и паттерны

### Компоненты
Для вдохновения:
- [Tailwind UI](https://tailwindui.com/components)
- [Headless UI](https://headlessui.com/) - для модалок, dropdowns
- [DaisyUI](https://daisyui.com/) - готовые компоненты (опционально)

---

## ⚠️ Важные замечания

### Detail.html - НЕ АДАПТИРОВАТЬ!

```html
<!-- ✅ ПРАВИЛЬНО: фиксированная ширина + скролл -->
<div class="w-screen overflow-x-auto">
  <div class="min-w-[1003px] max-w-[1003px] mx-auto">
    <!-- Контент -->
  </div>
</div>

<!-- ❌ НЕПРАВИЛЬНО: адаптивная ширина -->
<div class="w-full max-w-7xl mx-auto">
  <!-- НЕ ДЕЛАТЬ ТАК ДЛЯ DETAIL! -->
</div>
```

### Mobile-First подход

Всегда начинай со стилей для мобильных:

```html
<!-- ✅ ПРАВИЛЬНО -->
<div class="text-sm sm:text-base lg:text-lg">
  Текст
</div>

<!-- ❌ НЕПРАВИЛЬНО -->
<div class="text-lg md:text-base sm:text-sm">
  Текст
</div>
```

### Touch targets

Минимум 44x44px для кликабельных элементов:

```html
<!-- ✅ ПРАВИЛЬНО -->
<button class="min-w-[44px] min-h-[44px] px-4 py-2">
  Кнопка
</button>

<!-- ❌ НЕПРАВИЛЬНО -->
<button class="w-8 h-8">
  Слишком маленькая
</button>
```

---

## 🆘 Troubleshooting

### Проблема: CSS не применяется

**Решение**:
1. Убедись что `npm run watch:css` запущен
2. Проверь путь к `output.css` в `base.html`
3. Очисти кеш браузера (`Cmd+Shift+R`)
4. Проверь `tailwind.config.js` - правильные ли пути в `content`

### Проблема: Tailwind конфликтует с existing CSS

**Решение**:
1. Используй `@layer utilities` для кастомных классов
2. Добавь `!important` если нужно переопределить
3. Удаляй старые CSS файлы постепенно

### Проблема: Большой размер output.css

**Решение**:
1. Убедись что `content` в `tailwind.config.js` правильно настроен
2. Используй `--minify` флаг при сборке
3. Проверь что PurgeCSS работает (только используемые классы)

---

## 📅 Рекомендуемый timeline

- **День 1-2**: Настройка Tailwind, базовые компоненты
- **День 3-4**: Миграция списка реплеев
- **День 5-7**: Миграция detail.html (осторожно!)
- **День 8**: Фильтры и auth страницы
- **День 9**: Тестирование на всех устройствах
- **День 10**: Удаление legacy CSS, деплой

**Итого: ~2 недели** для полной миграции с тестированием.

---

## ✅ Готов начать?

1. Установи зависимости: `npm install -D tailwindcss`
2. Создай конфиг: скопируй `tailwind.config.js` из этого файла
3. Запусти watch: `npm run watch:css`
4. Начни с `list.html` - самая важная страница!

**Удачи! 🚀**
