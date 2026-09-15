import { useMemo, useRef, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import './App.css'

const API = import.meta.env.VITE_API_BASE_URL || ''
const prompts = [
  'How many patients are in the dataset?',
  'What are the 5 most frequent conditions?',
  'How many female patients have diabetes?',
]

function Icon({ name, size = 19 }) {
  const paths = {
    upload: <><path d="M12 16V4m0 0L7 9m5-5 5 5M5 20h14" /></>,
    data: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5m-8 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></>,
    ask: <><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 9h8m-8 4h5"/></>,
    chart: <><path d="M4 20V10m6 10V4m6 16v-7M22 20H2"/></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></>,
    file: <><path d="M6 2h8l4 4v16H6z"/><path d="M14 2v5h5"/></>,
    arrow: <><path d="M5 12h14m-5-5 5 5-5 5"/></>,
    spark: <><path d="m12 3 1.4 4.1 4.1 1.4-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4z"/></>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    check: <path d="m5 12 4 4L19 6"/>,
  }
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

function chartFor(data) {
  if (data?.type !== 'aggregate' || data.columns?.length !== 2 || !data.rows?.length) return null
  const [a, b] = data.columns
  if (typeof data.rows[0]?.[a] !== 'number' && typeof data.rows[0]?.[b] === 'number') return { category: a, value: b }
  if (typeof data.rows[0]?.[a] === 'number' && typeof data.rows[0]?.[b] !== 'number') return { category: b, value: a }
  return null
}

export default function App() {
  const input = useRef(null)
  const [file, setFile] = useState(null)
  const [dataset, setDataset] = useState(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const chart = useMemo(() => chartFor(answer?.data), [answer])

  const choose = (selected) => {
    if (!selected) return
    if (!/\.(csv|zip)$/i.test(selected.name)) return setError('Choose a CSV file or a ZIP containing CSV files.')
    setFile(selected); setDataset(null); setAnswer(null); setError('')
  }

  const upload = async (selected = file) => {
    if (!selected) return
    setBusy('upload'); setError('')
    const body = new FormData(); body.append('file', selected)
    try {
      const response = await fetch(`${API}/api/datasets`, { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.error?.message || 'The dataset could not be processed.')
      setFile(selected); setDataset(data); setAnswer(null)
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  const demo = async () => {
    setBusy('upload'); setError('')
    try {
      const response = await fetch('/demo/health-demo.zip')
      if (!response.ok) throw new Error('The demo dataset is unavailable.')
      const sample = new File([await response.blob()], 'synthetic-health-demo.zip', { type: 'application/zip' })
      await upload(sample)
    } catch (err) { setError(err.message); setBusy('') }
  }

  const ask = async (suggestion) => {
    const prompt = typeof suggestion === 'string' ? suggestion : question.trim()
    if (!prompt || !dataset) return
    setQuestion(prompt); setBusy('ask'); setError(''); setAnswer(null)
    try {
      const response = await fetch(`${API}/api/datasets/${dataset.datasetId}/query`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: prompt }) })
      const data = await response.json()
      if (!response.ok) throw new Error(response.status === 429 ? 'The AI service is busy. Please try again shortly.' : data?.error?.message || 'The question could not be analyzed.')
      setAnswer(data)
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  const reset = () => { setFile(null); setDataset(null); setQuestion(''); setAnswer(null); setError(''); if (input.current) input.current.value = '' }

  return <div className="app">
    <header>
      <a className="brand" href="#top"><b>H</b><span>Health Data Agent</span></a>
      <div className="header-right"><span className="online"><i/>Demo environment</span><a href="https://github.com/jhenifferg/health-data-agent" target="_blank" rel="noreferrer">View source ↗</a></div>
    </header>

    <main id="top">
      <section className="hero">
        <div>
          <p className="eyebrow">HEALTHCARE ANALYTICS <i/> NATURAL LANGUAGE</p>
          <h1>Ask your health data.<br/><em>Get evidence, not guesses.</em></h1>
          <p className="lead">Upload related CSV files in one ZIP. Ask questions in plain language and receive answers calculated directly from your data.</p>
          <div className="hero-actions"><button className="primary" onClick={() => document.querySelector('#workspace').scrollIntoView({ behavior: 'smooth' })}>Start exploring <Icon name="arrow" size={16}/></button><button className="link-button" onClick={demo} disabled={busy}><Icon name="spark"/> Try synthetic demo</button></div>
        </div>
        <div className="method">
          <div className="method-title"><span>HOW IT WORKS</span><b>Deterministic output</b></div>
          {[['ask','Question','interpreted by AI'],['data','Structured query','validated by the pipeline'],['chart','Evidence','calculated with Pandas']].map(([icon,title,copy], index) => <div className="method-step" key={title}><span className={index === 2 ? 'method-icon active' : 'method-icon'}><Icon name={icon}/></span><p><strong>{title}</strong><small>{copy}</small></p></div>)}
          <div className="proof"><Icon name="shield"/><span>The model plans the query. It never calculates the result.</span></div>
        </div>
      </section>

      <section className="workspace" id="workspace">
        <div className="workspace-title"><div><span className="label">ANALYSIS WORKSPACE</span><h2>{dataset ? 'Your data is ready to explore' : 'Bring your datasets together'}</h2><p>{dataset ? `${dataset.summary.files} sources connected in one temporary session.` : 'Upload one CSV or a ZIP with related files. Use synthetic data only in this public demo.'}</p></div>{dataset && <button className="outline" onClick={reset}><Icon name="close" size={15}/> New analysis</button>}</div>
        <nav className="steps">{['Upload','Inspect','Ask','Review'].map((item,index) => { const current = dataset ? (answer ? 3 : 2) : 0; return <span className={index <= current ? 'done' : ''} key={item}><b>{index < current ? <Icon name="check" size={12}/> : index+1}</b>{item}</span> })}</nav>

        {!dataset ? <>
          <div className="upload-grid">
            <div className="drop" role="button" tabIndex="0" onClick={() => input.current?.click()} onKeyDown={(event) => event.key === 'Enter' && input.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); choose(event.dataTransfer.files[0]) }}>
              <input ref={input} hidden type="file" accept=".csv,.zip" onChange={(event) => choose(event.target.files[0])}/><span className="upload-icon"><Icon name="upload" size={25}/></span><strong>{file?.name || 'Drop your dataset here'}</strong><small>{file ? `${(file.size/1024).toFixed(1)} KB · ready to process` : 'CSV or ZIP · click to browse'}</small>{file && <button className="primary compact" onClick={(event) => { event.stopPropagation(); upload() }} disabled={busy}>{busy ? 'Reading datasets…' : 'Analyze dataset'} <Icon name="arrow" size={15}/></button>}
            </div>
            <aside className="demo"><Icon name="spark"/><div><span className="label">NO DATASET?</span><h3>Use synthetic health data</h3><p>Explore patients, encounters and conditions without uploading a file.</p></div><button onClick={demo} disabled={busy}>{busy ? 'Preparing demo…' : 'Load demo dataset'} <Icon name="arrow" size={15}/></button></aside>
          </div>
          <p className="privacy"><Icon name="shield" size={15}/> Public demonstration: do not upload identifiable or sensitive patient information.</p>
        </> : <div className="analysis">
          <aside className="sources"><div className="panel-title"><span><Icon name="data"/>Data sources</span><small>{dataset.summary.rows.toLocaleString()} rows</small></div><div className="source-list">{dataset.datasets.map(item => <details key={item.name}><summary><span className="file"><Icon name="file" size={16}/></span><span><strong>{item.name}</strong><small>{item.rows.toLocaleString()} rows · {item.columnCount} columns</small></span><b>›</b></summary><div className="columns">{item.columns.map(column => <span key={column.name}>{column.name}<small>{column.type}</small></span>)}</div></details>)}</div><div className="totals"><span><b>{dataset.summary.files}</b>files</span><span><b>{dataset.summary.columns}</b>columns</span><span><b>{dataset.summary.rows.toLocaleString()}</b>rows</span></div></aside>
          <div className="query"><div className="query-title"><span><Icon name="spark"/></span><div><small className="label">DATA ASSISTANT</small><h3>What would you like to know?</h3></div></div><div className="suggestions">{prompts.map(prompt => <button key={prompt} onClick={() => ask(prompt)} disabled={busy}>{prompt}<Icon name="arrow" size={13}/></button>)}</div><div className="composer"><textarea rows="3" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && (event.metaKey || event.ctrlKey) && ask()} placeholder="Ask a question across your datasets…" disabled={busy}/><div><small>⌘ + Enter to submit</small><button onClick={() => ask()} disabled={busy || !question.trim()}>{busy === 'ask' ? <><i className="spinner"/>Analyzing</> : <>Ask data <Icon name="arrow" size={15}/></>}</button></div></div>
          {error && <div className="alert"><strong>We couldn’t complete that action.</strong><span>{error}</span></div>}
          {answer && <section className="results"><div className="result-title"><div><span className="label">ANALYSIS RESULT</span><h3>Answer from your data</h3></div><span><Icon name="check" size={13}/>Computed result</span></div><div className={answer.data?.type === 'count' ? 'answer count' : 'answer'}>{answer.data?.type === 'count' && <strong>{answer.data.value.toLocaleString()}</strong>}<p>{answer.answer}</p></div>
          {chart && <div className="chart"><span className="label">VISUAL SUMMARY</span><ResponsiveContainer width="100%" height={290}><BarChart data={answer.data.rows} margin={{top:20,right:15,left:0,bottom:55}}><CartesianGrid stroke="#e8eceb" vertical={false}/><XAxis dataKey={chart.category} angle={-30} textAnchor="end" interval={0} height={68} tick={{fontSize:10,fill:'#65716e'}} axisLine={false} tickLine={false}/><YAxis tick={{fontSize:10,fill:'#65716e'}} axisLine={false} tickLine={false}/><Tooltip/><Bar dataKey={chart.value} fill="#147d64" radius={[5,5,0,0]}/></BarChart></ResponsiveContainer></div>}
          {['table','aggregate'].includes(answer.data?.type) && <div className="table"><div><table><thead><tr>{answer.data.columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{answer.data.rows.map((row,index) => <tr key={index}>{answer.data.columns.map(column => <td key={column}>{String(row[column] ?? '')}</td>)}</tr>)}</tbody></table></div>{answer.data.truncated && <p>Showing {answer.data.returnedRows} rows. Additional results were omitted.</p>}</div>}</section>}
          </div>
        </div>}
        {error && !dataset && <div className="alert standalone"><strong>We couldn’t process that file.</strong><span>{error}</span></div>}
      </section>

      <section className="principles">{[['01','Multi-file by design','Inspect related CSVs together and query relationships across datasets.'],['02','Grounded in evidence','Calculations run deterministically against the uploaded data.'],['03','Built for exploration','A portfolio demonstration using synthetic, non-identifiable data.']].map(([number,title,copy]) => <div key={number}><span>{number}</span><h3>{title}</h3><p>{copy}</p></div>)}</section>
    </main>
    <footer><b>Health Data Agent</b><span>Healthcare data exploration · Not for clinical decision-making</span><a href="https://github.com/jhenifferg/health-data-agent" target="_blank" rel="noreferrer">GitHub ↗</a></footer>
  </div>
}
