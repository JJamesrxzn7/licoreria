import { useEffect, useState } from 'react';
import { AlertCircle, ArrowLeft, Lock, Mail, Shield, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { authApi, usuariosApi, rolesApi } from '../api';
import type { Empleado, Rol } from '../api';

type RegistroProps = {
  onBack: () => void;
};

export default function Registro({ onBack }: RegistroProps) {
  const { user, hasPermission } = useAuth();
  const isAuthenticated = Boolean(user);
  const isUserManager = Boolean(
    user?.roles.some(role => ['admin', 'administrador', 'jefe_talento_humano'].includes(role.trim().toLowerCase()))
      || hasPermission('PRM-USU'),
  );
  const [empleados, setEmpleados] = useState<Empleado[]>([]);
  const [rolesDisponibles, setRolesDisponibles] = useState<Rol[]>([]);
  const [form, setForm] = useState({
    id_Empleado: '',
    cedula: '',
    username: '',
    password: '',
    confirmPassword: '',
    rol_ids: [] as string[],
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingCatalogs, setLoadingCatalogs] = useState(false);

  useEffect(() => {
    if (!isUserManager) return;
    let cancelled = false;
    setLoadingCatalogs(true);
    Promise.all([usuariosApi.empleadosDisponibles(), rolesApi.listar()])
      .then(([employeeList, roleList]) => {
        if (cancelled) return;
        setEmpleados(employeeList);
        setRolesDisponibles(roleList.filter(role => role.estado === 'ACT'));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'No se pudo cargar la información inicial.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingCatalogs(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isUserManager]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (form.password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres.');
      return;
    }
    if (form.password !== form.confirmPassword) {
      setError('Las contraseñas no coinciden.');
      return;
    }
    if (isAuthenticated && !isUserManager) {
      setError('No tienes permiso para crear usuarios.');
      return;
    }
    if (isAuthenticated && form.rol_ids.length === 0) {
      setError('Asigna al menos un rol para crear la cuenta.');
      return;
    }

    setLoading(true);
    try {
      if (isUserManager) {
        await usuariosApi.crear({
          id_Empleado: form.id_Empleado,
          username: form.username,
          password: form.password,
          rol_ids: form.rol_ids,
        });
        setSuccess('Usuario creado y activado. Ya puede iniciar sesión.');
        setForm({
          id_Empleado: '',
          cedula: '',
          username: '',
          password: '',
          confirmPassword: '',
          rol_ids: [],
        });
      } else {
        const response = await authApi.register({
          cedula: form.cedula.trim(),
          username: form.username,
          password: form.password,
        });
        setSuccess(response.mensaje);
        setForm({
          id_Empleado: '',
          cedula: '',
          username: '',
          password: '',
          confirmPassword: '',
          rol_ids: [],
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear la solicitud de usuario.');
    } finally {
      setLoading(false);
    }
  };

  if (isAuthenticated && !isUserManager) {
    return (
      <section className="card" role="alert">
        <h2>Acceso restringido</h2>
        <p>No tienes permiso para crear usuarios.</p>
        <button type="button" className="btn btn-outline" onClick={onBack}>Volver</button>
      </section>
    );
  }

  const adminMode = isUserManager;

  return (
    <div className={`login-page ${adminMode ? 'registro-admin-page' : ''}`}>
      <div className={`login-container ${adminMode ? 'registro-admin-container' : ''}`}>
        <div className="login-brand">
          <div className="brand-mark">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="#183a31" />
              <path d="M12 7L12 13M12 13L9.29 17.21M12 13L14.71 17.21M2 9.27L22 9.27" stroke="#183a31" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
          <div className="brand-info">
            <h2>La Cava</h2>
            <p>{adminMode ? 'Administración de usuarios' : 'Registro de nuevo usuario'}</p>
          </div>
        </div>

        <div className="login-card">
          <button type="button" className="back-btn" onClick={onBack}>
            <ArrowLeft size={16} /> {adminMode ? 'Volver a usuarios' : 'Volver al login'}
          </button>

          <div className="login-header">
            <h3>{adminMode ? 'Crear usuario' : 'Solicitar una cuenta'}</h3>
            <p>
              {adminMode
                ? 'Registra una cuenta para un empleado y asigna sus roles.'
                : 'Ingresa tu cédula registrada como empleado. El sistema localizará tu ficha y un administrador activará la cuenta.'}
            </p>
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

          <form onSubmit={handleSubmit} className="login-form">
            {adminMode ? (
              <div className="form-group">
                <label className="form-label" htmlFor="registro-empleado">Empleado</label>
                <div className="input-wrapper">
                  <User size={18} className="input-icon" />
                  <select
                    id="registro-empleado"
                    className="form-input"
                    value={form.id_Empleado}
                    onChange={event => setForm({ ...form, id_Empleado: event.target.value })}
                    disabled={loading || loadingCatalogs}
                    required
                  >
                    <option value="">Seleccionar empleado sin cuenta</option>
                    {empleados.map(employee => (
                      <option key={employee.id} value={employee.id}>
                        {employee.nombre} {employee.apellido} {employee.departamento ? `(${employee.departamento})` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            ) : (
              <div className="form-group">
                <label className="form-label" htmlFor="registro-cedula">Cédula del empleado</label>
                <div className="input-wrapper">
                  <User size={18} className="input-icon" />
                  <input
                    id="registro-cedula"
                    type="text"
                    className="form-input"
                    placeholder="Ingresa tu cédula"
                    value={form.cedula}
                    onChange={event => setForm({ ...form, cedula: event.target.value.replace(/\D/g, '') })}
                    disabled={loading}
                    inputMode="numeric"
                    minLength={10}
                    maxLength={20}
                    autoComplete="off"
                    required
                  />
                </div>
              </div>
            )}

            <div className="form-group">
              <label className="form-label" htmlFor="registro-username">Nombre de usuario</label>
              <div className="input-wrapper">
                <Mail size={18} className="input-icon" />
                <input
                  id="registro-username"
                  type="text"
                  className="form-input"
                  placeholder="ej. nuevo_usuario"
                  value={form.username}
                  onChange={event => setForm({ ...form, username: event.target.value })}
                  disabled={loading}
                  autoComplete="username"
                  minLength={3}
                  maxLength={50}
                  required
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="registro-password">Contraseña</label>
              <div className="input-wrapper">
                <Lock size={18} className="input-icon" />
                <input
                  id="registro-password"
                  type="password"
                  className="form-input"
                  placeholder="Mínimo 8 caracteres"
                  value={form.password}
                  onChange={event => setForm({ ...form, password: event.target.value })}
                  disabled={loading}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={100}
                  required
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="registro-confirm-password">Confirmar contraseña</label>
              <div className="input-wrapper">
                <Lock size={18} className="input-icon" />
                <input
                  id="registro-confirm-password"
                  type="password"
                  className="form-input"
                  placeholder="Repite la contraseña"
                  value={form.confirmPassword}
                  onChange={event => setForm({ ...form, confirmPassword: event.target.value })}
                  disabled={loading}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={100}
                  required
                />
              </div>
            </div>

            {adminMode && (
              <div className="form-group">
                <label className="form-label">Roles asignados</label>
                <div className="roles-list">
                  {rolesDisponibles.map(role => (
                    <label key={role.id} className="role-checkbox">
                      <input
                        type="checkbox"
                        checked={form.rol_ids.includes(role.id)}
                        onChange={event => {
                          const rol_ids = event.target.checked
                            ? [...form.rol_ids, role.id]
                            : form.rol_ids.filter(id => id !== role.id);
                          setForm({ ...form, rol_ids });
                        }}
                        disabled={loading}
                      />
                      <span>{role.nombre}</span>
                    </label>
                  ))}
                </div>
                {rolesDisponibles.length === 0 && !loadingCatalogs && (
                  <small>No hay roles activos disponibles para asignar.</small>
                )}
              </div>
            )}

            <button
              type="submit"
              className="login-button"
              disabled={
                loading
                || loadingCatalogs
                || (adminMode && (!form.id_Empleado || form.rol_ids.length === 0))
                || (!adminMode && !form.cedula)
              }
            >
              {loading
                ? 'Creando...'
                : <><Shield size={18} /> {adminMode ? 'Crear usuario' : 'Solicitar cuenta'}</>}
            </button>
          </form>
        </div>

        <div className="login-footer">
          <p>La Cava Licorería · Quito, Ecuador</p>
        </div>
      </div>
    </div>
  );
}
