(function () {
  const QUIZ_SIZE = 50;

  const screenStart = document.getElementById('screen-start');
  const screenQuiz = document.getElementById('screen-quiz');
  const screenResult = document.getElementById('screen-result');

  const startStats = document.getElementById('start-stats');
  const btnStart = document.getElementById('btn-start');
  const btnNext = document.getElementById('btn-next');
  const btnRetry = document.getElementById('btn-retry');

  const qIndexEl = document.getElementById('q-index');
  const qTotalEl = document.getElementById('q-total');
  const progressFill = document.getElementById('progress-fill');
  const scoreCountEl = document.getElementById('score-count');

  const qImageWrap = document.getElementById('q-image-wrap');
  const qImage = document.getElementById('q-image');
  const qNumber = document.getElementById('q-number');
  const qText = document.getElementById('q-text');
  const qOptions = document.getElementById('q-options');
  const qFeedback = document.getElementById('q-feedback');

  const resultScore = document.getElementById('result-score');
  const resultSummary = document.getElementById('result-summary');
  const reviewList = document.getElementById('review-list');

  let quizQuestions = [];
  let currentIndex = 0;
  let score = 0;
  let records = [];
  let answered = false;

  const total = (typeof QUESTIONS !== 'undefined') ? QUESTIONS.length : 0;
  startStats.textContent = total > 0
    ? `총 ${total}개 문제 은행에서 무작위로 ${Math.min(QUIZ_SIZE, total)}문제가 출제됩니다.`
    : '문제 데이터를 불러오지 못했습니다. questions.js 파일을 확인하세요.';
  btnStart.disabled = total === 0;

  function shuffle(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function showScreen(el) {
    [screenStart, screenQuiz, screenResult].forEach(s => s.classList.add('hidden'));
    el.classList.remove('hidden');
  }

  function startQuiz() {
    quizQuestions = shuffle(QUESTIONS).slice(0, Math.min(QUIZ_SIZE, QUESTIONS.length));
    currentIndex = 0;
    score = 0;
    records = [];
    qTotalEl.textContent = quizQuestions.length;
    showScreen(screenQuiz);
    renderQuestion();
  }

  function renderQuestion() {
    answered = false;
    const q = quizQuestions[currentIndex];
    qIndexEl.textContent = currentIndex + 1;
    scoreCountEl.textContent = score;
    progressFill.style.width = `${(currentIndex / quizQuestions.length) * 100}%`;

    if (q.image) {
      qImage.src = q.image;
      qImageWrap.classList.remove('hidden');
    } else {
      qImageWrap.classList.add('hidden');
      qImage.removeAttribute('src');
    }

    qNumber.textContent = '';
    qText.textContent = q.text;
    qFeedback.classList.add('hidden');
    qFeedback.textContent = '';
    btnNext.classList.add('hidden');
    qOptions.innerHTML = '';

    if (q.type === 'tf') {
      qOptions.classList.add('tf-options');
      const yes = makeOptionButton('O', '맞음', 'Y', q);
      const no = makeOptionButton('X', '틀림', 'N', q);
      qOptions.appendChild(yes);
      qOptions.appendChild(no);
    } else {
      qOptions.classList.remove('tf-options');
      const labels = ['A', 'B', 'C', 'D'];
      q.options.forEach((opt, i) => {
        qOptions.appendChild(makeOptionButton(labels[i], opt, labels[i], q));
      });
    }
  }

  function makeOptionButton(label, displayText, value, q) {
    const btn = document.createElement('button');
    btn.className = 'opt-btn';
    btn.innerHTML = `<span class="opt-label">${label}</span>${escapeHtml(displayText)}`;
    btn.addEventListener('click', () => selectAnswer(value, q, btn));
    return btn;
  }

  function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function selectAnswer(value, q, btnEl) {
    if (answered) return;
    answered = true;
    const isCorrect = value === q.answer;
    if (isCorrect) score++;

    Array.from(qOptions.children).forEach(btn => {
      btn.disabled = true;
    });
    if (isCorrect) {
      btnEl.classList.add('correct');
    } else {
      btnEl.classList.add('wrong');
      const correctBtn = Array.from(qOptions.children).find(b =>
        b.querySelector('.opt-label').textContent === q.answer
      );
      if (correctBtn) correctBtn.classList.add('correct');
    }

    qFeedback.classList.remove('hidden', 'correct', 'wrong');
    qFeedback.classList.add(isCorrect ? 'correct' : 'wrong');
    qFeedback.textContent = isCorrect ? '정답입니다!' : `오답입니다. 정답: ${answerLabel(q)}`;

    scoreCountEl.textContent = score;
    records.push({ q, selected: value, correct: isCorrect });
    btnNext.classList.remove('hidden');
  }

  function answerLabel(q) {
    if (q.type === 'tf') return q.answer === 'Y' ? 'O (맞음)' : 'X (틀림)';
    const idx = ['A', 'B', 'C', 'D'].indexOf(q.answer);
    return `${q.answer} - ${q.options[idx]}`;
  }

  function nextQuestion() {
    currentIndex++;
    if (currentIndex >= quizQuestions.length) {
      finishQuiz();
    } else {
      renderQuestion();
    }
  }

  function finishQuiz() {
    progressFill.style.width = '100%';
    showScreen(screenResult);
    const pct = Math.round((score / quizQuestions.length) * 100);
    resultScore.textContent = `${score} / ${quizQuestions.length}`;
    resultSummary.textContent = `정답률 ${pct}% · ${pct >= 90 ? '훌륭해요! 합격권입니다.' : pct >= 70 ? '조금 더 연습하면 좋아요.' : '더 많은 복습이 필요해요.'}`;

    reviewList.innerHTML = '';
    const wrongOnes = records.filter(r => !r.correct);
    if (wrongOnes.length === 0) {
      const div = document.createElement('div');
      div.className = 'review-item';
      div.textContent = '모든 문제를 맞혔습니다!';
      reviewList.appendChild(div);
      return;
    }
    const heading = document.createElement('h2');
    heading.textContent = '틀린 문제 복습';
    heading.style.fontSize = '1.1rem';
    reviewList.appendChild(heading);

    wrongOnes.forEach(r => {
      const div = document.createElement('div');
      div.className = 'review-item';
      let html = '';
      if (r.q.image) html += `<img src="${r.q.image}" alt="">`;
      html += `<div class="rv-text">${escapeHtml(r.q.text)}</div>`;
      const yourLabel = r.q.type === 'tf' ? (r.selected === 'Y' ? 'O (맞음)' : 'X (틀림)') : r.selected;
      html += `<div class="rv-answer rv-your">내 답: ${yourLabel}</div>`;
      html += `<div class="rv-answer rv-correct">정답: ${answerLabel(r.q)}</div>`;
      div.innerHTML = html;
      reviewList.appendChild(div);
    });
  }

  btnStart.addEventListener('click', startQuiz);
  btnNext.addEventListener('click', nextQuestion);
  btnRetry.addEventListener('click', () => showScreen(screenStart));
})();
