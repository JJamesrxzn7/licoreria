import React, { useEffect, useState, useCallback } from 'react';
import {
  Server, Database, Terminal, Play, RefreshCw, ShieldCheck, AlertTriangle,
  Layers, Cloud, Activity, CheckCircle2, XCircle, HardDrive, Network,
  Filter, GitCompare, Lock, Bot, Globe, Cpu, BarChart3
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

type InteractiveElementId =
  | 'quito-sql'
  | 'quito-nosql'
  | 'quito-otras'
  | 'guayaquil-sql'
  | 'guayaquil-replica'
  | 'cuenca-cloud'
  | 'api-gateway'
  | 'gui-frontend'
  | 'agentes-quito'
  | 'agentes-gye'
  | 'power-bi';

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

  // Elemento interactivo seleccionado en el Diagrama Visual
  const [focusedElement, setFocusedElement] = useState<InteractiveElementId>('cuenca-cloud');

  // Consola Global del DBA (GET /api/dba/global)
  const [globalData, setGlobalData] = useState<GlobalDbaResponse | null>(null);
  const [filterSede, setFilterSede] = useState<string>('TODAS');
  const [filterModulo, setFilterModulo] = useState<string>('TODOS');
  const [loadingGlobal, setLoadingGlobal] = useState<boolean>(false);

  // Prompt SQL DBA state
  const [selectedNodeId, setSelectedNodeId] = useState<string>('cuenca-cloud');
  const [sqlText, setSqlText] = useState<string>(
    "SELECT id_op, sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, latencia_wan_ms, fecha_hora FROM operaciones_agentes_cloud ORDER BY id_op DESC LIMIT 15;"
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

  const runDbaQuery = useCallback(async (overrideNodeId?: string, overrideSql?: string) => {
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
  }, [selectedNodeId, sqlText, fetchNodeLogs]);

  useEffect(() => {
    void fetchTopology();
    void fetchGlobalDbaConsole('TODAS', 'TODOS');
    void runDbaQuery('cuenca-cloud', "SELECT id_op, sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, latencia_wan_ms, fecha_hora FROM operaciones_agentes_cloud ORDER BY id_op DESC LIMIT 10;");
  }, [fetchTopology, fetchGlobalDbaConsole, runDbaQuery]);

  useEffect(() => {
    if (selectedNodeId && selectedNodeId !== 'global-federated') {
      void fetchNodeLogs(selectedNodeId);
    }
  }, [selectedNodeId, fetchNodeLogs]);

  const handleClickDiagramNode = (elemId: InteractiveElementId) => {
    setFocusedElement(elemId);
    const dbIds: InteractiveElementId[] = ['quito-sql', 'quito-nosql', 'quito-otras', 'guayaquil-sql', 'guayaquil-replica', 'cuenca-cloud'];
    if (dbIds.includes(elemId)) {
      setSelectedNodeId(elemId);
      const nodeObj = topology?.nodes.find(n => n.id === elemId);
      if (nodeObj && nodeObj.presets.length > 0) {
        setSqlText(nodeObj.presets[0].sql);
        void runDbaQuery(elemId, nodeObj.presets[0].sql);
      } else {
        void fetchNodeLogs(elemId);
      }
    }
  };

  const handleSelectNodeForDba = (nodeId: string, defaultSql?: string) => {
    setSelectedNodeId(nodeId);
    const nodeObj = topology?.nodes.find(n => n.id === nodeId);
    if (defaultSql) {
      setSqlText(defaultSql);
    } else if (nodeObj && nodeObj.presets.length > 0) {
      setSqlText(nodeObj.presets[0].sql);
    }
    setActiveTab('dba_prompt');
    void runDbaQuery(nodeId, defaultSql || nodeObj?.presets[0]?.sql);
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
  const focusedDbNode = topology?.nodes.find(n => n.id === focusedElement);

  const findNode = (id: string) => topology?.nodes.find(n => n.id === id);

  // Renderizador de cada cajita "BD" del boceto del usuario
  const renderDbSquare = (nodeId: InteractiveElementId, shortCode: string, subtitle: string) => {
    const n = findNode(nodeId);
    const isOnline = !n || n.status === 'ONLINE';
    const isFocused = focusedElement === nodeId;
    return (
      <button
        key={nodeId}
        type="button"
        onClick={() => handleClickDiagramNode(nodeId)}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '4px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          padding: '4px',
          transition: 'transform 0.15s ease',
          transform: isFocused ? 'scale(1.06)' : 'scale(1)',
        }}
      >
        <div
          style={{
            width: '86px',
            height: '82px',
            borderRadius: '16px',
            border: isFocused
              ? '3px solid #782c3e'
              : isOnline
              ? '2.5px solid #183a31'
              : '2.5px solid #9a3937',
            background: isFocused
              ? '#fbf3f0'
              : isOnline
              ? '#ffffff'
              : '#f8e9e8',
            boxShadow: isFocused
              ? '0 8px 22px rgba(120,44,62,0.22)'
              : '0 4px 12px rgba(24,58,49,0.08)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
          }}
        >
          {/* Punto de estado en vivo */}
          <span
            style={{
              position: 'absolute',
              top: '7px',
              right: '7px',
              width: '9px',
              height: '9px',
              borderRadius: '50%',
              background: isOnline ? '#267154' : '#9a3937',
              boxShadow: isOnline ? '0 0 0 3px rgba(38,113,84,0.2)' : '0 0 0 3px rgba(154,57,55,0.2)',
            }}
          />
          <Database size={22} color={isFocused ? '#782c3e' : isOnline ? '#183a31' : '#9a3937'} />
          <strong style={{ fontSize: '11px', color: '#25251f', marginTop: '3px' }}>{shortCode}</strong>
          <code style={{ fontSize: '9.5px', color: '#782c3e', fontWeight: 700 }}>
            :{n?.actualPort || subtitle}
          </code>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: "'Playfair Display', Georgia, serif", fontWeight: 700, fontSize: '13px', color: '#25251f' }}>
            BD ({shortCode})
          </div>
          <div style={{ fontSize: '9.5px', color: isOnline ? '#267154' : '#9a3937', fontWeight: 700 }}>
            {isOnline ? `${n?.latencyMs ?? 12} ms` : 'OFFLINE'}
          </div>
        </div>
      </button>
    );
  };

  return (
    <div>
      {/* ENCABEZADO CON LA ESTÉTICA DE LA CAVA */}
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            TOPOLOGÍA INTERACTIVA EN VIVO · TÚNEL VPN TAILSCALE · 3 RÉPLICAS API ({globalData?.apiReplica || topology?.apiReplica || 'api_lacava_1'})
          </span>
          <h1>Mapa Visual del Clúster Híbrido "La Cava"</h1>
          <p>
            Haz clic en cualquiera de las <strong>6 Bases de Datos (BD)</strong>, en los <strong>Agentes IA</strong>, en el <strong>API Gateway</strong> o en la <strong>GUI</strong> del diagrama para inspeccionar su flujo, tablas y consultas en vivo.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span className="demo-badge">
            {topology ? `${topology.onlineNodes}/${topology.totalNodes} BDs CONECTADAS POR TAILSCALE` : 'CONECTANDO...'}
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
          { id: 'diagram_vs', label: '1. Diagrama Interactivo en Vivo (6 BDs + Túnel Tailscale + Agentes + API + GUI)', icon: GitCompare, show: true },
          { id: 'dba_prompt', label: '2. Terminal Read-Only del DBA (Consultas para las 3 Sucursales / 6 BDs)', icon: Terminal, show: true },
          { id: 'global_dba', label: '3. Monitor Global Unificado (6 BDs en Paralelo · Solo Lectura)', icon: Filter, show: true },
          { id: 'board', label: '4. Identidad por Sucursal & Tarjetas de Nodos', icon: Network, show: true },
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

      {/* ==================== TAB 1: DIAGRAMA VISUAL INTERACTIVO (EXACTAMENTE COMO EL BOCETO) ==================== */}
      {activeTab === 'diagram_vs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <section className="card" style={{ padding: '22px', position: 'relative', overflow: 'hidden' }}>
            <div className="section-heading" style={{ marginBottom: '12px' }}>
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '18px' }}>
                  <Network size={20} color="#782c3e" />
                  Arquitectura en Vivo: Quito (3 BDs) · Guayaquil (2 BDs) · Cuenca (1 BD) ↔ Túnel Tailscale ↔ API ↔ GUI
                </h2>
                <p>
                  <strong>Interactivo:</strong> Haz clic sobre cualquier bloque (<strong>BD 1..6</strong>, <strong>Agentes IA</strong>, <strong>API</strong> o <strong>GUI</strong>) para abrir abajo su inspector en vivo con todos sus datos, logs y terminal Read-Only.
                </p>
              </div>
              <span className="demo-badge">HAZ CLIC EN CUALQUIER NODO DEL DIAGRAMA</span>
            </div>

            {/* ==================== LIENZO GRÁFICO CON LÍNEAS SVG DEL TÚNEL TAILSCALE ==================== */}
            <div
              style={{
                position: 'relative',
                width: '100%',
                minHeight: '590px',
                background: 'radial-gradient(circle at 50% 52%, #ffffff 0%, #f6f4ef 100%)',
                border: '1.5px solid #dfded7',
                borderRadius: '16px',
                padding: '18px',
                overflowX: 'auto',
              }}
            >
              <div style={{ position: 'relative', minWidth: '940px', height: '550px', margin: '0 auto' }}>
                {/* LÍNEAS DE CONEXIÓN SVG (TÚNEL TAILSCALE WIREGUARD + ENRUTAMIENTO X-SEDE) */}
                <svg
                  viewBox="0 0 1000 550"
                  style={{
                    position: 'absolute',
                    inset: 0,
                    width: '100%',
                    height: '100%',
                    pointerEvents: 'none',
                    zIndex: 1,
                  }}
                >
                  <defs>
                    <marker id="arrow-wine" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                      <path d="M0,0 L8,4 L0,8 Z" fill="#782c3e" />
                    </marker>
                    <marker id="arrow-green" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                      <path d="M0,0 L8,4 L0,8 Z" fill="#183a31" />
                    </marker>
                    <marker id="arrow-gold" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                      <path d="M0,0 L8,4 L0,8 Z" fill="#a96b16" />
                    </marker>
                  </defs>

                  {/* Halo del Túnel Tailscale */}
                  <ellipse cx="500" cy="310" rx="235" ry="62" fill="rgba(24,58,49,0.04)" stroke="#cbd5cb" strokeDasharray="6 4" strokeWidth="1.5" />
                  <text x="500" y="259" textAnchor="middle" fill="#183a31" fontSize="10" fontWeight="800" letterSpacing="1.5">
                    🔒 MALLA VPN TAILSCALE (100.77.220.102 ◄── WireGuard 7ms ──► 100.123.81.4)
                  </text>

                  {/* Línea: Quito (3 BDs a la izquierda) <---> API Central */}
                  <path
                    d="M 315 235 C 375 260, 400 310, 415 340"
                    fill="none"
                    stroke="#782c3e"
                    strokeWidth="2.8"
                    strokeDasharray="7 4"
                    markerEnd="url(#arrow-wine)"
                  />
                  <rect x="295" y="274" width="138" height="20" rx="10" fill="#fbf3f0" stroke="#ead6cf" />
                  <text x="364" y="287" textAnchor="middle" fill="#782c3e" fontSize="9.5" fontWeight="700">
                    Tailscale :3307/:27017/:3308
                  </text>

                  {/* Línea: Agentes Quito ---> API Central */}
                  <path
                    d="M 225 365 C 310 380, 360 365, 412 355"
                    fill="none"
                    stroke="#782c3e"
                    strokeWidth="2"
                    markerEnd="url(#arrow-wine)"
                  />
                  <text x="320" y="390" textAnchor="middle" fill="#782c3e" fontSize="9" fontWeight="700">
                    X-Sede: QUITO / NOSQL / PARALELA
                  </text>

                  {/* Línea: Guayaquil (2 BDs arriba) <---> API Central */}
                  <path
                    d="M 500 175 L 500 295"
                    fill="none"
                    stroke="#183a31"
                    strokeWidth="2.8"
                    strokeDasharray="7 4"
                    markerEnd="url(#arrow-green)"
                  />
                  <rect x="424" y="212" width="152" height="20" rx="10" fill="#eff5f1" stroke="#cde0d3" />
                  <text x="500" y="225" textAnchor="middle" fill="#183a31" fontSize="9.5" fontWeight="700">
                    Tailscale 100.123.81.4 (:3306/:3309)
                  </text>

                  {/* Línea: Cuenca (1 BD a la derecha) <---> API Central */}
                  <path
                    d="M 760 250 C 690 280, 635 315, 588 340"
                    fill="none"
                    stroke="#a96b16"
                    strokeWidth="2.8"
                    strokeDasharray="7 4"
                    markerEnd="url(#arrow-gold)"
                  />
                  <rect x="615" y="274" width="142" height="20" rx="10" fill="#fbf4e6" stroke="#ead8b8" />
                  <text x="686" y="287" textAnchor="middle" fill="#a96b16" fontSize="9.5" fontWeight="700">
                    TLS WAN Supabase :5432
                  </text>

                  {/* Línea: Agentes Guayaquil/Cuenca ---> API Central */}
                  <path
                    d="M 765 375 C 690 385, 640 370, 588 358"
                    fill="none"
                    stroke="#183a31"
                    strokeWidth="2"
                    markerEnd="url(#arrow-green)"
                  />
                  <text x="685" y="394" textAnchor="middle" fill="#183a31" fontSize="9" fontWeight="700">
                    X-Sede: GUAYAQUIL / DWH / CUENCA
                  </text>

                  {/* Línea: API Central <---> GUI (Abajo) */}
                  <path
                    d="M 500 402 L 500 456"
                    fill="none"
                    stroke="#183a31"
                    strokeWidth="3"
                    markerEnd="url(#arrow-green)"
                  />
                  <text x="568" y="435" textAnchor="middle" fill="#575950" fontSize="9.5" fontWeight="700">
                    HTTPS / CORS JSON
                  </text>
                </svg>

                {/* ==================== 1. GRUPO IZQUIERDO: QUITO (3 BDs + 3 AGENTES IA EN PC ESCRITORIO) ==================== */}
                <div
                  style={{
                    position: 'absolute',
                    left: '14px',
                    top: '95px',
                    width: '310px',
                    zIndex: 2,
                    background: 'rgba(255,255,255,0.94)',
                    border: '2px solid #782c3e',
                    borderRadius: '14px',
                    padding: '12px',
                    boxShadow: '0 8px 24px rgba(120,44,62,0.08)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '10px', fontWeight: 800, color: '#782c3e', letterSpacing: '.08em' }}>
                      🖥️ PC ESCRITORIO (`JERXMY-01`)
                    </span>
                    <code style={{ fontSize: '10px', background: '#fbf3f0', color: '#782c3e', padding: '2px 6px', borderRadius: '6px', fontWeight: 700 }}>
                      100.77.220.102
                    </code>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: '13px', color: '#25251f', marginBottom: '10px', fontFamily: "'Playfair Display', Georgia, serif" }}>
                    Sede Quito — 3 Bases de Datos
                  </div>

                  {/* LAS 3 CAJITAS BD DE LA IZQUIERDA (COMO EN EL DIBUJO) */}
                  <div style={{ display: 'flex', justifyContent: 'space-around', alignItems: 'flex-start' }}>
                    {renderDbSquare('quito-sql', 'BD 1 SQL', '3307')}
                    {renderDbSquare('quito-nosql', 'BD 2 NoSQL', '27017')}
                    {renderDbSquare('quito-otras', 'BD 3 Hash', '3308')}
                  </div>

                  {/* REFERENCIA DEL AGENTE AL LADO EN LA MISMA MÁQUINA DE ESCRITORIO */}
                  <button
                    type="button"
                    onClick={() => handleClickDiagramNode('agentes-quito')}
                    style={{
                      marginTop: '10px',
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '10px',
                      border: focusedElement === 'agentes-quito' ? '2px solid #782c3e' : '1px dashed #782c3e',
                      background: focusedElement === 'agentes-quito' ? '#fbf3f0' : '#faf9f6',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '7px', textAlign: 'left' }}>
                      <Bot size={17} color="#782c3e" />
                      <div>
                        <strong style={{ fontSize: '11px', color: '#782c3e', display: 'block' }}>
                          3 Agentes IA Quito (`agentes_quito.py`)
                        </strong>
                        <span style={{ fontSize: '9.5px', color: '#787970' }}>
                          Agente 1 (OLTP) · Agente 2 (Mongo) · Agente 3 (Hash)
                        </span>
                      </div>
                    </div>
                    <span className="badge badge-APR" style={{ fontSize: '8.5px' }}>ACTIVOS 60s</span>
                  </button>
                </div>

                {/* ==================== 2. GRUPO SUPERIOR CENTRAL: GUAYAQUIL (2 BDs EN LAPTOP) ==================== */}
                <div
                  style={{
                    position: 'absolute',
                    left: '375px',
                    top: '8px',
                    width: '250px',
                    zIndex: 2,
                    background: 'rgba(255,255,255,0.94)',
                    border: '2px solid #183a31',
                    borderRadius: '14px',
                    padding: '10px 12px',
                    boxShadow: '0 8px 24px rgba(24,58,49,0.08)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span style={{ fontSize: '9.5px', fontWeight: 800, color: '#183a31', letterSpacing: '.06em' }}>
                      💻 LAPTOP (`DESKTOP-6JDT8Q0`)
                    </span>
                    <code style={{ fontSize: '9.5px', background: '#eff5f1', color: '#183a31', padding: '2px 6px', borderRadius: '6px', fontWeight: 700 }}>
                      100.123.81.4
                    </code>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: '12.5px', color: '#25251f', marginBottom: '6px', textAlign: 'center', fontFamily: "'Playfair Display', Georgia, serif" }}>
                    Sede Guayaquil — 2 BDs
                  </div>

                  {/* LAS 2 CAJITAS BD DE ARRIBA (COMO EN EL DIBUJO) */}
                  <div style={{ display: 'flex', justifyContent: 'center', gap: '18px' }}>
                    {renderDbSquare('guayaquil-sql', 'BD 4 OLTP', '3306')}
                    {renderDbSquare('guayaquil-replica', 'BD 5 DWH', '3309')}
                  </div>
                </div>

                {/* ==================== 3. GRUPO DERECHO: CUENCA (1 BD SOLA EN LA NUBE + AGENTES LAPTOP/BI) ==================== */}
                <div
                  style={{
                    position: 'absolute',
                    right: '18px',
                    top: '110px',
                    width: '255px',
                    zIndex: 2,
                    background: 'rgba(255,255,255,0.94)',
                    border: '2px solid #a96b16',
                    borderRadius: '14px',
                    padding: '12px',
                    boxShadow: '0 8px 24px rgba(169,107,22,0.08)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                  }}
                >
                  <div style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <span style={{ fontSize: '10px', fontWeight: 800, color: '#a96b16' }}>
                      ☁️ NUBE SUPABASE DBaaS
                    </span>
                    <code style={{ fontSize: '9.5px', background: '#fbf4e6', color: '#a96b16', padding: '2px 6px', borderRadius: '6px', fontWeight: 700 }}>
                      us-east-1
                    </code>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: '13px', color: '#25251f', marginBottom: '8px', fontFamily: "'Playfair Display', Georgia, serif" }}>
                    Sede Cuenca & Loja — 1 BD Cloud
                  </div>

                  {/* LA CAJITA BD SOLA A LA DERECHA (COMO EN EL DIBUJO) */}
                  {renderDbSquare('cuenca-cloud', 'BD 6 Cloud', '5432')}

                  {/* REFERENCIA DE AGENTES GUAYAQUIL/CUENCA Y POWER BI */}
                  <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px' }}>
                    <button
                      type="button"
                      onClick={() => handleClickDiagramNode('agentes-gye')}
                      style={{
                        width: '100%',
                        padding: '7px 9px',
                        borderRadius: '9px',
                        border: focusedElement === 'agentes-gye' ? '2px solid #183a31' : '1px dashed #183a31',
                        background: focusedElement === 'agentes-gye' ? '#eff5f1' : '#faf9f6',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', textAlign: 'left' }}>
                        <Bot size={15} color="#183a31" />
                        <div>
                          <strong style={{ fontSize: '10.5px', color: '#183a31', display: 'block' }}>
                            3 Agentes Laptop (`agentes_gye_cuenca.py`)
                          </strong>
                          <span style={{ fontSize: '9px', color: '#787970' }}>
                            Agente 4 (GYE) · Agente 5 (ETL) · Agente 6 (Cuenca)
                          </span>
                        </div>
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleClickDiagramNode('power-bi')}
                      style={{
                        width: '100%',
                        padding: '6px 9px',
                        borderRadius: '9px',
                        border: focusedElement === 'power-bi' ? '2px solid #a96b16' : '1px solid #ead8b8',
                        background: focusedElement === 'power-bi' ? '#fbf4e6' : '#ffffff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        cursor: 'pointer',
                      }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '10.5px', fontWeight: 700, color: '#a96b16' }}>
                        <BarChart3 size={14} /> Power BI Desktop (OLAP :3309 & :5432)
                      </span>
                      <span style={{ fontSize: '9px', color: '#787970' }}>Ver conexión</span>
                    </button>
                  </div>
                </div>

                {/* ==================== 4. BLOQUE CENTRAL: API (NGINX LB + 3 RÉPLICAS) ==================== */}
                <button
                  type="button"
                  onClick={() => handleClickDiagramNode('api-gateway')}
                  style={{
                    position: 'absolute',
                    left: '412px',
                    top: '296px',
                    width: '176px',
                    height: '104px',
                    zIndex: 3,
                    borderRadius: '20px',
                    border: focusedElement === 'api-gateway' ? '3px solid #782c3e' : '2.5px solid #183a31',
                    background: focusedElement === 'api-gateway' ? '#183a31' : '#ffffff',
                    color: focusedElement === 'api-gateway' ? '#ffffff' : '#25251f',
                    boxShadow: '0 12px 28px rgba(24,58,49,0.16)',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '10px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Cpu size={20} color={focusedElement === 'api-gateway' ? '#e7c6a8' : '#782c3e'} />
                    <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: '20px', fontWeight: 700 }}>
                      API
                    </span>
                  </div>
                  <div style={{ fontSize: '10px', fontWeight: 700, marginTop: '2px', color: focusedElement === 'api-gateway' ? '#e7c6a8' : '#782c3e' }}>
                    Nginx LB :8000 / :8080
                  </div>
                  <div style={{ fontSize: '9px', marginTop: '3px', opacity: 0.9 }}>
                    3 Réplicas (`api_lacava_1..3`)
                  </div>
                  <div style={{ fontSize: '8.5px', marginTop: '2px', fontFamily: 'monospace', background: 'rgba(120,44,62,0.12)', padding: '2px 6px', borderRadius: '6px' }}>
                    Pool 6 BDs · Header X-Sede
                  </div>
                </button>

                {/* ==================== 5. BLOQUE INFERIOR: GUI (FRONTEND GITHUB PAGES) ==================== */}
                <button
                  type="button"
                  onClick={() => handleClickDiagramNode('gui-frontend')}
                  style={{
                    position: 'absolute',
                    left: '430px',
                    top: '458px',
                    width: '140px',
                    height: '72px',
                    zIndex: 3,
                    borderRadius: '16px',
                    border: focusedElement === 'gui-frontend' ? '3px solid #782c3e' : '2.5px solid #25251f',
                    background: focusedElement === 'gui-frontend' ? '#782c3e' : '#ffffff',
                    color: focusedElement === 'gui-frontend' ? '#ffffff' : '#25251f',
                    boxShadow: '0 8px 20px rgba(0,0,0,0.1)',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Globe size={17} color={focusedElement === 'gui-frontend' ? '#fff' : '#183a31'} />
                    <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: '18px', fontWeight: 700 }}>
                      GUI
                    </span>
                  </div>
                  <div style={{ fontSize: '9.5px', fontWeight: 600 }}>
                    GitHub Pages · React 18
                  </div>
                  <div style={{ fontSize: '8.5px', opacity: 0.85 }}>
                    17 Usuarios RBAC
                  </div>
                </button>
              </div>
            </div>

            {/* ==================== PANEL INSPECTOR DINÁMICO DEL ELEMENTO CLICADO EN EL DIAGRAMA ==================== */}
            <div
              style={{
                marginTop: '18px',
                border: '2px solid #183a31',
                borderRadius: '14px',
                background: '#faf9f6',
                padding: '18px 20px',
              }}
            >
              {/* CASO A: EL USUARIO HIZO CLIC EN UNA DE LAS 6 BASES DE DATOS (EJ. BD 6 CUENCA SOLA A LA DERECHA) */}
              {focusedDbNode && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', borderBottom: '1px solid #e9e6de', paddingBottom: '12px', marginBottom: '14px' }}>
                    <div>
                      <span style={{ fontSize: '10px', fontWeight: 800, color: '#782c3e', letterSpacing: '.12em' }}>
                        INSPECTOR EN VIVO DE BASE DE DATOS SELECCIONADA EN EL DIAGRAMA
                      </span>
                      <h3 style={{ margin: '3px 0 0', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                        {focusedDbNode.name} — <code>{focusedDbNode.activeHost || focusedDbNode.host}:{focusedDbNode.actualPort}</code>
                      </h3>
                      <p style={{ margin: '3px 0 0', fontSize: '12px', color: '#575950' }}>
                        <strong>Propósito Arquitectónico:</strong> {focusedDbNode.role}
                      </p>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <span className={`badge ${focusedDbNode.status === 'ONLINE' ? 'badge-APR' : 'badge-ERR'}`} style={{ fontSize: '11px', padding: '6px 12px' }}>
                        {focusedDbNode.status} · Ping: {focusedDbNode.latencyMs} ms
                      </span>
                      <span className="demo-badge">Header X-Sede: {focusedDbNode.xSede}</span>
                    </div>
                  </div>

                  {/* FICHA TÉCNICA COMPLETA DE LA BD SELECCIONADA */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(175px, 1fr))', gap: '10px', marginBottom: '14px' }}>
                    <div style={{ background: '#fff', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e9e6de' }}>
                      <small style={{ color: '#787970', display: 'block', fontSize: '10px' }}>MOTOR DE BASE DE DATOS</small>
                      <strong style={{ fontSize: '12.5px', color: '#183a31' }}>{focusedDbNode.engine}</strong>
                    </div>
                    <div style={{ background: '#fff', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e9e6de' }}>
                      <small style={{ color: '#787970', display: 'block', fontSize: '10px' }}>MÁQUINA FÍSICA / IP TAILSCALE</small>
                      <strong style={{ fontSize: '12.5px', color: '#782c3e' }}>{focusedDbNode.machine}</strong>
                    </div>
                    <div style={{ background: '#fff', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e9e6de' }}>
                      <small style={{ color: '#787970', display: 'block', fontSize: '10px' }}>ESQUEMA / BASE & PUERTO TCP</small>
                      <strong style={{ fontSize: '12.5px', fontFamily: 'monospace' }}>{focusedDbNode.database} (:{focusedDbNode.actualPort})</strong>
                    </div>
                    <div style={{ background: '#fff', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e9e6de' }}>
                      <small style={{ color: '#787970', display: 'block', fontSize: '10px' }}>TABLAS / COLECCIONES & TAMAÑO</small>
                      <strong style={{ fontSize: '12.5px' }}>{focusedDbNode.tablesCount} objetos · {focusedDbNode.sizeKb} KB</strong>
                    </div>
                  </div>

                  {/* CONSULTAS RÁPIDAS Y TERMINAL READ-ONLY EMBEBIDA PARA ESTE NODO */}
                  <div style={{ background: '#ffffff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '14px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px', marginBottom: '10px' }}>
                      <strong style={{ fontSize: '12.5px', color: '#183a31', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Terminal size={15} color="#782c3e" />
                        Consultas en Vivo sobre {focusedDbNode.shortName} (Solo Lectura / Read-Only):
                      </strong>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {focusedDbNode.presets.map((p, idx) => (
                          <button
                            key={idx}
                            type="button"
                            className="btn btn-outline"
                            onClick={() => {
                              setSqlText(p.sql);
                              void runDbaQuery(focusedDbNode.id, p.sql);
                            }}
                            style={{ padding: '5px 10px', fontSize: '11px', background: '#faf9f6' }}
                          >
                            {p.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '8px', alignItems: 'stretch', marginBottom: '10px' }}>
                      <input
                        className="input"
                        value={sqlText}
                        onChange={e => setSqlText(e.target.value)}
                        style={{ fontFamily: 'Consolas, monospace', fontSize: '12px', background: '#132a23', color: '#e8f3ec' }}
                      />
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => void runDbaQuery(focusedDbNode.id, sqlText)}
                        disabled={runningQuery}
                        style={{ whiteSpace: 'nowrap' }}
                      >
                        <Play size={14} />
                        {runningQuery ? 'Consultando...' : 'Consultar BD'}
                      </button>
                    </div>

                    {queryError && (
                      <div style={{ padding: '10px', background: '#f8e9e8', border: '1px solid #e2b4b1', borderRadius: '7px', color: '#9a3937', fontSize: '12px', marginBottom: '10px' }}>
                        <strong>Bloqueo de Seguridad DBA:</strong> {queryError}
                      </div>
                    )}

                    {queryResult && (
                      <div className="table-scroll" style={{ maxHeight: '250px', border: '1px solid #e9e6de', borderRadius: '8px' }}>
                        <table>
                          <thead>
                            <tr>
                              {queryResult.columns.map((c, i) => <th key={i}>{c}</th>)}
                            </tr>
                          </thead>
                          <tbody>
                            {queryResult.rows.slice(0, 12).map((r, ri) => (
                              <tr key={ri}>
                                {r.map((v, ci) => (
                                  <td key={ci} style={{ whiteSpace: 'normal', maxWidth: '320px' }}>
                                    {v === null ? 'NULL' : String(v)}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* CASO B: EL USUARIO HIZO CLIC EN EL BLOQUE CENTRAL "API" */}
              {focusedElement === 'api-gateway' && (
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 800, color: '#782c3e', letterSpacing: '.12em' }}>
                    INSPECTOR EN VIVO DE LA CAPA MEDIA (MIDDLEWARE & BALANCEADOR)
                  </span>
                  <h3 style={{ margin: '4px 0 8px', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                    API Gateway: Balanceador Nginx Round-Robin (:8000 / :8080) + 3 Réplicas FastAPI (`api_lacava_1..3`)
                  </h3>
                  <p style={{ fontSize: '12.5px', color: '#575950', marginBottom: '12px' }}>
                    Vive en la <strong>Laptop (`100.123.81.4`)</strong>. Recibe todas las peticiones de la <strong>GUI (GitHub Pages)</strong> y de los <strong>6 Agentes IA</strong>, inspecciona el header obligatorio <code>X-Sede</code> (<code>QUITO</code>, <code>QUITO_NOSQL</code>, <code>QUITO_PARALELA</code>, <code>GUAYAQUIL</code>, <code>GUAYAQUIL_DWH</code>, <code>CUENCA</code>) y enruta la conexión por el túnel Tailscale hacia el motor correspondiente.
                  </p>
                  <div className="grid-3">
                    {[
                      { id: 'api_lacava_1', port: '127.0.0.1:8001', role: 'Réplica FastAPI #1 (Scale-Out Horizontal)' },
                      { id: 'api_lacava_2', port: '127.0.0.1:8002', role: 'Réplica FastAPI #2 (Scale-Out Horizontal)' },
                      { id: 'api_lacava_3', port: '127.0.0.1:8003', role: 'Réplica FastAPI #3 (Scale-Out Horizontal)' },
                    ].map(rep => (
                      <div key={rep.id} style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '9px', padding: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <strong style={{ color: '#183a31' }}>{rep.id}</strong>
                          <span className="badge badge-APR">ONLINE · {rep.port}</span>
                        </div>
                        <div style={{ fontSize: '11.5px', color: '#787970', marginTop: '5px' }}>{rep.role}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* CASO C: EL USUARIO HIZO CLIC EN EL BLOQUE INFERIOR "GUI" */}
              {focusedElement === 'gui-frontend' && (
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 800, color: '#782c3e', letterSpacing: '.12em' }}>
                    INSPECTOR DE LA CAPA DE PRESENTACIÓN (CLIENTE WEB)
                  </span>
                  <h3 style={{ margin: '4px 0 8px', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                    GUI — Interfaz Web "La Cava" (React 18 + TypeScript en GitHub Pages)
                  </h3>
                  <p style={{ fontSize: '12.5px', color: '#575950', marginBottom: '12px' }}>
                    Desplegada en <code>https://jjamesrxzn7.github.io/licoreria/</code> (ahorrando levantar un servidor de frontend adicional). Adapta dinámicamente el menú lateral y las acciones permitidas según cuál de los <strong>17 Usuarios RBAC</strong> inicia sesión:
                  </p>
                  <div className="grid-3">
                    <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '9px', padding: '12px' }}>
                      <strong style={{ color: '#782c3e' }}>1. Rol `dba` (`LaCavaDba2026*`)</strong>
                      <p style={{ fontSize: '11.5px', color: '#575950', margin: '4px 0 0' }}>
                        Ve únicamente este Diagrama Interactivo, la Terminal de Consultas Read-Only para las 6 BDs y la Auditoría. No puede borrar, insertar ni actualizar.
                      </p>
                    </div>
                    <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '9px', padding: '12px' }}>
                      <strong style={{ color: '#183a31' }}>2. Rol `admin` (`LaCavaAdmin2026*`)</strong>
                      <p style={{ fontSize: '11.5px', color: '#575950', margin: '4px 0 0' }}>
                        Centro de Mando Global con las 3 Sucursales lado a lado (Quito, Guayaquil y Cuenca), acceso a los 5 módulos y simulador 2PC.
                      </p>
                    </div>
                    <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '9px', padding: '12px' }}>
                      <strong style={{ color: '#a96b16' }}>3. 15 Usuarios por Módulo (`C, I, V, TH, Ctbl`)</strong>
                      <p style={{ fontSize: '11.5px', color: '#575950', margin: '4px 0 0' }}>
                        Cada usuario ve solo su módulo: `_operador` (VER/CREAR), `_supervisor` (+APROBAR) y `_jefe` (+ANULAR).
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* CASO D: EL USUARIO HIZO CLIC EN LOS AGENTES IA DE QUITO O GUAYAQUIL */}
              {(focusedElement === 'agentes-quito' || focusedElement === 'agentes-gye') && (
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 800, color: '#782c3e', letterSpacing: '.12em' }}>
                    INSPECTOR EN VIVO DE AGENTES IA TRANSACCIONALES (EJECUCIÓN CADA 60 SEGUNDOS)
                  </span>
                  <h3 style={{ margin: '4px 0 8px', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                    {focusedElement === 'agentes-quito'
                      ? '🤖 3 Agentes IA en PC de Escritorio (`agentes_quito.py` · 100.77.220.102 → 100.123.81.4:8000)'
                      : '🤖 3 Agentes IA en Laptop (`agentes_gye_cuenca.py` · 100.123.81.4 → :8000)'}
                  </h3>
                  <div className="grid-3" style={{ marginBottom: '12px' }}>
                    {(focusedElement === 'agentes-quito'
                      ? [
                          { name: 'Agente 1 (`X-Sede: QUITO`)', target: 'BD 1 MariaDB (:3307)', desc: 'Rota entre los 15 usuarios RBAC con su contraseña real e inserta operaciones en los 5 módulos de Quito.' },
                          { name: 'Agente 2 (`X-Sede: QUITO_NOSQL`)', target: 'BD 2 MongoDB (:27017)', desc: 'Envía documentos JSON de telemetría y alertas de stock bajo a `eventos_agentes` y `logs_auditoria`.' },
                          { name: 'Agente 3 (`X-Sede: QUITO_PARALELA`)', target: 'BD 3 MariaDB Hash (:3308)', desc: 'Inserta lotes históricos en `historico_transacciones` (`PARTITION BY HASH(id) PARTITIONS 4`).' },
                        ]
                      : [
                          { name: 'Agente 4 (`X-Sede: GUAYAQUIL`)', target: 'BD 4 MariaDB Local (:3306)', desc: 'Simula operaciones de los 5 módulos en Guayaquil autenticándose con los 15 usuarios RBAC.' },
                          { name: 'Agente 5 (`X-Sede: GUAYAQUIL_DWH`)', target: 'BD 5 Estrella DWH (:3309)', desc: 'Ejecuta un Mini-ETL cada minuto consolidando ventas hacia `fact_ventas` para Power BI.' },
                          { name: 'Agente 6 (`X-Sede: CUENCA`)', target: 'BD 6 Supabase Cloud (:5432)', desc: 'Inserta transacciones australes en Cuenca Cloud y mide la latencia WAN en milisegundos.' },
                        ]
                    ).map(ag => (
                      <div key={ag.name} style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '9px', padding: '12px' }}>
                        <strong style={{ color: '#183a31', fontSize: '12.5px' }}>{ag.name}</strong>
                        <div style={{ fontSize: '11px', color: '#782c3e', fontWeight: 700, marginTop: '2px' }}>Destino: {ag.target}</div>
                        <p style={{ fontSize: '11px', color: '#575950', margin: '5px 0 0' }}>{ag.desc}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* CASO E: EL USUARIO HIZO CLIC EN POWER BI */}
              {focusedElement === 'power-bi' && (
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 800, color: '#a96b16', letterSpacing: '.12em' }}>
                    CONEXIÓN GERENCIAL OLAP & BUSINESS INTELLIGENCE
                  </span>
                  <h3 style={{ margin: '4px 0 8px', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                    📊 Power BI Desktop conectado a BD 5 Estrella (:3309), BD 6 Cuenca (:5432) y API Global
                  </h3>
                  <div className="grid-3">
                    <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '9px', padding: '12px' }}>
                      <strong style={{ color: '#183a31' }}>1. Esquema Estrella (`db_gye_dwh`)</strong>
                      <p style={{ fontSize: '11.5px', color: '#575950', margin: '4px 0 0' }}>
                        Servidor MySQL/MariaDB: <code>100.123.81.4:3309</code> | Tablas: <code>fact_ventas</code>, <code>dim_sede</code>, <code>dim_producto</code>, <code>dim_tiempo</code>.
                      </p>
                    </div>
                    <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '9px', padding: '12px' }}>
                      <strong style={{ color: '#a96b16' }}>2. Nodo Cloud Cuenca (`cloud_cuenca_loja`)</strong>
                      <p style={{ fontSize: '11.5px', color: '#575950', margin: '4px 0 0' }}>
                        Servidor PostgreSQL: <code>100.123.81.4:5432</code> / Supabase Pooler | Tablas: <code>operaciones_agentes_cloud</code>, <code>frag_austral_facturas</code>.
                      </p>
                    </div>
                    <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '9px', padding: '12px' }}>
                      <strong style={{ color: '#782c3e' }}>3. Endpoint Web JSON Unificado</strong>
                      <p style={{ fontSize: '11.5px', color: '#575950', margin: '4px 0 0' }}>
                        Conector Web de Power BI apuntando a <code>http://100.123.81.4:8000/api/dba/global</code> (6 BDs en paralelo).
                      </p>
                    </div>
                  </div>
                </div>
              )}
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
                    {currentNode ? `${currentNode.name} (Header X-Sede: ${currentNode.xSede} · Puerto :${currentNode.actualPort})` : 'Consulta Federada Multi-Sucursal (6 BDs)'}
                  </strong>
                </span>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void runDbaQuery()}
                  disabled={runningQuery}
                >
                  <Play size={15} />
                  {runningQuery ? 'Ejecutando...' : 'Ejecutar Consulta Read-Only'}
                </button>
              </div>
            </div>

            {queryError && (
              <div style={{ marginTop: '12px', padding: '12px', background: '#f8e9e8', border: '1px solid #e2b4b1', borderRadius: '8px', color: '#9a3937', fontSize: '12.5px' }}>
                <strong>Error / Bloqueo Read-Only:</strong> {queryError}
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
