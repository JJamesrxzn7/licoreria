import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, Edit3, Eye, EyeOff, RefreshCw, Shield, Trash2, UserPlus } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { rolesApi, usuariosApi } from '../api';
import type { Rol, Usuario, UsuarioRol } from '../api';
import { PaginationControls, usePagination } from '../components/Pagination';

type UsuariosProps = {
  onCreate: () => void;
};

export default function Usuarios({ onCreate }: UsuariosProps) {
  const { user, hasPermission } = useAuth();
  const isUserManager = Boolean(
    user?.roles.some(role => ['admin', 'administrador', 'superadministrador', 'jefe_talento_humano'].includes(role.trim().toLowerCase()))
      || hasPermission('PRM-USU'),
  );
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [roles, setRoles] = useState<Rol[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewingRoles, setViewingRoles] = useState<string | null>(null);
  const [usuarioRoles, setUsuarioRoles] = useState<UsuarioRol[]>([]);
  const [editingUsuario, setEditingUsuario] = useState<Usuario | null>(null);
  const [usernameEdit, setUsernameEdit] = useState('');
  const [passwordEdit, setPasswordEdit] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const pagination = usePagination(usuarios);

  const cargarUsuarios = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [usuariosActualizados, rolesActualizados] = await Promise.all([
        usuariosApi.listar(),
        rolesApi.listar(),
      ]);
      setUsuarios(usuariosActualizados);
      setRoles(rolesActualizados.filter(role => role.estado === 'ACT'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cargar la lista de usuarios.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isUserManager) void cargarUsuarios();
  }, [cargarUsuarios, isUserManager]);

  const handleCambiarEstado = async (usuario: Usuario) => {
    const nuevoEstado = usuario.ESTADO_USR === 'ACT' ? 'INA' : 'ACT';
    const accion = nuevoEstado === 'ACT' ? 'activar' : 'desactivar';
    if (!window.confirm(`¿Está seguro de ${accion} a ${usuario.username}?`)) return;

    setError(null);
    setSuccess(null);
    try {
      await usuariosApi.actualizar(usuario.id_Usuario, { ESTADO_USR: nuevoEstado });
      setSuccess(`Usuario ${nuevoEstado === 'ACT' ? 'activado' : 'desactivado'} exitosamente.`);
      await cargarUsuarios();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cambiar el estado del usuario.');
    }
  };

  const guardarUsuario = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingUsuario) return;
    setError(null);
    setSuccess(null);
    try {
      await usuariosApi.actualizar(editingUsuario.id_Usuario, {
        username: usernameEdit.trim(),
        ...(passwordEdit ? { password: passwordEdit } : {}),
      });
      setEditingUsuario(null);
      setPasswordEdit('');
      setSuccess('Usuario actualizado exitosamente.');
      await cargarUsuarios();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo actualizar el usuario.');
    }
  };

  const verRoles = async (usuarioId: string) => {
    setError(null);
    try {
      const rolesAsignados = await usuariosApi.obtenerRoles(usuarioId);
      setUsuarioRoles(rolesAsignados);
      setViewingRoles(usuarioId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron cargar los roles del usuario.');
    }
  };

  const cerrarRoles = () => {
    setViewingRoles(null);
    setUsuarioRoles([]);
  };

  const actualizarRolesVisibles = async (usuarioId: string) => {
    const [rolesAsignados, usuariosActualizados] = await Promise.all([
      usuariosApi.obtenerRoles(usuarioId),
      usuariosApi.listar(),
    ]);
    setUsuarioRoles(rolesAsignados);
    setUsuarios(usuariosActualizados);
  };

  const handleAsignarRol = async (rolId: string) => {
    if (!viewingRoles) return;
    setError(null);
    try {
      await usuariosApi.asignarRol(viewingRoles, rolId);
      setSuccess('Rol asignado exitosamente.');
      try {
        await actualizarRolesVisibles(viewingRoles);
      } catch (err) {
        setError(err instanceof Error ? `Rol asignado, pero no se pudo actualizar la vista: ${err.message}` : 'Rol asignado, pero no se pudo actualizar la vista.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo asignar el rol.');
    }
  };

  const handleRemoverRol = async (rolId: string) => {
    if (!viewingRoles) return;
    setError(null);
    try {
      await usuariosApi.removerRol(viewingRoles, rolId);
      setSuccess('Rol removido exitosamente.');
      try {
        await actualizarRolesVisibles(viewingRoles);
      } catch (err) {
        setError(err instanceof Error ? `Rol removido, pero no se pudo actualizar la vista: ${err.message}` : 'Rol removido, pero no se pudo actualizar la vista.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo remover el rol.');
    }
  };

  if (!isUserManager) {
    return (
      <section className="card" role="alert">
        <h2>Acceso restringido</h2>
        <p>No tienes permiso para administrar usuarios.</p>
      </section>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>Gestión de usuarios</h1>
        <p>Administra las cuentas, aprueba solicitudes y asigna roles del sistema.</p>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          <AlertCircle size={16} />
          {error}
        </div>
      )}
      {success && (
        <div className="alert alert-error" role="status" style={{ background: 'rgba(38, 113, 84, 0.08)', color: '#267154', borderColor: 'rgba(38, 113, 84, 0.2)' }}>
          <Shield size={16} />
          {success}
        </div>
      )}

      <div className="usuarios-toolbar">
        <button type="button" className="btn-primary" onClick={onCreate}>
          <UserPlus size={18} /> Nuevo usuario
        </button>
        <button type="button" className="btn-secondary" onClick={() => void cargarUsuarios()} disabled={loading}>
          <RefreshCw size={16} /> Actualizar
        </button>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Empleado</th>
              <th>Departamento</th>
              <th>Roles</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6}>Cargando usuarios...</td></tr>
            ) : usuarios.length === 0 ? (
              <tr><td colSpan={6}>No hay usuarios registrados.</td></tr>
            ) : pagination.pageItems.map(usuario => (
              <tr key={usuario.id_Usuario}>
                <td>{usuario.username}</td>
                <td>{[usuario.emp_Nombre1, usuario.emp_Apellido1].filter(Boolean).join(' ') || '-'}</td>
                <td>{usuario.dep_Nombre || '-'}</td>
                <td>
                  <span className="roles-badge">
                    {usuario.roles.length > 0
                      ? usuario.roles.map(role => <span key={role} className="role-badge">{role}</span>)
                      : <span className="role-badge">Sin roles</span>}
                  </span>
                </td>
                <td>
                  <span className={`status-badge ${usuario.ESTADO_USR === 'ACT' ? 'status-activo' : usuario.ESTADO_USR === 'PEN' ? 'status-pendiente' : 'status-inactivo'}`}>
                    {usuario.ESTADO_USR === 'ACT'
                      ? 'Activo'
                      : usuario.ESTADO_USR === 'PEN'
                        ? 'Pendiente'
                        : 'Inactivo'}
                  </span>
                </td>
                <td className="actions-cell">
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => {
                      setEditingUsuario(usuario);
                      setUsernameEdit(usuario.username);
                      setPasswordEdit('');
                    }}
                    title="Editar usuario"
                    aria-label={`Editar usuario ${usuario.username}`}
                  >
                    <Edit3 size={16} />
                  </button>
                  <button type="button" className="icon-btn" onClick={() => void verRoles(usuario.id_Usuario)} title="Administrar roles" aria-label={`Administrar roles de ${usuario.username}`}>
                    <Shield size={16} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => void handleCambiarEstado(usuario)}
                    title={usuario.ESTADO_USR === 'ACT' ? 'Desactivar' : 'Activar'}
                    aria-label={`${usuario.ESTADO_USR === 'ACT' ? 'Desactivar' : 'Activar'} a ${usuario.username}`}
                    disabled={
                      usuario.id_Usuario === user?.id
                      || (usuario.ESTADO_USR !== 'ACT' && usuario.roles.length === 0)
                    }
                  >
                    {usuario.ESTADO_USR === 'ACT' ? <Trash2 size={16} /> : <Eye size={16} />}
                  </button>
                </td>
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
        totalItems={usuarios.length}
        onPageChange={pagination.setPage}
      />

      {viewingRoles && (
        <div className="modal-backdrop" onClick={cerrarRoles}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="roles-title" onClick={event => event.stopPropagation()}>
            <div className="modal-header">
              <h3 id="roles-title">Roles del usuario</h3>
              <button type="button" className="btn-close" onClick={cerrarRoles} aria-label="Cerrar roles">
                <EyeOff size={20} />
              </button>
            </div>
            <div className="modal-body">
              {error && <div className="alert alert-error" role="alert"><AlertCircle size={16} />{error}</div>}
              {success && <div className="alert alert-error" role="status">{success}</div>}
              <p>Roles actualmente asignados:</p>
              <div className="roles-assigned-list">
                {usuarioRoles.length === 0
                  ? <span style={{ color: '#787970', fontStyle: 'italic' }}>Sin roles asignados</span>
                  : usuarioRoles.map(role => (
                    <div key={role.id} className="role-assigned-item">
                      <span>{role.nombre}</span>
                      <button type="button" className="btn-remove" onClick={() => void handleRemoverRol(role.id)} title="Remover rol" aria-label={`Remover ${role.nombre}`}>
                        ×
                      </button>
                    </div>
                  ))}
              </div>

              <div className="roles-available-section">
                <h4>Asignar nuevo rol:</h4>
                <div className="roles-available-list">
                  {roles
                    .filter(role => !usuarioRoles.some(assigned => assigned.id === role.id))
                    .map(role => (
                      <button key={role.id} type="button" className="btn-role-add" onClick={() => void handleAsignarRol(role.id)}>
                        + {role.nombre}
                      </button>
                    ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {editingUsuario && (
        <div className="modal-backdrop" onClick={() => setEditingUsuario(null)}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="edit-user-title" onClick={event => event.stopPropagation()}>
            <div className="modal-header">
              <h3 id="edit-user-title">Editar usuario</h3>
              <button type="button" className="btn-close" onClick={() => setEditingUsuario(null)} aria-label="Cerrar edición">
                <EyeOff size={20} />
              </button>
            </div>
            <form className="modal-body" onSubmit={event => void guardarUsuario(event)}>
              {error && <div className="alert alert-error" role="alert"><AlertCircle size={16} />{error}</div>}
              <label className="form-group">
                Nombre de usuario
                <input
                  className="input"
                  value={usernameEdit}
                  onChange={event => setUsernameEdit(event.target.value)}
                  minLength={3}
                  maxLength={50}
                  required
                />
              </label>
              <label className="form-group">
                Nueva contraseña (opcional)
                <input
                  className="input"
                  type="password"
                  value={passwordEdit}
                  onChange={event => setPasswordEdit(event.target.value)}
                  minLength={8}
                  maxLength={100}
                  autoComplete="new-password"
                  placeholder="Dejar vacío para no cambiarla"
                />
              </label>
              <button type="submit" className="btn btn-primary" disabled={!usernameEdit.trim() || (passwordEdit.length > 0 && passwordEdit.length < 8)}>
                Guardar cambios
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
