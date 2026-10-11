import { useEffect, useState } from 'react';
import { StoreState } from './types';

const STORAGE_KEY = 'licoreria_state_v2';

const initialState: StoreState = {
  products: [
    { id: 'p1', name: 'Casillero del Diablo Cabernet', sku: 'V-001', barcode: '7804320000001', brand: 'Concha y Toro', category: 'Vino tinto', ml: 750, abv: 13.5, cost: 8.5, price: 15, stock: 24, minStock: 6, buyUnit: 'Caja', sellUnit: 'Botella', purchaseFactor: 12, shelf: 'A1', status: 'ACTIVE' },
    { id: 'p2', name: 'Johnnie Walker Black Label', sku: 'W-001', barcode: '5000267014203', brand: 'Johnnie Walker', category: 'Whisky', ml: 750, abv: 40, cost: 25, price: 45, stock: 12, minStock: 3, buyUnit: 'Caja', sellUnit: 'Botella', purchaseFactor: 6, shelf: 'B2', status: 'ACTIVE' },
    { id: 'p3', name: 'Zhumir Aguardiente', sku: 'A-001', barcode: '7861001234567', brand: 'Zhumir', category: 'Aguardiente', ml: 750, abv: 29, cost: 4, price: 7.5, stock: 50, minStock: 10, buyUnit: 'Caja', sellUnit: 'Botella', purchaseFactor: 12, shelf: 'C1', status: 'ACTIVE' },
    { id: 'p4', name: 'Cerveza artesanal IPA', sku: 'C-001', barcode: '7862000111111', brand: 'Santa Rosa', category: 'Cerveza', ml: 330, abv: 6.2, cost: 1.15, price: 2.5, stock: 7, minStock: 12, buyUnit: 'Caja', sellUnit: 'Botella', purchaseFactor: 24, shelf: 'D1', status: 'ACTIVE' },
    { id: 'p5', name: 'Espumante Brut Rosé', sku: 'E-001', barcode: '7791234567890', brand: 'Chandon', category: 'Espumante', ml: 750, abv: 12, cost: 12.5, price: 22, stock: 9, minStock: 4, buyUnit: 'Caja', sellUnit: 'Botella', purchaseFactor: 6, shelf: 'A3', status: 'ACTIVE' },
    { id: 'p6', name: 'Ron añejo 8 años', sku: 'R-001', barcode: '7863000222222', brand: 'San Miguel', category: 'Ron', ml: 750, abv: 40, cost: 11, price: 19.5, stock: 0, minStock: 5, buyUnit: 'Caja', sellUnit: 'Botella', purchaseFactor: 6, shelf: 'B3', status: 'ACTIVE' },
  ],
  customers: [
    { id: 'c1', ciRuc: '9999999999999', name: 'Consumidor Final', contact: '', email: '', city: 'Quito', address: '', type: 'NAT', creditLimit: 0, creditUsed: 0, discountRate: 0, status: 'ACTIVE' },
    { id: 'c2', ciRuc: '1712345678', name: 'Juan Pérez', contact: '0991234567', email: 'juan@example.com', city: 'Quito', address: 'La Floresta', type: 'NAT', creditLimit: 500, creditUsed: 120, discountRate: 5, status: 'ACTIVE' },
    { id: 'c3', ciRuc: '1790012345001', name: 'Eventos La Cava Cía. Ltda.', contact: '022345678', email: 'compras@lacava.example', city: 'Quito', address: 'Av. República', type: 'JUR', creditLimit: 1500, creditUsed: 0, discountRate: 8, status: 'ACTIVE' },
  ],
  suppliers: [
    { id: 's1', ruc: '1790000000001', name: 'Distribuidora Andina', contact: '022345678', email: 'ventas@andina.example', city: 'Quito', address: 'Av. 6 de Diciembre', status: 'ACTIVE' },
    { id: 's2', ruc: '0990000000001', name: 'Bebidas del Pacífico', contact: '042345678', email: 'pedidos@pacifico.example', city: 'Guayaquil', address: 'Vía Daule', status: 'ACTIVE' },
  ],
  invoices: [],
  purchaseOrders: [],
  receptions: [],
  deliveries: [],
  adjustments: [],
  employees: [
    { id: 'e1', ci: '1723456789', name: 'Carlos Admin', department: 'Administración', role: 'Gerente', salary: 1200, status: 'ACTIVE', familyDependents: 1 },
    { id: 'e2', ci: '1734567890', name: 'María Ventas', department: 'Ventas', role: 'Cajera', salary: 550, status: 'ACTIVE', familyDependents: 0 },
  ],
  payrolls: [],
  accounts: [
    { id: 'a1', code: '1.1.01.01', name: 'Caja', type: 'ASSET', balance: 1000 },
    { id: 'a2', code: '1.1.01.02', name: 'Bancos', type: 'ASSET', balance: 5000 },
    { id: 'a3', code: '1.1.03', name: 'Cuentas por cobrar', type: 'ASSET', balance: 120 },
    { id: 'a4', code: '1.1.04', name: 'Inventario', type: 'ASSET', balance: 5000 },
    { id: 'a5', code: '2.1.01', name: 'Proveedores', type: 'LIABILITY', balance: 0 },
    { id: 'a6', code: '2.1.02', name: 'IVA por pagar', type: 'LIABILITY', balance: 0 },
    { id: 'a7', code: '3.1.01', name: 'Capital', type: 'EQUITY', balance: 10000 },
    { id: 'a8', code: '4.1.01', name: 'Ventas', type: 'REVENUE', balance: 0 },
    { id: 'a9', code: '5.1.01', name: 'Costo de ventas', type: 'EXPENSE', balance: 0 },
    { id: 'a10', code: '5.2.01', name: 'Gasto de nómina', type: 'EXPENSE', balance: 0 },
    { id: 'a11', code: '2.1.03', name: 'Nómina por pagar', type: 'LIABILITY', balance: 0 },
    { id: 'a12', code: '2.1.04', name: 'Retenciones por pagar', type: 'LIABILITY', balance: 0 },
    { id: 'a13', code: '1.1.05', name: 'Impuestos de compras por recuperar', type: 'ASSET', balance: 0 },
    { id: 'a14', code: '5.3.01', name: 'Pérdida de inventario', type: 'EXPENSE', balance: 0 },
    { id: 'a15', code: '4.2.01', name: 'Sobrantes de inventario', type: 'REVENUE', balance: 0 },
  ],
  journalEntries: [],
  settings: { taxRate: 0 },
};

function isStoreState(value: unknown): value is StoreState {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<StoreState>;
  return ['products', 'customers', 'suppliers', 'invoices', 'purchaseOrders', 'receptions', 'deliveries', 'adjustments', 'employees', 'payrolls', 'accounts', 'journalEntries']
    .every(key => Array.isArray(candidate[key as keyof StoreState]))
    && typeof candidate.settings === 'object'
    && candidate.settings !== null
    && Number.isFinite(candidate.settings.taxRate)
    && candidate.settings.taxRate >= 0
    && candidate.settings.taxRate <= 100;
}

function loadState(): StoreState {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return structuredClone(initialState);
    const parsed: unknown = JSON.parse(saved);
    if (!isStoreState(parsed)) throw new TypeError('El formato guardado no corresponde al modelo de la aplicación.');
    return parsed;
  } catch (error) {
    console.error('No se pudo cargar la información local de demostración; se usarán los datos iniciales.', error);
    return structuredClone(initialState);
  }
}

export const useStore = () => {
  const [state, setState] = useState<StoreState>(loadState);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (error) {
      console.error('No se pudo guardar la información local de demostración.', error);
    }
  }, [state]);

  const updateState = (updater: (draft: StoreState) => StoreState) => {
    setState(previous => updater(structuredClone(previous)));
  };

  return { state, updateState };
};
