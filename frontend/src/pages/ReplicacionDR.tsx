import React, { useCallback, useEffect, useState } from 'react';
import { Cpu, Database, Play, RefreshCw, ShieldCheck, Zap } from 'lucide-react';

const configuredApiUrl = import.meta.env.VITE_API_URL?.trim();
const isGithubPages = typeof window !== 'undefined' && window.location.hostname.endsWith('github.io');
const API_BASE_URL = (
  configuredApiUrl
    ? (/^https?:\/\//i.test(configuredApiUrl) ? configuredApiUrl : `https://${configuredApiUrl}`)
    : (isGithubPages ? 'http://127.0.0.1:8000' : `http://${window.location.hostname}:8000`)
).replace(/\/$/, '');

type Celda = string | number | boolean | null;

interface EstadoEnlace {
  enlace: string;
  origen: string;
  destino: string;
  tablaReplica: string;
  origenOnline: boolean;
  destinoOnline: boolean;
  filasOrigen: number | null;
  filasReplica: number | null;
  marcaDeAgua: number | null;
  segundosDesdeUltimaCopia: number | null;
  pendientes: number | null;
  rpoSegundos: number | null;
  estado: string;
  errorOrigen?: string;
  errorDestino?: string;
}

interface LecturaFailover {
  sede: string;
  servidoDesde: 'PRIMARIA' | 'REPLICA';
  nodo: string;
  tabla: string;
  errorPrimaria?: string;
  ms: number;
  filas: Array<Record<string, Celda>>;
}

const COLOR_SEDE: Record<string, string> = { QUITO: '#782c3e', GUAYAQUIL: '#183a31', CUENCA: '#a96b16' };
const NOMBRE_SEDE: Record<string, string> = {
  QUITO: 'Quito · BD 1 (PC Escritorio)',
  GUAYAQUIL: 'Guayaquil · BD 4 (Laptop)',
  CUENCA: 'Cuenca · BD 6 (PostgreSQL)',
};

const fmtSeg = (s: number | null | undefined) => {
  if (s === null || s === undefined) return '—';
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${Math.round(s / 3600)} h`;
};

const colorDeEtiqueta = (texto: string) =>
  texto.includes('Quito') ? '#782c3e' : texto.includes('Guayaquil') ? '#183a31' : '#a96b16';

/** Etiqueta visible que marca un dato como copia de otra sucursal. */
const EtiquetaReplica: React.FC<{ texto: string }> = ({ texto }) => (
  <span style={{
    display: 'inline-block', whiteSpace: 'nowrap', fontSize: '10px', fontWeight: 800, letterSpacing: '.03em',
    color: '#fff', background: colorDeEtiqueta(texto), padding: '2px 8px', borderRadius: '999px',
  }}>
    ⧉ {texto}
  </span>
);

interface Comparacion {
  enlace: string;
  origen: { sede: string; bd: string; maquina: string; motor: string; tabla: string; ms: number; filas: Array<Record<string, Celda>> };
  replica: { sede: string; bd: string; maquina: string; motor: string; tabla: string; etiqueta: string; ms: number; filas: Array<Record<string, Celda>> };
  pendientes: number;
}

const TablaFilas: React.FC<{ filas: Array<Record<string, Celda>>; max?: number }> = ({ filas, max = 8 }) => (
  <div className="table-scroll" style={{ maxHeight: '260px' }}>
    <table>
      <thead>
        <tr>{Object.keys(filas[0] || {}).map(c => <th key={c}>{c}</th>)}</tr>
      </thead>
      <tbody>
        {filas.slice(0, max).map((f, i) => (
          <tr key={i}>
            {Object.entries(f).map(([k, v], j) => (
              <td key={j} style={{ whiteSpace: 'normal', maxWidth: '320px' }}>
                {k === 'etiqueta_replica' ? <EtiquetaReplica texto={String(v)} />
                  : v === null ? '—' : /^\d{4}-\d{2}-\d{2}T/.test(String(v)) ? String(v).replace('T', ' ').slice(0, 19) : String(v)}
              </td>
            ))}
          </tr>
        ))}
        {filas.length === 0 && <tr><td className="empty-state">Sin filas.</td></tr>}
      </tbody>
    </table>
  </div>
);

/* =============================================================================================
   REPLICACIÓN EN ANILLO + CONTINUIDAD (DR)
   ============================================================================================= */
export const ReplicacionDR: React.FC = () => {
  const [enlaces, setEnlaces] = useState<EstadoEnlace[] | null>(null);
  const [errorEstado, setErrorEstado] = useState<string>('');
  const [sincronizando, setSincronizando] = useState(false);
  const [ultimaSync, setUltimaSync] = useState<string>('');
  const [sedeLectura, setSedeLectura] = useState<'QUITO' | 'GUAYAQUIL' | 'CUENCA'>('QUITO');
  const [lectura, setLectura] = useState<LecturaFailover | null>(null);
  const [leyendo, setLeyendo] = useState(false);
  const [errorLectura, setErrorLectura] = useState('');

  const cargarEstado = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/replicacion/estado`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEnlaces(data.enlaces);
      setErrorEstado('');
    } catch (err) {
      setErrorEstado(err instanceof Error ? err.message : 'sin respuesta');
    }
  }, []);

  useEffect(() => {
    void cargarEstado();
    const t = window.setInterval(() => void cargarEstado(), 6000);
    return () => window.clearInterval(t);
  }, [cargarEstado]);

  // Visor lado a lado: origen vs réplica (por defecto Quito -> Guayaquil, la copia vive en la Laptop)
  const [origenVisor, setOrigenVisor] = useState<'QUITO' | 'GUAYAQUIL' | 'CUENCA'>('QUITO');
  const [comparacion, setComparacion] = useState<Comparacion | null>(null);
  const [errorVisor, setErrorVisor] = useState('');

  const cargarComparacion = useCallback(async (origen: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/replicacion/comparar/${origen}?limit=8`);
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`);
      setComparacion(body);
      setErrorVisor('');
    } catch (err) {
      setErrorVisor(err instanceof Error ? err.message : 'Error');
    }
  }, []);

  useEffect(() => {
    setComparacion(null);
    void cargarComparacion(origenVisor);
    const t = window.setInterval(() => void cargarComparacion(origenVisor), 3000);
    return () => window.clearInterval(t);
  }, [origenVisor, cargarComparacion]);

  const sincronizar = async () => {
    setSincronizando(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/replicacion/sincronizar`, { method: 'POST' });
      const data = await res.json();
      const total = (data.enlaces as Array<{ copiadas: number }>).reduce((a, e) => a + e.copiadas, 0);
      setUltimaSync(`${total} filas copiadas en ${data.ms} ms (réplica de la API: ${data.apiReplica})`);
      await cargarEstado();
    } catch {
      setUltimaSync('No se pudo sincronizar: API sin respuesta.');
    } finally {
      setSincronizando(false);
    }
  };

  const leer = async (simular: boolean) => {
    setLeyendo(true);
    setErrorLectura('');
    try {
      const res = await fetch(`${API_BASE_URL}/api/replicacion/leer/${sedeLectura}?limit=8${simular ? '&simularCaida=true' : ''}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setLectura(data);
    } catch (err) {
      setLectura(null);
      setErrorLectura(err instanceof Error ? err.message : 'Error');
    } finally {
      setLeyendo(false);
    }
  };

  const tarjetaEnlace = (e: EstadoEnlace) => {
    const ok = e.estado === 'SINCRONIZADO';
    const caido = e.estado.includes('CAÍDO');
    const color = ok ? '#267154' : caido ? '#9a3937' : '#a96b16';
    return (
      <div key={e.enlace} style={{ background: '#fff', border: `1.5px solid ${color}55`, borderTop: `4px solid ${color}`, borderRadius: '10px', padding: '11px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 800, fontSize: '12.5px' }}>
          <span style={{ color: COLOR_SEDE[e.origen] }}>{e.origen}</span>
          <span style={{ color: '#787970' }}>──►</span>
          <span style={{ color: COLOR_SEDE[e.destino] }}>{e.destino}</span>
        </div>
        <div className={caido ? 'lc-blink' : undefined} style={{ fontSize: '11px', fontWeight: 800, color, margin: '4px 0 6px' }}>{e.estado}</div>
        <div style={{ fontSize: '11.5px', color: '#25251f', lineHeight: 1.6 }}>
          <div>Cambios en el log del origen: <strong>{e.filasOrigen ?? '—'}</strong></div>
          <div>Cambios replicados: <strong>{e.filasReplica ?? '—'}</strong> <code style={{ fontSize: '10px' }}>({e.tablaReplica})</code></div>
          <div>Pendientes de copiar: <strong>{e.pendientes ?? '—'}</strong></div>
          <div>RPO actual (dato más viejo sin copiar): <strong>{e.pendientes ? fmtSeg(e.rpoSegundos) : '0 s'}</strong></div>
          <div>Última copia: <strong>hace {fmtSeg(e.segundosDesdeUltimaCopia)}</strong></div>
        </div>
        {(e.errorOrigen || e.errorDestino) && (
          <div style={{ fontSize: '10.5px', color: '#9a3937', marginTop: '5px' }}>{e.errorOrigen || e.errorDestino}</div>
        )}
      </div>
    );
  };

  return (
    <div>
      <section className="card">
        <div className="section-heading">
          <div>
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ShieldCheck size={20} color="#183a31" />
              Replicación en anillo y continuidad del negocio (DR)
            </h2>
            <p>
              Cada sede tiene su sistema transaccional y además guarda una <strong>réplica de la sede anterior</strong>:
              Quito ──► Guayaquil ──► Cuenca ──► Quito. Si una sede se pierde, sus datos siguen vivos en otra.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <button type="button" className="btn btn-outline" onClick={() => void cargarEstado()}>
              <RefreshCw size={14} /> Actualizar
            </button>
            <button type="button" className="btn btn-primary" disabled={sincronizando} onClick={() => void sincronizar()}>
              <Play size={14} /> {sincronizando ? 'Replicando…' : 'Sincronizar ahora'}
            </button>
          </div>
        </div>

        {/* ANILLO */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px', marginBottom: '8px' }}>
          {enlaces ? enlaces.map(tarjetaEnlace) : <div className="empty-state">{errorEstado ? `Sin respuesta de la API (${errorEstado})` : 'Leyendo estado de los 3 enlaces…'}</div>}
        </div>
        <div style={{ textAlign: 'center', fontSize: '11px', color: '#787970', marginBottom: '12px' }}>
          ↺ El anillo se cierra: Cuenca devuelve su copia a Quito. Se actualiza cada 6 s; los agentes de la Laptop replican una vez por minuto.
          {ultimaSync && <div style={{ color: '#183a31', fontWeight: 700, marginTop: '4px' }}>Última sincronización manual: {ultimaSync}</div>}
        </div>

        {/* VISOR EN VIVO: ORIGEN vs RÉPLICA */}
        <div style={{ border: '2px solid #183a31', borderRadius: '12px', padding: '12px', background: '#fff', marginBottom: '14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
            <div>
              <strong style={{ fontSize: '13.5px', color: '#183a31' }}>Ver la replicación en vivo: el dato en su sede y su copia en la otra</strong>
              <div style={{ fontSize: '11px', color: '#787970' }}>Se actualiza cada 3 s. Las filas en ámbar todavía no llegan a la réplica; llegan en la próxima ronda (o pulsa «Sincronizar ahora»).</div>
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {(['QUITO', 'GUAYAQUIL', 'CUENCA'] as const).map(s => (
                <button key={s} type="button" className="btn btn-outline" onClick={() => setOrigenVisor(s)}
                  style={{ padding: '5px 10px', fontSize: '11px', background: origenVisor === s ? COLOR_SEDE[s] : '#fff', color: origenVisor === s ? '#fff' : '#25251f' }}>
                  {s === 'QUITO' ? 'Quito → Guayaquil (recomendado)' : s === 'GUAYAQUIL' ? 'Guayaquil → Cuenca' : 'Cuenca → Quito'}
                </button>
              ))}
            </div>
          </div>
          {errorVisor && <div style={{ fontSize: '11.5px', color: '#9a3937', marginBottom: '6px' }}>{errorVisor}</div>}
          {comparacion ? (
            <div className="grid-2">
              <div>
                <div style={{ fontSize: '12px', marginBottom: '4px' }}>
                  <strong style={{ color: COLOR_SEDE[comparacion.origen.sede] }}>ORIGEN · {comparacion.origen.bd} {comparacion.origen.sede}</strong>{' '}
                  <span style={{ color: '#787970' }}>{comparacion.origen.maquina} · <code>{comparacion.origen.tabla}</code> · leído en {comparacion.origen.ms} ms</span>
                </div>
                <div className="table-scroll" style={{ maxHeight: '300px' }}>
                  <table>
                    <thead><tr><th>log_seq</th><th>Hora</th><th>Usuario</th><th>Cambio</th><th>Registro</th><th>¿En la réplica?</th></tr></thead>
                    <tbody>
                      {comparacion.origen.filas.map(f => {
                        const pend = f.estado_replica === 'pendiente';
                        return (
                          <tr key={String(f.id_op)} style={{ background: pend ? '#fff3d6' : undefined }}>
                            <td><code>{String(f.id_op)}</code></td>
                            <td>{String(f.fecha_hora ?? '').replace('T', ' ').slice(11, 19)}</td>
                            <td><code>{String(f.usuario_rbac ?? '')}</code></td>
                            <td>{String(f.modulo ?? '')}</td>
                            <td><code>{String(f.documento ?? '—')}</code></td>
                            <td style={{ fontWeight: 800, color: pend ? '#a96b16' : '#267154' }}>{pend ? '⏳ pendiente' : '✔ copiada'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', marginBottom: '4px' }}>
                  <strong style={{ color: COLOR_SEDE[comparacion.replica.sede] }}>RÉPLICA · {comparacion.replica.bd} {comparacion.replica.sede}</strong>{' '}
                  <span style={{ color: '#787970' }}>{comparacion.replica.maquina} · <code>{comparacion.replica.tabla}</code> · leído en {comparacion.replica.ms} ms</span>
                </div>
                <div className="table-scroll" style={{ maxHeight: '300px' }}>
                  <table>
                    <thead><tr><th>Etiqueta</th><th>log_seq origen</th><th>Copiada a las</th><th>Tardó</th><th>Usuario</th><th>Cambio</th><th>Registro</th></tr></thead>
                    <tbody>
                      {comparacion.replica.filas.map(f => (
                        <tr key={String(f.id_origen)}>
                          <td><EtiquetaReplica texto={String(f.etiqueta_replica)} /></td>
                          <td><code>{String(f.id_origen)}</code></td>
                          <td>{String(f.replicado_en ?? '').replace('T', ' ').slice(11, 19)}</td>
                          <td>{f.segundos_en_llegar !== null && f.segundos_en_llegar !== undefined ? fmtSeg(Number(f.segundos_en_llegar)) : '—'}</td>
                          <td><code>{String(f.usuario_rbac ?? '')}</code></td>
                          <td>{String(f.modulo ?? '')}</td>
                          <td><code>{String(f.documento ?? '—')}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            !errorVisor && <div className="empty-state">Leyendo las dos bases…</div>
          )}
          {comparacion && (
            <div style={{ fontSize: '11px', color: '#575950', marginTop: '6px' }}>
              {comparacion.pendientes > 0
                ? <>Hay <strong>{comparacion.pendientes}</strong> cambio(s) del log del origen que aún no llegan: es el retraso normal de una réplica asíncrona (RPO).</>
                : <>Todo lo reciente del origen ya está copiado en la réplica.</>}
              {' '}«Tardó» = tiempo entre que se escribió en el origen y que se copió en la réplica.
            </div>
          )}
        </div>

        <div className="grid-2" style={{ marginBottom: '14px' }}>
          <div style={{ background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
            <strong style={{ color: '#782c3e', fontSize: '12.5px' }}>Cómo funciona</strong>
            <ul style={{ fontSize: '11.5px', margin: '6px 0 0', paddingLeft: '18px', lineHeight: 1.55 }}>
              <li><strong>Log shipping lógico, asíncrono e incremental:</strong> se copia el <code>LOG_AUDITORIA</code> del ERP de cada sede (todo INSERT/UPDATE/DELETE de cualquier tabla, con su usuario y sus valores antes/después) a la tabla réplica del siguiente nodo, en orden de <code>log_seq</code> (marca de agua).</li>
              <li><strong>Idempotente:</strong> la tabla réplica usa el <code>log_seq</code> de origen como llave primaria; repetir una ronda no duplica nada. Si la sede cae, sus facturas se reconstruyen aplicando ese log (el último cambio gana).</li>
              <li><strong>¿Por qué no replicación nativa?</strong> El anillo cruza motores distintos (MariaDB ↔ PostgreSQL) y la replicación nativa de cada motor solo funciona entre motores iguales.</li>
              <li><strong>Asíncrona = RPO de segundos:</strong> lo escrito en el último minuto puede no estar aún en la réplica. Una síncrona daría RPO 0, pero cada escritura esperaría a la otra sede (más latencia).</li>
            </ul>
          </div>
          <div style={{ background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
            <strong style={{ color: '#183a31', fontSize: '12.5px' }}>Failover de lectura: si se cae una sede</strong>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', margin: '8px 0' }}>
              {(['QUITO', 'GUAYAQUIL', 'CUENCA'] as const).map(s => (
                <button key={s} type="button" className="btn btn-outline" onClick={() => setSedeLectura(s)}
                  style={{ padding: '5px 11px', fontSize: '11.5px', background: sedeLectura === s ? COLOR_SEDE[s] : '#fff', color: sedeLectura === s ? '#fff' : '#25251f' }}>
                  {s.charAt(0) + s.slice(1).toLowerCase()}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <button type="button" className="btn btn-secondary" disabled={leyendo} onClick={() => void leer(false)}>
                <Database size={14} /> Leer datos de {sedeLectura.toLowerCase()}
              </button>
              <button type="button" className="btn btn-outline" disabled={leyendo} onClick={() => void leer(true)}>
                Leer simulando caída de su BD principal
              </button>
            </div>
            <p style={{ fontSize: '10.5px', color: '#787970', margin: '6px 0 0' }}>
              Si la BD principal no responde de verdad, el primer botón cambia solo a la réplica. El segundo omite la principal a propósito, para mostrarlo sin apagar ninguna máquina.
            </p>
          </div>
        </div>

        {errorLectura && <div style={{ padding: '10px', background: '#f8e9e8', borderRadius: '8px', color: '#9a3937', fontSize: '12px', marginBottom: '10px' }}>{errorLectura}</div>}
        {lectura && (
          <div style={{ border: `2px solid ${lectura.servidoDesde === 'PRIMARIA' ? '#267154' : '#a96b16'}`, borderRadius: '10px', padding: '12px', background: '#fff', marginBottom: '14px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
              <strong style={{ fontSize: '13px', color: lectura.servidoDesde === 'PRIMARIA' ? '#267154' : '#a96b16' }}>
                Datos de {lectura.sede} servidos desde {lectura.servidoDesde === 'PRIMARIA' ? 'su BD PRINCIPAL' : `la RÉPLICA en ${NOMBRE_SEDE[lectura.nodo]}`}
              </strong>
              <span style={{ fontSize: '11px', color: '#575950' }}>tabla <code>{lectura.tabla}</code> · {lectura.ms} ms</span>
            </div>
            {lectura.errorPrimaria && <div style={{ fontSize: '11px', color: '#9a3937', marginBottom: '6px' }}>Principal: {lectura.errorPrimaria}</div>}
            <TablaFilas filas={lectura.filas} />
          </div>
        )}
      </section>

      {/* PLAN DEL DBA */}
      <section className="card">
        <div className="section-heading">
          <div>
            <h2>Plan del DBA central: continuidad, servicio e incidentes</h2>
            <p>Antes había un DBA por data center; hoy un solo DBA administra los tres desde esta consola. Este es su plan.</p>
          </div>
        </div>
        <div className="grid-2">
          <div style={{ background: '#fbf3f0', border: '1px solid #ead6cf', borderRadius: '10px', padding: '12px', fontSize: '11.5px', lineHeight: 1.55 }}>
            <strong style={{ color: '#782c3e', fontSize: '12.5px' }}>1. Plan de continuidad del negocio (BCP)</strong>
            <ul style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
              <li>Cada sede opera sola su sistema transaccional (Quito BD 1, Guayaquil BD 4, Cuenca BD 6).</li>
              <li>Cada una tiene copia en otra ciudad y otra máquina: perder un edificio no pierde sus datos.</li>
              <li><strong>Objetivos:</strong> RPO ≤ 1–2 min (una ronda de replicación); RTO de lectura ≈ 0 (failover automático); RTO de escritura &lt; 30 min (el DBA promueve la réplica).</li>
            </ul>
          </div>
          <div style={{ background: '#eff5f1', border: '1px solid #cde0d3', borderRadius: '10px', padding: '12px', fontSize: '11.5px', lineHeight: 1.55 }}>
            <strong style={{ color: '#183a31', fontSize: '12.5px' }}>2. Plan de servicio (monitoreo y SLA)</strong>
            <ul style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
              <li>Estado de las 6 BDs, la API y los 6 agentes cada 2–4 s en el diagrama, con alarmas visuales.</li>
              <li>Retraso de replicación (pendientes y RPO) visible en esta pestaña.</li>
              <li>Vigilante en la Laptop: reenciende réplicas, balanceador y agentes en ≤ 15 s.</li>
              <li>Balanceador con 3 réplicas: una caída no corta el servicio.</li>
            </ul>
          </div>
          <div style={{ background: '#fdf6e7', border: '1px solid #ead8b8', borderRadius: '10px', padding: '12px', fontSize: '11.5px', lineHeight: 1.55 }}>
            <strong style={{ color: '#a96b16', fontSize: '12.5px' }}>3. Plan de recuperación ante desastres (DRP)</strong>
            <ol style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
              <li><strong>Detectar:</strong> la BD parpadea en rojo; el enlace muestra «ORIGEN CAÍDO · RÉPLICA DISPONIBLE».</li>
              <li><strong>Contener:</strong> las lecturas pasan solas a la réplica; las escrituras de esa sede se pausan.</li>
              <li><strong>Promover:</strong> el DBA declara la réplica como principal temporal (en este prototipo es un paso manual).</li>
              <li><strong>Recuperar:</strong> al volver la sede, se copia lo nuevo de vuelta y se reanuda el anillo.</li>
              <li><strong>Revisar:</strong> se documenta la causa y cuánto tiempo y datos se perdieron frente al RPO/RTO.</li>
            </ol>
          </div>
          <div style={{ background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px', fontSize: '11.5px', lineHeight: 1.55 }}>
            <strong style={{ color: '#25251f', fontSize: '12.5px' }}>4. Actividades periódicas del DBA</strong>
            <ul style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
              <li><strong>Diario:</strong> respaldo completo de cada BD (mysqldump / pg_dump) guardado en otra sede; revisar alarmas y retraso del anillo.</li>
              <li><strong>Semanal:</strong> restaurar un respaldo de prueba (un respaldo sin probar no sirve).</li>
              <li><strong>Mensual:</strong> simulacro de caída de una sede y medir el RTO real.</li>
              <li>Altas, bajas y permisos de los 15 usuarios RBAC con mínimo privilegio.</li>
            </ul>
            <div style={{ marginTop: '6px', color: '#787970' }}>Los respaldos y simulacros periódicos son procedimiento del plan; no están automatizados en este prototipo.</div>
          </div>
        </div>
      </section>
    </div>
  );
};

/* =============================================================================================
   PARALELISMO: SOLO MEDICIONES REALES
   ============================================================================================= */
interface MedicionParalelismo {
  hardware: { maquina: string; nucleosLogicos: number; procesador: string; sistema: string };
  interNodo: { nodos: number; serieMs: number; paraleloMs: number; speedup: number };
  interConsultaMariaDB: { consultas?: number; sql?: string; serieMs?: number; paraleloMs?: number; speedup?: number; error?: string };
  intraConsulta: {
    mariadb: { version?: string; manejoHilos?: string; explicacionPoda?: Record<string, Celda>; conclusion?: string; error?: string };
    postgresql: { trabajadoresPorConsulta?: string; tamanoTabla?: string; tamanoMinimoTabla?: string; plan?: string; usaParalelismo?: boolean; conclusion?: string; error?: string };
  };
}

const Barra: React.FC<{ etiqueta: string; ms: number; max: number; color: string }> = ({ etiqueta, ms, max, color }) => (
  <div style={{ marginBottom: '6px' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11.5px' }}>
      <span>{etiqueta}</span>
      <strong>{ms.toLocaleString('es-EC')} ms</strong>
    </div>
    <div style={{ height: '10px', background: '#efede7', borderRadius: '5px' }}>
      <div style={{ width: `${Math.max(2, (ms / max) * 100)}%`, height: '100%', background: color, borderRadius: '5px' }} />
    </div>
  </div>
);

export const ParalelismoReal: React.FC = () => {
  const [m, setM] = useState<MedicionParalelismo | null>(null);
  const [midiendo, setMidiendo] = useState(false);
  const [error, setError] = useState('');

  const medir = async () => {
    setMidiendo(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE_URL}/api/paralelismo/medir`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setM(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setMidiendo(false);
    }
  };

  const b = m?.interConsultaMariaDB;
  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Cpu size={20} color="#782c3e" />
            Paralelismo: qué puede hacer de verdad nuestro clúster
          </h2>
          <p>Nada aquí está simulado: cada número sale de ejecutar las consultas en este momento. Lo que el motor no puede paralelizar se explica abajo.</p>
        </div>
        <button type="button" className="btn btn-primary" disabled={midiendo} onClick={() => void medir()}>
          <Zap size={14} /> {midiendo ? 'Midiendo (≈ 10–20 s)…' : 'Medir ahora'}
        </button>
      </div>

      {error && <div style={{ padding: '10px', background: '#f8e9e8', borderRadius: '8px', color: '#9a3937', fontSize: '12px' }}>{error}</div>}
      {!m && !error && <div className="empty-state">Pulsa «Medir ahora» para ejecutar las 3 pruebas.</div>}

      {m && (
        <>
          <div style={{ fontSize: '12px', color: '#575950', marginBottom: '12px' }}>
            Hardware de la Laptop (nodo Guayaquil + API): <strong>{m.hardware.nucleosLogicos} núcleos lógicos</strong> · {m.hardware.procesador} · {m.hardware.sistema}
          </div>
          <div className="grid-2" style={{ marginBottom: '12px' }}>
            <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
              <strong style={{ color: '#183a31', fontSize: '12.5px' }}>A. Paralelismo entre nodos (SÍ)</strong>
              <p style={{ fontSize: '11.5px', color: '#575950', margin: '4px 0 8px' }}>
                Leer las {m.interNodo.nodos} BDs una tras otra frente a las {m.interNodo.nodos} a la vez (lo que hace la consola global).
              </p>
              <Barra etiqueta="En serie" ms={m.interNodo.serieMs} max={m.interNodo.serieMs} color="#9e9d95" />
              <Barra etiqueta="En paralelo" ms={m.interNodo.paraleloMs} max={m.interNodo.serieMs} color="#267154" />
              <div style={{ fontSize: '12px', fontWeight: 800, color: '#267154' }}>Speed-up real: {m.interNodo.speedup}×</div>
              <p style={{ fontSize: '10.5px', color: '#787970', margin: '4px 0 0' }}>Cada nodo tiene su propia CPU y disco (Shared Nothing): el total tiende al nodo más lento, no a la suma.</p>
            </div>
            <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
              <strong style={{ color: '#183a31', fontSize: '12.5px' }}>B. Paralelismo entre consultas en MariaDB (SÍ)</strong>
              {b?.error ? (
                <div style={{ fontSize: '11.5px', color: '#9a3937' }}>{b.error}</div>
              ) : b && b.serieMs !== undefined && b.paraleloMs !== undefined ? (
                <>
                  <p style={{ fontSize: '11.5px', color: '#575950', margin: '4px 0 8px' }}>
                    {b.consultas} consultas que consumen CPU en BD 4 (<code>{b.sql}</code>), primero en serie y luego en {b.consultas} conexiones simultáneas.
                  </p>
                  <Barra etiqueta="En serie" ms={b.serieMs} max={b.serieMs} color="#9e9d95" />
                  <Barra etiqueta="Simultáneas" ms={b.paraleloMs} max={b.serieMs} color="#782c3e" />
                  <div style={{ fontSize: '12px', fontWeight: 800, color: '#782c3e' }}>Speed-up real: {b.speedup}×</div>
                  <p style={{ fontSize: '10.5px', color: '#787970', margin: '4px 0 0' }}>MariaDB atiende cada conexión con su propio hilo y el sistema operativo los reparte entre los núcleos.</p>
                </>
              ) : null}
            </div>
          </div>

          <div style={{ background: '#fdf6e7', border: '1px solid #ead8b8', borderRadius: '10px', padding: '12px', marginBottom: '10px' }}>
            <strong style={{ color: '#a96b16', fontSize: '12.5px' }}>C. Paralelismo dentro de UNA consulta (intra-consulta)</strong>
            <div style={{ fontSize: '11.5px', lineHeight: 1.6, marginTop: '6px' }}>
              <div><strong>MariaDB (BD 1–5; BD 4 usa {m.intraConsulta.mariadb.version ?? '—'}): NO es posible.</strong> {m.intraConsulta.mariadb.conclusion ?? m.intraConsulta.mariadb.error}</div>
              {m.intraConsulta.mariadb.explicacionPoda && (
                <div style={{ marginTop: '4px' }}>
                  EXPLAIN en BD 3 para <code>WHERE id = 42</code> → particiones leídas: <strong>{String(m.intraConsulta.mariadb.explicacionPoda.partitions ?? '—')}</strong> (de p0, p1, p2, p3).
                </div>
              )}
              <div style={{ marginTop: '8px' }}><strong>PostgreSQL (BD 6): posible, pero no aplica aquí.</strong> {m.intraConsulta.postgresql.conclusion ?? m.intraConsulta.postgresql.error}</div>
              {m.intraConsulta.postgresql.plan && (
                <pre style={{ background: '#132a23', color: '#e8f3ec', padding: '8px', borderRadius: '6px', fontSize: '10.5px', whiteSpace: 'pre-wrap', margin: '6px 0 0' }}>
                  {m.intraConsulta.postgresql.plan}
                </pre>
              )}
            </div>
          </div>
          <div style={{ fontSize: '11.5px', color: '#25251f', background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px', lineHeight: 1.6 }}>
            <strong>Conclusión para la defensa:</strong> nuestro clúster sí paraleliza <strong>entre nodos</strong> (A) y <strong>entre consultas</strong> (B), y lo medimos.
            <strong> No</strong> paraleliza <strong>dentro de una misma consulta</strong>: MariaDB no tiene esa función, y en PostgreSQL nuestras tablas son demasiado pequeñas para que el planificador la active.
            Las particiones HASH de BD 3 aceleran por poda (leer menos), no por paralelismo. No simulamos ningún paralelismo que el motor no haga.
          </div>
        </>
      )}
    </section>
  );
};
