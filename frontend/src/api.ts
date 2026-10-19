import {
  Customer, Supplier, Product, Invoice, Reception, Delivery,
  Adjustment, Employee, Payroll, Account, JournalEntry,
  Dependent, CargoHistoryEntry, BonusCatalogItem, DeductionCatalogItem,
  Banco, CentroCosto, AuthUser
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
    const headers = new Headers(init?.headers);
    headers.set('Content-Type', 'application/json');
    const token = localStorage.getItem('licoreria_token');
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
    });
  } catch (error) {
    if (error instanceof Error && error.message.includes('fetch')) {
      throw new Error('No se pudo conectar con el servidor.');
    }
    throw error;
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const status = response.status;
    let mensaje = 'Ocurrió un error inesperado.';
    if (body && typeof body === 'object' && 'detail' in body) {
      if (typeof body.detail === 'string') {
        mensaje = body.detail;
      } else if (Array.isArray(body.detail)) {
        const validationMessages = body.detail.flatMap((issue: unknown) => {
          if (!issue || typeof issue !== 'object') return [];
          const validationIssue = issue as { loc?: unknown; msg?: unknown };
          if (typeof validationIssue.msg !== 'string') return [];
          const location = Array.isArray(validationIssue.loc)
            ? validationIssue.loc
              .filter((part): part is string | number => typeof part === 'string' || typeof part === 'number')
              .filter(part => part !== 'body')
              .map(String)
              .join('.')
            : '';
          return [location ? `${location}: ${validationIssue.msg}` : validationIssue.msg];
        });
        if (validationMessages.length > 0) {
          mensaje = validationMessages.join(' · ');
        }
      }
    }
    if (status === 401) {
      mensaje = mensaje === 'Ocurrió un error inesperado.' ? 'Credenciales inválidas o sesión expirada.' : mensaje;
    } else if (status === 403) {
      mensaje = mensaje === 'Ocurrió un error inesperado.' ? 'No tienes permiso para realizar esta acción.' : mensaje;
    } else if (status === 404) {
      mensaje = mensaje === 'Ocurrió un error inesperado.' ? 'El recurso solicitado no existe.' : mensaje;
    } else if (status === 409) {
      mensaje = mensaje === 'Ocurrió un error inesperado.' ? 'Conflicto al procesar la solicitud.' : mensaje;
    } else if (status === 422) {
      mensaje = mensaje === 'Ocurrió un error inesperado.'
        ? 'Hay datos que no cumplen los requisitos. Revisa la cédula, la fecha de nacimiento y los campos obligatorios.'
        : mensaje;
    } else if (status >= 500) {
      mensaje = 'No se pudo completar la solicitud. Intenta nuevamente más tarde.';
    } else if (status === 0) {
      mensaje = 'No se pudo conectar con el servidor.';
    }
    throw new Error(mensaje);
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

export const unitApi = {
  list: () => request<Array<{ id: string; nombre: string; factor: number }>>('/api/unidades-medida'),
  create: (data: { id: string; nombre: string; factor: number }) => request<{ mensaje: string; id: string }>('/api/unidades-medida', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  update: (id: string, data: { nombre: string; factor: number }) => request<{ mensaje: string }>(`/api/unidades-medida/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  delete: (id: string) => request<{ mensaje: string }>(`/api/unidades-medida/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }),
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
    idCategoria?: string;
    idMarca?: string;
    idPercha?: string;
    umCompra?: string;
    umVenta?: string;
    costoCompra: number;
    precioVenta: number;
  }) => request<{ id: string; mensaje: string }>(`/api/productos/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(product),
  }),
  toggleStatus: (id: string, status: 'ACTIVE' | 'INACTIVE') =>
    request<{ id: string; estado: string; mensaje: string }>(`/api/productos/${encodeURIComponent(id)}/estado`, {
      method: 'PUT',
      body: JSON.stringify({ estado: status === 'ACTIVE' ? 'ACT' : 'INA' }),
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
  listDepartments: () => request<Array<{ id: string; nombre: string }>>('/api/departamentos'),
  listCargos: () => request<Array<{ id: string; nombre: string }>>('/api/cargos'),
  createEmployee: (emp: {
    ci: string;
    nombre1: string;
    nombre2?: string;
    apellido1: string;
    apellido2?: string;
    sexo?: string;
    fechaNacimiento?: string;
    sueldo: number;
    idDepartamento?: string;
    idCargo?: string;
    telefono?: string;
    celular?: string;
    direccion?: string;
    email?: string;
  }) => request<{ id: string; mensaje: string }>('/api/empleados', {
    method: 'POST',
    body: JSON.stringify(emp),
  }),
  updateEmployee: (id: string, emp: {
    ci: string;
    nombre1: string;
    nombre2?: string;
    apellido1: string;
    apellido2?: string;
    sexo?: string;
    fechaNacimiento?: string;
    sueldo: number;
    idDepartamento?: string;
    idCargo?: string;
    telefono?: string;
    celular?: string;
    direccion?: string;
    email?: string;
  }) => request<{ id: string; mensaje: string }>(`/api/empleados/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(emp),
  }),
  listCargosHistory: (employeeId: string) =>
    request<CargoHistoryEntry[]>(`/api/empleados/${encodeURIComponent(employeeId)}/cargos`),
  assignCargo: (employeeId: string, data: { idCargo: string; fechaInicio: string; fechaFin?: string | null }) =>
    request<{ mensaje: string }>(`/api/empleados/${encodeURIComponent(employeeId)}/cargos`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  listDependents: (employeeId: string) =>
    request<Dependent[]>(`/api/empleados/${encodeURIComponent(employeeId)}/cargas`),
  createDependent: (employeeId: string, dependent: {
    ci: string;
    nombre1: string;
    nombre2?: string;
    apellido1: string;
    apellido2?: string;
    sexo: string;
    fechaNacimiento: string;
    parentesco: string;
    estadoCivil: string;
    dependencia: string;
  }) => request<{ id: string; mensaje: string }>(`/api/empleados/${encodeURIComponent(employeeId)}/cargas`, {
    method: 'POST',
    body: JSON.stringify(dependent),
  }),
  deleteDependent: (employeeId: string, cargaId: string) =>
    request<{ id: string; mensaje: string }>(`/api/empleados/${encodeURIComponent(employeeId)}/cargas/${encodeURIComponent(cargaId)}`, {
      method: 'DELETE',
    }),
  updateDependent: (employeeId: string, cargaId: string, dependent: {
    ci: string;
    nombre1: string;
    nombre2?: string;
    apellido1: string;
    apellido2?: string;
    sexo: string;
    fechaNacimiento: string;
    parentesco: string;
    estadoCivil: string;
    dependencia: string;
  }) => request<{ id: string; mensaje: string }>(`/api/empleados/${encodeURIComponent(employeeId)}/cargas/${encodeURIComponent(cargaId)}`, {
    method: 'PUT',
    body: JSON.stringify(dependent),
  }),
  listBonuses: () => request<BonusCatalogItem[]>('/api/nomina/bonificaciones'),
  listDeductions: () => request<DeductionCatalogItem[]>('/api/nomina/descuentos'),
  listPayrolls: () => request<Payroll[]>('/api/nomina'),
  createPayroll: (payroll: {
    descripcion: string;
    fechaInicio: string;
    fechaFin: string;
    idEmpleado: string;
    sueldoBase: number;
    bonificaciones?: number;
    descuentos?: number;
    lineasBonos?: Array<{ idBonificacion: string; fecha?: string; valor: number }>;
    lineasDescuentos?: Array<{ idDescuento: string; fecha?: string; valor: number }>;
  }) => request<{ id: string; estado: string; neto: string; mensaje: string }>('/api/nomina', {
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
    fecha?: string;
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
  listBancos: () => request<Banco[]>('/api/contabilidad/bancos'),
  createBanco: (data: { idBanco?: string; nombre: string; estado?: string }) =>
    request<{ id: string; mensaje: string }>('/api/contabilidad/bancos', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateBanco: (id: string, data: { nombre: string; estado?: string }) =>
    request<{ id: string; mensaje: string }>(`/api/contabilidad/bancos/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  listCentrosCostos: () => request<CentroCosto[]>('/api/contabilidad/centros-costos'),
  createCentroCosto: (data: {
    idCentroCosto?: string;
    idDepartamento: string;
    nombre: string;
    presupuestoMensual?: number;
    estado?: string;
  }) =>
    request<{ id: string; mensaje: string }>('/api/contabilidad/centros-costos', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateCentroCosto: (id: string, data: {
    idDepartamento: string;
    nombre: string;
    presupuestoMensual?: number;
    estado?: string;
  }) =>
    request<{ id: string; mensaje: string }>(`/api/contabilidad/centros-costos/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
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

// 10. Autenticación
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  success: boolean;
  token: string;
  user: AuthUser;
}

export interface InitialAdminSetupRequest {
  employee: {
    ci: string;
    nombre1: string;
    nombre2?: string;
    apellido1: string;
    apellido2?: string;
    sexo: string;
    fechaNacimiento: string;
    idDepartamento: string;
    telefono?: string;
    celular?: string;
    direccion?: string;
    email?: string;
  };
  username: string;
  password: string;
}

export interface InitialAdminSetupResponse {
  idEmpleado: string;
  idUsuario: string;
  mensaje: string;
}

export interface DemoAccount {
  role: string;
  roleId: string;
  username: string;
  password: string;
  description: string;
  color: string;
}

export const authApi = {
  setupStatus: () =>
    request<{ initialized: boolean }>('/api/auth/setup-status'),
  setupInitialAdmin: (data: InitialAdminSetupRequest) =>
    request<InitialAdminSetupResponse>('/api/auth/setup', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  login: (data: LoginRequest) =>
    request<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  register: (data: { cedula: string; username: string; password: string }) =>
    request<{ id: string; mensaje: string }>('/api/auth/registro', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  logout: (data: { userId?: string; username?: string }) =>
    request<{ success: boolean; mensaje: string }>('/api/auth/logout', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  demoAccounts: () => request<DemoAccount[]>('/api/auth/demo-accounts'),
};

// 11. Gestión de Usuarios
export interface Usuario {
  id_Usuario: string;
  id_Empleado: string;
  username: string;
  ESTADO_USR: string;
  emp_Nombre1: string | null;
  emp_Apellido1: string | null;
  dep_Nombre: string | null;
  roles: string[];
}

export interface UsuarioRol {
  id: string;
  nombre: string;
}

export interface UsuarioCreate {
  id_Empleado: string;
  username: string;
  password: string;
  rol_ids: string[];
}

export interface UsuarioUpdate {
  id_Empleado?: string;
  username?: string;
  password?: string;
  ESTADO_USR?: string;
}

export interface Empleado {
  id: string;
  nombre: string;
  apellido: string;
  departamento: string | null;
}

export interface Departamento {
  id: string;
  nombre: string;
}

export interface Rol {
  id: string;
  nombre: string;
  descripcion: string;
  estado: string;
  usuariosAsignados: number;
}

export const usuariosApi = {
  listar: () => request<Usuario[]>('/api/usuarios'),
  empleadosDisponibles: () => request<Empleado[]>('/api/usuarios/empleados-disponibles'),
  crear: (data: UsuarioCreate) =>
    request<{ id: string; mensaje: string }>('/api/usuarios', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  actualizar: (id: string, data: UsuarioUpdate) =>
    request<{ mensaje: string }>(`/api/usuarios/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  desactivar: (id: string) =>
    request<{ mensaje: string }>(`/api/usuarios/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),
  obtenerRoles: (usuarioId: string) => request<UsuarioRol[]>(`/api/usuarios/${encodeURIComponent(usuarioId)}/roles`),
  asignarRol: (usuarioId: string, rolId: string) =>
    request<{ mensaje: string }>(`/api/usuarios/${encodeURIComponent(usuarioId)}/roles`, {
      method: 'POST',
      body: JSON.stringify({ rol_id: rolId }),
    }),
  removerRol: (usuarioId: string, rolId: string) =>
    request<{ mensaje: string }>(
      `/api/usuarios/${encodeURIComponent(usuarioId)}/roles/${encodeURIComponent(rolId)}`,
      { method: 'DELETE' }
    ),
};

export const empleadosApi = {
  listar: () => request<Empleado[]>('/api/empleados'),
};

export const departamentosApi = {
  listar: () => request<Departamento[]>('/api/departamentos'),
};

export const rolesApi = {
  listar: () => request<Rol[]>('/api/auth/roles'),
};
