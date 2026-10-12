import { useEffect, useState } from 'react';
import { StoreState } from './types';

const STORAGE_KEY = 'licoreria_state_v3';

const initialState: StoreState = {
  products: [],
  customers: [],
  suppliers: [],
  invoices: [],
  purchaseOrders: [],
  receptions: [],
  deliveries: [],
  adjustments: [],
  employees: [],
  payrolls: [],
  accounts: [],
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
