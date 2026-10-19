import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, ClipboardList, RefreshCw, Search } from 'lucide-react';
import { auditApi } from '../api';
import type { AuditLogEntry } from '../api';
import { useAuth } from '../context/AuthContext';
import { PaginationControls, usePagination } from '../components/Pagination';

const administratorRoles = new Set(['admin', 'administrador', 'superadministrador']);

const formatDate = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('es-EC');
};

const formatValue = (value: string | null) => value?.trim() || '—';

export default function AuditLogs() {
  const { user } = useAuth();
  const isAdministrator = Boolean(
    user?.roleIds.includes('ROL-ADMIN')
      || user?.roles.some(role => administratorRoles.has(role.trim().toLowerCase())),
  );
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const normalizedSearch = search.trim().toLowerCase();
  const filteredLogs = logs.filter(log => [
    log.id,
    log.usuario,
    log.tabla,
    log.accion,
    log.valorAnterior ?? '',
    log.valorNuevo ?? '',
  ].some(value => value.toLowerCase().includes(normalizedSearch)));
  const pagination = usePagination(filteredLogs, search);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLogs(await auditApi.listLogs());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron cargar los registros de auditoría.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdministrator) void loadLogs();
  }, [isAdministrator, loadLogs]);

  if (!isAdministrator) {
    return (
      <section className="card" role="alert">
        <h2>Acceso restringido</h2>
        <p>Solo los administradores pueden consultar la auditoría.</p>
      </section>
    );
  }

  return (
    <div className="page-container">
      <div className="page-heading">
        <div>
          <span className="eyebrow">ADMINISTRACIÓN</span>
          <h1>Auditoría del sistema</h1>
          <p>Consulta los últimos 100 eventos registrados. Esta pantalla es de solo lectura.</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => void loadLogs()} disabled={loading}>
          <RefreshCw size={16} /> {loading ? 'Actualizando...' : 'Actualizar'}
        </button>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      <section className="card">
        <div className="section-heading audit-toolbar">
          <div>
            <h2><ClipboardList size={18} /> Eventos recientes</h2>
            <p>{filteredLogs.length} registros</p>
          </div>
          <label className="search-control audit-search">
            <Search size={16} />
            <input
              type="search"
              aria-label="Buscar en registros de auditoría"
              placeholder="Buscar por usuario, tabla o acción"
              value={search}
              onChange={event => setSearch(event.target.value)}
            />
          </label>
        </div>

        <div className="table-container">
          <table className="data-table audit-table">
            <thead>
              <tr>
                <th>Fecha y hora</th>
                <th>Usuario</th>
                <th>Tabla</th>
                <th>Acción</th>
                <th>Valor anterior</th>
                <th>Valor nuevo</th>
              </tr>
            </thead>
            <tbody>
              {loading && logs.length === 0 ? (
                <tr><td colSpan={6}>Cargando registros...</td></tr>
              ) : filteredLogs.length === 0 ? (
                <tr><td colSpan={6}>{logs.length === 0 ? 'No hay registros de auditoría.' : 'No hay coincidencias.'}</td></tr>
              ) : pagination.pageItems.map(log => (
                <tr key={log.id}>
                  <td>{formatDate(log.fechaHora)}</td>
                  <td>{log.usuario}</td>
                  <td>{log.tabla}</td>
                  <td><span className="audit-action">{log.accion}</span></td>
                  <td className="audit-value">{formatValue(log.valorAnterior)}</td>
                  <td className="audit-value">{formatValue(log.valorNuevo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <PaginationControls
          page={pagination.page}
          pageCount={pagination.pageCount}
          firstItem={pagination.firstItem}
          lastItem={pagination.lastItem}
          totalItems={filteredLogs.length}
          onPageChange={pagination.setPage}
        />
      </section>
    </div>
  );
}
