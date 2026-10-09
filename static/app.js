(function () {
  "use strict";

  // telegram-web-app.js создаёт window.Telegram.WebApp ДАЖЕ в обычном браузере
  // (platform="unknown", initData=""). Поэтому проверяем реальные признаки Mini App,
  // иначе в вебе ошибочно включается телеграм-ветка: не спрашивается имя и ссылки
  // открываются в текущем окне, «убивая» игру.
  const telegramWebApp = (window.Telegram && window.Telegram.WebApp) || null;
  const isTelegram = !!(
    telegramWebApp &&
    (telegramWebApp.initData ||
      (telegramWebApp.platform && telegramWebApp.platform !== "unknown"))
  );
  const tg = isTelegram ? telegramWebApp : null;
  if (tg) { try { tg.ready(); tg.expand(); } catch (e) {} }
  const Sound = window.Sound || {
    play() {}, unlock() {}, toggle() { return false; }, muted: true,
  };

  // Профиль из initData — отправляем на сервер, чтобы соперник увидел @username и аватар.
  const tgUser = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || null;
  const tgProfile = tgUser
    ? {
        username: tgUser.username || null,
        name: [tgUser.first_name, tgUser.last_name].filter(Boolean).join(" ") || null,
        photo_url: tgUser.photo_url || null,
      }
    : null;

  const $ = (id) => document.getElementById(id);
  const screens = { lobby: $("lobby"), game: $("game") };
  const battleOverlay = $("battle");
  const overtimeOverlay = $("overtime");
  const rpOwn = $("rp-own");
  const rpEnemy = $("rp-enemy");
  const battleCard = $("battle-card");
  const bbOwnTitle = $("bb-own-title");
  const bbEnemyTitle = $("bb-enemy-title");
  const battleShare = $("battle-share");
  const rpOt = $("rp-ot");
  const bbMain = $("bb-main");
  const bbOt = $("bb-ot");
  const lgYour = $("lg-your");
  const lgEnemy = $("lg-enemy");
  const btnCancel = $("btn-cancel");
  const btnBot = $("btn-bot");
  const btnCreate = $("btn-create");
  const btnInviteCancel = $("btn-invite-cancel");
  const btnQuick = $("btn-quick");
  const ownBoard = $("own-board");
  const enemyBoard = $("enemy-board");
  const banner = $("banner");
  const timerFill = $("timer-fill");
  const timerText = $("timer-text");
  const fireBtn = $("btn-fire");
  const selectedCount = $("selected-count");
  const lobbyStatus = $("lobby-status-text");
  const lobbyCode = $("lobby-code");
  const roomInfo = $("room-info");
  const enemyTitle = $("enemy-title");
  const hintEl = $("hint");
  const btnSound = $("btn-sound");
  const scoreUs = $("score-us");
  const scoreThem = $("score-them");
  const battleRounds = $("battle-rounds");
  const bbStatsUs = $("bb-stats-us");
  const bbStatsThem = $("bb-stats-them");
  const bbStatsOt = $("bb-stats-ot");
  const bbWhoOt = $("bb-who-ot");
  const bbWhoEnemy = $("bb-who-enemy");
  const bbWhoMe = $("bb-who-me");
  const battleResult = $("battle-result");
  // Профиль для сервера: в Telegram — из initData, в браузере — введённое имя.
  // Соперник увидит его в боевом отчёте (иначе был бы просто «игрок»).
  const nameModal = $("name-modal");
  const nameField = $("name-field");
  let pendingAction = null;

  function savedName() {
    try { return (localStorage.getItem("seablitz_name") || "").trim().slice(0, 24); }
    catch (e) { return ""; }
  }
  function currentProfile() {
    if (tgProfile) return tgProfile;
    const name = savedName();
    return name ? { name: name } : null;
  }
  function showNameModal() {
    if (!nameModal) return;
    nameField.value = savedName();
    nameModal.classList.add("active");
    setTimeout(() => { try { nameField.focus(); } catch (e) {} }, 60);
  }
  function hideNameModal() {
    if (nameModal) nameModal.classList.remove("active");
  }
  function submitName() {
    const name = nameField ? nameField.value.trim().slice(0, 24) : "";
    try { localStorage.setItem("seablitz_name", name); } catch (e) {}
    hideNameModal();
    const action = pendingAction;
    pendingAction = null;
    if (action) action();
  }
  // В браузере спрашиваем имя перед действием, если оно ещё не задано.
  function requireName(action) {
    if (isTelegram || savedName()) { action(); return; }
    pendingAction = action;
    showNameModal();
  }
  if (nameField) {
    $("name-ok").addEventListener("click", submitName);
    nameField.addEventListener("keydown", (e) => { if (e.key === "Enter") submitName(); });
  }
  // Маленькая кнопка «Изменить имя» рядом со звуком — только в вебе
  // (в Telegram имя берётся из профиля и не редактируется здесь).
  const btnName = $("btn-name");
  if (btnName) {
    if (isTelegram) {
      btnName.hidden = true;
    } else {
      btnName.hidden = false;
      btnName.addEventListener("click", () => { pendingAction = null; showNameModal(); });
    }
  }

  let ws = null;
  let mySlot = null;
  let roomCode = null;
  let roomPlayers = [];
  let lastFinal = null;
  let shotsPerRound = 3;
  let selectable = false;
  const selected = new Set();
  let rafId = null;
  let countdownId = null;
  let myRematch = false;
  let oppRematch = false;
  let shareUrl = "https://t.me/seablitz_bot";
  let searching = false;

  function showScreen(name) {
    Object.values(screens).forEach((s) => s.classList.remove("active"));
    screens[name].classList.add("active");
  }

  function haptic(kind) {
    const h = tg && tg.HapticFeedback;
    if (!h) return;
    try {
      if (kind === "hit") h.impactOccurred("heavy");
      else if (kind === "miss") h.impactOccurred("light");
      else if (kind === "select") h.selectionChanged();
      else if (kind === "win") h.notificationOccurred("success");
      else h.notificationOccurred("error");
    } catch (e) {}
  }

  function buildGrid(el) {
    el.innerHTML = "";
    for (let r = 0; r < 5; r++) {
      for (let c = 0; c < 5; c++) {
        const d = document.createElement("div");
        d.className = "cell";
        d.dataset.r = r;
        d.dataset.c = c;
        el.appendChild(d);
      }
    }
  }
  buildGrid(ownBoard);
  buildGrid(enemyBoard);
  buildGrid(rpOwn);
  buildGrid(rpEnemy);
  buildGrid(rpOt);

  const key = (r, c) => r + ":" + c;
  const cellAt = (el, r, c) => el.children[r * 5 + c];

  function clearBoard(el) {
    for (const cell of Array.from(el.children)) cell.className = "cell";
  }

  function animate(el, cls) {
    el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), 500);
  }

  function setBanner(text, draw) {
    banner.textContent = text || "";
    banner.classList.toggle("draw", !!draw);
  }

  function updateFire() {
    selectedCount.textContent = "Выбрано " + selected.size + "/" + shotsPerRound;
    fireBtn.disabled = !selectable || selected.size === 0;
    if (selected.size >= shotsPerRound) hideHint();
  }

  function showHint(text) { hintEl.textContent = text; }
  function hideHint() { hintEl.textContent = ""; }

  // --- счёт подбитых палуб (нижняя строка игрового экрана) ---
  // Считаем попадания (не промахи): в основном бою — по outcome, в тайбрейке — по hit.
  function countHits(shots) {
    return (shots || []).filter(
      (s) => s.hit === true || (s.outcome && s.outcome !== "miss")
    ).length;
  }

  function setScore(weHit, theyHit, total) {
    const t = total || 6;
    if (scoreUs) scoreUs.textContent = weHit + "/" + t;
    if (scoreThem) scoreThem.textContent = theyHit + "/" + t;
  }

  function updateScore(view) {
    if (!view) return;
    const ships = view.your_ships || [];
    const total = ships.reduce((n, ship) => n + ship.length, 0) || 6;
    setScore(countHits(view.your_shots), countHits(view.enemy_shots), total);
  }

  // Состояние лобби: идёт поиск / создана комната -> лишние кнопки тускнеют.
  function updateLobbyState() {
    const inRoom = !!roomCode;
    btnCancel.hidden = !searching;
    const inviteBox = $("invite-box");
    if (inviteBox) inviteBox.hidden = !inRoom;
    if (lobbyCode) {
      lobbyCode.textContent = inRoom ? roomCode.toUpperCase() : "";
      lobbyCode.hidden = !inRoom;
    }
    btnInviteCancel.hidden = !inRoom;
    const busy = inRoom || searching;
    btnQuick.disabled = busy;
    btnCreate.disabled = busy;
    btnBot.disabled = busy;
  }

  function resetSelection() {
    selected.clear();
    for (const cell of Array.from(enemyBoard.children)) cell.classList.remove("selected");
    selectable = true;
    hideHint();
    updateFire();
  }

  function lockSelection() {
    selectable = false;
    updateFire();
  }

  function startTimer(ms) {
    if (rafId) cancelAnimationFrame(rafId);
    const end = performance.now() + ms;
    const tick = (now) => {
      const left = Math.max(0, end - now);
      timerFill.style.width = (left / ms) * 100 + "%";
      timerText.textContent = (left / 1000).toFixed(1);
      if (left > 0) rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
  }

  // Закрашивает результат выстрела; при потоплении — весь корабль тёмно-красным.
  function markShot(gridEl, s) {
    const cell = cellAt(gridEl, s.cell[0], s.cell[1]);
    cell.classList.add(s.outcome === "miss" ? "miss" : "hit");
    if (s.outcome === "sunk" && s.ship) {
      s.ship.forEach(([r, c]) => cellAt(gridEl, r, c).classList.add("sunk"));
    }
  }

  function renderOwn(view) {
    clearBoard(ownBoard);
    (view.your_ships || []).forEach((ship) =>
      ship.forEach(([r, c]) => cellAt(ownBoard, r, c).classList.add("ship"))
    );
    (view.enemy_shots || []).forEach((s) => markShot(ownBoard, s));
  }

  function renderEnemy(view) {
    clearBoard(enemyBoard);
    (view.your_shots || []).forEach((s) => markShot(enemyBoard, s));
    selected.forEach((k) => {
      const parts = k.split(":");
      cellAt(enemyBoard, +parts[0], +parts[1]).classList.add("selected");
    });
  }

  enemyBoard.addEventListener("click", (e) => {
    const cell = e.target.closest(".cell");
    if (!cell || !selectable) return;
    if (cell.classList.contains("hit") || cell.classList.contains("miss")) return;
    const k = key(+cell.dataset.r, +cell.dataset.c);
    if (selected.has(k)) {
      selected.delete(k);
      cell.classList.remove("selected");
    } else if (selected.size < shotsPerRound) {
      selected.add(k);
      cell.classList.add("selected");
      haptic("select");
      Sound.play("select");
    }
    updateFire();
  });

  function playShot(gridEl, s) {
    const cell = cellAt(gridEl, s.cell[0], s.cell[1]);
    const cls =
      s.outcome === "miss" ? "anim-miss" : s.outcome === "sunk" ? "anim-sunk" : "anim-hit";
    animate(cell, cls);
    if (s.outcome === "sunk") {
      gridEl.classList.add("shake");
      setTimeout(() => gridEl.classList.remove("shake"), 360);
    }
  }

  function animateShots(msg) {
    const yours = msg.your_shots || [];
    const theirs = msg.enemy_shots || [];
    yours.forEach((s) => playShot(enemyBoard, s));
    theirs.forEach((s) => playShot(ownBoard, s));

    const all = yours.concat(theirs);
    if (all.some((s) => s.outcome === "sunk")) { Sound.play("sunk"); haptic("hit"); }
    else if (all.some((s) => s.outcome !== "miss")) { Sound.play("hit"); haptic("hit"); }
    else if (all.length) { Sound.play("miss"); haptic("miss"); }
  }

  function renderTiebreak(msg) {
    clearBoard(enemyBoard);
    (msg.ships || []).forEach(([r, c]) => cellAt(enemyBoard, r, c).classList.add("ship"));
    (msg.your_shots || []).forEach((s) => {
      const cell = cellAt(enemyBoard, s.cell[0], s.cell[1]);
      cell.classList.add(s.hit ? "hit" : "miss");
      cell.classList.add("your-shot");
    });
    (msg.enemy_shots || []).forEach((s) => {
      cellAt(enemyBoard, s.cell[0], s.cell[1]).classList.add("enemy-shot");
    });
    const line = "Золотой раунд: вы " + msg.your_hits + " : " + msg.enemy_hits + " соперник";
    if (msg.need_repeat) setBanner("НИЧЬЯ! Ещё один «Золотой раунд»", true);
    else setBanner(line, false);
  }

  function hideOverlays() {
    battleOverlay.classList.remove("active");
    overtimeOverlay.classList.remove("active");
    if (countdownId) { clearInterval(countdownId); countdownId = null; }
  }

  function startCountdown(el, ms) {
    if (countdownId) { clearInterval(countdownId); countdownId = null; }
    const end = Date.now() + ms;
    const render = () => {
      const left = Math.max(0, end - Date.now());
      el.textContent = left > 0 ? "Дальше через " + Math.ceil(left / 1000) + " с…" : "";
      if (left <= 0) { clearInterval(countdownId); countdownId = null; }
    };
    render();
    countdownId = setInterval(render, 250);
  }

  function renderReveal(gridEl, ships, shots) {
    clearBoard(gridEl);
    (ships || []).forEach((ship) =>
      ship.forEach(([r, c]) => cellAt(gridEl, r, c).classList.add("ship"))
    );
    (shots || []).forEach((s) => markShot(gridEl, s));
  }

  function updateRematchUI() {
    const btn = $("battle-continue");
    const note = $("battle-note");
    if (myRematch) {
      btn.disabled = true;
      btn.textContent = "Ожидаем соперника…";
      note.textContent = "Вы предложили реванш.";
    } else if (oppRematch) {
      btn.disabled = false;
      btn.textContent = "ПРИНЯТЬ РЕВАНШ";
      note.textContent = "⚔️ Соперник предлагает реванш!";
    } else {
      btn.disabled = false;
      btn.textContent = "РЕВАНШ";
      note.textContent = "";
    }
  }

  function requestRematch() {
    if (myRematch) return;
    myRematch = true;
    Sound.play("rematch");
    send({ type: "rematch" });
    updateRematchUI();
  }

  // Поле овертайма: один флот + выстрелы обоих (рамка отличает владельца).
  function renderOvertimeBoard(pic) {
    clearBoard(rpOt);
    (pic.ships || []).forEach(([r, c]) => cellAt(rpOt, r, c).classList.add("ship"));
    (pic.your_shots || []).forEach((s) => {
      const cell = cellAt(rpOt, s.cell[0], s.cell[1]);
      cell.classList.add(s.hit ? "hit" : "miss");
      cell.classList.add("your-shot");
    });
    (pic.enemy_shots || []).forEach((s) => {
      const cell = cellAt(rpOt, s.cell[0], s.cell[1]);
      cell.classList.add(s.hit ? "hit" : "miss");
      cell.classList.add("enemy-shot");
    });
  }

  // Строка статистики: подпись + число (наши попадания — зелёные, врага — красные).
  function sideLine(label, hits, shots, tone) {
    return (
      '<div class="side-line"><span class="side-label">' + label + '</span>' +
      '<span class="side-value ' + tone + '">' + hits + "/" + shots + "</span></div>"
    );
  }

  // Обе строки подряд (для общего поля овертайма).
  function sideStatsHtml(yourHits, yourShots, enemyHits, enemyShots) {
    return (
      sideLine("Ваши попадания", yourHits, yourShots, "good") +
      sideLine("Попадания врага", enemyHits, enemyShots, "bad")
    );
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  // Карточка игрока справа от поля: имя в рамке (цвет зависит от роли).
  function whoCard(player, tone) {
    if (!player) return "";
    const label = player.username ? "@" + player.username : (player.name || "игрок");
    return (
      '<div class="who-card ' + (tone || "") + '">' +
      '<span class="who-name">' + esc(label) + "</span>" +
      "</div>"
    );
  }

  // Картина сражения. final => экран результата: картина основного боя,
  // либо (если решил овертайм) расклад «Золотого раунда».
  function showBattle(msg) {
    const final = !!msg.final;
    hideOverlays();
    battleCard.classList.remove("win", "lose", "draw");
    battleShare.hidden = true;

    if (msg.mode === "tiebreak" && msg.picture) {
      const pic = msg.picture;
      bbMain.hidden = true;
      bbOt.hidden = false;
      lgYour.hidden = false;
      lgEnemy.hidden = false;
      renderOvertimeBoard(pic);
      const yShots = pic.your_shots || [];
      const eShots = pic.enemy_shots || [];
      if (bbStatsOt) bbStatsOt.innerHTML = sideStatsHtml(
        countHits(yShots), yShots.length, countHits(eShots), eShots.length
      );
      // Справа: сверху — вы, под вами — соперник.
      const meOt = roomPlayers.find((p) => p && p.slot === mySlot) || null;
      const foeOt = roomPlayers.find((p) => p && p.slot !== mySlot) || null;
      if (bbWhoOt) bbWhoOt.innerHTML = whoCard(meOt, "me") + whoCard(foeOt, "foe");
      if (battleRounds) battleRounds.textContent = "Золотой раунд " + (pic.round || 1);
    } else {
      const view = msg.view || {};
      const st = view.stats || {};
      bbMain.hidden = false;
      bbOt.hidden = true;
      lgYour.hidden = true;
      lgEnemy.hidden = true;
      bbOwnTitle.textContent = "Ваш флот";
      bbEnemyTitle.textContent = "Флот врага";
      renderReveal(rpOwn, view.your_ships, view.enemy_shots);
      renderReveal(rpEnemy, view.enemy_ships, view.your_shots);
      // Подписи слева напротив своих полей: враг (сверху) — наши попадания,
      // наш флот (снизу) — попадания врага.
      if (bbStatsUs) bbStatsUs.innerHTML =
        sideLine("Ваши попадания", st.your_hits || 0, st.your_shots || 0, "good");
      if (bbStatsThem) bbStatsThem.innerHTML =
        sideLine("Попадания врага", st.enemy_hits || 0, st.enemy_shots || 0, "bad");
      // Справа — кто есть кто: напротив флота врага соперник, напротив своего — вы.
      const me = roomPlayers.find((p) => p && p.slot === mySlot) || null;
      const foe = roomPlayers.find((p) => p && p.slot !== mySlot) || null;
      if (bbWhoEnemy) bbWhoEnemy.innerHTML = whoCard(foe, "foe");
      if (bbWhoMe) bbWhoMe.innerHTML = whoCard(me, "me");
      if (battleRounds) battleRounds.textContent =
        "Раундов: " + (st.rounds || 0) +
        (st.tiebreak_rounds ? " · «Золотых»: " + st.tiebreak_rounds : "");
    }

    const btn = $("battle-continue");
    if (final) {
      if (msg.share_url) shareUrl = msg.share_url;
      haptic(msg.you_won ? "win" : "lose");
      Sound.play(msg.you_won ? "win" : "lose");
      battleCard.classList.add(msg.you_won ? "win" : "lose");
      $("battle-title").textContent = msg.you_won ? "ПОБЕДА!" : "ПОРАЖЕНИЕ";
      if (battleResult) battleResult.textContent = msg.you_won
        ? (msg.mode === "tiebreak" ? "Вы выиграли «Золотой раунд»." : "Флот врага уничтожен.")
        : (msg.mode === "tiebreak" ? "Вы проиграли «Золотой раунд»." : "Ваш флот уничтожен.");
      $("battle-count").textContent = "";
      $("battle-exit").style.display = "";
      battleShare.hidden = false;
      battleShare.textContent = msg.you_won ? "📣 Поделиться победой" : "📣 Поделиться игрой";
      myRematch = false;
      oppRematch = false;
      btn.onclick = requestRematch;
      updateRematchUI();
    } else {
      const isDraw = !!msg.draw;
      if (isDraw) battleCard.classList.add("draw");
      $("battle-title").textContent = isDraw ? "НИЧЬЯ" : "⚓ Боевой отчёт";
      if (battleResult) battleResult.textContent = "";
      $("battle-exit").style.display = "none";
      $("battle-note").textContent = isDraw
        ? "Оба флота уничтожены — «Золотой раунд»"
        : "";
      btn.disabled = false;
      btn.textContent = "Продолжить";
      btn.onclick = () => { hideOverlays(); send({ type: "ready" }); };
      if (msg.gate_ms) startCountdown($("battle-count"), msg.gate_ms);
    }
    battleOverlay.classList.add("active");
  }

  function showOvertime(msg) {
    const btn = $("ot-start");
    btn.onclick = () => { hideOverlays(); send({ type: "ready" }); };
    overtimeOverlay.classList.add("active");
    if (msg.gate_ms) startCountdown($("ot-count"), msg.gate_ms);
    else $("ot-count").textContent = "";
    Sound.play("overtime");
    haptic("select");
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case "joined":
        searching = false;
        mySlot = msg.slot;
        roomCode = msg.code;
        updateLobbyState();
        break;
      case "waiting":
        if (msg.share_url) shareUrl = msg.share_url;
        if (msg.code) {
          searching = false;
          roomCode = msg.code;
          lobbyStatus.textContent = "Ждём соперника…";
        } else {
          searching = true;
          roomCode = null;
          lobbyStatus.textContent = "Ищем соперника…";
        }
        updateLobbyState();
        break;
      case "search_cancelled":
        searching = false;
        updateLobbyState();
        lobbyStatus.textContent = "Поиск отменён.";
        break;
      case "search_timeout":
        if (msg.share_url) shareUrl = msg.share_url;
        lobbyStatus.textContent =
          "Соперник не нашёлся. Создай вызов другу ⚔️ или сыграй с ботом 🤖";
        break;
      case "left_room":
        roomCode = null;
        updateLobbyState();
        lobbyStatus.textContent = "Вызов отменён.";
        break;
      case "error":
        lobbyStatus.textContent = "Комната недоступна, попробуйте другую.";
        break;
      case "state":
        showScreen("game");
        hideOverlays();
        if (msg.slot != null) mySlot = msg.slot;
        roomPlayers = msg.players || [];
        renderOwn(msg.view);
        renderEnemy(msg.view);
        updateScore(msg.view);
        lockSelection();
        break;
      case "round_start":
        hideOverlays();
        shotsPerRound = msg.shots || 3;
        enemyTitle.textContent = "Поле врага";
        setBanner("Раунд " + msg.round + ": выберите " + shotsPerRound + " клетки");
        startTimer(msg.timeout_ms);
        resetSelection();
        break;
      case "round_result":
        lockSelection();
        renderOwn(msg.view);
        renderEnemy(msg.view);
        updateScore(msg.view);
        animateShots(msg);
        if (msg.needs_tiebreak) setBanner("⚔️ Обоюдный залп! Золотой раунд");
        else setBanner("Раунд " + msg.round + ": попаданий — " + msg.your_hits);
        break;
      case "tiebreak_start":
        hideOverlays();
        shotsPerRound = msg.shots || 3;
        enemyTitle.textContent = "Общее поле (тайбрейк)";
        setBanner("⚔️ Золотой раунд " + msg.round + ": у кого больше попаданий");
        startTimer(msg.timeout_ms);
        clearBoard(enemyBoard);
        setScore(0, 0, msg.ships_total);
        resetSelection();
        break;
      case "tiebreak_result":
        lockSelection();
        renderTiebreak(msg);
        setScore(
          countHits(msg.your_shots),
          countHits(msg.enemy_shots),
          (msg.ships || []).length
        );
        break;
      case "game_over":
        msg.final = true;  // финальный бой — всегда экран результата
        lastFinal = msg;
        showBattle(msg);
        break;
      case "battle_report":
        showBattle(msg);
        break;
      case "overtime_intro":
        showOvertime(msg);
        break;
      case "opponent_locked":
        if (selectable) setBanner("Соперник отстрелялся — ваш залп!");
        break;
      case "rematch_request":
        oppRematch = true;
        updateRematchUI();
        break;
      case "rematch_start":
        myRematch = false;
        oppRematch = false;
        hideOverlays();
        break;
      case "opponent_left":
        lockSelection();
        setBanner("Соперник покинул бой");
        break;
    }
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(proto + "://" + location.host + "/ws");
    ws.onopen = () => { lobbyStatus.textContent = "Подключено."; };
    ws.onmessage = (ev) => {
      try {
        handleMessage(JSON.parse(ev.data));
      } catch (e) {
        // Не глотаем молча: одна ошибка не должна «вешать» весь экран.
        console.error("SeaBlitz: ошибка обработки сообщения", e);
      }
    };
    ws.onclose = () => {
      lobbyStatus.textContent = "Соединение закрыто. Обновите страницу.";
    };
  }

  fireBtn.addEventListener("click", () => {
    if (!selectable || selected.size === 0) return;
    if (selected.size < shotsPerRound) {
      showHint("Выбирайте до трёх целей за залп!");  // залп всё равно уйдёт
    } else {
      hideHint();
    }
    const cells = Array.from(selected).map((k) => k.split(":").map(Number));
    send({ type: "volley", cells: cells });
    Sound.play("fire");
    lockSelection();
    setBanner("Залп сделан. Ждём соперника…");
  });

  $("btn-quick").addEventListener("click", () => {
    requireName(() => {
      searching = true;
      updateLobbyState();
      lobbyStatus.textContent = "Ищем соперника…";
      send({ type: "quickmatch", user: currentProfile() });
    });
  });

  btnCancel.addEventListener("click", () => {
    searching = false;
    updateLobbyState();
    lobbyStatus.textContent = "Поиск отменён.";
    send({ type: "cancel" });
  });

  btnBot.addEventListener("click", () => {
    requireName(() => {
      lobbyStatus.textContent = "Готовим тренировочный бой…";
      send({ type: "play_bot", user: currentProfile() });
    });
  });

  btnInviteCancel.addEventListener("click", () => {
    roomCode = null;
    updateLobbyState();
    lobbyStatus.textContent = "Вызов отменён.";
    send({ type: "leave_room" });
  });

  function randomCode(len) {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let s = "";
    for (let i = 0; i < len; i++) s += chars[Math.floor(Math.random() * chars.length)];
    return s;
  }

  $("btn-create").addEventListener("click", () => {
    requireName(() => {
      lobbyStatus.textContent = "Создаём комнату…";
      send({ type: "join", code: randomCode(4), user: currentProfile() });
    });
  });

  // Ссылка внутри Telegram: открывает полноэкранный Mini App нужной комнаты.
  function inviteTelegramLink() {
    const base = shareUrl || "https://t.me/seablitz_bot";
    return roomCode
      ? base + "?startapp=" + encodeURIComponent(roomCode.toUpperCase())
      : base;
  }

  // Веб-ссылка-вызов: работает в любом браузере (в т.ч. без Telegram).
  // /room/<CODE> отдаёт OG-превью для мессенджера и ведёт прямо в комнату.
  function inviteWebLink() {
    return roomCode
      ? location.origin + "/room/" + roomCode.toUpperCase()
      : location.origin;
  }

  function inviteText() {
    return "⚔️ Вызываю на морскую дуэль SeaBlitz! Открой ссылку и вступай:";
  }

  // Открыть внешнюю ссылку в отдельном окне/вкладке, не теряя игру.
  // window.open синхронно из клика + запасной вариант через <a target="_blank">.
  function openNewTab(url) {
    let w = null;
    try { w = window.open(url, "_blank", "noopener"); } catch (e) {}
    if (!w) {
      try {
        const a = document.createElement("a");
        a.href = url; a.target = "_blank"; a.rel = "noopener";
        document.body.appendChild(a); a.click(); a.remove();
      } catch (e) {}
    }
  }

  // Открыть внешнюю ссылку, не закрывая игру/Mini App: внутри Telegram — через
  // WebApp.openLink (открывает системный браузер), иначе — новую вкладку.
  function openExternal(url) {
    if (tg && typeof tg.openLink === "function") {
      try { tg.openLink(url); return; } catch (e) {}
    }
    openNewTab(url);
  }

  function shareWhatsApp() {
    if (!roomCode) return;
    Sound.play("select");
    const link = inviteWebLink();
    const waUrl = "https://wa.me/?text=" + encodeURIComponent(inviteText() + " " + link);
    // Внутри Telegram на мобильных надёжнее нативный share-sheet (в нём есть
    // WhatsApp), чем tg.openLink: тот открывает wa.me во встроенном браузере
    // Telegram и не всегда запускает приложение WhatsApp.
    if (tg && navigator.share) {
      navigator.share({ title: "SeaBlitz", text: inviteText(), url: link }).catch((err) => {
        // Закрытие шторки самим пользователем — не ошибка, ничего не делаем.
        if (err && err.name === "AbortError") return;
        openExternal(waUrl);
      });
      return;
    }
    // Десктоп (Telegram/веб) — wa.me во внешнем браузере / новой вкладке.
    openExternal(waUrl);
  }

  function copyInviteLink() {
    if (!roomCode) return;
    Sound.play("select");
    const link = inviteWebLink();
    const done = () => { lobbyStatus.textContent = "Ссылка-вызов скопирована: " + link; };
    const manual = () => { lobbyStatus.textContent = "Ссылка-вызов: " + link; };
    // Запасной путь: скрытый textarea + execCommand("copy"). Нужен внутри Telegram,
    // где Clipboard API запрещён (iframe без права clipboard-write) и промис падает.
    const legacyCopy = () => {
      try {
        const ta = document.createElement("textarea");
        ta.value = link;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.top = "-1000px";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        ta.setSelectionRange(0, link.length);
        const ok = document.execCommand("copy");
        ta.remove();
        ok ? done() : manual();
      } catch (e) {
        manual();
      }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link).then(done, legacyCopy);
    } else {
      legacyCopy();
    }
  }

  function inviteFriend() {
    if (!roomCode) return;
    Sound.play("select");
    const link = inviteTelegramLink();
    // Диалог «Поделиться» в Telegram: выбор чата → отправка карточки-вызова.
    const shareUrl =
      "https://t.me/share/url?url=" + encodeURIComponent(link) +
      "&text=" + encodeURIComponent(inviteText() + " " + link);
    // Внутри Telegram — нативный диалог (Mini App остаётся открыт).
    if (tg && tg.openTelegramLink) {
      tg.openTelegramLink(shareUrl);
      return;
    }
    // В вебе открываем Telegram-шаринг в отдельном окне/вкладке — игра не закрывается.
    openNewTab(shareUrl);
  }
  $("btn-invite").addEventListener("click", inviteFriend);
  $("btn-whatsapp").addEventListener("click", shareWhatsApp);
  $("btn-copy").addEventListener("click", copyInviteLink);

  $("btn-join").addEventListener("click", () => {
    const code = ($("code-input").value || "").trim().toUpperCase();
    if (!code) { lobbyStatus.textContent = "Введите код комнаты."; return; }
    requireName(() => send({ type: "join", code: code, user: currentProfile() }));
  });

  $("battle-exit").addEventListener("click", () => {
    send({ type: "leave" });
    location.reload();
  });

  // ---------- Итоговая картинка для кнопки «Поделиться победой» ----------
  function playerLabel(p) {
    if (!p) return "игрок";
    return p.username ? "@" + p.username : (p.name || "игрок");
  }

  function rr(ctx, x, y, w, h, rad) {
    ctx.beginPath();
    ctx.moveTo(x + rad, y);
    ctx.arcTo(x + w, y, x + w, y + h, rad);
    ctx.arcTo(x + w, y + h, x, y + h, rad);
    ctx.arcTo(x, y + h, x, y, rad);
    ctx.arcTo(x, y, x + w, y, rad);
    ctx.closePath();
  }

  function star6(ctx, cx, cy, r) {
    ctx.save();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 5;
    ctx.lineCap = "round";
    for (let i = 0; i < 3; i++) {
      const a = (Math.PI / 3) * i;
      ctx.beginPath();
      ctx.moveTo(cx - Math.cos(a) * r, cy - Math.sin(a) * r);
      ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
      ctx.stroke();
    }
    ctx.restore();
  }

  function boardMarks(ships, shots) {
    const marks = {};
    (ships || []).forEach((ship) =>
      ship.forEach(([r, c]) => { marks[r + ":" + c] = "ship"; })
    );
    (shots || []).forEach((s) => {
      const [r, c] = s.cell;
      marks[r + ":" + c] = (s.outcome && s.outcome !== "miss") ? "hit" : "miss";
    });
    return marks;
  }

  function shareBoards(msg) {
    if (msg.mode === "tiebreak" && msg.picture) {
      const pic = msg.picture;
      const marks = {};
      (pic.ships || []).forEach(([r, c]) => { marks[r + ":" + c] = "ship"; });
      [pic.your_shots, pic.enemy_shots].forEach((arr) =>
        (arr || []).forEach((s) => {
          const [r, c] = s.cell;
          marks[r + ":" + c] = s.hit ? "hit" : "miss";
        })
      );
      return [{ title: "Общее поле", marks }];
    }
    const view = msg.view || {};
    return [
      { title: "Флот врага", marks: boardMarks(view.enemy_ships, view.your_shots) },
      { title: "Ваш флот", marks: boardMarks(view.your_ships, view.enemy_shots) },
    ];
  }

  function drawBoard(ctx, x, y, size, marks) {
    const gap = 6;
    const cell = (size - gap * 4) / 5;
    for (let r = 0; r < 5; r++) {
      for (let c = 0; c < 5; c++) {
        const cx = x + c * (cell + gap);
        const cy = y + r * (cell + gap);
        const m = marks[r + ":" + c];
        let fill = "#0f2a3d";
        if (m === "ship") fill = "#6b7c8c";
        else if (m === "hit") fill = "#e23b22";
        else if (m === "miss") fill = "#2b4a63";
        rr(ctx, cx, cy, cell, cell, 10);
        ctx.fillStyle = fill;
        ctx.fill();
        if (m === "hit") star6(ctx, cx + cell / 2, cy + cell / 2, cell * 0.22);
        else if (m === "miss") {
          ctx.beginPath();
          ctx.arc(cx + cell / 2, cy + cell / 2, 4, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(180,205,225,.55)";
          ctx.fill();
        }
      }
    }
  }

  function wrapLeft(ctx, text, x, y, maxWidth, lh) {
    const words = String(text).split(" ");
    let line = "";
    let ly = y;
    for (const w of words) {
      const test = line ? line + " " + w : w;
      if (ctx.measureText(test).width > maxWidth && line) {
        ctx.fillText(line, x, ly);
        line = w;
        ly += lh;
      } else {
        line = test;
      }
    }
    if (line) ctx.fillText(line, x, ly);
  }

  // Карточка игрока в шарещейся картинке: имя в рамке (цвет — роль).
  function drawWhoCard(ctx, cx, cy, player, color) {
    const label = playerLabel(player);
    const font = "22px 'Segoe UI', Roboto, sans-serif";
    ctx.font = font;
    const maxW = 150;
    const words = String(label).split(" ");
    const lines = [];
    let line = "";
    for (const w of words) {
      const test = line ? line + " " + w : w;
      if (ctx.measureText(test).width > maxW && line) { lines.push(line); line = w; }
      else line = test;
    }
    if (line) lines.push(line);
    const lineH = 26, padX = 14, padY = 10;
    let textW = 0;
    lines.forEach((l) => { textW = Math.max(textW, ctx.measureText(l).width); });
    const boxW = Math.min(maxW + padX * 2, textW + padX * 2);
    const boxH = lines.length * lineH + padY * 2;
    const x = cx - boxW / 2;
    const y = cy - boxH / 2;
    rr(ctx, x, y, boxW, boxH, 12);
    ctx.fillStyle = "rgba(13, 36, 55, .85)";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    lines.forEach((l, i) => ctx.fillText(l, cx, y + padY + lineH * i + lineH / 2));
    ctx.textBaseline = "alphabetic";
  }

  function buildShareImageDataUrl(winnerText) {
    const msg = lastFinal || {};
    const view = msg.view || {};
    const st = view.stats || {};
    const youWon = !!msg.you_won;
    const tie = msg.mode === "tiebreak" && !!msg.picture;
    const W = 900;
    const H = tie ? 1020 : 1560;
    const cv = document.createElement("canvas");
    cv.width = W;
    cv.height = H;
    const ctx = cv.getContext("2d");

    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, "#0d2437");
    bg.addColorStop(1, "#081521");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);
    ctx.textAlign = "center";

    ctx.font = "bold 104px 'Segoe UI', Roboto, sans-serif";
    ctx.fillStyle = youWon ? "#ffd76a" : "#ff7a6a";
    ctx.shadowColor = youWon ? "rgba(255,214,106,.55)" : "rgba(255,90,58,.55)";
    ctx.shadowBlur = 34;
    ctx.fillText(youWon ? "ПОБЕДА!" : "ПОРАЖЕНИЕ", W / 2, 148);
    ctx.shadowBlur = 0;

    const rounds = st.rounds || (msg.picture && msg.picture.round) || 0;
    ctx.font = "42px 'Segoe UI', Roboto, sans-serif";
    ctx.fillStyle = "#cfe4f4";
    ctx.fillText("Раундов: " + rounds, W / 2, 220);

    ctx.font = "bold 46px 'Segoe UI', Roboto, sans-serif";
    ctx.fillStyle = "#eaf4ff";
    ctx.fillText(winnerText, W / 2, 296);

    const me = roomPlayers.find((p) => p && p.slot === mySlot) || null;
    const foe = roomPlayers.find((p) => p && p.slot !== mySlot) || null;
    const boards = shareBoards(msg);
    const avatars = tie ? [me] : [foe, me];
    // Рамки: соперник — красная, игрок — зелёная (как в счёте).
    const frameColors = tie ? ["#57d96a"] : ["#ff7a6a", "#57d96a"];
    const statLines = tie
      ? [null]
      : [
          { label: "Ваши попадания", value: (st.your_hits || 0) + "/" + (st.your_shots || 0), color: "#57d96a" },
          { label: "Попадания врага", value: (st.enemy_hits || 0) + "/" + (st.enemy_shots || 0), color: "#ff7a6a" },
        ];

    const boardSize = 430;
    const bx = (W - boardSize) / 2;
    let top = tie ? 380 : 360;
    for (let i = 0; i < boards.length; i++) {
      const b = boards[i];
      ctx.font = "bold 40px 'Segoe UI', Roboto, sans-serif";
      ctx.fillStyle = "#dbeaf5";
      ctx.textAlign = "center";
      ctx.fillText(b.title, W / 2, top + 34);
      drawBoard(ctx, bx, top + 56, boardSize, b.marks);
      const s = statLines[i];
      if (s) {
        ctx.textAlign = "left";
        ctx.font = "26px 'Segoe UI', Roboto, sans-serif";
        ctx.fillStyle = "rgba(234,244,255,.75)";
        wrapLeft(ctx, s.label, 24, top + 150, 175, 32);
        ctx.font = "bold 44px 'Segoe UI', Roboto, sans-serif";
        ctx.fillStyle = s.color;
        ctx.fillText(s.value, 24, top + 250);
      }
      const p = avatars[i];
      if (p) drawWhoCard(ctx, W - 100, top + 150, p, frameColors[i]);
      top += boardSize + 116;
    }

    ctx.textAlign = "center";
    ctx.font = "bold 40px 'Segoe UI', Roboto, sans-serif";
    ctx.fillStyle = "#9fd0ff";
    ctx.fillText("⚓ SeaBlitz", W / 2, H - 64);

    return cv.toDataURL("image/png");
  }

  function dataUrlToBlob(dataUrl) {
    const [head, b64] = dataUrl.split(",");
    const mime = (head.match(/:(.*?);/) || [null, "image/png"])[1];
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return new Blob([arr], { type: mime });
  }

  async function createShareLink(image, title, text) {
    const resp = await fetch("/api/share", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: image, title: title, text: text }),
    });
    if (!resp.ok) throw new Error("share " + resp.status);
    const data = await resp.json();
    return data && data.url ? data.url : "";
  }

  async function shareGame() {
    Sound.play("select");
    const url = shareUrl || "https://t.me/seablitz_bot";
    const me = roomPlayers.find((p) => p && p.slot === mySlot) || null;
    const foe = roomPlayers.find((p) => p && p.slot !== mySlot) || null;
    const youWon = !!(lastFinal && lastFinal.you_won);
    const winnerText =
      playerLabel(youWon ? me : foe) + " победил " + playerLabel(youWon ? foe : me);
    const footer = "Сыграй в SeaBlitz ⚓ — если ты настоящий морской волк";

    let dataUrl = null;
    try {
      dataUrl = buildShareImageDataUrl(winnerText);
    } catch (e) {
      console.error("SeaBlitz: не удалось собрать картинку", e);
    }

    // 1) Системное «Поделиться» с картинкой — если платформа это умеет.
    if (dataUrl && navigator.share) {
      try {
        const file = new File(
          [dataUrlToBlob(dataUrl)], "seablitz.png", { type: "image/png" }
        );
        await navigator.share({
          files: [file],
          text: winnerText + "\n\n" + footer + "\n" + url,
        });
        return;
      } catch (e) {
        if (e && e.name === "AbortError") return;  // пользователь закрыл «Поделиться»
        // иначе — уходим на ссылку с OG-превью ниже
      }
    }

    // 2) Запасной путь: грузим картинку на сервер и делимся ссылкой с превью.
    let pageUrl = url;
    if (dataUrl) {
      try {
        const link = await createShareLink(dataUrl, winnerText, footer);
        if (link) pageUrl = link;
      } catch (e) {
        console.error("SeaBlitz: не удалось загрузить картинку", e);
      }
    }
    const shareLink =
      "https://t.me/share/url?url=" + encodeURIComponent(pageUrl) +
      "&text=" + encodeURIComponent(winnerText + "\n\n" + footer);
    if (tg && tg.openTelegramLink) tg.openTelegramLink(shareLink);
    else if (navigator.share) {
      navigator.share({ text: winnerText + "\n\n" + footer + "\n" + pageUrl }).catch(() => {});
    } else window.open(shareLink, "_blank");
  }
  battleShare.addEventListener("click", shareGame);

  function updateSoundButton() {
    btnSound.textContent = Sound.muted ? "🔇" : "🔊";
  }
  updateSoundButton();
  btnSound.addEventListener("click", () => {
    Sound.toggle();
    updateSoundButton();
    if (!Sound.muted) Sound.play("select");
  });
  ["pointerdown", "touchstart", "keydown"].forEach((ev) =>
    window.addEventListener(ev, () => Sound.unlock(), { once: true })
  );

  // Код комнаты может прийти из Telegram (start_param) или из веб-ссылки (?room=CODE).
  const startParam = tg && tg.initDataUnsafe ? (tg.initDataUnsafe.start_param || "") : "";
  const urlRoom = (new URLSearchParams(location.search).get("room") || "")
    .toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
  const autoJoinCode = String(startParam).toUpperCase().slice(0, 8) || urlRoom;
  connect();
  const joinByCode = () => {
    lobbyStatus.textContent = "Подключаемся к комнате " + autoJoinCode + "…";
    setTimeout(
      () => send({ type: "join", code: autoJoinCode, user: currentProfile() }),
      300
    );
  };
  if (autoJoinCode) {
    // Пришли по ссылке-вызову: в браузере без имени сначала спросим его, потом вступаем.
    if (!isTelegram && !savedName()) { pendingAction = joinByCode; showNameModal(); }
    else joinByCode();
  } else if (!isTelegram && !savedName()) {
    // Обычный заход в вебе: сразу просим имя, чтобы соперник видел игрока, а не «игрок».
    showNameModal();
  }
})();
