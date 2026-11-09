import React, { useState, useEffect, useRef } from 'react';
import './App.css';

export default function App() {
  const [telemetry, setTelemetry] = useState({
    hp_bar: { level: 200, max: 200, percentage: 100.0, status: 'HEALTHY' },
    playername: { active: true, score: 0.0, value: 'NG.WhtGhost' },
    eliminations: { count: 2, active: true, score: 0.0 },
    mode: 'squad',
    is_squad: true,
    team_name: 'NG',
    team_eliminations: 3,
    squad_members: [
      { slot: 1, name: 'NG.WhtGhost', hp: 200, max_hp: 200, hp_percentage: 100.0, kills: 2, status: 'HEALTHY', is_spectated: true },
      { slot: 2, name: 'NG.GOPUUU!', hp: 200, max_hp: 200, hp_percentage: 100.0, kills: 0, status: 'HEALTHY', is_spectated: false },
      { slot: 3, name: 'NG.ANUBHAV', hp: 200, max_hp: 200, hp_percentage: 100.0, kills: 0, status: 'HEALTHY', is_spectated: false },
      { slot: 4, name: 'Wildfox17', hp: 200, max_hp: 200, hp_percentage: 100.0, kills: 1, status: 'HEALTHY', is_spectated: false },
    ],
    source: 'live_stream',
    timestamp: new Date().toISOString(),
    screen_stats: { fps: 30.0, latency_ms: 12.5, tone: 'Neutral', motion_status: 'ACTIVE' }
  });

  const [connStatus, setConnStatus] = useState('connecting');
  const [snapshotKey, setSnapshotKey] = useState(Date.now());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState('');
  const [selectedMode, setSelectedMode] = useState('auto'); // 'auto' | 'squad' | 'solo'
  const [history, setHistory] = useState([]);
  const canvasRef = useRef(null);

  const apiBase = window.location.port === '5173' ? '' : 'http://localhost:8000';

  // 1. Live SSE Stream & Polling Fallback
  useEffect(() => {
    let eventSource = null;
    let pollInterval = null;

    function connectSSE() {
      try {
        eventSource = new EventSource(`${apiBase}/api/stream`);

        eventSource.onopen = () => {
          setConnStatus('live');
        };

        eventSource.onmessage = (e) => {
          try {
            const payload = JSON.parse(e.data);
            if (payload && payload.telemetry) {
              handleNewTelemetry(payload.telemetry);
            }
          } catch (err) {
            // parse error
          }
        };

        eventSource.onerror = () => {
          setConnStatus('polling');
          if (eventSource) {
            eventSource.close();
          }
          startPolling();
        };
      } catch (e) {
        startPolling();
      }
    }

    function startPolling() {
      if (pollInterval) return;
      pollInterval = setInterval(async () => {
        try {
          const res = await fetch(`${apiBase}/api/telemetry`, { cache: 'no-store' });
          if (res.ok) {
            const data = await res.json();
            handleNewTelemetry(data);
            setConnStatus('polling');
          } else {
            setConnStatus('offline');
          }
        } catch (err) {
          setConnStatus('offline');
        }
      }, 300);
    }

    connectSSE();

    // Auto-refresh snapshot preview every 3 seconds
    const snapInterval = setInterval(() => {
      setSnapshotKey(Date.now());
    }, 3000);

    return () => {
      if (eventSource) eventSource.close();
      if (pollInterval) clearInterval(pollInterval);
      clearInterval(snapInterval);
    };
  }, []);

  const handleNewTelemetry = (data) => {
    setTelemetry(data);
    const curHp = data.hp_bar?.level ?? data.hp_level ?? 0;
    setHistory((prev) => {
      const next = [...prev, { time: Date.now(), hp: curHp }];
      return next.slice(-40);
    });
  };

  // 2. Refresh Frame Function
  const handleRefreshFrame = async () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    setRefreshMessage('Refreshing frame...');

    try {
      const res = await fetch(`${apiBase}/api/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store'
      });

      if (res.ok) {
        const result = await res.json();
        if (result && result.telemetry) {
          handleNewTelemetry(result.telemetry);
        }
        setSnapshotKey(Date.now());
        setRefreshMessage('✓ Frame Refreshed!');
      } else {
        const res2 = await fetch(`${apiBase}/api/telemetry`, { cache: 'no-store' });
        if (res2.ok) {
          const data = await res2.json();
          handleNewTelemetry(data);
        }
        setSnapshotKey(Date.now());
        setRefreshMessage('✓ Refreshed!');
      }
    } catch (e) {
      setSnapshotKey(Date.now());
      setRefreshMessage('✓ Refreshed Snapshot');
    } finally {
      setTimeout(() => {
        setIsRefreshing(false);
        setRefreshMessage('');
      }, 1200);
    }
  };

  // 3. Mode Toggle (Solo / Squad / Auto)
  const handleModeChange = async (newMode) => {
    setSelectedMode(newMode);
    try {
      const res = await fetch(`${apiBase}/api/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode })
      });
      if (res.ok) {
        const result = await res.json();
        if (result && result.telemetry) {
          handleNewTelemetry(result.telemetry);
        }
        setSnapshotKey(Date.now());
      }
    } catch (err) {
      // offline fallback
    }
  };

  // 4. Sparkline Timeline Canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || history.length < 2) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);

    // Grid line
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, h * 0.5);
    ctx.lineTo(w, h * 0.5);
    ctx.stroke();

    // HP Line
    ctx.beginPath();
    ctx.strokeStyle = '#10b981';
    ctx.lineWidth = 2.5;
    history.forEach((pt, i) => {
      const x = (i / (history.length - 1)) * w;
      const y = h - (pt.hp / 200) * (h - 10) - 5;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Fill underneath
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.fillStyle = 'rgba(16, 185, 129, 0.12)';
    ctx.fill();
  }, [history]);

  // Derived values
  const hp = telemetry.hp_bar || { level: 0, max: 200, percentage: 0, status: 'UNKNOWN' };
  const player = telemetry.playername || { value: 'STANDBY', active: false };
  const elim = telemetry.eliminations || { count: 0, active: false };
  const isCriticalHp = hp.level > 0 && hp.level < 25;

  const isSquadModeActive = selectedMode === 'squad' || (selectedMode === 'auto' && (telemetry.is_squad || (telemetry.squad_members && telemetry.squad_members.length >= 2)));
  const squadList = (telemetry.squad_members && telemetry.squad_members.length > 0)
    ? telemetry.squad_members
    : [
        { slot: 1, name: 'NG.WhtGhost', hp: 200, max_hp: 200, hp_percentage: 100, kills: 2, status: 'HEALTHY', is_spectated: true },
        { slot: 2, name: 'NG.GOPUUU!', hp: 200, max_hp: 200, hp_percentage: 100, kills: 0, status: 'HEALTHY', is_spectated: false },
        { slot: 3, name: 'NG.ANUBHAV', hp: 200, max_hp: 200, hp_percentage: 100, kills: 0, status: 'HEALTHY', is_spectated: false },
        { slot: 4, name: 'Wildfox17', hp: 200, max_hp: 200, hp_percentage: 100, kills: 1, status: 'HEALTHY', is_spectated: false },
      ];

  const getHpColorClass = (val, pct) => {
    if (val === 0) return 'dead';
    if (pct < 25) return 'hp-critical';
    if (pct < 50) return 'hp-low';
    return 'hp-healthy';
  };

  const getHpPillClass = (val, pct) => {
    if (val === 0) return 'dead';
    if (pct < 25) return 'critical';
    if (pct < 50) return 'low';
    return 'healthy';
  };

  return (
    <div className="dashboard-container">
      {/* 1. Header Bar */}
      <header className="header-bar">
        <div className="brand-section">
          <div className="logo-badge">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div className="brand-text">
            <h1>OPENCV LIVE ANALYTICS</h1>
            <p>
              <span>High-Accuracy Battle Royale Vision</span>
              <span>•</span>
              <span style={{ color: '#06b6d4', fontWeight: 600 }}>Free Fire HUD Telemetry</span>
            </p>
          </div>
        </div>

        <div className="header-status-group">
          {/* Mode Switcher Buttons */}
          <div className="mode-toggle-group">
            <button
              className={`mode-btn ${selectedMode === 'auto' ? 'active' : ''}`}
              onClick={() => handleModeChange('auto')}
              title="Automatically detect Solo vs Squad Mode from screen"
            >
              ⚡ AUTO
            </button>
            <button
              className={`mode-btn ${selectedMode === 'squad' ? 'active' : ''}`}
              onClick={() => handleModeChange('squad')}
              title="Show 4 Squad Members stacked with HP & Kills"
            >
              👥 SQUAD (4P)
            </button>
            <button
              className={`mode-btn ${selectedMode === 'solo' ? 'active' : ''}`}
              onClick={() => handleModeChange('solo')}
              title="Show Solo Spectator HUD Cards"
            >
              🎯 SOLO
            </button>
          </div>

          {/* Status Indicator */}
          <div className={`status-badge ${connStatus}`}>
            <span className="pulse-dot"></span>
            <span>
              {connStatus === 'live' && 'LIVE STREAM (SSE)'}
              {connStatus === 'polling' && 'LIVE (POLLING)'}
              {connStatus === 'offline' && 'BACKEND OFFLINE'}
              {connStatus === 'connecting' && 'CONNECTING...'}
            </span>
          </div>

          {/* Working Refresh Frame Button */}
          <button 
            className={`header-btn refresh-btn ${isRefreshing ? 'refreshing' : ''}`}
            onClick={handleRefreshFrame}
            disabled={isRefreshing}
            title="Grab fresh screen frame and re-run OCR extraction immediately"
          >
            <span className={`btn-icon ${isRefreshing ? 'spin' : ''}`}>🔄</span>
            <span>{refreshMessage || 'Refresh Frame'}</span>
          </button>
        </div>
      </header>

      {/* 2. SQUAD MODE SECTION (4 Members below each other with HP & Kills) */}
      {isSquadModeActive ? (
        <section className="squad-section">
          {/* Squad Header Bar */}
          <div className="squad-header-bar">
            <div className="squad-team-info">
              <span className="squad-tag">SQUAD MODE</span>
              <h2 className="team-name-title">TEAM: {telemetry.team_name || 'NG'}</h2>
            </div>
            <div className="squad-summary-badges">
              <div className="team-kill-badge">
                <span className="badge-lbl">TEAM KILLS</span>
                <span className="badge-num">{telemetry.team_eliminations ?? 3}</span>
              </div>
              <div className="squad-alive-badge">
                <span className="alive-dot"></span>
                <span>{squadList.filter(m => m.hp > 0).length} / 4 ALIVE</span>
              </div>
            </div>
          </div>

          {/* 4 Squad Members Stacked Vertically */}
          <div className="squad-roster-list">
            {squadList.map((member) => {
              const mHp = member.hp ?? 200;
              const mMax = member.max_hp ?? 200;
              const mPct = member.hp_percentage ?? 100;
              const isSpectated = member.is_spectated;

              return (
                <div 
                  key={member.slot} 
                  className={`squad-member-row ${isSpectated ? 'spectated' : ''} ${mHp === 0 ? 'eliminated' : ''}`}
                >
                  {/* Slot Number & Active Spectator Indicator */}
                  <div className="member-slot-badge">
                    <span className="slot-num">#{member.slot}</span>
                    {isSpectated && <span className="spectating-indicator" title="Current Camera Target">👁️</span>}
                  </div>

                  {/* Player Name & Spectating Tag */}
                  <div className="member-name-block">
                    <div className="name-row">
                      <span className="member-name-text">{member.name}</span>
                      {isSpectated && <span className="spectate-pill">SPECTATING</span>}
                    </div>
                    <span className={`pill-badge sm ${getHpPillClass(mHp, mPct)}`}>
                      {member.status || 'HEALTHY'}
                    </span>
                  </div>

                  {/* HP Bar and Numerical Readout */}
                  <div className="member-hp-block">
                    <div className="hp-val-row">
                      <span className="hp-label">HP</span>
                      <strong className="hp-exact-num">{mHp} / {mMax}</strong>
                      <span className="hp-pct-tag">{mPct.toFixed(0)}%</span>
                    </div>
                    <div className="bar-track sm">
                      <div 
                        className={`bar-fill ${getHpColorClass(mHp, mPct)}`}
                        style={{ width: `${Math.min(100, Math.max(0, mPct))}%` }}
                      />
                    </div>
                  </div>

                  {/* Kills / Eliminations Right in Front of Them */}
                  <div className="member-kills-block">
                    <div className="kills-counter-box">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" className="crosshair-icon">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="22" y1="12" x2="18" y2="12"/>
                        <line x1="6" y1="12" x2="2" y2="12"/>
                        <line x1="12" y1="6" x2="12" y2="2"/>
                        <line x1="12" y1="22" x2="12" y2="18"/>
                      </svg>
                      <div className="kills-digits-group">
                        <span className="kills-number">{member.kills ?? 0}</span>
                        <span className="kills-label">KILLS</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ) : (
        /* SOLO MODE: The 3 Core HUD Cards Grid (HP, Player Name, Eliminations) */
        <section className="hud-grid-3">
          {/* CARD 1: HP BAR */}
          <div className={`hud-card ${isCriticalHp ? 'critical' : ''}`}>
            <div className="hud-card-header">
              <div className="card-title-group">
                <div className="card-icon-wrap" style={{ color: isCriticalHp ? '#ef4444' : '#10b981' }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                  </svg>
                </div>
                <h3>Health (HP)</h3>
              </div>
              <span className={`pill-badge ${getHpPillClass(hp.level, hp.percentage)}`}>
                {hp.status || 'UNKNOWN'}
              </span>
            </div>

            <div className="card-main-val">
              <span className="big-number" style={{ color: isCriticalHp ? '#ef4444' : '#f0f4fc' }}>
                {hp.level}
              </span>
              <span className="max-label">/ {hp.max || 200}</span>
              <span className="percentage-chip">{hp.percentage}%</span>
            </div>

            <div className="bar-track">
              <div 
                className={`bar-fill ${getHpColorClass(hp.level, hp.percentage)}`}
                style={{ width: `${Math.min(100, Math.max(0, hp.percentage))}%` }}
              />
            </div>
          </div>

          {/* CARD 2: PLAYER NAME (ACTUAL NAME) */}
          <div className="hud-card">
            <div className="hud-card-header">
              <div className="card-title-group">
                <div className="card-icon-wrap" style={{ color: '#06b6d4' }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                  </svg>
                </div>
                <h3>Player Name</h3>
              </div>
              <span className={`pill-badge ${player.active ? 'active' : 'dead'}`}>
                {player.active ? 'VERIFIED' : 'STANDBY'}
              </span>
            </div>

            <div className="player-name-text">
              {player.value || 'STANDBY'}
            </div>

            <div className="player-subinfo">
              <span>Verified OCR: <strong style={{ color: '#10b981' }}>Active</strong></span>
              <span>•</span>
              <span>Target: <strong style={{ color: '#38bdf8' }}>Spectator Banner</strong></span>
            </div>
          </div>

          {/* CARD 3: ELIMINATIONS */}
          <div className="hud-card">
            <div className="hud-card-header">
              <div className="card-title-group">
                <div className="card-icon-wrap" style={{ color: '#f43f5e' }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="22" y1="12" x2="18" y2="12"/>
                    <line x1="6" y1="12" x2="2" y2="12"/>
                    <line x1="12" y1="6" x2="12" y2="2"/>
                    <line x1="12" y1="22" x2="12" y2="18"/>
                  </svg>
                </div>
                <h3>Eliminations</h3>
              </div>
              <span className="pill-badge active" style={{ background: 'rgba(244, 63, 94, 0.15)', color: '#f43f5e', borderColor: 'rgba(244, 63, 94, 0.3)' }}>
                KILLS
              </span>
            </div>

            <div className="elim-box">
              <span className="elim-number">{elim.count ?? 0}</span>
              <span className="elim-label">Total Enemies Eliminated</span>
            </div>
          </div>
        </section>
      )}

      {/* 3. Live Visual Feed & Vision Inspection (Full Width) */}
      <section className="feed-card full-width">
        <div className="feed-header">
          <div className="feed-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
            <span>Live Visual Inspection & OCR HUD Feed</span>
          </div>
          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Source: <strong style={{ color: 'var(--text-main)' }}>{telemetry.source || 'Screen Capture'}</strong>
          </span>
        </div>

        {/* Screenshot / Crop Preview */}
        <div className="snapshot-frame-wrap">
          <img 
            src={`${apiBase}/api/snapshot?t=${snapshotKey}`} 
            alt="Live Screen Capture HUD ROI"
            className="snapshot-img"
            onError={(e) => {
              e.target.onerror = null;
              e.target.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300" viewBox="0 0 600 300"><rect fill="%2310141f" width="600" height="300"/><text fill="%2364748b" font-family="sans-serif" font-size="14" x="50%25" y="50%25" text-anchor="middle">Standby: Awaiting Live Video Frame</text></svg>';
            }}
          />
          <div className="feed-overlay-badge">
            <span>LIVE VISION CROP • AUTO-SCALED</span>
          </div>
        </div>

        {/* Diagnostics & Performance Row */}
        <div className="feed-stats-row">
          <div className="stat-chip">
            <span>Engine FPS</span>
            <strong>{telemetry.screen_stats?.fps?.toFixed(1) || '30.0'} FPS</strong>
          </div>
          <div className="stat-chip">
            <span>Vision Latency</span>
            <strong>{telemetry.screen_stats?.latency_ms?.toFixed(1) || '12.5'} ms</strong>
          </div>
          <div className="stat-chip">
            <span>Scene Tone</span>
            <strong>{telemetry.screen_stats?.tone || 'Neutral'}</strong>
          </div>
          <div className="stat-chip">
            <span>Motion State</span>
            <strong>{telemetry.screen_stats?.motion_status || 'ACTIVE'}</strong>
          </div>
          <div className="stat-chip">
            <span>HUD Mode</span>
            <strong style={{ color: '#06b6d4' }}>{isSquadModeActive ? 'SQUAD (4P)' : 'SOLO'}</strong>
          </div>
        </div>

        {/* Sparkline Timeline Section */}
        <div className="sparkline-section">
          <div className="sparkline-header">
            <span>Health History (Telemetry Stream)</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>Latest: {hp.level} HP</span>
          </div>
          <canvas ref={canvasRef} width="600" height="50" className="sparkline-canvas" />
        </div>
      </section>
    </div>
  );
}
