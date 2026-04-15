import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Zap, Gauge, Wallet, Thermometer, ShieldAlert,
  TrendingUp, TrendingDown, RefreshCw, ToggleRight
} from 'lucide-react'
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'
import axios from 'axios'
import toast from 'react-hot-toast'
import { format, parseISO } from 'date-fns'

const API = '/api'
const DEVICE = 'METER_001'

// ── Custom tooltip ─────────────────────────────────────────────────────────
const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '10px 14px', fontSize: 12,
    }}>
      <p style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color, fontWeight: 600 }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(2) : p.value}
        </p>
      ))}
    </div>
  )
}

// ── KPI Card ───────────────────────────────────────────────────────────────
function KpiCard({ icon: Icon, label, value, unit, sub, color, trend }) {
  return (
    <div className="kpi-card animate-in">
      <div className="kpi-icon" style={{ background: `${color}22` }}>
        <Icon size={20} color={color} />
      </div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ color }}>
        {value}<span style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-secondary)', marginLeft: 4 }}>{unit}</span>
      </div>
      {sub && <div className="kpi-sub">{sub}</div>}
      {trend !== undefined && (
        <span className={`kpi-trend ${trend > 0 ? 'up' : trend < 0 ? 'down' : 'flat'}`}>
          {trend > 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
          {Math.abs(trend)}%
        </span>
      )}
    </div>
  )
}

// ── Alert item ─────────────────────────────────────────────────────────────
function AlertItem({ alert }) {
  const cls = alert.type === 'THEFT' ? 'danger'
            : alert.type === 'LOW_BALANCE' ? 'warning'
            : alert.type === 'RECHARGE'    ? 'success'
            : 'info'
  return (
    <div className={`alert-item ${cls}`}>
      <span style={{ fontSize: 18 }}>
        {cls === 'danger' ? '🚨' : cls === 'warning' ? '⚠️' : cls === 'success' ? '✅' : 'ℹ️'}
      </span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          {alert.type.replace(/_/g, ' ')}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
          {alert.message}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
          {alert.sent_at ? format(parseISO(alert.sent_at), 'dd MMM, HH:mm') : '—'}
        </div>
      </div>
    </div>
  )
}

// ── Device toggle ──────────────────────────────────────────────────────────
function RelayControl({ deviceId }) {
  const [on, setOn] = useState(true)
  const [loading, setLoading] = useState(false)

  const toggle = async () => {
    setLoading(true)
    try {
      await axios.post(`${API}/control/relay`, { device_id: deviceId, state: !on })
      setOn(v => !v)
      toast.success(`Relay turned ${!on ? 'ON' : 'OFF'}`)
    } catch {
      toast.error('Failed to toggle relay')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card animate-in">
      <div className="card-header">
        <span className="card-title">⚡ Device Control</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div className="toggle-wrap">
          <div onClick={toggle} className={`toggle ${on ? 'on' : ''}`} />
          <span style={{ fontSize: 14, color: on ? 'var(--success)' : 'var(--text-muted)' }}>
            {loading ? 'Switching…' : on ? 'Relay ON' : 'Relay OFF'}
          </span>
        </div>

        <button
          className="btn btn-primary"
          style={{ width: '100%', justifyContent: 'center' }}
          onClick={async () => {
            try {
              const { data } = await axios.post(`${API}/recharge`, {
                device_id: deviceId, amount: 200, method: 'dashboard'
              })
              toast.success(data.message)
            } catch { toast.error('Recharge failed') }
          }}
        >
          ₹ Recharge ₹200
        </button>

        <button
          className="btn btn-ghost"
          style={{ width: '100%', justifyContent: 'center' }}
          onClick={async () => {
            try {
              const { data } = await axios.post(`${API}/recharge`, {
                device_id: deviceId, amount: 500, method: 'dashboard'
              })
              toast.success(data.message)
            } catch { toast.error('Recharge failed') }
          }}
        >
          ₹ Recharge ₹500
        </button>
      </div>
    </div>
  )
}

// ── Main Dashboard ─────────────────────────────────────────────────────────
export default function Dashboard() {
  const [readings, setReadings]     = useState([])
  const [predictions, setPreds]     = useState([])
  const [balance, setBalance]       = useState(null)
  const [alerts, setAlerts]         = useState([])
  const [insights, setInsights]     = useState(null)
  const [loading, setLoading]       = useState(true)
  const [lastUpdate, setLastUpdate] = useState(null)
  const timerRef = useRef(null)

  const fetchAll = useCallback(async () => {
    try {
      const [rRes, pRes, bRes, aRes, iRes] = await Promise.all([
        axios.get(`${API}/readings?device_id=${DEVICE}&limit=144`),
        axios.get(`${API}/predictions?device_id=${DEVICE}&horizon=24`),
        axios.get(`${API}/balance?device_id=${DEVICE}`),
        axios.get(`${API}/alerts?device_id=${DEVICE}&limit=8`),
        axios.get(`${API}/insights?device_id=${DEVICE}`),
      ])
      setReadings(rRes.data)
      setPreds(pRes.data.predictions?.slice(0, 288) ?? [])  // next 24h
      setBalance(bRes.data)
      setAlerts(aRes.data)
      setInsights(iRes.data)
      setLastUpdate(new Date())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    timerRef.current = setInterval(fetchAll, 5000)
    return () => clearInterval(timerRef.current)
  }, [fetchAll])

  // ── Derived KPIs ──────────────────────────────────────────────────────────
  const latest   = readings.at(-1) ?? {}
  const prev     = readings.at(-13) ?? {}  // 1 h ago
  const voltage  = (latest.voltage  ?? 0).toFixed(1)
  const current  = (latest.current  ?? 0).toFixed(3)
  const power    = (latest.power    ?? 0).toFixed(1)
  const balVal   = (latest.balance  ?? balance?.balance ?? 0).toFixed(2)
  const energyKwh = (latest.energy_kwh ?? 0).toFixed(3)

  const powerDelta = prev.power
    ? Math.round(((latest.power - prev.power) / prev.power) * 100)
    : 0

  // Chart data: last 50 readings + predictions overlaid
  const chartData = readings.slice(-50).map(r => ({
    time:    format(parseISO(r.timestamp), 'HH:mm'),
    power:   parseFloat(r.power?.toFixed(1) ?? 0),
    voltage: parseFloat(r.voltage?.toFixed(1) ?? 0),
  }))

  const predData = predictions.slice(0, 24).map((p, i) => ({
    time:     `+${p.minutes_ahead}m`,
    predicted: parseFloat(p.predicted_watts?.toFixed(1) ?? 0),
  }))

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '80vh', gap: 12 }}>
        <div className="loading-spinner" />
        <span style={{ color: 'var(--text-muted)' }}>Loading smart meter data…</span>
      </div>
    )
  }

  return (
    <div>
      {/* ── Page header ── */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Energy Dashboard</h1>
          <p className="page-subtitle">
            Real-time monitoring · AI Predictions · {' '}
            {lastUpdate && `Updated ${format(lastUpdate, 'HH:mm:ss')}`}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span className="badge badge-success">
            <span className="live-dot" style={{ width: 6, height: 6 }} /> Live
          </span>
          <button className="btn btn-ghost" onClick={fetchAll}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* ── KPI row ── */}
      <div className="kpi-grid">
        <KpiCard icon={Zap}        label="Voltage"     value={voltage}   unit="V"   color="var(--accent)"   sub="Phase voltage" />
        <KpiCard icon={Gauge}      label="Current"     value={current}   unit="A"   color="#7c3aed"         sub="Line current" />
        <KpiCard icon={TrendingUp} label="Power"       value={power}     unit="W"   color="#f59e0b" trend={powerDelta} sub="Active load" />
        <KpiCard icon={Zap}        label="Energy"      value={energyKwh} unit="kWh" color="#10b981"         sub="Cumulative" />
        <KpiCard icon={Wallet}     label="Balance"     value={`₹${balVal}`} unit="" color={parseFloat(balVal) < 50 ? 'var(--danger)' : 'var(--success)'} sub={balance?.forecast?.expiry_message?.slice(0,40)} />
        {balance?.forecast && (
          <KpiCard icon={Thermometer} label="Est. Remaining" value={balance.forecast.days_remaining} unit="days" color="var(--accent)" sub={`₹${balance.forecast.daily_cost_rs}/day`} />
        )}
      </div>

      {/* ── Main charts row ── */}
      <div className="dashboard-grid" style={{ marginBottom: 20 }}>
        {/* Real-time power + prediction */}
        <div className="card animate-in">
          <div className="card-header">
            <span className="card-title">⚡ Live Power + AI Forecast</span>
            <span className="badge badge-info">LSTM</span>
          </div>
          <div className="chart-container-lg">
            <ResponsiveContainer>
              <AreaChart data={chartData} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="pwrGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} interval="preserveStartEnd" />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="power" name="Power (W)"
                  stroke="var(--accent)" strokeWidth={2} fill="url(#pwrGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Prediction strip */}
          {predData.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
                🔮 AI Forecast — Next 2 Hours
              </div>
              <div className="chart-container" style={{ height: 120 }}>
                <ResponsiveContainer>
                  <LineChart data={predData} margin={{ top: 0, right: 10, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 9 }} interval={3} />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 9 }} />
                    <Tooltip content={<ChartTooltip />} />
                    <Line type="monotone" dataKey="predicted" name="Predicted (W)"
                      stroke="#7c3aed" strokeWidth={2} dot={false} strokeDasharray="4 2" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Alerts */}
          <div className="card animate-in" style={{ flex: 1, overflow: 'hidden' }}>
            <div className="card-header">
              <span className="card-title">🚨 Alerts</span>
              <span className="badge badge-danger">{alerts.filter(a => a.type === 'THEFT' || a.type === 'LOW_BALANCE').length}</span>
            </div>
            <div style={{ maxHeight: 280, overflowY: 'auto' }}>
              {alerts.length === 0
                ? <p style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>✅ No active alerts</p>
                : alerts.map(a => <AlertItem key={a.id} alert={a} />)
              }
            </div>
          </div>

          {/* Device control */}
          <RelayControl deviceId={DEVICE} />
        </div>
      </div>

      {/* ── Voltage chart + AI insights row ── */}
      <div className="dashboard-grid-3">
        {/* Voltage */}
        <div className="card animate-in">
          <div className="card-header">
            <span className="card-title">🔌 Voltage Trend</span>
          </div>
          <div className="chart-container">
            <ResponsiveContainer>
              <LineChart data={chartData.slice(-30)} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} interval={5} />
                <YAxis domain={[180, 260]} tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                <Tooltip content={<ChartTooltip />} />
                <ReferenceLine y={240} stroke="var(--warning)" strokeDasharray="4 2" label={{ value: '240V', fill: 'var(--warning)', fontSize: 10 }} />
                <Line type="monotone" dataKey="voltage" name="Voltage (V)"
                  stroke="#f59e0b" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Balance forecast */}
        <div className="card animate-in">
          <div className="card-header">
            <span className="card-title">💰 Balance Status</span>
          </div>
          {balance?.forecast ? (
            <div>
              <div style={{
                fontSize: 36, fontWeight: 800, fontFamily: 'var(--font-mono)',
                color: parseFloat(balVal) < 50 ? 'var(--danger)' : 'var(--success)',
                marginBottom: 4,
              }}>₹{balVal}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
                {balance.forecast.expiry_message}
              </div>
              <div className="stat-row">
                <span className="stat-label">Daily cost</span>
                <span className="stat-value" style={{ color: 'var(--warning)' }}>₹{balance.forecast.daily_cost_rs}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Avg load</span>
                <span className="stat-value">{balance.forecast.avg_power_w} W</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Recommended recharge</span>
                <span className="stat-value" style={{ color: 'var(--accent)' }}>₹{balance.forecast.recommended_recharge}</span>
              </div>
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>No forecast data</p>
          )}
        </div>

        {/* AI Insights */}
        <div className="card animate-in" style={{ overflow: 'hidden' }}>
          <div className="card-header">
            <span className="card-title">💡 AI Insights</span>
            <span className="badge badge-info">AI</span>
          </div>
          <div style={{ maxHeight: 280, overflowY: 'auto' }}>
            {insights?.recommendations?.slice(0, 4).map((r, i) => (
              <div key={i} className="rec-item">
                <div className="rec-icon" style={{
                  background: r.category === 'alert' ? 'var(--danger-dim)'
                            : r.category === 'green' ? 'var(--success-dim)'
                            : 'var(--accent-dim)'
                }}>
                  {r.category === 'alert' ? '⚠️' : r.category === 'green' ? '🌱' : r.category === 'schedule' ? '🕐' : '💡'}
                </div>
                <div className="rec-body">
                  <div className="rec-message">{r.message}</div>
                  {r.potential_saving !== '—' && (
                    <div className="rec-saving">💚 Save: {r.potential_saving}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
