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
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const validateField = (field: string, value: string): string => {
    const clean = value.trim();
    if (field === 'id_Empleado') return clean ? '' : 'Selecciona un empleado.';
    if (field === 'cedula') {
      return /^\d{10,20}$/.test(clean) ? '' : 'Ingresa entre 10 y 20 dígitos, sin espacios ni símbolos.';
    }
    if (field === 'username') {
      if (clean.length < 3 || clean.length > 50) return 'El usuario debe tener entre 3 y 50 caracteres.';
      return /^[A-Za-z0-9_.@-]+$/.test(clean) ? '' : 'Usa solo letras, números, punto, guion, guion bajo o @.';
    }
    if (field === 'password') {
      return value.length >= 8 && value.length <= 100 ? '' : 'La contraseña debe tener entre 8 y 100 caracteres.';
    }
    if (field === 'confirmPassword') {
      return value === form.password ? '' : 'Las contraseñas no coinciden.';
    }
    return '';
  };

  const updateField = (field: string, value: string) => {
    const nextForm = { ...form, [field]: value };
    setForm(nextForm);
    setError(null);
    if (touched[field]) {
      setFieldErrors(current => ({ ...current, [field]: validateField(field, value) }));
    }
    if (field === 'password' && touched.confirmPassword) {
      setFieldErrors(current => ({
        ...current,
        confirmPassword: nextForm.confirmPassword === value ? '' : 'Las contraseñas no coinciden.',
      }));
    }
  };

  const markTouched = (field: string) => {
    setTouched(current => ({ ...current, [field]: true }));
    setFieldErrors(current => ({
      ...current,
      [field]: validateField(field, form[field as keyof typeof form] as string || ''),
    }));
  };

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

    if (isAuthenticated && !isUserManager) {
      setError('No tienes permiso para crear usuarios.');
      return;
    }
    const fields = isUserManager
      ? ['id_Empleado', 'username', 'password', 'confirmPassword']
      : ['cedula', 'username', 'password', 'confirmPassword'];
    const nextErrors = Object.fromEntries(fields.map(field => [
      field,
      validateField(field, String(form[field as keyof typeof form] || '')),
    ]));
    setTouched(current => ({ ...current, ...Object.fromEntries(fields.map(field => [field, true])) }));
    setFieldErrors(current => ({ ...current, ...nextErrors }));
    if (Object.values(nextErrors).some(Boolean)) {
      const firstInvalid = fields.find(field => nextErrors[field]);
      if (firstInvalid) {
        const inputId = firstInvalid === 'id_Empleado' ? 'registro-empleado' : `registro-${firstInvalid}`;
        document.getElementById(inputId)?.focus();
      }
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
        setFieldErrors({});
        setTouched({});
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
        setFieldErrors({});
        setTouched({});
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '';
      setError(/database|sql|mysql|maria|traceback|constraint|table|column/i.test(message)
        ? 'No se pudo completar el registro. Revisa los datos o inténtalo más tarde.'
        : message || 'No se pudo completar el registro. Revisa los datos o inténtalo más tarde.');
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

          <form onSubmit={handleSubmit} className="login-form" noValidate>
            {adminMode ? (
              <div className="form-group">
                <label className="form-label" htmlFor="registro-empleado">Empleado</label>
                <div className="input-wrapper">
                  <User size={18} className="input-icon" />
                  <select
                    id="registro-empleado"
                    className="form-input"
                    value={form.id_Empleado}
                    onChange={event => updateField('id_Empleado', event.target.value)}
                    onBlur={() => markTouched('id_Empleado')}
                    disabled={loading || loadingCatalogs}
                    aria-invalid={Boolean(touched.id_Empleado && fieldErrors.id_Empleado)}
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
                {touched.id_Empleado && fieldErrors.id_Empleado && <span className="field-error" role="alert">{fieldErrors.id_Empleado}</span>}
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
                    onChange={event => updateField('cedula', event.target.value.replace(/\D/g, '').slice(0, 20))}
                    onBlur={() => markTouched('cedula')}
                    disabled={loading}
                    inputMode="numeric"
                    minLength={10}
                    maxLength={20}
                    autoComplete="off"
                    aria-invalid={Boolean(touched.cedula && fieldErrors.cedula)}
                    required
                  />
                </div>
                {touched.cedula && fieldErrors.cedula && <span className="field-error" role="alert">{fieldErrors.cedula}</span>}
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
                  onChange={event => updateField('username', event.target.value)}
                  onBlur={() => markTouched('username')}
                  disabled={loading}
                  autoComplete="username"
                  minLength={3}
                  maxLength={50}
                  aria-invalid={Boolean(touched.username && fieldErrors.username)}
                  required
                />
              </div>
              {touched.username && fieldErrors.username && <span className="field-error" role="alert">{fieldErrors.username}</span>}
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
                  onChange={event => updateField('password', event.target.value)}
                  onBlur={() => markTouched('password')}
                  disabled={loading}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={100}
                  aria-invalid={Boolean(touched.password && fieldErrors.password)}
                  required
                />
              </div>
              {touched.password && fieldErrors.password && <span className="field-error" role="alert">{fieldErrors.password}</span>}
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
                  onChange={event => updateField('confirmPassword', event.target.value)}
                  onBlur={() => markTouched('confirmPassword')}
                  disabled={loading}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={100}
                  aria-invalid={Boolean(touched.confirmPassword && fieldErrors.confirmPassword)}
                  required
                />
              </div>
              {touched.confirmPassword && fieldErrors.confirmPassword && <span className="field-error" role="alert">{fieldErrors.confirmPassword}</span>}
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
                          setError(null);
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
              disabled={loading || loadingCatalogs}
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
