import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  Server, Database, Terminal, Play, RefreshCw, ShieldCheck, AlertTriangle,
  Layers, Cloud, Activity, CheckCircle2, XCircle, HardDrive, Network,
  Filter, GitCompare, Lock, Bot, Globe, Cpu, BarChart3
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { isDbaUser, isSuperAdmin } from '../rolePermissions';
import { ParalelismoReal, ReplicacionDR } from './ReplicacionDR';
import { EsquemaEstrella } from './EsquemaEstrella';
import { ArquitectoSI } from './ArquitectoSI';

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

interface PowerBiDataset {
  sourceDatabase: string;
  host: string;
  port: number;
  totalFacts: number;
  kpisBySede: Array<{ sede: string; lotes_etl: number; botellas: number; total_usd: number }>;
  kpisByCategoria: Array<{ categoria: string; botellas: number; total_usd: number }>;
  starSchemaFacts: Array<Record<string, string | number>>;
}

type InteractiveElementId =
  | 'quito-sql'
  | 'quito-nosql'
  | 'quito-otras'
  | 'guayaquil-sql'
  | 'guayaquil-replica'
  | 'cuenca-cloud'
  | 'agente-1'
  | 'agente-2'
  | 'agente-3'
  | 'agente-4'
  | 'agente-5'
  | 'agente-6'
  | 'api-gateway'
  | 'gui-frontend'
  | 'power-bi'
  | 'cluster-global';

type AgentId = 'agente-1' | 'agente-2' | 'agente-3' | 'agente-4' | 'agente-5' | 'agente-6';

interface AgentActivity {
  agentId: string;
  codigo: string;
  nombre: string;
  sede: string;
  script: string;
  maquina: string;
  bdId: string;
  nodeId: string;
  baseDatos: string;
  puerto: number;
  motor: string;
  nodoOnline: boolean;
  estado: string;
  segundosDesdeUltima: number | null;
  totalRegistros: number;
  porModulo: Array<{ modulo: string; operaciones: number }>;
  impactoTablas: Array<{ tabla: string; filas: number; ultimaCorrida?: string; ultimoLote?: string }>;
  ultimos: Array<Record<string, string | number | null>>;
  error?: string;
  latencyMs: number;
}

interface AgentRunResult {
  routedTo: string;
  modulo: string;
  usuarioRbac: string;
  rolRbac: string;
  apiReplica: string;
  latencyMs: number;
  impacto: Array<{ tabla: string; accion: string; id: string | number | null; ok: boolean; error?: string }>;
}

const AGENT_DETAILS: Record<
  AgentId,
  {
    code: string;
    short: string;
    name: string;
    script: string;
    headerXSede: string;
    targetDbId: InteractiveElementId;
    targetDbName: string;
    whatItDoes: string;
    whereToSeeIt: string;
    credentialsUsed: string;
    accent: string;
  }
> = {
  'agente-1': {
    code: 'AG 1',
    short: 'OLTP Quito',
    name: 'Agente 1 — Transaccional OLTP Quito',
    script: 'agentes_quito.py (corre en la PC de Escritorio)',
    headerXSede: 'QUITO',
    targetDbId: 'quito-sql',
    targetDbName: 'BD 1 · ERP MariaDB Quito (:3307 lacava_quito)',
    whatItDoes:
      'Cada 60 s hace UNA transacción real en el ERP de Quito usando la app como un usuario más (header X-Sede-App: QUITO): cada acción la hace el rol que le corresponde: el OPERATIVO (ver + crear) vende en el POS, crea órdenes de compra, registra y edita clientes o consulta facturas (SELECT); el SUPERVISOR (ver + aprobar) aprueba facturas y órdenes, confirma el ingreso a bodega o despacha; el JEFE (ver + anular) anula facturas no despachadas u órdenes no aprobadas (en el ERP un documento no se borra: se anula). Los procedimientos y triggers del ERP la guardan y la auditan en LOG_AUDITORIA con el usuario que la hizo (v_operador, c_supervisor, i_supervisor…). Luego anota en `operaciones_agentes_ia` qué documento tocó (tabla_ref, documento_ref).',
    whereToSeeIt:
      'Aquí (clic en una fila → el documento, su auditoría y si ya llegó a la réplica), en las pantallas de Ventas, Compras, Recepciones y Entregas eligiendo la sede Quito arriba, y en la Terminal DBA sobre BD 1 (consultas 1, 2 y 4).',
    credentialsUsed: 'Rota entre los 15 usuarios operativos (c_*, i_*, v_*, th_*, ctbl_*) con su contraseña real',
    accent: '#782c3e',
  },
  'agente-2': {
    code: 'AG 2',
    short: 'NoSQL JSON',
    name: 'Agente 2 — Documentos NoSQL y alertas JSON',
    script: 'agentes_quito.py (corre en la PC de Escritorio)',
    headerXSede: 'QUITO_NOSQL',
    targetDbId: 'quito-nosql',
    targetDbName: 'BD 2 · MongoDB Quito (:27017)',
    whatItDoes:
      'Cada 60 s envía un documento JSON sin esquema fijo (alerta STOCK_BAJO, usuario, ciclo). La API lo inserta en las colecciones `eventos_agentes` y `logs_auditoria` de MongoDB.',
    whereToSeeIt:
      'Lo ves aquí (columna documento_json), en el Monitor Global y en la Terminal DBA → BD 2 → MONGO_COLLECTION:eventos_agentes.',
    credentialsUsed: 'Rota entre los 15 usuarios operativos',
    accent: '#782c3e',
  },
  'agente-3': {
    code: 'AG 3',
    short: 'Lotes HASH',
    name: 'Agente 3 — Speed-up paralelo (PARTITION BY HASH)',
    script: 'agentes_quito.py (corre en la PC de Escritorio)',
    headerXSede: 'QUITO_PARALELA',
    targetDbId: 'quito-otras',
    targetDbName: 'BD 3 · MariaDB Paralela Quito (:3308)',
    whatItDoes:
      'Cada 60 s inserta una transacción histórica en `historico_transacciones`. El motor calcula MOD(id, 4) y guarda la fila en una de las 4 particiones físicas (p0..p3): así se demuestra speed-up dentro del motor.',
    whereToSeeIt:
      'Lo ves aquí (columna particion y el conteo por partición) y en la Terminal DBA → BD 3 → "Distribución real de registros por partición".',
    credentialsUsed: 'Rota entre los 15 usuarios operativos',
    accent: '#782c3e',
  },
  'agente-4': {
    code: 'AG 4',
    short: 'OLTP GYE',
    name: 'Agente 4 — Transaccional OLTP Guayaquil',
    script: 'agentes_gye_cuenca.py (corre en la Laptop)',
    headerXSede: 'GUAYAQUIL',
    targetDbId: 'guayaquil-sql',
    targetDbName: 'BD 4 · ERP MariaDB Guayaquil (:3307 licoreriadatabase)',
    whatItDoes:
      'Cada 60 s hace UNA transacción real en el ERP de Guayaquil usando la app como un usuario más (header X-Sede-App: GUAYAQUIL): cada acción la hace el rol que le corresponde: el OPERATIVO (ver + crear) vende en el POS, crea órdenes de compra, registra y edita clientes o consulta facturas (SELECT); el SUPERVISOR (ver + aprobar) aprueba facturas y órdenes, confirma el ingreso a bodega o despacha; el JEFE (ver + anular) anula facturas no despachadas u órdenes no aprobadas (en el ERP un documento no se borra: se anula). Los procedimientos y triggers del ERP la guardan y la auditan en LOG_AUDITORIA con el usuario que la hizo (v_operador, c_supervisor, i_supervisor…). Luego anota en `operaciones_agentes_ia` qué documento tocó (tabla_ref, documento_ref).',
    whereToSeeIt:
      'Aquí (clic en una fila → el documento, su auditoría y si ya llegó a la réplica), en las pantallas de Ventas, Compras, Recepciones y Entregas eligiendo la sede Guayaquil arriba, y en la Terminal DBA sobre BD 4 (consultas 1, 2 y 4).',
    credentialsUsed: 'Rota entre los 15 usuarios operativos con su contraseña real',
    accent: '#183a31',
  },
  'agente-5': {
    code: 'AG 5',
    short: 'Mini-ETL',
    name: 'Agente 5 — Mini-ETL hacia el esquema estrella',
    script: 'agentes_gye_cuenca.py (corre en la Laptop)',
    headerXSede: 'GUAYAQUIL_DWH',
    targetDbId: 'guayaquil-replica',
    targetDbName: 'BD 5 · MariaDB DWH (:3309)',
    whatItDoes:
      'Cada 60 s ejecuta un ETL incremental real desde los 3 ERP: EXTRAE del LOG_AUDITORIA de cada sede las líneas de venta nuevas (INSERT en PROxFAC con log_seq > marca de agua en `etl_control`), las TRANSFORMA (producto real del ERP con categoría y marca en dim_producto, cantidad, subtotal, IVA 15 %, mes, usuario que vendió) y las CARGA en `fact_ventas` con su factura de origen. UNIQUE(sede, log_seq) evita duplicados. Si un ERP está caído, lo salta y lo recupera en la siguiente corrida.',
    whereToSeeIt:
      'Lo ves aquí (lotes ETL y marcas de agua), en la pestaña 2 "Power BI" y en Power BI Desktop, que lee `fact_ventas` + `dim_*`.',
    credentialsUsed: 'Usuarios de Ventas y Contabilidad (v_*, ctbl_*)',
    accent: '#183a31',
  },
  'agente-6': {
    code: 'AG 6',
    short: 'ERP Cuenca',
    name: 'Agente 6 — Transaccional ERP Cuenca (PostgreSQL)',
    script: 'agentes_gye_cuenca.py (corre en la Laptop)',
    headerXSede: 'CUENCA',
    targetDbId: 'cuenca-cloud',
    targetDbName: 'BD 6 · ERP PostgreSQL 18 Cuenca (:5432 lacava_cuenca)',
    whatItDoes:
      'Cada 60 s hace UNA transacción real en el ERP de Cuenca usando la app como un usuario más (header X-Sede-App: CUENCA): cada acción la hace el rol que le corresponde: el OPERATIVO (ver + crear) vende en el POS, crea órdenes de compra, registra y edita clientes o consulta facturas (SELECT); el SUPERVISOR (ver + aprobar) aprueba facturas y órdenes, confirma el ingreso a bodega o despacha; el JEFE (ver + anular) anula facturas no despachadas u órdenes no aprobadas (en el ERP un documento no se borra: se anula). Los procedimientos y triggers del ERP la guardan y la auditan en LOG_AUDITORIA con el usuario que la hizo (v_operador, c_supervisor, i_supervisor…). Luego anota en `operaciones_agentes_cloud` qué documento tocó (tabla_ref, documento_ref). Mide la latencia hasta el nodo (latencia_wan_ms).',
    whereToSeeIt:
      'Aquí (clic en una fila → el documento, su auditoría y si ya llegó a la réplica), en las pantallas de Ventas, Compras, Recepciones y Entregas eligiendo la sede Cuenca arriba, y en la Terminal DBA sobre BD 6 (consultas 1, 2 y 4).',
    credentialsUsed: 'Usuarios de la app del ERP de Cuenca (v_operador, v_supervisor, c_*, i_supervisor)',
    accent: '#a96b16',
  },
};

const AGENT_IDS = Object.keys(AGENT_DETAILS) as AgentId[];

interface FeedEvent {
  key: string;
  agentId: string;
  codigo: string;
  sede: string;
  bdId: string;
  segundos: number | null;
  usuario: string | null;
  modulo: string | null;
  detalle: string;
  monto: number;
}

interface FeedResponse {
  timestamp: string;
  apiReplica: string;
  latencyMs: number;
  agentes: Record<string, { agentId: string; online: boolean; segundosDesdeUltima: number | null; error?: string }>;
  eventos: FeedEvent[];
}

interface OperacionDetalle {
  agentId: string;
  codigo: string;
  agente: string;
  bdId: string;
  nodeId: string;
  baseDatos: string;
  motor: string;
  puerto: number;
  operacion: Record<string, string | number | boolean | null>;
  documento: {
    tabla: string;
    id: string;
    modulo: string | null;
    fila: Record<string, string | number | boolean | null> | null;
    consultaSql: string | null;
    appRoute?: string;
  } | null;
  auditoria?: {
    bd: Array<Record<string, string | number | boolean | null>>;
    app: Array<Record<string, string | number | boolean | null>>;
  };
  replica: { nodo: string; tabla: string; presente: boolean | null; replicadoEn?: string | null; error?: string } | null;
  consultaSqlOperacion: string;
  sinDocumento?: string | null;
}

interface LbStatus {
  balanceador: string;
  replicasOnline: number;
  replicasTotal: number;
  replicas: Array<{ replica: string; url: string; online: boolean; ms: number }>;
}

type SiteKey = 'QUITO' | 'GUAYAQUIL' | 'CUENCA';

// Medidas del layout dividido (px)
const CANVAS_W = 1100;
const SIDE_PANEL_W = 430;
const SPLIT_MIN_W = 1180;

const AGENT_SITE: Record<AgentId, SiteKey> = {
  'agente-1': 'QUITO', 'agente-2': 'QUITO', 'agente-3': 'QUITO',
  'agente-4': 'GUAYAQUIL', 'agente-5': 'GUAYAQUIL', 'agente-6': 'CUENCA',
};

const SITE_SUMMARY: Array<{ id: SiteKey; label: string; accent: string; agents: AgentId[] }> = [
  { id: 'QUITO', label: '🖥️ Quito · PC Escritorio', accent: '#782c3e', agents: ['agente-1', 'agente-2', 'agente-3'] },
  { id: 'GUAYAQUIL', label: '💻 Guayaquil · Laptop', accent: '#183a31', agents: ['agente-4', 'agente-5'] },
  { id: 'CUENCA', label: '🐘 Cuenca · PostgreSQL', accent: '#a96b16', agents: ['agente-6'] },
];

const LIVE_CSS = `
@keyframes lcFlowX { from { background-position: 0 0; } to { background-position: 12px 0; } }
@keyframes lcFlowY { from { background-position: 0 0; } to { background-position: 0 12px; } }
@keyframes lcDot { 0% { box-shadow: 0 0 0 0 currentColor; } 70% { box-shadow: 0 0 0 6px transparent; } 100% { box-shadow: 0 0 0 0 transparent; } }
.lc-dot-live { animation: lcDot 1.6s ease-out infinite; display: inline-block; }
@keyframes lcRowNew { 0% { background: #ffe9a8; } 100% { background: transparent; } }
.lc-row-new td { animation: lcRowNew 4s ease-out; }
.lc-row-new { animation: lcRowNew 4s ease-out; }
.lc-side .grid-2, .lc-side .grid-3 { grid-template-columns: minmax(0, 1fr); gap: 10px; }
.lc-side h3 { font-size: 17px !important; }
@keyframes lcAlertRed {
  0%, 100% { box-shadow: 0 0 0 0 rgba(210,58,51,0); border-color: #9a3937; }
  50% { box-shadow: 0 0 0 5px rgba(210,58,51,.30), 0 0 24px rgba(210,58,51,.75); border-color: #d23a33; }
}
@keyframes lcAlertAmber {
  0%, 100% { box-shadow: 0 0 0 0 rgba(229,162,26,0); border-color: #c98a14; }
  50% { box-shadow: 0 0 0 4px rgba(229,162,26,.30), 0 0 18px rgba(229,162,26,.70); border-color: #e5a21a; }
}
.lc-alert-red { animation: lcAlertRed 1s ease-in-out infinite !important; border-style: solid !important; border-width: 2.5px !important; }
.lc-alert-amber { animation: lcAlertAmber 1.4s ease-in-out infinite !important; border-style: solid !important; border-width: 2px !important; }
@keyframes lcBlink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: .2; } }
.lc-blink { animation: lcBlink 1s linear infinite; display: inline-block; }
`;

const isAgentId = (id: string): id is AgentId => id in AGENT_DETAILS;

const formatAgo = (secs: number | null | undefined): string => {
  if (secs === null || secs === undefined) return 'sin datos';
  if (secs < 0) return 'ahora';
  if (secs < 60) return `hace ${secs} s`;
  if (secs < 3600) return `hace ${Math.round(secs / 60)} min`;
  return `hace ${Math.round(secs / 3600)} h`;
};

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
    agents: 'Agente 1 (BD 1) · Agente 2 (BD 2) · Agente 3 (BD 3)',
  },
  {
    code: 'GYE',
    city: 'SUCURSAL REGIONAL GUAYAQUIL (Costa & Puerto)',
    machine: 'Laptop · IP Tailscale: 100.123.81.4',
    accent: '#183a31',
    bg: '#eff5f1',
    emblem: '⚓ Hub Logístico Puerto Marítimo & Data Warehouse BI',
    specialty: 'Importación de Contenedores SENAE, Distribución Cervecería Nacional, Rones Añejos y Cubo Estrella Power BI.',
    databases: '2 Bases de Datos: BD 4 ERP MariaDB (:3307 licoreriadatabase) · BD 5 MariaDB DWH Estrella (:3309)',
    agents: 'Agente 4 (BD 4) · Agente 5 Mini-ETL (BD 5) + Nginx LB & 3 Réplicas API',
  },
  {
    code: 'CUE',
    city: 'SUCURSAL AUSTRAL CUENCA & LOJA (Cloud DBaaS)',
    machine: 'Laptop · PostgreSQL 18 (:5432)',
    accent: '#a96b16',
    bg: '#fbf4e6',
    emblem: '🏔️ Destilerías Tradicionales del Sur (Azuay & Loja)',
    specialty: 'Productores y Destilerías Australes: Aguardiente Zhumir (Azende), Cristal (EASA), Ron San Miguel y Cantaclaro.',
    databases: '1 Base de Datos: BD 6 ERP PostgreSQL 18 (:5432 lacava_cuenca)',
    agents: 'Agente 6 (BD 6) · Medición de Latencia WAN en Tiempo Real',
  },
];

export const ArchitectureConsole: React.FC<{ onNavigate?: (route: string) => void }> = ({ onNavigate }) => {
  const { user } = useAuth();
  const isStrictDba = isDbaUser(user) && !isSuperAdmin(user);
  const [activeTab, setActiveTab] = useState<'diagram_vs' | 'powerbi_tab' | 'global_dba' | 'board' | 'dba_prompt' | 'twopc' | 'replicacion' | 'paralelismo' | 'arquitecto'>('diagram_vs');
  const [topology, setTopology] = useState<TopologyResponse | null>(null);
  const [loadingTopo, setLoadingTopo] = useState(false);

  // Elemento interactivo seleccionado en el Diagrama Visual
  const [focusedElement, setFocusedElement] = useState<InteractiveElementId>('cluster-global');

  // Consola Global del DBA (GET /api/dba/global)
  const [globalData, setGlobalData] = useState<GlobalDbaResponse | null>(null);
  const [filterSede, setFilterSede] = useState<string>('TODAS');
  const [filterModulo, setFilterModulo] = useState<string>('TODOS');
  const [loadingGlobal, setLoadingGlobal] = useState<boolean>(false);

  // Power BI Star Schema state
  const [powerBiData, setPowerBiData] = useState<PowerBiDataset | null>(null);

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

  // 6 Agentes IA (1 por BD): estado resumido + actividad del agente seleccionado
  const [agentActivity, setAgentActivity] = useState<AgentActivity | null>(null);
  const [agentRun, setAgentRun] = useState<AgentRunResult | null>(null);
  const [agentRunError, setAgentRunError] = useState<string>('');
  const [runningAgent, setRunningAgent] = useState<boolean>(false);

  // Feed en vivo (GET /api/agentes/feed cada 2 s) + reloj de 1 s para los cronómetros
  const [feed, setFeed] = useState<FeedResponse | null>(null);
  const [feedAt, setFeedAt] = useState<number>(0);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  const [pulses, setPulses] = useState<Partial<Record<AgentId, number>>>({});
  const [newKeys, setNewKeys] = useState<Record<string, number>>({});
  const [globalFeedFilter, setGlobalFeedFilter] = useState<'TODAS' | SiteKey>('TODAS');
  const seenKeysRef = useRef<Set<string> | null>(null);
  // Layout dividido: diagrama a la izquierda (escalado para caber) + panel lateral fijo a la derecha
  // Ref de callback: vuelve a observar si el contenedor se monta de nuevo (cambio de pestaña, recarga en caliente)
  const splitObserverRef = useRef<ResizeObserver | null>(null);
  const [splitWidth, setSplitWidth] = useState<number>(0);
  const splitRef = useCallback((el: HTMLDivElement | null) => {
    splitObserverRef.current?.disconnect();
    splitObserverRef.current = null;
    if (!el) return;
    setSplitWidth(el.getBoundingClientRect().width);
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(entries => setSplitWidth(entries[0].contentRect.width));
    ro.observe(el);
    splitObserverRef.current = ro;
  }, []);
  const isSplit = splitWidth >= SPLIT_MIN_W;
  const canvasArea = isSplit ? splitWidth - SIDE_PANEL_W - 16 : splitWidth;
  const canvasScale = canvasArea > 0 ? Math.min(1, canvasArea / CANVAS_W) : 1;
  const feedBusyRef = useRef<boolean>(false);

  // Alarmas: error del feed (API) y estado del balanceador + réplicas (GET /api/lb/estado cada 4 s)
  const [feedError, setFeedError] = useState<string | null>(null);
  const [lbStatus, setLbStatus] = useState<LbStatus | null>(null);
  const [lbError, setLbError] = useState<boolean>(false);

  const fetchLbStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/lb/estado`);
      if (res.ok) {
        setLbStatus(await res.json());
        setLbError(false);
      } else {
        setLbError(true);
      }
    } catch {
      setLbError(true);
    }
  }, []);

  const fetchFeed = useCallback(async () => {
    if (feedBusyRef.current) return;
    feedBusyRef.current = true;
    try {
      const res = await fetch(`${API_BASE_URL}/api/agentes/feed?limit=10`);
      if (res.ok) {
        const data: FeedResponse = await res.json();
        const t = Date.now();
        const seen = seenKeysRef.current;
        if (seen) {
          // Solo lo que no habíamos visto antes enciende las líneas (la primera carga no dispara pulsos)
          const fresh = data.eventos.filter(e => !seen.has(e.key));
          if (fresh.length > 0) {
            setPulses(prev => {
              const next = { ...prev };
              fresh.forEach(e => { if (isAgentId(e.agentId)) next[e.agentId] = t; });
              return next;
            });
            setNewKeys(prev => {
              const next: Record<string, number> = {};
              Object.entries(prev).forEach(([k, v]) => { if (t - v < 10000) next[k] = v; });
              fresh.forEach(e => { next[e.key] = t; });
              return next;
            });
          }
        }
        const merged = new Set(seen && seen.size < 3000 ? seen : []);
        data.eventos.forEach(e => merged.add(e.key));
        seenKeysRef.current = merged;
        setFeed(data);
        setFeedAt(t);
        setFeedError(null);
      } else {
        let detalle = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          detalle = body?.error || body?.detail || detalle;
        } catch {
          // respuesta sin JSON
        }
        setFeedError(detalle);
      }
    } catch {
      setFeedError('sin respuesta del balanceador');
    } finally {
      feedBusyRef.current = false;
    }
  }, []);

  const fetchAgentActivity = useCallback(async (agentId: AgentId) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/agentes/${agentId}/actividad?limit=15`);
      if (res.ok) {
        const data: AgentActivity = await res.json();
        setAgentActivity(data);
      }
    } catch {
      // API no disponible momentáneamente
    }
  }, []);

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

  const fetchPowerBiStar = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/powerbi/estrella`);
      if (res.ok) {
        const data: PowerBiDataset = await res.json();
        setPowerBiData(data);
      }
    } catch {
      // Ignore
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

  // Carga inicial UNA sola vez. Antes dependía de runDbaQuery, que cambia con cada edición del SQL,
  // y volvía a lanzar la consulta por defecto de Cuenca encima de la consulta del usuario.
  const cargaInicialHecha = useRef(false);
  useEffect(() => {
    if (cargaInicialHecha.current) return;
    cargaInicialHecha.current = true;
    void fetchTopology();
    void fetchGlobalDbaConsole('TODAS', 'TODOS');
    void fetchPowerBiStar();
    void runDbaQuery('cuenca-cloud', "SELECT id_op, sede_header, agente_nombre, usuario_rbac, rol_rbac, modulo, operacion, monto_usd, latencia_wan_ms, fecha_hora FROM operaciones_agentes_cloud ORDER BY id_op DESC LIMIT 10;");
  }, [fetchTopology, fetchGlobalDbaConsole, fetchPowerBiStar, runDbaQuery]);

  useEffect(() => {
    if (selectedNodeId && selectedNodeId !== 'global-federated') {
      void fetchNodeLogs(selectedNodeId);
    }
  }, [selectedNodeId, fetchNodeLogs]);

  // Reloj de 1 s: hace avanzar todos los cronómetros "hace X s" sin pedir nada al servidor
  useEffect(() => {
    const t = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  // Feed de las 6 BDs cada 2 s mientras se ve el diagrama
  useEffect(() => {
    if (activeTab !== 'diagram_vs') return undefined;
    void fetchFeed();
    const t = window.setInterval(() => void fetchFeed(), 2000);
    return () => window.clearInterval(t);
  }, [activeTab, fetchFeed]);

  // Estado del balanceador y sus 3 réplicas cada 4 s (luces de la caja API)
  useEffect(() => {
    if (activeTab !== 'diagram_vs') return undefined;
    void fetchLbStatus();
    const t = window.setInterval(() => void fetchLbStatus(), 4000);
    return () => window.clearInterval(t);
  }, [activeTab, fetchLbStatus]);

  // Detalle del agente seleccionado: cada 5 s y al instante cuando el feed detecta una escritura suya
  const focusedPulseAt = isAgentId(focusedElement) ? pulses[focusedElement] ?? 0 : 0;
  useEffect(() => {
    if (activeTab !== 'diagram_vs' || !isAgentId(focusedElement)) return undefined;
    const id = focusedElement;
    void fetchAgentActivity(id);
    const t = window.setInterval(() => void fetchAgentActivity(id), 5000);
    return () => window.clearInterval(t);
  }, [activeTab, focusedElement, fetchAgentActivity, focusedPulseAt]);

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
    } else if (isAgentId(elemId)) {
      setAgentActivity(null);
      setAgentRun(null);
      setAgentRunError('');
      void fetchAgentActivity(elemId);
    } else if (elemId === 'power-bi') {
      void fetchPowerBiStar();
    }
  };

  // ---------- Detalle de UNA operación de un agente (qué hizo exactamente y dónde quedó) ----------
  const [opDetalle, setOpDetalle] = useState<{ agentId: AgentId; opId: string; data: OperacionDetalle | null; error: string } | null>(null);

  const opIdDeFila = (agentId: AgentId, fila: Record<string, string | number | null>): string => {
    const v = agentId === 'agente-2' ? fila.evento_id
      : agentId === 'agente-3' ? fila.id
        : agentId === 'agente-5' ? fila.etl_lote
          : fila.id_op;
    return String(v ?? '');
  };

  const abrirDetalleOperacion = async (agentId: AgentId, opId: string) => {
    if (!opId) return;
    setOpDetalle({ agentId, opId, data: null, error: '' });
    try {
      const res = await fetch(`${API_BASE_URL}/api/agentes/${agentId}/operacion/${encodeURIComponent(opId)}`);
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`);
      setOpDetalle({ agentId, opId, data: body, error: '' });
    } catch (err) {
      setOpDetalle({ agentId, opId, data: null, error: err instanceof Error ? err.message : 'Error' });
    }
  };

  const abrirEnTerminal = (nodeId: string, sql: string) => {
    setOpDetalle(null);
    setSelectedNodeId(nodeId);
    setSqlText(sql);
    setActiveTab('dba_prompt');
    void runDbaQuery(nodeId, sql);
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
      // Una operación de cada uno de los 6 agentes (el 5 va al final para que el ETL recoja las ventas nuevas).
      await Promise.all(
        AGENT_IDS.filter(id => id !== 'agente-5').map(id =>
          fetch(`${API_BASE_URL}/api/agentes/${id}/ejecutar`, { method: 'POST' }).catch(() => null)
        )
      );
      await fetch(`${API_BASE_URL}/api/agentes/agente-5/ejecutar`, { method: 'POST' }).catch(() => null);
      await fetchGlobalDbaConsole(filterSede, filterModulo);
      await fetchTopology();
      await fetchPowerBiStar();
      await fetchFeed();
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
  const focusedAgentId: AgentId | null = isAgentId(focusedElement) ? focusedElement : null;
  const focusedAgent = focusedAgentId ? AGENT_DETAILS[focusedAgentId] : null;
  const findNode = (id: string) => topology?.nodes.find(n => n.id === id);

  // ---------- Tiempo real: cronómetros, pulsos y estado de cada agente a partir del feed ----------
  const elapsedSinceFeed = feedAt ? Math.max(0, Math.floor((nowMs - feedAt) / 1000)) : 0;
  const liveSecs = (secs: number | null | undefined): number | null =>
    secs === null || secs === undefined ? null : secs + elapsedSinceFeed;
  const agentLiveSecs = (agentId: AgentId) => liveSecs(feed?.agentes[agentId]?.segundosDesdeUltima);
  // Estado de la API: caída (rojo) si el balanceador no responde, no quedan réplicas o el feed falla;
  // degradada (ámbar) si faltan réplicas pero el balanceador sigue atendiendo con las que quedan.
  const replicasOnline = lbStatus?.replicasOnline ?? null;
  const apiDown = lbError || replicasOnline === 0 || feedError !== null;
  const apiDegraded = !apiDown && replicasOnline !== null && replicasOnline < (lbStatus?.replicasTotal ?? 3);

  const agentEstado = (agentId: AgentId): 'ACTIVO' | 'INACTIVO' | 'SIN CONEXIÓN' | 'SIN API' | 'CARGANDO' => {
    if (apiDown) return 'SIN API';
    const a = feed?.agentes[agentId];
    if (!a) return 'CARGANDO';
    if (!a.online) return 'SIN CONEXIÓN';
    const s = agentLiveSecs(agentId);
    return s !== null && s <= 150 ? 'ACTIVO' : 'INACTIVO';
  };

  // Lista de problemas actuales (banner del diagrama y panel global)
  const problemas: Array<{ nivel: 'rojo' | 'ambar'; texto: string }> = [];
  if (lbError) {
    problemas.push({ nivel: 'rojo', texto: 'El balanceador (:8000) no responde: ejecuta iniciar_laptop.ps1 en la Laptop.' });
  } else if (replicasOnline === 0) {
    problemas.push({ nivel: 'rojo', texto: 'API: las 3 réplicas están apagadas. Ejecuta iniciar_laptop.ps1 en la Laptop.' });
  } else if (feedError) {
    problemas.push({ nivel: 'rojo', texto: `La API no entrega datos (${feedError}).` });
  } else if (apiDegraded && lbStatus) {
    const caidas = lbStatus.replicas.filter(r => !r.online).map(r => r.replica).join(', ');
    problemas.push({ nivel: 'ambar', texto: `API degradada: ${replicasOnline}/${lbStatus.replicasTotal} réplicas (${caidas} apagada). El balanceador reparte entre las que quedan.` });
  }
  if (!apiDown && feed) {
    AGENT_IDS.forEach(id => {
      const ag = AGENT_DETAILS[id];
      const a = feed.agentes[id];
      if (!a) return;
      if (!a.online) {
        problemas.push({ nivel: 'rojo', texto: `${ag.targetDbName} sin conexión: ${ag.code} no puede escribir.` });
      } else if (agentEstado(id) === 'INACTIVO') {
        const donde = AGENT_SITE[id] === 'QUITO' ? 'agentes_quito.py en la PC de Escritorio' : 'iniciar_laptop.ps1 en la Laptop';
        problemas.push({ nivel: 'ambar', texto: `${ag.code} dormido (última operación ${formatAgo(agentLiveSecs(id))}): enciende ${donde}.` });
      }
    });
  }

  const renderAlarmas = (compacto: boolean) => (
    problemas.length === 0 ? (
      <div style={{ display: 'flex', alignItems: 'center', gap: '7px', padding: compacto ? '5px 12px' : '8px 12px', borderRadius: '999px', background: '#eff5f1', border: '1px solid #cde0d3', color: '#183a31', fontSize: '11px', fontWeight: 700 }}>
        <span className="lc-dot-live" style={{ width: 8, height: 8, borderRadius: '50%', background: '#267154', color: '#267154' }} />
        Todo operativo · API {replicasOnline ?? '?'}/{lbStatus?.replicasTotal ?? 3} réplicas · 6/6 BDs · 6/6 agentes activos
      </div>
    ) : (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', padding: '8px 12px', borderRadius: '10px', background: problemas.some(p => p.nivel === 'rojo') ? '#f8e9e8' : '#fdf3df', border: `1.5px solid ${problemas.some(p => p.nivel === 'rojo') ? '#9a3937' : '#c98a14'}`, maxWidth: '760px' }}>
        {problemas.map((p, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11.5px', fontWeight: 700, color: p.nivel === 'rojo' ? '#9a3937' : '#8a5a00' }}>
            <span className="lc-blink" style={{ width: 9, height: 9, flexShrink: 0, borderRadius: '50%', background: p.nivel === 'rojo' ? '#d23a33' : '#e5a21a', boxShadow: `0 0 8px ${p.nivel === 'rojo' ? '#d23a33' : '#e5a21a'}` }} />
            {p.texto}
          </div>
        ))}
      </div>
    )
  );
  const isPulsing = (agentId: AgentId) => nowMs - (pulses[agentId] ?? 0) < 2600;
  const anyPulsing = (ids: AgentId[]) => ids.some(isPulsing);
  const isNewKey = (key: string) => nowMs - (newKeys[key] ?? 0) < 4000;

  // ---------- Piezas del lienzo ----------
  const COL_W = 100;
  const COL_GAP = 12;

  /** Línea de conexión: punteada en reposo; se enciende y "fluye" cuando pasa una operación. */
  const renderFlowLine = (opts: { dir: 'h' | 'v'; color: string; active: boolean; length?: string; reverse?: boolean; grow?: boolean }) => {
    const thick = opts.active ? 5 : 3;
    const base: React.CSSProperties = {
      backgroundImage: `linear-gradient(${opts.dir === 'h' ? 'to right' : 'to bottom'}, ${opts.color} 55%, transparent 55%)`,
      backgroundSize: opts.dir === 'h' ? '12px 100%' : '100% 12px',
      backgroundRepeat: opts.dir === 'h' ? 'repeat-x' : 'repeat-y',
      opacity: opts.active ? 1 : 0.5,
      boxShadow: opts.active ? `0 0 12px 2px ${opts.color}99` : 'none',
      borderRadius: '3px',
      transition: 'opacity .3s, box-shadow .3s, width .2s, height .2s',
      animation: opts.active ? `${opts.dir === 'h' ? 'lcFlowX' : 'lcFlowY'} .45s linear infinite${opts.reverse ? ' reverse' : ''}` : 'none',
      flexShrink: 0,
    };
    return opts.dir === 'h' ? (
      <div style={{ ...base, height: `${thick}px`, width: opts.length ?? '100%' }} />
    ) : (
      <div style={{ ...base, width: `${thick}px`, height: opts.length ?? '100%', flex: opts.grow ? 1 : undefined }} />
    );
  };

  const renderDbBox = (nodeId: InteractiveElementId, agentId: AgentId, bdLabel: string, roleShort: string, portStr: string) => {
    const n = findNode(nodeId);
    // El feed (cada 2 s) manda: si el agente no puede leer su BD, la BD está caída en este momento.
    const live = feed?.agentes[agentId];
    const isOnline = live ? live.online : !n || n.status === 'ONLINE';
    // Sin API no se puede saber el estado de la BD: se muestra en gris, sin alarma propia.
    const unknown = apiDown;
    const alarma = !unknown && !isOnline;
    const isDbFocused = focusedElement === nodeId;
    const pulse = isPulsing(agentId);
    const accent = AGENT_DETAILS[agentId].accent;
    return (
      <button
        key={nodeId}
        type="button"
        onClick={() => handleClickDiagramNode(nodeId)}
        title={n ? `${n.name} — ${n.status}` : bdLabel}
        style={{ width: `${COL_W}px`, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', background: 'transparent', border: 'none', cursor: 'pointer', padding: 0 }}
      >
        <div
          className={alarma ? 'lc-alert-red' : undefined}
          style={{
            width: '86px',
            height: '80px',
            borderRadius: '16px',
            border: isDbFocused ? '3px solid #782c3e' : isOnline ? '2px solid #25251f' : '2.5px solid #9a3937',
            background: pulse ? '#fffbe9' : isDbFocused ? '#fbf3f0' : isOnline ? '#ffffff' : '#f8e9e8',
            boxShadow: pulse
              ? `0 0 0 4px ${accent}40, 0 0 22px ${accent}99`
              : isDbFocused ? '0 8px 20px rgba(120,44,62,0.22)' : '0 3px 10px rgba(0,0,0,0.06)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
            transition: 'all 0.25s ease',
          }}
        >
          <span
            className={alarma ? 'lc-blink' : undefined}
            style={{ position: 'absolute', top: '7px', right: '7px', width: '9px', height: '9px', borderRadius: '50%', background: unknown ? '#b5b3aa' : isOnline ? '#267154' : '#d23a33' }}
          />
          {pulse && (
            <span style={{ position: 'absolute', top: '-9px', left: '50%', transform: 'translateX(-50%)', fontSize: '9px', fontWeight: 800, background: accent, color: '#fff', padding: '1px 7px', borderRadius: '999px', whiteSpace: 'nowrap' }}>
              + escritura
            </span>
          )}
          <Database size={21} color={isOnline ? '#183a31' : '#9a3937'} />
          <strong style={{ fontSize: '11.5px', color: '#25251f', marginTop: '3px' }}>{bdLabel}</strong>
          <code style={{ fontSize: '9.5px', color: '#782c3e', fontWeight: 700 }}>:{n?.actualPort || portStr}</code>
        </div>
        <span style={{ fontSize: '12px', fontWeight: 700, color: '#25251f' }}>{roleShort}</span>
        <span className={alarma ? 'lc-blink' : undefined} style={{ fontSize: '10px', fontWeight: 800, color: unknown ? '#9e9d95' : isOnline ? '#267154' : '#d23a33' }}>
          {unknown ? 'sin datos (API)' : !isOnline ? '● CAÍDA' : n ? `${n.latencyMs} ms` : '…'}
        </span>
      </button>
    );
  };

  const renderAgentCard = (agentId: AgentId) => {
    const ag = AGENT_DETAILS[agentId];
    const estado = agentEstado(agentId);
    const focused = focusedElement === agentId;
    const pulse = isPulsing(agentId);
    const color = estado === 'ACTIVO' ? '#267154' : estado === 'INACTIVO' ? '#e5a21a' : estado === 'CARGANDO' ? '#9e9d95' : '#d23a33';
    const secs = agentLiveSecs(agentId);
    const alarmClass = focused ? undefined
      : estado === 'INACTIVO' ? 'lc-alert-amber'
        : estado === 'SIN CONEXIÓN' || estado === 'SIN API' ? 'lc-alert-red' : undefined;
    const statusText = estado === 'SIN API' ? 'sin API'
      : estado === 'SIN CONEXIÓN' ? 'BD caída'
        : pulse ? '¡escribiendo!'
          : estado === 'INACTIVO' ? `DORMIDO · ${formatAgo(secs)}`
            : formatAgo(secs);
    return (
      <div key={agentId} style={{ width: `${COL_W}px`, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {renderFlowLine({ dir: 'v', color: ag.accent, active: pulse, length: '20px', reverse: true })}
        <button
          type="button"
          className={alarmClass}
          onClick={() => handleClickDiagramNode(agentId)}
          title={`${ag.name}: clic para ver qué está insertando`}
          style={{
            width: '100%',
            padding: '7px 6px',
            borderRadius: '12px',
            border: focused || pulse ? `2px solid ${ag.accent}` : '1.5px solid #d9d6cc',
            background: focused ? ag.accent : pulse ? '#fffbe9' : '#ffffff',
            color: focused ? '#ffffff' : '#25251f',
            boxShadow: pulse ? `0 0 0 3px ${ag.accent}33, 0 0 16px ${ag.accent}88` : focused ? `0 6px 16px ${ag.accent}40` : '0 2px 6px rgba(0,0,0,0.05)',
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '2px',
            transition: 'all 0.25s ease',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px', fontWeight: 800 }}>
            <Bot size={14} color={focused ? '#ffffff' : ag.accent} />
            {ag.code}
            <span
              className={estado === 'ACTIVO' ? 'lc-dot-live' : estado === 'CARGANDO' ? undefined : 'lc-blink'}
              style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, color }}
            />
          </span>
          <span style={{ fontSize: '10.5px', fontWeight: 600, opacity: 0.9 }}>{ag.short}</span>
          <span style={{ fontSize: '10px', fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: focused ? undefined : estado === 'INACTIVO' ? '#8a5a00' : estado === 'SIN CONEXIÓN' || estado === 'SIN API' ? '#d23a33' : undefined }}>
            {statusText}
          </span>
        </button>
      </div>
    );
  };

  type SiteDb = [InteractiveElementId, AgentId, string, string, string];

  const renderSite = (opts: { label: string; sub: string; accent: string; bg: string; dbs: SiteDb[]; spine?: boolean }) => {
    const cols = `repeat(${opts.dbs.length}, ${COL_W}px)`;
    const agentIds = opts.dbs.map(d => d[1]);
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {/* RECUADRO DE LA MÁQUINA: SOLO SUS BASES DE DATOS */}
        <div style={{ border: `2px solid ${opts.accent}`, borderRadius: '16px', background: opts.bg, padding: '10px 14px 12px', boxShadow: anyPulsing(agentIds) ? `0 0 0 3px ${opts.accent}22, 0 8px 24px ${opts.accent}33` : '0 6px 18px rgba(0,0,0,0.05)', transition: 'box-shadow .3s' }}>
          <div style={{ textAlign: 'center', marginBottom: '10px' }}>
            <div style={{ fontSize: '10.5px', fontWeight: 800, color: opts.accent, letterSpacing: '.06em' }}>{opts.label}</div>
            <div style={{ fontSize: '9.5px', color: '#787970', fontFamily: 'monospace' }}>{opts.sub}</div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: cols, gap: `${COL_GAP}px`, justifyItems: 'center' }}>
            {opts.dbs.map(([nodeId, agentId, bd, role, port]) => renderDbBox(nodeId, agentId, bd, role, port))}
          </div>
        </div>
        {/* CARRIL DE AGENTES: FUERA DEL RECUADRO, UNO DEBAJO DE CADA BD */}
        <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: cols, gap: `${COL_GAP}px`, justifyItems: 'center', padding: '0 16px' }}>
          {opts.spine && (
            // Eje central que baja desde el recuadro hasta la API pasando entre los agentes
            <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, transform: 'translateX(-50%)', display: 'flex', flexDirection: 'column' }}>
              {renderFlowLine({ dir: 'v', color: opts.accent, active: anyPulsing(agentIds), grow: true })}
            </div>
          )}
          {opts.dbs.map(([, agentId]) => renderAgentCard(agentId))}
        </div>
      </div>
    );
  };

  const handleCanvasClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('button')) return;
    setFocusedElement('cluster-global');
  };

  const runSingleAgent = async (agentId: AgentId) => {
    setRunningAgent(true);
    setAgentRunError('');
    setAgentRun(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/agentes/${agentId}/ejecutar`, { method: 'POST' });
      const body = await res.json();
      if (!res.ok) {
        setAgentRunError(body?.detail || 'La API rechazó la operación.');
      } else {
        setAgentRun(body);
      }
      await Promise.all([fetchAgentActivity(agentId), fetchFeed()]);
    } catch (err) {
      setAgentRunError(err instanceof Error ? err.message : 'Error de red.');
    } finally {
      setRunningAgent(false);
    }
  };

  return (
    <div>
      <style>{LIVE_CSS}</style>

      {/* ==================== DETALLE DE UNA OPERACIÓN DE AGENTE (ventana superpuesta) ==================== */}
      {opDetalle && (
        <div
          onClick={() => setOpDetalle(null)}
          style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(20,24,20,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{ width: 'min(860px, 100%)', maxHeight: '88vh', overflowY: 'auto', background: '#faf9f6', borderRadius: '14px', border: `3px solid ${AGENT_DETAILS[opDetalle.agentId].accent}`, padding: '18px 20px', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px', marginBottom: '10px' }}>
              <div>
                <span style={{ fontSize: '10px', fontWeight: 800, letterSpacing: '.12em', color: AGENT_DETAILS[opDetalle.agentId].accent }}>
                  DETALLE DE LA OPERACIÓN · {AGENT_DETAILS[opDetalle.agentId].code}
                </span>
                <h3 style={{ margin: '3px 0 0', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                  {AGENT_DETAILS[opDetalle.agentId].name} · operación <code>{opDetalle.opId}</code>
                </h3>
              </div>
              <button type="button" className="btn btn-outline" onClick={() => setOpDetalle(null)}>Cerrar</button>
            </div>

            {!opDetalle.data && !opDetalle.error && <div className="empty-state">Leyendo la operación desde su base de datos…</div>}
            {opDetalle.error && <div style={{ padding: '10px', background: '#f8e9e8', borderRadius: '8px', color: '#9a3937', fontSize: '12px' }}>{opDetalle.error}</div>}

            {opDetalle.data && (() => {
              const d = opDetalle.data;
              const kv = (obj: Record<string, string | number | boolean | null>) => (
                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(130px, max-content) 1fr', gap: '3px 12px', fontSize: '12px' }}>
                  {Object.entries(obj).map(([k, v]) => (
                    <React.Fragment key={k}>
                      <span style={{ color: '#787970' }}>{k}</span>
                      <span style={{ fontWeight: 600, wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>
                        {v === null ? '—' : /^\d{4}-\d{2}-\d{2}T/.test(String(v)) ? String(v).replace('T', ' ').slice(0, 19) : String(v)}
                      </span>
                    </React.Fragment>
                  ))}
                </div>
              );
              return (
                <>
                  <div style={{ fontSize: '12px', color: '#575950', marginBottom: '10px' }}>
                    Escrita en <strong>{d.bdId}</strong> · {d.motor} · base <code>{d.baseDatos}</code> (:{d.puerto})
                  </div>
                  <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px', marginBottom: '10px' }}>
                    <strong style={{ color: '#782c3e', fontSize: '12.5px', display: 'block', marginBottom: '6px' }}>1. La transacción (qué acción hizo, quién y cuándo)</strong>
                    {kv(d.operacion)}
                  </div>
                  <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px', marginBottom: '10px' }}>
                    <strong style={{ color: '#183a31', fontSize: '12.5px', display: 'block', marginBottom: '6px' }}>
                      2. Lo que dejó en el módulo{d.documento?.modulo ? ` de ${d.documento.modulo}` : ''}
                    </strong>
                    {d.documento ? (
                      <>
                        <div style={{ fontSize: '12px', marginBottom: '6px' }}>Tabla <code>{d.documento.tabla}</code> · registro <code>{d.documento.id}</code></div>
                        {d.documento.fila ? kv(d.documento.fila) : <div style={{ fontSize: '12px', color: '#9a3937' }}>El registro ya no existe en la tabla.</div>}
                      </>
                    ) : (
                      <div style={{ fontSize: '12px', color: '#787970' }}>{d.sinDocumento}</div>
                    )}
                  </div>
                  {d.replica && (
                    <div style={{ background: d.replica.presente ? '#eff5f1' : '#fdf6e7', border: '1px solid #e9e6de', borderRadius: '10px', padding: '10px 12px', marginBottom: '10px', fontSize: '12px' }}>
                      <strong>3. Réplica:</strong>{' '}
                      {d.replica.presente === true && <>ya copiada en <strong>{d.replica.nodo}</strong> (<code>{d.replica.tabla}</code>) el {String(d.replica.replicadoEn ?? '').replace('T', ' ').slice(0, 19)}.</>}
                      {d.replica.presente === false && <>todavía no está en <strong>{d.replica.nodo}</strong>: se copiará en la próxima ronda (replicación asíncrona).</>}
                      {d.replica.presente === null && <>no se pudo consultar {d.replica.nodo} ({d.replica.error}).</>}
                    </div>
                  )}
                  {d.auditoria && (d.auditoria.bd.length > 0 || d.auditoria.app.length > 0) && (
                    <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px', marginBottom: '10px' }}>
                      <strong style={{ color: '#25251f', fontSize: '12.5px', display: 'block', marginBottom: '6px' }}>
                        4. Auditoría (quién lo hizo, cuándo y qué tablas tocó)
                      </strong>
                      {d.auditoria.bd.length > 0 && (
                        <>
                          <div style={{ fontSize: '11.5px', color: '#575950', marginBottom: '4px' }}>En la bitácora de auditoría de {d.bdId}:</div>
                          <ul style={{ margin: '0 0 8px', paddingLeft: '18px', fontSize: '11.5px' }}>
                            {d.auditoria.bd.map((a, i) => (
                              <li key={i}>
                                {String(a.fecha_hora ?? '').replace('T', ' ').slice(0, 19)} · <code>{String(a.usuario)}</code> · {String(a.accion ?? a.evento ?? '')} {a.tabla ? <code>{String(a.tabla)}</code> : null}
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                      {d.auditoria.app.length > 0 && (
                        <>
                          <div style={{ fontSize: '11.5px', color: '#575950', marginBottom: '4px' }}>En la auditoría de la app principal (pantalla Auditoría):</div>
                          <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '11.5px' }}>
                            {d.auditoria.app.map((a, i) => (
                              <li key={i}>
                                {String(a.fecha_hora ?? '').replace('T', ' ').slice(0, 19)} · <code>{String(a.usuario ?? 'sistema (trigger)')}</code> · {String(a.accion)} <code>{String(a.tabla)}</code>
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    {d.documento?.appRoute && onNavigate && (
                      <button type="button" className="btn btn-primary" onClick={() => { setOpDetalle(null); onNavigate(d.documento!.appRoute!); }}>
                        Ir al módulo: abrir la pantalla {d.documento.modulo}
                      </button>
                    )}
                    {d.documento?.consultaSql && (
                      <button type="button" className="btn btn-primary" onClick={() => abrirEnTerminal(d.nodeId, d.documento!.consultaSql!)}>
                        <Terminal size={14} /> Ir al módulo: abrir {d.documento.tabla.split(' ')[0]} en la Terminal DBA
                      </button>
                    )}
                    <button type="button" className="btn btn-outline" onClick={() => abrirEnTerminal(d.nodeId, d.consultaSqlOperacion)}>
                      Ver en la bitácora del agente
                    </button>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      )}
      {/* ENCABEZADO CON LA ESTÉTICA DE LA CAVA */}
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            TOPOLOGÍA INTERACTIVA EN VIVO · TÚNEL VPN TAILSCALE · 6 BDs + 6 AGENTES IA ({globalData?.apiReplica || topology?.apiReplica || 'api_lacava_1'})
          </span>
          <h1>Diagrama en Vivo del Clúster Híbrido "La Cava"</h1>
          <p>
            Haz clic en cualquiera de las <strong>6 BDs</strong>, en cualquiera de los <strong>6 Agentes IA (`AG 1..AG 6`)</strong>, en la <strong>API</strong> o en la <strong>GUI</strong> para ver abajo qué datos está ingresando y consultar sus tablas en vivo.
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
              void fetchPowerBiStar();
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
          { id: 'diagram_vs', label: '1. Diagrama Interactivo (6 BDs + 6 Agentes IA + Túnel Tailscale + API + GUI)', icon: GitCompare, show: true },
          { id: 'powerbi_tab', label: '2. Dashboard OLAP & Configuración Power BI (BD 5 Estrella :3309)', icon: BarChart3, show: true },
          { id: 'dba_prompt', label: '3. Terminal Read-Only del DBA (Consultas 3 Sucursales / 6 BDs)', icon: Terminal, show: true },
          { id: 'global_dba', label: '4. Monitor Global Unificado (6 BDs en Paralelo)', icon: Filter, show: true },
          { id: 'board', label: '5. Identidad por Sucursal & Tarjetas de Nodos', icon: Network, show: true },
          { id: 'twopc', label: '6. Simulador 2PC (Exclusivo Admin / Arquitecto)', icon: ShieldCheck, show: !isStrictDba },
          { id: 'replicacion', label: '7. Replicación en anillo y plan DR', icon: Layers, show: true },
          { id: 'paralelismo', label: '8. Paralelismo real (medido)', icon: Cpu, show: true },
          { id: 'arquitecto', label: '9. Control del arquitecto de SI', icon: Server, show: !isStrictDba },
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

      {/* ==================== TAB 1: DIAGRAMA VISUAL LIMPIO Y CUADRADO (EXACTAMENTE COMO EL BOCETO) ==================== */}
      {activeTab === 'diagram_vs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <section className="card" style={{ padding: '22px' }}>
            <div className="section-heading" style={{ marginBottom: '14px' }}>
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '18px' }}>
                  <Network size={20} color="#782c3e" />
                  Flujo en Vivo: 3 BDs Quito (Izq) · 2 BDs Guayaquil (Arriba) · 1 BD Cuenca (Der) ↔ Túnel Tailscale ↔ API ↔ GUI
                </h2>
                <p>
                  Cada Base de Datos tiene su propio <strong>Agente IA independiente (`AG 1` a `AG 6`)</strong> justo debajo. Haz clic en una <strong>BD</strong>, un <strong>Agente</strong>, la <strong>API</strong> o el <strong>fondo</strong> del diagrama: el detalle en vivo aparece {isSplit ? 'en el panel de la derecha' : 'debajo del diagrama'} sin perder de vista las líneas.
                </p>
              </div>
              <span className="demo-badge">1 AGENTE IA POR CADA BASE DE DATOS</span>
            </div>

            {/* ==================== DIAGRAMA (IZQUIERDA, ESCALADO) + PANEL LATERAL FIJO (DERECHA) ==================== */}
            <div
              ref={splitRef}
              style={{
                display: 'grid',
                gridTemplateColumns: isSplit ? `minmax(0, 1fr) ${SIDE_PANEL_W}px` : 'minmax(0, 1fr)',
                gap: '16px',
                alignItems: 'start',
              }}
            >
            <div style={{ minWidth: 0, overflowX: canvasScale < 0.6 ? 'auto' : 'visible' }}>
            <div style={{ zoom: Math.max(canvasScale, 0.6) }}>
              <div
                onClick={handleCanvasClick}
                title="Clic en el fondo: actividad en vivo de las 3 sedes"
                style={{
                  width: `${CANVAS_W}px`,
                  position: 'relative',
                  cursor: 'pointer',
                  background: 'radial-gradient(circle at 50% 45%, #ffffff 0%, #f6f4ef 100%)',
                  border: focusedElement === 'cluster-global' ? '2.5px solid #183a31' : '1.5px solid #dfded7',
                  boxShadow: focusedElement === 'cluster-global' ? '0 0 0 4px rgba(24,58,49,0.10)' : 'none',
                  borderRadius: '16px',
                  padding: '40px 20px 18px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  transition: 'border .2s, box-shadow .2s',
                }}
              >
                {/* RELOJ EN VIVO */}
                <div style={{ position: 'absolute', top: '12px', right: '14px', display: 'flex', alignItems: 'center', gap: '7px', fontSize: '10.5px', color: '#575950', fontWeight: 700 }}>
                  <span
                    className={apiDown ? 'lc-blink' : 'lc-dot-live'}
                    style={{ width: 8, height: 8, borderRadius: '50%', background: apiDown ? '#d23a33' : feed ? '#267154' : '#9e9d95', color: '#267154' }}
                  />
                  {apiDown ? 'SIN CONEXIÓN CON LA API' : 'EN VIVO'} · {new Date(nowMs).toLocaleTimeString('es-EC')}
                  <span style={{ fontWeight: 500, color: elapsedSinceFeed > 10 ? '#d23a33' : undefined }}>· datos de hace {elapsedSinceFeed} s</span>
                </div>
                <div style={{ position: 'absolute', top: '12px', left: '14px', fontSize: '10.5px', color: '#787970' }}>
                  Clic en el fondo = actividad de todas las sedes
                </div>

                {/* BANNER DE ALARMAS: verde si todo funciona; luces parpadeantes si algo falla */}
                <div style={{ marginBottom: '12px', display: 'flex', justifyContent: 'center' }}>{renderAlarmas(true)}</div>

                {/* FILA SUPERIOR: LAPTOP GUAYAQUIL (su eje central baja hasta la API) */}
                {renderSite({
                  label: '💻 LAPTOP — SEDE GUAYAQUIL',
                  sub: `${findNode('guayaquil-sql')?.machine || 'Laptop (100.123.81.4)'} · 2 BDs`,
                  accent: '#183a31',
                  bg: '#f4f9f6',
                  spine: true,
                  dbs: [
                    ['guayaquil-sql', 'agente-4', 'BD 4', 'OLTP', '3306'],
                    ['guayaquil-replica', 'agente-5', 'BD 5', 'DWH', '3309'],
                  ],
                })}

                {/* FILA CENTRAL: [QUITO ── Tailscale] [API] [WAN ── CUENCA] con la API exactamente al centro */}
                <div style={{ width: '100%', display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'start' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end' }}>
                    {renderSite({
                      label: '🖥️ PC ESCRITORIO — SEDE QUITO',
                      sub: `${findNode('quito-sql')?.machine || 'PC Escritorio (100.77.220.102)'} · 3 BDs`,
                      accent: '#782c3e',
                      bg: '#fcf6f4',
                      dbs: [
                        ['quito-sql', 'agente-1', 'BD 1', 'SQL OLTP', '3307'],
                        ['quito-nosql', 'agente-2', 'BD 2', 'NoSQL', '27017'],
                        ['quito-otras', 'agente-3', 'BD 3', 'Hash', '3308'],
                      ],
                    })}
                    <div style={{ flex: 1, minWidth: '70px', marginTop: '74px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                      <span style={{ fontSize: '9px', fontWeight: 800, color: '#782c3e', background: '#fbf3f0', padding: '3px 8px', borderRadius: '999px', border: '1px solid #ead6cf', marginBottom: '5px', whiteSpace: 'nowrap' }}>
                        🔒 Túnel Tailscale
                      </span>
                      {renderFlowLine({ dir: 'h', color: '#782c3e', active: anyPulsing(['agente-1', 'agente-2', 'agente-3']) })}
                      <span style={{ fontSize: '8.5px', color: '#575950', fontWeight: 700, marginTop: '5px' }}>:3307 · :27017 · :3308</span>
                    </div>
                  </div>

                  {/* COLUMNA CENTRAL: continuación del eje de Guayaquil → API → GUI */}
                  <div style={{ alignSelf: 'stretch', display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative' }}>
                    {renderFlowLine({ dir: 'v', color: '#183a31', active: anyPulsing(['agente-4', 'agente-5']), length: '44px' })}
                    <span style={{ position: 'absolute', top: '12px', left: 'calc(50% + 10px)', fontSize: '9px', fontWeight: 700, color: '#183a31', background: '#eff5f1', padding: '2px 8px', borderRadius: '8px', whiteSpace: 'nowrap' }}>
                      X-Sede: GUAYAQUIL · GUAYAQUIL_DWH (local)
                    </span>
                    <button
                      type="button"
                      className={focusedElement === 'api-gateway' ? undefined : apiDown ? 'lc-alert-red' : apiDegraded ? 'lc-alert-amber' : undefined}
                      onClick={() => handleClickDiagramNode('api-gateway')}
                      style={{
                        width: '196px',
                        padding: '14px 12px',
                        borderRadius: '20px',
                        border: focusedElement === 'api-gateway' ? '3px solid #782c3e' : '2.5px solid #183a31',
                        background: focusedElement === 'api-gateway' ? '#183a31' : '#ffffff',
                        color: focusedElement === 'api-gateway' ? '#ffffff' : '#25251f',
                        boxShadow: anyPulsing(AGENT_IDS) ? '0 0 0 5px rgba(24,58,49,0.15), 0 0 26px rgba(24,58,49,0.45)' : '0 12px 28px rgba(24,58,49,0.16)',
                        cursor: 'pointer',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: '3px',
                        transition: 'box-shadow .3s',
                      }}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                        <Cpu size={21} color={focusedElement === 'api-gateway' ? '#e7c6a8' : '#782c3e'} />
                        <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: '22px', fontWeight: 700 }}>API</span>
                      </span>
                      <span style={{ fontSize: '10.5px', fontWeight: 700 }}>Balanceador :8000 / :8080</span>
                      {/* Una luz por réplica: verde encendida, roja parpadeante apagada */}
                      <span style={{ display: 'flex', alignItems: 'center', gap: '7px', fontSize: '9.5px', fontWeight: 700 }}>
                        {(lbStatus?.replicas ?? [1, 2, 3].map(i => ({ replica: `api_lacava_${i}`, online: !lbError }))).map((r, i) => (
                          <span key={r.replica} title={`${r.replica}: ${lbError ? 'balanceador sin respuesta' : r.online ? 'encendida' : 'APAGADA'}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                            <span
                              className={lbError || !r.online ? 'lc-blink' : undefined}
                              style={{ width: 8, height: 8, borderRadius: '50%', background: lbError || !r.online ? '#d23a33' : '#267154' }}
                            />
                            R{i + 1}
                          </span>
                        ))}
                        <span style={{ opacity: 0.85 }}>{lbError ? 'LB caído' : `${replicasOnline ?? '?'}/3`}</span>
                      </span>
                      <span style={{ fontSize: '8.5px', fontFamily: 'monospace', background: 'rgba(120,44,62,0.12)', padding: '2px 8px', borderRadius: '6px', marginTop: '2px' }}>
                        respondió: {feed?.apiReplica || globalData?.apiReplica || '…'}
                      </span>
                    </button>
                    {renderFlowLine({ dir: 'v', color: '#25251f', active: false, grow: true, length: 'auto' })}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1, minWidth: '70px', marginTop: '74px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                      <span style={{ fontSize: '9px', fontWeight: 800, color: '#a96b16', background: '#fbf4e6', padding: '3px 8px', borderRadius: '999px', border: '1px solid #ead8b8', marginBottom: '5px', whiteSpace: 'nowrap' }}>
                        ☁️ TLS WAN Internet
                      </span>
                      {renderFlowLine({ dir: 'h', color: '#a96b16', active: isPulsing('agente-6'), reverse: true })}
                      <span style={{ fontSize: '8.5px', color: '#575950', fontWeight: 700, marginTop: '5px' }}>X-Sede: CUENCA · :5432</span>
                    </div>
                    {renderSite({
                      label: '☁️ NUBE — SEDE CUENCA',
                      sub: 'PostgreSQL 18 · 1 BD',
                      accent: '#a96b16',
                      bg: '#fdf8ee',
                      dbs: [['cuenca-cloud', 'agente-6', 'BD 6', 'Cloud', '5432']],
                    })}
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  {renderFlowLine({ dir: 'v', color: '#25251f', active: false, length: '14px' })}
                  <span style={{ fontSize: '9px', fontWeight: 700, color: '#575950', margin: '3px 0' }}>▼ HTTPS / JSON · la GUI consulta cada 2 s ▼</span>
                </div>

                {/* FILA INFERIOR: GUI + POWER BI */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap', justifyContent: 'center' }}>
                  <button
                    type="button"
                    onClick={() => handleClickDiagramNode('gui-frontend')}
                    style={{
                      width: '170px', padding: '11px 14px', borderRadius: '18px',
                      border: focusedElement === 'gui-frontend' ? '3px solid #782c3e' : '2.5px solid #25251f',
                      background: focusedElement === 'gui-frontend' ? '#782c3e' : '#ffffff',
                      color: focusedElement === 'gui-frontend' ? '#ffffff' : '#25251f',
                      boxShadow: '0 8px 20px rgba(0,0,0,0.08)', cursor: 'pointer',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px',
                    }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Globe size={18} color={focusedElement === 'gui-frontend' ? '#fff' : '#183a31'} />
                      <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: '20px', fontWeight: 700 }}>GUI</span>
                    </span>
                    <span style={{ fontSize: '10px', fontWeight: 600 }}>React · solo LEE las 6 BDs</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleClickDiagramNode('power-bi')}
                    style={{
                      width: '185px', padding: '11px 14px', borderRadius: '18px',
                      border: focusedElement === 'power-bi' ? '3px solid #a96b16' : '2px dashed #a96b16',
                      background: focusedElement === 'power-bi' ? '#fbf4e6' : '#ffffff',
                      color: '#25251f', boxShadow: '0 8px 20px rgba(169,107,22,0.08)', cursor: 'pointer',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px',
                    }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#a96b16' }}>
                      <BarChart3 size={18} />
                      <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: '18px', fontWeight: 700 }}>Power BI</span>
                    </span>
                    <span style={{ fontSize: '10px', fontWeight: 600, color: '#575950' }}>Lee BD 5 (:3309) vía API</span>
                  </button>
                </div>

                {/* LEYENDA */}
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', justifyContent: 'center', marginTop: '12px', fontSize: '10.5px', color: '#575950' }}>
                  <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#267154', marginRight: 5 }} />Agente activo (operó hace &lt; 2.5 min)</span>
                  <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#a96b16', marginRight: 5 }} />Agente detenido</span>
                  <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#9a3937', marginRight: 5 }} />Sin conexión</span>
                  <span>━ línea encendida y en movimiento = una operación acaba de viajar por ese camino</span>
                </div>
              </div>
            </div>

            </div>

            {/* ==================== PANEL LATERAL FIJO: DETALLE EN VIVO DEL ELEMENTO CLICADO ==================== */}
            {/* En modo dividido el panel mide exactamente lo mismo que el diagrama (su contenido es absoluto
                y no estira la fila) y desplaza su contenido por dentro: diagrama y detalle siempre a la vista. */}
            <aside
              className={isSplit ? 'lc-side' : undefined}
              style={{
                position: 'relative',
                alignSelf: isSplit ? 'stretch' : undefined,
                minHeight: isSplit ? '560px' : undefined,
                marginTop: isSplit ? 0 : '18px',
                border: '2px solid #183a31',
                borderRadius: '14px',
                background: '#faf9f6',
                overflow: 'hidden',
              }}
            >
            <div
              style={
                isSplit
                  ? { position: 'absolute', inset: 0, overflowY: 'auto', padding: '14px' }
                  : { padding: '18px 20px' }
              }
            >
              {/* CASO 0: CLIC EN EL FONDO DEL LIENZO → ACTIVIDAD EN VIVO DE LAS 3 SEDES */}
              {focusedElement === 'cluster-global' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '10px', borderBottom: '1px solid #e9e6de', paddingBottom: '12px', marginBottom: '12px' }}>
                    <div>
                      <span style={{ fontSize: '10px', fontWeight: 800, color: '#183a31', letterSpacing: '.12em', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span className="lc-dot-live" style={{ width: 8, height: 8, borderRadius: '50%', background: '#267154', color: '#267154' }} />
                        EN VIVO · SE ACTUALIZA CADA 2 s
                      </span>
                      <h3 style={{ margin: '3px 0 0', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                        Actividad de todas las sedes (6 agentes · 6 BDs)
                      </h3>
                      <p style={{ margin: '3px 0 0', fontSize: '12px', color: '#575950' }}>
                        Cada fila es una escritura real leída de su base de datos. Las nuevas aparecen arriba resaltadas.
                      </p>
                    </div>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {(['TODAS', 'QUITO', 'GUAYAQUIL', 'CUENCA'] as const).map(f => (
                        <button
                          key={f}
                          type="button"
                          className="btn btn-outline"
                          onClick={() => setGlobalFeedFilter(f)}
                          style={{
                            padding: '5px 12px',
                            fontSize: '11.5px',
                            background: globalFeedFilter === f ? '#183a31' : '#ffffff',
                            color: globalFeedFilter === f ? '#ffffff' : '#25251f',
                          }}
                        >
                          {f === 'TODAS' ? 'Todas' : f.charAt(0) + f.slice(1).toLowerCase()}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div style={{ marginBottom: '12px' }}>{renderAlarmas(false)}</div>

                  {/* RESUMEN POR SEDE: cada agente con su cronómetro y su última acción */}
                  <div className="grid-3" style={{ marginBottom: '14px' }}>
                    {SITE_SUMMARY.map(site => {
                      const evs = (feed?.eventos ?? []).filter(e => isAgentId(e.agentId) && AGENT_SITE[e.agentId] === site.id);
                      const ultimos5 = evs.filter(e => (liveSecs(e.segundos) ?? 9999) <= 300).length;
                      return (
                        <div key={site.id} style={{ background: '#fff', border: `1px solid ${site.accent}44`, borderTop: `4px solid ${site.accent}`, borderRadius: '10px', padding: '10px 12px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '6px' }}>
                            <strong style={{ color: site.accent, fontSize: '13px' }}>{site.label}</strong>
                            <small style={{ color: '#787970' }}>{ultimos5} escrituras en 5 min</small>
                          </div>
                          {site.agents.map(aid => {
                            const ag = AGENT_DETAILS[aid];
                            const last = evs.find(e => e.agentId === aid);
                            const estado = agentEstado(aid);
                            const pulse = isPulsing(aid);
                            return (
                              <button
                                key={aid}
                                type="button"
                                onClick={() => handleClickDiagramNode(aid)}
                                style={{
                                  width: '100%', textAlign: 'left', display: 'block', cursor: 'pointer',
                                  border: 'none', borderTop: '1px solid #f0eee8', padding: '6px 2px',
                                  background: pulse ? '#fff6d6' : 'transparent', transition: 'background .4s',
                                }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11.5px' }}>
                                  <span style={{ fontWeight: 800, color: '#25251f' }}>
                                    <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', marginRight: 5, background: estado === 'ACTIVO' ? '#267154' : estado === 'INACTIVO' ? '#a96b16' : '#9a3937' }} />
                                    {ag.code} · {ag.short}
                                  </span>
                                  <span style={{ fontVariantNumeric: 'tabular-nums', color: pulse ? ag.accent : '#575950', fontWeight: 700 }}>
                                    {pulse ? '¡ahora!' : formatAgo(agentLiveSecs(aid))}
                                  </span>
                                </div>
                                <div style={{ fontSize: '10.5px', color: '#787970', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                  {last ? `${last.usuario ?? ''} · ${last.modulo ?? ''} · ${last.detalle}` : estado === 'SIN CONEXIÓN' ? 'Sin conexión con la BD' : 'Sin acciones registradas'}
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>

                  {/* LÍNEA DE TIEMPO UNIFICADA */}
                  <strong style={{ fontSize: '12px', color: '#183a31', display: 'block', margin: '2px 0 6px' }}>
                    Línea de tiempo (más reciente arriba)
                  </strong>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {(feed?.eventos ?? [])
                      .filter(e => globalFeedFilter === 'TODAS' || (isAgentId(e.agentId) && AGENT_SITE[e.agentId] === globalFeedFilter))
                      .map(e => {
                        const ag = isAgentId(e.agentId) ? AGENT_DETAILS[e.agentId] : null;
                        return (
                          <button
                            key={e.key}
                            type="button"
                            className={isNewKey(e.key) ? 'lc-row-new' : undefined}
                            onClick={() => { if (isAgentId(e.agentId)) void abrirDetalleOperacion(e.agentId, e.key.slice(e.key.indexOf(':') + 1)); }}
                            title="Ver exactamente qué hizo esta operación"
                            style={{
                              textAlign: 'left', cursor: 'pointer', background: '#fff',
                              border: '1px solid #e9e6de', borderLeft: `4px solid ${ag?.accent ?? '#9e9d95'}`,
                              borderRadius: '8px', padding: '7px 10px',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', fontSize: '11.5px' }}>
                              <span>
                                <strong style={{ color: ag?.accent ?? '#25251f' }}>{e.codigo}</strong>
                                <span style={{ color: '#787970' }}> → {e.bdId} · {e.sede}</span>
                              </span>
                              <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, color: '#575950', whiteSpace: 'nowrap' }}>
                                {formatAgo(liveSecs(e.segundos))}
                              </span>
                            </div>
                            <div style={{ fontSize: '11.5px', color: '#25251f', margin: '2px 0' }}>{e.detalle}</div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10.5px', color: '#787970' }}>
                              <span><code>{e.usuario ?? '—'}</code> · {e.modulo ?? '—'}</span>
                              <strong style={{ color: '#183a31' }}>{e.monto ? `$${e.monto.toFixed(2)}` : ''}</strong>
                            </div>
                          </button>
                        );
                      })}
                    {!feed && <div className="empty-state">Conectando con las 6 BDs…</div>}
                  </div>
                </div>
              )}

              {/* CASO 1: CLIC EN UNO DE LOS 6 AGENTES IA → ACTIVIDAD EN VIVO */}
              {focusedAgent && focusedAgentId && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '10px', borderBottom: '1px solid #e9e6de', paddingBottom: '12px', marginBottom: '12px' }}>
                    <div>
                      <span style={{ fontSize: '10px', fontWeight: 800, color: focusedAgent.accent, letterSpacing: '.12em' }}>
                        🤖 AGENTE IA · EN VIVO
                      </span>
                      <h3 style={{ margin: '3px 0 0', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                        {focusedAgent.name}
                      </h3>
                      <p style={{ margin: '3px 0 0', fontSize: '12px', color: '#575950' }}>
                        Escribe en <strong>{focusedAgent.targetDbName}</strong> · <code>{focusedAgent.script}</code>
                      </p>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                      <span
                        className={`badge ${agentEstado(focusedAgentId) === 'ACTIVO' ? 'badge-APR' : 'badge-ERR'}`}
                        style={{ fontSize: '11px', padding: '5px 11px' }}
                      >
                        {isPulsing(focusedAgentId) ? '● ESCRIBIENDO AHORA' : `${agentEstado(focusedAgentId)} · última operación ${formatAgo(agentLiveSecs(focusedAgentId))}`}
                      </span>
                      <span className="demo-badge">X-Sede: {focusedAgent.headerXSede}</span>
                      {!isStrictDba && (
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={runningAgent}
                          onClick={() => void runSingleAgent(focusedAgentId)}
                        >
                          <Play size={14} />
                          {runningAgent ? 'Ejecutando…' : 'Ejecutar 1 operación ahora'}
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="grid-2" style={{ marginBottom: '12px' }}>
                    <div style={{ background: '#ffffff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
                      <strong style={{ color: '#782c3e', fontSize: '12.5px', display: 'block', marginBottom: '4px' }}>¿Qué inserta?</strong>
                      <p style={{ fontSize: '12px', color: '#25251f', margin: 0, lineHeight: 1.55 }}>{focusedAgent.whatItDoes}</p>
                    </div>
                    <div style={{ background: '#ffffff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
                      <strong style={{ color: '#183a31', fontSize: '12.5px', display: 'block', marginBottom: '4px' }}>¿Dónde se ve?</strong>
                      <p style={{ fontSize: '12px', color: '#25251f', margin: '0 0 6px', lineHeight: 1.55 }}>{focusedAgent.whereToSeeIt}</p>
                      <div style={{ fontSize: '11.5px', color: '#575950' }}><strong>Credenciales:</strong> {focusedAgent.credentialsUsed}</div>
                    </div>
                  </div>

                  {agentRunError && (
                    <div style={{ padding: '10px', background: '#f8e9e8', border: '1px solid #e2b4b1', borderRadius: '7px', color: '#9a3937', fontSize: '12px', marginBottom: '10px' }}>
                      {agentRunError}
                    </div>
                  )}

                  {agentRun && (
                    <div style={{ background: '#eff5f1', border: '1px solid #cde0d3', borderRadius: '10px', padding: '10px 12px', marginBottom: '12px', fontSize: '12px' }}>
                      <strong style={{ color: '#183a31' }}>
                        Operación ejecutada → {agentRun.routedTo} · {agentRun.modulo} · usuario <code>{agentRun.usuarioRbac}</code> · réplica {agentRun.apiReplica} · {agentRun.latencyMs} ms
                      </strong>
                      <ul style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
                        {agentRun.impacto.map((i, idx) => (
                          <li key={idx} style={{ color: i.ok ? '#25251f' : '#9a3937' }}>
                            {i.ok ? '✔' : '✖'} <code>{i.tabla}</code> — {i.accion}{i.id !== null && i.id !== undefined ? ` (${i.id})` : ''}{i.error ? ` — ${i.error}` : ''}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {agentActivity?.error && (
                    <div style={{ padding: '10px', background: '#f8e9e8', border: '1px solid #e2b4b1', borderRadius: '7px', color: '#9a3937', fontSize: '12px', marginBottom: '10px' }}>
                      <strong>No se pudo leer {agentActivity.bdId}:</strong> {agentActivity.error}
                    </div>
                  )}

                  {agentActivity && !agentActivity.error && (
                    <>
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                        <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '8px', padding: '8px 12px' }}>
                          <small style={{ color: '#787970', display: 'block', fontSize: '10px' }}>REGISTROS TOTALES</small>
                          <strong style={{ fontSize: '16px', color: '#183a31' }}>{agentActivity.totalRegistros.toLocaleString('es-EC')}</strong>
                        </div>
                        {agentActivity.impactoTablas.map(t => (
                          <div key={t.tabla} style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '8px', padding: '8px 12px' }}>
                            <small style={{ color: '#787970', display: 'block', fontSize: '10px' }}>{t.tabla}</small>
                            <strong style={{ fontSize: '16px', color: '#782c3e' }}>{t.filas.toLocaleString('es-EC')}</strong>
                            {t.ultimoLote && <small style={{ display: 'block', fontSize: '10px', color: '#787970' }}>último lote {t.ultimoLote}</small>}
                          </div>
                        ))}
                        {agentActivity.porModulo.map(m => (
                          <div key={m.modulo} style={{ background: '#faf9f6', border: '1px dashed #d9d6cc', borderRadius: '8px', padding: '8px 12px' }}>
                            <small style={{ color: '#787970', display: 'block', fontSize: '10px' }}>{m.modulo}</small>
                            <strong style={{ fontSize: '14px' }}>{m.operaciones}</strong>
                          </div>
                        ))}
                      </div>

                      <div style={{ background: '#ffffff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                          <strong style={{ fontSize: '12.5px', color: '#183a31' }}>
                            Últimas filas que {focusedAgent.code} dejó en {agentActivity.bdId} ({agentActivity.baseDatos}) · clic en una fila para ver el detalle:
                          </strong>
                          <span style={{ fontSize: '11px', color: '#267154', fontWeight: 700 }}>
                            {agentActivity.ultimos.length} filas · {agentActivity.latencyMs} ms
                          </span>
                        </div>
                        <div className="table-scroll" style={{ maxHeight: '280px' }}>
                          <table>
                            <thead>
                              <tr>{Object.keys(agentActivity.ultimos[0] || {}).map(c => <th key={c}>{c}</th>)}</tr>
                            </thead>
                            <tbody>
                              {agentActivity.ultimos.map((r, ri) => (
                                <tr
                                  key={ri}
                                  onClick={() => void abrirDetalleOperacion(focusedAgentId, opIdDeFila(focusedAgentId, r))}
                                  title="Clic para ver exactamente qué hizo esta operación"
                                  style={{ cursor: 'pointer' }}
                                >
                                  {Object.values(r).map((v, ci) => (
                                    <td key={ci} style={{ whiteSpace: 'normal', maxWidth: '340px' }}>
                                      {v === null ? '—' : /^\d{4}-\d{2}-\d{2}T/.test(String(v)) ? String(v).replace('T', ' ').slice(0, 19) : String(v)}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                              {agentActivity.ultimos.length === 0 && (
                                <tr><td className="empty-state">Este agente todavía no ha insertado nada.</td></tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* CASO 2: EL USUARIO HIZO CLIC EN UNA DE LAS 6 BASES DE DATOS */}
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

              {/* CASO 3: EL USUARIO HIZO CLIC EN API */}
              {focusedElement === 'api-gateway' && (
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 800, color: '#782c3e', letterSpacing: '.12em' }}>
                    INSPECTOR EN VIVO DE LA CAPA MEDIA (MIDDLEWARE & BALANCEADOR)
                  </span>
                  <h3 style={{ margin: '4px 0 8px', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                    API Gateway: Balanceador Nginx Round-Robin (:8000 / :8080) + 3 Réplicas FastAPI (`api_lacava_1..3`)
                  </h3>
                  <p style={{ fontSize: '12.5px', color: '#575950', marginBottom: '12px' }}>
                    Vive en la <strong>Laptop (`100.123.81.4`)</strong>. Recibe todas las peticiones de la <strong>GUI (GitHub Pages)</strong> y de los <strong>6 Agentes IA (`AG 1..AG 6`)</strong>, lee el header obligatorio <code>X-Sede</code> y enruta la conexión por el túnel Tailscale hacia la Base de Datos correspondiente.
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

              {/* CASO 4: EL USUARIO HIZO CLIC EN GUI */}
              {focusedElement === 'gui-frontend' && (
                <div>
                  <span style={{ fontSize: '10px', fontWeight: 800, color: '#782c3e', letterSpacing: '.12em' }}>
                    INSPECTOR DE LA CAPA DE PRESENTACIÓN (CLIENTE WEB)
                  </span>
                  <h3 style={{ margin: '4px 0 8px', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                    GUI — Interfaz Web "La Cava" (React 18 + TypeScript en GitHub Pages)
                  </h3>
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

              {/* CASO 5: EL USUARIO HIZO CLIC EN POWER BI */}
              {focusedElement === 'power-bi' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px', marginBottom: '10px' }}>
                    <div>
                      <span style={{ fontSize: '10px', fontWeight: 800, color: '#a96b16', letterSpacing: '.12em' }}>
                        CUBO OLAP ESTRELLA EN VIVO · BD 5 (`db_gye_dwh` :3309) ALIMENTADO POR AGENTE 5
                      </span>
                      <h3 style={{ margin: '3px 0 0', fontSize: '19px', fontFamily: "'Playfair Display', Georgia, serif", color: '#183a31' }}>
                        📊 Vista Previa Power BI & Conexión Directa (`http://127.0.0.1:8000/api/powerbi/estrella`)
                      </h3>
                    </div>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => setActiveTab('powerbi_tab')}
                    >
                      Abrir Dashboard OLAP & Guía Power BI Completa
                    </button>
                  </div>
                  {powerBiData && (
                    <div className="grid-3">
                      {powerBiData.kpisBySede.map(k => (
                        <div key={k.sede} style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '9px', padding: '12px' }}>
                          <strong style={{ color: '#183a31' }}>Sede {k.sede} (Esquema Estrella)</strong>
                          <div style={{ fontSize: '18px', fontWeight: 800, color: '#782c3e', marginTop: '4px' }}>
                            ${Number(k.total_usd || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} USD
                          </div>
                          <small style={{ color: '#787970' }}>{k.botellas} botellas · {k.lotes_etl} lotes ETL cargados por AG 5</small>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            </aside>
            </div>
          </section>
        </div>
      )}

      {/* ==================== TAB 2: DASHBOARD OLAP & CONFIGURACIÓN POWER BI DESKTOP ==================== */}
      {activeTab === 'powerbi_tab' && (
        <div>
          <EsquemaEstrella />
          <section className="card">
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <BarChart3 size={20} color="#a96b16" />
                  Dashboard Gerencial OLAP (Esquema Estrella BD 5 `:3309`) & Conector Power BI Desktop
                </h2>
                <p>
                  El <strong>Agente 5 (`AG 5`)</strong> consolida ventas cada 60 segundos hacia <code>db_gye_dwh</code> (<code>fact_ventas</code>, <code>dim_sede</code>, <code>dim_producto</code>, <code>dim_tiempo</code>). Aquí tienes el cubo renderizado en vivo y los 2 métodos para abrirlo en <strong>Power BI Desktop</strong> en 15 segundos.
                </p>
              </div>
              <span className="demo-badge">{powerBiData?.totalFacts ?? 0} HECHOS EN ESQUEMA ESTRELLA</span>
            </div>

            {powerBiData && (
              <>
                <div className="grid-3" style={{ marginBottom: '16px' }}>
                  {powerBiData.kpisBySede.map(s => (
                    <article key={s.sede} className="card" style={{ marginBottom: 0, background: '#faf9f6', borderTop: '4px solid #183a31' }}>
                      <span style={{ fontSize: '10px', fontWeight: 800, color: '#782c3e' }}>DIMENSIÓN SEDE (`dim_sede`)</span>
                      <h3 style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: '18px', margin: '4px 0' }}>{s.sede}</h3>
                      <div style={{ fontSize: '22px', fontWeight: 800, color: '#183a31' }}>
                        ${Number(s.total_usd || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })} USD
                      </div>
                      <small style={{ color: '#787970' }}>
                        {s.botellas} botellas consolidadas · {s.lotes_etl} lotes Mini-ETL
                      </small>
                    </article>
                  ))}
                </div>

                {/* INSTRUCCIONES PASO A PASO PARA POWER BI DESKTOP */}
                <div className="grid-2" style={{ marginBottom: '16px' }}>
                  <div style={{ background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '10px', padding: '14px' }}>
                    <strong style={{ color: '#782c3e', fontSize: '13px', display: 'block', marginBottom: '6px' }}>
                      Conexión en vivo (sin drivers) — guía completa en <code>powerbi_datos/GUIA_POWER_BI.md</code>:
                    </strong>
                    <ol style={{ fontSize: '12px', color: '#25251f', margin: 0, paddingLeft: '18px', lineHeight: 1.6 }}>
                      <li>Power BI Desktop → <strong>Transformar datos → Nuevo origen → Consulta en blanco</strong>.</li>
                      <li>Pega cada bloque de <code>powerbi_datos/LaCava_PowerQuery.pq</code> en el <strong>Editor avanzado</strong> (7 consultas: <code>ApiLaCava</code>, <code>fact_ventas</code>, <code>dim_sede</code>, <code>dim_producto</code>, <code>dim_tiempo</code>, <code>operaciones_6bds</code>, <code>salud_nodos</code>).</li>
                      <li>Relaciona <code>fact_ventas</code> con las 3 dimensiones por <code>id_sede</code>, <code>id_producto</code> e <code>id_tiempo</code> (varios a uno).</li>
                      <li>Crea las medidas de <code>powerbi_datos/MEDIDAS_DAX.dax</code> y arma las 3 páginas sugeridas.</li>
                      <li>Sin API: <code>python exportar_powerbi.py</code> genera los CSV del estrella en la misma carpeta.</li>
                    </ol>
                  </div>

                  <div style={{ background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '10px', padding: '14px' }}>
                    <strong style={{ color: '#183a31', fontSize: '13px', display: 'block', marginBottom: '6px' }}>
                      Ejemplo de una consulta (tabla de hechos) — endpoints: /api/powerbi/fact_ventas · /dim/dim_sede · /dim/dim_producto · /dim/dim_tiempo · /operaciones_6bds · /salud_nodos
                    </strong>
                    <textarea
                      readOnly
                      rows={6}
                      value={`let\n    Origen = Json.Document(Web.Contents(ApiLaCava, [RelativePath = "/api/powerbi/fact_ventas"])),\n    Tabla = Table.FromRecords(Origen)\nin\n    Tabla`}
                      style={{
                        width: '100%',
                        fontFamily: 'Consolas, monospace',
                        fontSize: '11.5px',
                        background: '#132a23',
                        color: '#e8f3ec',
                        padding: '10px',
                        borderRadius: '8px',
                      }}
                    />
                  </div>
                </div>

                {/* TABLA EN VIVO DEL ESQUEMA ESTRELLA */}
                <div className="table-scroll" style={{ maxHeight: '320px' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>ID Hecho</th>
                        <th>Sede (`dim_sede`)</th>
                        <th>Producto (`dim_producto`)</th>
                        <th>Categoría</th>
                        <th>Mes (`dim_tiempo`)</th>
                        <th>Usuario RBAC</th>
                        <th>Botellas</th>
                        <th>Total Venta USD</th>
                        <th>Lote ETL (`AG 5`)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {powerBiData.starSchemaFacts.slice(0, 25).map((f, idx) => (
                        <tr key={idx}>
                          <td><code>{f.id_fact}</code></td>
                          <td><strong>{f.nombre_sede}</strong></td>
                          <td>{f.nombre_producto}</td>
                          <td>{f.categoria}</td>
                          <td>{f.mes} ({f.trimestre})</td>
                          <td><code>{f.usuario_rbac}</code></td>
                          <td><strong>{f.cantidad_botellas}</strong></td>
                          <td><strong style={{ color: '#183a31' }}>${Number(f.total_venta_usd || 0).toFixed(2)}</strong></td>
                          <td><span className="badge badge-APR">{f.etl_lote}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        </div>
      )}

      {/* ==================== TAB 3: CONSOLA GLOBAL DEL DBA (TAREA 2.2 Y 2.3) ==================== */}
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
                  Unifica en tiempo real los registros de <strong>MariaDB (:3307, :3308, :3309)</strong>, <strong>MongoDB (:27017)</strong> y <strong>PostgreSQL 18 (:5432)</strong> agregando <code>origen_nodo</code> y latencia en <code>ms</code>.
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
                  <option value="GUAYAQUIL">BD 4 · GUAYAQUIL (ERP MariaDB :3307)</option>
                  <option value="GUAYAQUIL_DWH">BD 5 · GUAYAQUIL_DWH (Estrella :3309)</option>
                  <option value="CUENCA">BD 6 · CUENCA (ERP PostgreSQL :5432)</option>
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

      {/* ==================== TAB 4: IDENTIDAD DE CADA SUCURSAL & MAPA DE 6 NODOS ==================== */}
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

      {/* ==================== TAB 5: PROMPT SQL / MONGODB DEL DBA + 17 USUARIOS ==================== */}
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

      {/* ==================== TAB 6: SIMULADOR 2PC (PREGUNTAS 4 Y 5) ==================== */}
      {activeTab === 'replicacion' && <ReplicacionDR />}
      {activeTab === 'paralelismo' && <ParalelismoReal />}
      {activeTab === 'arquitecto' && !isStrictDba && <ArquitectoSI />}

      {activeTab === 'twopc' && (
        <div>
          <section className="card">
            <div className="section-heading">
              <div>
                <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShieldCheck size={19} color="#183a31" />
                  Two-Phase Commit (2PC) real sobre los 3 ERP — BD 1 Quito (:3307), BD 4 Guayaquil (:3307) y BD 6 Cuenca (:5432)
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
                  Unidades a trasladar entre bodegas (BD 4 Guayaquil → BD 1 Quito; Cuenca registra el traslado):
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
