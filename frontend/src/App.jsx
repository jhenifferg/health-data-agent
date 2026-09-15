import { useState } from 'react'
import './App.css'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'

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
    setAnswer(null)

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
        if (response.status === 422) {
          console.error('422 response:', data)

          const detail = Array.isArray(data?.detail)
            ? data.detail.map((item) => item.msg).join(' | ')
            : data?.detail

          throw new Error(
            detail || 'The request could not be validated.',
          )
        }
        if (response.status === 429) {
          throw new Error(
            'The AI provider is temporarily rate-limited. Please try again in a few minutes.',
          )
        }

        throw new Error(data?.error?.message || 'Failed to analyze question')
      }

      setAnswer(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setAsking(false)
    }
  }

  const getChartConfig = (data) => {
    if (data?.type !== 'aggregate' || !data.rows?.length) {
      return null
    }

    if (data.columns.length !== 2) {
      return null
    }

    const [firstColumn, secondColumn] = data.columns
    const firstValue = data.rows[0]?.[firstColumn]
    const secondValue = data.rows[0]?.[secondColumn]

    if (
      typeof firstValue !== 'number' &&
      typeof secondValue === 'number'
    ) {
      return {
        category: firstColumn,
        value: secondColumn,
      }
    }

    if (
      typeof firstValue === 'number' &&
      typeof secondValue !== 'number'
    ) {
      return {
        category: secondColumn,
        value: firstColumn,
      }
    }

    return null
  }

  const chartConfig = getChartConfig(answer?.data)

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
            <span className="data-label">
              {dataset ? 'DATA RECORDS' : 'DATA ANALYSIS'}
            </span>

            <strong>
              {dataset
                ? dataset.summary.rows.toLocaleString()
                : 'Ready'}
            </strong>

            <small>
              {dataset
                ? 'records loaded'
                : 'waiting for dataset'}
            </small>
          </div>

          <div className="data-card data-card-secondary">
            <span className="data-label">DATASETS</span>

            <strong>
              {dataset
                ? String(dataset.summary.files).padStart(2, '0')
                : '—'}
            </strong>

            <small>
              {dataset
                ? 'connected sources'
                : 'upload CSV or ZIP'}
            </small>
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

        <label
          className={`upload-zone ${uploading ? 'uploading' : ''}`}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault()

            const droppedFile = event.dataTransfer.files[0]

            if (
              droppedFile &&
              !(
                droppedFile.name.toLowerCase().endsWith('.csv') ||
                droppedFile.name.toLowerCase().endsWith('.zip')
              )
            ) {
              setError('Please upload a CSV or ZIP file.')
              return
            }

            if (
              droppedFile &&
              (droppedFile.name.toLowerCase().endsWith('.csv') ||
                droppedFile.name.toLowerCase().endsWith('.zip'))
            ) {

              setFile(droppedFile)
              setDataset(null)
              setAnswer(null)
              setError('')
            }
          }}
        >
          <input
            type="file"
            accept=".csv,.zip"
            disabled={uploading}
            onChange={(event) => {
              const selectedFile = event.target.files[0]
              if (
                selectedFile &&
                !(
                  selectedFile.name.toLowerCase().endsWith('.csv') ||
                  selectedFile.name.toLowerCase().endsWith('.zip')
                )
              ) {
                setError('Please upload a CSV or ZIP file.')
                event.target.value = ''
                return
              }

              if (
                selectedFile &&
                (selectedFile.name.toLowerCase().endsWith('.csv') ||
                  selectedFile.name.toLowerCase().endsWith('.zip'))
              ) {
                setFile(selectedFile)
                setDataset(null)
                setAnswer(null)
                setError('')
              }
            }}
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
          <div className="selected-file">
            <div>
              <strong>{file.name}</strong>
              <span>{(file.size / 1024 / 1024).toFixed(2)} MB</span>
            </div>

            <button
              type="button"
              aria-label="Remove selected file"
              onClick={() => {
                setFile(null)
                setError('')
              }}
            >
              ×
            </button>
          </div>
        )}

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

            <button
              className="remove-dataset-button"
              onClick={() => {
                setDataset(null)
                setFile(null)
                setQuestion('')
                setAnswer(null)
                setError('')
              }}
            >
              Remove dataset
            </button>

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

            <div className="dataset-overview">
              <div className="overview-heading">
                <h4>Dataset overview</h4>
                <span>{dataset.datasets.length} sources detected</span>
              </div>

              <div className="dataset-list">
                {dataset.datasets.map((item) => (
                  <details className="dataset-item" key={item.name}>
                    <summary>
                      <div className="dataset-item-name">
                        <span className="dataset-file-icon">CSV</span>

                        <div>
                          <strong>{item.name}</strong>
                          <span>{item.columnCount} columns</span>
                        </div>
                      </div>

                      <strong className="dataset-row-count">
                        {item.rows.toLocaleString()}
                        <span> rows</span>
                      </strong>
                    </summary>

                    <div className="column-list">
                      {item.columns.map((column) => (
                        <div className="column-item" key={column.name}>
                          <span>{column.name}</span>
                          <small>{column.type}</small>
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            </div>
          </section>
        )}

        {dataset && (
          <section className="query-section">
            <span className="section-label">03 / ASK THE AGENT</span>

            <h3>Ask a question about your data</h3>

            <div className="question-suggestions">
              {[
                'How many records are in this dataset?',
                'What are the most frequent values?',
                'Show the top 5 results',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => setQuestion(suggestion)}
                  disabled={asking}
                >
                  {suggestion}
                </button>
              ))}
            </div>

            <div className="query-box">
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Example: How many female patients have diabetes?"
                rows="4"
                disabled={asking}
              />

              <button
                onClick={askQuestion}
                disabled={asking || !question.trim()}
              >
                {asking ? (
                  <>
                    <span className="spinner" />
                    Analyzing data...
                  </>
                ) : (
                  'Ask question'
                )}
              </button>
            </div>
          </section>
        )}

        {answer && (
          <section className="answer-section">
            <span className="section-label">04 / RESULT</span>

            <h3>Analysis result</h3>

            <div className="answer-card">
              {answer.data?.type === 'count' ? (
                <div className="count-result">
                  <strong>{answer.data.value}</strong>
                  <p>{answer.answer}</p>
                </div>
              ) : (
                <p>{answer.answer}</p>
              )}
            </div>

            {chartConfig && (
              <div className="chart-card">
                <div className="chart-heading">
                  <div>
                    <span>DATA VISUALIZATION</span>
                    <h4>Visual summary</h4>
                  </div>
                </div>

                <div className="chart-container">
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart
                      data={answer.data.rows}
                      margin={{ top: 10, right: 20, left: 10, bottom: 60 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />

                      <XAxis
                        dataKey={chartConfig.category}
                        angle={-35}
                        textAnchor="end"
                        interval={0}
                        height={80}
                      />

                      <YAxis />

                      <Tooltip />

                      <Bar
                        dataKey={chartConfig.value}
                        fill="#087f72"
                        radius={[6, 6, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {['table', 'aggregate'].includes(answer.data?.type) && (
              <div className="result-table-wrapper">

              <table className="result-table">
                <thead>
                  <tr>
                    {answer.data.columns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {answer.data.rows.map((row, index) => (
                    <tr key={index}>
                      {answer.data.columns.map((column) => (
                        <td key={column}>{String(row[column] ?? '')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {answer.data?.type === 'table' && answer.data.truncated && (
            <p className="table-note">
              Showing {answer.data.returnedRows} results. The full dataset contains additional records.
            </p>
          )}

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
