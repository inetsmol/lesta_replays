/**
 * Модалка статистики игрока — загрузка данных через Lesta API прокси
 * и рендеринг в стиле tanki.su (оригинальная HTML-структура)
 */
(function () {
  'use strict';

  var playerCache = new Map();
  var vehicleDb = null; // справочник танков {tank_id: {name, tier, type, nation}}
  var vehicleDbPromise = null;
  var modal, body, loading, error, content;

  // Римские цифры для уровней
  var TIER_ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI'];

  // Типы техники
  var TYPE_NAMES = {
    'lightTank': 'ЛТ', 'mediumTank': 'СТ', 'heavyTank': 'ТТ',
    'AT-SPG': 'ПТ', 'SPG': 'САУ'
  };

  // Типы боёв для выпадающего списка
  var BATTLE_TYPES = [
    { key: 'all', label: 'Случайные бои' },
    { key: 'stronghold_defense', label: 'Укрепрайон: Наступления' },
    { key: 'stronghold_skirmish', label: 'Укрепрайон: Вылазки' },
  ];

  // Основные достижения для отображения

  function init() {
    modal = document.getElementById('player-stats-modal');
    if (!modal) return;

    body = document.getElementById('player-stats-body');
    loading = document.getElementById('player-stats-loading');
    error = document.getElementById('player-stats-error');
    content = document.getElementById('player-stats-content');

    // Делегирование: клик по имени игрока
    document.addEventListener('click', function (e) {
      var link = e.target.closest('.player-stats-link');
      if (!link) return;
      e.preventDefault();
      var accountId = link.dataset.accountId;
      var playerName = link.dataset.playerName || '';
      if (!accountId || accountId === '0') return;
      openModal(accountId, playerName);
    });

    // Закрытие
    modal.addEventListener('click', function (e) {
      if (e.target.matches('[data-close="player-stats"]') || e.target.closest('[data-close="player-stats"]')) {
        closeModal();
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal.getAttribute('aria-hidden') === 'false') {
        closeModal();
      }
    });
  }

  function loadVehicleDb() {
    if (vehicleDb) return Promise.resolve(vehicleDb);
    if (vehicleDbPromise) return vehicleDbPromise;
    vehicleDbPromise = fetch('/api/vehicles/encyclopedia/')
      .then(function (resp) { return resp.ok ? resp.json() : {}; })
      .then(function (data) {
        if (!data.error) vehicleDb = data;
        return vehicleDb || {};
      })
      .catch(function () { return {}; });
    return vehicleDbPromise;
  }

  function getVehicleInfo(tankId) {
    if (!vehicleDb) return null;
    return vehicleDb[String(tankId)] || null;
  }

  function openModal(accountId, playerName) {
    document.getElementById('player-stats-title').textContent =
      playerName ? 'Статистика — ' + playerName : 'Статистика игрока';

    loading.style.display = '';
    error.style.display = 'none';
    content.style.display = 'none';

    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';

    if (playerCache.has(accountId)) {
      renderData(playerCache.get(accountId), accountId);
      return;
    }

    // Загружаем данные игрока и справочник параллельно
    Promise.all([
      fetch('/api/player/' + accountId + '/stats/')
        .then(function (resp) {
          if (!resp.ok) throw new Error(resp.status);
          return resp.json();
        }),
      loadVehicleDb()
    ])
      .then(function (results) {
        var data = results[0];
        if (data.error) throw new Error(data.error);
        playerCache.set(accountId, data);
        renderData(data, accountId);
      })
      .catch(function () {
        loading.style.display = 'none';
        error.style.display = '';
      });
  }

  function closeModal() {
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  function fmt(n) {
    if (n == null) return '—';
    return Number(n).toLocaleString('ru-RU');
  }

  function fmtDate(ts) {
    if (!ts) return '—';
    var d = new Date(ts * 1000);
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
  }

  function fmtDateTime(ts) {
    if (!ts) return '—';
    var d = new Date(ts * 1000);
    return d.toLocaleDateString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  }

  function pct(a, b) {
    if (!b) return '0,00';
    return (a / b * 100).toFixed(2).replace('.', ',');
  }

  function renderStatsBlock(s, battles, avgDmg, avgXp, mastery, totalTanks, globalRating) {
    var h = `
      <div class="stats_item stats_item__big">
          <div class="stats_ico stats_ico__big"></div>
          <span class="stats_value">${globalRating !== null ? fmt(globalRating) : '—'}</span>
          <span class="stats_text">Личный рейтинг</span>
      </div>

      <div class="stats_box stats_box__left">
          <div class="stats_item">
              <div class="stats_ico"><span class="ico-win-rate ico-win-rate__light"></span></div>
              <span class="stats_value">${pct(s.wins, battles)}%</span>
              <span class="stats_text">Победы</span>
          </div>
          <div class="stats_item">
              <div class="stats_ico"><span class="ico-stats ico-stats__btl"></span></div>
              <span class="stats_value">${fmt(battles)}</span>
              <span class="stats_text">Бои</span>
          </div>
          <div class="stats_item">
              <div class="stats_ico"><span class="ico-stats ico-stats__btl-targets"></span></div>
              <span class="stats_value">${(s.hits_percents || 0).toFixed(2).replace('.', ',')}%</span>
              <span class="stats_text">Попадания</span>
          </div>
          <div class="stats_item">
              <div class="stats_ico"><span class="ico-dmg-per-btl ico-dmg-per-btl__light"></span></div>
              <span class="stats_value">${fmt(avgDmg)}</span>
              <span class="stats_text">Средний урон</span>
          </div>
      </div>

      <div class="stats_box stats_box__right">
          <div class="stats_item">
              <div class="stats_ico"><span class="ico-exp-per-btl ico-exp-per-btl__light"></span></div>
              <span class="stats_value">${fmt(avgXp)}</span>
              <span class="stats_text">Средний опыт за бой</span>
          </div>
          <div class="stats_item">
              <div class="stats_ico"><span class="ico-stats ico-stats__max-exp"></span></div>
              <span class="stats_value">${fmt(s.max_xp)}</span>
              <span class="stats_text">Максимальный опыт за бой</span>
          </div>
          <div class="stats_item">
              <div class="stats_ico"><span class="ico-stats ico-stats__frags"></span></div>
              <span class="stats_value">${fmt(s.max_frags)}</span>
              <span class="stats_text">Максимум уничтожено за бой</span>
          </div>
          <div class="stats_item">
              <div class="stats_ico"><span class="ico-stats ico-stats__master"></span></div>
              <span class="stats_value"><span>${fmt(mastery[4])}</span>/<span class="stats_small-value">${fmt(totalTanks)}</span></span>
              <span class="stats_text">Знаки классности «Мастер»</span>
          </div>
      </div>
    `;
    return h;
  }

  function renderData(data, accountId) {
    var info = data.info;
    var tanks = data.tanks;
    var achievements = data.achievements;
    var clan = data.clan;

    if (!info) {
      loading.style.display = 'none';
      error.style.display = '';
      return;
    }

    var s = info.statistics && info.statistics.all || {};
    var nickname = info.nickname || '';

    // Считаем знаки классности из tanks
    var mastery = { 4: 0, 3: 0, 2: 0, 1: 0 };
    var totalTanks = 0;
    if (tanks && Array.isArray(tanks)) {
      totalTanks = tanks.length;
      tanks.forEach(function (t) {
        var m = t.mark_of_mastery;
        if (m >= 1 && m <= 4) mastery[m]++;
      });
    }

    // Средние показатели
    var battles = s.battles || 0;
    var avgDmg = battles ? Math.round(s.damage_dealt / battles) : 0;
    var avgXp = s.battle_avg_xp || 0;
    var avgSpotted = battles ? (s.spotted / battles).toFixed(2).replace('.', ',') : '0';
    var avgKills = battles ? (s.frags / battles).toFixed(2).replace('.', ',') : '0';
    var avgDmgReceived = battles ? Math.round(s.damage_received / battles) : 0;

    // Коэффициенты
    var dmgRatio = s.damage_received ? (s.damage_dealt / s.damage_received).toFixed(2).replace('.', ',') : '—';
    var deadBattles = battles - (s.survived_battles || 0);
    var killRatio = deadBattles > 0 ? (s.frags / deadBattles).toFixed(2).replace('.', ',') : '—';
    var armorEff = s.tanking_factor != null ? Number(s.tanking_factor).toFixed(2).replace('.', ',') : '—';

    // Оглушения (средние)
    var avgStun = battles ? Math.round(s.stun_number / battles) : 0;
    var avgAssisted = battles ? Math.round(s.avg_damage_assisted || 0) : 0;
    var avgStunAssisted = battles ? Math.round(s.avg_damage_assisted_stun || 0) : 0;

    var html = `
      <div class="ps-header">
        <div class="ps-header-wrapper">
          <div class="ps-header-left">
            <div class="ps-user-name">${esc(nickname)}</div>
            <ul class="ps-user-info-list">
              <li class="ps-user-info-item">Дата регистрации: <span class="ps-user-info-value">${fmtDate(info.created_at)}</span> &nbsp; Последний раз был в бою: <span class="ps-user-info-value">${fmtDateTime(info.last_battle_time)}</span></li>
            </ul>
          </div>
    `;

    if (clan && clan.tag) {
      var clanColor = clan.color || '#e59400';
      var clanEmblem = (clan.emblems && clan.emblems.x64 && clan.emblems.x64.portal) || '';
      var member = clan.member;
      html += `
          <div class="ps-header-right">
            <div class="ps-clan-box">
              <h4 class="ps-clan-heading">Клан</h4>
              <div class="ps-clan-holder">
                ${clanEmblem ? `<span class="ps-clan-img" style="background-image:url(${esc(clanEmblem)})"></span>` : ''}
                <span class="ps-clan-name">
                  <span class="ps-clan-tag" style="color:${esc(clanColor)}">[${esc(clan.tag)}]</span>
                  <span class="ps-clan-fullname">${esc(clan.name)}</span>
                </span>
              </div>
      `;
      if (member) {
        html += `<ul class="ps-clan-member-info">`;
        if (member.role_i18n) {
          html += `<li>Должность: <span class="ps-user-info-value">${esc(member.role_i18n)}</span></li>`;
        }
        if (member.joined_at) {
          var daysInClan = Math.floor((Date.now() / 1000 - member.joined_at) / 86400);
          html += `<li>Дней в клане: <span class="ps-user-info-value">${fmt(daysInClan)}</span></li>`;
        }
        html += `</ul>`;
      }
      html += `</div></div>`;
    }

    html += `
        </div>
        <div class="ps-header-links">
          <a class="ps-tanki-link" href="https://tanki.su/ru/community/accounts/${accountId}-${encodeURIComponent(nickname)}/" target="_blank" rel="noopener">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 19H5V5h7V3H5a2 2 0 00-2 2v14a2 2 0 002 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
            Профиль на tanki.su
          </a>
        </div>
      </div>
    `;

    // === Основная статистика (структура tanki.su) ===
    html += `
      <section class="profile-grid profile-grid__small-margin">
        <header class="profile-grid_header">
          <h2 class="profile-grid_heading">Статистика</h2>
          <span class="profile-grid_sub-info">
            <a href="#" class="profile-grid_info-link ps-battle-type-toggle">Случайные бои</a>
            <div class="ps-dropdown" style="display:none">
              <ul class="ps-dropdown-list">
    `;
    
    BATTLE_TYPES.forEach(function (bt) {
      var active = bt.key === 'all' ? ' select-list_item__active' : '';
      html += `<li class="select-list_item${active} ps-dropdown-item" data-stat-key="${bt.key}">${bt.label}</li>`;
    });

    html += `
              </ul>
            </div>
          </span>
        </header>

        <div class="stats">
          <div class="stats_inner" id="ps-stats-inner">
            ${renderStatsBlock(s, battles, avgDmg, avgXp, mastery, totalTanks, info.global_rating)}
          </div>
        </div>
      </section>
    `;

    // === Достижения ===
    if (achievements && achievements.length) {
      html += renderAchievements(achievements);
    }

    // === Бои по уровням (бар-чарт) ===
    if (tanks && tanks.length && vehicleDb) {
      html += renderVehicleCharts(tanks, data);
    }

    // === Подробная статистика ===
    html += `
      <section class="profile-grid">
        <div class="all-stats-grid">
          <div class="all-stats-grid_inner">

            <div class="all-stats-grid_item">
              <div class="all-stats">
                <h4 class="all-stats_heading">Общие параметры</h4>
                <ul class="all-stats_list">
                  ${allStatsRow('Бои', fmt(battles))}
                  ${allStatsRow('Победы', fmt(s.wins) + ' (' + pct(s.wins, battles) + '%)')}
                  ${allStatsRow('Поражения', fmt(s.losses) + ' (' + pct(s.losses, battles) + '%)')}
                  ${allStatsRow('Выживаемость', fmt(s.survived_battles) + ' (' + pct(s.survived_battles, battles) + '%)')}
                </ul>
                <ul class="all-stats_list">
                  ${allStatsRow('Коэффициент урона', dmgRatio)}
                  ${allStatsRow('Коэффициент уничтожения', killRatio)}
                  ${allStatsRow('Эффективность использования брони', armorEff)}
                  ${allStatsRow('Очки захвата базы', fmt(s.capture_points))}
                  ${allStatsRow('Очки защиты базы', fmt(s.dropped_capture_points))}
                </ul>
              </div>
            </div>

            <div class="all-stats-grid_item">
              <div class="all-stats">
                <h4 class="all-stats_heading">Средние показатели за бой</h4>
                <ul class="all-stats_list">
                  ${allStatsRow('Опыт', fmt(avgXp))}
                </ul>
                <ul class="all-stats_list">
                  ${allStatsRow('Нанесённый урон', fmt(avgDmg))}
                  ${allStatsRow('Полученный урон', fmt(avgDmgReceived))}
                  ${allStatsRow('Количество оглушений', fmt(avgStun))}
                  ${allStatsRow('Урон, нанесённый с вашей помощью', fmt(avgAssisted))}
                  ${allStatsRow('Урон по оглушённым вами целям', fmt(avgStunAssisted))}
                </ul>
                <ul class="all-stats_list">
                  ${allStatsRow('Обнаружено машин противника', avgSpotted)}
                  ${allStatsRow('Уничтожено машин противника', avgKills)}
                </ul>
              </div>
            </div>

            <div class="all-stats-grid_holder">
              <div class="all-stats-grid_item all-stats-grid_item__wide">
                <div class="all-stats">
                  <h4 class="all-stats_heading">Рекордные показатели</h4>
                  <ul class="all-stats_list">
                    ${allStatsRow('Максимум уничтожено за бой', fmt(s.max_frags))}
                    ${allStatsRow('Максимальный опыт за бой', fmt(s.max_xp))}
                    ${allStatsRow('Максимальный урон за бой', fmt(s.max_damage))}
                  </ul>
                </div>
              </div>

              <div class="all-stats-grid_item all-stats-grid_item__wide">
                <div class="all-stats">
                  <h4 class="all-stats_heading">Знаки классности</h4>
                  <ul class="all-stats_list">
                    ${allStatsRowIco('ico-ranks ico-ranks__master', 'Мастер', fmt(mastery[4]))}
                    ${allStatsRowIco('ico-ranks ico-ranks__01', '1 степень', fmt(mastery[3]))}
                    ${allStatsRowIco('ico-ranks ico-ranks__02', '2 степень', fmt(mastery[2]))}
                    ${allStatsRowIco('ico-ranks ico-ranks__03', '3 степень', fmt(mastery[1]))}
                  </ul>
                </div>
              </div>
            </div>

          </div>
        </div>
      </section>
    `;

    // === Техника ===
    if (tanks && tanks.length) {
      html += renderVehiclesTable(tanks);
    }

    loading.style.display = 'none';
    content.innerHTML = html;
    content.style.display = '';

    initBattleTypeDropdown(data);
    initVehicleChartsDropdown(data);
    initAchievements();
  }

  function allStatsRow(title, value) {
    return '<li class="all-stats_item">' +
      '<span class="all-stats_title">' + title + '</span>' +
      '<span class="all-stats_value">' + value + '</span></li>';
  }

  function allStatsRowIco(icoClass, title, value) {
    return '<li class="all-stats_item">' +
      '<span class="all-stats_ico"><span class="' + icoClass + '"></span></span>' +
      '<span class="all-stats_title">' + title + '</span>' +
      '<span class="all-stats_value">' + value + '</span></li>';
  }

  // === 4. Бои по технике (Бар-чарт по уровням, нациям, типам) ===
  function renderVehicleCharts(tanks, data) {
    if (!tanks || !tanks.length) return '';

    var NATIONS = ['ussr', 'germany', 'usa', 'china', 'france', 'uk', 'japan', 'czech', 'sweden', 'poland', 'italy', 'intunion'];
    var NATION_NAMES = {
      'ussr': 'СССР', 'germany': 'Германия', 'usa': 'США', 'china': 'Китай', 'france': 'Франция',
      'uk': 'Великобритания', 'japan': 'Япония', 'czech': 'Чехословакия', 'sweden': 'Швеция',
      'poland': 'Польша', 'italy': 'Италия', 'intunion': 'Сборная наций'
    };
    var TYPES = ['lighttank', 'mediumtank', 'heavytank', 'at-spg', 'spg'];
    var TYPE_NAMES = {
      'lighttank': 'Лёгкие танки',
      'mediumtank': 'Средние танки',
      'heavytank': 'Тяжёлые танки',
      'at-spg': 'ПТ-САУ',
      'spg': 'САУ'
    };

    var iterBattles = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0, 10: 0, 11: 0 };
    var natBattles = {};
    var typBattles = {};

    var maxTier = 0, maxNat = 0, maxTyp = 0;
    var totalBattles = 0;

    // Агрегируем бои
    tanks.forEach(function (t) {
      if (!t.tank_id) return;
      var info = vehicleDb[t.tank_id];
      if (!info) return;

      var b = t.statistics && t.statistics.battles ? t.statistics.battles : 0;
      if (b > 0) {
        var lvl = info.tier || 1;
        var nat = (info.nation || 'ussr').toLowerCase();
        var typ = (info.type || 'mediumtank').toLowerCase();

        iterBattles[lvl] = (iterBattles[lvl] || 0) + b;
        natBattles[nat] = (natBattles[nat] || 0) + b;
        typBattles[typ] = (typBattles[typ] || 0) + b;
        totalBattles += b;
      }
    });

    if (totalBattles === 0) return '';

    for (var k in iterBattles) { if (iterBattles[k] > maxTier) maxTier = iterBattles[k]; }
    for (var k in natBattles) { if (natBattles[k] > maxNat) maxNat = natBattles[k]; }
    for (var k in typBattles) { if (typBattles[k] > maxTyp) maxTyp = typBattles[k]; }

    // Строим шапку и dropdown внутри
    var html = `
      <section class="profile-grid">
        <header class="profile-grid_header">
          <h2 class="profile-grid_heading">Бои на технике</h2>
          <span class="profile-grid_sub-info">
            <a href="#" class="profile-grid_info-link ps-vehicle-charts-toggle">Случайные бои</a>
            <div class="ps-dropdown ps-dropdown-charts" style="display:none">
              <ul class="ps-dropdown-list">
    `;
    
    BATTLE_TYPES.forEach(function (bt) {
      var active = bt.key === 'all' ? ' select-list_item__active' : '';
      html += `<li class="select-list_item${active} ps-dropdown-charts-item" data-stat-key="${bt.key}">${bt.label}</li>`;
    });

    html += `
              </ul>
            </div>
          </span>
        </header>

        <div class="diagram-grid">
          <div class="diagram-grid_arrow diagram-grid_arrow__left diagram-grid_arrow__active"></div>
          <div class="diagram-grid_arrow diagram-grid_arrow__right diagram-grid_arrow__active"></div>
          <div class="diagram-grid_shadow diagram-grid_shadow__left diagram-grid_shadow__active"></div>
          <div class="diagram-grid_shadow diagram-grid_shadow__right diagram-grid_shadow__active"></div>

          <div class="diagram-grid_holder js-slider-scrollable">
            <div class="diagram-grid_inner js-vehicle-charts">
    `;

    // 1. По уровню
    html += `
              <div class="diagram-grid_item js-slider-frame">
                <div class="diagram">
                  <div class="diagram_inner">
    `;
    var roms = { 1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X', 11: 'XI' };
    var tplTier = document.getElementById('tpl-diagram-tier');
    if (tplTier && maxTier > 0) {
      for (var i = 1; i <= 11; i++) {
        var b = iterBattles[i] || 0;
        var pct = maxTier > 0 ? (b / maxTier * 100) : 0;
        if (pct > 0 && pct < 1) pct = 1;

        var clone = tplTier.content.cloneNode(true);
        var bar = clone.querySelector('.diagram_bar');
        var val = clone.querySelector('.diagram_value');
        
        bar.style.height = pct + '%';
        if (b > 0) val.textContent = fmt(b);
        else val.textContent = '';
        
        clone.querySelectorAll('.ps-tier-name').forEach(el => el.textContent = roms[i]);
        clone.querySelector('.ps-tier-battles').textContent = fmt(b);

        var tempDiv = document.createElement('div');
        tempDiv.appendChild(clone);
        html += tempDiv.innerHTML;
      }
    }
    html += `
                  </div>
                  <p class="diagram_text">По уровню</p>
                </div>
              </div>
    `;

    // 2. По нации
    html += `
              <div class="diagram-grid_item js-slider-frame">
                <div class="diagram">
                  <div class="diagram_inner">
    `;
    var tplNation = document.getElementById('tpl-diagram-nation');
    if (tplNation && maxNat > 0) {
      NATIONS.forEach(function(natCode) {
        var b = natBattles[natCode] || 0;
        // Отрисовываем даже если 0, как в танках, чтобы сохранить порядок
        var pct = maxNat > 0 ? (b / maxNat * 100) : 0;
        if (pct > 0 && pct < 1) pct = 1;

        var clone = tplNation.content.cloneNode(true);
        var bar = clone.querySelector('.diagram_bar');
        var val = clone.querySelector('.diagram_value');
        var flag = clone.querySelector('.rastr-flag');
        
        bar.style.height = pct + '%';
        if (b > 0) val.textContent = fmt(b);
        else val.textContent = '';
        
        flag.className = 'rastr-flag rastr-flag__small rastr-flag__ico-' + natCode;
        
        var localized = NATION_NAMES[natCode] || natCode;
        clone.querySelectorAll('.ps-nation-name').forEach(el => el.textContent = localized);
        clone.querySelector('.ps-nation-battles').textContent = fmt(b);

        var tempDiv = document.createElement('div');
        tempDiv.appendChild(clone);
        html += tempDiv.innerHTML;
      });
    }
    html += `
                  </div>
                  <p class="diagram_text">По нации</p>
                </div>
              </div>
    `;

    // 3. По типу (классу)
    html += `
              <div class="diagram-grid_item js-slider-frame">
                <div class="diagram">
                  <div class="diagram_inner">
    `;
    var tplType = document.getElementById('tpl-diagram-type');
    if (tplType && maxTyp > 0) {
      TYPES.forEach(function(typCode) {
        var b = typBattles[typCode] || 0;
        var pct = maxTyp > 0 ? (b / maxTyp * 100) : 0;
        if (pct > 0 && pct < 1) pct = 1;

        var clone = tplType.content.cloneNode(true);
        var bar = clone.querySelector('.diagram_bar');
        var val = clone.querySelector('.diagram_value');
        var ico = clone.querySelector('.ico-vehicle-type');
        
        bar.style.height = pct + '%';
        if (b > 0) val.textContent = fmt(b);
        else val.textContent = '';
        
        ico.className = 'ico-vehicle-type ico-vehicle-type__' + typCode;
        
        var localized = TYPE_NAMES[typCode] || typCode;
        clone.querySelectorAll('.ps-type-name').forEach(el => el.textContent = localized);
        clone.querySelector('.ps-type-battles').textContent = fmt(b);

        var tempDiv = document.createElement('div');
        tempDiv.appendChild(clone);
        html += tempDiv.innerHTML;
      });
    }
    html += `
                  </div>
                  <p class="diagram_text">По типу</p>
                </div>
              </div>
    `;

    // Закрываем сетку
    html += `
            </div>
          </div>
        </div>
      </section>
    `;

    return html;
  }

  function initVehicleChartsDropdown(data) {
    var toggle = content.querySelector('.ps-vehicle-charts-toggle');
    var wrapper = content.querySelector('.ps-dropdown-charts');
    if (!toggle || !wrapper) return;

    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      var isShown = wrapper.style.display !== 'none';
      wrapper.style.display = isShown ? 'none' : '';
      if (!isShown) toggle.classList.add('profile-grid_info-link__opened');
      else toggle.classList.remove('profile-grid_info-link__opened');
    });

    document.addEventListener('click', function(e) {
      if (!toggle.contains(e.target) && !wrapper.contains(e.target)) {
        wrapper.style.display = 'none';
        toggle.classList.remove('profile-grid_info-link__opened');
      }
    });

    var items = wrapper.querySelectorAll('.ps-dropdown-charts-item');
    items.forEach(function(item) {
      item.addEventListener('click', function() {
        items.forEach(function(i) { i.classList.remove('select-list_item__active'); });
        this.classList.add('select-list_item__active');
        
        var label = this.textContent;
        toggle.textContent = label;
        wrapper.style.display = 'none';
        toggle.classList.remove('profile-grid_info-link__opened');

        // Note: Currently, backend tanks data aggregates all battle types.
        // True separation by type requires server changes to return per-key tanks statistics.
        // Therefore, we visually switch the dropdown but leave the charts unchanged for now.
      });
    });
  }

  // Названия и порядок секций (как на tanki.su)
  // action=Особые (свёрнутый вид), battle=Герои битвы, special=Почётные звания,
  // epic=Эпические медали, group=Групповые награды, memorial=Памятные знаки, class=Этапные награды
  var ACH_SECTION_ORDER = ['battle', 'special', 'epic', 'group', 'memorial', 'class', 'action'];
  var ACH_SECTION_NAMES = {
    'battle': 'Герои битвы',
    'special': 'Почётные звания',
    'epic': 'Эпические медали',
    'group': 'Групповые награды',
    'memorial': 'Памятные знаки',
    'class': 'Этапные награды',
    'action': 'Особые',
    '': 'Прочие',
  };
   // === 3. Достижения ===

  function achItemHtml(a) {
    var tpl = document.getElementById('tpl-achievement');
    if (!tpl) return '';
    var clone = tpl.content.cloneNode(true);
    var item = clone.querySelector('.achiev-item');
    var img = clone.querySelector('.achiev-item_img');
    var counter = clone.querySelector('.achiev-item_counter');
    var title = clone.querySelector('.small-tooltip_title');
    var desc = clone.querySelector('.ps-ach-desc');
    var cond = clone.querySelector('.ps-ach-cond');
    
    // Иконка
    var src = a.image || a.image_big || a.image_small || '';
    if (src && !src.startsWith('/') && !src.startsWith('http')) {
        src = '/static/' + src;
    }
    img.src = src;
    
    // Значение/количество
    var count = a.count !== undefined ? a.count : a.value;
    if (count > 1 || (count > 0 && typeof count === 'number')) {
      counter.textContent = fmt(count);
      counter.style.display = '';
    }
    
    // Тултип
    var achName = a.name_i18n || a.name || a.title || '';
    achName = achName.replace(/^«(.*)»$/, '$1'); // убираем кавычки если уже есть
    title.textContent = achName ? '«' + esc(achName) + '»' : '';
    desc.innerHTML = a.description ? a.description.replace(/\n/g, '<br>') : '';
    cond.innerHTML = a.condition ? a.condition.replace(/\n/g, '<br>') : '';
    
    // Сериализация обратно в строку для конкатенации
    var tempDiv = document.createElement('div');
    tempDiv.appendChild(clone);
    return tempDiv.innerHTML;
  }

  function renderAchievements(achievements) {
    if (!achievements || !achievements.length) return '';

    // Группируем по section
    var sections = {};
    achievements.forEach(function (a) {
      var sec = a.section || 'other';
      if (!sections[sec]) sections[sec] = [];
      sections[sec].push(a);
    });

    // Подсчёт: "обычные" (все кроме action) и "особые" (action)
    var actionList = sections['action'] || [];
    var regularCount = achievements.length - actionList.length;
    // Всего обычных не знаем (нет данных), показываем как на tanki.su: earned + особые N
    var headerSub = fmt(regularCount) + ' достижений';
    if (actionList.length) {
      headerSub += ' + ОСОБЫЕ ' + fmt(actionList.length);
    }

    var html = '<section class="profile-grid">';
    html += '<header class="profile-grid_header profile-grid_header__small-margin">';
    html += '<h2 class="profile-grid_heading">ДОСТИЖЕНИЯ</h2>';
    html += '<span class="profile-grid_sub-info">' + headerSub + '</span>';
    html += '</header>';

    // Свёрнутый вид — первые 9 из секции "action" (Особые, как на tanki.su)
    var shortList = actionList.slice(0, 9);
    html += '<div class="ps-ach-short">';
    html += '<div class="achievements achievements__has-ribbon">';
    html += '<div class="achievements_inner">';
    html += '<ul class="achievements_list">';
    shortList.forEach(function(a) {
      html += '<li class="achievements_item">' + achItemHtml(a) + '</li>';
    });
    html += '</ul>';
    html += '</div></div>';
    html += '<div class="show-more show-more__has-margins">';
    html += '<button class="js-ps-ach-show-all profile-grid_info-link">ПОКАЗАТЬ ВСЕ ДОСТИЖЕНИЯ</button>';
    html += '</div>';
    html += '</div>';

    // Развёрнутый вид — по секциям в порядке как на tanki.su
    html += '<div class="ps-ach-full" style="display:none;">';
    ACH_SECTION_ORDER.forEach(function(key) {
      var list = sections[key];
      if (!list || !list.length) return;
      var name = ACH_SECTION_NAMES[key] || key;
      html += '<div class="ps-ach-section">';
      html += '<h4 class="achievements_heading">';
      html += '<span>' + esc(name) + '</span>';
      html += '<span class="achievements_info">' + fmt(list.length) + '</span>';
      html += '</h4>';
      html += '<ul class="achievements_list ps-ach-section-list">';
      list.forEach(function(a) {
        html += '<li class="achievements_item">' + achItemHtml(a) + '</li>';
      });
      html += '</ul>';
      html += '</div>';
    });
    html += '<div class="show-more show-more__has-margins">';
    html += '<button class="js-ps-ach-hide profile-grid_info-link">СВЕРНУТЬ</button>';
    html += '</div>';
    html += '</div>';

    html += '</section>';
    return html;
  }

   // === 5. Таблица техники ===
  function renderVehiclesTable(tanks) {
    if (!tanks || !tanks.length) return '';

    // Обогащаем данными о танках
    var enriched = [];
    tanks.forEach(function (t) {
      if (!t.tank_id) return;
      var info = vehicleDb[t.tank_id];
      if (!info) return;

      var b = t.statistics && t.statistics.battles ? t.statistics.battles : 0;
      var w = t.statistics && t.statistics.wins ? t.statistics.wins : 0;
      var mastery = t.mark_of_mastery || 0;
      var dmg = t.statistics && t.statistics.damage_dealt ? t.statistics.damage_dealt : 0;
      var xp = t.statistics && t.statistics.xp ? t.statistics.xp : 0;
      var frags = t.statistics && t.statistics.frags ? t.statistics.frags : 0;
      var deaths = (b - (t.statistics && t.statistics.survived_battles ? t.statistics.survived_battles : 0)) || 1;

      enriched.push({
        id: t.tank_id,
        name: info.name,
        short_name: info.short_name,
        tier: info.tier,
        type: info.type,
        nation: info.nation,
        is_premium: info.is_premium,
        icon: info.images && info.images.small_icon ? info.images.small_icon : '',
        battles: b,
        winrate: b > 0 ? (w / b * 100) : 0,
        mastery: mastery,
        stats: t.statistics,
        marksOnGun: t.marksOnGun || 0,
        avgDmg: b > 0 ? (dmg / b) : 0,
        avgXp: b > 0 ? (xp / b) : 0,
        kd: deaths > 0 ? (frags / deaths) : frags
      });
    });

    // Сортируем по боям (убывание) по умолчанию
    enriched.sort(function (a, b) { return b.battles - a.battles; });

    var html = `
      <div class="table">
        <div class="table_inner table_inner__no-mobile-indent">
          <div class="table_head table_head__has-btn-right">
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-1 table_td__show-tablet js-sort" data-sort="nation"><span class="table_ico"><span class="ico-nation"></span></span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-2 table_td__show-tablet js-sort" data-sort="type"><span class="table_ico"><span class="ico-technic-type"></span></span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-3 table_td__show-tablet table_td__bold js-sort" data-sort="tier">I-XI<span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-wide table_td__no-mob-border table_td__paddings table_td__align-left js-sort" data-sort="name"><span class="table_td-text">Название техники</span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-role table_td__show-tablet js-sort" data-sort="role"><span class="table_td-text">Роль</span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-4 table_td__paddings js-sort js-tooltip" data-sort="battles" data-tooltip-text="Бои"><span class="table_ico"><span class="ico-stats ico-stats__btl-dark"></span></span><span class="table_col-title">TB</span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-4 table_td__paddings js-sort js-tooltip" data-sort="winrate" data-tooltip-text="Победы"><span class="table_ico"><span class="ico-win-rate"></span></span><span class="table_col-title">W/B</span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-4 table_td__paddings js-sort js-tooltip" data-sort="mastery" data-tooltip-text="Знаки классности"><span class="table_ico"><span class="ico-stats ico-stats__master-dark"></span></span><span class="table_col-title">MB</span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-4 table_td__paddings js-sort js-tooltip" data-sort="marks" data-tooltip-text="Отличительные отметки"><span class="table_ico"><span class="ico-stats ico-stats__marks-dark"></span></span><span class="table_col-title">MG</span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-4 table_td__paddings js-sort js-tooltip" data-sort="avgDmg" data-tooltip-text="Средний урон за бой"><span class="table_ico"><span class="ico-dmg-per-btl"></span></span><span class="table_col-title">D/B</span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-4 table_td__paddings js-sort js-tooltip" data-sort="avgXp" data-tooltip-text="Средний опыт за бой"><span class="table_ico"><span class="ico-stats ico-stats__exp-dark"></span></span><span class="table_col-title">E/B</span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
            <a href="#" class="table_td table_td__heading table_td__link table_td__size-4 table_td__paddings js-sort js-tooltip" data-sort="kd" data-tooltip-text="Уничтожил / Уничтожен"><span class="table_ico"><span class="ico-stats ico-stats__kd-dark"></span></span><span class="table_col-title">F/D</span><span class="table_arrow"><span class="ico-arrow"></span></span></a>
          </div>
          <div class="ps-vehicles-tbody" id="ps-vehicles-tbody">
    `;

    var tpl = document.getElementById('tpl-vehicle-row');
    if (tpl) {
        enriched.forEach(function (t) {
            var clone = tpl.content.cloneNode(true);
            var tr = clone.querySelector('.table_row');
            tr.dataset.tankId = t.id;

            // Nation flag
            var flag = clone.querySelector('.rastr-flag');
            flag.className = 'rastr-flag rastr-flag__ico-' + (t.nation || 'ussr').toLowerCase();
            
            // Type icon
            var tIconClass = 'ico-vehicle-type ico-vehicle-type__' + (t.type || 'mediumTank').toLowerCase();
            if (t.is_premium) tIconClass += '-prem';
            clone.querySelector('.ico-vehicle-type').className = tIconClass;

            // Tier
            clone.querySelector('.ps-tier-roman').textContent = TIER_ROMAN[t.tier] || t.tier;
            if (t.is_premium) clone.querySelector('.table_td__size-3').classList.add('table_td__prem');
            
            // Name & Icon
            var nameTd = clone.querySelector('.table_td__size-wide');
            if (t.is_premium) nameTd.classList.add('table_td__prem');
            var nameSpan = clone.querySelector('.ps-vehicle-name');
            nameSpan.textContent = t.short_name || t.name;
            var nameIconWrap = document.createElement('div');
            nameIconWrap.className = 'table_tank-img';
            if (t.icon) nameIconWrap.innerHTML = '<img src="' + esc(t.icon) + '">';
            nameTd.insertBefore(nameIconWrap, nameSpan);
            
            // Battles
            clone.querySelector('.ps-battles').textContent = fmt(t.battles);
            
            // Winrate
            clone.querySelector('.ps-winrate').textContent = t.winrate.toFixed(2).replace('.', ',') + '%';
            clone.querySelector('.table_td:nth-child(7)').innerHTML = '<span class="ps-winrate">' + t.winrate.toFixed(2).replace('.', ',') + '%</span><div class="table_progress"><div class="table_progress-inner table_progress-inner__' + (t.winrate >= 50 ? 'green' : 'yellow') + '" style="width: ' + t.winrate + '%"></div></div>';
            
            // Mastery
            var mSpan = clone.querySelector('.ps-mastery');
            mSpan.className = 'ico-ranks ' + (t.mastery === 4 ? 'ico-ranks__master' : (t.mastery > 0 ? 'ico-ranks__0' + Math.abs(t.mastery - 4) : ''));
            if(t.mastery === 0) mSpan.style.display = 'none';

            // Marks
            var markImg = clone.querySelector('.ps-marks');
            if (t.marksOnGun > 0) {
               markImg.src = '/static/images/marks/' + t.nation + '_' + t.marksOnGun + '_marks.png';
            } else {
               markImg.style.display = 'none';
            }
            
            // D/X/K
            clone.querySelector('.ps-dmg').textContent = fmt(Math.round(t.avgDmg));
            clone.querySelector('.ps-xp').textContent = fmt(Math.round(t.avgXp));
            clone.querySelector('.ps-kd').textContent = t.kd.toFixed(2).replace('.', ',');

            var tempDiv = document.createElement('div');
            tempDiv.appendChild(clone);
            html += tempDiv.innerHTML;
        });
    }

    html += `
          </div>
        </div>
      </div>
    `;

    return html;
  }

  function initBattleTypeDropdown(data) {
    var toggle = content.querySelector('.ps-battle-type-toggle');
    var wrapper = content.querySelector('.ps-dropdown');
    if (!toggle || !wrapper) return;

    // Открыть/закрыть dropdown
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      var isShown = wrapper.style.display !== 'none';
      wrapper.style.display = isShown ? 'none' : '';
      if (!isShown) {
        toggle.classList.add('profile-grid_info-link__opened');
      } else {
        toggle.classList.remove('profile-grid_info-link__opened');
      }
    });

    document.addEventListener('click', function(e) {
      if (!toggle.contains(e.target) && !wrapper.contains(e.target)) {
        wrapper.style.display = 'none';
        toggle.classList.remove('profile-grid_info-link__opened');
      }
    });

    var items = wrapper.querySelectorAll('.ps-dropdown-item');
    items.forEach(function(item) {
      item.addEventListener('click', function() {
        items.forEach(function(i) { i.classList.remove('select-list_item__active'); });
        this.classList.add('select-list_item__active');
        var statKey = this.dataset.statKey;
        var label = this.textContent;
        toggle.textContent = label;
        wrapper.style.display = 'none';
        toggle.classList.remove('profile-grid_info-link__opened');

        var info = data.info;
        var stats = info.statistics && info.statistics[statKey] || {};
        var b = stats.battles || 0;
        var ad = b ? Math.round((stats.damage_dealt || 0) / b) : 0;
        var ax = stats.battle_avg_xp || 0;

        var mastery = { 4: 0, 3: 0, 2: 0, 1: 0 };
        var totalTanks = 0;
        if (data.tanks && Array.isArray(data.tanks)) {
          totalTanks = data.tanks.length;
          data.tanks.forEach(function(t) {
            if (t.mark_of_mastery) mastery[t.mark_of_mastery] = (mastery[t.mark_of_mastery] || 0) + 1;
          });
        }

        var blockHtml = renderStatsBlock(stats, b, ad, ax, mastery, totalTanks, info.global_rating);
        var statsInner = document.getElementById('ps-stats-inner');
        if (statsInner) {
          statsInner.innerHTML = blockHtml;
        }
      });
    });
  }

  function initAchievements() {
    var btnShow = document.querySelector('.js-ps-ach-show-all');
    var btnHide = document.querySelector('.js-ps-ach-hide');
    var shortView = document.querySelector('.ps-ach-short');
    var fullView = document.querySelector('.ps-ach-full');

    if (btnShow && shortView && fullView) {
      btnShow.addEventListener('click', function () {
        shortView.style.display = 'none';
        fullView.style.display = '';
      });
    }
    if (btnHide && shortView && fullView) {
      btnHide.addEventListener('click', function () {
        fullView.style.display = 'none';
        shortView.style.display = '';
      });
    }
  }

  function initTooltips() {
    var tooltips = document.querySelectorAll('.js-tooltip');
    tooltips.forEach(function(el) {
      var tooltip = el.querySelector('.small-tooltip');
      if (tooltip) {
        el.addEventListener('mouseenter', function() {
          tooltip.style.display = 'block';
          tooltip.style.opacity = '1';
        });
        el.addEventListener('mouseleave', function() {
          tooltip.style.display = 'none';
          tooltip.style.opacity = '0';
        });
      }
    });
  }



  function esc(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // Запуск
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
