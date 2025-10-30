# Примеры миграции на Tailwind CSS

## Содержание
1. [Настройка Tailwind Config](#1-настройка-tailwind-config)
2. [Адаптивные паттерны](#2-адаптивные-паттерны)
3. [Миграция компонентов](#3-миграция-компонентов)
4. [Detail.html - Fixed Layout](#4-detailhtml---fixed-layout)
5. [Мобильное меню](#5-мобильное-меню)
6. [Утилиты и хелперы](#6-утилиты-и-хелперы)

---

## 1. Настройка Tailwind Config

### tailwind.config.js

```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './replays/templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        // Основные цвета из site.css
        dark: {
          900: '#0b0b0b',  // --bg
          800: '#141414',  // --panel
          700: '#1a1a1a',  // --panel-2
        },
        accent: {
          500: '#c0392b',  // --accent
          600: '#e74c3c',  // --accent-2
        },
        gold: '#f7c76b',
        border: '#292929',
        muted: '#b6b6b6',
        success: '#27ae60',
      },
      boxShadow: {
        'custom': '0 6px 18px rgba(0, 0, 0, 0.35)',
      },
      borderRadius: {
        'custom': '12px',
        'custom-sm': '8px',
      },
      screens: {
        'xs': '480px',
        // sm, md, lg, xl - дефолтные
        '2xl': '1600px',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
```

### input.css

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Кастомные компоненты */
@layer components {
  .btn {
    @apply inline-flex items-center justify-center px-4 py-2 rounded-lg font-medium transition-colors duration-200;
  }

  .btn--accent {
    @apply bg-accent-500 hover:bg-accent-600 text-white;
  }

  .btn--ghost {
    @apply border border-border hover:bg-dark-700 text-muted hover:text-white;
  }

  .card {
    @apply bg-dark-800 border border-border rounded-custom p-6 shadow-custom;
  }
}

/* Утилиты для detail.html - фиксированная ширина */
@layer utilities {
  .detail-fixed-container {
    @apply min-w-[1003px] max-w-[1003px] mx-auto;
  }

  .detail-scroll-container {
    @apply overflow-x-auto;
  }
}
```

### package.json

```json
{
  "name": "lesta-replays",
  "version": "1.0.0",
  "scripts": {
    "build:css": "tailwindcss -i ./static/css/input.css -o ./static/css/output.css --minify",
    "watch:css": "tailwindcss -i ./static/css/input.css -o ./static/css/output.css --watch",
    "dev": "npm run watch:css"
  },
  "devDependencies": {
    "@tailwindcss/forms": "^0.5.7",
    "@tailwindcss/typography": "^0.5.10",
    "tailwindcss": "^3.4.0"
  }
}
```

---

## 2. Адаптивные паттерны

### Responsive Grid (Mobile-First)

**До (wot_record_skin.css)**:
```css
.replay-grid {
    display: flex;
    flex-direction: column;
    gap: 12px;
}
```

**После (Tailwind)**:
```html
<!-- 1 колонка на мобильных, 2 на планшетах, 3 на десктопе -->
<div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
  <!-- Карточки -->
</div>

<!-- Для списка реплеев: вертикальный список с адаптивными карточками -->
<div class="flex flex-col gap-3">
  <div class="w-full sm:w-auto">
    <!-- Карточка реплея -->
  </div>
</div>
```

### Responsive Typography

```html
<!-- Заголовок адаптируется -->
<h1 class="text-2xl sm:text-3xl lg:text-4xl font-bold">
  {{ page_title }}
</h1>

<!-- Текст адаптируется -->
<p class="text-sm sm:text-base lg:text-lg">
  Описание
</p>
```

### Responsive Spacing

```html
<!-- Padding адаптируется -->
<div class="p-4 sm:p-6 lg:p-8">
  Контент
</div>

<!-- Margin адаптируется -->
<div class="mb-4 sm:mb-6 lg:mb-8">
  Контент
</div>
```

### Responsive Flex Direction

```html
<!-- Стек на мобильных, горизонтально на десктопе -->
<div class="flex flex-col md:flex-row gap-4">
  <div>Левая часть</div>
  <div>Правая часть</div>
</div>
```

---

## 3. Миграция компонентов

### Карточка реплея (tovabb)

**До (wot_record_skin.css)**:
```css
.tovabb {
    display: block;
    position: relative;
    max-width: 1024px;
    background: linear-gradient(135deg, rgba(51, 65, 85, 0.4) 0%, rgba(30, 41, 59, 0.6) 100%);
    border: 1px solid rgba(100, 116, 139, 0.3);
    border-radius: 12px;
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
```

**После (Tailwind)**:
```html
<a class="block relative max-w-full lg:max-w-4xl
          bg-gradient-to-br from-slate-700/40 to-slate-800/60
          border border-slate-500/30 rounded-xl overflow-hidden
          transition-all duration-300 ease-out
          hover:border-purple-500/40 hover:shadow-2xl
          transform hover:-translate-y-1 hover:scale-[1.02]
          cursor-pointer"
   href="{% url 'replay_detail' replay.id %}">

  <!-- Wrapper -->
  <div class="flex flex-col sm:flex-row items-stretch">

    <!-- Изображение карты + танк -->
    <div class="relative w-full sm:w-60 h-32 bg-gradient-to-br from-slate-900 to-slate-800
                flex-shrink-0 overflow-hidden">

      <!-- Gradient overlay -->
      <div class="absolute inset-x-0 bottom-0 h-3/5
                  bg-gradient-to-t from-black/50 to-transparent z-10
                  pointer-events-none"></div>

      <!-- Карта (фон) -->
      <img class="absolute inset-0 w-full h-full object-cover z-0 transition-opacity duration-200"
           src="{% static 'style/images/wot/map/stats/' %}{{ replay.map.map_name }}.png"
           alt="{{ replay.map.map_display_name }}">

      <!-- Танк (поверх) -->
      <img class="absolute right-1.5 bottom-1.5 h-[90px] w-auto max-w-[135px]
                  object-contain z-20 drop-shadow-[1px_1px_2px_rgba(0,0,0,0.7)]"
           src="{% static 'style/images/wot/shop/vehicles/180x135/' %}{{ replay.tank.vehicleId }}.png"
           alt="{{ replay.tank.name }}">

      <!-- Название карты -->
      <span class="absolute left-2 bottom-2 z-30
                   inline-flex items-center px-2 py-1
                   bg-black/40 backdrop-blur-sm rounded text-xs font-medium text-white
                   shadow-[0_0_8px_rgba(0,0,0,0.8)]">
        {{ replay.map.map_display_name }}
      </span>

      <!-- Тип и уровень танка (верхний правый угол) -->
      <div class="absolute right-2 top-2 flex items-center gap-1.5 z-30">
        {% if replay.tank.type %}
        <span class="relative h-7 w-7 sm:h-8 sm:w-8">
          <img class="h-full w-full brightness-125 contrast-125
                      drop-shadow-[0_0_45px_rgba(0,0,0,1)]"
               src="{% static 'style/images/wot/vehicleTypes/' %}{{ replay.tank.type }}.png"
               alt="Type">
        </span>
        {% endif %}
        {% if replay.tank.level %}
        <span class="relative h-7 w-7 sm:h-8 sm:w-8">
          <img class="h-full w-full brightness-125 contrast-125
                      drop-shadow-[0_0_45px_rgba(0,0,0,1)]"
               src="{% static 'style/images/wot/levels/tank_level_' %}{{ replay.tank.level }}.png"
               alt="Level {{ replay.tank.level }}">
        </span>
        {% endif %}
      </div>

      <!-- Mastery badge (левый нижний угол) -->
      {% if replay.mastery %}
      <img class="absolute left-1.5 bottom-1.5 h-12 w-12 sm:h-14 sm:w-14 z-30
                  drop-shadow-[0_4px_10px_rgba(0,0,0,0.85)]"
           src="{% static 'style/images/wot/library/proficiency/class_icons_' %}{{ replay.mastery }}.png"
           alt="Mastery {{ replay.mastery }}">
      {% endif %}
    </div>

    <!-- Детали -->
    <div class="flex-1 p-3 sm:p-4 flex flex-col justify-between gap-3">

      <!-- Заголовок -->
      <div class="flex flex-col gap-1">
        <div class="text-base sm:text-lg font-semibold text-white leading-tight">
          {% if replay.short_description %}
            {{ replay.short_description }}
          {% else %}
            {{ replay.tank.name }} • {{ replay.map.map_display_name }}
          {% endif %}
        </div>

        <!-- Дата и счетчики -->
        <div class="flex flex-wrap items-center justify-between gap-2 text-xs sm:text-sm">
          <div class="font-semibold text-gray-300">
            {{ replay.battle_date|localtime|date:"d.m.Y H:i" }}
          </div>
          <div class="flex items-center gap-3 text-gray-400">
            <span class="inline-flex items-center gap-1">
              <i class="far fa-comments text-base"></i>
              <span>{{ comment_count|default:"0" }}</span>
            </span>
            <span class="inline-flex items-center gap-1">
              <i class="far fa-eye text-base"></i>
              <span>{{ replay.view_count|intcomma }}</span>
            </span>
            <span class="inline-flex items-center gap-1">
              <i class="fas fa-download text-base"></i>
              <span>{{ replay.download_count|intcomma }}</span>
            </span>
          </div>
        </div>
      </div>

      <!-- Статистика -->
      <div class="grid grid-cols-3 sm:grid-cols-6 gap-2 sm:gap-3">
        <!-- Кредиты -->
        <div class="flex items-center gap-1">
          <img class="h-3 w-3 sm:h-4 sm:w-4"
               src="{% static 'style/images/wot/library/CreditsIconBig.png' %}"
               alt="Credits">
          <span class="text-xs sm:text-sm tabular-nums">{{ replay.credits|intcomma }}</span>
        </div>
        <!-- XP -->
        <div class="flex items-center gap-1">
          <img class="h-3 w-3 sm:h-4 sm:w-4"
               src="{% static 'style/images/wot/library/XpIconBig.png' %}"
               alt="XP">
          <span class="text-xs sm:text-sm tabular-nums">{{ replay.xp|intcomma }}</span>
        </div>
        <!-- Kills -->
        <div class="flex items-center gap-1">
          <img class="h-3 w-3 sm:h-4 sm:w-4"
               src="{% static 'style/images/wot/buttons/Tank-ico.png' %}"
               alt="Kills">
          <span class="text-xs sm:text-sm tabular-nums">{{ replay.kills }}</span>
        </div>
        <!-- Damage -->
        <div class="flex items-center gap-1">
          <img class="h-3 w-3 sm:h-4 sm:w-4"
               src="{% static 'style/images/wot/library/BattleResultIcon-1.png' %}"
               alt="Damage">
          <span class="text-xs sm:text-sm tabular-nums">{{ replay.damage|intcomma }}</span>
        </div>
        <!-- Assist -->
        <div class="flex items-center gap-1">
          <img class="h-3 w-3 sm:h-4 sm:w-4"
               src="{% static 'style/images/wot/buttons/assist.png' %}"
               alt="Assist">
          <span class="text-xs sm:text-sm tabular-nums">{{ replay.assist|intcomma }}</span>
        </div>
        <!-- Block -->
        <div class="flex items-center gap-1">
          <img class="h-3 w-3 sm:h-4 sm:w-4"
               src="{% static 'style/images/wot/buttons/blocked.png' %}"
               alt="Blocked">
          <span class="text-xs sm:text-sm tabular-nums">{{ replay.block|intcomma }}</span>
        </div>
      </div>
    </div>
  </div>
</a>
```

---

## 4. Detail.html - Fixed Layout

### Обертка для фиксированной ширины

```html
<!-- replays/templates/replays/detail.html -->
{% extends "base.html" %}

{% block content %}
<link rel="stylesheet" href="{% static 'css/output.css' %}">

<!-- ВАЖНО: Контейнер фиксированной ширины с горизонтальным скроллом -->
<div class="w-screen overflow-x-auto">
  <div class="min-w-[1003px] max-w-[1003px] mx-auto px-4">

    {% if parse_error %}
      <!-- Ошибка -->
      <div class="bg-red-900/20 border border-red-500/50 rounded-lg p-6">
        <h2 class="text-xl font-bold text-white mb-2">Ошибка обработки реплея</h2>
        <p class="text-red-300">{{ parse_error }}</p>
        <a href="{{ back_url }}" class="inline-block mt-4 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg">
          ← К списку реплеев
        </a>
      </div>
    {% else %}

      <!-- Replay Wrapper -->
      <div class="bg-dark-800 border border-border rounded-custom shadow-custom">

        <!-- Табы -->
        <div class="flex items-center gap-2 p-4 border-b border-border overflow-x-auto">
          <a href="{{ back_url }}" class="btn btn--ghost shrink-0">← Назад</a>
          <div class="tab active shrink-0 px-4 py-2 rounded-lg cursor-pointer" data-tab="personal">
            Личный результат
          </div>
          <div class="tab shrink-0 px-4 py-2 rounded-lg cursor-pointer" data-tab="team">
            Командный результат
          </div>
          <div class="tab shrink-0 px-4 py-2 rounded-lg cursor-pointer" data-tab="detailed">
            Подробный отчёт
          </div>
        </div>

        <!-- Контент табов - ВСЁ ФИКСИРОВАННОЙ ШИРИНЫ -->
        <!-- НЕ АДАПТИРОВАТЬ ПОД МОБИЛЬНЫЕ -->
        <!-- ... остальной контент ... -->

      </div>

      <!-- Комментарии (могут быть адаптивными, но внутри fixed контейнера) -->
      <div class="mt-8 bg-dark-800 border border-border rounded-custom p-6">
        <h4 class="text-xl font-bold text-white mb-4">Комментарии</h4>
        <!-- ... комментарии ... -->
      </div>

    {% endif %}
  </div>
</div>

{% endblock %}
```

### Таблицы в detail (фиксированная ширина)

```html
<!-- Таблица команды (НЕ адаптировать!) -->
<div class="w-full min-w-[500px]">
  <table class="w-full border-collapse">
    <thead>
      <tr class="bg-dark-700">
        <th class="px-2 py-2 text-left text-xs font-semibold text-gray-300 w-10">
          <div>&nbsp;</div>
        </th>
        <th class="px-2 py-2 text-left text-xs font-semibold text-gray-300 w-32">
          <div>Игрок</div>
        </th>
        <th class="px-2 py-2 text-left text-xs font-semibold text-gray-300 w-40">
          <div>Техника</div>
        </th>
        <th class="px-2 py-2 text-right text-xs font-semibold text-gray-300 w-20">
          <div>Урон</div>
        </th>
        <th class="px-2 py-2 text-right text-xs font-semibold text-gray-300 w-16">
          <div>Фраги</div>
        </th>
        <th class="px-2 py-2 text-right text-xs font-semibold text-gray-300 w-20">
          <div>Опыт</div>
        </th>
      </tr>
    </thead>
    <tbody>
      {% for player in team_results.allies_players %}
      <tr class="border-t border-border hover:bg-dark-700/50 transition-colors
                 {% if not player.is_alive %}opacity-50{% endif %}
                 {% if player.is_current_player %}bg-accent-500/10{% endif %}">
        <td class="px-2 py-2 text-center">
          {% if player.platoon_id %}
          <div class="inline-flex items-center justify-center w-6 h-6 bg-blue-500/20 rounded text-xs font-bold text-blue-400">
            {{ player.platoon_id }}
          </div>
          {% endif %}
        </td>
        <td class="px-2 py-2 text-sm text-white">{{ player.display_name }}</td>
        <td class="px-2 py-2">
          <div class="flex items-center gap-2">
            <img class="h-8 w-auto"
                 src="{% static 'style/images/wot/shop/vehicles/180x135/' %}{{ player.vehicle_tag }}.png"
                 alt="">
            <span class="text-xs text-gray-300">{{ player.vehicle_display_name }}</span>
          </div>
        </td>
        <td class="px-2 py-2 text-right text-sm font-semibold text-orange-400 tabular-nums">
          {{ player.damage_dealt|intcomma }}
        </td>
        <td class="px-2 py-2 text-right text-sm font-semibold text-white tabular-nums">
          {{ player.kills }}
        </td>
        <td class="px-2 py-2 text-right text-sm text-white tabular-nums">
          {{ player.xp }}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
```

---

## 5. Мобильное меню

### Navbar с hamburger menu

```html
<!-- templates/includes/_navbar.html -->
<header class="sticky top-0 z-50 backdrop-blur-md bg-dark-900/85 border-b border-border">
  <div class="max-w-7xl mx-auto px-4 sm:px-6">
    <div class="flex items-center justify-between py-3">

      <!-- Бренд -->
      <a class="flex items-center gap-2 font-extrabold tracking-wide" href="/">
        <img src="{% static 'style/images/wot/logo.png' %}" alt="Logo" class="h-8 w-auto">
        <span class="text-lg hidden sm:inline">РЕПЛЕИ</span>
      </a>

      <!-- Desktop Navigation -->
      <nav class="hidden md:flex items-center space-x-4">
        <button id="upload-replay-btn" type="button" class="btn btn--accent">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
            <path d="M7.646 1.146a.5.5 0 0 1 .708 0L10.5 3.293V10a.5.5 0 0 1-1 0V4.414..."/>
          </svg>
          <span>Загрузить</span>
        </button>

        {% if user.is_authenticated %}
          <!-- User Dropdown (Alpine.js) -->
          <div x-data="{ open: false }" class="relative">
            <button @click="open = !open"
                    class="flex items-center gap-2 text-gray-300 hover:text-white">
              {{ user.username }}
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94..."/>
              </svg>
            </button>

            <!-- Dropdown Menu -->
            <div x-show="open"
                 @click.away="open = false"
                 x-transition:enter="transition ease-out duration-100"
                 x-transition:enter-start="opacity-0 scale-95"
                 x-transition:enter-end="opacity-100 scale-100"
                 x-transition:leave="transition ease-in duration-75"
                 x-transition:leave-start="opacity-100 scale-100"
                 x-transition:leave-end="opacity-0 scale-95"
                 class="absolute right-0 mt-2 w-48 bg-dark-800 border border-border rounded-lg shadow-lg py-1 z-50"
                 style="display: none;">
              <a href="{% url 'my_replay_list' %}"
                 class="block px-4 py-2 text-sm text-gray-300 hover:bg-dark-700 hover:text-white">
                Мои реплеи
              </a>
              <div class="border-t border-border my-1"></div>
              <form method="post" action="{% url 'account_logout' %}">
                {% csrf_token %}
                <button type="submit"
                        class="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-dark-700 hover:text-white">
                  Выход
                </button>
              </form>
            </div>
          </div>
        {% else %}
          <a href="{% url 'account_login' %}" class="text-gray-300 hover:text-white">
            Войти
          </a>
        {% endif %}

        <a href="{% url 'about' %}" class="text-gray-300 hover:text-white">О проекте</a>
      </nav>

      <!-- Mobile Menu Button -->
      <button @click="mobileMenuOpen = !mobileMenuOpen"
              class="md:hidden p-2 text-gray-300 hover:text-white">
        <svg x-show="!mobileMenuOpen" class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
        </svg>
        <svg x-show="mobileMenuOpen" class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="display: none;">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <!-- Mobile Menu -->
    <div x-show="mobileMenuOpen"
         @click.away="mobileMenuOpen = false"
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 -translate-y-1"
         x-transition:enter-end="opacity-100 translate-y-0"
         x-transition:leave="transition ease-in duration-150"
         x-transition:leave-start="opacity-100 translate-y-0"
         x-transition:leave-end="opacity-0 -translate-y-1"
         class="md:hidden pb-4 space-y-2"
         style="display: none;">

      <button id="upload-replay-btn-mobile" type="button"
              class="w-full btn btn--accent justify-center">
        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
          <path d="M7.646 1.146a.5.5 0 0 1 .708 0L10.5 3.293V10a.5.5 0 0 1-1 0V4.414..."/>
        </svg>
        <span>Загрузить</span>
      </button>

      {% if user.is_authenticated %}
        <a href="{% url 'my_replay_list' %}"
           class="block px-4 py-2 text-gray-300 hover:bg-dark-700 rounded-lg">
          Мои реплеи
        </a>
        <form method="post" action="{% url 'account_logout' %}">
          {% csrf_token %}
          <button type="submit"
                  class="w-full text-left px-4 py-2 text-gray-300 hover:bg-dark-700 rounded-lg">
            Выход
          </button>
        </form>
      {% else %}
        <a href="{% url 'account_login' %}"
           class="block px-4 py-2 text-gray-300 hover:bg-dark-700 rounded-lg">
          Войти
        </a>
      {% endif %}

      <a href="{% url 'about' %}"
         class="block px-4 py-2 text-gray-300 hover:bg-dark-700 rounded-lg">
        О проекте
      </a>
    </div>
  </div>
</header>

<script>
  // Инициализация Alpine.js для mobile menu
  document.addEventListener('alpine:init', () => {
    Alpine.data('navbar', () => ({
      mobileMenuOpen: false
    }))
  })
</script>
```

---

## 6. Утилиты и хелперы

### Скрыть/показать на разных разрешениях

```html
<!-- Скрыть на мобильных -->
<div class="hidden md:block">
  Виден только на десктопе
</div>

<!-- Показать только на мобильных -->
<div class="block md:hidden">
  Виден только на мобильных
</div>

<!-- Разные размеры на разных экранах -->
<div class="w-full sm:w-1/2 lg:w-1/3">
  Адаптивная ширина
</div>
```

### Touch-friendly кнопки (минимум 44x44px)

```html
<!-- Кнопка для мобильных -->
<button class="min-w-[44px] min-h-[44px] flex items-center justify-center
               px-4 py-2 bg-accent-500 hover:bg-accent-600
               active:bg-accent-700 rounded-lg text-white
               touch-manipulation select-none">
  Нажми меня
</button>
```

### Горизонтальный скролл (для таблиц на мобильных)

```html
<div class="w-full overflow-x-auto">
  <table class="min-w-[600px] w-full">
    <!-- Таблица -->
  </table>
</div>
```

### Адаптивные изображения

```html
<!-- Responsive изображение -->
<img class="w-full h-auto max-w-full object-cover"
     src="..." alt="...">

<!-- Изображение с разными размерами -->
<img class="w-32 sm:w-48 lg:w-64 h-auto"
     src="..." alt="...">
```

### Sticky элементы

```html
<!-- Sticky navbar -->
<header class="sticky top-0 z-50 bg-dark-900">
  Навигация
</header>

<!-- Sticky sidebar -->
<aside class="sticky top-20 h-screen overflow-y-auto">
  Sidebar
</aside>
```

### Truncate текста

```html
<!-- Одна строка с ellipsis -->
<p class="truncate">
  Очень длинный текст который будет обрезан...
</p>

<!-- Две строки с ellipsis -->
<p class="line-clamp-2">
  Очень длинный текст который будет обрезан после второй строки...
</p>
```

### Loading state (skeleton)

```html
<div class="animate-pulse space-y-4">
  <div class="h-4 bg-gray-700 rounded w-3/4"></div>
  <div class="h-4 bg-gray-700 rounded w-1/2"></div>
  <div class="h-4 bg-gray-700 rounded w-5/6"></div>
</div>
```

---

## Заключение

Эти примеры покрывают основные паттерны миграции. Используй их как reference при работе с конкретными компонентами.

**Ключевые принципы**:
1. **Mobile-First**: Начинай со стилей для мобильных, затем добавляй breakpoints
2. **Touch-Friendly**: Минимум 44x44px для интерактивных элементов
3. **Fixed Detail**: Страница detail.html НЕ адаптивна, только horizontal scroll
4. **Consistency**: Используй одинаковые spacing/sizing паттерны
5. **Performance**: Используй PurgeCSS для удаления неиспользуемых классов

**Полезные команды**:
```bash
# Сборка CSS для разработки
npm run watch:css

# Сборка минифицированного CSS для продакшна
npm run build:css

# Проверка размера CSS
ls -lh static/css/output.css
```
