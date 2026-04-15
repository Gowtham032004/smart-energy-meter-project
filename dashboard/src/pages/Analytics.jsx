import { useState, useEffect } from 'react'
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import axios from 'axios'
import { format, parseISO, subDays, startOfDay } from 'date-fns'

const API    = '/api'
const DEVICE = 'METER_001'

const DOW_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const Tip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, padding: '10px 14px', fontSize: 12 }}>
      <p style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color, fontWeight: 600 }}>{p.name}: {Number(p.value).toFixed(2)}</p>
      ))}
    </div>
  )
}

// ── Heatmap ──────────────────────────────────────────────────────────────────
function Heatmap({ data }) {
  const maxVal = Math.max(...data.map(d => d.value), 1)

  const getColor = (val) => {
    const pct = val / maxVal
    if (pct < 0.2) return '#1a2744'
    if (pct < 0.4) return '#0f4c7a'
    if (pct < 0.6) return '#0369a1'
    if (pct < 0.8) return '#0ea5e9'
    return '#00d4ff'
  }

  const hours = Array.from({ length: 24 }, (_, i) => i)

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: `40px repeat(7, 1fr)`, gap: 3, marginBottom: 4 }}>
        <div />
        {DOW_LABELS.map(d => (
          <div key={d} style={{ textAlign: 'center', fontSize: 10, color: 'var(--text-muted)', fontWeight: 600 }}>{d}</div>
        ))}
      </div>
      {hours.map(h => (
        <div key={h} style={{ display: 'grid', gridTemplateColumns: `40px repeat(7, 1fr)`, gap: 3, marginBottom: 3 }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'right', paddingRight: 8, lineHeight: '20px' }}>
            {h.toString().padStart(2, '0')}h
          </div>
          {Array.from({ length: 7 }, (_, dow) => {
            const cell = data.find(d => d.hour === h && d.dow === dow)
            const val  = cell?.value ?? 0
            return (
              <div
                key={dow}
                className="heatmap-cell"
                style={{ height: 20, background: getColor(val) }}
                title={`${DOW_LABELS[dow]} ${h}:00 — ${val.toFixed(0)}W`}
              />
            )
          })}
        </div>
      ))}

      {/* Legend */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 12, justifyContent: 'flex-end' }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>Low</span>
        {['#1a2744','#0f4c7a','#0369a1','#0ea5e9','#00d4ff'].map(c => (
          <div key={c} style={{ width: 24, height: 10, background: c, borderRadius: 3 }} />
        ))}
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>High</span>
      </div>
    </div>
  )
}

// ── Daily bar chart ──────────────────────────────────────────────────────────
function DailyUsageChart({ readings }) {
  const daily = {}
  readings.forEach(r => {
    const day = format(parseISO(r.timestamp), 'dd MMM')
    if (!daily[day]) daily[day] = { day, kwh: 0, cost: 0, minKwh: r.energy_kwh }
    daily[day].kwh  = r.energy_kwh - daily[day].minKwh
    daily[day].cost = daily[day].kwh * 6.5
  })
  const data = Object.values(daily).slice(-7).map(d => ({
    day:  d.day,
    kWh:  parseFloat(d.kwh.toFixed(3)),
    cost: parseFloat(d.cost.toFixed(2)),
  }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="day" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
        <YAxis yAxisId="left"  tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
        <Tooltip content={<Tip />} />
        <Legend wrapperStyle={{ fontSize: 12, color: 'var(--text-secondary)' }} />
        <Bar yAxisId="left"  dataKey="kWh"  name="Energy (kWh)" fill="#00d4ff" radius={[4,4,0,0]} opacity={0.85} />
        <Bar yAxisId="right" dataKey="cost" name="Cost (₹)"     fill="#7c3aed" radius={[4,4,0,0]} opacity={0.85} />
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Anomaly table ─────────────────────────────────────────────────────────────
function AnomalyTable({ anomalies }) {
  const sev = { HIGH: 'danger', MEDIUM: 'warning', LOW: 'info' }
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
      <thead>
        <tr style={{ borderBottom: '1px solid var(--border)' }}>
          {['Type','Severity','Description','Time','Status'].map(h => (
            <th key={h} style={{ padding: '8px 10px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase' }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {anomalies.length === 0 && (
          <tr><td colSpan={5} style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>✅ No anomalies detected</td></tr>
        )}
        {anomalies.map(a => (
          <tr key={a.id} style={{ borderBottom: '1px solid var(--border)' }}>
            <td style={{ padding: '10px 10px' }}>
              <span className={`badge badge-${sev[a.severity] ?? 'info'}`}>{a.type}</span>
            </td>
            <td style={{ padding: '10px 10px' }}>
              <span className={`badge badge-${sev[a.severity] ?? 'info'}`}>{a.severity}</span>
            </td>
            <td style={{ padding: '10px 10px', color: 'var(--text-secondary)', maxWidth: 280 }}>{a.description}</td>
            <td style={{ padding: '10px 10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              {a.detected_at ? format(parseISO(a.detected_at), 'dd MMM HH:mm') : '—'}
            </td>
            <td style={{ padding: '10px 10px' }}>
              <span className={`badge ${a.resolved ? 'badge-success' : 'badge-warning'}`}>
                {a.resolved ? 'Resolved' : 'Active'}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function Analytics() {
  const [readings,  setReadings]  = useState([])
  const [heatmap,   setHeatmap]   = useState([])
  const [anomalies, setAnomalies] = useState([])
  const [recharges, setRecharges] = useState([])
  const [loading,   setLoading]   = useState(true)

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/readings?device_id=${DEVICE}&limit=2016`),
      axios.get(`${API}/heatmap?device_id=${DEVICE}`),
      axios.get(`${API}/anomalies?device_id=${DEVICE}&limit=30`),
      axios.get(`${API}/recharges?device_id=${DEVICE}&limit=20`),
    ]).then(([r, h, a, re]) => {
      setReadings(r.data)
      setHeatmap(h.data.data)
      setAnomalies(a.data)
      setRecharges(re.data)
    }).finally(() => setLoading(false))
  }, [])

  // Power over time (last 500 readings)
  const powerChart = readings.slice(-200).map(r => ({
    time:   format(parseISO(r.timestamp), 'dd/MM HH:mm'),
    power:  parseFloat(r.power?.toFixed(1) ?? 0),
    energy: parseFloat(r.energy_kwh?.toFixed(3) ?? 0),
  }))

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', gap: 12 }}>
        <div className="loading-spinner" />
        <span style={{ color: 'var(--text-muted)' }}>Loading analytics…</span>
      </div>
    )
  }

  const totalKwh  = readings.length > 1 ? (readings.at(-1).energy_kwh - readings[0].energy_kwh) : 0
  const totalCost = (totalKwh * 6.5).toFixed(2)
  const avgPower  = readings.length ? (readings.reduce((s,r) => s + r.power, 0) / readings.length).toFixed(1) : 0

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Analytics</h1>
          <p className="page-subtitle">Historical energy data · Anomalies · Usage patterns</p>
        </div>
      </div>

      {/* ── Summary KPIs ── */}
      <div className="kpi-grid" style={{ marginBottom: 20 }}>
        {[
          { label: 'Total Energy (7d)', value: totalKwh.toFixed(3), unit: 'kWh', color: 'var(--accent)' },
          { label: 'Total Cost (7d)',   value: `₹${totalCost}`,      unit: '',    color: 'var(--warning)' },
          { label: 'Avg Power',         value: avgPower,             unit: 'W',   color: '#7c3aed' },
          { label: 'Anomalies',         value: anomalies.filter(a => !a.resolved).length, unit: 'active', color: 'var(--danger)' },
          { label: 'Recharges',         value: recharges.length,     unit: 'txns', color: 'var(--success)' },
        ].map((k, i) => (
          <div key={i} className="kpi-card animate-in">
            <div className="kpi-label">{k.label}</div>
            <div className="kpi-value" style={{ color: k.color }}>{k.value}
              <span style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 4 }}>{k.unit}</span>
            </div>
          </div>
        ))}
      </div>

      {/* ── Power history chart ── */}
      <div className="card animate-in" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title">📈 Power Consumption History</span>
        </div>
        <div className="chart-container-lg">
          <ResponsiveContainer>
            <AreaChart data={powerChart} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="pGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} interval={15} />
              <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
              <Tooltip content={<Tip />} />
              <Area type="monotone" dataKey="power" name="Power (W)"
                stroke="var(--accent)" strokeWidth={1.5} fill="url(#pGrad)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Daily chart + heatmap ── */}
      <div className="dashboard-grid" style={{ marginBottom: 20 }}>
        <div className="card animate-in">
          <div className="card-header">
            <span className="card-title">📅 Daily Usage (Last 7 Days)</span>
          </div>
          <DailyUsageChart readings={readings} />
        </div>

        <div className="card animate-in">
          <div className="card-header">
            <span className="card-title">🌡️ Usage Heatmap (Hour × Day)</span>
          </div>
          {heatmap.length > 0
            ? <Heatmap data={heatmap} />
            : <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Need 7 days of data</p>
          }
        </div>
      </div>

      {/* ── Anomaly table ── */}
      <div className="card animate-in" style={{ marginBottom: 20, overflowX: 'auto' }}>
        <div className="card-header">
          <span className="card-title">🚨 Anomaly Log</span>
          <span className="badge badge-danger">{anomalies.filter(a => !a.resolved).length} Active</span>
        </div>
        <AnomalyTable anomalies={anomalies} />
      </div>

      {/* ── Recharge history ── */}
      <div className="card animate-in">
        <div className="card-header">
          <span className="card-title">💳 Recharge History</span>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['#','Amount','Method','Date'].map(h => (
                <th key={h} style={{ padding: '8px 10px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {recharges.length === 0 && (
              <tr><td colSpan={4} style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>No recharge history</td></tr>
            )}
            {recharges.map((r, i) => (
              <tr key={r.id} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '10px 10px', color: 'var(--text-muted)' }}>{i+1}</td>
                <td style={{ padding: '10px 10px', color: 'var(--success)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>+₹{r.amount}</td>
                <td style={{ padding: '10px 10px' }}><span className="badge badge-info">{r.method}</span></td>
                <td style={{ padding: '10px 10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                  {r.timestamp ? format(parseISO(r.timestamp), 'dd MMM yyyy HH:mm') : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
