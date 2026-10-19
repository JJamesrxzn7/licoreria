import { useEffect, useState } from 'react';
import {
  Bell, BookOpen, Briefcase, Calculator, FileText, LayoutDashboard, Menu,
  PanelLeftClose, PanelLeftOpen, ShoppingCart, Truck, Users, Wine, X,
  Building2, PieChart, Scale, LogOut
} from 'lucide-react';
import { StoreProvider } from './context';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Registro from './pages/Registro';
import InitialSetup from './pages/InitialSetup';
import Usuarios from './pages/Usuarios';
import { POS } from './pages/POS';
import { Customers, Dashboard, EmployeeFile, PayrollManagement, Suppliers } from './pages/CorePages';
import { Adjustments, Catalog, Deliveries, PurchaseOrders, Receptions } from './pages/InventoryPages';
import { UnitsOfMeasure } from './pages/UnitsOfMeasure';
import { Accounting, Reports, Sales } from './pages/FinancialPages';

const navItems = [
  { id: 'dashboard', label: 'Resumen', icon: LayoutDashboard, group: 'GENERAL' },
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
];

const AppContent = () => {
  const { user, isAuthenticated, logout, isLoading } = useAuth();
  const [hashRoute, setHashRoute] = useState(() => window.location.hash.replace('#/', ''));
  const [currentRoute, setCurrentRoute] = useState(() => {
    const initialRoute = window.location.hash.replace('#/', '');
    return initialRoute === 'usuarios' || initialRoute === 'registro' ? initialRoute : 'dashboard';
  });
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    const handleHashChange = () => {
      const route = window.location.hash.replace('#/', '');
      setHashRoute(route);
      if (route === 'usuarios' || (route === 'registro' && isAuthenticated)) {
        setCurrentRoute(route);
      }
      if (route === 'login' && isAuthenticated) {
        setCurrentRoute('dashboard');
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [isAuthenticated]);

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

  const activePage = navItems.find(item => item.id === currentRoute);

  const allowedNavItems = navItems.filter(item => user?.allowedRoutes.includes(item.id));
  const allowedGroups = [...new Set(allowedNavItems.map(item => item.group))];

  const navigate = (route: string) => {
    setCurrentRoute(route);
    setMobileNavOpen(false);
  };

  const handleLogout = async () => {
    await logout();
    setCurrentRoute('dashboard');
    setMobileNavOpen(false);
  };

  const routeViews: Record<string, JSX.Element> = {
    dashboard: <Dashboard />,
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
  };

  return (
    <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
      {mobileNavOpen && <button className="mobile-backdrop" aria-label="Cerrar menú" onClick={() => setMobileNavOpen(false)} />}
      <aside className={`sidebar ${mobileNavOpen ? 'mobile-open' : ''}`}>
        <div className="brand">
          <span className="brand-mark"><Wine size={21} /></span>
          <span className="brand-copy"><strong>La Cava</strong><small>LICORERÍA · QUITO</small></span>
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
          <div className="topbar-actions">
            <button type="button" className="notification-button" aria-label="Ver alertas de inventario" onClick={() => navigate('products')}><Bell size={18} /></button>
            <div className="user-profile" onClick={handleLogout} title="Cerrar sesión">
              <span className="avatar">{user?.username.charAt(0).toUpperCase()}</span>
              <span className="user-name">{user?.fullName}</span>
              <LogOut size={14} className="logout-icon" />
            </div>
          </div>
        </header>
        <div className="page-content">{routeViews[currentRoute] ?? <Dashboard />}</div>
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
