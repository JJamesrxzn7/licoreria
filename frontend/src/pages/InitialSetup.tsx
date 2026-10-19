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
const earliestBirthDateDate = new Date(today.getFullYear() - 90, today.getMonth(), today.getDate());
const earliestBirthDate = [
  earliestBirthDateDate.getFullYear(),
  String(earliestBirthDateDate.getMonth() + 1).padStart(2, '0'),
  String(earliestBirthDateDate.getDate()).padStart(2, '0'),
].join('-');
const namePattern = /^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s.\-]+$/;
const emailPattern = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
const phonePattern = /^(0[2-7]\d{7}|\d{7})$/;
const mobilePattern = /^09\d{8}$/;
const unsafeTextPattern = /(\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|EXEC|EXECUTE)\b|--|\/\*|\*\/|;|'|"|<script)/i;

function isValidEcuadorianId(value: string): boolean {
  if (!/^\d{10}$/.test(value)) return false;

  const province = Number(value.slice(0, 2));
  if (!(province >= 1 && province <= 24) && province !== 30) return false;
  if (Number(value[2]) >= 6) return false;

  const coefficients = [2, 1, 2, 1, 2, 1, 2, 1, 2];
  const sum = coefficients.reduce((total, coefficient, index) => {
    const product = Number(value[index]) * coefficient;
    return total + (product >= 10 ? product - 9 : product);
  }, 0);
  const checkDigit = (10 - (sum % 10)) % 10;
  return checkDigit === Number(value[9]);
}

type SetupField = keyof typeof initialSetupForm;

const initialSetupForm = {
  ci: '',
  firstName: '',
  secondName: '',
  lastName1: '',
  lastName2: '',
  gender: '',
  birthDate: '',
  departmentId: '',
  address: '',
  phone: '',
  mobile: '',
  email: '',
  username: '',
  password: '',
  confirmPassword: '',
};

export default function InitialSetup() {
  const [departments, setDepartments] = useState<Departamento[]>([]);
  const [initialized, setInitialized] = useState(false);
  const [loadingCatalogs, setLoadingCatalogs] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [form, setForm] = useState(initialSetupForm);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<SetupField, string>>>({});
  const [touched, setTouched] = useState<Partial<Record<SetupField, boolean>>>({});

  useEffect(() => {
    let cancelled = false;
    Promise.all([authApi.setupStatus(), departamentosApi.listar()])
      .then(([status, departmentList]) => {
        if (cancelled) return;
        setInitialized(status.initialized);
        setDepartments(departmentList);
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
    const nextForm = { ...form, [field]: value };
    setForm(nextForm);
    setError(null);
    if (touched[field]) {
      setFieldErrors(current => ({ ...current, [field]: validateField(field, nextForm) }));
    }
    if (field === 'password' && touched.confirmPassword) {
      setFieldErrors(current => ({
        ...current,
        confirmPassword: nextForm.password === nextForm.confirmPassword ? '' : 'Las contraseñas no coinciden.',
      }));
    }
  };

  const validateField = (field: SetupField, values: typeof form): string => {
    const value = values[field].trim();
    if (field === 'ci') {
      return isValidEcuadorianId(value) ? '' : 'Ingresa una cédula ecuatoriana válida de 10 dígitos.';
    }
    if (field === 'firstName' || field === 'lastName1') {
      if (value.length < 2 || value.length > 30) return 'Este campo debe tener entre 2 y 30 caracteres.';
      return namePattern.test(value) ? '' : 'Usa solo letras, espacios, puntos, guiones o apóstrofes.';
    }
    if (field === 'secondName' || field === 'lastName2') {
      if (!value) return '';
      if (value.length > 30) return 'No puede superar 30 caracteres.';
      return namePattern.test(value) ? '' : 'Usa solo letras, espacios, puntos, guiones o apóstrofes.';
    }
    if (field === 'gender') return value ? '' : 'Selecciona una opción.';
    if (field === 'birthDate') {
      if (!value) return 'Ingresa la fecha de nacimiento.';
      if (value > latestBirthDate) return 'El empleado debe tener al menos 18 años.';
      if (value < earliestBirthDate) return 'La fecha indica una edad mayor a 90 años.';
      return '';
    }
    if (field === 'departmentId') return value ? '' : 'Selecciona un departamento.';
    if (field === 'address') {
      if (value.length > 60) return 'La dirección no puede superar 60 caracteres.';
      return value && unsafeTextPattern.test(value) ? 'Revisa los caracteres ingresados en la dirección.' : '';
    }
    if (field === 'phone') {
      if (!value) return '';
      return phonePattern.test(value.replace(/\D/g, '')) ? '' : 'Usa 7 dígitos o 9 incluyendo el código de provincia.';
    }
    if (field === 'mobile') {
      if (!value) return '';
      return mobilePattern.test(value.replace(/\D/g, '')) ? '' : 'Usa 10 dígitos y comienza con 09.';
    }
    if (field === 'email') {
      if (!value) return '';
      if (value.length > 60) return 'El correo no puede superar 60 caracteres.';
      return emailPattern.test(value) ? '' : 'Ingresa un correo electrónico válido.';
    }
    if (field === 'username') {
      if (value.length < 3 || value.length > 50) return 'El usuario debe tener entre 3 y 50 caracteres.';
      return /^[A-Za-z0-9_.@-]+$/.test(value) ? '' : 'Usa solo letras, números, punto, guion, guion bajo o @.';
    }
    if (field === 'password') {
      if (values.password.length < 8 || values.password.length > 100) return 'La contraseña debe tener entre 8 y 100 caracteres.';
      return '';
    }
    if (field === 'confirmPassword') {
      return values.confirmPassword === values.password ? '' : 'Las contraseñas no coinciden.';
    }
    return '';
  };

  const markTouched = (field: SetupField) => {
    setTouched(current => ({ ...current, [field]: true }));
    setFieldErrors(current => ({ ...current, [field]: validateField(field, form) }));
  };

  const fieldError = (field: SetupField) => touched[field] ? fieldErrors[field] : '';

  const renderFieldError = (field: SetupField) => fieldError(field)
    ? <span id={`setup-${field}-error`} className="field-error" role="alert">{fieldError(field)}</span>
    : null;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    const fields = Object.keys(form) as SetupField[];
    const nextErrors = Object.fromEntries(fields.map(field => [field, validateField(field, form)])) as Record<SetupField, string>;
    setTouched(Object.fromEntries(fields.map(field => [field, true])));
    setFieldErrors(nextErrors);
    const invalidFields = fields.filter(field => nextErrors[field]);
    if (invalidFields.length > 0) {
      document.getElementById(`setup-${invalidFields[0]}`)?.focus();
      return;
    }
    if (initialized) {
      setError('El sistema ya está configurado y no admite otro administrador inicial.');
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
      setError(err instanceof Error && !/database|sql|mysql|maria|traceback|constraint|table|column/i.test(err.message)
        ? err.message
        : 'No se pudo completar la configuración. Revisa los datos e inténtalo nuevamente.');
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
            <h3>Configura tu acceso administrativo</h3>
            <p>Registra tus datos y crea las credenciales para comenzar a usar el sistema. Este proceso solo puede completarse una vez.</p>
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
            <form onSubmit={handleSubmit} className="login-form initial-setup-form" noValidate>
              <h4 className="initial-setup-section">Datos del empleado</h4>
              <label className="form-group">
                <span className="form-label">Cédula ecuatoriana *</span>
                <div className="input-wrapper">
                  <User size={18} className="input-icon" />
                  <input id="setup-ci" className="form-input" value={form.ci} onChange={event => update('ci', event.target.value.replace(/\D/g, '').slice(0, 10))} onBlur={() => markTouched('ci')} maxLength={10} inputMode="numeric" autoComplete="off" aria-invalid={Boolean(fieldError('ci'))} aria-describedby={fieldError('ci') ? 'setup-ci-error' : undefined} required />
                </div>
                {renderFieldError('ci')}
              </label>
              <label className="form-group">
                <span className="form-label">Primer nombre *</span>
                <input id="setup-firstName" className="form-input setup-plain-input" value={form.firstName} onChange={event => update('firstName', event.target.value)} onBlur={() => markTouched('firstName')} maxLength={30} autoComplete="given-name" aria-invalid={Boolean(fieldError('firstName'))} required />
                {renderFieldError('firstName')}
              </label>
              <label className="form-group">
                <span className="form-label">Segundo nombre</span>
                <input id="setup-secondName" className="form-input setup-plain-input" value={form.secondName} onChange={event => update('secondName', event.target.value)} onBlur={() => markTouched('secondName')} maxLength={30} aria-invalid={Boolean(fieldError('secondName'))} required={false} />
                {renderFieldError('secondName')}
              </label>
              <label className="form-group">
                <span className="form-label">Primer apellido *</span>
                <input id="setup-lastName1" className="form-input setup-plain-input" value={form.lastName1} onChange={event => update('lastName1', event.target.value)} onBlur={() => markTouched('lastName1')} maxLength={30} autoComplete="family-name" aria-invalid={Boolean(fieldError('lastName1'))} required />
                {renderFieldError('lastName1')}
              </label>
              <label className="form-group">
                <span className="form-label">Segundo apellido</span>
                <input id="setup-lastName2" className="form-input setup-plain-input" value={form.lastName2} onChange={event => update('lastName2', event.target.value)} onBlur={() => markTouched('lastName2')} maxLength={30} aria-invalid={Boolean(fieldError('lastName2'))} />
                {renderFieldError('lastName2')}
              </label>
              <label className="form-group">
                <span className="form-label">Sexo *</span>
                <select id="setup-gender" className="form-input setup-plain-input" value={form.gender} onChange={event => update('gender', event.target.value)} onBlur={() => markTouched('gender')} aria-invalid={Boolean(fieldError('gender'))} required>
                  <option value="">Selecciona una opción</option>
                  <option value="M">Masculino</option>
                  <option value="F">Femenino</option>
                </select>
                {renderFieldError('gender')}
              </label>
              <label className="form-group">
                <span className="form-label">Fecha de nacimiento *</span>
                <input id="setup-birthDate" className="form-input setup-plain-input" type="date" value={form.birthDate} onChange={event => update('birthDate', event.target.value)} onBlur={() => markTouched('birthDate')} min={earliestBirthDate} max={latestBirthDate} aria-invalid={Boolean(fieldError('birthDate'))} required />
                {renderFieldError('birthDate')}
              </label>
              <label className="form-group">
                <span className="form-label">Departamento *</span>
                <select id="setup-departmentId" className="form-input setup-plain-input" value={form.departmentId} onChange={event => update('departmentId', event.target.value)} onBlur={() => markTouched('departmentId')} disabled={loadingCatalogs || departments.length === 0} aria-invalid={Boolean(fieldError('departmentId'))} required>
                  <option value="">{loadingCatalogs ? 'Cargando departamentos...' : 'Selecciona un departamento'}</option>
                  {departments.map(department => (
                    <option key={department.id} value={department.id}>{department.nombre}</option>
                  ))}
                </select>
                {renderFieldError('departmentId')}
              </label>
              <label className="form-group">
                <span className="form-label">Dirección</span>
                <input id="setup-address" className="form-input setup-plain-input" value={form.address} onChange={event => update('address', event.target.value)} onBlur={() => markTouched('address')} maxLength={60} autoComplete="street-address" aria-invalid={Boolean(fieldError('address'))} />
                {renderFieldError('address')}
              </label>
              <label className="form-group">
                <span className="form-label">Teléfono convencional</span>
                <input id="setup-phone" className="form-input setup-plain-input" value={form.phone} onChange={event => update('phone', event.target.value.replace(/\D/g, '').slice(0, 9))} onBlur={() => markTouched('phone')} maxLength={9} inputMode="tel" autoComplete="tel-national" aria-invalid={Boolean(fieldError('phone'))} />
                {renderFieldError('phone')}
              </label>
              <label className="form-group">
                <span className="form-label">Celular</span>
                <input id="setup-mobile" className="form-input setup-plain-input" value={form.mobile} onChange={event => update('mobile', event.target.value.replace(/\D/g, '').slice(0, 10))} onBlur={() => markTouched('mobile')} maxLength={10} inputMode="tel" autoComplete="tel" aria-invalid={Boolean(fieldError('mobile'))} />
                {renderFieldError('mobile')}
              </label>
              <label className="form-group initial-setup-wide">
                <span className="form-label">Correo electrónico</span>
                <div className="input-wrapper">
                  <Mail size={18} className="input-icon" />
                  <input id="setup-email" className="form-input" type="email" value={form.email} onChange={event => update('email', event.target.value)} onBlur={() => markTouched('email')} maxLength={60} autoComplete="email" aria-invalid={Boolean(fieldError('email'))} />
                </div>
                {renderFieldError('email')}
              </label>

              <h4 className="initial-setup-section initial-setup-wide">Credenciales del administrador</h4>
              <label className="form-group initial-setup-wide">
                <span className="form-label">Nombre de usuario *</span>
                <div className="input-wrapper">
                  <User size={18} className="input-icon" />
                  <input id="setup-username" className="form-input" value={form.username} onChange={event => update('username', event.target.value)} onBlur={() => markTouched('username')} minLength={3} maxLength={50} autoComplete="username" aria-invalid={Boolean(fieldError('username'))} required />
                </div>
                {renderFieldError('username')}
              </label>
              <label className="form-group">
                <span className="form-label">Contraseña (mínimo 8 caracteres) *</span>
                <div className="input-wrapper">
                  <Lock size={18} className="input-icon" />
                  <input id="setup-password" className="form-input" type="password" value={form.password} onChange={event => update('password', event.target.value)} onBlur={() => markTouched('password')} minLength={8} maxLength={100} autoComplete="new-password" aria-invalid={Boolean(fieldError('password'))} required />
                </div>
                {renderFieldError('password')}
              </label>
              <label className="form-group">
                <span className="form-label">Confirmar contraseña *</span>
                <div className="input-wrapper">
                  <Lock size={18} className="input-icon" />
                  <input id="setup-confirmPassword" className="form-input" type="password" value={form.confirmPassword} onChange={event => update('confirmPassword', event.target.value)} onBlur={() => markTouched('confirmPassword')} minLength={8} maxLength={100} autoComplete="new-password" aria-invalid={Boolean(fieldError('confirmPassword'))} required />
                </div>
                {renderFieldError('confirmPassword')}
              </label>
              {departments.length === 0 && !loadingCatalogs && (
                <p className="initial-setup-wide initial-setup-hint">
                  No hay departamentos disponibles. Carga primero los departamentos en la base de datos y vuelve a intentarlo.
                </p>
              )}
              <button type="submit" className="login-button initial-setup-wide" disabled={loading || loadingCatalogs || departments.length === 0}>
                <ShieldCheck size={18} /> {loading ? 'Configurando acceso...' : 'Crear acceso de administrador'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
