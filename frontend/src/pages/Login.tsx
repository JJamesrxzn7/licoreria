import { useState, useEffect } from 'react';
import { Mail, Lock, AlertCircle, Eye, EyeOff, LogIn } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { authApi } from '../api';
import { DemoAccount } from '../api';

export default function Login() {
  const { login, isLoading, error } = useAuth();
  const [demoAccounts, setDemoAccounts] = useState<DemoAccount[]>([]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    authApi.demoAccounts().then(setDemoAccounts).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    try {
      await login(username, password);
    } catch (err: any) {
      setLoginError(err?.message || 'Credenciales inválidas. Intenta nuevamente.');
    }
  };

  const handleDemoLogin = (account: DemoAccount) => {
    setUsername(account.username);
    setPassword(account.password);
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-brand">
          <div className="brand-mark">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="#183a31" />
              <path d="M12 7L12 13M12 13L9.29 17.21M12 13L14.71 17.21M12 13L12 13M2 9.27L22 9.27" stroke="#183a31" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
          <div className="brand-info">
            <h2>La Cava</h2>
            <p>Sistema de Gestión de Licorería</p>
          </div>
        </div>

        <div className="login-card">
          <div className="login-header">
            <h3>Iniciar sesión</h3>
            <p>Ingresa tus credenciales para acceder al sistema</p>
          </div>

          {error && (
            <div className="alert alert-error">
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          {loginError && (
            <div className="alert alert-error">
              <AlertCircle size={16} />
              {loginError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="login-form">
            <div className="form-group">
              <label className="form-label">Usuario</label>
              <div className="input-wrapper">
                <Mail size={18} className="input-icon" />
                <input
                  type="text"
                  className="form-input"
                  placeholder="ej. admin"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={isLoading}
                  autoComplete="username"
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Contraseña</label>
              <div className="input-wrapper">
                <Lock size={18} className="input-icon" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  className="form-input"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="toggle-password"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="login-button"
              disabled={isLoading}
            >
              {isLoading ? 'Ingresando...' : <><LogIn size={18} /> Iniciar sesión</>}
            </button>
          </form>

          <div className="divider">
            <span>o prueba con una cuenta de demostración</span>
          </div>

          <div className="demo-accounts">
            {demoAccounts.length > 0 ? (
              demoAccounts.map((account) => (
                <button
                  key={account.username}
                  type="button"
                  className="demo-btn"
                  disabled={isLoading}
                  onClick={() => handleDemoLogin(account)}
                  title={account.description}
                >
                  <span className="demo-color" style={{ backgroundColor: account.color }}></span>
                  <span className="demo-info">
                    <strong>{account.username}</strong>
                    <span className="demo-role">{account.role}</span>
                  </span>
                </button>
              ))
            ) : (
              <button className="demo-btn" disabled>Cargando cuentas...</button>
            )}
          </div>
        </div>

        <div className="login-footer">
          <p>La Cava Licorería · Quito, Ecuador</p>
        </div>
      </div>
    </div>
  );
}