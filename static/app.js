(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) { try { tg.ready(); tg.expand(); } catch (e) {} }
  const Sound = window.Sound || {
    play() {}, unlock() {}, toggle() { return false; }, muted: true,
  };

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
  const ownBoard = $("own-board");
  const enemyBoard = $("enemy-board");
  const banner = $("banner");
  const timerFill = $("timer-fill");
  const timerText = $("timer-text");
  const fireBtn = $("btn-fire");
  const selectedCount = $("selected-count");
  const lobbyStatus = $("lobby-status");
  const roomInfo = $("room-info");
  const enemyTitle = $("enemy-title");
  const hintEl = $("hint");
  const btnSound = $("btn-sound");

  let ws = null;
  let mySlot = null;
  let roomCode = null;
  let shotsPerRound = 3;
  let selectable = false;
  const selected = new Set();
  let rafId = null;
  let countdownId = null;
  let myRematch = false;
  let oppRematch = false;
  let shareUrl = "https://t.me/seablitz_bot";

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

  function picShots(list) {
    return (list || []).map((s) => ({ cell: s.cell, outcome: s.hit ? "hit" : "miss" }));
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
      bbOwnTitle.textContent = "Ваши выстрелы";
      bbEnemyTitle.textContent = "Выстрелы соперника";
      renderReveal(rpOwn, [pic.ships], picShots(pic.your_shots));
      renderReveal(rpEnemy, [pic.ships], picShots(pic.enemy_shots));
      $("battle-stats").textContent =
        "Золотой раунд " + (pic.round || 1) +
        " · Ваши попадания: " + (pic.your_hits || 0) +
        " · Соперника: " + (pic.enemy_hits || 0);
    } else {
      const view = msg.view || {};
      const st = view.stats || {};
      bbOwnTitle.textContent = "Ваш флот";
      bbEnemyTitle.textContent = "Флот врага";
      renderReveal(rpOwn, view.your_ships, view.enemy_shots);
      renderReveal(rpEnemy, view.enemy_ships, view.your_shots);
      $("battle-stats").textContent =
        "Раундов: " + (st.rounds || 0) +
        " · Ваши попадания: " + (st.your_hits || 0) + "/" + (st.your_shots || 0) +
        " · Попадания врага: " + (st.enemy_hits || 0) + "/" + (st.enemy_shots || 0);
    }

    const btn = $("battle-continue");
    if (final) {
      if (msg.share_url) shareUrl = msg.share_url;
      haptic(msg.you_won ? "win" : "lose");
      Sound.play(msg.you_won ? "win" : "lose");
      battleCard.classList.add(msg.you_won ? "win" : "lose");
      $("battle-title").textContent = msg.you_won ? "ПОБЕДА!" : "ПОРАЖЕНИЕ";
      $("battle-count").textContent = msg.you_won
        ? (msg.mode === "tiebreak" ? "Вы выиграли «Золотой раунд»." : "Флот врага уничтожен.")
        : (msg.mode === "tiebreak" ? "Вы проиграли «Золотой раунд»." : "Ваш флот уничтожен.");
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
        mySlot = msg.slot;
        roomCode = msg.code;
        roomInfo.textContent = "Комната " + msg.code;
        break;
      case "waiting":
        if (msg.share_url) shareUrl = msg.share_url;
        if (msg.code) {
          roomCode = msg.code;
          roomInfo.textContent = "Комната " + msg.code;
          lobbyStatus.textContent = "Комната " + msg.code + ": ждём соперника…";
          $("btn-invite").hidden = false;
        } else {
          lobbyStatus.textContent = "Ищем соперника…";
        }
        break;
      case "error":
        lobbyStatus.textContent = "Комната недоступна, попробуйте другую.";
        break;
      case "state":
        showScreen("game");
        hideOverlays();
        renderOwn(msg.view);
        renderEnemy(msg.view);
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
        resetSelection();
        break;
      case "tiebreak_result":
        lockSelection();
        renderTiebreak(msg);
        break;
      case "game_over":
        msg.final = true;  // финальный бой — всегда экран результата
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
      try { handleMessage(JSON.parse(ev.data)); } catch (e) {}
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
    lobbyStatus.textContent = "Ищем соперника…";
    send({ type: "quickmatch" });
  });

  function randomCode(len) {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let s = "";
    for (let i = 0; i < len; i++) s += chars[Math.floor(Math.random() * chars.length)];
    return s;
  }

  $("btn-create").addEventListener("click", () => {
    lobbyStatus.textContent = "Создаём комнату…";
    send({ type: "join", code: randomCode(4) });
  });

  function inviteLink() {
    const base = shareUrl || "https://t.me/seablitz_bot";
    return roomCode
      ? base + "?startapp=" + encodeURIComponent(roomCode.toUpperCase())
      : base;
  }

  function inviteFriend() {
    if (!roomCode) return;
    const link = inviteLink();
    const text =
      "⚔️ Вызываю на морскую дуэль SeaBlitz! Код комнаты: " +
      roomCode.toUpperCase();
    Sound.play("select");

    // Telegram: нативный диалог «Поделиться» (выбор чата → отправка ссылки).
    if (tg && tg.openTelegramLink) {
      tg.openTelegramLink(
        "https://t.me/share/url?url=" + encodeURIComponent(link) +
        "&text=" + encodeURIComponent(text)
      );
      return;
    }

    // Браузер: копируем ссылку-вызов.
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link).then(
        () => { lobbyStatus.textContent = "Ссылка-вызов скопирована: " + link; },
        () => { lobbyStatus.textContent = "Ссылка-вызов: " + link; }
      );
    } else {
      lobbyStatus.textContent = "Ссылка-вызов: " + link;
    }
  }
  $("btn-invite").addEventListener("click", inviteFriend);

  $("btn-join").addEventListener("click", () => {
    const code = ($("code-input").value || "").trim().toUpperCase();
    if (!code) { lobbyStatus.textContent = "Введите код комнаты."; return; }
    send({ type: "join", code: code });
  });

  $("battle-exit").addEventListener("click", () => {
    send({ type: "leave" });
    location.reload();
  });

  function shareGame() {
    const text = "Сыграй в SeaBlitz ⚓ — морская дуэль 5×5 за минуту!";
    const url = shareUrl || "https://t.me/seablitz_bot";
    const shareLink =
      "https://t.me/share/url?url=" + encodeURIComponent(url) +
      "&text=" + encodeURIComponent(text);
    Sound.play("select");
    if (tg && tg.openTelegramLink) {
      tg.openTelegramLink(shareLink);
    } else if (navigator.share) {
      navigator.share({ text: text, url: url }).catch(() => {});
    } else {
      window.open(shareLink, "_blank");
    }
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

  const startParam = tg && tg.initDataUnsafe ? (tg.initDataUnsafe.start_param || "") : "";
  connect();
  if (startParam) {
    setTimeout(
      () => send({ type: "join", code: String(startParam).toUpperCase().slice(0, 8) }),
      300
    );
  }
})();
