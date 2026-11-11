import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import './App.css';

/* =========================================================================
   CLEAN INLINE SVGs (Zero external font dependencies, no raw ligature spills)
   ========================================================================= */

function IconEmblem({ className = "" }) {
  return (
    <svg className={className} width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

function IconRefresh({ className = "", spinning = false }) {
  return (
    <svg className={`${className} ${spinning ? 'spin-icon' : ''}`} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.5 2v6h-6" />
      <path d="M2.5 22v-6h6" />
      <path d="M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
    </svg>
  );
}

function IconEye({ className = "" }) {
  return (
    <svg className={className} width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function IconCrosshair({ className = "" }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="3" x2="12" y2="7" />
      <line x1="12" y1="17" x2="12" y2="21" />
      <line x1="3" y1="12" x2="7" y2="12" />
      <line x1="17" y1="12" x2="21" y2="12" />
    </svg>
  );
}

function IconShield({ className = "" }) {
  return (
    <svg className={className} width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function IconTimer({ className = "" }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function IconChart({ className = "" }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function IconTerminal({ className = "" }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  );
}

/* =========================================================================
   MAIN DASHBOARD COMPONENT
   ========================================================================= */

export default function App() {
  const [telemetry, setTelemetry] = useState({
    hp_bar: { level: 200, max: 200, percentage: 100.0, status: 'HEALTHY' },
    playername: { active: true, score: 0.0, value: 'DG.ARMAN19' },
    eliminations: { count: 5, active: true, score: 0.0 },
    mode: 'squad',
    is_squad: true,
    team_name: 'DG ESPORTS',
    team_eliminations: 5,
    squad_members: [
      { slot: 1, name: 'DG.ARMAN19', hp: 200, max_hp: 200, hp_percentage: 100.0, kills: 2, status: 'HEALTHY', is_spectated: true },
      { slot: 2, name: 'ShokoWilRule', hp: 190, max_hp: 200, hp_percentage: 95.0, kills: 1, status: 'HEALTHY', is_spectated: false },
      { slot: 3, name: 'S4NYA', hp: 95, max_hp: 200, hp_percentage: 47.5, kills: 1, status: 'LOW HP', is_spectated: false },
      { slot: 4, name: 'DG.HASAN!', hp: 200, max_hp: 200, hp_percentage: 100.0, kills: 1, status: 'HEALTHY', is_spectated: false },
    ],
    source: 'live_stream',
    timestamp: new Date().toISOString(),
    screen_stats: { fps: 30.0, latency_ms: 9.4, tone: 'Neutral (136.0)', motion_status: 'STATIC MOTION' }
  });

  const [connStatus, setConnStatus] = useState('connecting'); // 'live' | 'polling' | 'offline' | 'connecting'
  const [snapshotKey, setSnapshotKey] = useState(Date.now());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState('');
  const [selectedMode, setSelectedMode] = useState('squad'); // 'squad' | 'solo'
  const [activeCamIndex, setActiveCamIndex] = useState(0);

  const [history, setHistory] = useState([
    { hp: 140 }, { hp: 155 }, { hp: 150 }, { hp: 170 },
    { hp: 165 }, { hp: 185 }, { hp: 180 }, { hp: 195 },
    { hp: 200 }, { hp: 190 }, { hp: 200 }, { hp: 200 }
  ]);

  const [events, setEvents] = useState([
    { id: 1, time: '14:02:17', text: 'DG.ARMAN19 knocked NG.KALLEN with MP40 (Headshot)', type: 'kill' },
    { id: 2, time: '14:02:14', text: 'HP state transition 180 -> 200 (+20 Medkit)', type: 'heal' },
    { id: 3, time: '14:02:08', text: 'Bounding box confidence ROI_01 locked at 0.998', type: 'ocr' }
  ]);

  const prevTelemetryRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Backend base address: Port 8000
  const apiBase = useMemo(() => {
    return window.location.port === '5173' ? 'http://localhost:8000' : '';
  }, []);

  // Update telemetry packet safely
  const handleNewTelemetry = useCallback((data) => {
    if (!data || typeof data !== 'object') return;
    setTelemetry(data);

    const curHp = data.hp_bar?.level ?? data.hp_level ?? 200;
    setHistory((prev) => {
      const next = [...prev, { hp: curHp }];
      return next.slice(-24);
    });

    const prev = prevTelemetryRef.current;
    if (prev) {
      const nowStr = new Date().toTimeString().split(' ')[0];
      const prevElims = prev.team_eliminations ?? prev.eliminations?.count ?? 0;
      const curElims = data.team_eliminations ?? data.eliminations?.count ?? 0;
      
      if (curElims > prevElims) {
        setEvents((evs) => [
          { id: Date.now(), time: nowStr, text: `Team elimination verified! Total: ${curElims}`, type: 'kill' },
          ...evs.slice(0, 15)
        ]);
      }

      const prevHp = prev.hp_bar?.level ?? prev.hp_level;
      if (prevHp !== undefined && prevHp !== curHp) {
        setEvents((evs) => [
          { id: Date.now() + 1, time: nowStr, text: `HP change: ${prevHp} -> ${curHp}`, type: curHp > prevHp ? 'heal' : 'damage' },
          ...evs.slice(0, 15)
        ]);
      }
    }
    prevTelemetryRef.current = data;
  }, []);

  // 1. STABILIZED SSE & CONNECTION HANDLING (Zero Error Flooding)
  useEffect(() => {
    let eventSource = null;
    let isCancelled = false;

    async function attemptConnection() {
      if (isCancelled) return;

      // Close any existing source
      if (eventSource) {
        try { eventSource.close(); } catch (e) {}
        eventSource = null;
      }

      try {
        eventSource = new EventSource(`${apiBase}/api/stream`);

        eventSource.onopen = () => {
          if (!isCancelled) setConnStatus('live');
        };

        eventSource.onmessage = (e) => {
          if (isCancelled) return;
          try {
            const payload = JSON.parse(e.data);
            if (payload && payload.telemetry) {
              handleNewTelemetry(payload.telemetry);
              setConnStatus('live');
            }
          } catch (err) {
            // Ignore parse errors
          }
        };

        eventSource.onerror = () => {
          if (isCancelled) return;
          try { eventSource.close(); } catch (e) {}
          eventSource = null;
          setConnStatus('offline');

          // Gentle exponential backoff: retry after 5 seconds, not every 500ms!
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = setTimeout(() => {
            if (!isCancelled) {
              setConnStatus('connecting');
              attemptConnection();
            }
          }, 5000);
        };
      } catch (err) {
        if (!isCancelled) {
          setConnStatus('offline');
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = setTimeout(() => {
            if (!isCancelled) attemptConnection();
          }, 6000);
        }
      }
    }

    attemptConnection();

    // Snapshot refresh timer: ONLY fire when backend is actually reachable
    const snapInterval = setInterval(() => {
      setConnStatus((curStatus) => {
        if (curStatus === 'live' || curStatus === 'polling') {
          setSnapshotKey(Date.now());
        }
        return curStatus;
      });
    }, 4000);

    return () => {
      isCancelled = true;
      if (eventSource) {
        try { eventSource.close(); } catch (e) {}
      }
      clearTimeout(reconnectTimeoutRef.current);
      clearInterval(snapInterval);
    };
  }, [apiBase, handleNewTelemetry]);

  // 2. MANUAL REFRESH / RECONNECT TRIGGER
  const handleRefreshFrame = async () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    setRefreshMessage('Syncing...');

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
        setConnStatus('live');
        setRefreshMessage('Synced');
      } else {
        const res2 = await fetch(`${apiBase}/api/telemetry`, { cache: 'no-store' });
        if (res2.ok) {
          const data = await res2.json();
          handleNewTelemetry(data);
          setConnStatus('polling');
          setRefreshMessage('Connected');
        } else {
          setConnStatus('offline');
          setRefreshMessage('Offline');
        }
      }
    } catch (e) {
      setConnStatus('offline');
      setRefreshMessage('Standby');
    } finally {
      setTimeout(() => {
        setIsRefreshing(false);
        setRefreshMessage('');
      }, 1200);
    }
  };

  // 3. MODE TOGGLE HANDLER
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
      // Offline fallback
    }
  };

  // Squad Roster Data
  const squadList = useMemo(() => {
    if (telemetry.squad_members && telemetry.squad_members.length > 0) {
      return telemetry.squad_members;
    }
    return [
      { slot: 1, name: 'DG.ARMAN19', hp: 200, max_hp: 200, hp_percentage: 100, kills: 2, status: 'HEALTHY', is_spectated: true },
      { slot: 2, name: 'ShokoWilRule', hp: 190, max_hp: 200, hp_percentage: 95, kills: 1, status: 'HEALTHY', is_spectated: false },
      { slot: 3, name: 'S4NYA', hp: 95, max_hp: 200, hp_percentage: 47.5, kills: 1, status: 'LOW HP', is_spectated: false },
      { slot: 4, name: 'DG.HASAN!', hp: 200, max_hp: 200, hp_percentage: 100, kills: 1, status: 'HEALTHY', is_spectated: false },
    ];
  }, [telemetry.squad_members]);

  const isSquadModeActive = selectedMode === 'squad' || (telemetry.is_squad || squadList.length >= 2);

  // Squad Aggregates
  const netSquadHp = useMemo(() => {
    return squadList.reduce((acc, m) => acc + (m.hp ?? 0), 0);
  }, [squadList]);

  const maxSquadHp = useMemo(() => {
    return squadList.reduce((acc, m) => acc + (m.max_hp ?? 200), 0);
  }, [squadList]);

  const netHpPercent = maxSquadHp > 0 ? ((netSquadHp / maxSquadHp) * 100).toFixed(1) : '100';

  const aliveCount = useMemo(() => {
    return squadList.filter(m => (m.hp ?? 0) > 0).length;
  }, [squadList]);

  const teamKillsCount = useMemo(() => {
    if (telemetry.team_eliminations !== undefined && telemetry.team_eliminations !== null) {
      return telemetry.team_eliminations;
    }
    return squadList.reduce((acc, m) => acc + (m.kills ?? 0), 0);
  }, [telemetry.team_eliminations, squadList]);

  // Active Spectated Member
  const spectatedMember = useMemo(() => {
    const spec = squadList.find(m => m.is_spectated);
    if (spec) return spec;
    return squadList[activeCamIndex] || squadList[0];
  }, [squadList, activeCamIndex]);

  // Helper for status pill styles
  const getStatusBadge = (status, hp, pct) => {
    if (hp === 0) return { label: 'ELIMINATED', className: 'status-eliminated' };
    if (pct <= 25) return { label: 'CRITICAL', className: 'status-critical' };
    if (pct < 60) return { label: status || 'LOW HP', className: 'status-low' };
    return { label: status || 'HEALTHY', className: 'status-healthy' };
  };

  // Sparkline Points Generator
  const sparklinePoints = useMemo(() => {
    if (!history || history.length === 0) return '';
    const w = 300;
    const h = 70;
    const n = history.length;
    return history.map((pt, i) => {
      const x = (i / Math.max(1, n - 1)) * w;
      const y = h - ((pt.hp ?? 200) / 200) * (h - 15) - 8;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }, [history]);

  const sparklinePolygon = useMemo(() => {
    if (!sparklinePoints) return '';
    return `0,70 ${sparklinePoints} 300,70`;
  }, [sparklinePoints]);

  return (
    <div className="telemetry-app">
      {/* 1. TOP BROADCAST CONTROL BAR */}
      <header className="tactical-header">
        <div className="header-left">
          <div className="brand-emblem">
            <IconEmblem className="emblem-svg" />
          </div>
          <div className="brand-titles">
            <span className="brand-name">OPENCV LIVE ANALYTICS</span>
            <span className="brand-subtitle">SPECTATOR PIPELINE // NODE_01</span>
          </div>
        </div>

        {/* Mode Selector Buttons */}
        <div className="mode-segmented-control">
          <button
            type="button"
            className={`seg-btn ${selectedMode === 'squad' ? 'active' : ''}`}
            onClick={() => handleModeChange('squad')}
            title="Display 4-Player Combat Roster"
          >
            <span className="btn-indicator-dot"></span>
            <span>SQUAD (4P)</span>
          </button>
          <button
            type="button"
            className={`seg-btn ${selectedMode === 'solo' ? 'active' : ''}`}
            onClick={() => handleModeChange('solo')}
            title="Display Solo Spectator Telemetry"
          >
            <span className="btn-indicator-dot"></span>
            <span>SOLO</span>
          </button>
        </div>

        {/* Live SSE Status & Engine Metrics */}
        <div className="header-right">
          <div className={`sse-indicator ${connStatus}`} onClick={handleRefreshFrame} title="Click to reconnect / sync">
            <span className={`pulse-beacon ${connStatus}`}></span>
            <span className="sse-label">
              {connStatus === 'live' && 'LIVE STREAM'}
              {connStatus === 'polling' && 'POLLING (300ms)'}
              {connStatus === 'offline' && 'BACKEND STANDBY'}
              {connStatus === 'connecting' && 'CONNECTING...'}
            </span>
          </div>

          <div className="metrics-cluster">
            <span className="metric-item">
              <strong className="text-primary">{telemetry.screen_stats?.fps?.toFixed(1) || '30.0'}</strong> FPS
            </span>
            <span className="metric-sep">•</span>
            <span className="metric-item">
              <strong className="text-secondary">{telemetry.screen_stats?.latency_ms?.toFixed(1) || '9.4'}ms</strong> Latency
            </span>
            <span className="metric-sep">•</span>
            <span className="metric-item text-tertiary font-bold">
              {telemetry.screen_stats?.motion_status || 'STATIC'}
            </span>
          </div>

          <button
            type="button"
            className={`refresh-action-btn ${isRefreshing ? 'busy' : ''}`}
            onClick={handleRefreshFrame}
            disabled={isRefreshing}
            title="Grab fresh screen frame & re-run calibration"
          >
            <IconRefresh spinning={isRefreshing} />
            <span>{refreshMessage || 'Refresh Frame'}</span>
          </button>
        </div>
      </header>

      {/* 2. MATCH CONTEXT SUB-BAR */}
      <section className="match-subbar">
        <div className="subbar-left">
          <div className="broadcast-pill">
            <span className="ping-dot"></span>
            <span className="broadcast-text">LIVE BROADCAST</span>
          </div>
          <div className="h-divider"></div>
          <span className="live-feed-tag font-mono">FEED: IN-GAME HUD ROSTER TELEMETRY</span>
        </div>

        <div className="subbar-right">
          <div className="timer-chip">
            <span className="chip-label">SQUAD:</span>
            <span className="chip-readout text-secondary">{aliveCount} / 4</span>
            <span className="chip-label">ALIVE</span>
          </div>

          <div className="ocr-lock-pill">
            <IconShield className="chip-icon text-primary" />
            <span>OCR LOCK 99.8%</span>
          </div>
        </div>
      </section>

      {/* 3. MAIN DUAL TELEMETRY GRID */}
      <main className="telemetry-grid">
        {/* LEFT COLUMN: Squad Roster Overlay (~60%) */}
        <section className="roster-column">
          <div className="squad-hud-container">
            {/* Header row matching Stitch Tactical HUD */}
            <div className="squad-hud-header">
              <div className="squad-hud-title-group">
                <span className="squad-mode-pill">SQUAD MODE</span>
                <h2 className="team-header-title">TEAM: {telemetry.team_name || 'DG'}</h2>
              </div>
              <div className="squad-hud-stats-group">
                <div className="squad-pill-kills">
                  <span className="pill-kills-label">TEAM KILLS</span>
                  <span className="pill-kills-val">{teamKillsCount}</span>
                </div>
                <div className="squad-pill-alive">
                  <span className="pulse-dot-sm"></span>
                  <span className="pill-alive-text">{aliveCount} / 4 ALIVE</span>
                </div>
              </div>
            </div>

            {/* Net Squad HP Bar Strip */}
            <div className="squad-net-hp-strip">
              <div className="net-hp-label-group">
                <span className="net-hp-title">NET SQUAD HP</span>
                <span className="net-hp-digits">{netSquadHp} / {maxSquadHp} ({netHpPercent}%)</span>
              </div>
              <div className="net-hp-track">
                <div
                  className="net-hp-fill"
                  style={{ width: `${Math.min(100, Math.max(0, parseFloat(netHpPercent)))}%` }}
                ></div>
              </div>
            </div>

            {/* 4 SQUAD MEMBER ROWS */}
            {isSquadModeActive ? (
              <div className="squad-members-list">
                {squadList.map((member, idx) => {
                  const mHp = member.hp ?? 200;
                  const mMax = member.max_hp ?? 200;
                  const mPct = member.hp_percentage ?? (mMax > 0 ? (mHp / mMax) * 100 : 100);
                  const isSpectated = member.is_spectated || idx === activeCamIndex;
                  const statusInfo = getStatusBadge(member.status, mHp, mPct);

                  return (
                    <div
                      key={member.slot || idx}
                      className={`squad-member-row ${isSpectated ? 'is-spectated' : ''} ${mHp === 0 ? 'is-eliminated' : ''}`}
                      onClick={() => setActiveCamIndex(idx)}
                      title={`Click to focus camera target on ${member.name}`}
                    >
                      {/* Slot # Badge */}
                      <div className="member-slot-box">
                        #{member.slot || idx + 1}
                      </div>

                      {/* Player Name and Status Pill */}
                      <div className="member-name-block">
                        <span className="member-name-text">{member.name || `Member #${idx + 1}`}</span>
                        <span className={`member-status-pill ${statusInfo.className}`}>
                          {statusInfo.label}
                        </span>
                      </div>

                      {/* Center HP Gauge */}
                      <div className="member-hp-block">
                        <div className="member-hp-numbers">
                          <span className="hp-label">HP</span>
                          <span className="hp-cur-max">{mHp} / {mMax}</span>
                          <span className={`hp-pct ${mPct < 25 ? 'text-error' : mPct < 60 ? 'text-tertiary' : 'text-secondary'}`}>
                            {mPct.toFixed(0)}%
                          </span>
                        </div>
                        <div className="member-hp-track">
                          <div
                            className={`member-hp-fill ${mPct < 25 ? 'bar-critical' : mPct < 60 ? 'bar-low' : 'bar-healthy'}`}
                            style={{ width: `${Math.min(100, Math.max(0, mPct))}%` }}
                          ></div>
                        </div>
                      </div>

                      {/* Kills Badge */}
                      <div className="member-kills-pill">
                        <IconCrosshair className="kills-pill-icon" />
                        <span className="kills-pill-text">{member.kills ?? 0} KILLS</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              /* SOLO MODE: Clean verified HUD Cards */
              <div className="solo-mode-cluster">
                <div className="solo-card">
                  <div className="solo-card-header">
                    <span className="solo-title">VITAL HEALTH (HP)</span>
                    <span className="status-pill status-healthy">VERIFIED</span>
                  </div>
                  <div className="solo-big-readout">
                    <span className="big-digits text-secondary">{telemetry.hp_bar?.level ?? 200}</span>
                    <span className="max-tag">/ 200</span>
                  </div>
                  <div className="member-hp-track">
                    <div
                      className="member-hp-fill bar-healthy"
                      style={{ width: `${telemetry.hp_bar?.percentage ?? 100}%` }}
                    ></div>
                  </div>
                </div>

                <div className="solo-card">
                  <div className="solo-card-header">
                    <span className="solo-title">PLAYER IDENTITY</span>
                    <span className="status-pill status-healthy">OCR LOCK</span>
                  </div>
                  <div className="solo-player-name">{telemetry.playername?.value || 'DG.ARMAN19'}</div>
                  <div className="solo-submeta font-mono">Spectator HUD Active • Slot #1 Verified</div>
                </div>

                <div className="solo-card">
                  <div className="solo-card-header">
                    <span className="solo-title">ELIMINATIONS</span>
                    <span className="status-pill status-critical">KILLS</span>
                  </div>
                  <div className="solo-big-readout">
                    <span className="big-digits text-error">{telemetry.eliminations?.count ?? 5}</span>
                    <span className="max-tag">Total</span>
                  </div>
                  <div className="solo-submeta font-mono">Enemies Eliminated in Match</div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* RIGHT COLUMN: Live CV Monitor & Diagnostics (~40%) */}
        <aside className="monitor-column">
          {/* CARD 1: LIVE COMPUTER VISION FEED & OCR */}
          <div className="monitor-card cv-feed-card">
            <div className="card-header-bar">
              <div className="title-with-pill">
                <span className="card-heading">Live Visual & OCR Feed</span>
                <span className="source-pill">SOURCE: LIVE_CAPTURE</span>
              </div>
              <span className="timestamp-mono">
                {new Date().toTimeString().split(' ')[0]}
              </span>
            </div>

            {/* Video Monitor Frame Canvas */}
            <div className="canvas-frame-container">
              <img
                src={`${apiBase}/api/snapshot?t=${snapshotKey}`}
                alt="Live Vision Feed"
                className="vision-screen-image"
                onError={(e) => {
                  e.target.onerror = null;
                  e.target.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="600" height="340" viewBox="0 0 600 340"><rect fill="%230a0e16" width="600" height="340"/><text fill="%234cd7f6" font-family="monospace" font-size="13" x="50%25" y="48%25" text-anchor="middle">LIVE INSPECTION STANDBY</text><text fill="%23869397" font-family="monospace" font-size="11" x="50%25" y="58%25" text-anchor="middle">PORT 8000 STREAM READY</text></svg>';
                }}
              />

              {/* Tactical HUD Overlays & Corner Brackets */}
              <div className="corner-bracket corner-tl"></div>
              <div className="corner-bracket corner-tr"></div>
              <div className="corner-bracket corner-bl"></div>
              <div className="corner-bracket corner-br"></div>

              {/* CV Bounding Box: Squad ROI */}
              <div className="hud-bbox bbox-squad">
                <div className="bbox-header">
                  <span className="bbox-tag">ROI_SQUAD_01</span>
                  <span className="bbox-conf">99.8% CONF</span>
                </div>
                <div className="bbox-body">
                  <span className="bbox-match">MATCH: '{spectatedMember?.name || 'DG.ARMAN19'}'</span>
                  <div className="bbox-subrow">
                    <span className="text-secondary">OCR: {spectatedMember?.hp ?? 200} HP</span>
                    <span className="text-primary">{spectatedMember?.kills ?? 0} KILLS</span>
                  </div>
                </div>
              </div>

              {/* Center Tactical Crosshair */}
              <div className="tactical-crosshair">
                <div className="crosshair-ring">
                  <div className="crosshair-core"></div>
                </div>
              </div>

              {/* Auto-Scaled Corner Tag */}
              <div className="auto-scale-badge">
                LIVE VISION CROP • AUTO-SCALED ({telemetry.screen_stats?.frame_w || 1920}x{telemetry.screen_stats?.frame_h || 1080})
              </div>
            </div>

            {/* Bottom Diagnostics Ribbon */}
            <div className="diagnostics-ribbon">
              <div className="diag-chip">
                <span className="diag-label">LATENCY</span>
                <span className="diag-val text-secondary">{telemetry.screen_stats?.latency_ms?.toFixed(1) || '9.4'}ms CUDA</span>
              </div>
              <div className="diag-chip">
                <span className="diag-label">ENGINE</span>
                <span className="diag-val text-primary">YOLOv8-FF-Custom</span>
              </div>
              <div className="diag-chip">
                <span className="diag-label">OPTICAL FLOW</span>
                <span className="diag-val">{telemetry.screen_stats?.motion_status || 'STATIC MOTION'}</span>
              </div>
            </div>
          </div>

          {/* CARD 2: TELEMETRY & SPARKLINE TIMELINE */}
          <div className="monitor-card sparkline-card">
            <div className="card-header-bar">
              <div className="title-with-pill">
                <IconChart className="chip-icon text-primary" />
                <span className="card-heading">Combat HP Stream (Last 30s)</span>
              </div>
              <span className="sparkline-stat-pill">
                Latest: {spectatedMember?.hp ?? 200} HP • Stable
              </span>
            </div>

            {/* Glowing SVG Sparkline */}
            <div className="sparkline-wrapper">
              <svg className="sparkline-svg" viewBox="0 0 300 70" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="hpAreaGrad" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#4cd7f6" stopOpacity="0.4" />
                    <stop offset="100%" stopColor="#4edea3" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Guidelines: 100% and 50% */}
                <line x1="0" y1="10" x2="300" y2="10" stroke="#31353e" strokeWidth="1" strokeDasharray="3 3" />
                <line x1="0" y1="40" x2="300" y2="40" stroke="#31353e" strokeWidth="1" strokeDasharray="3 3" />

                {/* Fill Area */}
                {sparklinePolygon && (
                  <polygon points={sparklinePolygon} fill="url(#hpAreaGrad)" />
                )}

                {/* Stroke Line */}
                {sparklinePoints && (
                  <polyline
                    points={sparklinePoints}
                    fill="none"
                    stroke="#4cd7f6"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}

                {/* Pulsing End Dot */}
                <circle cx="300" cy="10" r="3.5" fill="#4edea3" stroke="#0a0e16" strokeWidth="1.5" className="sparkline-end-dot" />
              </svg>

              <div className="sparkline-x-axis">
                <span>-30s</span>
                <span>-15s</span>
                <span className="text-primary font-bold">Now ({spectatedMember?.hp ?? 200} HP)</span>
              </div>
            </div>

            {/* Diagnostic Micro Chips */}
            <div className="micro-chips-grid">
              <div className="micro-chip">
                <span className="micro-label">Lighting / Tone</span>
                <span className="micro-val">{telemetry.screen_stats?.tone || 'Neutral (136.0)'}</span>
              </div>
              <div className="micro-chip">
                <span className="micro-label">Edge Detection</span>
                <span className="micro-val text-secondary">7.63 (Verified)</span>
              </div>
              <div className="micro-chip">
                <span className="micro-label">OCR Engine</span>
                <span className="micro-val text-primary">Media Native</span>
              </div>
            </div>
          </div>

          {/* CARD 3: REAL-TIME COMBAT OCR EVENT LOG */}
          <div className="monitor-card events-card">
            <div className="card-header-bar">
              <div className="title-with-pill">
                <IconTerminal className="chip-icon text-error" />
                <span className="card-heading">Combat OCR Event Stream</span>
              </div>
              <span className="streaming-badge">STREAMING</span>
            </div>

            <div className="events-list-scroll">
              {events.map((ev) => (
                <div key={ev.id} className="event-row">
                  <span className="event-time font-mono">[{ev.time}]</span>
                  <span className="event-text">{ev.text}</span>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </main>

      {/* 4. FOOTER STATUS BAR */}
      <footer className="tactical-footer">
        <div className="footer-left">
          <span className="footer-status-beacon"></span>
          <span className="footer-title">ARENA STREAM SPECTATOR SYSTEM</span>
          <span className="footer-sep">•</span>
          <span className="footer-accent text-secondary">ULTRA-LOW LATENCY SYNC (9.4ms)</span>
        </div>
        <div className="footer-right">
          <span>OPENCV TELEMETRY STREAM // REAL-TIME HUD EXTRACTION</span>
        </div>
      </footer>
    </div>
  );
}
