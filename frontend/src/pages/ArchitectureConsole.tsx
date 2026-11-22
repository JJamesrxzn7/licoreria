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
  | 'power-bi';

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
    targetDbName: 'BD 1 · MariaDB Quito (:3307)',
    whatItDoes:
      'Cada 60 s elige uno de los 15 usuarios RBAC y un módulo al azar, y hace POST /api/agentes/operacion con X-Sede: QUITO. La API guarda la operación en `operaciones_agentes_ia` y además escribe en la tabla de negocio del módulo: VENTAS → `facturas`, COMPRAS → `compras`, CONTABILIDAD → `asientos`, INVENTARIOS → +2 de stock en `productos`. TALENTO HUMANO solo queda en la bitácora.',
    whereToSeeIt:
      'No escribe en la interfaz: escribe en BD 1. Lo ves aquí (tabla de abajo), en la pestaña 4 "Monitor Global" y en la Terminal DBA sobre BD 1. Las filas que crea llevan prefijo AGF-Q-, AGC-Q- y AGA-Q-.',
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
    targetDbName: 'BD 4 · MariaDB Guayaquil (:3306)',
    whatItDoes:
      'Igual que el Agente 1 pero contra BD 4: cada 60 s un usuario RBAC al azar registra una operación en `operaciones_agentes_ia` y la API la replica en `facturas`, `compras`, `asientos` o el stock de `productos` según el módulo.',
    whereToSeeIt:
      'Lo ves aquí, en el Monitor Global y en la Terminal DBA sobre BD 4. Las filas que crea llevan prefijo AGF-G-, AGC-G- y AGA-G-.',
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
      'Cada 60 s ejecuta un ETL incremental real: EXTRAE las ventas nuevas de BD 1, BD 4 y BD 6 (id_op > marca de agua guardada en `etl_control`), las TRANSFORMA (producto, botellas = monto / precio, IVA 15 %, mes) y las CARGA en `fact_ventas`. Si un nodo está caído, lo salta y lo recupera en la siguiente corrida.',
    whereToSeeIt:
      'Lo ves aquí (lotes ETL y marcas de agua), en la pestaña 2 "Power BI" y en Power BI Desktop, que lee `fact_ventas` + `dim_*`.',
    credentialsUsed: 'Usuarios de Ventas y Contabilidad (v_*, ctbl_*)',
    accent: '#183a31',
  },
  'agente-6': {
    code: 'AG 6',
    short: 'Cloud WAN',
    name: 'Agente 6 — Transacciones en la nube (Cuenca)',
    script: 'agentes_gye_cuenca.py (corre en la Laptop)',
    headerXSede: 'CUENCA',
    targetDbId: 'cuenca-cloud',
    targetDbName: 'BD 6 · PostgreSQL Supabase (:5432)',
    whatItDoes:
      'Cada 60 s inserta una operación en `operaciones_agentes_cloud` de Supabase y mide la latencia WAN (latencia_wan_ms). Si el módulo es VENTAS, además crea una factura en `frag_austral_facturas`.',
    whereToSeeIt:
      'Lo ves aquí, en el Monitor Global y en la Terminal DBA sobre BD 6. Compara su latencia con la de los nodos por Tailscale.',
    credentialsUsed: '15 usuarios RBAC replicados en Cuenca Cloud',
    accent: '#a96b16',
  },
};

const AGENT_IDS = Object.keys(AGENT_DETAILS) as AgentId[];

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
    databases: '2 Bases de Datos: BD 4 MariaDB Local OLTP (:3306) · BD 5 MariaDB DWH Estrella (:3309)',
    agents: 'Agente 4 (BD 4) · Agente 5 Mini-ETL (BD 5) + Nginx LB & 3 Réplicas API',
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
    agents: 'Agente 6 (BD 6) · Medición de Latencia WAN en Tiempo Real',
  },
];

export const ArchitectureConsole: React.FC = () => {
  const { user } = useAuth();
  const isStrictDba = isDbaUser(user) && !isSuperAdmin(user);
  const [activeTab, setActiveTab] = useState<'diagram_vs' | 'powerbi_tab' | 'global_dba' | 'board' | 'dba_prompt' | 'twopc'>('diagram_vs');
  const [topology, setTopology] = useState<TopologyResponse | null>(null);
  const [loadingTopo, setLoadingTopo] = useState(false);

  // Elemento interactivo seleccionado en el Diagrama Visual
  const [focusedElement, setFocusedElement] = useState<InteractiveElementId>('cuenca-cloud');

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
  const [agentStatus, setAgentStatus] = useState<Partial<Record<AgentId, AgentActivity>>>({});
  const [agentActivity, setAgentActivity] = useState<AgentActivity | null>(null);
  const [agentRun, setAgentRun] = useState<AgentRunResult | null>(null);
  const [agentRunError, setAgentRunError] = useState<string>('');
  const [runningAgent, setRunningAgent] = useState<boolean>(false);

  const fetchAgentStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/agentes/estado`);
      if (res.ok) {
        const data: { agentes: AgentActivity[] } = await res.json();
        const map: Partial<Record<AgentId, AgentActivity>> = {};
        data.agentes.forEach(a => {
          if (isAgentId(a.agentId)) map[a.agentId] = a;
        });
        setAgentStatus(map);
      }
    } catch {
      // API no disponible momentáneamente
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

  useEffect(() => {
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

  // Estado de los 6 agentes (punto verde/ámbar en cada tarjeta) cada 15 s mientras se ve el diagrama
  useEffect(() => {
    if (activeTab !== 'diagram_vs') return undefined;
    void fetchAgentStatus();
    const t = window.setInterval(() => void fetchAgentStatus(), 15000);
    return () => window.clearInterval(t);
  }, [activeTab, fetchAgentStatus]);

  // Actividad del agente seleccionado cada 10 s
  useEffect(() => {
    if (activeTab !== 'diagram_vs' || !isAgentId(focusedElement)) return undefined;
    const id = focusedElement;
    const t = window.setInterval(() => void fetchAgentActivity(id), 10000);
    return () => window.clearInterval(t);
  }, [activeTab, focusedElement, fetchAgentActivity]);

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
      await fetchAgentStatus();
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
  const focusedAgentId: AgentId | null = isAgentId(focusedElement) ? focusedElement : null;
  const focusedAgent = focusedAgentId ? AGENT_DETAILS[focusedAgentId] : null;
  const findNode = (id: string) => topology?.nodes.find(n => n.id === id);

  // ---------- Piezas del lienzo: caja de BD, tarjeta de Agente (separada) y bloque de sede ----------
  const COL_W = 108;
  const COL_GAP = 14;

  const renderDbBox = (nodeId: InteractiveElementId, bdLabel: string, roleShort: string, portStr: string) => {
    const n = findNode(nodeId);
    const isOnline = !n || n.status === 'ONLINE';
    const isDbFocused = focusedElement === nodeId;
    return (
      <button
        key={nodeId}
        type="button"
        onClick={() => handleClickDiagramNode(nodeId)}
        title={n ? `${n.name} — ${n.status}` : bdLabel}
        style={{
          width: `${COL_W}px`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '4px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          padding: 0,
        }}
      >
        <div
          style={{
            width: '86px',
            height: '80px',
            borderRadius: '16px',
            border: isDbFocused ? '3px solid #782c3e' : isOnline ? '2px solid #25251f' : '2.5px solid #9a3937',
            background: isDbFocused ? '#fbf3f0' : isOnline ? '#ffffff' : '#f8e9e8',
            boxShadow: isDbFocused ? '0 8px 20px rgba(120,44,62,0.22)' : '0 3px 10px rgba(0,0,0,0.06)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
            transition: 'all 0.15s ease',
          }}
        >
          <span
            style={{
              position: 'absolute', top: '7px', right: '7px', width: '9px', height: '9px', borderRadius: '50%',
              background: isOnline ? '#267154' : '#9a3937',
            }}
          />
          <Database size={21} color={isOnline ? '#183a31' : '#9a3937'} />
          <strong style={{ fontSize: '11.5px', color: '#25251f', marginTop: '3px' }}>{bdLabel}</strong>
          <code style={{ fontSize: '9.5px', color: '#782c3e', fontWeight: 700 }}>:{n?.actualPort || portStr}</code>
        </div>
        <span style={{ fontSize: '12px', fontWeight: 700, color: '#25251f' }}>{roleShort}</span>
        <span style={{ fontSize: '10px', fontWeight: 700, color: isOnline ? '#267154' : '#9a3937' }}>
          {n ? (isOnline ? `${n.latencyMs} ms` : 'OFFLINE') : '…'}
        </span>
      </button>
    );
  };

  const renderAgentCard = (agentId: AgentId) => {
    const ag = AGENT_DETAILS[agentId];
    const st = agentStatus[agentId];
    const focused = focusedElement === agentId;
    const color = !st ? '#9e9d95' : st.estado === 'ACTIVO' ? '#267154' : st.estado === 'INACTIVO' ? '#a96b16' : '#9a3937';
    return (
      <div key={agentId} style={{ width: `${COL_W}px`, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {/* conector punteado: el agente escribe en la BD de arriba (vía API + X-Sede) */}
        <div style={{ width: '2px', height: '20px', background: `repeating-linear-gradient(to bottom, ${ag.accent} 0, ${ag.accent} 4px, transparent 4px, transparent 7px)` }} />
        <button
          type="button"
          onClick={() => handleClickDiagramNode(agentId)}
          title={`${ag.name}: clic para ver qué está insertando`}
          style={{
            width: '100%',
            padding: '7px 6px',
            borderRadius: '12px',
            border: focused ? `2px solid ${ag.accent}` : '1.5px solid #d9d6cc',
            background: focused ? ag.accent : '#ffffff',
            color: focused ? '#ffffff' : '#25251f',
            boxShadow: focused ? `0 6px 16px ${ag.accent}40` : '0 2px 6px rgba(0,0,0,0.05)',
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '2px',
            transition: 'all 0.15s ease',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px', fontWeight: 800 }}>
            <Bot size={14} color={focused ? '#ffffff' : ag.accent} />
            {ag.code}
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, boxShadow: `0 0 0 2px ${focused ? '#ffffff55' : color + '33'}` }} />
          </span>
          <span style={{ fontSize: '10.5px', fontWeight: 600, opacity: 0.9 }}>{ag.short}</span>
          <span style={{ fontSize: '9.5px', opacity: 0.85 }}>
            {st ? (st.nodoOnline ? formatAgo(st.segundosDesdeUltima) : 'sin conexión') : '…'}
          </span>
        </button>
      </div>
    );
  };

  type SiteDb = [InteractiveElementId, AgentId, string, string, string];

  const renderSite = (opts: {
    label: string;
    sub: string;
    accent: string;
    bg: string;
    border: string;
    dbs: SiteDb[];
  }) => {
    const cols = `repeat(${opts.dbs.length}, ${COL_W}px)`;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {/* RECUADRO DE LA MÁQUINA: SOLO CONTIENE SUS BASES DE DATOS */}
        <div style={{ border: `2px solid ${opts.accent}`, borderRadius: '16px', background: opts.bg, padding: '10px 14px 12px', boxShadow: '0 6px 18px rgba(0,0,0,0.05)' }}>
          <div style={{ textAlign: 'center', marginBottom: '10px' }}>
            <div style={{ fontSize: '10.5px', fontWeight: 800, color: opts.accent, letterSpacing: '.06em' }}>{opts.label}</div>
            <div style={{ fontSize: '9.5px', color: '#787970', fontFamily: 'monospace' }}>{opts.sub}</div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: cols, gap: `${COL_GAP}px`, justifyItems: 'center' }}>
            {opts.dbs.map(([nodeId, , bd, role, port]) => renderDbBox(nodeId, bd, role, port))}
          </div>
        </div>
        {/* CARRIL DE AGENTES: FUERA DEL RECUADRO, UNO DEBAJO DE CADA BD */}
        <div style={{ display: 'grid', gridTemplateColumns: cols, gap: `${COL_GAP}px`, justifyItems: 'center', padding: '0 16px' }}>
          {opts.dbs.map(([, agentId]) => renderAgentCard(agentId))}
        </div>
      </div>
    );
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
      await Promise.all([fetchAgentActivity(agentId), fetchAgentStatus()]);
    } catch (err) {
      setAgentRunError(err instanceof Error ? err.message : 'Error de red.');
    } finally {
      setRunningAgent(false);
    }
  };

  return (
    <div>
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
                  Cada Base de Datos tiene su propio <strong>Agente IA independiente (`AG 1` a `AG 6`)</strong> justo debajo. Haz clic en cualquier <strong>BD</strong> o en cualquier <strong>Agente (`AG 1..6`)</strong> para ver exactamente qué está ingresando.
                </p>
              </div>
              <span className="demo-badge">1 AGENTE IA POR CADA BASE DE DATOS</span>
            </div>

            {/* ==================== LIENZO: SEDES (SOLO BDs) + CARRIL DE AGENTES APARTE + API + GUI ==================== */}
            <div style={{ overflowX: 'auto' }}>
              <div
                style={{
                  minWidth: '980px',
                  background: 'radial-gradient(circle at 50% 45%, #ffffff 0%, #f6f4ef 100%)',
                  border: '1.5px solid #dfded7',
                  borderRadius: '16px',
                  padding: '22px 20px 18px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                {/* FILA SUPERIOR: LAPTOP GUAYAQUIL */}
                {renderSite({
                  label: '💻 LAPTOP — SEDE GUAYAQUIL',
                  sub: `${findNode('guayaquil-sql')?.machine || 'Laptop (100.123.81.4)'} · 2 BDs`,
                  accent: '#183a31',
                  bg: '#f4f9f6',
                  border: '#cde0d3',
                  dbs: [
                    ['guayaquil-sql', 'agente-4', 'BD 4', 'OLTP', '3306'],
                    ['guayaquil-replica', 'agente-5', 'BD 5', 'DWH', '3309'],
                  ],
                })}

                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', margin: '2px 0' }}>
                  <div style={{ width: '2.5px', height: '18px', background: 'repeating-linear-gradient(to bottom, #183a31 0, #183a31 5px, transparent 5px, transparent 9px)' }} />
                  <span style={{ fontSize: '9.5px', fontWeight: 700, color: '#183a31', background: '#eff5f1', padding: '2px 8px', borderRadius: '8px' }}>
                    ▼ X-Sede: GUAYAQUIL · GUAYAQUIL_DWH (local)
                  </span>
                </div>

                {/* FILA CENTRAL: QUITO ── TAILSCALE ── API ── TLS WAN ── CUENCA */}
                <div
                  style={{
                    width: '100%',
                    display: 'grid',
                    gridTemplateColumns: 'auto minmax(110px, 1fr) auto minmax(110px, 1fr) auto',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  {renderSite({
                    label: '🖥️ PC ESCRITORIO — SEDE QUITO',
                    sub: `${findNode('quito-sql')?.machine || 'PC Escritorio (100.77.220.102)'} · 3 BDs`,
                    accent: '#782c3e',
                    bg: '#fcf6f4',
                    border: '#ead6cf',
                    dbs: [
                      ['quito-sql', 'agente-1', 'BD 1', 'SQL OLTP', '3307'],
                      ['quito-nosql', 'agente-2', 'BD 2', 'NoSQL', '27017'],
                      ['quito-otras', 'agente-3', 'BD 3', 'Hash', '3308'],
                    ],
                  })}

                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                    <span style={{ fontSize: '9px', fontWeight: 800, color: '#782c3e', background: '#fbf3f0', padding: '3px 8px', borderRadius: '999px', border: '1px solid #ead6cf', marginBottom: '4px', whiteSpace: 'nowrap' }}>
                      🔒 Túnel Tailscale
                    </span>
                    <div style={{ width: '100%', height: '3px', background: 'repeating-linear-gradient(to right, #782c3e 0, #782c3e 6px, transparent 6px, transparent 10px)' }} />
                    <span style={{ fontSize: '8.5px', color: '#575950', fontWeight: 700, marginTop: '4px', textAlign: 'center' }}>
                      :3307 · :27017 · :3308
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleClickDiagramNode('api-gateway')}
                    style={{
                      width: '196px',
                      padding: '14px 12px',
                      borderRadius: '20px',
                      border: focusedElement === 'api-gateway' ? '3px solid #782c3e' : '2.5px solid #183a31',
                      background: focusedElement === 'api-gateway' ? '#183a31' : '#ffffff',
                      color: focusedElement === 'api-gateway' ? '#ffffff' : '#25251f',
                      boxShadow: '0 12px 28px rgba(24,58,49,0.16)',
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: '3px',
                    }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                      <Cpu size={21} color={focusedElement === 'api-gateway' ? '#e7c6a8' : '#782c3e'} />
                      <span style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: '22px', fontWeight: 700 }}>API</span>
                    </span>
                    <span style={{ fontSize: '10.5px', fontWeight: 700 }}>Balanceador :8000 / :8080</span>
                    <span style={{ fontSize: '9.5px', opacity: 0.9 }}>3 réplicas · enruta por X-Sede</span>
                    <span style={{ fontSize: '8.5px', fontFamily: 'monospace', background: 'rgba(120,44,62,0.12)', padding: '2px 8px', borderRadius: '6px', marginTop: '2px' }}>
                      respondió: {globalData?.apiReplica || topology?.apiReplica || '…'}
                    </span>
                  </button>

                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                    <span style={{ fontSize: '9px', fontWeight: 800, color: '#a96b16', background: '#fbf4e6', padding: '3px 8px', borderRadius: '999px', border: '1px solid #ead8b8', marginBottom: '4px', whiteSpace: 'nowrap' }}>
                      ☁️ TLS WAN Internet
                    </span>
                    <div style={{ width: '100%', height: '3px', background: 'repeating-linear-gradient(to right, #a96b16 0, #a96b16 6px, transparent 6px, transparent 10px)' }} />
                    <span style={{ fontSize: '8.5px', color: '#575950', fontWeight: 700, marginTop: '4px' }}>X-Sede: CUENCA · :5432</span>
                  </div>

                  {renderSite({
                    label: '☁️ NUBE — SEDE CUENCA',
                    sub: 'Supabase DBaaS · 1 BD',
                    accent: '#a96b16',
                    bg: '#fdf8ee',
                    border: '#ead8b8',
                    dbs: [['cuenca-cloud', 'agente-6', 'BD 6', 'Cloud', '5432']],
                  })}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', margin: '4px 0' }}>
                  <div style={{ width: '2.5px', height: '18px', background: '#183a31' }} />
                  <span style={{ fontSize: '9px', fontWeight: 700, color: '#575950' }}>▼ HTTPS / JSON ▼</span>
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
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', justifyContent: 'center', marginTop: '10px', fontSize: '10.5px', color: '#575950' }}>
                  <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#267154', marginRight: 5 }} />Agente activo (operó hace &lt; 2.5 min)</span>
                  <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#a96b16', marginRight: 5 }} />Agente detenido</span>
                  <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#9a3937', marginRight: 5 }} />BD sin conexión</span>
                  <span>┆ línea punteada = el agente escribe en esa BD (envía HTTP a la API con su X-Sede)</span>
                </div>
              </div>
            </div>

            {/* ==================== PANEL INSPECTOR DINÁMICO DEL ELEMENTO CLICADO ==================== */}
            <div
              style={{
                marginTop: '18px',
                border: '2px solid #183a31',
                borderRadius: '14px',
                background: '#faf9f6',
                padding: '18px 20px',
              }}
            >
              {/* CASO 1: CLIC EN UNO DE LOS 6 AGENTES IA → ACTIVIDAD EN VIVO */}
              {focusedAgent && focusedAgentId && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '10px', borderBottom: '1px solid #e9e6de', paddingBottom: '12px', marginBottom: '12px' }}>
                    <div>
                      <span style={{ fontSize: '10px', fontWeight: 800, color: focusedAgent.accent, letterSpacing: '.12em' }}>
                        🤖 AGENTE IA · SE ACTUALIZA CADA 10 s
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
                        className={`badge ${agentActivity?.estado === 'ACTIVO' ? 'badge-APR' : 'badge-ERR'}`}
                        style={{ fontSize: '11px', padding: '5px 11px' }}
                      >
                        {agentActivity ? `${agentActivity.estado} · última operación ${formatAgo(agentActivity.segundosDesdeUltima)}` : 'Cargando…'}
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
                            Últimas filas que {focusedAgent.code} dejó en {agentActivity.bdId} ({agentActivity.baseDatos}):
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
                                <tr key={ri}>
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
          </section>
        </div>
      )}

      {/* ==================== TAB 2: DASHBOARD OLAP & CONFIGURACIÓN POWER BI DESKTOP ==================== */}
      {activeTab === 'powerbi_tab' && (
        <div>
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
