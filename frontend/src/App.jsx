import { useState } from "react"
import "./App.css"

const API_URL = "http://localhost:8000/validate"

const KIND_COLOUR = {
  expired:             "#dc2626",
  expires_during_task: "#d97706",
  not_recent:          "#d97706",
  missing:             "#dc2626",
  insufficient_staff:  "#7c3aed",
}

function Badge({ kind }) {
  return (
    <span className="badge" style={{ background: KIND_COLOUR[kind] ?? "#555" }}>
      {kind.replace(/_/g, " ")}
    </span>
  )
}


// Overview tab

function OverviewTab({ data, onSelectTask }) {
  const ov = data.overview
  return (
    <div>
      <div className="stat-row">
        <div className="stat-card">
          <div className="stat-value">{ov.total_tasks}</div>
          <div className="stat-label">Tasks</div>
        </div>
        <div className="stat-card stat-good">
          <div className="stat-value">{ov.covered}</div>
          <div className="stat-label">Covered</div>
        </div>
        <div className="stat-card stat-bad">
          <div className="stat-value">{ov.at_risk}</div>
          <div className="stat-label">At Risk</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{ov.total_violations}</div>
          <div className="stat-label">Violations</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{ov.total_staff}</div>
          <div className="stat-label">Staff</div>
        </div>
      </div>

      <h3 className="section-title">Task Coverage</h3>
      <div className="task-grid">
        {data.tasks.map(t => (
          <div
            key={t.name}
            className={`task-card ${t.status === "at_risk" ? "task-at-risk" : "task-ok"}`}
            onClick={() => onSelectTask(t.name)}
          >
            <div className="task-card-header">
              <span className="task-name">{t.name.replace(/_/g, " ")}</span>
              <span className={`status-dot ${t.status}`} />
            </div>
            <div className="task-card-meta">
              {t.window.start} to {t.window.end}
              {t.location && <> &middot; {t.location}</>}
            </div>
            <div className="coverage-row">
              <div className="coverage-bar">
                <div
                  className={`coverage-fill ${t.status}`}
                  style={{ width: `${Math.min(100, (t.eligible.length / t.min_staff) * 100)}%` }}
                />
              </div>
              <span className="coverage-text">
                {t.eligible.length}/{t.min_staff} staff
              </span>
            </div>
            {t.violations.length > 0 && (
              <div className="task-card-footer">
                {t.violations.length} violation{t.violations.length !== 1 ? "s" : ""}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}


// Tasks tab

function TasksTab({ data, selectedTask, onSelectTask }) {
  const current = data.tasks.find(t => t.name === selectedTask) || data.tasks[0]
  if (!current) return <p className="muted">No tasks to show.</p>

  return (
    <div className="split-layout">
      <div className="task-sidebar">
        {data.tasks.map(t => (
          <div
            key={t.name}
            className={`sidebar-item ${t.name === current.name ? "active" : ""}`}
            onClick={() => onSelectTask(t.name)}
          >
            <span className={`status-dot ${t.status}`} />
            <span>{t.name.replace(/_/g, " ")}</span>
          </div>
        ))}
      </div>

      <div className="task-detail">
        <h2>{current.name.replace(/_/g, " ")}</h2>
        <div className="detail-meta">
          <span>{current.window.start} to {current.window.end}</span>
          {current.location && <span>{current.location}</span>}
          {current.aircraft && <span>{current.aircraft}</span>}
        </div>

        {current.status === "at_risk" && (
          <div className="warning-banner">
            Understaffed — needs {current.min_staff}, only {current.eligible.length} eligible
          </div>
        )}

        <div className="detail-section">
          <h4>Required Qualifications</h4>
          <div className="qual-list">
            {current.required_quals.map(q => (
              <span key={q} className="qual-tag">{q.replace(/_/g, " ")}</span>
            ))}
          </div>
        </div>

        {current.eligible.length > 0 && (
          <div className="detail-section">
            <h4>
              Eligible Staff ({current.eligible.length})
              {current.prefer && (
                <span className="prefer-label">{current.prefer.replace(/_/g, " ")}</span>
              )}
            </h4>
            <div className="eligible-list">
              {current.eligible.map((name, i) => (
                <span key={name} className="eligible-name">
                  {current.prefer && <span className="rank-num">#{i + 1}</span>}
                  {name}
                </span>
              ))}
            </div>
          </div>
        )}

        {current.violations.length > 0 && (
          <div className="detail-section">
            <h4>Non-Compliant Staff</h4>
            <NonCompliantList violations={current.violations} />
          </div>
        )}
      </div>
    </div>
  )
}

function NonCompliantList({ violations }) {
  // group by staff
  const grouped = {}
  for (const v of violations) {
    if (!grouped[v.staff]) grouped[v.staff] = []
    grouped[v.staff].push(v)
  }

  const [expanded, setExpanded] = useState({})
  const toggle = name => setExpanded(prev => ({ ...prev, [name]: !prev[name] }))

  return (
    <div className="noncompliant">
      {Object.entries(grouped).map(([name, vs]) => (
        <div key={name} className="nc-group">
          <div className="nc-header" onClick={() => toggle(name)}>
            <span className="nc-arrow">{expanded[name] ? "v" : ">"}</span>
            <span className="nc-name">{name}</span>
            <span className="nc-count">{vs.length} issue{vs.length !== 1 ? "s" : ""}</span>
          </div>
          {expanded[name] && (
            <div className="nc-details">
              {vs.map((v, i) => (
                <div key={i} className="nc-row">
                  <Badge kind={v.kind} />
                  <span>{v.qualification?.replace(/_/g, " ")}</span>
                  {v.on_date && <span className="nc-date">{v.on_date}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}


// Staff tab

function StaffTab({ data }) {
  const [search, setSearch] = useState("")
  const [expanded, setExpanded] = useState({})

  const toggle = name => setExpanded(prev => ({ ...prev, [name]: !prev[name] }))

  const filtered = data.staff.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div>
      <input
        className="search-box"
        type="text"
        placeholder="Search staff..."
        value={search}
        onChange={e => setSearch(e.target.value)}
      />

      <div className="staff-list">
        {filtered.map(s => {
          const ratio = `${s.tasks_eligible.length}/${s.tasks_checked.length}`
          const allGood = s.violation_count === 0
          return (
            <div key={s.name} className="staff-card">
              <div className="staff-header" onClick={() => toggle(s.name)}>
                <div className="staff-info">
                  <span className="staff-name">{s.name}</span>
                  <span className="staff-meta">{s.role.replace(/_/g, " ")} {s.base && `· ${s.base}`}</span>
                </div>
                <div className="staff-status">
                  <span className={`staff-ratio ${allGood ? "good" : "warn"}`}>
                    {ratio} tasks
                  </span>
                  {s.violation_count > 0 && (
                    <span className="staff-violations">{s.violation_count} violations</span>
                  )}
                </div>
              </div>
              {expanded[s.name] && s.violations.length > 0 && (
                <div className="staff-details">
                  {s.violations.map((v, i) => (
                    <div key={i} className="staff-violation-row">
                      <Badge kind={v.kind} />
                      <span>{v.task?.replace(/_/g, " ")}</span>
                      <span className="muted">{v.qualification?.replace(/_/g, " ")}</span>
                      {v.on_date && <span className="nc-date">{v.on_date}</span>}
                    </div>
                  ))}
                </div>
              )}
              {expanded[s.name] && s.violations.length === 0 && (
                <div className="staff-details">
                  <p className="all-clear">Fully compliant for all checked tasks</p>
                </div>
              )}
            </div>
          )
        })}
        {filtered.length === 0 && <p className="muted">No staff match "{search}"</p>}
      </div>
    </div>
  )
}


// Violations tab

function ViolationsTab({ data }) {
  const [filterKind, setFilterKind] = useState("")
  const [filterTask, setFilterTask] = useState("")
  const [filterStaff, setFilterStaff] = useState("")

  const violations = data.violations
  const kinds = [...new Set(violations.map(v => v.kind))]
  const tasks = [...new Set(violations.map(v => v.task))]
  const staffNames = [...new Set(violations.filter(v => v.staff).map(v => v.staff))]

  const rows = violations.filter(v =>
    (!filterKind  || v.kind  === filterKind) &&
    (!filterTask  || v.task  === filterTask) &&
    (!filterStaff || v.staff === filterStaff)
  )

  function handleExport() {
    const json = JSON.stringify(data.violations, null, 2)
    const blob = new Blob([json], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "foresight-violations.json"
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="filters">
        <select value={filterKind} onChange={e => setFilterKind(e.target.value)}>
          <option value="">All kinds</option>
          {kinds.map(k => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}
        </select>
        <select value={filterTask} onChange={e => setFilterTask(e.target.value)}>
          <option value="">All tasks</option>
          {tasks.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={filterStaff} onChange={e => setFilterStaff(e.target.value)}>
          <option value="">All staff</option>
          {staffNames.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button className="export-btn" onClick={handleExport}>Export</button>
      </div>

      <table>
        <thead>
          <tr>
            <th>Kind</th>
            <th>Task</th>
            <th>Staff</th>
            <th>Qualification</th>
            <th>Date</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((v, i) => (
            <tr key={i}>
              <td><Badge kind={v.kind} /></td>
              <td>{v.task ?? "-"}</td>
              <td>{v.staff ?? "-"}</td>
              <td>{v.qualification?.replace(/_/g, " ") ?? "-"}</td>
              <td>{v.on_date ?? "-"}</td>
              <td className="detail">{v.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="muted">No violations match the filters.</p>}
    </div>
  )
}


// App shell

const TABS = ["Overview", "Tasks", "Staff", "Violations"]

export default function App() {
  const [result, setResult]   = useState(null)
  const [error, setError]     = useState(null)
  const [loading, setLoading] = useState(false)
  const [tab, setTab]         = useState("Overview")
  const [selectedTask, setSelectedTask] = useState(null)

  function goToTask(taskName) {
    setSelectedTask(taskName)
    setTab("Tasks")
  }

  async function handleFile(e) {
    const file = e.target.files[0]
    if (!file) return

    setLoading(true)
    setError(null)
    setResult(null)

    const body = new FormData()
    body.append("file", file)

    try {
      const res  = await fetch(API_URL, { method: "POST", body })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? "Unknown error")
      setResult(data)
      setTab("Overview")
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header>
        <div className="header-row">
          <div>
            <h1>Foresight</h1>
            <p className="subtitle">Aviation maintenance qualification compliance</p>
          </div>
          <label className="upload-btn">
            <input type="file" accept=".aero" onChange={handleFile} />
            {result ? "Upload new file" : "Choose .aero file"}
          </label>
        </div>
      </header>

      {loading && <p className="muted">Validating...</p>}
      {error   && <p className="error">Error: {error}</p>}

      {result && (
        <>
          <nav className="tab-bar">
            {TABS.map(t => (
              <button
                key={t}
                className={`tab-btn ${tab === t ? "active" : ""}`}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </nav>

          <div className="tab-content">
            {tab === "Overview"   && <OverviewTab data={result} onSelectTask={goToTask} />}
            {tab === "Tasks"      && <TasksTab data={result} selectedTask={selectedTask} onSelectTask={setSelectedTask} />}
            {tab === "Staff"      && <StaffTab data={result} />}
            {tab === "Violations" && <ViolationsTab data={result} />}
          </div>
        </>
      )}
    </div>
  )
}
