import { useState } from 'react';
import { Mail, Lock, AlertCircle, Eye, EyeOff, LogIn, UserPlus } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const { login, isLoading, error } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const irARegistro = () => {
    window.location.hash = '#/registro';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await login(username, password).catch(() => undefined);
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
                  required
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
                  required
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
            <button
              type="button"
              className="registro-btn"
              onClick={irARegistro}
              disabled={isLoading}
            >
              <UserPlus size={16} /> Crear cuenta nueva
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