import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { authApi } from '../api';
import { AuthUser } from '../types';

type AuthContextType = {
  user: AuthUser | null;
  isLoading: boolean;
  error: string | null;
  isAuthenticated: boolean;
  hasPermission: (permission: string) => boolean;
  hasRouteAccess: (routeId: string) => boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
};

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const token = localStorage.getItem('licoreria_token');
    if (!token || !token.includes('.')) {
      localStorage.removeItem('licoreria_token');
      localStorage.removeItem('licoreria_user');
      return null;
    }
    try {
      const saved = localStorage.getItem('licoreria_user');
      if (saved) return JSON.parse(saved);
    } catch {
      localStorage.removeItem('licoreria_token');
      localStorage.removeItem('licoreria_user');
    }
    return null;
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => setError(null), []);

  const login = useCallback(async (username: string, password: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await authApi.login({ username, password });
      if (response.success && response.user) {
        setUser(response.user);
        localStorage.setItem('licoreria_token', response.token);
        localStorage.setItem('licoreria_user', JSON.stringify(response.user));
      } else {
        throw new Error('No se pudo iniciar sesión.');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Credenciales inválidas o error de conexión.';
      setError(message);
      throw new Error(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    if (user) {
      try {
        await authApi.logout({ userId: user.id, username: user.username });
      } catch {
        // Ignorar errores de logout, limpiar sesión de todas formas
      }
    }
    setUser(null);
    localStorage.removeItem('licoreria_token');
    localStorage.removeItem('licoreria_user');
  }, [user]);

  const hasPermission = useCallback((permission: string) => {
    return user?.permissions.includes(permission) ?? false;
  }, [user]);

  const hasRouteAccess = useCallback((routeId: string) => {
    return user?.allowedRoutes.includes(routeId) ?? false;
  }, [user]);

  const isAuthenticated = !!user;

  return (
    <AuthContext.Provider value={{ user, isLoading, error, isAuthenticated, hasPermission, hasRouteAccess, login, logout, clearError }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
};