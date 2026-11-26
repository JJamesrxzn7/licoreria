import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { KeyRound, Link2, RefreshCw, Star } from 'lucide-react';

const configuredApiUrl = import.meta.env.VITE_API_URL?.trim();
const isGithubPages = typeof window !== 'undefined' && window.location.hostname.endsWith('github.io');
const API_BASE_URL = (
  configuredApiUrl
    ? (/^https?:\/\//i.test(configuredApiUrl) ? configuredApiUrl : `https://${configuredApiUrl}`)
    : (isGithubPages ? 'http://127.0.0.1:8000' : `http://${window.location.hostname}:8000`)
).replace(/\/$/, '');

type Celda = string | number | boolean | null;
interface Columna { nombre: string; tipo: string; pk: boolean; fk: boolean }
interface Tabla { columnas: Columna[]; filas: number; muestra: Array<Record<string, Celda>> }
interface Esquema {
  baseDatos: string;
  tablas: Record<string, Tabla>;
  relaciones: Array<{ desde: string; columna: string; hacia: string; cardinalidad: string }>;
  fuentes: Array<{ fuente_dato: string; hechos: number; total: number }>;
}

const VERDE = '#183a31';
const BORGONA = '#782c3e';
const AMBAR = '#a96b16';
const FILA = 17;
const CABECERA = 44;

// Posición de cada tabla en el lienzo: los hechos en el centro y las 3 dimensiones como puntas de la estrella
const POS: Record<string, { x: number; y: number; w: number; color: string }> = {
  fact_ventas: { x: 375, y: 240, w: 250, color: BORGONA },
  dim_tiempo: { x: 385, y: 8, w: 230, color: AMBAR },
  dim_sede: { x: 10, y: 360, w: 220, color: VERDE },
  dim_producto: { x: 770, y: 360, w: 220, color: VERDE },
};

const EXPLICACION: Record<string, { rol: string; texto: string }> = {
  fact_ventas: {
    rol: 'TABLA DE HECHOS (el centro de la estrella)',
    texto: 'Una fila por cada línea de venta: guarda las MEDIDAS numéricas que se suman (botellas, subtotal, IVA, total) y '
      + 'solo las LLAVES de las dimensiones (id_sede, id_producto, id_tiempo). No repite nombres ni descripciones: eso vive en las puntas.',
  },
  dim_sede: { rol: 'DIMENSIÓN «¿DÓNDE?»', texto: 'Describe cada sucursal: nombre, ciudad, región, máquina y motor. Permite agrupar las ventas por sede.' },
  dim_producto: { rol: 'DIMENSIÓN «¿QUÉ?»', texto: 'Describe cada producto del ERP: nombre, categoría, marca y precio. Permite agrupar por categoría o marca.' },
  dim_tiempo: { rol: 'DIMENSIÓN «¿CUÁNDO?»', texto: 'Describe cada mes: año, mes, nombre y trimestre. Permite ver la evolución en el tiempo.' },
};

const SQL_EJEMPLO = `-- Una consulta OLAP típica: el hecho se une con sus dimensiones por sus llaves
SELECT s.nombre_sede, p.categoria, t.nombre_mes,
       SUM(f.cantidad_botellas) AS botellas,
       SUM(f.total_venta_usd)   AS ventas
FROM fact_ventas f
JOIN dim_sede     s ON s.id_sede     = f.id_sede      -- ¿dónde?
JOIN dim_producto p ON p.id_producto = f.id_producto  -- ¿qué?
JOIN dim_tiempo   t ON t.id_tiempo   = f.id_tiempo    -- ¿cuándo?
GROUP BY s.nombre_sede, p.categoria, t.nombre_mes;`;

const alto = (t?: Tabla) => CABECERA + (t ? t.columnas.length : 4) * FILA + 8;

export const EsquemaEstrella: React.FC = () => {
  const [esquema, setEsquema] = useState<Esquema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seleccion, setSeleccion] = useState<string>('fact_ventas');
  const [resaltada, setResaltada] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/powerbi/estrella/esquema`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setEsquema(await res.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void cargar();
    const id = window.setInterval(() => void cargar(), 10000);
    return () => window.clearInterval(id);
  }, [cargar]);

  // Punto de anclaje de una columna dentro de su caja (para que la línea salga de la FK y llegue a la PK)
  const ancla = useCallback((tabla: string, columna: string, lado: 'izq' | 'der' | 'arriba' | 'abajo') => {
    const p = POS[tabla];
    const t = esquema?.tablas[tabla];
    const i = Math.max(0, t?.columnas.findIndex(c => c.nombre === columna) ?? 0);
    const y = p.y + CABECERA + i * FILA + FILA / 2;
    if (lado === 'izq') return { x: p.x, y };
    if (lado === 'der') return { x: p.x + p.w, y };
    if (lado === 'arriba') return { x: p.x + p.w / 2, y: p.y };
    return { x: p.x + p.w / 2, y: p.y + alto(t) };
  }, [esquema]);

  const lineas = useMemo(() => {
    if (!esquema) return [];
    return [
      { hacia: 'dim_sede', col: 'id_sede', a: ancla('fact_ventas', 'id_sede', 'izq'), b: ancla('dim_sede', 'id_sede', 'der') },
      { hacia: 'dim_producto', col: 'id_producto', a: ancla('fact_ventas', 'id_producto', 'der'), b: ancla('dim_producto', 'id_producto', 'izq') },
      { hacia: 'dim_tiempo', col: 'id_tiempo', a: ancla('fact_ventas', 'id_tiempo', 'arriba'), b: ancla('dim_tiempo', 'id_tiempo', 'abajo') },
    ];
  }, [esquema, ancla]);

  const altoLienzo = esquema ? Math.max(POS.fact_ventas.y + alto(esquema.tablas.fact_ventas), POS.dim_sede.y + alto(esquema.tablas.dim_sede)) + 16 : 520;
  const tablaSel = esquema?.tablas[seleccion];
  const erp = esquema?.fuentes.find(f => f.fuente_dato === 'ERP');
  const bitacora = esquema?.fuentes.find(f => f.fuente_dato === 'BITACORA');

  const cajaTabla = (nombre: string) => {
    const p = POS[nombre];
    const t = esquema?.tablas[nombre];
    const activa = seleccion === nombre || resaltada === nombre;
    return (
      <g key={nombre} style={{ cursor: 'pointer' }} onClick={() => setSeleccion(nombre)}
        onMouseEnter={() => setResaltada(nombre)} onMouseLeave={() => setResaltada(null)}>
        <rect x={p.x} y={p.y} width={p.w} height={alto(t)} rx={10} fill="#fff" stroke={p.color} strokeWidth={activa ? 3 : 1.6}
          style={{ filter: activa ? 'drop-shadow(0 3px 8px rgba(0,0,0,.18))' : undefined }} />
        <rect x={p.x} y={p.y} width={p.w} height={CABECERA - 6} rx={10} fill={p.color} />
        <rect x={p.x} y={p.y + CABECERA - 16} width={p.w} height={10} fill={p.color} />
        <text x={p.x + 12} y={p.y + 19} fill="#fff" fontSize={14} fontWeight={800} fontFamily="Consolas, monospace">{nombre}</text>
        <text x={p.x + 12} y={p.y + 33} fill="#ffffffcc" fontSize={10.5}>
          {nombre === 'fact_ventas' ? 'HECHOS' : 'DIMENSIÓN'} · {t ? `${t.filas.toLocaleString('es-EC')} filas` : '…'}
        </text>
        {t?.columnas.map((c, i) => {
          const y = p.y + CABECERA + i * FILA + 12;
          const esLlaveRelacion = resaltada && lineas.some(l => l.hacia === resaltada && l.col === c.nombre);
          return (
            <g key={c.nombre}>
              {esLlaveRelacion && <rect x={p.x + 4} y={y - 12} width={p.w - 8} height={FILA} rx={4} fill={`${AMBAR}22`} />}
              <text x={p.x + 12} y={y} fontSize={11} fontFamily="Consolas, monospace"
                fill={c.pk ? BORGONA : c.fk ? AMBAR : '#25251f'} fontWeight={c.pk || c.fk ? 800 : 400}>
                {c.pk ? '🔑 ' : c.fk ? '🔗 ' : '   '}{c.nombre}
              </text>
              <text x={p.x + p.w - 10} y={y} fontSize={9.5} textAnchor="end" fill="#9e9d95" fontFamily="Consolas, monospace">
                {c.tipo.replace(/\(.*\)/, '')}
              </text>
            </g>
          );
        })}
      </g>
    );
  };

  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Star size={20} color={AMBAR} fill={AMBAR} />
            El esquema estrella de BD 5, dibujado desde el motor
          </h2>
          <p>
            Estructura real de <code>{esquema?.baseDatos ?? 'db_gye_dwh'}</code> leída de <code>information_schema</code> (se actualiza cada 10 s).
            La <strong>tabla de hechos</strong> va al centro y cada <strong>dimensión</strong> es una punta de la estrella, unida por su llave.
            Haz clic en una tabla para ver sus filas reales.
          </p>
        </div>
        <button type="button" className="btn btn-outline" onClick={() => void cargar()}><RefreshCw size={14} /> Actualizar</button>
      </div>

      {error && <div style={{ color: '#9a3937', fontSize: '12px', marginBottom: '8px' }}>No se pudo leer BD 5: {error}</div>}

      <div style={{ overflowX: 'auto', background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '12px' }}>
        <svg viewBox={`0 0 1000 ${altoLienzo}`} style={{ width: '100%', minWidth: '760px', display: 'block' }} role="img"
          aria-label="Diagrama del esquema estrella: fact_ventas al centro unida a dim_sede, dim_producto y dim_tiempo">
          {/* Los 3 rayos de la estrella: de cada llave (FK) del centro a la llave primaria (PK) de su dimensión */}
          {lineas.map(l => {
            const activa = resaltada === l.hacia || seleccion === l.hacia;
            const mx = (l.a.x + l.b.x) / 2;
            const my = (l.a.y + l.b.y) / 2;
            const d = l.hacia === 'dim_tiempo'
              ? `M ${l.a.x} ${l.a.y} L ${l.b.x} ${l.b.y}`
              : `M ${l.a.x} ${l.a.y} C ${mx} ${l.a.y}, ${mx} ${l.b.y}, ${l.b.x} ${l.b.y}`;
            return (
              <g key={l.hacia} onMouseEnter={() => setResaltada(l.hacia)} onMouseLeave={() => setResaltada(null)}>
                <path d={d} fill="none" stroke={activa ? AMBAR : '#9e9d95'} strokeWidth={activa ? 3.5 : 2}
                  strokeDasharray={activa ? undefined : '6 4'} />
                <circle cx={l.a.x} cy={l.a.y} r={4} fill={AMBAR} />
                <circle cx={l.b.x} cy={l.b.y} r={4} fill={BORGONA} />
                <rect x={mx - 62} y={my - 22} width={124} height={34} rx={6} fill="#fff" stroke={activa ? AMBAR : '#d9d6cd'} />
                <text x={mx} y={my - 7} textAnchor="middle" fontSize={11} fontWeight={800} fill={VERDE} fontFamily="Consolas, monospace">{l.col}</text>
                <text x={mx} y={my + 7} textAnchor="middle" fontSize={10} fill="#575950">muchas ventas → 1 ({'N:1'})</text>
              </g>
            );
          })}
          {Object.keys(POS).map(cajaTabla)}
        </svg>
      </div>

      <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', fontSize: '11px', color: '#575950', margin: '8px 0 14px' }}>
        <span><span style={{ color: BORGONA, fontWeight: 800 }}>🔑 PK</span> llave primaria (identifica la fila)</span>
        <span><span style={{ color: AMBAR, fontWeight: 800 }}>🔗 FK</span> llave que apunta a una dimensión</span>
        <span><Link2 size={11} /> pasa el mouse por una línea o tabla para resaltar la relación</span>
        {erp && (
          <span style={{ marginLeft: 'auto' }}>
            Origen de los hechos: <strong>{erp.hechos}</strong> ventas reales de los 3 ERP
            {bitacora ? <> · <strong>{bitacora.hechos}</strong> de la bitácora antigua de los agentes</> : null}
          </span>
        )}
      </div>

      <div className="grid-2">
        <div style={{ background: '#fff', border: `2px solid ${POS[seleccion]?.color ?? VERDE}`, borderRadius: '10px', padding: '12px' }}>
          <div style={{ fontSize: '10.5px', fontWeight: 800, color: POS[seleccion]?.color }}>{EXPLICACION[seleccion]?.rol}</div>
          <h3 style={{ margin: '2px 0 6px', fontFamily: 'Consolas, monospace', fontSize: '16px' }}>
            <KeyRound size={14} /> {seleccion} <span style={{ fontSize: '12px', color: '#787970' }}>· {tablaSel?.filas.toLocaleString('es-EC')} filas</span>
          </h3>
          <p style={{ fontSize: '12px', margin: '0 0 8px', lineHeight: 1.5 }}>{EXPLICACION[seleccion]?.texto}</p>
          <div className="table-scroll" style={{ maxHeight: '230px' }}>
            <table>
              <thead><tr>{tablaSel?.columnas.map(c => <th key={c.nombre}>{c.nombre}</th>)}</tr></thead>
              <tbody>
                {tablaSel?.muestra.map((f, i) => (
                  <tr key={i}>{tablaSel.columnas.map(c => <td key={c.nombre} style={{ whiteSpace: 'nowrap' }}>{String(f[c.nombre] ?? '—')}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: '10.5px', color: '#787970', marginTop: '4px' }}>
            {seleccion === 'fact_ventas' ? 'Las 5 ventas más recientes cargadas por el ETL.' : 'Primeras filas de la dimensión.'}
          </div>
        </div>
        <div style={{ background: '#faf9f6', border: '1px solid #e9e6de', borderRadius: '10px', padding: '12px' }}>
          <strong style={{ color: VERDE, fontSize: '12.5px' }}>Cómo funciona la estrella</strong>
          <ol style={{ fontSize: '11.5px', lineHeight: 1.55, paddingLeft: '18px', margin: '6px 0 8px' }}>
            <li>El <strong>ETL (Agente 5)</strong> lee cada venta nueva de los 3 ERP y deja una fila en <code>fact_ventas</code> con sus números y 3 llaves.</li>
            <li>Las <strong>dimensiones</strong> guardan una sola vez la descripción de cada sede, producto y mes (por eso tienen pocas filas).</li>
            <li>Para analizar, se une el centro con las puntas por sus llaves y se <strong>agrupa</strong> por lo que quieras: sede, categoría, mes…</li>
            <li>Power BI hace exactamente eso: relaciona <code>fact_ventas</code> con las 3 dimensiones (varios a uno) y suma las medidas.</li>
          </ol>
          <pre style={{ background: VERDE, color: '#e9f1ec', padding: '10px', borderRadius: '8px', fontSize: '10.5px', overflowX: 'auto', margin: 0 }}>{SQL_EJEMPLO}</pre>
        </div>
      </div>
    </section>
  );
};
