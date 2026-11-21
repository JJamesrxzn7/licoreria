import React, { useEffect, useState, useCallback } from 'react';
import {
  Server, Database, Terminal, Play, RefreshCw, ShieldCheck, AlertTriangle,
  Layers, Cloud, Cpu, Activity, CheckCircle2, XCircle, HardDrive, Network,
  ArrowRight, Box, Filter
} from 'lucide-react';
import { useGlobalStore } from '../context';

const configuredApiUrl = import.meta.env.VITE_API_URL?.trim();
const isGithubPages = typeof window !== 'undefined' && window.location.hostname.endsWith('github.io');
const API_BASE_URL = (
  configuredApiUrl
    ? (/^https?:\/\//i.test(configuredApiUrl) ? configuredApiUrl : `https://${configuredApiUrl}`)
    : (isGithubPages ? 'http://127.0.0.1:8000' : `http://${window.location.hostname}:8000`)
).replace(/\/$/, '');

interface ModuleInfo {
  code: string;
  name: string;
  table: string;
  rows: number;
}

interface PresetQuery {
  label: string;
  sql: string;
}

interface ClusterNode {
  bdId?: string;
  id: string;
  xSede?: string;
  site: string;
  siteLabel: string;
  machine?: string;
  name: string;
  shortName: string;
  engine: string;
  engineType: 'mariadb' | 'postgresql' | 'mongodb';
  role: string;
  host: string;
  activeHost?: string;
  port: number;
  actualPort: number;
  database: string;
  user: string;
  heidiSqlHint: string;
  status: 'ONLINE' | 'OFFLINE';
  latencyMs: number;
  version: string;
  datadir: string;
  tablesCount: number;
  sizeKb: number;
  activeConnections: number;
  modules: ModuleInfo[];
  presets: PresetQuery[];
  error?: string;
}

interface SiteGroup {
  siteId: string;
  title: string;
  subtitle: string;
  badge: string;
  nodes: ClusterNode[];
}

interface TopologyResponse {
  timestamp: string;
  apiReplica?: string;
  clusterName: string;
  totalNodes: number;
  onlineNodes: number;
  sites: SiteGroup[];
  nodes: ClusterNode[];
  informationSystemArchitecture: {
    presentationLayer: string;
    middlewareLayer: string;
    dataLayer: string;
    containerization: string;
    scalabilityMetrics: {
      usersMin: number;
      usersMax: number;
      txPerSecond: number;
      txPerMinute: number;
      txPerHour: number;
      txPerDay: number;
    };
  };
}

interface GlobalDbaRecord {
  id: string;
  origen_nodo: string;
  sede: string;
  motor: string;
  puerto: number;
  modulo: string;
  usuario_rbac: string;
  rol_rbac: string;
  detalle: string;
  monto_usd: number;
  fecha_hora: string;
}

interface GlobalDbaResponse {
  timestamp: string;
  apiReplica: string;
  totalExecutionTimeMs: number;
  totalRecords: number;
  filtersApplied: { sede: string; modulo: string };
  nodeLatencies: Record<string, { bdId: string; status: string; latencyMs: number; recordsReturned: number }>;
  data: GlobalDbaRecord[];
}

interface QueryResult {
  success: boolean;
  nodeId: string;
  nodeName: string;
  engine: string;
  host: string;
  port: number;
  database: string;
  sql: string;
  executionTimeMs: number;
  columns: string[];
  rows: Array<Array<string | number | null>>;
  rowCount: number;
  executedAt: string;
}

interface NodeLogsResponse {
  nodeId: string;
  nodeName: string;
  port: number;
  engine: string;
  variables: Record<string, string | number | null>;
  activeConnections: Array<Record<string, string | number | null>>;
  auditLogs: Array<{
    id: string | number;
    fecha_hora: string;
    usuario: string;
    evento: string;
    detalle: string;
  }>;
}

interface TwoPcStep {
  phase: string;
  timestamp: string;
  node: string;
  status: string;
  message: string;
}

interface TwoPcResult {
  txId: string;
  decision: 'GLOBAL_COMMIT' | 'GLOBAL_ROLLBACK';
  phaseReached: string;
  simulatePrepareFailure: boolean;
  executionTimeMs: number;
  summary: string;
  steps: TwoPcStep[];
}

export const ArchitectureConsole: React.FC = () => {
  const { activeSite } = useGlobalStore();
  const [activeTab, setActiveTab] = useState<'global_dba' | 'board' | 'dba_prompt' | 'twopc' | 'si_docker'>('global_dba');
  const [topology, setTopology] = useState<TopologyResponse | null>(null);
  const [loadingTopo, setLoadingTopo] = useState(false);

  // Consola Global del DBA (GET /api/dba/global)
  const [globalData, setGlobalData] = useState<GlobalDbaResponse | null>(null);
  const [filterSede, setFilterSede] = useState<string>('TODAS');
  const [filterModulo, setFilterModulo] = useState<string>('TODOS');
  const [loadingGlobal, setLoadingGlobal] = useState<boolean>(false);

  // Prompt SQL DBA state
  const [selectedNodeId, setSelectedNodeId] = useState<string>('guayaquil-sql');
  const [sqlText, setSqlText] = useState<string>(
    "SELECT username, rol_bd, modulo_codigo, modulo_nombre, descripcion_cargo, sede_nodo, estado FROM rbac_matriz_15_usuarios ORDER BY modulo_codigo, rol_bd;"
  );
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [queryError, setQueryError] = useState<string>('');
  const [runningQuery, setRunningQuery] = useState(false);

  // Logs & Monitor state
  const [nodeLogs, setNodeLogs] = useState<NodeLogsResponse | null>(null);

  // 2PC Simulator state
  const [twoPcQty, setTwoPcQty] = useState<number>(15);
  const [simulateFail, setSimulateFail] = useState<boolean>(false);
  const [twoPcResult, setTwoPcResult] = useState<TwoPcResult | null>(null);
  const [runningTwoPc, setRunningTwoPc] = useState<boolean>(false);

  // SI Users slider
  const [simulatedUsers, setSimulatedUsers] = useState<number>(250);

  const fetchTopology = useCallback(async () => {
    setLoadingTopo(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/arquitectura/topologia`);
      if (res.ok) {
        const data: TopologyResponse = await res.json();
        setTopology(data);
      }
    } catch {
      // Ignore transient errors
    } finally {
      setLoadingTopo(false);
    }
  }, []);

  const fetchGlobalDbaConsole = useCallback(async (sedeVal?: string, modVal?: string) => {
    setLoadingGlobal(true);
    const s = sedeVal ?? filterSede;
    const m = modVal ?? filterModulo;
    const params = new URLSearchParams();
    if (s && s !== 'TODAS') params.set('sede', s);
    if (m && m !== 'TODOS') params.set('modulo', m);
    try {
      const res = await fetch(`${API_BASE_URL}/api/dba/global?${params.toString()}`);
      if (res.ok) {
        const data: GlobalDbaResponse = await res.json();
        setGlobalData(data);
      }
    } catch {
      // Ignore
    } finally {
      setLoadingGlobal(false);
    }
  }, [filterSede, filterModulo]);

  const fetchNodeLogs = useCallback(async (nodeId: string) => {
    if (nodeId === 'global-federated') return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/arquitectura/dba/logs/${nodeId}`);
      if (res.ok) {
        const data: NodeLogsResponse = await res.json();
        setNodeLogs(data);
      }
    } catch {
      // Ignore
    }
  }, []);

  useEffect(() => {
    void fetchTopology();
    void fetchGlobalDbaConsole('TODAS', 'TODOS');
  }, [fetchTopology, fetchGlobalDbaConsole]);

  useEffect(() => {
    if (activeSite === 'QUITO') setSelectedNodeId('quito-sql');
    else if (activeSite === 'GUAYAQUIL') setSelectedNodeId('guayaquil-sql');
    else if (activeSite === 'CUENCA_CLOUD') setSelectedNodeId('cuenca-cloud');
  }, [activeSite]);

  useEffect(() => {
    if (selectedNodeId && selectedNodeId !== 'global-federated') {
      void fetchNodeLogs(selectedNodeId);
    }
  }, [selectedNodeId, fetchNodeLogs]);

  const handleSelectNodeForDba = (nodeId: string, defaultSql?: string) => {
    setSelectedNodeId(nodeId);
    const nodeObj = topology?.nodes.find(n => n.id === nodeId);
    if (defaultSql) {
      setSqlText(defaultSql);
    } else if (nodeObj && nodeObj.presets.length > 0) {
      setSqlText(nodeObj.presets[0].sql);
    }
    setActiveTab('dba_prompt');
  };

  const runDbaQuery = async (overrideNodeId?: string, overrideSql?: string) => {
    const targetNode = overrideNodeId ?? selectedNodeId;
    const targetSql = overrideSql ?? sqlText;
    setRunningQuery(true);
    setQueryError('');
    try {
      const res = await fetch(`${API_BASE_URL}/api/arquitectura/dba/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nodeId: targetNode, sql: targetSql }),
      });
      const body = await res.json();
      if (!res.ok) {
        setQueryError(body?.detail || 'Error al ejecutar la consulta SQL en el nodo.');
      } else {
        setQueryResult(body);
        if (targetNode !== 'global-federated') {
          void fetchNodeLogs(targetNode);
        }
      }
    } catch (err) {
      setQueryError(err instanceof Error ? err.message : 'Error de red conectando al nodo.');
    } finally {
      setRunningQuery(false);
    }
  };

  const triggerAgentsRoundNow = async () => {
    setLoadingGlobal(true);
    try {
      const operations = [
        { sede: 'GUAYAQUIL', agente: 'Agente-4-GYE', usuario: 'v_jefe', modulo: 'VENTAS', operacion: 'Venta corporativa POS Guayaquil (:3306)', montoUsd: 495.5 },
        { sede: 'GUAYAQUIL_DWH', agente: 'Agente-5-DWH', usuario: 'ctbl_supervisor', modulo: 'VENTAS', operacion: 'Mini-ETL consolidación hacia Esquema Estrella BD 5 (:3309)', montoUsd: 1420.0 },
        { sede: 'CUENCA', agente: 'Agente-6-Cuenca', usuario: 'i_operador', modulo: 'INVENTARIOS', operacion: 'Transacción WAN Supabase Cloud Cuenca (:5432)', montoUsd: 380.0 },
      ];
      await Promise.all(
        operations.map(op =>
          fetch(`${API_BASE_URL}/api/agentes/operacion`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Sede': op.sede },
            body: JSON.stringify(op),
          })
        )
      );
      await fetchGlobalDbaConsole(filterSede, filterModulo);
      await fetchTopology();
    } finally {
      setLoadingGlobal(false);
    }
  };

  const runTwoPhaseCommit = async (forceFail?: boolean) => {
    const failFlag = forceFail !== undefined ? forceFail : simulateFail;
    setSimulateFail(failFlag);
    setRunningTwoPc(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/arquitectura/distribuida/2pc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          productId: 'PRO-004',
          quantity: twoPcQty,
          sourceNode: 'GUAYAQUIL',
          targetNode: 'QUITO',
          simulatePrepareFailure: failFlag,
        }),
      });
      if (res.ok) {
        const data: TwoPcResult = await res.json();
        setTwoPcResult(data);
        void fetchTopology();
      }
    } finally {
      setRunningTwoPc(false);
    }
  };

  const currentNode = topology?.nodes.find(n => n.id === selectedNodeId);
  const tps = Math.max(2, Math.round(simulatedUsers * 0.18));

  return (
    <div>
      {/* ENCABEZADO CON LA ESTÉTICA DE LA CAVA */}
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            CLÚSTER HÍBRIDO MULTI-MÁQUINA · TAILSCALE VPN · 3 RÉPLICAS API ({globalData?.apiReplica || topology?.apiReplica || 'api_lacava_1'})
          </span>
          <h1>Consola Global del DBA & Topología en Vivo</h1>
          <p>
            <strong>Quito (PC Escritorio):</strong> BD 1 SQL (:3307), BD 2 MongoDB (:27017), BD 3 Paralela HASH (:3308) ·{' '}
            <strong>Guayaquil (Laptop):</strong> BD 4 SQL (:3306), BD 5 DWH Estrella (:3309) ·{' '}
            <strong>Cuenca (Cloud):</strong> BD 6 Supabase PostgreSQL (:5432)
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span className="demo-badge">
            {topology ? `${topology.onlineNodes}/${topology.totalNodes} BDs ONLINE` : 'CONECTANDO...'}
          </span>
          <button
            type="button"
            className="btn btn-outline"
            onClick={() => {
              void fetchTopology();
              void fetchGlobalDbaConsole();
            }}
            disabled={loadingTopo || loadingGlobal}
          >
            <RefreshCw size={14} />
            {loadingTopo || loadingGlobal ? 'Sincronizando...' : 'Refrescar 6 BDs'}
          </button>
        </div>
      </div>

      {/* PESTAÑAS CON LOS COLORES BORGOÑA Y VERDE BOSQUE DE LA CAVA */}
      <div style={{ display: 'flex', gap: '9px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {[
          { id: 'global_dba', label: '1. Consola Global del DBA (6 BDs Unificadas + Filtro Sede/Módulo)', icon: Filter },
          { id: 'board', label: '2. Mapa de Topología en Vivo (Quito 3 + GYE 2 + Cuenca Cloud)', icon: Network },
          { id: 'dba_prompt', label: '3. Prompt SQL / MongoDB + 15 Usuarios RBAC', icon: Terminal },
          { id: 'twopc', label: '4. Concurrencia & Simulador 2PC (Preguntas 4 y 5)', icon: ShieldCheck },
          { id: 'si_docker', label: '5. Nginx LB :8080, 3 Réplicas Docker & Power BI', icon: Box },
        ].map(tab => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id as typeof activeTab)}
              className="btn"
              style={{
                background: active ? '#183a31' : '#ffffff',
                color: active ? '#ffffff' : '#25251f',
                border: active ? '1px solid #183a31' : '1px solid #e9e6de',
                boxShadow: active ? '0 4px 12px rgba(24,58,49,0.14)' : 'none',
              }}
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ==================== TAB 1: CONSOLA GLOBAL DEL DBA (TAREA 2.2 Y 2.3) ==================== */}
      {activeTab === 'global_dba' && (
        <div>
          <section className="card">
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Database size={18} color="#782c3e" />
                  Consola Global del DBA — Consulta Paralela de las 6 BDs (`GET /api/dba/global`)
                </h2>
                <p>
                  Unifica en tiempo real los registros de <strong>MariaDB (:3307, :3308, :3306, :3309)</strong>, <strong>MongoDB (:27017)</strong> y <strong>Supabase PostgreSQL (:5432)</strong> agregando <code>origen_nodo</code> y latencia en <code>ms</code>.
                </p>
              </div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span className="demo-badge">
                  RÉPLICA QUE RESPONDIÓ: {globalData?.apiReplica || 'api_lacava_1'} · {globalData?.totalExecutionTimeMs ?? 0} ms
                </span>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void triggerAgentsRoundNow()}
                  disabled={loadingGlobal}
                >
                  <Play size={14} />
                  Disparar Ronda de Agentes IA Ahora
                </button>
              </div>
            </div>

            {/* TARJETAS DE LATENCIA EN PARALELO DE LAS 6 BDs */}
            {globalData && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(175px, 1fr))', gap: '10px', marginBottom: '16px' }}>
                {Object.entries(globalData.nodeLatencies).map(([sedeKey, info]) => (
                  <div
                    key={sedeKey}
                    onClick={() => {
                      const nextSede = filterSede === sedeKey ? 'TODAS' : sedeKey;
                      setFilterSede(nextSede);
                      void fetchGlobalDbaConsole(nextSede, filterModulo);
                    }}
                    style={{
                      padding: '11px 13px',
                      borderRadius: '9px',
                      border: filterSede === sedeKey ? '2px solid #782c3e' : '1px solid #e9e6de',
                      background: filterSede === sedeKey ? '#fbf3f0' : '#faf9f6',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '11.5px', color: '#183a31' }}>{info.bdId} · {sedeKey}</strong>
                      <span className={`badge ${info.status === 'ONLINE' ? 'badge-APR' : 'badge-ERR'}`}>
                        {info.latencyMs} ms
                      </span>
                    </div>
                    <div style={{ fontSize: '10.5px', color: '#787970', marginTop: '4px' }}>
                      {info.recordsReturned} registros unificados
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* FILTROS POR SEDE (`X-Sede`) Y POR MÓDULO (`C, I, V, TH, Ctbl`) */}
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '14px', padding: '12px', background: '#faf9f6', borderRadius: '9px', border: '1px solid #e9e6de' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <strong style={{ fontSize: '11.5px', color: '#183a31' }}>Filtrar por Sede (Header X-Sede):</strong>
                <select
                  className="select"
                  style={{ width: 'auto', minWidth: '185px', height: '35px', padding: '4px 10px' }}
                  value={filterSede}
                  onChange={e => {
                    setFilterSede(e.target.value);
                    void fetchGlobalDbaConsole(e.target.value, filterModulo);
                  }}
                >
                  <option value="TODAS">Todas las 6 Bases de Datos</option>
                  <option value="QUITO">BD 1 · QUITO (MariaDB :3307)</option>
                  <option value="QUITO_NOSQL">BD 2 · QUITO_NOSQL (MongoDB :27017)</option>
                  <option value="QUITO_PARALELA">BD 3 · QUITO_PARALELA (Hash :3308)</option>
                  <option value="GUAYAQUIL">BD 4 · GUAYAQUIL (MariaDB Local :3306)</option>
                  <option value="GUAYAQUIL_DWH">BD 5 · GUAYAQUIL_DWH (Estrella :3309)</option>
                  <option value="CUENCA">BD 6 · CUENCA (Supabase :5432)</option>
                </select>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <strong style={{ fontSize: '11.5px', color: '#183a31' }}>Filtrar por Módulo (5 Cilindros):</strong>
                <select
                  className="select"
                  style={{ width: 'auto', minWidth: '175px', height: '35px', padding: '4px 10px' }}
                  value={filterModulo}
                  onChange={e => {
                    setFilterModulo(e.target.value);
                    void fetchGlobalDbaConsole(filterSede, e.target.value);
                  }}
                >
                  <option value="TODOS">Todos los 5 Módulos</option>
                  <option value="COMPRAS">[C] Compras</option>
                  <option value="INVENTARIOS">[I] Inventarios</option>
                  <option value="VENTAS">[V] Ventas</option>
                  <option value="TALENTO_HUMANO">[TH] Talento Humano</option>
                  <option value="CONTABILIDAD">[Ctbl] Contabilidad</option>
                </select>
              </div>
            </div>

            {/* TABLA UNIFICADA DE LAS 6 BDs */}
            <div className="table-scroll" style={{ maxHeight: '440px' }}>
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Origen Nodo (`origen_nodo`)</th>
                    <th>Header `X-Sede`</th>
                    <th>Módulo</th>
                    <th>Usuario RBAC (15 Usr)</th>
                    <th>Rol RBAC (3 Roles)</th>
                    <th>Operación / Documento / Lote ETL</th>
                    <th>Monto USD</th>
                    <th>Fecha / Hora</th>
                  </tr>
                </thead>
                <tbody>
                  {globalData?.data.map((row, idx) => (
                    <tr key={idx}>
                      <td><code>{row.id}</code></td>
                      <td><strong style={{ color: '#183a31' }}>{row.origen_nodo}</strong></td>
                      <td><span className="badge badge-ABI">{row.sede}</span></td>
                      <td><strong>{row.modulo}</strong></td>
                      <td><code>{row.usuario_rbac}</code></td>
                      <td><span className="badge badge-APR">{row.rol_rbac}</span></td>
                      <td style={{ whiteSpace: 'normal', maxWidth: '340px' }}>{row.detalle}</td>
                      <td><strong>${Number(row.monto_usd || 0).toFixed(2)}</strong></td>
                      <td>{String(row.fecha_hora).replace('T', ' ').slice(0, 19)}</td>
                    </tr>
                  ))}
                  {(!globalData || globalData.data.length === 0) && (
                    <tr>
                      <td colSpan={9} className="empty-state">No hay registros para el filtro seleccionado.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}

      {/* ==================== TAB 2: MAPA DE TOPOLOGÍA EN VIVO ==================== */}
      {activeTab === 'board' && topology && (
        <div>
          {/* 5 CILINDROS DE LA PIZARRA (C, I, V, TH, Ctbl) */}
          <section className="card">
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Layers size={18} color="#782c3e" />
                  5 Módulos del Negocio ("La Cava") + 15 Usuarios y 3 Roles RBAC
                </h2>
                <p>
                  Cada módulo tiene 3 usuarios dedicados (<code>_jefe</code>, <code>_supervisor</code>, <code>_operador</code>) en BD 1 Quito (<code>:3307</code>) y BD 4 Guayaquil (<code>:3306</code>).
                </p>
              </div>
              <span className="demo-badge">15 USUARIOS · 3 ROLES RBAC</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(185px, 1fr))', gap: '12px' }}>
              {[
                { code: 'C', name: 'Compras', users: 'c_jefe, c_supervisor, c_operador', accent: '#782c3e', bg: '#fbf3f0' },
                { code: 'I', name: 'Inventarios', users: 'i_jefe, i_supervisor, i_operador', accent: '#183a31', bg: '#eff5f1' },
                { code: 'V', name: 'Ventas', users: 'v_jefe, v_supervisor, v_operador', accent: '#782c3e', bg: '#fbf3f0' },
                { code: 'TH', name: 'Talento Humano', users: 'th_jefe, th_supervisor, th_operador', accent: '#a96b16', bg: '#fbf4e6' },
                { code: 'Ctbl', name: 'Contabilidad', users: 'ctbl_jefe, ctbl_supervisor, ctbl_operador', accent: '#183a31', bg: '#eff5f1' },
              ].map(m => {
                const countObj = topology.nodes[3]?.modules?.find(x => x.code === m.code);
                return (
                  <div
                    key={m.code}
                    onClick={() => handleSelectNodeForDba('guayaquil-sql')}
                    style={{
                      border: '1px solid #e9e6de',
                      borderTop: `3px solid ${m.accent}`,
                      borderRadius: '10px',
                      padding: '14px',
                      background: '#faf9f6',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ background: m.bg, color: m.accent, fontWeight: 800, fontSize: '12px', padding: '3px 9px', borderRadius: '6px' }}>
                        Módulo [{m.code}]
                      </span>
                      <span style={{ fontSize: '11px', fontWeight: 700, color: '#25251f' }}>
                        {countObj ? `${countObj.rows} filas` : 'Activo'}
                      </span>
                    </div>
                    <div style={{ fontFamily: "'Playfair Display', Georgia, serif", fontWeight: 600, fontSize: '16px', marginTop: '8px', color: '#25251f' }}>
                      {m.name}
                    </div>
                    <div style={{ fontSize: '10.5px', color: '#787970', marginTop: '4px', fontFamily: 'monospace' }}>
                      {m.users}
                    </div>
                    <div style={{ fontSize: '11px', color: m.accent, fontWeight: 700, marginTop: '10px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      Ver en BD 4 Guayaquil (:3306) <ArrowRight size={12} />
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* 3 SEDES: PC ESCRITORIO QUITO (3 BDs), LAPTOP GUAYAQUIL (2 BDs), NUBE CUENCA (1 Cloud DB) */}
          {topology.sites.map(site => (
            <section key={site.siteId} className="card">
              <div className="section-heading" style={{ borderBottom: '1px solid #efeee9', paddingBottom: '12px' }}>
                <div>
                  <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {site.siteId === 'CUENCA_LOJA_CLOUD' ? <Cloud size={19} color="#782c3e" /> : <Server size={19} color="#183a31" />}
                    {site.title}
                  </h2>
                  <p>{site.subtitle}</p>
                </div>
                <span className="demo-badge">{site.badge}</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(310px, 1fr))', gap: '14px' }}>
                {site.nodes.map(node => (
                  <div
                    key={node.id}
                    style={{
                      border: '1px solid #e9e6de',
                      borderRadius: '10px',
                      padding: '16px',
                      background: '#faf9f6',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      gap: '10px',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                        <span className={`badge ${node.status === 'ONLINE' ? 'badge-APR' : 'badge-ERR'}`} style={{ gap: '4px' }}>
                          {node.status === 'ONLINE' ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                          {node.status} · {node.latencyMs} ms
                        </span>
                        <span
                          style={{
                            fontSize: '11px',
                            fontWeight: 700,
                            background: '#183a31',
                            color: '#f9f7f0',
                            padding: '3px 9px',
                            borderRadius: '6px',
                            fontFamily: 'monospace',
                          }}
                        >
                          X-Sede: {node.xSede} · :{node.actualPort}
                        </span>
                      </div>

                      <h3 style={{ margin: '10px 0 4px', fontSize: '14.5px', color: '#25251f', fontFamily: "'Playfair Display', Georgia, serif" }}>
                        {node.name}
                      </h3>
                      <div style={{ fontSize: '11.5px', color: '#782c3e', fontWeight: 600 }}>{node.role}</div>

                      <div
                        style={{
                          marginTop: '10px',
                          background: '#ffffff',
                          border: '1px solid #e9e6de',
                          borderRadius: '8px',
                          padding: '10px',
                          fontSize: '11.5px',
                          display: 'grid',
                          gridTemplateColumns: '1fr 1fr',
                          gap: '6px',
                        }}
                      >
                        <div><strong>Motor:</strong> {node.engine}</div>
                        <div><strong>Base:</strong> <code>{node.database}</code></div>
                        <div><strong>Objetos:</strong> {node.tablesCount}</div>
                        <div><strong>Tamaño:</strong> {node.sizeKb} KB</div>
                        <div><strong>Máquina:</strong> {node.machine || node.site}</div>
                        <div><strong>Endpoint:</strong> <code>{node.activeHost || node.host}:{node.actualPort}</code></div>
                      </div>

                      <div style={{ marginTop: '8px', fontSize: '10.5px', color: '#575950', background: '#f2efe9', padding: '7px 9px', borderRadius: '6px', fontFamily: 'monospace' }}>
                        {node.heidiSqlHint}
                      </div>
                    </div>

                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => handleSelectNodeForDba(node.id)}
                      style={{ width: '100%', marginTop: '4px' }}
                    >
                      <Terminal size={14} />
                      Inspeccionar {node.bdId} en Puerto :{node.actualPort}
                    </button>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {/* ==================== TAB 3: PROMPT SQL / MONGODB DEL DBA ==================== */}
      {activeTab === 'dba_prompt' && (
        <div>
          <section className="card">
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Terminal size={19} color="#782c3e" />
                  Prompt SQL & MongoDB del DBA — 6 BDs y Matriz de 15 Usuarios RBAC
                </h2>
                <p>
                  Selecciona cualquiera de las 6 BDs (<code>:3307</code>, <code>:27017</code>, <code>:3308</code>, <code>:3306</code>, <code>:3309</code>, <code>:5432</code>) para consultar sus tablas, particiones HASH o colecciones MongoDB.
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' }}>
              {topology?.nodes.map(n => {
                const isSelected = selectedNodeId === n.id;
                return (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => {
                      setSelectedNodeId(n.id);
                      if (n.presets.length > 0) {
                        setSqlText(n.presets[0].sql);
                        void runDbaQuery(n.id, n.presets[0].sql);
                      }
                    }}
                    className="btn"
                    style={{
                      background: isSelected ? '#183a31' : '#faf9f6',
                      color: isSelected ? '#ffffff' : '#25251f',
                      border: isSelected ? '1px solid #183a31' : '1px solid #d9d4c7',
                    }}
                  >
                    <Database size={13} />
                    {n.shortName}
                  </button>
                );
              })}
            </div>

            {currentNode && currentNode.presets.length > 0 && (
              <div style={{ marginBottom: '14px' }}>
                <div style={{ fontSize: '11.5px', fontWeight: 700, color: '#575950', marginBottom: '6px' }}>
                  Consultas Rápidas para {currentNode.name}:
                </div>
                <div style={{ display: 'flex', gap: '7px', flexWrap: 'wrap' }}>
                  {currentNode.presets.map((preset, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="btn btn-outline"
                      onClick={() => {
                        setSqlText(preset.sql);
                        void runDbaQuery(currentNode.id, preset.sql);
                      }}
                      style={{ padding: '6px 11px', fontSize: '11.5px', background: '#faf9f6' }}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <textarea
                rows={4}
                value={sqlText}
                onChange={e => setSqlText(e.target.value)}
                spellCheck={false}
                style={{
                  width: '100%',
                  fontFamily: 'Consolas, Monaco, monospace',
                  fontSize: '12.5px',
                  padding: '12px',
                  borderRadius: '8px',
                  border: '1px solid #183a31',
                  background: '#132a23',
                  color: '#e8f3ec',
                  resize: 'vertical',
                }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                <span style={{ fontSize: '12px', color: '#575950' }}>
                  Nodo destino:{' '}
                  <strong style={{ color: '#183a31' }}>
                    {currentNode ? `${currentNode.name} (Header X-Sede: ${currentNode.xSede} · Puerto :${currentNode.actualPort})` : ''}
                  </strong>
                </span>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void runDbaQuery()}
                  disabled={runningQuery}
                >
                  <Play size={15} />
                  {runningQuery ? 'Ejecutando...' : 'Ejecutar en Nodo'}
                </button>
              </div>
            </div>

            {queryError && (
              <div style={{ marginTop: '12px', padding: '12px', background: '#f8e9e8', border: '1px solid #e2b4b1', borderRadius: '8px', color: '#9a3937', fontSize: '12.5px' }}>
                <strong>Error:</strong> {queryError}
              </div>
            )}

            {queryResult && (
              <div style={{ marginTop: '16px' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    background: '#183a31',
                    color: '#f9f7f0',
                    padding: '10px 14px',
                    borderRadius: '8px 8px 0 0',
                    fontSize: '12px',
                    flexWrap: 'wrap',
                    gap: '8px',
                  }}
                >
                  <div>
                    <strong>Respuesta desde:</strong> {queryResult.nodeName} ·{' '}
                    <code style={{ color: '#e7c6a8' }}>
                      {queryResult.host}:{queryResult.port}/{queryResult.database}
                    </code>
                  </div>
                  <div style={{ display: 'flex', gap: '14px' }}>
                    <span><strong>Filas:</strong> {queryResult.rowCount}</span>
                    <span style={{ color: '#9ce2b9' }}><strong>Latencia:</strong> {queryResult.executionTimeMs} ms</span>
                  </div>
                </div>

                <div className="table-scroll" style={{ border: '1px solid #e9e6de', borderTop: 'none', borderRadius: '0 0 8px 8px', maxHeight: '380px' }}>
                  <table>
                    <thead>
                      <tr>
                        {queryResult.columns.map((col, idx) => (
                          <th key={idx}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {queryResult.rows.map((row, rIdx) => (
                        <tr key={rIdx}>
                          {row.map((val, cIdx) => (
                            <td key={cIdx} style={{ whiteSpace: 'normal', maxWidth: '360px' }}>
                              {val === null ? <em style={{ color: '#96968d' }}>NULL</em> : String(val)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>

          {nodeLogs && (
            <div className="grid-2">
              <section className="card">
                <div className="section-heading">
                  <div>
                    <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Activity size={17} color="#782c3e" />
                      Actividad de Agentes IA — Puerto :{nodeLogs.port}
                    </h2>
                    <p>{nodeLogs.nodeName}</p>
                  </div>
                </div>
                <div className="table-scroll" style={{ maxHeight: '280px' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Fecha/Hora</th>
                        <th>Usuario RBAC</th>
                        <th>Módulo/Lote</th>
                        <th>Detalle</th>
                      </tr>
                    </thead>
                    <tbody>
                      {nodeLogs.auditLogs.map((l, i) => (
                        <tr key={i}>
                          <td><code>{l.id}</code></td>
                          <td>{String(l.fecha_hora).replace('T', ' ').slice(0, 19)}</td>
                          <td><code>{l.usuario}</code></td>
                          <td><strong>{l.evento}</strong></td>
                          <td style={{ whiteSpace: 'normal' }}>{l.detalle}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="card">
                <div className="section-heading">
                  <div>
                    <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <HardDrive size={17} color="#183a31" />
                      Conexiones & Variables en Puerto :{nodeLogs.port}
                    </h2>
                    <p>Sesiones activas del motor</p>
                  </div>
                </div>
                <div style={{ fontSize: '11.5px', background: '#faf9f6', border: '1px solid #e9e6de', padding: '8px 10px', borderRadius: '6px', marginBottom: '10px', fontFamily: 'monospace' }}>
                  {Object.entries(nodeLogs.variables).map(([k, v]) => (
                    <div key={k}><strong>{k}:</strong> {String(v)}</div>
                  ))}
                </div>
                <div className="table-scroll" style={{ maxHeight: '200px' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>PID/ID</th>
                        <th>Usuario</th>
                        <th>Host</th>
                        <th>BD</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {nodeLogs.activeConnections.map((c, i) => (
                        <tr key={i}>
                          <td><code>{c.ID}</code></td>
                          <td>{c.USER}</td>
                          <td><code>{c.HOST}</code></td>
                          <td><code>{c.DB}</code></td>
                          <td>{c.COMMAND}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          )}
        </div>
      )}

      {/* ==================== TAB 4: SIMULADOR 2PC (PREGUNTAS 4 Y 5) ==================== */}
      {activeTab === 'twopc' && (
        <div>
          <section className="card">
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShieldCheck size={19} color="#183a31" />
                  Simulador del Protocolo Two-Phase Commit (2PC) — BD 1 Quito (:3307), BD 4 Guayaquil (:3306) y BD 6 Cuenca (:5432)
                </h2>
                <p>
                  Demuestra transacciones atómicas entre las máquinas y el manejo de <code>GLOBAL_ROLLBACK</code> si un nodo cae durante la Fase <code>PREPARE</code> (Pregunta 5).
                </p>
              </div>
              <span className="demo-badge">PREGUNTA 5 · 2PC XA</span>
            </div>

            <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap', background: '#faf9f6', padding: '16px', borderRadius: '10px', border: '1px solid #e9e6de' }}>
              <div>
                <label className="form-group" style={{ margin: 0 }}>
                  Botellas a transferir (BD 4 Guayaquil :3306 → BD 1 Quito :3307):
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={100}
                    value={twoPcQty}
                    onChange={e => setTwoPcQty(Number(e.target.value) || 10)}
                    style={{ width: '130px', fontWeight: 700 }}
                  />
                </label>
              </div>

              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '14px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={runningTwoPc}
                  onClick={() => void runTwoPhaseCommit(false)}
                >
                  <CheckCircle2 size={15} />
                  Ejecutar 2PC Exitoso (3/3 Votos COMMIT)
                </button>

                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={runningTwoPc}
                  onClick={() => void runTwoPhaseCommit(true)}
                >
                  <AlertTriangle size={15} />
                  Simular Caída de Nodo en Fase PREPARE (Pregunta 5 → ROLLBACK)
                </button>
              </div>
            </div>

            {twoPcResult && (
              <div style={{ marginTop: '18px' }}>
                <div
                  style={{
                    padding: '14px 18px',
                    borderRadius: '10px',
                    background: twoPcResult.decision === 'GLOBAL_COMMIT' ? '#e6f2eb' : '#f8e9e8',
                    border: twoPcResult.decision === 'GLOBAL_COMMIT' ? '1px solid #b8d8c5' : '1px solid #e2b4b1',
                    color: twoPcResult.decision === 'GLOBAL_COMMIT' ? '#183a31' : '#782c3e',
                    marginBottom: '14px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: '14.5px' }}>
                      Decisión del Coordinador 2PC: {twoPcResult.decision} (TX: {twoPcResult.txId})
                    </strong>
                    <span style={{ fontWeight: 700, fontSize: '12px' }}>Tiempo total: {twoPcResult.executionTimeMs} ms</span>
                  </div>
                  <div style={{ marginTop: '4px', fontSize: '12.5px' }}>{twoPcResult.summary}</div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {twoPcResult.steps.map((st, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '12px 16px',
                        borderRadius: '8px',
                        background: '#faf9f6',
                        border: '1px solid #e9e6de',
                        borderLeft:
                          st.status.includes('ABORT') || st.status.includes('ROLLBACK')
                            ? '4px solid #782c3e'
                            : '4px solid #183a31',
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#787970' }}>
                          [{st.timestamp}] · {st.phase} · <strong style={{ color: '#25251f' }}>{st.node}</strong>
                        </div>
                        <div style={{ fontSize: '12.5px', color: '#25251f', marginTop: '3px' }}>{st.message}</div>
                      </div>
                      <span
                        className={`badge ${st.status.includes('ABORT') || st.status.includes('ROLLBACK') ? 'badge-ERR' : 'badge-APR'}`}
                      >
                        {st.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {/* ==================== TAB 5: ARQUITECTURA DE SI, NGINX 3 RÉPLICAS & POWER BI ==================== */}
      {activeTab === 'si_docker' && topology && (
        <div>
          <section className="card">
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Cpu size={19} color="#782c3e" />
                  Speed-up vs. Scale-out: Particionamiento BD 3 (:3308) vs. 3 Réplicas API + Nginx LB + Power BI
                </h2>
                <p>
                  Validación de las 8 Preguntas del Examen: Balanceador Round-Robin, 3 Réplicas de <code>api_lacava</code> y conexión de Power BI a BD 5 (<code>:3309</code>).
                </p>
              </div>
              <span className="demo-badge">3 RÉPLICAS API · NGINX LB</span>
            </div>

            <div style={{ background: '#faf9f6', padding: '16px', borderRadius: '10px', border: '1px solid #e9e6de', marginBottom: '16px' }}>
              <label style={{ fontWeight: 700, fontSize: '13px', display: 'block', marginBottom: '8px', color: '#25251f' }}>
                Usuarios Concurrentes Conectados al Clúster (15 Usuarios RBAC → 1000 Usuarios):{' '}
                <span style={{ color: '#782c3e', fontSize: '15px' }}>{simulatedUsers} usuarios</span>
              </label>
              <input
                type="range"
                min={15}
                max={1000}
                step={5}
                value={simulatedUsers}
                onChange={e => setSimulatedUsers(Number(e.target.value))}
                style={{ width: '100%', accentColor: '#782c3e' }}
              />
              <div className="metric-grid" style={{ marginTop: '14px', marginBottom: 0 }}>
                <article className="metric-card" style={{ minHeight: '105px' }}>
                  <span>TRANSACCIONES / SEGUNDO (/s)</span>
                  <strong>{tps} tx/s</strong>
                  <small>Repartidas en 3 réplicas API</small>
                </article>
                <article className="metric-card" style={{ minHeight: '105px' }}>
                  <span>TRANSACCIONES / MINUTO (/m)</span>
                  <strong>{(tps * 60).toLocaleString()} tx/m</strong>
                  <small>6 Agentes IA + Terminales POS</small>
                </article>
                <article className="metric-card" style={{ minHeight: '105px' }}>
                  <span>TRANSACCIONES / HORA (/h)</span>
                  <strong>{(tps * 3600).toLocaleString()} tx/h</strong>
                  <small>Operación hora pico</small>
                </article>
                <article className="metric-card" style={{ minHeight: '105px' }}>
                  <span>TRANSACCIONES / DÍA (/d - 8h)</span>
                  <strong>{(tps * 28800).toLocaleString()} tx/d</strong>
                  <small>Consolidadas en BD 5 DWH (:3309)</small>
                </article>
              </div>
            </div>

            <div className="grid-3">
              <div style={{ border: '1px solid #e9e6de', borderRadius: '10px', padding: '14px', background: '#faf9f6' }}>
                <strong style={{ color: '#782c3e', fontSize: '13px' }}>1. Scale-Out Horizontal (3 Réplicas API)</strong>
                <p style={{ fontSize: '12px', color: '#575950', marginTop: '6px' }}>
                  <code>api_lacava_1 (:8001)</code>, <code>api_lacava_2 (:8002)</code> y <code>api_lacava_3 (:8003)</code> balanceadas en Round-Robin por <code>nginx_lb</code> (definido en <code>docker-compose.app.yml</code> y <code>nginx.conf</code>).
                </p>
              </div>
              <div style={{ border: '1px solid #e9e6de', borderRadius: '10px', padding: '14px', background: '#faf9f6' }}>
                <strong style={{ color: '#183a31', fontSize: '13px' }}>2. Speed-Up en Motor BD 3 (:3308)</strong>
                <p style={{ fontSize: '12px', color: '#575950', marginTop: '6px' }}>
                  Tabla masiva <code>quito_paralela_db.historico_transacciones</code> particionada con <code>PARTITION BY HASH(id) PARTITIONS 4</code> para paralelismo intra-consulta.
                </p>
              </div>
              <div style={{ border: '1px solid #e9e6de', borderRadius: '10px', padding: '14px', background: '#faf9f6' }}>
                <strong style={{ color: '#a96b16', fontSize: '13px' }}>3. Conexión Directa para Power BI Desktop</strong>
                <p style={{ fontSize: '12px', color: '#575950', marginTop: '6px' }}>
                  • <strong>BD 5 DWH (MySQL/MariaDB):</strong> <code>127.0.0.1:3309</code> BD: <code>db_gye_dwh</code> (Tablas: <code>fact_ventas</code>, <code>dim_sede</code>, <code>dim_producto</code>, <code>dim_tiempo</code>)<br />
                  • <strong>BD 6 Cloud (PostgreSQL):</strong> <code>127.0.0.1:5432</code> BD: <code>cloud_cuenca_loja</code><br />
                  • <strong>Web JSON API:</strong> <code>http://localhost:8000/api/dba/global</code>
                </p>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
};

export default ArchitectureConsole;
