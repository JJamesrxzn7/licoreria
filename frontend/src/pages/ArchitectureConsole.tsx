import React, { useEffect, useState, useCallback } from 'react';
import {
  Server, Database, Terminal, Play, RefreshCw, ShieldCheck, AlertTriangle,
  Layers, Cloud, Activity, CheckCircle2, XCircle, HardDrive, Network,
  Filter, GitCompare, Lock
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { isDbaUser, isSuperAdmin } from '../rolePermissions';

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

const BRANCH_IDENTITIES = [
  {
    code: 'UIO',
    city: 'SEDE MATRIZ QUITO (Sierra Norte)',
    machine: 'PC de Escritorio · IP Tailscale: 100.77.220.102',
    accent: '#782c3e',
    bg: '#fbf3f0',
    emblem: '🍷 Cava Gran Reserva & Centro Financiero Matriz',
    specialty: 'Whisky Single Malt Escocés 12Y/18Y, Vinos Gran Reserva de Altura y Consolidación Contable Nacional.',
    databases: '3 Bases de Datos: BD 1 MariaDB OLTP (:3307) · BD 2 MongoDB NoSQL (:27017) · BD 3 MariaDB Paralela HASH (:3308)',
    agents: 'Agente 1 (X-Sede: QUITO) · Agente 2 (X-Sede: QUITO_NOSQL) · Agente 3 (X-Sede: QUITO_PARALELA)',
  },
  {
    code: 'GYE',
    city: 'SUCURSAL REGIONAL GUAYAQUIL (Costa & Puerto)',
    machine: 'Laptop · IP Tailscale: 100.123.81.4',
    accent: '#183a31',
    bg: '#eff5f1',
    emblem: '⚓ Hub Logístico Puerto Marítimo & Data Warehouse BI',
    specialty: 'Importación de Contenedores SENAE, Distribución Cervecería Nacional, Rones Añejos y Cubo Estrella Power BI.',
    databases: '2 Bases de Datos: BD 4 MariaDB Local OLTP (:3306) · BD 5 MariaDB DWH Estrella (:3309)',
    agents: 'Agente 4 (X-Sede: GUAYAQUIL) · Agente 5 Mini-ETL (X-Sede: GUAYAQUIL_DWH) + Nginx LB & 3 Réplicas API',
  },
  {
    code: 'CUE',
    city: 'SUCURSAL AUSTRAL CUENCA & LOJA (Cloud DBaaS)',
    machine: 'Nube Administrada · Supabase PostgreSQL (:5432)',
    accent: '#a96b16',
    bg: '#fbf4e6',
    emblem: '🏔️ Destilerías Tradicionales del Sur (Azuay & Loja)',
    specialty: 'Productores y Destilerías Australes: Aguardiente Zhumir (Azende), Cristal (EASA), Ron San Miguel y Cantaclaro.',
    databases: '1 Base de Datos Cloud: BD 6 PostgreSQL 18 / Supabase DBaaS (:5432 cloud_cuenca_loja)',
    agents: 'Agente 6 (X-Sede: CUENCA) · Medición de Latencia WAN en Tiempo Real y Certificados TLS',
  },
];

export const ArchitectureConsole: React.FC = () => {
  const { user } = useAuth();
  const isStrictDba = isDbaUser(user) && !isSuperAdmin(user);
  const [activeTab, setActiveTab] = useState<'diagram_vs' | 'global_dba' | 'board' | 'dba_prompt' | 'twopc'>('diagram_vs');
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
    "SELECT username, password_plano, rol_bd, rol_aplicacion, modulo_codigo, modulo_nombre, nombre_colaborador, descripcion_cargo, sede_nodo, estado FROM rbac_matriz_15_usuarios ORDER BY modulo_codigo, rol_bd;"
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
        { sede: 'GUAYAQUIL', agente: 'Agente-4-GYE', usuario: 'v_jefe', password: 'VentasJefe2026*', modulo: 'VENTAS', operacion: 'Venta corporativa POS Guayaquil (:3306)', montoUsd: 495.5 },
        { sede: 'GUAYAQUIL_DWH', agente: 'Agente-5-DWH', usuario: 'ctbl_supervisor', password: 'CtblSup2026*', modulo: 'VENTAS', operacion: 'Mini-ETL consolidación hacia Esquema Estrella BD 5 (:3309)', montoUsd: 1420.0 },
        { sede: 'CUENCA', agente: 'Agente-6-Cuenca', usuario: 'i_operador', password: 'InveOpe2026*', modulo: 'INVENTARIOS', operacion: 'Transacción WAN Supabase Cloud Cuenca (:5432)', montoUsd: 380.0 },
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

  const getNodeBadge = (xSedeKey: string) => {
    const n = topology?.nodes.find(node => node.xSede === xSedeKey);
    if (!n) return { status: 'ONLINE', ms: '—' };
    return { status: n.status, ms: `${n.latencyMs} ms` };
  };

  return (
    <div>
      {/* ENCABEZADO CON LA ESTÉTICA DE LA CAVA */}
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            SECCIÓN EXCLUSIVA DBA & ARQUITECTURA · TAILSCALE VPN · 3 RÉPLICAS API ({globalData?.apiReplica || topology?.apiReplica || 'api_lacava_1'})
          </span>
          <h1>Arquitectura de BD vs. Arquitectura de SI</h1>
          <p>
            <strong>Quito (100.77.220.102):</strong> BD 1 (:3307), BD 2 Mongo (:27017), BD 3 Hash (:3308) ·{' '}
            <strong>Guayaquil (100.123.81.4):</strong> BD 4 (:3306), BD 5 DWH (:3309) ·{' '}
            <strong>Cuenca (Cloud):</strong> BD 6 Supabase (:5432)
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
            {loadingTopo || loadingGlobal ? 'Sincronizando...' : 'Refrescar Clúster'}
          </button>
        </div>
      </div>

      {/* PESTAÑAS CON LOS COLORES BORGOÑA Y VERDE BOSQUE DE LA CAVA */}
      <div style={{ display: 'flex', gap: '9px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {[
          { id: 'diagram_vs', label: '1. Diagrama Maestro: Arquitectura de BD vs. Arquitectura de SI', icon: GitCompare, show: true },
          { id: 'dba_prompt', label: '2. Terminal Read-Only del DBA (Consultas para las 3 Sucursales / 6 BDs)', icon: Terminal, show: true },
          { id: 'global_dba', label: '3. Monitor Global Unificado (6 BDs en Paralelo · Solo Lectura)', icon: Filter, show: true },
          { id: 'board', label: '4. Identidad por Sucursal & Estado de 6 Nodos en Vivo', icon: Network, show: true },
          { id: 'twopc', label: '5. Simulador de Escritura 2PC (Exclusivo Admin / Arquitecto)', icon: ShieldCheck, show: !isStrictDba },
        ].filter(t => t.show).map(tab => {
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

      {/* ==================== TAB 1: DIAGRAMA MAESTRO (ARQUITECTURA BD VS ARQUITECTURA SI) ==================== */}
      {activeTab === 'diagram_vs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <section className="card" style={{ padding: '22px' }}>
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '18px' }}>
                  <GitCompare size={20} color="#782c3e" />
                  Diagrama Arquitectónico Integral — Pizarra Completa del Clúster Híbrido "La Cava"
                </h2>
                <p>
                  Contraste visual e interactivo entre el <strong>Dominio del DBA (Arquitectura de Bases de Datos)</strong> y el <strong>Dominio del Arquitecto de Software (Arquitectura de Sistemas de Información)</strong> conectados por Tailscale VPN.
                </p>
              </div>
              <span className="demo-badge">SHARED NOTHING · SCALE-OUT + SPEED-UP</span>
            </div>

            {/* LIENZO DEL DIAGRAMA MAESTRO (2 GRANDES COLUMNAS + PUENTE CENTRAL VPN / X-SEDE) */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(460px, 1fr))',
                gap: '18px',
                alignItems: 'stretch',
              }}
            >
              {/* ==================== LADO IZQUIERDO: ARQUITECTURA DE BASES DE DATOS (DBA) ==================== */}
              <div
                style={{
                  border: '2px solid #183a31',
                  borderRadius: '14px',
                  background: '#faf9f6',
                  padding: '18px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #183a31', paddingBottom: '10px' }}>
                  <div>
                    <span style={{ fontSize: '10px', fontWeight: 800, letterSpacing: '.14em', color: '#782c3e' }}>
                      LADO IZQUIERDO DE LA PIZARRA · ROL: DBA (`dba`)
                    </span>
                    <h3 style={{ margin: '2px 0 0', fontSize: '18px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                      1. Arquitectura de Bases de Datos (6 BDs)
                    </h3>
                  </div>
                  <span style={{ background: '#183a31', color: '#fff', padding: '4px 10px', borderRadius: '20px', fontSize: '10.5px', fontWeight: 700 }}>
                    6 Motores · 17 Usuarios RBAC
                  </span>
                </div>

                {/* 5 CILINDROS DE FRAGMENTACIÓN MODULAR (C, I, V, TH, Ctbl) */}
                <div style={{ background: '#ffffff', border: '1px solid #d9d4c7', borderRadius: '10px', padding: '12px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 800, color: '#183a31', marginBottom: '8px', display: 'flex', justifyContent: 'space-between' }}>
                    <span>5 CILINDROS / MÓDULOS DE NEGOCIO FRAGMENTADOS</span>
                    <span style={{ color: '#782c3e' }}>3 Roles × 5 Módulos = 15 Usuarios + DBA + Admin</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '6px' }}>
                    {[
                      { c: 'C', n: 'Compras', u: 'c_jefe / sup / ope', col: '#782c3e' },
                      { c: 'I', n: 'Inventarios', u: 'i_jefe / sup / ope', col: '#183a31' },
                      { c: 'V', n: 'Ventas', u: 'v_jefe / sup / ope', col: '#782c3e' },
                      { c: 'TH', n: 'T. Humano', u: 'th_jefe / sup / ope', col: '#a96b16' },
                      { c: 'Ctbl', n: 'Contabilidad', u: 'ctbl_jefe / sup / ope', col: '#183a31' },
                    ].map(cyl => (
                      <div
                        key={cyl.c}
                        onClick={() => handleSelectNodeForDba('guayaquil-sql')}
                        style={{
                          border: `1.5px solid ${cyl.col}`,
                          borderRadius: '10px 10px 6px 6px',
                          padding: '7px 5px',
                          textAlign: 'center',
                          background: '#faf9f6',
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ background: cyl.col, color: '#fff', fontWeight: 800, fontSize: '11px', borderRadius: '999px', padding: '2px 0', marginBottom: '4px' }}>
                          ({cyl.c})
                        </div>
                        <div style={{ fontWeight: 700, fontSize: '10.5px', color: '#25251f' }}>{cyl.n}</div>
                        <div style={{ fontSize: '8.5px', color: '#787970', marginTop: '2px', fontFamily: 'monospace' }}>{cyl.u}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* MÁQUINA 1: PC DE ESCRITORIO — NODO QUITO (3 BDs) */}
                <div style={{ background: '#ffffff', border: '1.5px solid #782c3e', borderRadius: '10px', padding: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <strong style={{ fontSize: '12px', color: '#782c3e' }}>
                      🖥️ MÁQUINA 1 (PC ESCRITORIO · 100.77.220.102) — NODO QUITO (3 BDs)
                    </strong>
                    <span className="badge badge-ANU" style={{ background: '#fbf3f0', color: '#782c3e' }}>Cava Gran Reserva Sierra</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
                    {[
                      { id: 'quito-sql', x: 'QUITO', title: 'BD 1 · SQL OLTP', sub: 'MariaDB :3307', desc: 'licoreriadatabase + 17 Usuarios RBAC' },
                      { id: 'quito-nosql', x: 'QUITO_NOSQL', title: 'BD 2 · NoSQL JSON', sub: 'MongoDB :27017', desc: 'logs_auditoria & eventos_agentes' },
                      { id: 'quito-otras', x: 'QUITO_PARALELA', title: 'BD 3 · Paralela', sub: 'MariaDB :3308', desc: 'PARTITION BY HASH(id) PARTITIONS 4 (Speed-up)' },
                    ].map(b => {
                      const st = getNodeBadge(b.x);
                      const isOnline = st.status === 'ONLINE';
                      return (
                        <div
                          key={b.id}
                          onClick={() => handleSelectNodeForDba(b.id)}
                          style={{
                            border: isOnline ? '1px solid #e9e6de' : '2px solid #9a3937',
                            borderRadius: '8px',
                            padding: '8px',
                            background: isOnline ? '#faf9f6' : '#f8e9e8',
                            cursor: 'pointer',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <strong style={{ fontSize: '11px', color: isOnline ? '#183a31' : '#9a3937' }}>{b.title}</strong>
                            <span style={{ fontSize: '9px', fontWeight: 800, color: isOnline ? '#267154' : '#9a3937' }}>
                              ● {isOnline ? `ONLINE · ${st.ms}` : 'CAÍDA / OFFLINE'}
                            </span>
                          </div>
                          <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#782c3e', fontFamily: 'monospace', marginTop: '2px' }}>{b.sub}</div>
                          <div style={{ fontSize: '9.5px', color: '#787970', marginTop: '3px' }}>{b.desc}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* MÁQUINA 2: LAPTOP — NODO GUAYAQUIL (2 BDs) */}
                <div style={{ background: '#ffffff', border: '1.5px solid #183a31', borderRadius: '10px', padding: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <strong style={{ fontSize: '12px', color: '#183a31' }}>
                      💻 MÁQUINA 2 (LAPTOP · 100.123.81.4) — NODO GUAYAQUIL (2 BDs)
                    </strong>
                    <span className="badge badge-APR">Hub Puerto Marítimo Costa</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
                    {[
                      { id: 'guayaquil-sql', x: 'GUAYAQUIL', title: 'BD 4 · SQL OLTP Local', sub: 'MariaDB :3306', desc: 'licoreriadatabase Costa + 17 Usuarios RBAC' },
                      { id: 'guayaquil-replica', x: 'GUAYAQUIL_DWH', title: 'BD 5 · DWH Estrella (OLAP)', sub: 'MariaDB :3309', desc: 'db_gye_dwh (fact_ventas, dim_sede, dim_producto, dim_tiempo)' },
                    ].map(b => {
                      const st = getNodeBadge(b.x);
                      const isOnline = st.status === 'ONLINE';
                      return (
                        <div
                          key={b.id}
                          onClick={() => handleSelectNodeForDba(b.id)}
                          style={{
                            border: isOnline ? '1px solid #e9e6de' : '2px solid #9a3937',
                            borderRadius: '8px',
                            padding: '9px',
                            background: isOnline ? '#faf9f6' : '#f8e9e8',
                            cursor: 'pointer',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <strong style={{ fontSize: '11.5px', color: isOnline ? '#183a31' : '#9a3937' }}>{b.title}</strong>
                            <span style={{ fontSize: '9.5px', fontWeight: 800, color: isOnline ? '#267154' : '#9a3937' }}>
                              ● {isOnline ? `ONLINE · ${st.ms}` : 'CAÍDA / OFFLINE'}
                            </span>
                          </div>
                          <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#782c3e', fontFamily: 'monospace', marginTop: '2px' }}>{b.sub}</div>
                          <div style={{ fontSize: '10px', color: '#787970', marginTop: '3px' }}>{b.desc}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* NUBE: NODO CUENCA & LOJA (1 Cloud DB) */}
                <div style={{ background: '#ffffff', border: '1.5px solid #a96b16', borderRadius: '10px', padding: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <strong style={{ fontSize: '12px', color: '#a96b16' }}>
                      ☁️ NODO NUBE (SUPABASE DBaaS · AWS us-east-1) — SEDE CUENCA & LOJA (BD 6)
                    </strong>
                    <span className="badge badge-ABI">Destilerías del Sur (Zhumir/Cristal)</span>
                  </div>
                  <div
                    onClick={() => handleSelectNodeForDba('cuenca-cloud')}
                    style={{ border: '1px solid #e9e6de', borderRadius: '8px', padding: '9px', background: '#faf9f6', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  >
                    <div>
                      <strong style={{ fontSize: '11.5px', color: '#183a31' }}>BD 6 · PostgreSQL 18 Cloud DBaaS (:5432 `cloud_cuenca_loja`)</strong>
                      <div style={{ fontSize: '10px', color: '#787970', marginTop: '2px' }}>
                        Certificado TLS `prod-ca-2021.crt` · Pooler `aws-0-us-east-1.pooler.supabase.com:5432` · Medición de Latencia WAN
                      </div>
                    </div>
                    <span style={{ fontSize: '10px', fontWeight: 700, color: '#267154', whiteSpace: 'nowrap' }}>
                      ● {getNodeBadge('CUENCA').ms}
                    </span>
                  </div>
                </div>
              </div>

              {/* ==================== LADO DERECHO: ARQUITECTURA DE SISTEMAS DE INFORMACIÓN (SI) ==================== */}
              <div
                style={{
                  border: '2px solid #782c3e',
                  borderRadius: '14px',
                  background: '#faf9f6',
                  padding: '18px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #782c3e', paddingBottom: '10px' }}>
                  <div>
                    <span style={{ fontSize: '10px', fontWeight: 800, letterSpacing: '.14em', color: '#183a31' }}>
                      LADO DERECHO DE LA PIZARRA · ROL: ARQUITECTO SI (`admin`)
                    </span>
                    <h3 style={{ margin: '2px 0 0', fontSize: '18px', fontFamily: "'Playfair Display', Georgia, serif", color: '#782c3e' }}>
                      2. Arquitectura de Sistemas de Información (3 Capas + Docker)
                    </h3>
                  </div>
                  <span style={{ background: '#782c3e', color: '#fff', padding: '4px 10px', borderRadius: '20px', fontSize: '10.5px', fontWeight: 700 }}>
                    3 Réplicas API · 6 Agentes IA
                  </span>
                </div>

                {/* CAPA 1: PRESENTACIÓN + AGENTES IA + POWER BI */}
                <div style={{ background: '#ffffff', border: '1px solid #d9d4c7', borderRadius: '10px', padding: '12px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 800, color: '#782c3e', marginBottom: '8px' }}>
                    CAPA 1: PRESENTACIÓN, ANALÍTICA BI & 6 AGENTES IA AUTÓNOMOS (CADA 60s)
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
                    <div style={{ border: '1px solid #e9e6de', borderRadius: '8px', padding: '8px', background: '#faf9f6' }}>
                      <strong style={{ fontSize: '11px', color: '#183a31' }}>🌐 Frontend GitHub Pages</strong>
                      <div style={{ fontSize: '9.5px', color: '#787970', marginTop: '3px' }}>
                        `jjamesrxzn7.github.io/licoreria` · React 18 + TS · Login con 17 Usuarios RBAC.
                      </div>
                    </div>
                    <div style={{ border: '1px solid #e9e6de', borderRadius: '8px', padding: '8px', background: '#faf9f6' }}>
                      <strong style={{ fontSize: '11px', color: '#782c3e' }}>🤖 6 Agentes IA Python</strong>
                      <div style={{ fontSize: '9.5px', color: '#787970', marginTop: '3px' }}>
                        3 en Quito (`agentes_quito.py`) + 3 en Laptop (`agentes_gye_cuenca.py`) con Header `X-Sede`.
                      </div>
                    </div>
                    <div style={{ border: '1px solid #e9e6de', borderRadius: '8px', padding: '8px', background: '#faf9f6' }}>
                      <strong style={{ fontSize: '11px', color: '#a96b16' }}>📊 Power BI Desktop</strong>
                      <div style={{ fontSize: '9.5px', color: '#787970', marginTop: '3px' }}>
                        Conectado a BD 5 Estrella (`:3309`), BD 6 Supabase (`:5432`) y `/api/dba/global`.
                      </div>
                    </div>
                  </div>
                </div>

                {/* CAPA 2: CONTENEDOR DOCKER + NGINX LOAD BALANCER + 3 RÉPLICAS API (SCALE-OUT) */}
                <div style={{ background: '#ffffff', border: '1.5px dashed #183a31', borderRadius: '10px', padding: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <strong style={{ fontSize: '11.5px', color: '#183a31' }}>
                      🐳 CONTENEDOR DOCKER (`docker-compose.app.yml`) — CAPA DE LÓGICA DE NEGOCIO (SCALE-OUT)
                    </strong>
                    <span className="badge badge-APR">Round-Robin :8000 / :8080</span>
                  </div>

                  {/* NGINX LB */}
                  <div style={{ background: '#183a31', color: '#f9f7f0', borderRadius: '8px', padding: '9px 12px', marginBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <strong style={{ fontSize: '11.5px' }}>⚖️ Balanceador de Carga `nginx_lb` (`nginx.conf` / `load_balancer_8080.py`)</strong>
                      <div style={{ fontSize: '10px', color: '#c0cec2' }}>
                        Recibe peticiones HTTP en `100.123.81.4:8000/api`, lee Header `X-Sede` y reparte en Round-Robin:
                      </div>
                    </div>
                    <code style={{ background: '#782c3e', color: '#fff', padding: '3px 8px', borderRadius: '5px', fontSize: '10px' }}>
                      Activa: {globalData?.apiReplica || topology?.apiReplica || 'api_lacava_1'}
                    </code>
                  </div>

                  {/* 3 RÉPLICAS DE LA API */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
                    {[
                      { name: 'api_lacava_1', port: ':8001', desc: 'Réplica FastAPI #1 + Pool 6 BDs + 2PC' },
                      { name: 'api_lacava_2', port: ':8002', desc: 'Réplica FastAPI #2 + Pool 6 BDs + 2PC' },
                      { name: 'api_lacava_3', port: ':8003', desc: 'Réplica FastAPI #3 + Pool 6 BDs + 2PC' },
                    ].map(rep => {
                      const isCurrent = (globalData?.apiReplica || topology?.apiReplica) === rep.name;
                      return (
                        <div
                          key={rep.name}
                          style={{
                            border: isCurrent ? '2px solid #782c3e' : '1px solid #e9e6de',
                            borderRadius: '8px',
                            padding: '8px',
                            background: isCurrent ? '#fbf3f0' : '#faf9f6',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <strong style={{ fontSize: '11px', color: '#183a31' }}>{rep.name}</strong>
                            <code style={{ fontSize: '10px', color: '#782c3e', fontWeight: 700 }}>{rep.port}</code>
                          </div>
                          <div style={{ fontSize: '9.5px', color: '#787970', marginTop: '3px' }}>{rep.desc}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* CAPA 3: MALLA VPN TAILSCALE + ENRUTAMIENTO X-SEDE + ESCALABILIDAD */}
                <div style={{ background: '#ffffff', border: '1px solid #d9d4c7', borderRadius: '10px', padding: '12px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 800, color: '#183a31', marginBottom: '6px' }}>
                    🔗 MALLA VPN TAILSCALE & SIMULADOR DE ESCALABILIDAD (15 → 1000 USUARIOS)
                  </div>
                  <div style={{ fontSize: '11px', color: '#575950', marginBottom: '10px', fontFamily: 'monospace', background: '#faf9f6', padding: '7px 10px', borderRadius: '6px', border: '1px solid #e9e6de' }}>
                    IP_TS_QUITO = <strong>100.77.220.102</strong> (:3307, :27017, :3308) ◄── WireGuard 7ms ──► IP_TS_GUAYAQUIL = <strong>100.123.81.4</strong> (:3306, :3309, :8000)
                  </div>

                  <label style={{ fontWeight: 700, fontSize: '11.5px', display: 'block', marginBottom: '6px', color: '#25251f' }}>
                    Usuarios Concurrentes en el SI:{' '}
                    <span style={{ color: '#782c3e', fontSize: '13px' }}>{simulatedUsers} usuarios</span>
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
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', marginTop: '8px' }}>
                    <div style={{ background: '#faf9f6', padding: '7px', borderRadius: '6px', border: '1px solid #e9e6de', textAlign: 'center' }}>
                      <div style={{ fontSize: '9px', color: '#787970', fontWeight: 700 }}>TX / SEGUNDO</div>
                      <strong style={{ fontSize: '14px', color: '#183a31' }}>{tps} /s</strong>
                    </div>
                    <div style={{ background: '#faf9f6', padding: '7px', borderRadius: '6px', border: '1px solid #e9e6de', textAlign: 'center' }}>
                      <div style={{ fontSize: '9px', color: '#787970', fontWeight: 700 }}>TX / MINUTO</div>
                      <strong style={{ fontSize: '14px', color: '#782c3e' }}>{(tps * 60).toLocaleString()} /m</strong>
                    </div>
                    <div style={{ background: '#faf9f6', padding: '7px', borderRadius: '6px', border: '1px solid #e9e6de', textAlign: 'center' }}>
                      <div style={{ fontSize: '9px', color: '#787970', fontWeight: 700 }}>TX / HORA</div>
                      <strong style={{ fontSize: '14px', color: '#183a31' }}>{(tps * 3600).toLocaleString()} /h</strong>
                    </div>
                    <div style={{ background: '#faf9f6', padding: '7px', borderRadius: '6px', border: '1px solid #e9e6de', textAlign: 'center' }}>
                      <div style={{ fontSize: '9px', color: '#787970', fontWeight: 700 }}>TX / DÍA</div>
                      <strong style={{ fontSize: '14px', color: '#a96b16' }}>{(tps * 28800).toLocaleString()} /d</strong>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      )}

      {/* ==================== TAB 2: CONSOLA GLOBAL DEL DBA (TAREA 2.2 Y 2.3) ==================== */}
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
                {isStrictDba ? (
                  <span className="badge badge-APR" style={{ gap: '5px', padding: '6px 11px' }}>
                    <Lock size={12} /> MODO DBA: SOLO LECTURA (INSERT / UPDATE / DELETE BLOQUEADOS)
                  </span>
                ) : (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => void triggerAgentsRoundNow()}
                    disabled={loadingGlobal}
                  >
                    <Play size={14} />
                    Disparar Ronda de Agentes IA Ahora
                  </button>
                )}
              </div>
            </div>

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

            <div className="table-scroll" style={{ maxHeight: '440px' }}>
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Origen Nodo (`origen_nodo`)</th>
                    <th>Header `X-Sede`</th>
                    <th>Módulo</th>
                    <th>Usuario RBAC</th>
                    <th>Rol RBAC</th>
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

      {/* ==================== TAB 3: IDENTIDAD DE CADA SUCURSAL & MAPA DE 6 NODOS ==================== */}
      {activeTab === 'board' && topology && (
        <div>
          {/* IDENTIDAD DISTINTIVA POR SUCURSAL */}
          <section className="card">
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Layers size={18} color="#782c3e" />
                  Identidad Característica por Sucursal Regional (Quito · Guayaquil · Cuenca/Loja)
                </h2>
                <p>
                  Cada sucursal opera sobre su propia máquina/infraestructura, con su catálogo emblemático y sus agentes autónomos asignados.
                </p>
              </div>
              <span className="demo-badge">AUTONOMÍA LOCAL POR SEDE</span>
            </div>

            <div className="grid-3">
              {BRANCH_IDENTITIES.map(b => (
                <div
                  key={b.code}
                  style={{
                    border: '1px solid #e9e6de',
                    borderTop: `4px solid ${b.accent}`,
                    borderRadius: '10px',
                    padding: '15px',
                    background: '#faf9f6',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <span style={{ background: b.bg, color: b.accent, fontWeight: 800, fontSize: '11px', padding: '3px 9px', borderRadius: '6px' }}>
                      Sede [{b.code}]
                    </span>
                    <code style={{ fontSize: '10.5px', color: '#575950' }}>{b.machine}</code>
                  </div>
                  <h3 style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: '16px', margin: '6px 0 4px', color: '#25251f' }}>
                    {b.city}
                  </h3>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: b.accent, marginBottom: '6px' }}>{b.emblem}</div>
                  <p style={{ fontSize: '11.5px', color: '#575950', margin: '0 0 8px', lineHeight: 1.45 }}>{b.specialty}</p>
                  <div style={{ fontSize: '10.5px', background: '#fff', border: '1px solid #e9e6de', padding: '8px', borderRadius: '6px' }}>
                    <div><strong>Bases de Datos:</strong> {b.databases}</div>
                    <div style={{ marginTop: '4px' }}><strong>Agentes IA:</strong> {b.agents}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* 3 SEDES Y SUS 6 BASES DE DATOS */}
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
                      border: node.status === 'ONLINE' ? '1px solid #e9e6de' : '2px solid #9a3937',
                      borderRadius: '10px',
                      padding: '16px',
                      background: node.status === 'ONLINE' ? '#faf9f6' : '#fdf3f2',
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
                      {node.status === 'OFFLINE' && (
                        <div style={{ marginTop: '8px', fontSize: '11px', color: '#9a3937', background: '#f8e9e8', border: '1px solid #e2b4b1', padding: '7px 9px', borderRadius: '6px', fontWeight: 600 }}>
                          ⚠️ NODO CAÍDO / TÚNEL TAILSCALE INACCESIBLE: {node.error || 'La máquina física está apagada o en suspensión.'}
                        </div>
                      )}
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

      {/* ==================== TAB 4: PROMPT SQL / MONGODB DEL DBA + 17 USUARIOS ==================== */}
      {activeTab === 'dba_prompt' && (
        <div>
          <section className="card">
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Terminal size={19} color="#782c3e" />
                  Terminal de Diagnóstico Read-Only del DBA — Consultas Multi-Sucursal (Quito, Guayaquil y Cuenca)
                </h2>
                <p>
                  Modo seguro de <strong>SOLO LECTURA</strong>: Permite ejecutar <code>SELECT</code>, <code>SHOW</code>, <code>DESCRIBE</code>, <code>EXPLAIN</code> y <code>MONGO_COLLECTION</code> en las 6 BDs. Comandos <code>INSERT</code>, <code>UPDATE</code>, <code>DELETE</code> y <code>DROP</code> están bloqueados.
                </p>
              </div>
              <span className="badge badge-APR" style={{ gap: '5px', padding: '6px 11px' }}>
                <Lock size={12} /> READ-ONLY TERMINAL
              </span>
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
              <button
                type="button"
                onClick={() => {
                  const fedSql = "-- GLOBAL (Consulta Federada Read-Only de las 3 Sucursales: Quito + Guayaquil + Cuenca)\nSELECT id, origen_nodo, sede, modulo, usuario_rbac, rol_rbac, detalle, monto_usd, fecha_hora FROM vista_global_6_bds;";
                  setSelectedNodeId('global-federated');
                  setSqlText(fedSql);
                  void runDbaQuery('global-federated', fedSql);
                }}
                className="btn"
                style={{
                  background: selectedNodeId === 'global-federated' ? '#782c3e' : '#fbf3f0',
                  color: selectedNodeId === 'global-federated' ? '#ffffff' : '#782c3e',
                  border: '1px solid #ead6cf',
                }}
              >
                <Network size={13} />
                Consultar las 3 Sucursales Unidas (Quito + Guayaquil + Cuenca)
              </button>
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

      {/* ==================== TAB 5: SIMULADOR 2PC (PREGUNTAS 4 Y 5) ==================== */}
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
    </div>
  );
};

export default ArchitectureConsole;
