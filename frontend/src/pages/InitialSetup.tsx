import { useEffect, useState, type FormEvent } from 'react';
import { AlertCircle, ArrowLeft, Lock, Mail, ShieldCheck, User } from 'lucide-react';
import { authApi, departamentosApi, type Departamento } from '../api';

const today = new Date();
const latestBirthDateDate = new Date(today.getFullYear() - 18, today.getMonth(), today.getDate());
const latestBirthDate = [
  latestBirthDateDate.getFullYear(),
  String(latestBirthDateDate.getMonth() + 1).padStart(2, '0'),
  String(latestBirthDateDate.getDate()).padStart(2, '0'),
].join('-');

export default function InitialSetup() {
  const [departments, setDepartments] = useState<Departamento[]>([]);
  const [initialized, setInitialized] = useState(false);
  const [loadingCatalogs, setLoadingCatalogs] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [form, setForm] = useState({
    ci: '',
    firstName: '',
    secondName: '',
    lastName1: '',
    lastName2: '',
    gender: 'M',
    birthDate: '',
    salary: '',
    departmentId: '',
    address: '',
    phone: '',
    mobile: '',
    email: '',
    username: '',
    password: '',
    confirmPassword: '',
  });

  useEffect(() => {
    let cancelled = false;
    Promise.all([authApi.setupStatus(), departamentosApi.listar()])
      .then(([status, departmentList]) => {
        if (cancelled) return;
        setInitialized(status.initialized);
        setDepartments(departmentList);
        setForm(current => ({
          ...current,
          departmentId: current.departmentId || departmentList[0]?.id || '',
        }));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'No se pudo cargar la configuración inicial.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingCatalogs(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const update = (field: keyof typeof form, value: string) => {
    setForm(current => ({ ...current, [field]: value }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (initialized) {
      setError('El sistema ya está configurado y no admite otro administrador inicial.');
      return;
    }
    if (form.password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres.');
      return;
    }
    if (form.password !== form.confirmPassword) {
      setError('Las contraseñas no coinciden.');
      return;
    }
    if (!form.departmentId) {
      setError('Selecciona un departamento activo para la ficha del empleado.');
      return;
    }

    setLoading(true);
    try {
      const response = await authApi.setupInitialAdmin({
        employee: {
          ci: form.ci.trim(),
          nombre1: form.firstName.trim(),
          nombre2: form.secondName.trim() || undefined,
          apellido1: form.lastName1.trim(),
          apellido2: form.lastName2.trim() || undefined,
          sexo: form.gender,
          fechaNacimiento: form.birthDate,
          sueldo: Number(form.salary),
          idDepartamento: form.departmentId,
          direccion: form.address.trim() || undefined,
          telefono: form.phone.trim() || undefined,
          celular: form.mobile.trim() || undefined,
          email: form.email.trim() || undefined,
        },
        username: form.username.trim(),
        password: form.password,
      });
      setInitialized(true);
      setSuccess(`${response.mensaje} Código de empleado: ${response.idEmpleado}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo completar la configuración inicial.');
    } finally {
      setLoading(false);
    }
  };

  const backToLogin = () => {
    window.location.hash = '#/login';
  };

  return (
    <div className="login-page initial-setup-page">
      <div className="login-container initial-setup-container">
        <div className="login-brand">
          <div className="brand-mark"><ShieldCheck size={30} /></div>
          <div className="brand-info">
            <h2>La Cava</h2>
            <p>Configuración inicial segura</p>
          </div>
        </div>

        <div className="login-card">
          <button type="button" className="back-btn" onClick={backToLogin}>
            <ArrowLeft size={16} /> Volver al login
          </button>
          <div className="login-header">
            <h3>Crear empleado y administrador</h3>
            <p>Este proceso solo puede completarse una vez. La contraseña se almacenará protegida con hash.</p>
          </div>

          {error && (
            <div className="alert alert-error" role="alert">
              <AlertCircle size={16} /> {error}
            </div>
          )}
          {success && (
            <div className="alert initial-setup-success" role="status">
              <ShieldCheck size={16} /> {success}
              <button type="button" className="back-btn" onClick={backToLogin}>Ir a iniciar sesión</button>
            </div>
          )}

          {initialized ? (
            !success && (
              <div className="alert alert-error" role="status">
                El sistema ya tiene usuarios. La configuración inicial está cerrada.
              </div>
            )
          ) : (
            <form onSubmit={handleSubmit} className="login-form initial-setup-form">
              <h4 className="initial-setup-section">Datos del empleado</h4>
              <label className="form-group">
                <span className="form-label">Cédula ecuatoriana *</span>
                <div className="input-wrapper">
                  <User size={18} className="input-icon" />
                  <input className="form-input" value={form.ci} onChange={event => update('ci', event.target.value)} maxLength={10} inputMode="numeric" autoComplete="off" required />
                </div>
              </label>
              <label className="form-group">
                <span className="form-label">Primer nombre *</span>
                <input className="form-input setup-plain-input" value={form.firstName} onChange={event => update('firstName', event.target.value)} maxLength={30} autoComplete="given-name" required />
              </label>
              <label className="form-group">
                <span className="form-label">Segundo nombre</span>
                <input className="form-input setup-plain-input" value={form.secondName} onChange={event => update('secondName', event.target.value)} maxLength={30} />
              </label>
              <label className="form-group">
                <span className="form-label">Primer apellido *</span>
                <input className="form-input setup-plain-input" value={form.lastName1} onChange={event => update('lastName1', event.target.value)} maxLength={30} autoComplete="family-name" required />
              </label>
              <label className="form-group">
                <span className="form-label">Segundo apellido</span>
                <input className="form-input setup-plain-input" value={form.lastName2} onChange={event => update('lastName2', event.target.value)} maxLength={30} />
              </label>
              <label className="form-group">
                <span className="form-label">Sexo *</span>
                <select className="form-input setup-plain-input" value={form.gender} onChange={event => update('gender', event.target.value)} required>
                  <option value="M">Masculino</option>
                  <option value="F">Femenino</option>
                </select>
              </label>
              <label className="form-group">
                <span className="form-label">Fecha de nacimiento *</span>
                <input className="form-input setup-plain-input" type="date" value={form.birthDate} onChange={event => update('birthDate', event.target.value)} max={latestBirthDate} required />
              </label>
              <label className="form-group">
                <span className="form-label">Sueldo mensual (USD) *</span>
                <input className="form-input setup-plain-input" type="number" min="460" max="50000" step="0.01" value={form.salary} onChange={event => update('salary', event.target.value)} required />
              </label>
              <label className="form-group">
                <span className="form-label">Departamento *</span>
                <select className="form-input setup-plain-input" value={form.departmentId} onChange={event => update('departmentId', event.target.value)} disabled={loadingCatalogs || departments.length === 0} required>
                  <option value="">{loadingCatalogs ? 'Cargando departamentos...' : 'Selecciona un departamento'}</option>
                  {departments.map(department => (
                    <option key={department.id} value={department.id}>{department.nombre}</option>
                  ))}
                </select>
              </label>
              <label className="form-group">
                <span className="form-label">Dirección</span>
                <input className="form-input setup-plain-input" value={form.address} onChange={event => update('address', event.target.value)} maxLength={60} autoComplete="street-address" />
              </label>
              <label className="form-group">
                <span className="form-label">Teléfono convencional</span>
                <input className="form-input setup-plain-input" value={form.phone} onChange={event => update('phone', event.target.value)} maxLength={10} inputMode="tel" autoComplete="tel-national" />
              </label>
              <label className="form-group">
                <span className="form-label">Celular</span>
                <input className="form-input setup-plain-input" value={form.mobile} onChange={event => update('mobile', event.target.value)} maxLength={10} inputMode="tel" autoComplete="tel" />
              </label>
              <label className="form-group initial-setup-wide">
                <span className="form-label">Correo electrónico</span>
                <div className="input-wrapper">
                  <Mail size={18} className="input-icon" />
                  <input className="form-input" type="email" value={form.email} onChange={event => update('email', event.target.value)} maxLength={60} autoComplete="email" />
                </div>
              </label>

              <h4 className="initial-setup-section initial-setup-wide">Credenciales del administrador</h4>
              <label className="form-group initial-setup-wide">
                <span className="form-label">Nombre de usuario *</span>
                <div className="input-wrapper">
                  <User size={18} className="input-icon" />
                  <input className="form-input" value={form.username} onChange={event => update('username', event.target.value)} minLength={3} maxLength={50} autoComplete="username" required />
                </div>
              </label>
              <label className="form-group">
                <span className="form-label">Contraseña (mínimo 8 caracteres) *</span>
                <div className="input-wrapper">
                  <Lock size={18} className="input-icon" />
                  <input className="form-input" type="password" value={form.password} onChange={event => update('password', event.target.value)} minLength={8} maxLength={100} autoComplete="new-password" required />
                </div>
              </label>
              <label className="form-group">
                <span className="form-label">Confirmar contraseña *</span>
                <div className="input-wrapper">
                  <Lock size={18} className="input-icon" />
                  <input className="form-input" type="password" value={form.confirmPassword} onChange={event => update('confirmPassword', event.target.value)} minLength={8} maxLength={100} autoComplete="new-password" required />
                </div>
              </label>
              {departments.length === 0 && !loadingCatalogs && (
                <p className="initial-setup-wide initial-setup-hint">
                  No hay departamentos disponibles. Carga primero los departamentos en la base de datos y vuelve a intentarlo.
                </p>
              )}
              <button type="submit" className="login-button initial-setup-wide" disabled={loading || loadingCatalogs || departments.length === 0}>
                <ShieldCheck size={18} /> {loading ? 'Creando administrador...' : 'Crear empleado y administrador'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
