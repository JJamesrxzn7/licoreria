export type RecordStatus = 'ACTIVE' | 'INACTIVE';
export type WorkflowStatus = 'ABI' | 'APR' | 'ANU' | 'PEN' | 'ERR';

export interface Product {
  id: string;
  name: string;
  sku: string;
  barcode: string;
  brand: string;
  brandId?: string;
  category: string;
  categoryId?: string;
  ml: number;
  abv: number;
  cost: number;
  price: number;
  stock: number;
  minStock: number;
  buyUnit: string;
  buyUnitId?: string;
  sellUnit: string;
  sellUnitId?: string;
  purchaseFactor: number;
  shelf: string;
  shelfId?: string;
  status: RecordStatus;
}

export interface Customer {
  id: string;
  ciRuc: string;
  name: string;
  contact: string;
  mobile?: string;
  email: string;
  city: string;
  cityId?: string;
  address: string;
  type: 'NAT' | 'JUR';
  creditLimit: number;
  creditUsed: number;
  discountRate: number;
  status: RecordStatus;
}

export interface Supplier {
  id: string;
  ruc: string;
  name: string;
  contact: string;
  mobile?: string;
  email: string;
  city: string;
  cityId?: string;
  address: string;
  status: RecordStatus;
}

export interface CartItem {
  product: Product;
  qty: number;
  discount: number;
  subtotal: number;
}

export interface Invoice {
  id: string;
  date: string;
  customerId: string;
  items: CartItem[];
  subtotal: number;
  discount: number;
  taxRate: number;
  tax: number;
  total: number;
  paymentMethod: 'CASH' | 'CARD' | 'TRANSFER' | 'CREDIT';
  installments: number;
  status: WorkflowStatus;
}

export interface POItem {
  productId: string;
  qty: number;
  cost: number;
}

export interface PurchaseOrder {
  id: string;
  date: string;
  supplierId: string;
  items: POItem[];
  subtotal: number;
  taxRate: number;
  tax: number;
  total: number;
  status: 'ABI' | 'APR' | 'ANU';
}

export interface ReceptionItem {
  productId: string;
  expectedQty: number;
  receivedQty: number;
  diff: number;
  reason: string;
}

export interface Reception {
  id: string;
  poId: string;
  date: string;
  status: 'PENDING' | 'COMPLETED' | 'CANCELLED' | 'PEN' | 'APR' | 'ANU';
  items: ReceptionItem[];
}

export interface DeliveryItem {
  productId: string;
  expectedQty: number;
  deliveredQty: number;
  diff: number;
  reason: string;
}

export interface Delivery {
  id: string;
  invoiceId: string;
  date: string;
  status: 'PENDING' | 'COMPLETED' | 'CANCELLED' | 'PEN' | 'APR' | 'ANU';
  items: DeliveryItem[];
}

export interface Adjustment {
  id: string;
  date: string;
  type: 'IN' | 'OUT';
  productId: string;
  qty: number;
  reason: string;
  responsible: string;
  status: 'ABI' | 'APR' | 'ANU';
}

export interface Employee {
  id: string;
  ci: string;
  name: string;
  nombre1?: string;
  nombre2?: string;
  apellido1?: string;
  apellido2?: string;
  department: string;
  departmentId?: string;
  role: string;
  cargoId?: string;
  salary: number;
  birthDate?: string;
  gender?: string;
  address?: string;
  phone?: string;
  mobile?: string;
  email?: string;
  status: RecordStatus;
  familyDependents: number;
}

export interface Dependent {
  id?: string;
  ci: string;
  name?: string;
  nombre1: string;
  nombre2?: string;
  apellido1: string;
  apellido2?: string;
  sexo: string;
  fechaNacimiento: string;
  parentesco: string;
  estadoCivil: string;
  dependencia: string;
  estado?: string;
}

export interface CargoHistoryEntry {
  cargoId: string;
  cargoNombre: string;
  fechaInicio: string;
  fechaFin: string | null;
  estado: string;
}

export interface BonusCatalogItem {
  id: string;
  nombre: string;
  valor: number;
  estado: string;
}

export interface DeductionCatalogItem {
  id: string;
  nombre: string;
  valor: number;
  estado: string;
}

export interface PayrollBonusLine {
  bonusId: string;
  bonusName?: string;
  date?: string;
  amount: number;
}

export interface PayrollDeductionLine {
  deductionId: string;
  deductionName?: string;
  date?: string;
  amount: number;
}

export interface Payroll {
  id: string;
  description?: string;
  startDate?: string;
  endDate?: string;
  date: string;
  employeeId: string;
  employeeName?: string;
  department?: string;
  baseSalary: number;
  bonus: number;
  deductions: number;
  amount: number;
  status: 'PEN' | 'APR' | 'ANU' | 'ABI';
  bonusLines?: PayrollBonusLine[];
  deductionLines?: PayrollDeductionLine[];
}

export interface Account {
  id: string;
  code: string;
  name: string;
  type: 'ASSET' | 'LIABILITY' | 'EQUITY' | 'REVENUE' | 'EXPENSE';
  balance: number;
}

export interface JournalEntryLine {
  accountId: string;
  debit: number;
  credit: number;
}

export interface JournalEntry {
  id: string;
  date: string;
  description: string;
  lines: JournalEntryLine[];
  status: WorkflowStatus;
  source?: 'MANUAL';
}

export interface StoreState {
  products: Product[];
  customers: Customer[];
  suppliers: Supplier[];
  invoices: Invoice[];
  purchaseOrders: PurchaseOrder[];
  receptions: Reception[];
  deliveries: Delivery[];
  adjustments: Adjustment[];
  employees: Employee[];
  payrolls: Payroll[];
  accounts: Account[];
  journalEntries: JournalEntry[];
  settings: { taxRate: number };
}
