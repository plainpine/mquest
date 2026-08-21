// static/js/habatan.js
// Clean implementation for the Habatan page.
(function(){
  const STORAGE_VERSION = '3';
  const STORAGE_KEYS = [
    'habatan2500Words',
    'vocabStats',
    'habatan2500Bookmarks',
    'habatan2500DailyHistory',
    'habatanStudyDirection',
    'habatanWordOrder',
    'habatanListOrder',
    'habatanSessionId',
    'habatanStorageVersion'
  ];

  function $(selector){ return document.querySelector(selector); }
  function $$(selector){ return Array.from(document.querySelectorAll(selector)); }
  function escapeHtml(value){ return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }

  const localStorage = {
    getItem(key) {
      const suffix = window.HABATAN_USER_ID ? `_${window.HABATAN_USER_ID}` : '';
      return window.localStorage.getItem(key + suffix);
    },
    setItem(key, value) {
      const suffix = window.HABATAN_USER_ID ? `_${window.HABATAN_USER_ID}` : '';
      window.localStorage.setItem(key + suffix, value);
    },
    removeItem(key) {
      const suffix = window.HABATAN_USER_ID ? `_${window.HABATAN_USER_ID}` : '';
      window.localStorage.removeItem(key + suffix);
    }
  };

  function normalizeOrder(value){ return value === 'frequency' ? 'frequency' : 'number'; }

  function clearStorage(reason='refresh'){
    STORAGE_KEYS.forEach(key => localStorage.removeItem(key));
    localStorage.setItem('habatanStorageVersion', STORAGE_VERSION);
    console.info(`[Habatan] Cleared storage (${reason})`);
  }


  let words = [];
  let stats = {"total":0,"correct":0};
  let bookmarks = [];
  let dailyHistory = {};
  let studyDirection = 'en-ja';
  let wordOrder = 'number';
  let listOrder = 'number';
  let selectedMode = 'study';
  let activity = { items: [], index: 0, correct: 0, locked: false };
  let chartInstance = null;

  async function syncWithServer(payload = null) {
    try {
      const options = {
        method: payload ? 'POST' : 'GET',
        headers: { 'Content-Type': 'application/json' }
      };
      if (payload) {
        options.body = JSON.stringify(payload);
      }
      const res = await fetch('/habatan/api/state', options);
      if (res.ok) {
        const data = await res.json();
        if (data && Array.isArray(data.words)) {
          words = data.words;
          stats = data.stats || {"total":0,"correct":0};
          bookmarks = (data.bookmarks || []).map(Number);
          dailyHistory = data.dailyHistory || {};
          studyDirection = data.studyDirection || 'en-ja';
          wordOrder = normalizeOrder(data.wordOrder);
          // Also persist locally as backup
          localStorage.setItem('habatan2500Words', JSON.stringify(words));
          localStorage.setItem('vocabStats', JSON.stringify(stats));
          localStorage.setItem('habatan2500Bookmarks', JSON.stringify(bookmarks));
          localStorage.setItem('habatan2500DailyHistory', JSON.stringify(dailyHistory));
          localStorage.setItem('habatanStudyDirection', studyDirection);
          localStorage.setItem('habatanWordOrder', wordOrder);
          localStorage.setItem('habatanStorageVersion', STORAGE_VERSION);
          return true;
        }
      }
    } catch(e) {
      console.warn('[Habatan] Server sync failed, using local storage:', e);
    }
    return false;
  }

  function initializeStorage(){
    const storedVersion = localStorage.getItem('habatanStorageVersion');
    const storedWords = JSON.parse(localStorage.getItem('habatan2500Words') || 'null');
    if(storedVersion !== STORAGE_VERSION || !Array.isArray(storedWords) || storedWords.length < 100){
      clearStorage(storedVersion ? 'version mismatch' : 'empty storage');
    }
    
    // Read local variables fallback
    words = JSON.parse(localStorage.getItem('habatan2500Words') || 'null') || (window.SAMPLE_WORDS || []);
    stats = JSON.parse(localStorage.getItem('vocabStats') || '{"total":0,"correct":0}');
    bookmarks = JSON.parse(localStorage.getItem('habatan2500Bookmarks') || '[]').map(Number);
    dailyHistory = JSON.parse(localStorage.getItem('habatan2500DailyHistory') || '{}');
    studyDirection = localStorage.getItem('habatanStudyDirection') || 'en-ja';
    wordOrder = normalizeOrder(localStorage.getItem('habatanWordOrder'));
    listOrder = normalizeOrder(localStorage.getItem('habatanListOrder'));
  }

  function persistState(){
    localStorage.setItem('habatan2500Words', JSON.stringify(words));
    localStorage.setItem('vocabStats', JSON.stringify(stats));
    localStorage.setItem('habatan2500Bookmarks', JSON.stringify(bookmarks));
    localStorage.setItem('habatan2500DailyHistory', JSON.stringify(dailyHistory));
    localStorage.setItem('habatanStudyDirection', studyDirection);
    localStorage.setItem('habatanWordOrder', wordOrder);
    localStorage.setItem('habatanListOrder', listOrder);
    localStorage.setItem('habatanStorageVersion', STORAGE_VERSION);
    // Async save to server
    syncWithServer({
      stats,
      bookmarks,
      dailyHistory,
      studyDirection,
      wordOrder
    });
  }


  function sortWords(items, order){
    const targetOrder = normalizeOrder(order);
    return Array.from(items).sort((a,b) => {
      const aNum = Number(a?.number ?? Number.POSITIVE_INFINITY);
      const bNum = Number(b?.number ?? Number.POSITIVE_INFINITY);
      const aFreq = Number(a?.frequency ?? Number.POSITIVE_INFINITY);
      const bFreq = Number(b?.frequency ?? Number.POSITIVE_INFINITY);
      if(targetOrder === 'frequency'){
        if(aFreq !== bFreq) return aFreq - bFreq;
        return aNum - bNum;
      }
      return aNum - bNum;
    });
  }

  function speak(text, lang='en-US'){
    if(!('speechSynthesis' in window)) return;
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    speechSynthesis.speak(utterance);
  }

  function recordToday(){
    const key = localDateKey();
    if(!dailyHistory[key]) dailyHistory[key] = { studied: 0, answered: 0, correct: 0 };
    return dailyHistory[key];
  }

  function recordStudyWord(){
    recordToday().studied += 1;
    persistState();
  }

  function recordTestAnswer(isCorrect){
    const rec = recordToday();
    rec.answered += 1;
    if(isCorrect) rec.correct += 1;
    persistState();
  }

  function localDateKey(date = new Date()){
    const y = date.getFullYear();
    const m = String(date.getMonth()+1).padStart(2,'0');
    const d = String(date.getDate()).padStart(2,'0');
    return `${y}-${m}-${d}`;
  }

  function getDateKeys(days){
    const keys = [];
    const now = new Date();
    for(let i = days - 1; i >= 0; i--){
      const day = new Date(now);
      day.setDate(now.getDate() - i);
      keys.push(localDateKey(day));
    }
    return keys;
  }

  function drawStudyChart(records){
    const canvas = $('#hbt-studyChart');
    if(!canvas || typeof Chart === 'undefined') return;
    const labels = records.map(r => r.key.replace(/^\d{4}-/, ''));
    const studied = [];
    const answered = [];
    const correct = [];
    let cumulativeStudied = 0;
    let cumulativeAnswered = 0;
    let cumulativeCorrect = 0;
    const accuracies = [];
    records.forEach(r => {
      cumulativeAnswered += r.answered || 0;
      cumulativeCorrect += r.correct || 0;
      studied.push(cumulativeStudied);
      answered.push(cumulativeAnswered);
      correct.push(cumulativeCorrect);
      accuracies.push(r.answered ? Math.round((r.correct / r.answered) * 100) : 0);
    });
    try{ if(chartInstance) chartInstance.destroy(); }catch(e){}
    const ctx = canvas.getContext('2d');
    chartInstance = new Chart(ctx, {
      data: {
        labels,
        datasets: [
          { label:'学習単語数', type: 'line', data: studied, borderColor: 'rgb(73,103,255)', backgroundColor:'rgba(73,103,255,0.12)', fill:true, tension:0.2, yAxisID: 'y' },
          { label:'確認単語数', type: 'line', data: answered, borderColor: 'rgb(24,164,119)', backgroundColor:'rgba(24,164,119,0.12)', fill:true, tension:0.2, yAxisID: 'y' },
          { label:'正答数', type: 'line', data: correct, borderColor: 'rgb(156, 39, 176)', backgroundColor:'rgba(156, 39, 176, 0.12)', fill:true, tension:0.2, yAxisID: 'y' },
          { label:'正答率 (%)', type: 'bar', data: accuracies, borderColor: 'rgba(255, 143, 43, 0.8)', backgroundColor:'rgba(255, 143, 43, 0.4)', yAxisID: 'y1', borderRadius: 4 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero:true, ticks:{precision:0}, title: { display: true, text: '単語数' } },
          y1: {
            type: 'linear',
            beginAtZero: true,
            position: 'right',
            min: 0,
            max: 100,
            suggestedMin: 0,
            suggestedMax: 100,
            grace: '0%',
            ticks: {
              stepSize: 20,
              count: 6,
              includeBounds: true,
              callback: function(value) { return value + '%'; }
            },
            grid: { drawOnChartArea: false },
            title: { display: true, text: '正答率' }
          }
        },
        plugins: { legend: { position: 'bottom' } }
      }
    });
  }

  function renderStats(){
    const days = Number($('#hbt-historyDays')?.value || 30);
    const keys = getDateKeys(days);
    const records = keys.map(key => ({ key, ...(dailyHistory[key] || { studied: 0, answered: 0, correct: 0 }) }));
    const totalStudied = records.reduce((sum, r) => sum + (r.studied || 0), 0);
    const totalAnswered = records.reduce((sum, r) => sum + (r.answered || 0), 0);
    const totalCorrect = records.reduce((sum, r) => sum + (r.correct || 0), 0);
    const activeDays = records.filter(r => r.studied || r.answered).length;
    $('#hbt-studyDays') && ($('#hbt-studyDays').textContent = activeDays);
    $('#hbt-studiedWords') && ($('#hbt-studiedWords').textContent = totalStudied);
    $('#hbt-totalAnswers') && ($('#hbt-totalAnswers').textContent = totalAnswered);
    $('#hbt-correctAnswers') && ($('#hbt-correctAnswers').textContent = totalCorrect);
    $('#hbt-accuracy') && ($('#hbt-accuracy').textContent = totalAnswered ? `${Math.round(totalCorrect / totalAnswered * 100)}%` : '0%');
    $('#hbt-bookmarkTotal') && ($('#hbt-bookmarkTotal').textContent = bookmarks.length);
    drawStudyChart(records);
  }

  function renderAllWords(){
    const box = $('#hbt-allWordList');
    if(!box) return;
    const query = ($('#hbt-wordSearch')?.value || '').trim().toLowerCase();
    const filtered = sortWords(words.filter(w => {
      if(!query) return true;
      return String(w.word).toLowerCase().includes(query)
        || String(w.meaning || '').toLowerCase().includes(query);
    }), listOrder);
    $('#hbt-wordListCount') && ($('#hbt-wordListCount').textContent = `（${filtered.length}語）`);
    if(!filtered.length){
      box.innerHTML = '<div class="hbt-empty">該当する単語がありません。</div>';
      return;
    }
    const headerHtml = `
      <div class="hbt-word-row hbt-word-list-header">
        <div class="hbt-word-main">
          <div class="hbt-word-line">
            <span class="hbt-word-id"><span class="hbt-word-number">abc順番号</span><span class="hbt-word-frequency">頻度順番号</span></span>
            <span class="hbt-word-text">英単語</span>
          </div>
          <div class="hbt-meaning">日本語・用法</div>
        </div>
        <div class="hbt-word-actions">
          <span class="hbt-header-action-label">発音</span>
          <span class="hbt-header-action-label">マーク</span>
        </div>
      </div>
    `;
    box.innerHTML = headerHtml + filtered.map(w => `
      <div class="hbt-word-row">
        <div class="hbt-word-main">
          <div class="hbt-word-line">
            <span class="hbt-word-id"><span class="hbt-word-number">${w.number}</span><span class="hbt-word-frequency">${Number.isFinite(Number(w.frequency)) ? Number(w.frequency) : '-'}</span></span>
            <span class="hbt-word-text">${escapeHtml(w.word)}</span>
          </div>
          <div class="hbt-meaning">${escapeHtml(w.meaning || '')}</div>
        </div>
        <div class="hbt-word-actions">
          <button type="button" class="hbt-icon-btn hbt-speak-btn" data-number="${w.number}" title="発音">🔊</button>
          <button type="button" class="hbt-icon-btn hbt-bookmark-btn" data-number="${w.number}" title="マーク">${bookmarks.includes(Number(w.number)) ? '♥' : '♡'}</button>
        </div>
      </div>
    `).join('');
    $$('.hbt-speak-btn').forEach(button => button.addEventListener('click', () => {
      const number = Number(button.dataset.number);
      const item = words.find(w => Number(w.number) === number);
      if(item) speak(item.word, item.lang || 'en-US');
    }));
    $$('.hbt-bookmark-btn').forEach(button => button.addEventListener('click', () => {
      toggleBookmark(Number(button.dataset.number));
      renderAllWords();
      renderBookmarks();
    }));
  }

  function renderBookmarks(){
    const box = $('#hbt-bookmarkList');
    if(!box) return;
    const marked = sortWords(words.filter(w => bookmarks.includes(Number(w.number))), listOrder);
    if(!marked.length){
      box.innerHTML = '<div class="hbt-empty">マークした単語はまだありません。</div>';
      return;
    }
    box.innerHTML = marked.map(w => `
      <div class="hbt-word-row">
        <div class="hbt-word-main">
          <div class="hbt-word-line"><span class="hbt-word-number">${w.number}</span><span class="hbt-word-text">${escapeHtml(w.word)}</span></div>
          <div class="hbt-meaning">${escapeHtml(w.meaning || '')}</div>
        </div>
        <div class="hbt-word-actions">
          <button type="button" class="hbt-icon-btn hbt-speak-btn" data-number="${w.number}" title="発音">🔊</button>
          <button type="button" class="hbt-icon-btn hbt-remove-bookmark-btn" data-number="${w.number}" title="マーク解除">♥</button>
        </div>
      </div>
    `).join('');
    $$('.hbt-speak-btn').forEach(button => button.addEventListener('click', () => {
      const number = Number(button.dataset.number);
      const item = words.find(w => Number(w.number) === number);
      if(item) speak(item.word, item.lang || 'en-US');
    }));
    $$('.hbt-remove-bookmark-btn').forEach(button => button.addEventListener('click', () => {
      toggleBookmark(Number(button.dataset.number));
      renderBookmarks();
      renderAllWords();
    }));
  }

  function toggleBookmark(number){
    const n = Number(number);
    if(bookmarks.includes(n)){
      bookmarks = bookmarks.filter(x => x !== n);
    } else {
      bookmarks.push(n);
      bookmarks = Array.from(new Set(bookmarks)).sort((a,b) => a - b);
    }
    persistState();
  }

  function setMode(mode){
    selectedMode = mode;
    $('#hbt-studyModeBtn')?.classList.toggle('hbt-active', mode === 'study');
    $('#hbt-testModeBtn')?.classList.toggle('hbt-active', mode === 'test');
    $('#hbt-choiceSetting') && ($('#hbt-choiceSetting').style.display = mode === 'test' ? 'block' : 'none');
    $('#hbt-startModeBtn') && ($('#hbt-startModeBtn').textContent = mode === 'study' ? '学習開始' : '確認開始');
  }

  function setStudyDirection(direction){
    studyDirection = direction;
    persistState();
    $('#hbt-englishToJapaneseBtn')?.classList.toggle('hbt-active', direction === 'en-ja');
    $('#hbt-japaneseToEnglishBtn')?.classList.toggle('hbt-active', direction === 'ja-en');
  }

  function setWordOrder(order){
    wordOrder = normalizeOrder(order);
    persistState();
    $('#hbt-wordOrder') && ($('#hbt-wordOrder').value = wordOrder);
    updateRangeSummary();
  }

  function setWordListOrder(order){
    listOrder = normalizeOrder(order);
    persistState();
    $('#hbt-wordListOrder') && ($('#hbt-wordListOrder').value = listOrder);
    renderAllWords();
    renderBookmarks();
  }

  function getSelectedRange(){
    const markedOnly = $('#hbt-markedOnly')?.checked;
    if(markedOnly){
      const items = sortWords(words.filter(w => bookmarks.includes(Number(w.number))), wordOrder);
      return items.length ? { items } : { error: 'マークした単語がありません。' };
    }
    const start = Number($('#hbt-startNumber')?.value || 1);
    const count = Number($('#hbt-rangeQuestionCount')?.value || 50);
    if(!Number.isInteger(start) || !Number.isInteger(count) || start < 1 || count < 1 || start > 2500){
      return { error: '開始番号と単語数を、1〜2500の範囲で正しく入力してください。' };
    }
    if(wordOrder === 'frequency'){
      const filtered = words.filter(w => Number(w.frequency) >= start);
      const items = sortWords(filtered, 'frequency').slice(0, count);
      return items.length ? { start, count, items } : { error: '指定された範囲に単語がありません。' };
    }
    const filtered = words.filter(w => {
      const n = Number(w.number);
      return n >= start && n <= Math.min(2500, start + count - 1);
    });
    const items = sortWords(filtered, 'number').slice(0, count);
    return items.length ? { start, count, items } : { error: '指定された範囲に単語がありません。' };
  }

  function updateRangeSummary(){
    const markedOnly = $('#hbt-markedOnly')?.checked;
    const start = Number($('#hbt-startNumber')?.value || 1);
    const count = Number($('#hbt-rangeQuestionCount')?.value || 50);
    const summary = $('#hbt-rangeSummary');
    if(!summary) return;
    if(markedOnly){
      $('#hbt-startNumber')?.setAttribute('disabled', 'disabled');
      $('#hbt-rangeQuestionCount')?.setAttribute('disabled', 'disabled');
      summary.textContent = 'マークした単語のみを学習・確認します。';
      summary.classList.remove('hbt-range-error');
      return;
    }
    $('#hbt-startNumber')?.removeAttribute('disabled');
    $('#hbt-rangeQuestionCount')?.removeAttribute('disabled');
    if(!Number.isInteger(start) || !Number.isInteger(count) || start < 1 || count < 1 || start > 2500){
      summary.textContent = '開始番号と単語数を正しく入力してください。';
      summary.classList.add('hbt-range-error');
      return;
    }
    if(wordOrder === 'frequency'){
      summary.textContent = `頻度 ${start} 以上の単語を頻度順に ${count}語`;
    } else {
      summary.textContent = `abc順の番号 ${start} からabc順に ${count}語`;
    }
    summary.classList.remove('hbt-range-error');
  }

  function startActivity(){
    const range = getSelectedRange();
    const activityCard = $('#hbt-activityCard');
    if(activityCard) activityCard.style.display = 'block';
    // Show pronunciation note when starting study/test activity
    const pronounceNote = $('#hbt-pronunciation-note');
    if(pronounceNote) pronounceNote.classList.add('hbt-visible');
    const activityArea = $('#hbt-activityArea');
    if(range.error){
      if(activityArea) activityArea.innerHTML = `<div class="hbt-card"><p class="hbt-note hbt-range-error">${escapeHtml(range.error)}</p></div>`;
      return;
    }
    activity = { items: range.items, index: 0, correct: 0, locked: false };
    if(selectedMode === 'study') showStudyWord(); else showTestQuestion();
    activityCard?.scrollIntoView({ behavior:'smooth', block:'start' });
  }

  function showStudyWord(){
    const area = $('#hbt-activityArea');
    if(!area) return;
    if(activity.index >= activity.items.length){
      area.innerHTML = `<div class="hbt-card"><h2>学習完了！</h2><p class="hbt-note">${activity.items.length}語の学習を終えました。</p><button class="btn btn-primary" id="hbt-restartBtn">もう一度学習する</button></div>`;
      $('#hbt-restartBtn')?.addEventListener('click', startActivity);
      return;
    }
    const item = activity.items[activity.index];
    const question = studyDirection === 'en-ja' ? item.word : item.meaning;
    const answer = studyDirection === 'en-ja' ? item.meaning : item.word;
    const meaningRevealText = studyDirection === 'en-ja' ? '日本語・用法を表示' : '英語を表示';
    const bookmarked = bookmarks.includes(Number(item.number));
    area.innerHTML = `
      <div class="hbt-quiz-top"><span>問題 ${activity.index+1}/${activity.items.length}</span><span>${studyDirection === 'en-ja' ? '英語⇒日本語' : '日本語⇒英語'}</span></div>
      <div class="hbt-study-card">
        <div class="hbt-question-word">${escapeHtml(question)}</div>
        <div class="hbt-study-controls">
          <button type="button" class="btn btn-light" id="hbt-studySpeakBtn">🔊 発音</button>
          <button type="button" class="btn btn-light" id="hbt-bookmarkToggleBtn">${bookmarked ? '♥ マーク解除' : '♡ マーク'}</button>
        </div>
        <div class="hbt-meaning-reveal" id="hbt-meaningReveal"><span>${meaningRevealText}</span></div>
        <div class="hbt-study-controls">
          <button type="button" class="btn btn-light" id="hbt-prevStudyBtn" ${activity.index === 0 ? 'disabled' : ''}>← 前の単語</button>
          <button type="button" class="btn btn-primary" id="hbt-nextStudyBtn">${activity.index === activity.items.length-1 ? '学習を終了' : '次の単語 →'}</button>
        </div>
      </div>
    `;
    $('#hbt-studySpeakBtn')?.addEventListener('click', () => speak(item.word, item.lang || 'en-US'));
    $('#hbt-bookmarkToggleBtn')?.addEventListener('click', () => {
      toggleBookmark(item.number);
      renderAllWords();
      renderBookmarks();
      showStudyWord();
    });
    $('#hbt-meaningReveal')?.addEventListener('click', () => {
      $('#hbt-meaningReveal').innerHTML = `<span class="hbt-meaning-text">${escapeHtml(answer)}</span>`;
    });
    $('#hbt-prevStudyBtn')?.addEventListener('click', () => {
      if(activity.index > 0){ activity.index -= 1; showStudyWord(); }
    });
    $('#hbt-nextStudyBtn')?.addEventListener('click', () => {
      recordStudyWord();
      activity.index += 1;
      showStudyWord();
    });
  }

  function shuffle(array){
    const result = Array.from(array);
    for(let i = result.length -1; i > 0; i--){
      const j = Math.floor(Math.random() * (i + 1));
      [result[i], result[j]] = [result[j], result[i]];
    }
    return result;
  }

  function showTestQuestion(){
    const area = $('#hbt-activityArea');
    if(!area) return;
    if(activity.index >= activity.items.length){
      area.innerHTML = `<div class="hbt-card"><h2>確認終了！</h2><p class="hbt-note">${activity.items.length}問中 ${activity.correct}問正解でした。</p><button class="btn btn-primary" id="hbt-restartBtn">もう一度確認する</button></div>`;
      $('#hbt-restartBtn')?.addEventListener('click', startActivity);
      return;
    }
    activity.locked = false;
    const item = activity.items[activity.index];
    const prompt = studyDirection === 'en-ja' ? item.word : item.meaning;
    const correctAnswer = studyDirection === 'en-ja' ? item.meaning : item.word;
    const choiceCount = 4;
    const pool = words.filter(w => Number(w.number) !== Number(item.number));
    const options = shuffle([item, ...shuffle(pool).slice(0, Math.max(0, choiceCount - 1))]).slice(0, choiceCount);
    area.innerHTML = `
      <div class="hbt-quiz-top"><span>問題 ${activity.index+1}/${activity.items.length}</span><span>正解 ${activity.correct}</span></div>
      <div class="hbt-question-number">${item.number}</div>
      <div class="hbt-question-word">${escapeHtml(prompt)}</div>
      <div class="hbt-study-controls">
        <button type="button" class="btn btn-light" id="hbt-testSpeakBtn">🔊 発音</button>
        <button type="button" class="btn btn-light" id="hbt-testBookmarkBtn">${bookmarks.includes(Number(item.number)) ? '♥ マーク解除' : '♡ マーク'}</button>
      </div>
      <div class="hbt-choices">${options.map(option => `
        <button type="button" class="hbt-choice" data-number="${option.number}">${escapeHtml(studyDirection === 'en-ja' ? option.meaning : option.word)}</button>
      `).join('')}</div>
      <div class="hbt-feedback" id="hbt-feedback"></div>
      <div class="hbt-actions"><button type="button" class="btn btn-primary" id="hbt-nextTestBtn" style="display:none">次の問題</button></div>
    `;
    $('#hbt-testSpeakBtn')?.addEventListener('click', () => speak(item.word, item.lang || 'en-US'));
    $('#hbt-testBookmarkBtn')?.addEventListener('click', () => {
      toggleBookmark(item.number);
      renderAllWords();
      renderBookmarks();
      showTestQuestion();
    });
    $$('.hbt-choice').forEach(button => button.addEventListener('click', () => {
      if(activity.locked) return;
      activity.locked = true;
      const selectedNumber = Number(button.dataset.number);
      const isCorrect = selectedNumber === Number(item.number);
      button.classList.add(isCorrect ? 'hbt-correct' : 'hbt-wrong');
      if(!isCorrect){
        $$('.hbt-choice').find(b => Number(b.dataset.number) === Number(item.number))?.classList.add('hbt-correct');
      }
      $('#hbt-feedback').textContent = isCorrect ? '正解です！' : `不正解。正解：${escapeHtml(correctAnswer)}`;
      if(isCorrect){ activity.correct += 1; }
      recordTestAnswer(isCorrect);
      const nextTestBtn = $('#hbt-nextTestBtn');
      if(nextTestBtn){ nextTestBtn.style.display = 'inline-block'; }
    }));
    $('#hbt-nextTestBtn')?.addEventListener('click', () => {
      activity.index += 1;
      showTestQuestion();
    });
  }


  async function initializeApp(){
    // Local cache is a fallback only. Prefer server-side restore when possible.
    initializeStorage();

    const synced = await syncWithServer();
    if (!synced) {
      console.warn('[Habatan] Server restore failed or unavailable; using local fallback');
    }

    setMode(selectedMode);
    setStudyDirection(studyDirection);
    $('#hbt-wordOrder') && ($('#hbt-wordOrder').value = wordOrder);
    $('#hbt-wordListOrder') && ($('#hbt-wordListOrder').value = listOrder);
    renderAllWords();
    renderBookmarks();
    renderStats();
    updateRangeSummary();

    $$('.hbt-tab').forEach(tab => tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      $$('.hbt-tab').forEach(t => t.classList.toggle('hbt-active', t === tab));
      $$('.hbt-panel').forEach(p => p.classList.toggle('hbt-active', p.id === target));
      if(target === 'hbt-wordlist') renderAllWords();
      if(target === 'hbt-bookmarks') renderBookmarks();
      if(target === 'hbt-stats') renderStats();
      // Show pronunciation note only when speaking buttons are visible
      const pronounceNote = $('#hbt-pronunciation-note');
      const activityCard = $('#hbt-activityCard');
      if(pronounceNote){
        // Show if wordlist/bookmarks or if activity is in progress (home tab with activity shown)
        if(target === 'hbt-wordlist' || target === 'hbt-bookmarks' || (target === 'hbt-home' && activityCard?.style.display !== 'none')){
          pronounceNote.classList.add('hbt-visible');
        } else {
          pronounceNote.classList.remove('hbt-visible');
        }
      }
    }));
    $('#hbt-studyModeBtn')?.addEventListener('click', () => setMode('study'));
    $('#hbt-testModeBtn')?.addEventListener('click', () => setMode('test'));
    $('#hbt-englishToJapaneseBtn')?.addEventListener('click', () => setStudyDirection('en-ja'));
    $('#hbt-japaneseToEnglishBtn')?.addEventListener('click', () => setStudyDirection('ja-en'));
    $('#hbt-startModeBtn')?.addEventListener('click', startActivity);
    $('#hbt-wordOrder')?.addEventListener('change', event => setWordOrder(event.target.value));
    $('#hbt-wordListOrder')?.addEventListener('change', event => setWordListOrder(event.target.value));
    $('#hbt-wordSearch')?.addEventListener('input', renderAllWords);
    $('#hbt-historyDays')?.addEventListener('change', renderStats);
    $('#hbt-startNumber')?.addEventListener('input', updateRangeSummary);
    $('#hbt-rangeQuestionCount')?.addEventListener('input', updateRangeSummary);
    $('#hbt-markedOnly')?.addEventListener('change', updateRangeSummary);
    $('#hbt-resetStats')?.addEventListener('click', () => {
      if(confirm('すべての学習記録をリセットしますか？')){
        stats = { total:0, correct:0 };
        dailyHistory = {};
        persistState();
        renderStats();
      }
    });
  }


  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', initializeApp);
  } else {
    initializeApp();
  }
})();
