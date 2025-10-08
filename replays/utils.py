import json
from typing import Optional, Dict, Any, List


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


def summarize_credits(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Сводка «Серебро» (как на экране результата боя).
    Возвращает блоки 'base' (левая колонка) и 'premium' (правая), расходы и контрольные значения.

    Ключевые поля:
      originalCredits        — начислено за бой (база, без премиума)
      subtotalCredits        — начислено за бой (премиум-колонка, чаще = originalCredits * 1.5)
      boosterCreditsFactor100— +X% резервов (для базы считаем от originalCredits)
      boosterCredits         — сумма эффекта резервов (для премиум-колонки уже посчитана клиентом)
      teamSubsBonusCredits   — командный бонус от игрока с подпиской
      creditsPenalty         — штраф за урон союзникам
      creditsContributionIn  — компенсация за урон союзникам
      credits                — «Итого за бой» справа (для сверки)
      factualCredits         — фактические кредиты (без командного бонуса) — для сверки
      autoRepairCost / autoLoadCost[0] / autoEquipCost[0] — расходы
      piggyBank              — «Добавлено в хранилище ресурсов»
    """

    premium_credits_factor100 = int(data.get("premiumCreditsFactor100", 0))

    # --- поступления ---
    orig = int(data.get("originalCredits", 0))
    sub  = int(data.get("subtotalCredits", 0))
    team_bonus = int(data.get("teamSubsBonusCredits", 0))

    pen = int(data.get("creditsPenalty", 0))
    comp = int(data.get("creditsContributionIn", 0))

    order_credits = int(data.get("orderCredits", 0)) # Боевые выплаты (сумма с премом?)
    base_order_credits = order_credits * 100 // premium_credits_factor100

    event_credits = int(data.get("eventCredits", 0)) # Бонус за боевые задачи и события

    # резервы: в базе считаем от 'orig', в премиуме берём как есть
    boost_fact = int(data.get("boosterCreditsFactor100", 0))          # напр., 50 => +50%
    boost_base = round(orig * (boost_fact / 100.0))                   # 24_891 в примере
    boost_prem = int(data.get("boosterCredits", 0))                   # 37_337 в примере

    # --- расходы ---
    repair = int(data.get("autoRepairCost", 0))
    ammo   = int((data.get("autoLoadCost", [0, 0]) or [0, 0])[0])
    equip  = int((data.get("autoEquipCost", [0, 0, 0]) or [0, 0, 0])[0])
    total_costs = repair + ammo + equip

    # --- итоги по колонкам ---
    base_total_for_battle = orig + base_order_credits + event_credits + boost_base + team_bonus + comp - pen
    prem_total_for_battle = sub + order_credits + event_credits + boost_prem + team_bonus + comp - pen

    base_after_costs = base_total_for_battle - total_costs         # -31_801 в твоём бою
    prem_after_costs = prem_total_for_battle - total_costs         # 5_536  в твоём бою

    return {
        "event_credits": event_credits,
        "base": {
            "accrued": orig,
            "order_credits": base_order_credits,
            "booster_effect": boost_base,
            "team_subs_bonus": team_bonus,
            "team_damage_penalty": pen,
            "team_damage_compensation": comp,
            "total_for_battle": base_total_for_battle,
            "after_costs": base_after_costs,
        },
        "premium": {
            "accrued": sub,
            "order_credits": order_credits,
            "booster_effect": boost_prem,
            "team_subs_bonus": team_bonus,
            "team_damage_penalty": pen,
            "team_damage_compensation": comp,
            "total_for_battle": prem_total_for_battle,
            "after_costs": prem_after_costs,
        },
        "costs": {
            "auto_repair": repair,
            "auto_ammo": ammo,
            "auto_equipment": equip,
            "total_costs": total_costs,
        },
        "net": {
            "piggy_bank_added": int(data.get("piggyBank", 0)),
        },
        "control": {
            "reported_premium_total": int(data.get("credits", 0)),       # 112_508
            "reported_factual_credits": int(data.get("factualCredits", 0)),  # 112_010
        },
    }


def summarize_xp(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Сводка «Опыт» для двух колонок (Базовый аккаунт / Танковый премиум) + «Итого».

    Правила:
      • База: originalXP / originalFreeXP.
      • Прем:  subtotalXP / subtotalFreeXP.
      • Итог по прем-колонке для XP и FreeXP — берём factualXP / factualFreeXP из JSON, если есть.
        Если нет — считаем.
      • Дневной x2 и Управляемый x3 влияют ТОЛЬКО на XP (не на FreeXP).
      • Личные резервы (booster*) берём из JSON, если есть. Иначе считаем по факторам:
            boosterXP_base  = round(originalXP      * (boosterXPFactor100/100))
            boosterXP_prem  = round(subtotalXP      * (boosterXPFactor100/100))
            boosterFree_base= round(originalFreeXP  * (boosterFreeXPFactor100/100))
            boosterFree_prem= round(subtotalFreeXP  * (boosterFreeXPFactor100/100))
      • «Итого» БАЗА по XP считаем сами (в клиентском JSON нет): originalXP * eff_mult.
      • «Итого» ПРЕМ по XP/FreeXP — factual* (если есть), иначе считаем.
      • eff_mult = max(dailyXPFactor10, additionalXPFactor10) // 10   (т.е. x1/x2/x3).
    """
    # База/прем начислено
    base_xp   = int(data.get("originalXP", 0))
    base_free = int(data.get("originalFreeXP", 0))
    prem_xp   = int(data.get("subtotalXP", 0))
    prem_free = int(data.get("subtotalFreeXP", 0))

    # Что даёт клиент «как есть»
    factual_xp       = data.get("factualXP")
    factual_free_xp  = data.get("factualFreeXP")

    # Мультипликаторы (берём максимум — игра применяет больший множитель)
    daily_raw = int(data.get("dailyXPFactor10", 10))          # 10 -> x1, 20 -> x2
    add_raw   = int(data.get("additionalXPFactor10", 10))     # 30 -> x3
    daily_mult    = max(1, daily_raw // 10)
    managed_mult  = max(1, add_raw // 10)
    eff_mult      = max(daily_mult, managed_mult)

    # Готовые суммы от резервов, если есть — используем
    booster_xp_prem   = data.get("boosterXP")
    booster_free_prem = data.get("boosterFreeXP")
    booster_xp_base   = None
    booster_free_base = None

    # Факторы резервов (на случай отсутствия готовых сумм)
    bxpf = int(data.get("boosterXPFactor100", 0)) / 100.0
    bfxf = int(data.get("boosterFreeXPFactor100", 0)) / 100.0

    # Если каких-то сумм от резервов нет в JSON — досчитываем
    if booster_xp_prem is None and prem_xp:
        booster_xp_prem = int(round(prem_xp * bxpf))
    if booster_free_prem is None and prem_free:
        booster_free_prem = int(round(prem_free * bfxf))

    # Для базы в JSON обычно нет отдельных boosterXP/boosterFreeXP — считаем при необходимости
    if base_xp:
        booster_xp_base = int(round(base_xp * bxpf))
    else:
        booster_xp_base = 0
    if base_free:
        booster_free_base = int(round(base_free * bfxf))
    else:
        booster_free_base = 0

    penalty = int(data.get("xpPenalty", 0))

    # «Управляемый бонус к опыту» (orderXP) — если есть в JSON, отдадим как есть; считать его не пытаемся,
    # т.к. игра ведёт его по своим правилам (он то есть, то 0 при тех же множителях).
    order_xp = data.get("orderXP")

    # ИТОГО по колонкам
    base_total_xp  = int(round(base_xp * eff_mult)) if base_xp else 0
    # Прем: если клиент дал factualXP — берём его; иначе считаем упрощённо
    if factual_xp is not None:
        prem_total_xp = int(factual_xp)
    else:
        prem_total_xp = int(round(prem_xp * eff_mult)) + int(booster_xp_prem or 0)

    # FreeXP
    base_total_free  = base_free  + booster_free_base
    if factual_free_xp is not None:
        prem_total_free = int(factual_free_xp)
    else:
        prem_total_free = prem_free + int(booster_free_prem or 0)

    summarize = {
        "daily_xp_factor10": daily_mult,  # для "x2"
        "managed_xp_factor10": managed_mult, # для "x3"
        "multipliers": {
            "daily": daily_mult,          # x1/x2
            "managed": managed_mult,      # x1/x3
            "effective": eff_mult         # применённый (max)
        },
        "base": {
            "accrued": base_xp,
            "free_accrued": base_free,
            "penalty": penalty,
            "boosters": {"xp": booster_xp_base, "free_xp": booster_free_base},
            "total": base_total_xp,                 # «Итого» XP слева (рассчитано)
            "free_total": base_total_free           # «Итого» FreeXP слева (резервы + база)
        },
        "premium": {
            "accrued": prem_xp,
            "free_accrued": prem_free,
            "penalty": penalty,
            "boosters": {"xp": int(booster_xp_prem or 0), "free_xp": int(booster_free_prem or 0)},
            "order_xp": order_xp,                   # как есть из JSON (если есть)
            "total": prem_total_xp,                 # «Итого» XP справа (factualXP если есть)
            "free_total": prem_total_free           # «Итого» FreeXP справа (factualFreeXP если есть)
        },
    }
    # print(summarize)
    return summarize


def summarize_gold(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Сводка «Золото». В бою золото НЕ умножается премиум-аккаунтом,
    поэтому левая/правая колонка обычно идентичны (или правая просто не заполняется).

    Источники прихода:
      • originalGold — базовое золото за бой (редко, в ивентах)
      • eventGold, eventGoldList — золото из событий/задач
      • subtotalGold — «начислено» в правой колонке (если клиент его заполнил)
      • gold — «Итого за бой» (для контроля)

    Возможные расходы (редкость): если в дампе появятся поля вида goldPenalty/goldSpent/autoGoldCost —
    функция их вычитает. Сейчас в твоём примере все нули.
    """
    # --- поступления ---
    base_accrued = int(data.get("originalGold", 0))                 # 0
    event_gold = int(data.get("eventGold", 0))                      # 0
    # eventGoldList может быть списком ints или структур — аккуратно суммируем только ints
    evt_list: List[int] = []
    for x in (data.get("eventGoldList") or []):
        if isinstance(x, int):
            evt_list.append(x)
    event_gold += sum(evt_list)

    # subtotalGold может быть не задан — тогда берём сумму поступлений как «начислено»
    right_accrued = int(data.get("subtotalGold", base_accrued + event_gold))

    # --- возможные расходы по золоту (если встретятся) ---
    gold_cost_keys = ["goldPenalty", "goldSpent", "autoGoldCost"]
    gold_costs = 0
    for k in gold_cost_keys:
        v = data.get(k, 0)
        if isinstance(v, int):
            gold_costs += v

    # --- итоги ---
    left_total_for_battle  = base_accrued + event_gold
    right_total_for_battle = right_accrued                       # обычно совпадает с левым

    left_after_costs  = left_total_for_battle  - gold_costs
    right_after_costs = right_total_for_battle - gold_costs

    return {
        "base": {
            "accrued": base_accrued,                 # «Начислено за бой» (левая)
            "event_income": event_gold,              # золото из ивентов/задач
            "total_for_battle": left_total_for_battle,
            "after_costs": left_after_costs,
        },
        "premium": {
            "accrued": right_accrued,                # «Начислено за бой» (правая; премиум не влияет)
            "event_income": event_gold,
            "total_for_battle": right_total_for_battle,
            "after_costs": right_after_costs,
        },
        "costs": {
            "gold_costs": gold_costs,                # суммарные расходы золотом (если были)
        },
        "control": {
            "reported_final_gold": int(data.get("gold", 0)),     # «Итого за бой» золото
        },
    }
