import React, { useCallback, useEffect, useState } from 'react';
import { Bot, Cpu, Network, Power, RefreshCw, Server } from 'lucide-react';

const configuredApiUrl = import.meta.env.VITE_API_URL?.trim();
const isGithubPages = typeof window !== 'undefined' && window.location.hostname.endsWith('github.io');
const API_BASE_URL = (
  configuredApiUrl
    ? (/^https?:\/\//i.test(configuredApiUrl) ? configuredApiUrl : `https://${configuredApiUrl}`)
    : (isGithubPages ? 'http://127.0.0.1:8000' : `http://${window.location.hostname}:8000`)
).replace(/\/$/, '');

interface MetricaReplica {
  peticionesUltimoMinuto: number;
  peticiones5min: number;
  p50ms: number | null;
  p95ms: number | null;
  errores5xx5min: number;
}

interface EstadoArquitecto {
  timestamp: string;
  balanceador: { puerto: number; algoritmo: string; online: boolean };
  replicas: Array<{ numero: number; replica: string; puerto: number; online: boolean; apagadaPorArquitecto: boolean }>;
  agentesLaptop: { script: string; corriendo: boolean; pausadosPorArquitecto: boolean };
  vigilante: { corriendo: boolean };
  metricas: {
    totalUltimoMinuto: number;
    total5min: number;
    p50ms: number | null;
    p95ms: number | null;
    errores5xx5min: number;
    failovers5min: number;
    porReplica: Record<string, MetricaReplica>;
  };
  tailscale: {
    ok: boolean;
    error?: string;
    topologia?: string;
    yo?: { host: string; ip: string };
    pares: Array<{ host: string; ip: string; online: boolean; conexion: string; direccion: string | null }>;
  };
  historial: Array<{ fecha: string; usuario: string; accion: string }>;
}

const ms = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${Math.round(v)} ms`);

const Dato: React.FC<{ etiqueta: string; valor: React.ReactNode; color?: string }> = ({ etiqueta, valor, color }) => (
  <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '8px', padding: '8px 10px', minWidth: '110px' }}>
    <small style={{ display: 'block', fontSize: '10px', color: '#787970' }}>{etiqueta}</small>
    <strong style={{ fontSize: '15px', color: color ?? '#183a31' }}>{valor}</strong>
  </div>
);

export const ArquitectoSI: React.FC = () => {
  const [estado, setEstado] = useState<EstadoArquitecto | null>(null);
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState<string>('');
  const [mensaje, setMensaje] = useState('');

  const cargar = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/lb/arquitecto/estado`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setEstado(await res.json());
      setError('');
    } catch (err) {
      setError(err instanceof Error ? `El balanceador no responde (${err.message}).` : 'El balanceador no responde.');
    }
  }, []);

  useEffect(() => {
    void cargar();
    const t = window.setInterval(() => void cargar(), 3000);
    return () => window.clearInterval(t);
  }, [cargar]);

  const accion = async (ruta: string, etiqueta: string) => {
    setOcupado(etiqueta);
    setMensaje('');
    try {
      const token = localStorage.getItem('licoreria_token');
      const res = await fetch(`${API_BASE_URL}/api/lb/arquitecto/${ruta}`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`);
      setEstado(body.estado);
      setMensaje(`✔ ${etiqueta} (usuario: ${body.usuario})`);
    } catch (err) {
      setMensaje(`✖ ${etiqueta}: ${err instanceof Error ? err.message : 'error'}`);
    } finally {
      setOcupado('');
    }
  };

  const m = estado?.metricas;
  const vivas = estado?.replicas.filter(r => r.online).length ?? 0;

  return (
    <div>
      <section className="card">
        <div className="section-heading">
          <div>
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Server size={20} color="#183a31" />
              Control del arquitecto de SI: capa de aplicación, balanceo y red
            </h2>
            <p>
              El DBA cuida <strong>cómo se guardan los datos</strong> (pestañas 3 y 7). El arquitecto opera <strong>cómo llega la información al usuario</strong>:
              réplicas de la API, balanceador, agentes y red. Las acciones son reales y quedan registradas con tu usuario.
            </p>
          </div>
          <button type="button" className="btn btn-outline" onClick={() => void cargar()}>
            <RefreshCw size={14} /> Actualizar
          </button>
        </div>

        {error && <div style={{ padding: '10px', background: '#f8e9e8', borderRadius: '8px', color: '#9a3937', fontSize: '12px', marginBottom: '10px' }}>{error}</div>}
        {mensaje && (
          <div style={{ padding: '9px 12px', borderRadius: '8px', marginBottom: '10px', fontSize: '12px', fontWeight: 700,
            background: mensaje.startsWith('✔') ? '#eff5f1' : '#f8e9e8', color: mensaje.startsWith('✔') ? '#183a31' : '#9a3937' }}>
            {mensaje}
          </div>
        )}

        {estado && m && (
          <>
            {/* BALANCEADOR + MÉTRICAS DEL SERVICIO */}
            <div style={{ background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px', marginBottom: '12px' }}>
              <strong style={{ fontSize: '12.5px', color: '#183a31', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                <Cpu size={15} /> Balanceador :{estado.balanceador.puerto} · {estado.balanceador.algoritmo} · {vivas}/3 réplicas sirviendo
              </strong>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <Dato etiqueta="Peticiones último minuto" valor={m.totalUltimoMinuto} />
                <Dato etiqueta="Tiempo de respuesta p50" valor={ms(m.p50ms)} />
                <Dato etiqueta="Tiempo de respuesta p95" valor={ms(m.p95ms)} />
                <Dato etiqueta="Errores 5xx (5 min)" valor={m.errores5xx5min} color={m.errores5xx5min ? '#9a3937' : undefined} />
                <Dato etiqueta="Failovers (5 min)" valor={m.failovers5min} color={m.failovers5min ? '#a96b16' : undefined} />
              </div>
              <p style={{ fontSize: '10.5px', color: '#787970', margin: '6px 0 0' }}>
                Medidas en el balanceador sobre las peticiones reales de los últimos 5 minutos. Son métricas del <strong>servicio</strong>, no del motor de BD.
                Un failover es una petición que llegó a una réplica caída y el balanceador la pasó a otra.
              </p>
            </div>

            {/* RÉPLICAS */}
            <div className="grid-3" style={{ marginBottom: '12px' }}>
              {estado.replicas.map(r => {
                const mr = m.porReplica[r.replica];
                const color = r.online ? '#267154' : '#9a3937';
                return (
                  <div key={r.replica} className={r.online ? undefined : 'lc-alert-red'}
                    style={{ background: '#fff', border: `1.5px solid ${color}55`, borderTop: `4px solid ${color}`, borderRadius: '10px', padding: '11px 12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '13px' }}>{r.replica} <code style={{ fontSize: '10.5px' }}>:{r.puerto}</code></strong>
                      <span style={{ fontSize: '11px', fontWeight: 800, color }}>{r.online ? 'ENCENDIDA' : 'APAGADA'}</span>
                    </div>
                    {r.apagadaPorArquitecto && <div style={{ fontSize: '10.5px', color: '#a96b16', fontWeight: 700 }}>Apagada por el arquitecto: el vigilante no la reenciende</div>}
                    <div style={{ fontSize: '11.5px', lineHeight: 1.6, margin: '6px 0 8px' }}>
                      <div>Peticiones último minuto: <strong>{mr?.peticionesUltimoMinuto ?? 0}</strong></div>
                      <div>p50 / p95: <strong>{ms(mr?.p50ms)} / {ms(mr?.p95ms)}</strong></div>
                      <div>Errores 5xx (5 min): <strong>{mr?.errores5xx5min ?? 0}</strong></div>
                    </div>
                    {r.online ? (
                      <button type="button" className="btn btn-outline" disabled={!!ocupado || vivas <= 1}
                        title={vivas <= 1 ? 'No se puede apagar la última réplica' : undefined}
                        onClick={() => void accion(`replica/${r.numero}/apagar`, `Apagar ${r.replica}`)}>
                        <Power size={14} /> {ocupado === `Apagar ${r.replica}` ? 'Apagando…' : 'Apagar'}
                      </button>
                    ) : (
                      <button type="button" className="btn btn-primary" disabled={!!ocupado}
                        onClick={() => void accion(`replica/${r.numero}/encender`, `Encender ${r.replica}`)}>
                        <Power size={14} /> {ocupado === `Encender ${r.replica}` ? 'Encendiendo… (≈ 10 s)' : 'Encender'}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="grid-2" style={{ marginBottom: '12px' }}>
              {/* AGENTES Y VIGILANTE */}
              <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
                <strong style={{ fontSize: '12.5px', color: '#782c3e', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Bot size={15} /> Agentes de la Laptop (AG 4, 5, 6 + replicación automática)
                </strong>
                <div style={{ fontSize: '12px', margin: '6px 0 8px', lineHeight: 1.6 }}>
                  Estado: <strong style={{ color: estado.agentesLaptop.corriendo ? '#267154' : '#9a3937' }}>
                    {estado.agentesLaptop.corriendo ? 'CORRIENDO' : estado.agentesLaptop.pausadosPorArquitecto ? 'PAUSADOS POR EL ARQUITECTO' : 'DETENIDOS'}
                  </strong><br />
                  Vigilante (iniciar_laptop.ps1 -Vigilar): <strong style={{ color: estado.vigilante.corriendo ? '#267154' : '#a96b16' }}>
                    {estado.vigilante.corriendo ? 'activo (reenciende lo que se caiga)' : 'no está corriendo'}
                  </strong>
                </div>
                {estado.agentesLaptop.corriendo ? (
                  <button type="button" className="btn btn-outline" disabled={!!ocupado} onClick={() => void accion('agentes/pausar', 'Pausar agentes')}>
                    {ocupado === 'Pausar agentes' ? 'Pausando…' : 'Pausar agentes'}
                  </button>
                ) : (
                  <button type="button" className="btn btn-primary" disabled={!!ocupado} onClick={() => void accion('agentes/reanudar', 'Reanudar agentes')}>
                    {ocupado === 'Reanudar agentes' ? 'Reanudando…' : 'Reanudar agentes'}
                  </button>
                )}
                <p style={{ fontSize: '10.5px', color: '#787970', margin: '6px 0 0' }}>Los agentes 1–3 corren en la PC de Escritorio y se controlan allá.</p>
              </div>

              {/* RED */}
              <div style={{ background: '#fff', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
                <strong style={{ fontSize: '12.5px', color: '#183a31', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Network size={15} /> Red Tailscale · {estado.tailscale.topologia ?? 'malla'}
                </strong>
                {estado.tailscale.ok ? (
                  <table style={{ width: '100%', fontSize: '11.5px', marginTop: '6px' }}>
                    <thead><tr><th style={{ textAlign: 'left' }}>Equipo</th><th style={{ textAlign: 'left' }}>IP</th><th style={{ textAlign: 'left' }}>Conexión</th></tr></thead>
                    <tbody>
                      {estado.tailscale.yo && (
                        <tr><td><strong>{estado.tailscale.yo.host}</strong> (esta Laptop)</td><td><code>{estado.tailscale.yo.ip}</code></td><td>—</td></tr>
                      )}
                      {estado.tailscale.pares.map(p => (
                        <tr key={p.ip}>
                          <td>{p.host} {p.online ? '' : <span style={{ color: '#9a3937' }}>(offline)</span>}</td>
                          <td><code>{p.ip}</code></td>
                          <td style={{ color: p.conexion === 'directa' ? '#267154' : '#a96b16', fontWeight: 700 }}>
                            {p.conexion}{p.direccion ? ` · ${p.direccion}` : ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div style={{ fontSize: '11.5px', color: '#9a3937', marginTop: '6px' }}>{estado.tailscale.error}</div>
                )}
                <p style={{ fontSize: '10.5px', color: '#787970', margin: '6px 0 0' }}>
                  «Directa» = WireGuard punto a punto (menor latencia). «Relay» = pasa por un servidor DERP porque las redes no permiten conexión directa.
                </p>
              </div>
            </div>

            {/* HISTORIAL */}
            <div style={{ background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
              <strong style={{ fontSize: '12.5px' }}>Historial de acciones del arquitecto</strong>
              {estado.historial.length === 0 ? (
                <div style={{ fontSize: '11.5px', color: '#787970', marginTop: '4px' }}>Todavía no hay acciones.</div>
              ) : (
                <ul style={{ margin: '6px 0 0', paddingLeft: '18px', fontSize: '11.5px' }}>
                  {estado.historial.map((h, i) => (
                    <li key={i}>{h.fecha.replace('T', ' ')} · <code>{h.usuario}</code> · {h.accion}</li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
};
