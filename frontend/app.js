const form = document.getElementById('search-form');
const statusPanel = document.getElementById('status-panel');
const resultPanel = document.getElementById('result-panel');

async function submitSearch(event) {
  event.preventDefault();
  const formData = new FormData(form);
  const payload = {
    query: formData.get('query') || '',
    field: formData.get('field') || '自動判定',
    foundationalCount: 3,
    trendCount: 5,
    papersPerTrend: 3,
    recentYears: 5,
    languages: ['ja', 'en'],
    publicationTypes: ['article'],
  };

  statusPanel.innerHTML = `
    <div class="status-card">
      <strong>検索を開始しました</strong>
      <p class="muted">結果を待機しています…</p>
    </div>
  `;
  resultPanel.innerHTML = '';

  try {
    const response = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error('検索リクエストに失敗しました');
    }

    const data = await response.json();
    const searchId = data.searchId;

    statusPanel.innerHTML = `
      <div class="status-card">
        <strong>検索IDを受け取りました</strong>
        <p class="muted">結果の取得を開始します…</p>
        <p><strong>${searchId}</strong></p>
      </div>
    `;

    const resultResponse = await fetch(`/api/search/${searchId}`);
    const resultData = await resultResponse.json();

    renderResult(resultData);
  } catch (error) {
    statusPanel.innerHTML = `
      <div class="status-card">
        <strong>エラーが発生しました</strong>
        <p class="muted">${error.message}</p>
      </div>
    `;
  }
}

function renderResult(data) {
  const result = data.result || {};
  const querySummary = result.querySummary || {};
  const foundational = result.foundationalPapers || [];
  const trends = result.researchTrends || [];

  resultPanel.innerHTML = `
    <div class="result-grid">
      <div class="result-card">
        <span class="tag">Query Summary</span>
        <h3>${querySummary.originalQuery || '検索テーマ'}</h3>
        <p><strong>分野:</strong> ${querySummary.detectedField || '自動判定'}</p>
        <p><strong>検索期間:</strong> ${querySummary.searchPeriod?.from || '-'} - ${querySummary.searchPeriod?.to || '-'}</p>
        <p class="muted">${querySummary.modelSummary || 'モデル要約はまだありません。'}</p>
      </div>
      <div class="result-card">
        <span class="tag">Foundational Papers</span>
        <p>${foundational.length ? foundational.length + ' 件の基礎文献候補' : 'まだ基礎文献データはありません'}</p>
        <p class="muted">検索結果の中から、分野理解に重要な文献を整理します。</p>
      </div>
      <div class="result-card">
        <span class="tag">Research Trends</span>
        <p>${trends.length ? trends.length + ' 件の研究潮流候補' : 'まだ研究潮流データはありません'}</p>
        <p class="muted">現在注目されているテーマを、成熟度ごとに整理します。</p>
      </div>
    </div>
  `;
}

form.addEventListener('submit', submitSearch);
