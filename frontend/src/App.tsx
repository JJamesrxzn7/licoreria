import { useEffect, useRef, useState } from 'react';
import {
  Bell, BookOpen, Briefcase, Calculator, FileText, LayoutDashboard, Menu,
  PanelLeftClose, PanelLeftOpen, ShoppingCart, Truck, Users, Wine, X,
  Building2, PieChart, Scale, LogOut, ChevronDown, ClipboardList, Server, Database
} from 'lucide-react';
import { StoreProvider, useGlobalStore, ClusterSiteId } from './context';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Registro from './pages/Registro';
import InitialSetup from './pages/InitialSetup';
import Usuarios from './pages/Usuarios';
import AuditLogs from './pages/AuditLogs';
import ArchitectureConsole from './pages/ArchitectureConsole';
import { POS } from './pages/POS';
import { Customers, Dashboard, EmployeeFile, PayrollManagement, Suppliers } from './pages/CorePages';
import { Adjustments, Catalog, Deliveries, PurchaseOrders, Receptions } from './pages/InventoryPages';
import { UnitsOfMeasure } from './pages/UnitsOfMeasure';
import { Accounting, Reports, Sales } from './pages/FinancialPages';

const navItems = [
  { id: 'dashboard', label: 'Resumen', icon: LayoutDashboard, group: 'GENERAL' },
  { id: 'architecture', label: 'Arquitectura BD & DBA', icon: Server, group: 'GENERAL' },
  { id: 'pos', label: 'Punto de venta', icon: ShoppingCart, group: 'VENTAS' },
  { id: 'sales', label: 'Facturas', icon: FileText, group: 'VENTAS' },
  { id: 'customers', label: 'Clientes', icon: Users, group: 'VENTAS' },
  { id: 'adjustments', label: 'Ajustes físicos', icon: BookOpen, group: 'BODEGA' },
  { id: 'receptions', label: 'Recepciones', icon: Truck, group: 'BODEGA' },
  { id: 'deliveries', label: 'Entregas', icon: Truck, group: 'BODEGA' },
  { id: 'pos_orders', label: 'Compras', icon: Briefcase, group: 'ABASTECIMIENTO' },
  { id: 'suppliers', label: 'Proveedores', icon: Users, group: 'ABASTECIMIENTO' },
  { id: 'products', label: 'Productos', icon: Wine, group: 'ABASTECIMIENTO' },
  { id: 'units', label: 'Unidades de medida', icon: Scale, group: 'ABASTECIMIENTO' },
  { id: 'employees', label: 'Ficha del personal', icon: Users, group: 'ADMINISTRACIÓN' },
  { id: 'payroll', label: 'Roles de pago', icon: Calculator, group: 'ADMINISTRACIÓN' },
  { id: 'accounting', label: 'Contabilidad', icon: Calculator, group: 'ADMINISTRACIÓN' },
  { id: 'bancos', label: 'Bancos', icon: Building2, group: 'ADMINISTRACIÓN' },
  { id: 'cost_centers', label: 'Centros de costos', icon: PieChart, group: 'ADMINISTRACIÓN' },
  { id: 'reports', label: 'Reportes', icon: FileText, group: 'ADMINISTRACIÓN' },
  { id: 'usuarios', label: 'Usuarios', icon: Users, group: 'ADMINISTRACIÓN' },
  { id: 'audit', label: 'Auditoría', icon: ClipboardList, group: 'ADMINISTRACIÓN' },
];

const SITE_OPTIONS: Array<{
  id: ClusterSiteId;
  shortLabel: string;
  brandSub: string;
  portsLabel: string;
  description: string;
}> = [
  {
    id: 'QUITO',
    shortLabel: 'Nodo Quito (3 BDs)',
    brandSub: 'LICORERÍA · QUITO',
    portsLabel: ':3307 SQL · :27017 Mongo · :3308 Hash',
    description: 'PC Escritorio (Tailscale) · BD 1, BD 2 NoSQL y BD 3 Paralela',
  },
  {
    id: 'GUAYAQUIL',
    shortLabel: 'Nodo Guayaquil (2 BDs)',
    brandSub: 'LICORERÍA · GUAYAQUIL',
    portsLabel: ':3306 OLTP · :3309 DWH Power BI',
    description: 'Laptop · BD 4 Local (15 Usuarios RBAC) + BD 5 Estrella DWH',
  },
  {
    id: 'CUENCA_CLOUD',
    shortLabel: 'Nodo Cuenca (Cloud)',
    brandSub: 'LICORERÍA · CUENCA CLOUD',
    portsLabel: ':5432 Supabase PostgreSQL',
    description: 'Nube DBaaS · BD 6 Supabase PostgreSQL + Latencia WAN',
  },
];

const AppContent = () => {
  const { user, isAuthenticated, logout, isLoading } = useAuth();
  const { activeSite, setActiveSite } = useGlobalStore();
  const isAdministrator = Boolean(
    user?.roleIds.includes('ROL-ADMIN')
      || user?.roles.some(role => ['admin', 'administrador', 'superadministrador'].includes(role.trim().toLowerCase())),
  );
  const [hashRoute, setHashRoute] = useState(() => window.location.hash.replace('#/', ''));
  const [currentRoute, setCurrentRoute] = useState(() => {
    const initialRoute = window.location.hash.replace('#/', '');
    return initialRoute === 'usuarios' || initialRoute === 'registro' || initialRoute === 'architecture' ? initialRoute : 'dashboard';
  });
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [siteMenuOpen, setSiteMenuOpen] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  const profileRef = useRef<HTMLDivElement>(null);
  const siteMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleHashChange = () => {
      const route = window.location.hash.replace('#/', '');
      setHashRoute(route);
      if (route === 'usuarios' || route === 'architecture' || (route === 'registro' && isAuthenticated)) {
        setCurrentRoute(route);
      }
      if (route === 'login' && isAuthenticated) {
        setCurrentRoute('dashboard');
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [isAuthenticated]);

  useEffect(() => {
    if (!profileOpen && !siteMenuOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node) {
        if (!profileRef.current?.contains(event.target)) {
          setProfileOpen(false);
        }
        if (!siteMenuRef.current?.contains(event.target)) {
          setSiteMenuOpen(false);
        }
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setProfileOpen(false);
        setSiteMenuOpen(false);
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [profileOpen, siteMenuOpen]);

  if (isLoading && !isAuthenticated) {
    return (
      <div className="login-page">
        <div className="login-container">
          <div className="login-card">
            <div className="login-header">
              <h3>Cargando sesión...</h3>
              <p>Por favor espera mientras se restaura tu acceso.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    if (hashRoute === 'configuracion-inicial') {
      return <InitialSetup />;
    }
    return <Login />;
  }

  const allowedNavItems = navItems.filter(item =>
    item.id === 'architecture'
    || (user?.allowedRoutes.includes(item.id) && (item.id !== 'audit' || isAdministrator)),
  );
  const allowedGroups = [...new Set(allowedNavItems.map(item => item.group))];
  const canViewCurrentRoute = currentRoute === 'registro'
    ? allowedNavItems.some(item => item.id === 'usuarios')
    : allowedNavItems.some(item => item.id === currentRoute);
  const activePage = canViewCurrentRoute ? navItems.find(item => item.id === currentRoute) : undefined;

  const navigate = (route: string) => {
    setCurrentRoute(route);
    setMobileNavOpen(false);
  };

  const handleLogout = async () => {
    setLogoutError('');
    try {
      await logout();
      setCurrentRoute('dashboard');
      setMobileNavOpen(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Error de conexión.';
      setLogoutError(`No se pudo cerrar la sesión en el servidor: ${message}`);
    }
  };

  const routeViews: Record<string, JSX.Element> = {
    dashboard: <Dashboard />,
    architecture: <ArchitectureConsole />,
    pos: <POS />,
    products: <Catalog />,
    catalog: <Catalog />,
    units: <UnitsOfMeasure />,
    adjustments: <Adjustments />,
    deliveries: <Deliveries />,
    sales: <Sales />,
    customers: <Customers />,
    suppliers: <Suppliers onNavigate={navigate} />,
    pos_orders: <PurchaseOrders />,
    receptions: <Receptions />,
    employees: <EmployeeFile />,
    payroll: <PayrollManagement />,
    hr: <EmployeeFile />,
    accounting: <Accounting initialTab="diario" />,
    bancos: <Accounting initialTab="bancos" />,
    cost_centers: <Accounting initialTab="centros_costos" />,
    reports: <Reports />,
    usuarios: <Usuarios onCreate={() => navigate('registro')} />,
    registro: <Registro onBack={() => navigate('usuarios')} />,
    audit: <AuditLogs />,
  };

  const currentSiteMeta = SITE_OPTIONS.find(s => s.id === activeSite) ?? SITE_OPTIONS[0];

  return (
    <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
      {mobileNavOpen && <button className="mobile-backdrop" aria-label="Cerrar menú" onClick={() => setMobileNavOpen(false)} />}
      <aside className={`sidebar ${mobileNavOpen ? 'mobile-open' : ''}`}>
        <div className="brand">
          <span className="brand-mark"><Wine size={21} /></span>
          <span className="brand-copy"><strong>La Cava</strong><small>{currentSiteMeta.brandSub}</small></span>
          <button type="button" className="sidebar-toggle" aria-label={collapsed ? 'Expandir menú' : 'Contraer menú'} onClick={() => setCollapsed(value => !value)}>
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
          <button type="button" className="mobile-close" aria-label="Cerrar menú" onClick={() => setMobileNavOpen(false)}><X size={20} /></button>
        </div>
        <nav className="nav-links" aria-label="Navegación principal">
          {allowedGroups.map(group => (
            <div className="nav-group" key={group}>
              <span className="nav-group-label">{group}</span>
              {allowedNavItems.filter(item => item.group === group).map(item => {
                const Icon = item.icon;
                return (
                  <button key={item.id} type="button" className={`nav-link ${currentRoute === item.id ? 'active' : ''}`} aria-current={currentRoute === item.id ? 'page' : undefined} title={collapsed ? item.label : undefined} onClick={() => navigate(item.id)}>
                    <Icon size={18} strokeWidth={1.8} /><span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <span className="status-dot" style={{ backgroundColor: '#71bd91' }} />
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: '#fff' }}>{user?.fullName}</div>
              <div style={{ fontSize: '9px', color: '#bdc9bd', textTransform: 'uppercase' }}>{user?.primaryRole}</div>
            </div>
          </div>
          <button type="button" className="logout-btn" onClick={handleLogout} title="Cerrar sesión">
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <button type="button" className="mobile-menu" aria-label="Abrir menú" onClick={() => setMobileNavOpen(true)}><Menu size={21} /></button>
          <span className="breadcrumb">La Cava <span>/</span> {activePage?.label ?? (currentRoute === 'registro' ? 'Nuevo usuario' : '')}</span>
          <div className="topbar-actions" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* SELECTOR DE SEDE / NODO CON LA PALETA EDITORIAL DE LA CAVA */}
            <div ref={siteMenuRef} style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setSiteMenuOpen(open => !open)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  background: '#faf8f4',
                  color: '#183a31',
                  padding: '6px 12px',
                  borderRadius: '20px',
                  border: '1px solid #d9d4c7',
                  fontSize: '11.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  boxShadow: '0 1px 3px rgba(24,58,49,0.05)',
                }}
              >
                <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#267154', boxShadow: '0 0 0 3px rgba(38,113,84,0.14)' }} />
                <span>{currentSiteMeta.shortLabel}</span>
                <small style={{ color: '#782c3e', fontWeight: 700, fontSize: '10px' }}>({currentSiteMeta.portsLabel})</small>
                <ChevronDown size={13} style={{ color: '#787970' }} />
              </button>

              {siteMenuOpen && (
                <div
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 'calc(100% + 8px)',
                    width: '315px',
                    background: '#ffffff',
                    border: '1px solid #e9e6de',
                    borderRadius: '12px',
                    boxShadow: '0 14px 34px rgba(24,58,49,0.14)',
                    padding: '10px',
                    zIndex: 50,
                  }}
                >
                  <div style={{ padding: '4px 8px 8px', borderBottom: '1px solid #efeee9', marginBottom: '6px' }}>
                    <div style={{ fontSize: '9px', fontWeight: 700, letterSpacing: '.14em', color: '#782c3e', textTransform: 'uppercase' }}>
                      Clúster Multi-Sitio (6 Bases de Datos)
                    </div>
                    <div style={{ fontSize: '11px', color: '#787970', marginTop: '2px' }}>
                      Elige qué sede consultar en tiempo real:
                    </div>
                  </div>
                  {SITE_OPTIONS.map(opt => {
                    const selected = opt.id === activeSite;
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => {
                          setActiveSite(opt.id);
                          setSiteMenuOpen(false);
                        }}
                        style={{
                          width: '100%',
                          textAlign: 'left',
                          padding: '9px 10px',
                          borderRadius: '8px',
                          border: selected ? '1px solid #d4ded6' : '1px solid transparent',
                          background: selected ? '#f0f5f1' : 'transparent',
                          cursor: 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '2px',
                          marginBottom: '4px',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <strong style={{ fontSize: '12px', color: '#183a31' }}>{opt.shortLabel}</strong>
                          <span style={{ fontSize: '10px', fontWeight: 700, color: '#782c3e', background: '#fbf3f0', padding: '2px 7px', borderRadius: '12px' }}>
                            {opt.portsLabel}
                          </span>
                        </div>
                        <span style={{ fontSize: '10.5px', color: '#787970' }}>{opt.description}</span>
                      </button>
                    );
                  })}
                  <div style={{ borderTop: '1px solid #efeee9', paddingTop: '8px', marginTop: '4px' }}>
                    <button
                      type="button"
                      onClick={() => {
                        setSiteMenuOpen(false);
                        navigate('architecture');
                      }}
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        borderRadius: '8px',
                        border: 'none',
                        background: '#782c3e',
                        color: '#fff',
                        fontSize: '11.5px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                      }}
                    >
                      <Database size={13} />
                      Abrir Consola DBA & Pizarra de Nodos
                    </button>
                  </div>
                </div>
              )}
            </div>

            <button type="button" className="notification-button" aria-label="Ver alertas de inventario" onClick={() => navigate('products')}><Bell size={18} /></button>
            <div className="profile-menu" ref={profileRef}>
              <button
                type="button"
                className="user-profile"
                aria-expanded={profileOpen}
                aria-haspopup="dialog"
                aria-controls="profile-summary"
                onClick={() => setProfileOpen(open => !open)}
              >
                <span className="avatar">{user?.username.charAt(0).toUpperCase()}</span>
                <span className="user-name">{user?.fullName}</span>
                <ChevronDown size={14} className={`profile-chevron ${profileOpen ? 'open' : ''}`} />
              </button>
              {profileOpen && (
                <section id="profile-summary" className="profile-summary" role="dialog" aria-label="Resumen del perfil">
                  <div className="profile-summary-heading">
                    <span className="avatar profile-summary-avatar">{user?.username.charAt(0).toUpperCase()}</span>
                    <div>
                      <strong>{user?.fullName}</strong>
                      <span>{user?.primaryRole}</span>
                    </div>
                  </div>
                  <dl className="profile-summary-details">
                    <div><dt>Usuario</dt><dd>{user?.username}</dd></div>
                    <div><dt>Código de empleado</dt><dd>{user?.employeeId || 'No asignado'}</dd></div>
                    <div><dt>Departamento</dt><dd>{user?.department || 'General'}</dd></div>
                    <div><dt>Roles</dt><dd>{user?.roles.join(', ') || user?.primaryRole}</dd></div>
                  </dl>
                </section>
              )}
            </div>
            <button type="button" className="topbar-logout" onClick={() => void handleLogout()} title="Cerrar sesión" aria-label="Cerrar sesión">
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <div className="page-content">
          {logoutError && <p className="form-notice" role="alert">{logoutError}</p>}
          {canViewCurrentRoute
            ? routeViews[currentRoute]
            : <section className="card" role="alert">No tienes permiso para acceder a esta sección.</section>}
        </div>
      </main>
    </div>
  );
};

export default function App() {
  return (
    <StoreProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </StoreProvider>
  );
}
