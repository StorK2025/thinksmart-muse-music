(() => {
  'use strict';
  if (window.top !== window || location.protocol === 'file:') return;

  const postNavigation = command => {
    try {
      window.webkit.messageHandlers.thinksmartNav.postMessage(JSON.stringify({cmd: command}));
    } catch (_) {}
  };

  const postPlayer = message => {
    try {
      window.webkit.messageHandlers.thinksmartPlayer.postMessage(JSON.stringify(message));
      return true;
    } catch (_) {
      return false;
    }
  };

  const musicDocuments = () => {
    const docs = [document];
    try {
      const frame = document.getElementById('g_iframe');
      if (frame && frame.contentDocument) docs.push(frame.contentDocument);
    } catch (_) {}
    return docs;
  };

  const findInMusic = selector => {
    for (const doc of musicDocuments()) {
      const element = doc.querySelector(selector);
      if (element) return element;
    }
    return null;
  };

  const clickMusic = selector => {
    const element = findInMusic(selector);
    if (!element) return false;
    element.click();
    return true;
  };

  const mountHomeButton = () => {
    if (!document.body || document.getElementById('thinksmart-kiosk-tools')) return;
    const host = document.createElement('div');
    host.id = 'thinksmart-kiosk-tools';
    const root = host.attachShadow({mode: 'closed'});
    const style = document.createElement('style');
    style.textContent = `
      button {
        position: fixed; left: 12px; top: 50%; transform: translateY(-50%);
        z-index: 2147483647; width: 52px; height: 72px; border: 1px solid rgba(255,255,255,.42);
        border-radius: 0 18px 18px 0; background: rgba(8,20,30,.68); color: white;
        font: 32px/1 system-ui,sans-serif; box-shadow: 0 8px 22px rgba(0,0,0,.28);
        opacity: .72; touch-action: manipulation; -webkit-tap-highlight-color: transparent;
      }
      button:active { opacity: 1; background: rgba(20,115,125,.92); }
    `;
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = '⌂';
    button.title = '返回设备首页';
    button.setAttribute('aria-label', '返回设备首页');
    button.addEventListener('click', () => postNavigation('home'));
    root.append(style, button);
    document.body.appendChild(host);
  };

  const mountMusicPlayer = () => {
    if (!document.body || document.getElementById('thinksmart-music-home')) return;

    const host = document.createElement('div');
    host.id = 'thinksmart-music-home';
    host.style.pointerEvents = 'none';
    const root = host.attachShadow({mode: 'closed'});
    const style = document.createElement('style');
    style.textContent = `
      :host {
        position: fixed; inset: 0; z-index: 2147483646; display: block;
        color: #f8fbff; font-family: system-ui, "Noto Sans CJK SC", sans-serif;
      }
      * { box-sizing: border-box; }
      button, input { font: inherit; }
      button { -webkit-tap-highlight-color: transparent; touch-action: manipulation; }
      .shell {
        pointer-events: auto; position: absolute; inset: 0; overflow: hidden;
        background:
          radial-gradient(circle at 12% 10%, rgba(230,45,55,.34), transparent 33%),
          radial-gradient(circle at 90% 88%, rgba(54,135,176,.26), transparent 40%),
          linear-gradient(135deg, #130d16 0%, #17131f 52%, #071923 100%);
        padding: 24px 32px 22px; display: grid;
        grid-template-rows: auto minmax(0,1fr) auto; gap: 18px;
      }
      .shell[hidden] { display: none; }
      header { display: flex; align-items: center; justify-content: space-between; }
      .brand { display: flex; align-items: center; gap: 13px; }
      .brand-icon {
        width: 46px; height: 46px; border-radius: 15px; display: grid; place-items: center;
        background: linear-gradient(145deg,#ff4d56,#bf1526); box-shadow: 0 9px 24px rgba(220,30,50,.28);
        font-size: 27px; font-weight: 800;
      }
      .brand strong { display: block; font-size: 23px; letter-spacing: .02em; }
      .brand span { display: block; margin-top: 2px; color: #b9c7d2; font-size: 14px; }
      .top-actions { display: flex; align-items: center; gap: 12px; }
      .clock { text-align: right; margin-right: 6px; }
      .clock strong { display: block; font-size: 27px; font-variant-numeric: tabular-nums; }
      .clock span { color: #aab9c6; font-size: 13px; }
      .ghost {
        border: 1px solid rgba(255,255,255,.18); color: #e8f0f6; background: rgba(255,255,255,.08);
        min-height: 42px; padding: 0 15px; border-radius: 14px;
      }
      .layout {
        min-height: 0; display: grid; grid-template-columns: minmax(280px, 39%) minmax(0,1fr);
        gap: 34px; align-items: center;
      }
      .art-wrap { display: grid; place-items: center; }
      .art {
        position: relative; width: min(42vh, 320px); aspect-ratio: 1; border-radius: 34px;
        overflow: hidden; background: linear-gradient(145deg,#402832,#142f3c);
        box-shadow: 0 26px 70px rgba(0,0,0,.48), 0 0 0 1px rgba(255,255,255,.12);
      }
      .art::after {
        content: "♫"; position: absolute; inset: 0; display: grid; place-items: center;
        color: rgba(255,255,255,.28); font-size: 110px; z-index: 0;
      }
      .art img { position: relative; z-index: 1; width: 100%; height: 100%; object-fit: cover; display: none; }
      .art img.ready { display: block; }
      .playing-dot {
        position: absolute; z-index: 2; right: 17px; bottom: 17px; min-width: 90px; height: 34px;
        padding: 0 12px; border-radius: 17px; background: rgba(7,18,25,.78); backdrop-filter: blur(8px);
        display: flex; align-items: center; justify-content: center; gap: 7px; font-size: 13px;
      }
      .playing-dot i { width: 7px; height: 7px; border-radius: 50%; background: #52e59b; box-shadow: 0 0 12px #52e59b; }
      .playing-dot.paused i { background: #f3c85d; box-shadow: none; }
      .details { min-width: 0; align-self: stretch; display: flex; flex-direction: column; justify-content: center; }
      .eyebrow { color: #ff7f86; font-size: 15px; font-weight: 700; letter-spacing: .14em; }
      h1 { margin: 8px 0 3px; font-size: clamp(34px,4.2vw,58px); line-height: 1.08; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .artist { color: #bac8d3; font-size: clamp(18px,2vw,27px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .lyrics {
        min-height: 142px; margin: 18px 0 12px; padding: 15px 20px; border-radius: 20px;
        background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.08);
        display: grid; align-content: center; gap: 8px; overflow: hidden;
      }
      .lyric { margin: 0; text-align: center; color: #81909d; font-size: 18px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .lyric.current { color: white; font-size: clamp(23px,2.5vw,32px); font-weight: 720; text-shadow: 0 3px 16px rgba(0,0,0,.45); }
      .progress-row { display: grid; grid-template-columns: 46px minmax(0,1fr) 46px; gap: 12px; align-items: center; color: #95a6b4; font-size: 13px; font-variant-numeric: tabular-nums; }
      .progress { width: 100%; accent-color: #ef4652; }
      .controls { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 12px 18px; margin-top: 8px; }
      .transport { display: flex; align-items: center; justify-content: center; gap: 16px; flex-shrink: 0; }
      .control {
        width: 58px; height: 58px; border-radius: 50%; border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.08); color: white; font-size: 27px;
      }
      .control:active, .ghost:active, .app:active { transform: scale(.96); filter: brightness(1.16); }
      .control.main {
        width: 76px; height: 76px; border: 0; background: linear-gradient(145deg,#ff5962,#d51e36);
        box-shadow: 0 12px 28px rgba(218,26,49,.34); font-size: 34px;
      }
      footer { display: grid; grid-template-columns: 1fr auto; gap: 18px; align-items: center; }
      .hint { color: #a8b8c4; font-size: 16px; }
      .hint strong { color: #f5f8fa; font-weight: 650; }
      .apps { display: flex; gap: 10px; }
      .app {
        min-height: 48px; padding: 0 17px; border-radius: 16px; border: 1px solid rgba(255,255,255,.13);
        background: rgba(255,255,255,.075); color: #edf4f8; font-weight: 650;
      }
      .library {
        pointer-events: auto; position: absolute; inset: 0; z-index: 20; padding: 24px 32px;
        background:
          radial-gradient(circle at 85% 8%, rgba(226,48,62,.25), transparent 32%),
          linear-gradient(135deg,#100d14,#0b1c27);
        display: grid; grid-template-rows: auto auto minmax(0,1fr); gap: 18px;
      }
      .library[hidden] { display: none; }
      .library-head { display: grid; grid-template-columns: auto minmax(0,1fr) auto; gap: 14px; align-items: center; }
      .back {
        width: 48px; height: 48px; border-radius: 15px; border: 1px solid rgba(255,255,255,.15);
        background: rgba(255,255,255,.08); color: white; font-size: 26px;
      }
      .library-head h2 { margin: 0; font-size: 29px; }
      .library-head p { margin: 3px 0 0; color: #91a2af; font-size: 14px; }
      .library-actions { display: flex; align-items: center; gap: 10px; }
      .primary-action {
        min-height: 48px; padding: 0 24px; border: 0; border-radius: 15px;
        color: white; background: linear-gradient(135deg,#f14452,#c71f32);
        box-shadow: 0 10px 24px rgba(199,31,50,.3); font-size: 16px; font-weight: 750;
      }
      .primary-action:disabled { opacity: .55; box-shadow: none; }
      .primary-action[hidden] { display: none; }
      .library-tools { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
      .tabs, .modes { display: flex; gap: 8px; padding: 5px; border-radius: 16px; background: rgba(255,255,255,.055); }
      .tab, .mode {
        min-height: 42px; padding: 0 18px; border: 0; border-radius: 12px;
        color: #aebdc7; background: transparent; font-weight: 650;
      }
      .tab.active, .mode.active { color: white; background: rgba(224,49,62,.9); box-shadow: 0 7px 18px rgba(190,24,43,.25); }
      .controls .modes { gap: 4px; padding: 4px; }
      .controls .mode { min-height: 44px; padding: 0 10px; font-size: 14px; white-space: nowrap; }
      .controls .mode:active { filter: brightness(1.16); }
      .library-list {
        min-height: 0; overflow-y: auto; padding-right: 8px; display: grid; align-content: start;
        grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px 14px; scrollbar-color: #a62b3a transparent;
      }
      .library-item {
        width: 100%; min-height: 68px; padding: 10px 14px; border: 1px solid rgba(255,255,255,.09);
        border-radius: 17px; color: #f2f6f8; background: rgba(255,255,255,.055);
        display: grid; grid-template-columns: 38px minmax(0,1fr) auto; gap: 12px; align-items: center;
        text-align: left;
      }
      .library-item.active { border-color: rgba(255,91,103,.7); background: rgba(198,35,52,.22); }
      .item-index {
        width: 34px; height: 34px; border-radius: 11px; display: grid; place-items: center;
        background: rgba(255,255,255,.08); color: #aebcc6; font-variant-numeric: tabular-nums;
      }
      .item-title { display: block; font-size: 18px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .item-sub { display: block; margin-top: 3px; color: #91a2ae; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .item-mark { color: #ff7e87; font-size: 13px; }
      .empty { grid-column: 1/-1; min-height: 220px; display: grid; place-items: center; text-align: center; color: #91a2ae; font-size: 18px; line-height: 1.7; }
      .restore {
        pointer-events: auto; position: fixed; left: 10px; top: 50%; transform: translateY(-50%);
        z-index: 2147483647; width: 60px; min-height: 92px; padding: 8px 4px;
        border: 1px solid rgba(255,255,255,.35); border-radius: 0 18px 18px 0;
        background: rgba(16,21,29,.82); color: white; writing-mode: vertical-rl; letter-spacing: .12em;
      }
      .restore[hidden] { display: none; }
      @media (max-width: 800px), (max-height: 600px) {
        .shell { padding: 16px 22px; gap: 10px; }
        .layout { gap: 22px; grid-template-columns: minmax(210px,36%) minmax(0,1fr); }
        .art { width: min(38vh,270px); border-radius: 25px; }
        .lyrics { min-height: 112px; margin: 10px 0 8px; padding: 9px 14px; }
        .lyric { font-size: 15px; } .lyric.current { font-size: 23px; }
        .control { width: 50px; height: 50px; } .control.main { width: 64px; height: 64px; }
        .controls { column-gap: 12px; }
        .transport { gap: 12px; }
        .brand span, .clock span { display: none; }
        .library { padding: 16px 22px; gap: 12px; }
        .library-list { gap: 8px 10px; }
        .library-item { min-height: 58px; }
      }
    `;

    const shell = document.createElement('main');
    shell.className = 'shell';
    shell.innerHTML = `
      <header>
        <div class="brand"><div class="brand-icon">♫</div><div><strong>ThinkSmart 音乐</strong><span>网易云会员播放器</span></div></div>
        <div class="top-actions">
          <div class="clock"><strong id="clock-time">--:--</strong><span id="clock-date">--</span></div>
          <button class="ghost" id="open-library" type="button">播放列表</button>
          <button class="ghost" id="show-origin" type="button">网易云登录 / 原页</button>
        </div>
      </header>
      <section class="layout">
        <div class="art-wrap"><div class="art"><img id="cover" alt="专辑封面"><div class="playing-dot paused" id="state-pill"><i></i><span>等待播放</span></div></div></div>
        <div class="details">
          <div class="eyebrow">NOW PLAYING</div>
          <h1 id="song-title">等待点歌</h1>
          <div class="artist" id="song-artist">说“小麦小麦，播放一首歌”</div>
          <div class="lyrics"><p class="lyric" id="lyric-prev">&nbsp;</p><p class="lyric current" id="lyric-current">歌词将在播放后显示</p><p class="lyric" id="lyric-next">&nbsp;</p></div>
          <div class="progress-row"><span id="time-current">00:00</span><input class="progress" id="progress" type="range" min="0" max="1000" value="0" aria-label="播放进度"><span id="time-total">00:00</span></div>
          <div class="controls">
            <div class="transport"><button class="control" id="previous" type="button" aria-label="上一首">‹</button><button class="control main" id="toggle" type="button" aria-label="播放或暂停">▶</button><button class="control" id="next" type="button" aria-label="下一首">›</button></div>
            <div class="modes" role="group" aria-label="播放模式"><button class="mode" data-mode="list" type="button" aria-pressed="false">列表循环</button><button class="mode" data-mode="single" type="button" aria-pressed="false">单曲循环</button><button class="mode" data-mode="shuffle" type="button" aria-pressed="false">随机播放</button></div>
          </div>
        </div>
      </section>
      <footer><div class="hint">语音点歌：<strong>“小麦小麦，播放蔡依林的舞娘”</strong></div><div class="apps"><button class="app" data-nav="voice" type="button">Muse 对话</button><button class="app" data-nav="launcher" type="button">首页</button></div></footer>
      <section class="library" id="library-view" hidden>
        <div class="library-head"><button class="back" id="library-back" type="button">←</button><div><h2 id="library-title">播放列表</h2><p id="library-subtitle">当前播放队列 · 点击歌曲播放</p></div><div class="library-actions"><button class="primary-action" id="playlist-play-all" type="button" hidden>播放全部</button><button class="ghost" id="library-refresh" type="button">刷新</button></div></div>
        <div class="library-tools"><div class="tabs"><button class="tab active" data-tab="queue" type="button">当前列表</button><button class="tab" data-tab="playlists" type="button">我的歌单</button></div></div>
        <div class="library-list" id="library-list"><div class="empty">正在读取播放列表…</div></div>
      </section>
    `;
    const restore = document.createElement('button');
    restore.className = 'restore';
    restore.type = 'button';
    restore.textContent = '返回音乐播放器';
    restore.hidden = true;
    root.append(style, shell, restore);
    document.body.appendChild(host);

    const get = id => root.getElementById(id);
    const cover = get('cover');
    const title = get('song-title');
    const artist = get('song-artist');
    const statePill = get('state-pill');
    const toggle = get('toggle');
    const progress = get('progress');
    let dragging = false;
    let lastLyricRequest = 0;
    let lastStatusReport = 0;
    const library = get('library-view');
    const libraryList = get('library-list');
    const libraryState = {view: 'queue', selectedName: '', selectedId: '', renderKey: '', playAllPending: false};
    const libraryCounts = {queue: 0, playlists: 0, songs: 0};

    const audioElements = () => musicDocuments().flatMap(doc => Array.from(doc.querySelectorAll('audio')));
    const currentAudio = () => {
      const audios = audioElements().filter(item => Number.isFinite(item.duration) && item.duration > 0);
      return audios.find(item => !item.paused) || audios.sort((a,b) => b.currentTime - a.currentTime)[0] || null;
    };
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const formatTime = seconds => {
      if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
      const total = Math.floor(seconds);
      return `${Math.floor(total / 60).toString().padStart(2,'0')}:${(total % 60).toString().padStart(2,'0')}`;
    };
    const parseTime = value => {
      const parts = clean(value).split(':').map(Number);
      if (!parts.length || parts.some(part => !Number.isFinite(part))) return NaN;
      return parts.reduce((total, part) => total * 60 + part, 0);
    };

    const contentDocument = () => {
      try {
        const frame = document.getElementById('g_iframe');
        return frame && frame.contentDocument;
      } catch (_) {
        return null;
      }
    };

    const readQueue = () => {
      const rows = Array.from(document.querySelectorAll('.listbdc li[data-id]'));
      const seen = new Set();
      return rows.map((row, index) => {
        const id = String(row.dataset.id || '');
        if (!/^\d+$/.test(id) || seen.has(id)) return null;
        seen.add(id);
        return {
          id,
          title: clean((row.querySelector('.col-2') || {}).textContent) || `歌曲 ${index + 1}`,
          artist: clean((row.querySelector('.col-3') || {}).textContent),
          active: row.classList.contains('z-sel') || Boolean(row.querySelector('.playicn')),
        };
      }).filter(Boolean);
    };

    const readPlaylists = () => {
      const doc = contentDocument();
      if (!doc) return [];
      const seen = new Set();
      const playlists = [];
      const addPlaylist = (id, container, explicitName) => {
        if (!/^\d+$/.test(id) || seen.has(id)) return;
        const nameNode = container && container.querySelector('.name, [class~="name"]');
        const countNode = container && container.querySelector('.num, [class~="num"]');
        const name = clean(explicitName || (nameNode && (nameNode.getAttribute('title') || nameNode.textContent)));
        if (!name) return;
        seen.add(id);
        const image = container && container.querySelector('img');
        const count = clean(countNode && countNode.textContent);
        playlists.push({
          id,
          title: name,
          artist: count ? `网易云歌单 · ${count}` : '网易云歌单',
          artwork: image ? image.src : '',
          active: Boolean(container && container.classList.contains('z-selected')),
        });
      };

      // The current NetEase "My Music" page uses data-matcher="playlist-ID"
      // instead of links. Keep the old href path below as a compatibility fallback.
      for (const row of doc.querySelectorAll('.g-mymusic li.j-iflag[data-matcher^="playlist-"], li.j-iflag[data-matcher^="playlist-"]')) {
        const match = String(row.getAttribute('data-matcher') || '').match(/^playlist-(\d+)$/);
        if (match) addPlaylist(match[1], row, '');
      }
      for (const anchor of doc.querySelectorAll('a[href*="/playlist?id="]')) {
        const match = String(anchor.getAttribute('href') || '').match(/\/playlist\?id=(\d+)/);
        const name = clean(anchor.getAttribute('title') || anchor.textContent);
        if (!match || !name) continue;
        const container = anchor.closest('li, .item, .itm, .j-flag, div');
        addPlaylist(match[1], container, name);
      }
      return playlists;
    };

    const readPageSongs = () => {
      const doc = contentDocument();
      if (!doc) return [];
      const seen = new Set();
      const songs = [];
      for (const play of doc.querySelectorAll('[data-res-action="play"][data-res-type="18"][data-res-id]')) {
        const id = String(play.dataset.resId || '');
        const row = play.closest('tr');
        if (!/^\d+$/.test(id) || !row || seen.has(id)) continue;
        seen.add(id);
        const songLink = row.querySelector('a[href*="/song?id="]');
        const artists = Array.from(row.querySelectorAll('a[href*="/artist?id="]')).map(item => clean(item.textContent)).filter(Boolean);
        songs.push({
          id,
          title: clean(songLink && (songLink.getAttribute('title') || songLink.textContent)) || `歌曲 ${songs.length + 1}`,
          artist: artists.join(' / '),
          active: play.classList.contains('ply-z-slt'),
        });
      }
      return songs;
    };

    const renderLibrary = (items, kind) => {
      const key = `${kind}|${items.map(item => `${item.id}:${item.title}:${item.active ? 1 : 0}`).join('|')}`;
      if (key === libraryState.renderKey) return;
      libraryState.renderKey = key;
      libraryList.replaceChildren();
      if (!items.length) {
        const empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = kind === 'queue' ? '当前播放队列为空。可以先用“小麦小麦”点一首歌。' :
                            kind === 'playlists' ? '正在从网易云“我的音乐”读取歌单…' :
                            '正在读取这个歌单的歌曲…';
        libraryList.appendChild(empty);
        return;
      }
      items.forEach((item, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `library-item${item.active ? ' active' : ''}`;
        const number = document.createElement('span');
        number.className = 'item-index';
        number.textContent = kind === 'playlists' ? '♫' : String(index + 1).padStart(2,'0');
        const text = document.createElement('span');
        const itemTitle = document.createElement('span');
        itemTitle.className = 'item-title';
        itemTitle.textContent = item.title;
        const itemSub = document.createElement('span');
        itemSub.className = 'item-sub';
        itemSub.textContent = item.artist || (kind === 'playlists' ? '歌单' : '未知歌手');
        text.append(itemTitle, itemSub);
        const mark = document.createElement('span');
        mark.className = 'item-mark';
        mark.textContent = item.active ? '正在播放' : (kind === 'playlists' ? '进入 ›' : '播放');
        button.append(number, text, mark);
        button.addEventListener('click', () => {
          if (kind === 'queue') {
            postPlayer({cmd: 'queue_play', id: item.id});
            library.hidden = true;
          } else if (kind === 'playlists') {
            libraryState.view = 'songs';
            libraryState.selectedName = item.title;
            libraryState.selectedId = item.id;
            libraryState.renderKey = '';
            get('library-title').textContent = item.title;
            get('library-subtitle').textContent = '正在读取歌单歌曲…';
            get('playlist-play-all').hidden = false;
            get('playlist-play-all').disabled = true;
            postPlayer({cmd: 'open_playlist', id: item.id});
          } else {
            postPlayer({cmd: 'page_play', id: item.id});
            library.hidden = true;
          }
        });
        libraryList.appendChild(button);
      });
    };

    const setLibraryView = viewName => {
      libraryState.view = viewName;
      libraryState.renderKey = '';
      const playAllButton = get('playlist-play-all');
      playAllButton.hidden = viewName !== 'songs';
      playAllButton.disabled = viewName === 'songs' && (!libraryState.selectedId || libraryState.playAllPending);
      playAllButton.textContent = libraryState.playAllPending ? '正在载入…' : '播放全部';
      root.querySelectorAll('[data-tab]').forEach(button => button.classList.toggle('active', button.dataset.tab === (viewName === 'songs' ? 'playlists' : viewName)));
      if (viewName === 'queue') {
        get('library-title').textContent = '播放列表';
        get('library-subtitle').textContent = '当前播放队列 · 点击歌曲播放';
        postPlayer({cmd: 'lyrics'});
      } else if (viewName === 'playlists') {
        get('library-title').textContent = '我的歌单';
        get('library-subtitle').textContent = '收藏歌单与自建歌单';
        postPlayer({cmd: 'browse_playlists'});
      }
    };

    const syncLibrary = () => {
      const modeButton = findInMusic('#g_player [data-action="mode"]');
      const modeClass = modeButton ? modeButton.className : '';
      const currentMode = modeClass.includes('icn-one') ? 'single' : modeClass.includes('icn-shuffle') ? 'shuffle' : 'list';
      root.querySelectorAll('[data-mode]').forEach(button => {
        const selected = button.dataset.mode === currentMode;
        button.classList.toggle('active', selected);
        button.setAttribute('aria-pressed', String(selected));
      });

      const queue = readQueue();
      libraryCounts.queue = queue.length;
      if (library.hidden) return modeClass;
      if (libraryState.view === 'queue') {
        renderLibrary(queue, 'queue');
      } else if (libraryState.view === 'playlists') {
        const playlists = readPlaylists();
        libraryCounts.playlists = playlists.length;
        renderLibrary(playlists, 'playlists');
      } else {
        const songs = readPageSongs();
        libraryCounts.songs = songs.length;
        get('library-title').textContent = libraryState.selectedName || '歌单歌曲';
        get('library-subtitle').textContent = songs.length ? `共 ${songs.length} 首 · 点击即可播放` : '正在读取歌单歌曲…';
        const playAllButton = get('playlist-play-all');
        playAllButton.hidden = false;
        playAllButton.disabled = !libraryState.selectedId || libraryState.playAllPending || !songs.length;
        playAllButton.textContent = libraryState.playAllPending ? '正在载入…' : '播放全部';
        renderLibrary(songs, 'songs');
      }
      return modeClass;
    };

    const readMetadata = () => {
      const media = navigator.mediaSession && navigator.mediaSession.metadata;
      const words = findInMusic('#g_player .words');
      const nameNode = words && (words.querySelector('.name') || words.querySelector('a[href*="/song?id="]'));
      const artistNode = words && (words.querySelector('.by a') || words.querySelector('a[href*="/artist?id="]'));
      const artNode = findInMusic('#g_player .head img');
      const artwork = media && media.artwork && media.artwork.length ? media.artwork[media.artwork.length - 1].src : '';
      return {
        title: clean((media && media.title) || (nameNode && nameNode.textContent)),
        artist: clean((media && media.artist) || (artistNode && artistNode.textContent)),
        artwork: clean(artwork || (artNode && artNode.src)),
      };
    };

    const readLyrics = audio => {
      let lines = [];
      for (const doc of musicDocuments()) {
        const found = Array.from(doc.querySelectorAll('.listlyric p')).filter(item => clean(item.textContent));
        if (found.length > lines.length) lines = found;
      }
      if (!lines.length) return null;
      let index = lines.findIndex(item => item.classList.contains('z-sel'));
      if (index < 0 && audio) {
        const now = audio.currentTime;
        for (let i = 0; i < lines.length; i += 1) {
          let at = Number(lines[i].dataset.time);
          if (!Number.isFinite(at)) continue;
          if (audio.duration && at > audio.duration * 10) at /= 1000;
          if (at <= now + .15) index = i;
          else break;
        }
      }
      if (index < 0) index = 0;
      return {
        previous: index > 0 ? clean(lines[index - 1].textContent) : '',
        current: clean(lines[index].textContent),
        next: index + 1 < lines.length ? clean(lines[index + 1].textContent) : '',
      };
    };

    const updateClock = () => {
      const now = new Date();
      get('clock-time').textContent = new Intl.DateTimeFormat('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}).format(now);
      get('clock-date').textContent = new Intl.DateTimeFormat('zh-CN',{month:'numeric',day:'numeric',weekday:'short'}).format(now);
    };

    const sync = () => {
      const audio = currentAudio();
      const meta = readMetadata();
      const playerButton = findInMusic(
        '#g_player [data-action="play"], #g_player [data-action="pause"], #g_player .pas, #g_player .ply'
      );
      const playerClass = playerButton ? playerButton.className : '';
      if (meta.title) title.textContent = meta.title;
      if (meta.artist) artist.textContent = meta.artist;
      if (meta.artwork && cover.dataset.src !== meta.artwork) {
        cover.dataset.src = meta.artwork;
        cover.classList.remove('ready');
        cover.onload = () => cover.classList.add('ready');
        cover.onerror = () => cover.classList.remove('ready');
        cover.src = meta.artwork.replace(/^http:/,'https:');
      }
      const playingByClass = Boolean(playerButton && (
        playerButton.getAttribute('data-action') === 'pause' ||
        /(^|\s)pas(\s|$)/.test(playerClass)
      ));
      const paused = audio ? audio.paused : !playingByClass;
      toggle.textContent = paused ? '▶' : 'Ⅱ';
      statePill.classList.toggle('paused', paused);
      statePill.querySelector('span').textContent = (audio || playerButton) ? (paused ? '已暂停' : '正在播放') : '等待播放';
      if (audio) {
        get('time-current').textContent = formatTime(audio.currentTime);
        get('time-total').textContent = formatTime(audio.duration);
        if (!dragging && Number.isFinite(audio.duration) && audio.duration > 0) progress.value = String(Math.round(audio.currentTime / audio.duration * 1000));
      } else {
        const timeNode = findInMusic('#g_player .time');
        const currentNode = timeNode && timeNode.querySelector('em');
        const current = parseTime(currentNode && currentNode.textContent);
        const total = parseTime(timeNode ? timeNode.textContent.split('/').pop() : '');
        if (Number.isFinite(current)) get('time-current').textContent = formatTime(current);
        if (Number.isFinite(total)) get('time-total').textContent = formatTime(total);
        if (!dragging && Number.isFinite(current) && Number.isFinite(total) && total > 0) progress.value = String(Math.round(current / total * 1000));
      }
      const lyrics = readLyrics(audio);
      if (lyrics) {
        get('lyric-prev').textContent = lyrics.previous || '\u00a0';
        get('lyric-current').textContent = lyrics.current || '纯音乐，请欣赏';
        get('lyric-next').textContent = lyrics.next || '\u00a0';
      } else if (Date.now() - lastLyricRequest > 4000) {
        lastLyricRequest = Date.now();
        postPlayer({cmd: 'lyrics'});
      }
      const modeClass = syncLibrary();
      if (Date.now() - lastStatusReport > 2000) {
        lastStatusReport = Date.now();
        postPlayer({cmd: 'status', title: meta.title, artist: meta.artist,
          playing: toggle.textContent === 'Ⅱ', overlayVisible: !shell.hidden});
      }
    };

    toggle.addEventListener('click', () => {
      const willPause = toggle.textContent === 'Ⅱ';
      toggle.textContent = willPause ? '▶' : 'Ⅱ';
      statePill.classList.toggle('paused', willPause);
      statePill.querySelector('span').textContent = willPause ? '已暂停' : '正在播放';
      postPlayer({cmd: 'control', action: willPause ? 'pause' : 'resume'});
    });
    get('previous').addEventListener('click', () => postPlayer({cmd: 'control', action: 'previous'}));
    get('next').addEventListener('click', () => postPlayer({cmd: 'control', action: 'next'}));
    progress.addEventListener('pointerdown', () => { dragging = true; });
    progress.addEventListener('input', () => {
      const audio = currentAudio();
      if (audio && Number.isFinite(audio.duration)) get('time-current').textContent = formatTime(audio.duration * Number(progress.value) / 1000);
    });
    const seek = () => {
      postPlayer({cmd: 'seek', ratio: Number(progress.value) / 1000});
      dragging = false;
    };
    progress.addEventListener('change', seek);
    progress.addEventListener('pointerup', seek);
    get('open-library').addEventListener('click', () => {
      library.hidden = false;
      setLibraryView('queue');
    });
    get('library-back').addEventListener('click', () => {
      if (libraryState.view === 'songs') setLibraryView('playlists');
      else library.hidden = true;
    });
    get('library-refresh').addEventListener('click', () => {
      libraryState.renderKey = '';
      if (libraryState.view === 'queue') postPlayer({cmd: 'lyrics'});
      else if (libraryState.view === 'playlists') postPlayer({cmd: 'browse_playlists'});
      else if (libraryState.selectedId) postPlayer({cmd: 'open_playlist', id: libraryState.selectedId});
    });
    get('playlist-play-all').addEventListener('click', () => {
      if (!libraryState.selectedId || libraryState.playAllPending) return;
      const selectedName = libraryState.selectedName;
      libraryState.playAllPending = true;
      const button = get('playlist-play-all');
      button.disabled = true;
      button.textContent = '正在载入…';
      postPlayer({cmd: 'playlist_play_all', id: libraryState.selectedId});
      setTimeout(() => postPlayer({cmd: 'lyrics'}), 700);
      setTimeout(() => {
        libraryState.playAllPending = false;
        setLibraryView('queue');
        get('library-subtitle').textContent = selectedName ? `已载入「${selectedName}」` : '歌单已载入当前列表';
      }, 2200);
    });
    root.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => setLibraryView(button.dataset.tab)));
    root.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => {
      root.querySelectorAll('[data-mode]').forEach(item => {
        item.classList.toggle('active', item === button);
        item.setAttribute('aria-pressed', String(item === button));
      });
      postPlayer({cmd: 'mode', mode: button.dataset.mode});
    }));
    get('show-origin').addEventListener('click', () => { shell.hidden = true; restore.hidden = false; });
    restore.addEventListener('click', () => { restore.hidden = true; shell.hidden = false; });
    root.querySelectorAll('[data-nav]').forEach(button => button.addEventListener('click', () => postNavigation(button.dataset.nav)));

    updateClock();
    sync();
    setInterval(updateClock, 30000);
    setInterval(sync, 500);
  };

  const mount = () => {
    if (/^(?:www\.)?music\.163\.com$/i.test(location.hostname)) mountMusicPlayer();
    else mountHomeButton();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true});
  else mount();
})();
