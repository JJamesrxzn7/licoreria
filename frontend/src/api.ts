import {
  Customer, Supplier, Product, Invoice, Reception, Delivery,
  Adjustment, Employee, Payroll, Account, JournalEntry
} from './types';

const API_BASE_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export interface PurchaseSupplier {
  id: string;
  nombre: string;
  identificacion: string;
  estado: string;
}

export interface PurchaseProduct {
  id: string;
  nombre: string;
  costo: number | string;
  precio?: number | string;
  stock?: number;
  estado: string;
}

export interface PurchaseCatalogs {
  proveedores: PurchaseSupplier[];
  productos: PurchaseProduct[];
}

export interface PurchaseOrderItemRecord {
  productoId: string;
  producto: string;
  cantidad: number;
  costoUnitario: number | string;
  subtotal: number | string;
  estado: string;
}

export interface PurchaseOrderRecord {
  id: string;
  proveedorId: string;
  proveedor: string;
  fecha: string;
  fechaEntrega: string | null;
  subtotal: number | string;
  iva: number | string;
  total: number | string;
  estado: 'ABI' | 'APR' | 'ANU' | 'PEN';
  tasaIVA: number | string;
  items: PurchaseOrderItemRecord[];
}

type CreateOrderRequest = {
  idProveedor: string;
  fechaEntrega: string | null;
  tasaIVA: number;
  items: Array<{ idProducto: string; cantidad: number; costoUnitario: number }>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch (error) {
    throw new Error('No se pudo conectar con la API. Verifica que uvicorn esté corriendo en el puerto 8000.');
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body
      ? String(body.detail)
      : `La API respondió con el estado ${response.status}.`;
    throw new Error(detail);
  }
  return body as T;
}

// 1. Módulo Compras
export const purchaseApi = {
  getCatalogs: () => request<PurchaseCatalogs>('/api/compras/catalogos'),
  listOrders: () => request<PurchaseOrderRecord[]>('/api/compras'),
  createOrder: (order: CreateOrderRequest) => request<{ id: string; estado: string; mensaje: string }>('/api/compras', {
    method: 'POST',
    body: JSON.stringify(order),
  }),
  approveOrder: (orderId: string) => request<{ id: string; estado: string }>(`/api/compras/${encodeURIComponent(orderId)}/aprobar`, {
    method: 'POST',
  }),
  annulOrder: (orderId: string) => request<{ id: string; estado: string }>(`/api/compras/${encodeURIComponent(orderId)}/anular`, {
    method: 'POST',
  }),
};

export interface GeneralCatalogs {
  ciudades: Array<{ id: string; nombre: string; provincia: string; region: string }>;
  unidadesMedida: Array<{ id: string; nombre: string; factor: number | string }>;
  categorias: Array<{ id: string; nombre: string }>;
  marcas: Array<{ id: string; nombre: string }>;
  perchas: Array<{ id: string; nombre: string; letra: string; nivel: number }>;
  bancos: Array<{ id: string; nombre: string }>;
}

export const catalogApi = {
  getGenerales: () => request<GeneralCatalogs>('/api/catalogos/generales'),
  getCiudades: () => request<Array<{ id: string; nombre: string; provincia: string; region: string }>>('/api/ciudades'),
  getUnidades: () => request<Array<{ id: string; nombre: string; factor: number | string }>>('/api/unidades-medida'),
  getCategorias: () => request<Array<{ id: string; nombre: string }>>('/api/categorias'),
  getMarcas: () => request<Array<{ id: string; nombre: string }>>('/api/marcas'),
};

// 2. Módulo Productos
export const productApi = {
  listProducts: () => request<Product[]>('/api/productos'),
  createProduct: (product: {
    id?: string;
    nombre: string;
    idCategoria?: string;
    idMarca?: string;
    idPercha?: string;
    umCompra?: string;
    umVenta?: string;
    costoCompra: number;
    precioVenta: number;
    stockInicial?: number;
  }) => request<{ id: string; mensaje: string }>('/api/productos', {
    method: 'POST',
    body: JSON.stringify(product),
  }),
  updateProduct: (id: string, product: {
    nombre: string;
    costoCompra: number;
    precioVenta: number;
  }) => request<{ id: string; mensaje: string }>(`/api/productos/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(product),
  }),
};

// 3. Módulo Clientes
export const customerApi = {
  listCustomers: () => request<Customer[]>('/api/clientes'),
  createCustomer: (customer: {
    nombre: string;
    ciRuc: string;
    telefono?: string;
    email?: string;
    idCiudad?: string;
    celular?: string;
    direccion?: string;
    cupoCredito?: number;
    descuento?: number;
  }) => request<{ id: string; mensaje: string }>('/api/clientes', {
    method: 'POST',
    body: JSON.stringify(customer),
  }),
  updateCustomer: (id: string, customer: {
    nombre: string;
    ciRuc: string;
    telefono?: string;
    email?: string;
    direccion?: string;
    cupoCredito?: number;
    descuento?: number;
  }) => request<{ id: string; mensaje: string }>(`/api/clientes/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(customer),
  }),
};

// 4. Módulo Proveedores
export const supplierApi = {
  listSuppliers: () => request<Supplier[]>('/api/proveedores'),
  createSupplier: (supplier: {
    id?: string;
    nombre: string;
    ruc: string;
    telefono?: string;
    email?: string;
    idCiudad?: string;
    celular?: string;
    direccion?: string;
  }) => request<{ id: string; mensaje: string }>('/api/proveedores', {
    method: 'POST',
    body: JSON.stringify(supplier),
  }),
  updateSupplier: (id: string, supplier: {
    nombre: string;
    ruc: string;
    telefono?: string;
    celular?: string;
    email?: string;
    idCiudad?: string;
    direccion?: string;
  }) => request<{ id: string; mensaje: string }>(`/api/proveedores/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(supplier),
  }),
  changeStatus: (id: string, estado: 'ACTIVE' | 'INACTIVE') =>
    request<{ id: string; estado: string; mensaje: string }>(`/api/proveedores/${encodeURIComponent(id)}/estado`, {
      method: 'PATCH',
      body: JSON.stringify({ estado }),
    }),
};

// 5. Módulo Ventas
export const salesApi = {
  listInvoices: () => request<Invoice[]>('/api/ventas'),
  createInvoice: (sale: {
    idCliente: string;
    idEmpleado?: string;
    descripcion?: string;
    tasaIVA?: number;
    metodoPago?: string;
    cuotas?: number;
    items: Array<{ idProducto: string; cantidad: number; precioUnitario: number }>;
  }) => request<{ id: string; deliveryId: string; estado: string; total: string; mensaje: string }>('/api/ventas', {
    method: 'POST',
    body: JSON.stringify(sale),
  }),
  approveInvoice: (invoiceId: string) => request<{ id: string; estado: string; mensaje: string }>(`/api/ventas/${encodeURIComponent(invoiceId)}/aprobar`, {
    method: 'POST',
  }),
  annulInvoice: (invoiceId: string) => request<{ id: string; estado: string; mensaje: string }>(`/api/ventas/${encodeURIComponent(invoiceId)}/anular`, {
    method: 'POST',
  }),
};

// 6. Módulo Bodega (Recepciones, Entregas, Ajustes)
export const warehouseApi = {
  listReceptions: () => request<Reception[]>('/api/recepciones'),
  confirmReception: (receiptId: string, items: Array<{ productId: string; receivedQty: number; reason?: string }>) =>
    request<{ id: string; estado: string; mensaje: string }>(`/api/recepciones/${encodeURIComponent(receiptId)}/confirmar`, {
      method: 'POST',
      body: JSON.stringify({ items }),
    }),
  listDeliveries: () => request<Delivery[]>('/api/entregas'),
  confirmDelivery: (deliveryId: string, items: Array<{ productId: string; deliveredQty: number; reason?: string }>) =>
    request<{ id: string; estado: string; mensaje: string }>(`/api/entregas/${encodeURIComponent(deliveryId)}/confirmar`, {
      method: 'POST',
      body: JSON.stringify({ items }),
    }),
  listAdjustments: () => request<Adjustment[]>('/api/ajustes'),
  createAdjustment: (adj: {
    idEmpleado?: string;
    idProducto: string;
    tipo: 'IN' | 'OUT';
    cantidad: number;
    motivo: string;
  }) => request<{ id: string; estado: string; mensaje: string }>('/api/ajustes', {
    method: 'POST',
    body: JSON.stringify(adj),
  }),
  approveAdjustment: (id: string) => request<{ id: string; estado: string; mensaje: string }>(`/api/ajustes/${encodeURIComponent(id)}/aprobar`, {
    method: 'POST',
  }),
  annulAdjustment: (id: string) => request<{ id: string; estado: string; mensaje: string }>(`/api/ajustes/${encodeURIComponent(id)}/anular`, {
    method: 'POST',
  }),
};

// 7. Módulo Talento Humano y Nómina
export const hrApi = {
  listEmployees: () => request<Employee[]>('/api/empleados'),
  listPayrolls: () => request<Payroll[]>('/api/nomina'),
  createPayroll: (payroll: {
    descripcion: string;
    fechaInicio: string;
    fechaFin: string;
    idEmpleado: string;
    sueldoBase: number;
    bonificaciones?: number;
    descuentos?: number;
  }) => request<{ id: string; estado: string; mensaje: string }>('/api/nomina', {
    method: 'POST',
    body: JSON.stringify(payroll),
  }),
  approvePayroll: (id: string) => request<{ id: string; estado: string; mensaje: string }>(`/api/nomina/${encodeURIComponent(id)}/aprobar`, {
    method: 'POST',
  }),
  annulPayroll: (id: string) => request<{ id: string; estado: string; mensaje: string }>(`/api/nomina/${encodeURIComponent(id)}/anular`, {
    method: 'POST',
  }),
};

// 8. Módulo Contabilidad
export const accountingApi = {
  listAccounts: () => request<Account[]>('/api/contabilidad/cuentas'),
  createAccount: (account: {
    idCuenta: string;
    nombre: string;
    tipo?: string;
  }) => request<{ id: string; mensaje: string }>('/api/contabilidad/cuentas', {
    method: 'POST',
    body: JSON.stringify(account),
  }),
  listEntries: () => request<JournalEntry[]>('/api/contabilidad/asientos'),
  createEntry: (entry: {
    descripcion: string;
    lines: Array<{ idCuenta: string; debe: number; haber: number }>;
  }) => request<{ id: string; estado: string; mensaje: string }>('/api/contabilidad/asientos', {
    method: 'POST',
    body: JSON.stringify(entry),
  }),
  approveEntry: (id: string) => request<{ id: string; estado: string; mensaje: string }>(`/api/contabilidad/asientos/${encodeURIComponent(id)}/aprobar`, {
    method: 'POST',
  }),
  annulEntry: (id: string) => request<{ id: string; estado: string; mensaje: string }>(`/api/contabilidad/asientos/${encodeURIComponent(id)}/anular`, {
    method: 'POST',
  }),
};

// 9. Auditoría
export const auditApi = {
  listLogs: () => request<Array<{
    id: string;
    usuario: string;
    fechaHora: string;
    tabla: string;
    accion: string;
    valorAnterior: string | null;
    valorNuevo: string | null;
  }>>('/api/auditoria'),
};
