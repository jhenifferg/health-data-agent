import { useState } from 'react'
import './App.css'

function App() {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [dataset, setDataset] = useState(null)
  const [error, setError] = useState('')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [asking, setAsking] = useState(false)
  const uploadDataset = async () => {
    if (!file) return

    setUploading(true)
    setError('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('http://127.0.0.1:8000/api/datasets', {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data?.error?.message || 'Failed to upload dataset')
      }

      setDataset(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  const askQuestion = async () => {
    if (!question.trim() || !dataset) return

    setAsking(true)
    setError('')

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/api/datasets/${dataset.datasetId}/query`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            question: question.trim(),
          }),
        },
      )

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data?.error?.message || 'Failed to analyze question')
      }

      setAnswer(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setAsking(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">+</div>

          <div>
            <span className="brand-name">Health Data Agent</span>
            <span className="brand-tagline">
              Healthcare data intelligence
            </span>
          </div>
        </div>

        <div className="status">
          <span className="status-dot"></span>
          System ready
        </div>
      </header>

      <section className="hero-section">
        <div className="hero-copy">
          <span className="eyebrow">AI-POWERED HEALTH DATA ANALYSIS</span>

          <h1>
            Explore healthcare data
            <span> through natural language.</span>
          </h1>

          <p>
            Upload healthcare or biomedical datasets and ask questions
            without writing queries. The agent interprets your question
            while deterministic code performs the analysis.
          </p>

          <div className="trust-row">
            <span>Structured analysis</span>
            <span>CSV & ZIP</span>
            <span>Privacy-friendly workflow</span>
          </div>
        </div>

        <div className="health-visual" aria-hidden="true">
          <div className="visual-grid"></div>

          <div className="pulse-line">
            <span></span>
            <span></span>
            <span></span>
          </div>

          <div className="data-card data-card-main">
            <span className="data-label">PATIENT DATA</span>
            <strong>1,171</strong>
            <small>records detected</small>
          </div>

          <div className="data-card data-card-secondary">
            <span className="data-label">DATASETS</span>
            <strong>06</strong>
            <small>connected sources</small>
          </div>

          <div className="cross">+</div>
        </div>
      </section>

      <section className="workspace">
        <div className="workspace-heading">
          <div>
            <span className="section-label">01 / DATASET</span>
            <h2>Start your analysis</h2>
          </div>

          <p>
            Upload a CSV file or a ZIP containing multiple related datasets.
          </p>
        </div>

        <label className="upload-zone">
          <input
            type="file"
            accept=".csv,.zip"
            onChange={(event) => setFile(event.target.files[0] || null)}
          />

          <div className="upload-icon">
            <span>↑</span>
          </div>

          {file ? (
            <>
              <strong>{file.name}</strong>
              <span>Ready to upload</span>
            </>
          ) : (
            <>
              <strong>Drop your health dataset here</strong>
              <span>or click to browse · CSV or ZIP</span>
            </>
          )}
        </label>
        {file && !dataset && (
          <button
            className="upload-button"
            onClick={uploadDataset}
            disabled={uploading}
          >
            {uploading ? 'Processing dataset...' : 'Analyze dataset'}
          </button>
        )}

        {error && <p className="error-message">{error}</p>}

        {dataset && (
          <section className="dataset-summary">
            <span className="section-label">02 / DATASET READY</span>

            <h3>Dataset loaded successfully</h3>

            <div className="summary-grid">
              <div>
                <strong>{dataset.summary.files}</strong>
                <span>files</span>
              </div>

              <div>
                <strong>{dataset.summary.rows.toLocaleString()}</strong>
                <span>rows</span>
              </div>

              <div>
                <strong>{dataset.summary.columns}</strong>
                <span>columns</span>
              </div>
            </div>
          </section>
        )}

        {dataset && (
          <section className="query-section">
            <span className="section-label">03 / ASK THE AGENT</span>

            <h3>Ask a question about your data</h3>

            <div className="query-box">
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Example: How many female patients have diabetes?"
                rows="4"
              />

              <button
                onClick={askQuestion}
                disabled={asking || !question.trim()}
              >
                {asking ? 'Analyzing...' : 'Ask question'}
              </button>
            </div>
          </section>
        )}

        {answer && (
          <section className="answer-section">
            <span className="section-label">04 / RESULT</span>

            <h3>Analysis result</h3>

            <div className="answer-card">
              <p>{answer.answer}</p>
            </div>
          </section>
        )}

        <div className="privacy-note">
          <span className="privacy-icon">✓</span>

          <div>
            <strong>Data-first architecture</strong>
            <p>
              Answers are generated from the uploaded dataset rather than
              relying on built-in clinical assumptions.
            </p>
          </div>
        </div>
      </section>
    </main>
  )
}

export default App