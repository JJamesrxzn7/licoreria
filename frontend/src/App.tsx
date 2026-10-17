import { useState } from 'react';
import {
  Bell, BookOpen, Briefcase, Calculator, FileText, LayoutDashboard, Menu,
  PanelLeftClose, PanelLeftOpen, ShoppingCart, Truck, Users, Wine, X,
  Building2, PieChart
} from 'lucide-react';
import { StoreProvider } from './context';
import { POS } from './pages/POS';
import { Customers, Dashboard, EmployeeFile, PayrollManagement, Suppliers } from './pages/CorePages';
import { Adjustments, Catalog, Deliveries, PurchaseOrders, Receptions } from './pages/InventoryPages';
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
  { id: 'employees', label: 'Ficha del personal', icon: Users, group: 'ADMINISTRACIÓN' },
  { id: 'payroll', label: 'Roles de pago', icon: Calculator, group: 'ADMINISTRACIÓN' },
  { id: 'accounting', label: 'Contabilidad', icon: Calculator, group: 'ADMINISTRACIÓN' },
  { id: 'bancos', label: 'Bancos', icon: Building2, group: 'ADMINISTRACIÓN' },
  { id: 'cost_centers', label: 'Centros de costos', icon: PieChart, group: 'ADMINISTRACIÓN' },
  { id: 'reports', label: 'Reportes', icon: FileText, group: 'ADMINISTRACIÓN' },
];

const AppContent = () => {
  const [currentRoute, setCurrentRoute] = useState('dashboard');
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const activePage = navItems.find(item => item.id === currentRoute);
  const groups = [...new Set(navItems.map(item => item.group))];

  const navigate = (route: string) => {
    setCurrentRoute(route);
    setMobileNavOpen(false);
  };

  const routeViews: Record<string, JSX.Element> = {
    dashboard: <Dashboard />,
    pos: <POS />,
    products: <Catalog />,
    catalog: <Catalog />,
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
          {groups.map(group => (
            <div className="nav-group" key={group}>
              <span className="nav-group-label">{group}</span>
              {navItems.filter(item => item.group === group).map(item => {
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
        <div className="sidebar-footer"><span className="status-dot" /> <span>Modo demostración</span></div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <button type="button" className="mobile-menu" aria-label="Abrir menú" onClick={() => setMobileNavOpen(true)}><Menu size={21} /></button>
          <span className="breadcrumb">La Cava <span>/</span> {activePage?.label}</span>
          <div className="topbar-actions"><span className="demo-badge">DATOS DE PRUEBA</span><button type="button" className="notification-button" aria-label="Ver alertas de inventario" onClick={() => navigate('products')}><Bell size={18} /><i /></button><span className="avatar" aria-label="Usuario demostración">LC</span></div>
        </header>
        <div className="page-content">{routeViews[currentRoute] ?? <Dashboard />}</div>
      </main>
    </div>
  );
};

export default function App() {
  return <StoreProvider><AppContent /></StoreProvider>;
}
