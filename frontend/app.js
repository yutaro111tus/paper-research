const form = document.getElementById('search-form');
const statusPanel = document.getElementById('status-panel');
const resultPanel = document.getElementById('result-panel');


// ============================================================
// Utilities
// ============================================================

function escapeHtml(value) {
  if (value === null || value === undefined) {
    return '';
  }

  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}


function safeUrl(value) {
  if (!value) {
    return '';
  }

  try {
    const url = new URL(value);

    if (
      url.protocol === 'http:' ||
      url.protocol === 'https:'
    ) {
      return url.href;
    }
  } catch (error) {
    return '';
  }

  return '';
}


// ============================================================
// Search
// ============================================================

async function submitSearch(event) {
  event.preventDefault();

  const formData = new FormData(form);

  const payload = {
    query: formData.get('query') || '',
    field: formData.get('field') || 'Auto-detect',

    foundationalCount: 3,
    trendCount: 5,
    papersPerTrend: 3,

    recentYears: 5,

    // English-only output
    languages: ['en'],

    publicationTypes: ['article'],
  };


  statusPanel.innerHTML = `
    <div class="status-card">
      <strong>Searching literature...</strong>
      <p class="muted">
        Searching for foundational papers and current research trends.
      </p>
    </div>
  `;

  resultPanel.innerHTML = '';


  try {
    // --------------------------------------------------------
    // Start search
    // --------------------------------------------------------

    const response = await fetch(
      '/api/search',
      {
        method: 'POST',

        headers: {
          'Content-Type': 'application/json',
        },

        body: JSON.stringify(payload),
      }
    );


    if (!response.ok) {
      throw new Error(
        'Failed to start the research request.'
      );
    }


    const data = await response.json();

    const searchId = data.searchId;


    if (!searchId) {
      throw new Error(
        'No search ID was returned.'
      );
    }


    statusPanel.innerHTML = `
      <div class="status-card">
        <strong>Research completed</strong>

        <p class="muted">
          Retrieving the results...
        </p>

        <p>
          <strong>Search ID:</strong>
          ${escapeHtml(searchId)}
        </p>
      </div>
    `;


    // --------------------------------------------------------
    // Get result
    // --------------------------------------------------------

    const resultResponse = await fetch(
      `/api/search/${encodeURIComponent(searchId)}`,
      {
        cache: 'no-store',
      }
    );


    if (!resultResponse.ok) {
      throw new Error(
        'Failed to retrieve the research result.'
      );
    }


    const resultData =
      await resultResponse.json();


    if (resultData.status === 'error') {
      throw new Error(
        resultData.error ||
        'The research request failed.'
      );
    }


    renderResult(resultData);


    statusPanel.innerHTML = `
      <div class="status-card">
        <strong>Search results ready</strong>

        <p class="muted">
          Foundational papers and research trends have been retrieved.
        </p>

        <p>
          <strong>Search ID:</strong>
          ${escapeHtml(searchId)}
        </p>
      </div>
    `;

  } catch (error) {

    console.error(error);

    statusPanel.innerHTML = `
      <div class="status-card">
        <strong>An error occurred</strong>

        <p class="muted">
          ${escapeHtml(error.message)}
        </p>
      </div>
    `;
  }
}


// ============================================================
// Paper Card
// ============================================================

function renderPaper(
  paper,
  badge = 'Paper'
) {

  const authors =
    Array.isArray(paper.authors)
      ? paper.authors.join(', ')
      : 'Authors not available';


  const publisherUrl =
    safeUrl(paper.publisherUrl);


  const scholarUrl =
    safeUrl(paper.googleScholarUrl);


  const doiUrl =
    paper.doi
      ? `https://doi.org/${encodeURIComponent(paper.doi)}`
      : '';


  const abstract =
    paper.abstract ||
    paper.abstractJa ||
    'No publicly available abstract was verified.';


  const verification =
    paper.verificationStatus ||
    paper.verification?.status ||
    'unknown';


  return `
    <article class="paper-card">

      <div class="paper-header">

        <span class="tag">
          ${escapeHtml(badge)}
        </span>

        <span class="verification-badge">
          ${escapeHtml(verification)}
        </span>

      </div>


      <h3 class="paper-title">
        ${escapeHtml(paper.title || 'Untitled paper')}
      </h3>


      <p class="paper-meta">
        ${escapeHtml(authors)}
      </p>


      <p class="paper-meta">

        ${
          paper.year
            ? escapeHtml(paper.year)
            : ''
        }

        ${
          paper.year && paper.venue
            ? ' · '
            : ''
        }

        ${
          paper.venue
            ? escapeHtml(paper.venue)
            : ''
        }

      </p>


      ${
        paper.doi
          ? `
            <p class="paper-meta">
              <strong>DOI:</strong>
              ${escapeHtml(paper.doi)}
            </p>
          `
          : ''
      }


      <div class="paper-section">

        <h4>
          Abstract / Summary
        </h4>

        <p class="muted">
          ${escapeHtml(abstract)}
        </p>

      </div>


      <div class="paper-section">

        <h4>
          Why this paper matters
        </h4>

        <p class="muted">
          ${
            escapeHtml(
              paper.importanceReason ||
              'No explanation available.'
            )
          }
        </p>

      </div>


      <div class="paper-actions">

        ${
          publisherUrl
            ? `
              <a
                class="paper-button"
                href="${escapeHtml(publisherUrl)}"
                target="_blank"
                rel="noopener noreferrer"
              >
                Publisher / Paper
              </a>
            `
            : ''
        }


        ${
          doiUrl
            ? `
              <a
                class="paper-button"
                href="${escapeHtml(doiUrl)}"
                target="_blank"
                rel="noopener noreferrer"
              >
                DOI
              </a>
            `
            : ''
        }


        ${
          scholarUrl
            ? `
              <a
                class="paper-button"
                href="${escapeHtml(scholarUrl)}"
                target="_blank"
                rel="noopener noreferrer"
              >
                Google Scholar
              </a>
            `
            : ''
        }


        ${
          paper.bibtex
            ? `
              <button
                type="button"
                class="paper-button copy-bibtex"
                data-paper-id="${escapeHtml(paper.id || '')}"
              >
                Copy BibTeX
              </button>
            `
            : ''
        }

      </div>

    </article>
  `;
}


// ============================================================
// Research Trend
// ============================================================

function renderTrend(trend) {

  const name =
    trend.name ||
    trend.nameEn ||
    trend.nameJa ||
    'Research Trend';


  const keywords =
    Array.isArray(trend.keywords)
      ? trend.keywords
      : [];


  const questions =
    Array.isArray(trend.researchQuestions)
      ? trend.researchQuestions
      : [];


  const papers =
    Array.isArray(trend.papers)
      ? trend.papers
      : [];


  return `
    <details class="trend-card" open>

      <summary class="trend-title">

        ${escapeHtml(name)}

        ${
          trend.maturity
            ? `
              <span class="tag">
                ${escapeHtml(trend.maturity)}
              </span>
            `
            : ''
        }

      </summary>


      <div class="trend-content">

        ${
          trend.description
            ? `
              <p class="muted">
                ${escapeHtml(trend.description)}
              </p>
            `
            : ''
        }


        ${
          trend.whyImportantNow
            ? `
              <h4>
                Why it matters now
              </h4>

              <p class="muted">
                ${escapeHtml(trend.whyImportantNow)}
              </p>
            `
            : ''
        }


        ${
          questions.length
            ? `
              <h4>
                Key Research Questions
              </h4>

              <ul>
                ${
                  questions
                    .map(
                      question => `
                        <li>
                          ${escapeHtml(question)}
                        </li>
                      `
                    )
                    .join('')
                }
              </ul>
            `
            : ''
        }


        ${
          keywords.length
            ? `
              <div class="keyword-list">

                ${
                  keywords
                    .map(
                      keyword => `
                        <span class="tag">
                          ${escapeHtml(keyword)}
                        </span>
                      `
                    )
                    .join('')
                }

              </div>
            `
            : ''
        }


        <div class="representative-papers">

          <h4>
            Representative Papers
          </h4>

          ${
            papers.length
              ? papers
                  .map(
                    paper =>
                      renderPaper(
                        paper,
                        'Representative Paper'
                      )
                  )
                  .join('')
              : `
                <p class="muted">
                  No verified representative papers were returned.
                </p>
              `
          }

        </div>

      </div>

    </details>
  `;
}


// ============================================================
// Result Renderer
// ============================================================

function renderResult(data) {

  const result =
    data.result || {};


  const querySummary =
    result.querySummary || {};


  const foundational =
    Array.isArray(result.foundationalPapers)
      ? result.foundationalPapers
      : [];


  const trends =
    Array.isArray(result.researchTrends)
      ? result.researchTrends
      : [];


  const warnings =
    Array.isArray(result.warnings)
      ? result.warnings
      : [];


  // Store BibTeX for copy buttons
  window.paperBibtex = {};


  for (const paper of foundational) {

    if (
      paper.id &&
      paper.bibtex
    ) {
      window.paperBibtex[
        paper.id
      ] = paper.bibtex;
    }
  }


  for (const trend of trends) {

    for (
      const paper
      of (trend.papers || [])
    ) {

      if (
        paper.id &&
        paper.bibtex
      ) {
        window.paperBibtex[
          paper.id
        ] = paper.bibtex;
      }
    }
  }


  resultPanel.innerHTML = `

    <div class="result-grid">


      <!-- Query Summary -->

      <div class="result-card">

        <span class="tag">
          Query Summary
        </span>

        <h3>
          ${
            escapeHtml(
              querySummary.normalizedTopic ||
              querySummary.originalQuery ||
              'Research Topic'
            )
          }
        </h3>


        <p>
          <strong>Field:</strong>
          ${
            escapeHtml(
              querySummary.detectedField ||
              'Auto-detect'
            )
          }
        </p>


        <p>
          <strong>Search period:</strong>

          ${
            escapeHtml(
              querySummary.searchPeriod?.from ||
              '-'
            )
          }

          -

          ${
            escapeHtml(
              querySummary.searchPeriod?.to ||
              '-'
            )
          }
        </p>


        <p class="muted">
          ${
            escapeHtml(
              querySummary.modelSummary ||
              'No research summary available.'
            )
          }
        </p>

      </div>


      <!-- Foundational Papers -->

      <div class="result-card">

        <span class="tag">
          Foundational Papers
        </span>

        <h3>
          ${foundational.length}
          foundational paper${foundational.length === 1 ? '' : 's'}
        </h3>


        <div class="paper-list">

          ${
            foundational.length
              ? foundational
                  .map(
                    paper =>
                      renderPaper(
                        paper,
                        'Foundational Paper'
                      )
                  )
                  .join('')

              : `
                <p class="muted">
                  No verified foundational papers were returned.
                </p>
              `
          }

        </div>

      </div>


      <!-- Research Trends -->

      <div class="result-card">

        <span class="tag">
          Research Trends
        </span>

        <h3>
          ${trends.length}
          research trend${trends.length === 1 ? '' : 's'}
        </h3>


        <div class="trend-list">

          ${
            trends.length
              ? trends
                  .map(
                    trend =>
                      renderTrend(trend)
                  )
                  .join('')

              : `
                <p class="muted">
                  No research trends were returned.
                </p>
              `
          }

        </div>

      </div>


      ${
        warnings.length
          ? `
            <div class="result-card">

              <span class="tag">
                Search Notes
              </span>

              <ul>

                ${
                  warnings
                    .map(
                      warning => `
                        <li>
                          ${escapeHtml(warning)}
                        </li>
                      `
                    )
                    .join('')
                }

              </ul>

            </div>
          `
          : ''
      }


    </div>
  `;
}


// ============================================================
// BibTeX Copy
// ============================================================

resultPanel.addEventListener(
  'click',
  async event => {

    const button =
      event.target.closest(
        '.copy-bibtex'
      );


    if (!button) {
      return;
    }


    const paperId =
      button.dataset.paperId;


    const bibtex =
      window.paperBibtex?.[
        paperId
      ];


    if (!bibtex) {
      return;
    }


    try {

      await navigator.clipboard.writeText(
        bibtex
      );


      const originalText =
        button.textContent;


      button.textContent =
        'Copied';


      setTimeout(
        () => {

          button.textContent =
            originalText;

        },
        1200
      );

    } catch (error) {

      console.error(
        'Failed to copy BibTeX:',
        error
      );

    }
  }
);


// ============================================================
// Submit Event
// ============================================================

form.addEventListener(
  'submit',
  submitSearch
);