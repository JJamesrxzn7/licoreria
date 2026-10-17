import { useEffect, useMemo, useState } from 'react';
import { BookOpen, Calculator, FileText, Plus, X, Building2, PieChart, Edit3, List } from 'lucide-react';
import { useGlobalStore } from '../context';
import { accountingApi, hrApi, purchaseApi, salesApi } from '../api';
import { Banco, CentroCosto, Invoice, JournalEntry, JournalEntryLine } from '../types';

const money = (value: number) => `$${value.toFixed(2)}`;
const paymentLabel: Record<Invoice['paymentMethod'], string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia', CREDIT: 'Crédito' };

const RE_SQLI = /(--|\/\*|\*\/|;|'|"|<script|UNION\s+SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE|TRUNCATE\s+TABLE|EXEC\s*\()/i;
const RE_ACCOUNT_CODE = /^\d+(\.\d+)*$/;
const RE_NAME_GENERAL = /^[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-&/]+$/;

export const Sales = () => {
  const { state, updateState } = useGlobalStore();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState<Invoice | null>(null);
  const [notice, setNotice] = useState('');

  const loadSales = async () => {
    try {
      const remoteInvoices = await salesApi.listInvoices();
      if (remoteInvoices && remoteInvoices.length) {
        updateState(draft => {
          draft.invoices = remoteInvoices;
          return draft;
        });
      }
    } catch {
      // Mantiene datos locales si la API aún no está disponible
    }
  };

  useEffect(() => {
    void loadSales();
  }, []);

  const handleAnnul = async (invoiceId: string) => {
    try {
      await salesApi.annulInvoice(invoiceId);
      setNotice(`Factura ${invoiceId} anulada exitosamente.`);
      void loadSales();
    } catch (error) {
      updateState(draft => {
        const inv = draft.invoices.find(i => i.id === invoiceId);
        if (inv) inv.status = 'ANU';
        return draft;
      });
      setNotice(`Factura ${invoiceId} anulada exitosamente.`);
    }
    if (selected?.id === invoiceId) setSelected(null);
  };

  const visibleInvoices = useMemo(() => state.invoices.filter(invoice => {
    const customer = state.customers.find(candidate => candidate.id === invoice.customerId);
    const methodStr = paymentLabel[invoice.paymentMethod] || invoice.paymentMethod;
    return (!statusFilter || invoice.status === statusFilter)
      && `${invoice.id} ${customer?.name ?? ''} ${methodStr}`.toLowerCase().includes(search.toLowerCase());
  }), [state.invoices, state.customers, statusFilter, search]);
  const total = visibleInvoices.reduce((sum, invoice) => invoice.status === 'ANU' ? sum : sum + invoice.total, 0);

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">VENTAS · FACTURACIÓN</span><h1>Ventas y facturas</h1><p>Historial de ventas y facturación comercial.</p></div><div className="report-period">{visibleInvoices.length} documentos · {money(total)}</div></div>
      {notice && <p className="form-notice" role="status">{notice}</p>}
      <section className="card">
        <div className="section-heading"><div><h2>Registro de ventas</h2><p>Estados: ABI (Abierto), APR (Aprobado), ANU (Anulado).</p></div><div className="filter-group"><input className="input table-search" aria-label="Buscar facturas" placeholder="Buscar factura o cliente" value={search} onChange={event => setSearch(event.target.value)} /><select className="select filter-select" aria-label="Filtrar por estado" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="">-- Filtrar por estado (Todos) --</option><option value="ABI">ABI</option><option value="APR">APR</option><option value="ANU">ANU</option></select></div></div>
        <div className="table-scroll"><table><thead><tr><th>Factura</th><th>Fecha</th><th>Cliente</th><th>Subtotal</th><th>Descuento</th><th>Impuesto</th><th>Total</th><th>Pago</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>
          {visibleInvoices.map(invoice => <tr key={invoice.id}><td>{invoice.id}</td><td>{new Date(invoice.date).toLocaleString('es-EC')}</td><td>{state.customers.find(customer => customer.id === invoice.customerId)?.name ?? invoice.customerId}</td><td>{money(invoice.subtotal)}</td><td>{money(invoice.discount)}</td><td>{money(invoice.tax)}</td><td><strong>{money(invoice.total)}</strong></td><td>{paymentLabel[invoice.paymentMethod] || invoice.paymentMethod}{invoice.paymentMethod === 'CREDIT' ? ` · ${invoice.installments} cuotas` : ''}</td><td><span className={`badge badge-${invoice.status}`}>{invoice.status}</span></td><td><button type="button" className="btn btn-outline" onClick={() => setSelected(invoice)}>Ver</button></td></tr>)}
          {!visibleInvoices.length && <tr><td colSpan={10} className="empty-state">No hay facturas que coincidan con estos filtros.</td></tr>}
        </tbody></table></div>
      </section>
      {selected && <div className="modal-backdrop" role="presentation" onClick={event => { if (event.target === event.currentTarget) setSelected(null); }}><section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="invoice-title">
        <div className="section-heading"><div><span className="eyebrow">DETALLE DE VENTA</span><h2 id="invoice-title">{selected.id}</h2></div><button type="button" className="icon-button" aria-label="Cerrar detalle" onClick={() => setSelected(null)}><X size={18} /></button></div>
        <p className="helper-text">{state.customers.find(customer => customer.id === selected.customerId)?.name ?? selected.customerId} · {new Date(selected.date).toLocaleString('es-EC')}</p>
        <div className="table-scroll"><table><thead><tr><th>Producto</th><th>Cantidad</th><th>Precio</th><th>Importe</th></tr></thead><tbody>{selected.items?.map((item, index) => <tr key={`${selected.id}-${item.product?.id || index}`}><td>{item.product?.name || item.product?.id || 'Producto'}</td><td>{item.qty}</td><td>{money(item.product?.price || 0)}</td><td>{money(item.subtotal)}</td></tr>)}</tbody></table></div>
        <div className="invoice-totals"><span>Subtotal <strong>{money(selected.subtotal)}</strong></span><span>Descuento <strong>{money(selected.discount)}</strong></span><span>Impuestos ({selected.taxRate}%) <strong>{money(selected.tax)}</strong></span><span>Total <strong>{money(selected.total)}</strong></span></div>
        {selected.status !== 'ANU' && <div className="form-actions" style={{ marginTop: '1rem' }}><button type="button" className="btn btn-outline" onClick={() => handleAnnul(selected.id)}>Anular factura</button></div>}
      </section></div>}
    </div>
  );
};

export const Accounting = ({ initialTab = 'diario' }: { initialTab?: 'diario' | 'cuentas' | 'bancos' | 'centros_costos' }) => {
  const { state, updateState } = useGlobalStore();
  const [activeTab, setActiveTab] = useState<'diario' | 'cuentas' | 'bancos' | 'centros_costos'>(initialTab);

  useEffect(() => {
    if (initialTab) setActiveTab(initialTab);
  }, [initialTab]);

  // --- ASIENTOS CONTABLES & LIBRO DIARIO ---
  const [entryDate, setEntryDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [description, setDescription] = useState('');
  const [lines, setLines] = useState<JournalEntryLine[]>([{ accountId: '', debit: 0, credit: 0 }, { accountId: '', debit: 0, credit: 0 }]);
  const [editingEntryId, setEditingEntryId] = useState('');
  const [notice, setNotice] = useState('');

  // --- PLAN DE CUENTAS ---
  const [newAccCode, setNewAccCode] = useState('');
  const [newAccName, setNewAccName] = useState('');
  const [newAccType, setNewAccType] = useState('DET');
  const [accSearch, setAccSearch] = useState('');
  const [accNotice, setAccNotice] = useState('');

  // --- BANCOS ---
  const [bancos, setBancos] = useState<Banco[]>([]);
  const [bancoForm, setBancoForm] = useState({ idBanco: '', nombre: '', estado: 'ACT' });
  const [editingBanco, setEditingBanco] = useState<Banco | null>(null);
  const [editBancoForm, setEditBancoForm] = useState({ nombre: '', estado: 'ACT' });
  const [bancoNotice, setBancoNotice] = useState('');
  const [bancoLoading, setBancoLoading] = useState(false);

  // --- CENTROS DE COSTOS ---
  const [centrosCostos, setCentrosCostos] = useState<CentroCosto[]>([]);
  const [departments, setDepartments] = useState<Array<{ id: string; nombre: string }>>([]);
  const [ccoForm, setCcoForm] = useState({
    idCentroCosto: '',
    idDepartamento: '',
    nombre: '',
    presupuestoMensual: 0,
    estado: 'ACT',
  });
  const [editingCco, setEditingCco] = useState<CentroCosto | null>(null);
  const [editCcoForm, setEditCcoForm] = useState({
    idDepartamento: '',
    nombre: '',
    presupuestoMensual: 0,
    estado: 'ACT',
  });
  const [ccoNotice, setCcoNotice] = useState('');
  const [ccoLoading, setCcoLoading] = useState(false);

  const loadAccounting = async () => {
    try {
      const [remoteAccounts, remoteEntries] = await Promise.all([
        accountingApi.listAccounts().catch(() => null),
        accountingApi.listEntries().catch(() => null),
      ]);
      if (remoteAccounts !== null || remoteEntries !== null) {
        updateState(draft => {
          if (Array.isArray(remoteAccounts)) draft.accounts = remoteAccounts;
          if (Array.isArray(remoteEntries)) draft.journalEntries = remoteEntries;
          return draft;
        });
      }
    } catch {
      // Conserva estado local
    }
  };

  const loadBancos = async () => {
    try {
      const res = await accountingApi.listBancos();
      if (Array.isArray(res)) setBancos(res);
    } catch {
      // ignore
    }
  };

  const loadCentrosCostos = async () => {
    try {
      const [resCco, resDep] = await Promise.all([
        accountingApi.listCentrosCostos().catch(() => []),
        hrApi.listDepartments().catch(() => []),
      ]);
      if (Array.isArray(resCco)) setCentrosCostos(resCco);
      if (Array.isArray(resDep) && resDep.length) {
        setDepartments(resDep);
      } else {
        setDepartments([
          { id: 'DEP-000001', nombre: 'Administración' },
          { id: 'DEP-000002', nombre: 'Bodega y Logística' },
          { id: 'DEP-TEST', nombre: 'Ventas y Comercial' },
        ]);
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    void loadAccounting();
    void loadBancos();
    void loadCentrosCostos();
  }, []);

  // Guardar nueva cuenta contable (MAY o DET)
  const saveAccount = async () => {
    const code = newAccCode.trim();
    const name = newAccName.trim();

    if (!code || !name) {
      setAccNotice('Ingresa código y nombre de la cuenta contable.');
      return;
    }
    if (!RE_ACCOUNT_CODE.test(code)) {
      setAccNotice('El código de cuenta solo debe contener dígitos numéricos separados por puntos (ej: 1, 1.1, 1.1.01).');
      return;
    }
    if (code.length > 15) {
      setAccNotice('El código de cuenta no puede superar 15 caracteres.');
      return;
    }
    if (name.length < 3 || name.length > 60) {
      setAccNotice('El nombre de la cuenta debe tener entre 3 y 60 caracteres.');
      return;
    }
    if (RE_SQLI.test(name)) {
      setAccNotice('El nombre de la cuenta contiene caracteres o patrones no permitidos (anti-SQLi detectado).');
      return;
    }
    if (!newAccType || (newAccType !== 'MAY' && newAccType !== 'DET')) {
      setAccNotice('Selecciona si la cuenta es de tipo MAYOR (MAY) o DETALLE (DET).');
      return;
    }
    try {
      const res = await accountingApi.createAccount({
        idCuenta: code,
        nombre: name,
        tipo: newAccType,
      });
      setAccNotice(res.mensaje || `Cuenta ${code} registrada con éxito.`);
      setNewAccCode('');
      setNewAccName('');
      void loadAccounting();
    } catch (err: any) {
      setAccNotice(err.message || 'Error al crear la cuenta contable.');
    }
  };

  const totalDebit = lines.reduce((sum, line) => sum + line.debit, 0);
  const totalCredit = lines.reduce((sum, line) => sum + line.credit, 0);
  const balanced = Math.abs(totalDebit - totalCredit) < 0.005;

  const updateLine = (index: number, field: keyof JournalEntryLine, value: string) => {
    setLines(previous => previous.map((line, lineIndex) => lineIndex === index
      ? { ...line, [field]: field === 'accountId' ? value : Number(value) }
      : line));
  };

  // Guardar asiento con validación de cuentas de MAYOR y fecha explícita
  const saveDraft = async () => {
    if (!entryDate) {
      setNotice('Ingresa la fecha de la transacción contable.');
      return;
    }
    const entryYear = new Date(entryDate).getFullYear();
    if (isNaN(entryYear) || entryYear < 2000 || entryYear > 2100) {
      setNotice('La fecha de la transacción debe corresponder a un año válido entre 2000 y 2100.');
      return;
    }

    const cleanDesc = description.trim();
    if (!cleanDesc || cleanDesc.length < 5 || cleanDesc.length > 30) {
      setNotice('El concepto o glosa del asiento debe tener entre 5 y 30 caracteres.');
      return;
    }
    if (RE_SQLI.test(cleanDesc)) {
      setNotice('El concepto contiene caracteres o sentencias no permitidas (SQL injection detectado).');
      return;
    }

    if (lines.length < 2) {
      setNotice('El asiento debe tener al menos dos líneas contables.');
      return;
    }

    const validLines = lines.every(line => line.accountId
      && state.accounts.some(account => account.id === line.accountId)
      && Number.isFinite(line.debit) && Number.isFinite(line.credit)
      && line.debit >= 0 && line.credit >= 0
      && ((line.debit > 0 && line.credit === 0) || (line.credit > 0 && line.debit === 0)));

    if (!validLines) {
      setNotice('Todas las líneas deben tener cuenta válida y registrar valor exclusivamente en Debe o Haber (mayor a 0).');
      return;
    }

    if (totalDebit <= 0) {
      setNotice('El valor total del asiento debe ser mayor a $0.00.');
      return;
    }

    if (!balanced) {
      setNotice('El asiento debe estar cuadrado (Total Debe debe ser igual al Total Haber).');
      return;
    }

    // Validación vital: El sistema NO debe permitir que se hagan asientos usando cuentas de MAYOR
    const mayorAccount = lines
      .map(line => state.accounts.find(a => a.id === line.accountId))
      .find(a => a && (a.type === 'MAY' || a.type === 'MAYOR'));

    if (mayorAccount) {
      setNotice(`Validación contable vital: La cuenta '${mayorAccount.code} · ${mayorAccount.name}' es de tipo MAYOR. No se puede imputar en asientos contables. Seleccione cuentas de DETALLE (DET).`);
      return;
    }

    if (editingEntryId && !state.journalEntries.some(entry => entry.id === editingEntryId && entry.source === 'MANUAL' && entry.status === 'ERR')) {
      setEditingEntryId('');
      return setNotice('El asiento ya no está disponible para corrección.');
    }

    try {
      const res = await accountingApi.createEntry({
        descripcion: cleanDesc,
        fecha: entryDate,
        lines: lines.map(line => ({ idCuenta: line.accountId, debe: line.debit, haber: line.credit })),
      });
      setNotice(res.mensaje || `Asiento ${res.id} registrado exitosamente con fecha ${entryDate}.`);
      void loadAccounting();
    } catch (err: any) {
      const entryId = editingEntryId || `ASI-MAN-${Date.now()}`;
      updateState(draft => {
        draft.journalEntries.push({ id: entryId, date: entryDate, description: cleanDesc, lines: lines.map(line => ({ ...line })), status: 'ABI', source: 'MANUAL' });
        return draft;
      });
      setNotice(err.message || 'Asiento registrado exitosamente.');
    }

    setEditingEntryId('');
    setDescription('');
    setLines([{ accountId: '', debit: 0, credit: 0 }, { accountId: '', debit: 0, credit: 0 }]);
  };

  const editManualEntry = (entry: JournalEntry) => {
    setEditingEntryId(entry.id);
    setDescription(entry.description);
    if (entry.date) {
      setEntryDate(entry.date.slice(0, 10));
    }
    setLines(entry.lines.map(line => ({ ...line })));
    setNotice('Corrige el asiento y guárdalo para volver a enviarlo a aprobación.');
  };

  const approveEntry = async (entryId: string) => {
    try {
      await accountingApi.approveEntry(entryId);
      setNotice(`Asiento ${entryId} aprobado y contabilizado exitosamente.`);
      void loadAccounting();
    } catch (err: any) {
      const msg = err instanceof Error ? err.message : String(err);
      updateState(draft => {
        const draftEntry = draft.journalEntries.find(candidate => candidate.id === entryId);
        if (draftEntry) draftEntry.status = 'APR';
        return draft;
      });
      setNotice(`Asiento actualizado (${msg}).`);
    }
  };

  const annulEntry = async (entryId: string) => {
    if (!window.confirm(`¿Estás seguro de anular el asiento ${entryId}?`)) return;
    try {
      await accountingApi.annulEntry(entryId);
      setNotice(`Asiento ${entryId} anulado.`);
      void loadAccounting();
    } catch (err: any) {
      setNotice(err.message || 'Error al anular el asiento.');
    }
  };

  // Guardar banco
  const handleSaveBanco = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanName = bancoForm.nombre.trim();
    if (!cleanName || cleanName.length < 3 || cleanName.length > 50) {
      setBancoNotice('El nombre de la entidad bancaria debe tener entre 3 y 50 caracteres.');
      return;
    }
    if (RE_SQLI.test(cleanName)) {
      setBancoNotice('El nombre del banco contiene patrones o sentencias no permitidas (anti-SQLi detectado).');
      return;
    }
    if (!RE_NAME_GENERAL.test(cleanName)) {
      setBancoNotice('El nombre del banco contiene caracteres no permitidos.');
      return;
    }
    setBancoLoading(true);
    try {
      const res = await accountingApi.createBanco({
        idBanco: bancoForm.idBanco.trim() || undefined,
        nombre: cleanName,
        estado: bancoForm.estado || 'ACT',
      });
      setBancoNotice(res.mensaje || 'Banco registrado exitosamente.');
      setBancoForm({ idBanco: '', nombre: '', estado: 'ACT' });
      void loadBancos();
    } catch (err: any) {
      setBancoNotice(err.message || 'Error al registrar el banco.');
    } finally {
      setBancoLoading(false);
    }
  };

  const handleUpdateBanco = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingBanco) return;
    const cleanName = editBancoForm.nombre.trim();
    if (!cleanName || cleanName.length < 3 || cleanName.length > 50) {
      setBancoNotice('El nombre del banco debe tener entre 3 y 50 caracteres.');
      return;
    }
    if (RE_SQLI.test(cleanName)) {
      setBancoNotice('El nombre del banco contiene patrones no permitidos (anti-SQLi).');
      return;
    }
    if (!RE_NAME_GENERAL.test(cleanName)) {
      setBancoNotice('El nombre del banco contiene caracteres no permitidos.');
      return;
    }
    setBancoLoading(true);
    try {
      const res = await accountingApi.updateBanco(editingBanco.id, {
        nombre: cleanName,
        estado: editBancoForm.estado,
      });
      setBancoNotice(res.mensaje || 'Banco actualizado exitosamente.');
      setEditingBanco(null);
      void loadBancos();
    } catch (err: any) {
      setBancoNotice(err.message || 'Error al actualizar el banco.');
    } finally {
      setBancoLoading(false);
    }
  };

  const toggleBancoStatus = async (banco: Banco) => {
    const nuevoEstado = banco.estado === 'ACT' ? 'INA' : 'ACT';
    try {
      await accountingApi.updateBanco(banco.id, {
        nombre: banco.nombre,
        estado: nuevoEstado,
      });
      setBancoNotice(`Banco ${banco.id} ahora está ${nuevoEstado === 'ACT' ? 'Activo' : 'Inactivo'}.`);
      void loadBancos();
    } catch (err: any) {
      setBancoNotice(err.message || 'Error al cambiar estado del banco.');
    }
  };

  // Guardar centro de costo
  const handleSaveCco = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanName = ccoForm.nombre.trim();
    if (!cleanName || cleanName.length < 3 || cleanName.length > 50) {
      setCcoNotice('El nombre del centro de costo debe tener entre 3 y 50 caracteres.');
      return;
    }
    if (RE_SQLI.test(cleanName)) {
      setCcoNotice('El nombre contiene caracteres o patrones no permitidos (anti-SQLi detectado).');
      return;
    }
    if (!RE_NAME_GENERAL.test(cleanName)) {
      setCcoNotice('El nombre solo puede contener letras, números, espacios y caracteres básicos.');
      return;
    }
    if (!ccoForm.idDepartamento) {
      setCcoNotice('Debe seleccionar el departamento asignado al centro de costo.');
      return;
    }
    const presupuesto = Number(ccoForm.presupuestoMensual) || 0;
    if (presupuesto < 0 || presupuesto > 1000000) {
      setCcoNotice('El presupuesto mensual debe estar entre $0.00 y $1,000,000.00.');
      return;
    }
    setCcoLoading(true);
    try {
      const res = await accountingApi.createCentroCosto({
        idCentroCosto: ccoForm.idCentroCosto.trim() || undefined,
        idDepartamento: ccoForm.idDepartamento,
        nombre: cleanName,
        presupuestoMensual: presupuesto,
        estado: ccoForm.estado || 'ACT',
      });
      setCcoNotice(res.mensaje || 'Centro de Costo registrado exitosamente.');
      setCcoForm({
        idCentroCosto: '',
        idDepartamento: '',
        nombre: '',
        presupuestoMensual: 0,
        estado: 'ACT',
      });
      void loadCentrosCostos();
    } catch (err: any) {
      setCcoNotice(err.message || 'Error al registrar el centro de costo.');
    } finally {
      setCcoLoading(false);
    }
  };

  const handleUpdateCco = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCco) return;
    const cleanName = editCcoForm.nombre.trim();
    if (!cleanName || cleanName.length < 3 || cleanName.length > 50) {
      setCcoNotice('El nombre del centro de costo debe tener entre 3 y 50 caracteres.');
      return;
    }
    if (RE_SQLI.test(cleanName)) {
      setCcoNotice('El nombre contiene caracteres o patrones no permitidos (anti-SQLi).');
      return;
    }
    if (!RE_NAME_GENERAL.test(cleanName)) {
      setCcoNotice('El nombre solo puede contener caracteres válidos.');
      return;
    }
    if (!editCcoForm.idDepartamento) {
      setCcoNotice('Debe seleccionar el departamento asignado.');
      return;
    }
    const presupuesto = Number(editCcoForm.presupuestoMensual) || 0;
    if (presupuesto < 0 || presupuesto > 1000000) {
      setCcoNotice('El presupuesto mensual debe estar entre $0.00 y $1,000,000.00.');
      return;
    }
    setCcoLoading(true);
    try {
      const res = await accountingApi.updateCentroCosto(editingCco.id, {
        idDepartamento: editCcoForm.idDepartamento,
        nombre: cleanName,
        presupuestoMensual: presupuesto,
        estado: editCcoForm.estado,
      });
      setCcoNotice(res.mensaje || 'Centro de Costo actualizado exitosamente.');
      setEditingCco(null);
      void loadCentrosCostos();
    } catch (err: any) {
      setCcoNotice(err.message || 'Error al actualizar el centro de costo.');
    } finally {
      setCcoLoading(false);
    }
  };

  const toggleCcoStatus = async (cco: CentroCosto) => {
    const nuevoEstado = cco.estado === 'ACT' ? 'INA' : 'ACT';
    try {
      await accountingApi.updateCentroCosto(cco.id, {
        idDepartamento: cco.idDepartamento,
        nombre: cco.nombre,
        presupuestoMensual: cco.presupuestoMensual,
        estado: nuevoEstado,
      });
      setCcoNotice(`Centro de Costo ${cco.id} ahora está ${nuevoEstado === 'ACT' ? 'Activo' : 'Inactivo'}.`);
      void loadCentrosCostos();
    } catch (err: any) {
      setCcoNotice(err.message || 'Error al cambiar estado del centro de costo.');
    }
  };

  const filteredAccounts = useMemo(() => {
    if (!accSearch.trim()) return state.accounts;
    const q = accSearch.toLowerCase();
    return state.accounts.filter(a =>
      a.code.toLowerCase().includes(q) ||
      a.name.toLowerCase().includes(q) ||
      (a.type && a.type.toLowerCase().includes(q))
    );
  }, [state.accounts, accSearch]);

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">FINANZAS & CONTROL</span>
          <h1>Contabilidad General</h1>
          <p>Gestión del libro diario, plan de cuentas (MAY/DET), entidades bancarias y centros de costos.</p>
        </div>
      </div>

      {/* Pestañas de navegación contable */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', borderBottom: '2px solid #e2e8f0', paddingBottom: '10px', flexWrap: 'wrap' }}>
        <button
          type="button"
          className={`btn ${activeTab === 'diario' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveTab('diario')}
        >
          <BookOpen size={16} /> Libro Diario y Asientos
        </button>
        <button
          type="button"
          className={`btn ${activeTab === 'cuentas' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveTab('cuentas')}
        >
          <List size={16} /> Plan de Cuentas ({state.accounts.length})
        </button>
        <button
          type="button"
          className={`btn ${activeTab === 'bancos' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveTab('bancos')}
        >
          <Building2 size={16} /> Bancos ({bancos.length})
        </button>
        <button
          type="button"
          className={`btn ${activeTab === 'centros_costos' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveTab('centros_costos')}
        >
          <PieChart size={16} /> Centros de Costos ({centrosCostos.length})
        </button>
      </div>

      {/* =========================================================================
          PESTAÑA 1: LIBRO DIARIO Y ASIENTOS MANUALES
          ========================================================================= */}
      {activeTab === 'diario' && (
        <>
          <section className="card">
            <div className="section-heading">
              <div>
                <h2>{editingEntryId ? `Corregir Asiento (${editingEntryId})` : 'Nuevo Asiento Manual'}</h2>
                <p>Ingresa la fecha de la transacción y las cuentas de Detalle (DET). No se permiten cuentas de Mayor.</p>
              </div>
              <span className={`balance-indicator ${balanced ? 'is-balanced' : 'is-unbalanced'}`}>
                Debe {money(totalDebit)} · Haber {money(totalCredit)}
              </span>
            </div>

            <div className="grid-3" style={{ marginBottom: '16px' }}>
              <label className="form-group">
                <span>Fecha de la transacción <strong style={{ color: '#ef4444' }}>*</strong></span>
                <input
                  className="input"
                  type="date"
                  value={entryDate}
                  onChange={event => setEntryDate(event.target.value)}
                  required
                />
                <small style={{ fontSize: '11px', color: '#64748b' }}>Permite registrar operaciones de días o semanas anteriores</small>
              </label>

              <label className="form-group" style={{ gridColumn: 'span 2' }}>
                <span>Concepto / Glosa <strong style={{ color: '#ef4444' }}>*</strong></span>
                <input
                  className="input"
                  minLength={5}
                  maxLength={30}
                  pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-&/]+"
                  title="Entre 5 y 30 caracteres (letras, números y signos básicos)."
                  value={description}
                  onChange={event => setDescription(event.target.value)}
                  placeholder="Ej: Pago de arriendo local matriz"
                />
                <small style={{ fontSize: '11px', color: '#64748b' }}>Entre 5 y 30 caracteres (CHAR(30))</small>
              </label>
            </div>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Cuenta contable (Solo DETALLE - DET)</th>
                    <th style={{ width: '160px' }}>Debe (USD)</th>
                    <th style={{ width: '160px' }}>Haber (USD)</th>
                    <th style={{ width: '50px' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line, index) => (
                    <tr key={index}>
                      <td>
                        <select
                          className="select"
                          value={line.accountId}
                          onChange={event => updateLine(index, 'accountId', event.target.value)}
                        >
                          <option value="">-- Seleccione una cuenta --</option>
                          {state.accounts.map(account => {
                            const isMayor = account.type === 'MAY' || account.type === 'MAYOR';
                            return (
                              <option
                                key={account.id}
                                value={account.id}
                                disabled={isMayor}
                                style={isMayor ? { color: '#94a3b8', background: '#f8fafc', fontStyle: 'italic' } : {}}
                              >
                                {account.code} · {account.name} {isMayor ? '[MAYOR - No imputable]' : '(DET)'}
                              </option>
                            );
                          })}
                        </select>
                      </td>
                      <td>
                        <input
                          className="input compact-input"
                          type="number"
                          min="0"
                          max="1000000"
                          step="0.01"
                          value={line.debit}
                          onChange={event => updateLine(index, 'debit', event.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          className="input compact-input"
                          type="number"
                          min="0"
                          max="1000000"
                          step="0.01"
                          value={line.credit}
                          onChange={event => updateLine(index, 'credit', event.target.value)}
                        />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="icon-button"
                          aria-label="Eliminar línea"
                          onClick={() => setLines(previous => previous.filter((_, lineIndex) => lineIndex !== index))}
                        >
                          <X size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="form-actions" style={{ marginTop: '16px' }}>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => setLines(previous => [...previous, { accountId: '', debit: 0, credit: 0 }])}
              >
                <Plus size={15} /> Agregar línea
              </button>
              {editingEntryId && (
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => {
                    setEditingEntryId('');
                    setDescription('');
                    setLines([{ accountId: '', debit: 0, credit: 0 }, { accountId: '', debit: 0, credit: 0 }]);
                    setNotice('Corrección cancelada.');
                  }}
                >
                  Cancelar corrección
                </button>
              )}
              <button type="button" className="btn btn-primary" onClick={saveDraft}>
                {editingEntryId ? 'Guardar corrección ABI' : 'Guardar asiento ABI'}
              </button>
            </div>

            {notice && (
              <p
                className="form-notice"
                role="status"
                style={notice.includes('vital') || notice.includes('Error') ? { color: '#ef4444', borderColor: '#fca5a5', background: '#fef2f2' } : {}}
              >
                {notice}
              </p>
            )}
          </section>

          <section className="card">
            <div className="section-heading">
              <div>
                <h2>Libro Diario</h2>
                <p>Asientos contables ordenados cronológicamente por fecha de transacción.</p>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Asiento</th>
                    <th>Fecha Transacción</th>
                    <th>Concepto</th>
                    <th>Líneas</th>
                    <th>Debe</th>
                    <th>Haber</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {state.journalEntries.map(entry => {
                    const debit = entry.lines.reduce((sum, line) => sum + line.debit, 0);
                    const credit = entry.lines.reduce((sum, line) => sum + line.credit, 0);
                    const formattedDate = entry.date ? new Date(entry.date).toLocaleDateString('es-EC') : 'Sin fecha';
                    return (
                      <tr key={entry.id}>
                        <td><strong>{entry.id}</strong></td>
                        <td>{formattedDate}</td>
                        <td>{entry.description}</td>
                        <td>{entry.lines.length} líneas</td>
                        <td>{money(debit)}</td>
                        <td>{money(credit)}</td>
                        <td><span className={`badge badge-${entry.status}`}>{entry.status}</span></td>
                        <td>
                          <div className="inline-actions">
                            {(entry.status === 'PEN' || entry.status === 'ABI') && (
                              <>
                                <button type="button" className="btn btn-secondary" onClick={() => approveEntry(entry.id)}>
                                  Aprobar
                                </button>
                                <button type="button" className="btn btn-outline" onClick={() => annulEntry(entry.id)}>
                                  Anular
                                </button>
                              </>
                            )}
                            {entry.status === 'ERR' && entry.source === 'MANUAL' && (
                              <button type="button" className="btn btn-outline" onClick={() => editManualEntry(entry)}>
                                Corregir
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {!state.journalEntries.length && <tr><td colSpan={8} className="empty-state">No hay asientos contables registrados.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {/* =========================================================================
          PESTAÑA 2: PLAN DE CUENTAS (MAYOR vs DETALLE)
          ========================================================================= */}
      {activeTab === 'cuentas' && (
        <>
          <section className="card">
            <h2 className="section-title">Registrar Cuenta Contable</h2>
            <div className="grid-4">
              <label className="form-group">
                <span>Código contable <strong style={{ color: '#ef4444' }}>*</strong></span>
                <input
                  className="input"
                  maxLength={15}
                  pattern="^\d+(\.\d+)*$"
                  title="Formato numérico jerárquico separado por puntos (ej: 1, 1.1, 1.1.01)"
                  value={newAccCode}
                  onChange={e => setNewAccCode(e.target.value.replace(/[^0-9.]/g, ''))}
                  placeholder="Ej. 1.1.01.001"
                  required
                />
              </label>

              <label className="form-group">
                <span>Nombre de la cuenta <strong style={{ color: '#ef4444' }}>*</strong></span>
                <input
                  className="input"
                  minLength={3}
                  maxLength={60}
                  pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-&/]+"
                  title="Entre 3 y 60 caracteres válidos (letras, números y signos básicos)."
                  value={newAccName}
                  onChange={e => setNewAccName(e.target.value)}
                  placeholder="Ej. Caja Chica"
                  required
                />
              </label>

              <label className="form-group">
                <span>Tipo de cuenta (TIPO_CUENTA) <strong style={{ color: '#ef4444' }}>*</strong></span>
                <select
                  className="select"
                  value={newAccType}
                  onChange={e => setNewAccType(e.target.value)}
                >
                  <option value="">-- Seleccione tipo de cuenta --</option>
                  <option value="MAY">MAY · Cuenta de Mayor (Agrupadora / No imputable)</option>
                  <option value="DET">DET · Cuenta de Detalle (Transaccional / Imputable)</option>
                </select>
                <small style={{ fontSize: '11px', color: '#64748b' }}>Las cuentas MAYOR no permiten asentar en el libro diario</small>
              </label>

              <div className="form-action" style={{ alignSelf: 'flex-end' }}>
                <button type="button" className="btn btn-primary" onClick={saveAccount}>
                  <Plus size={16} /> Guardar cuenta
                </button>
              </div>
            </div>
            {accNotice && <p className="form-notice" role="status">{accNotice}</p>}
          </section>

          <section className="card">
            <div className="section-heading">
              <div>
                <h2>Catálogo de Cuentas Contables</h2>
                <p>{filteredAccounts.length} cuentas registradas en el sistema</p>
              </div>
              <input
                className="input table-search"
                aria-label="Buscar cuentas"
                placeholder="Buscar por código, nombre o tipo"
                value={accSearch}
                onChange={e => setAccSearch(e.target.value)}
              />
            </div>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Código</th>
                    <th>Nombre de la Cuenta</th>
                    <th>Tipo</th>
                    <th>Imputable en Asientos</th>
                    <th>Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAccounts.map(account => {
                    const isMayor = account.type === 'MAY' || account.type === 'MAYOR';
                    return (
                      <tr key={account.id} style={isMayor ? { background: '#f8fafc', fontWeight: 600 } : {}}>
                        <td><code>{account.code}</code></td>
                        <td>{account.name}</td>
                        <td>
                          {isMayor ? (
                            <span style={{ background: '#e0f2fe', color: '#0369a1', padding: '3px 8px', borderRadius: '4px', fontSize: '12px' }}>
                              MAYOR (MAY)
                            </span>
                          ) : (
                            <span style={{ background: '#dcfce7', color: '#15803d', padding: '3px 8px', borderRadius: '4px', fontSize: '12px' }}>
                              DETALLE (DET)
                            </span>
                          )}
                        </td>
                        <td>
                          {isMayor ? (
                            <span style={{ color: '#94a3b8', fontSize: '12px' }}>No (Solo Agrupador)</span>
                          ) : (
                            <span style={{ color: '#16a34a', fontSize: '12px', fontWeight: 600 }}>Sí (Permitido)</span>
                          )}
                        </td>
                        <td><strong>{money(account.balance)}</strong></td>
                      </tr>
                    );
                  })}
                  {!filteredAccounts.length && (
                    <tr>
                      <td colSpan={5} className="empty-state">
                        No hay cuentas contables que coincidan con la búsqueda.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {/* =========================================================================
          PESTAÑA 3: BANCOS (BANCOS)
          ========================================================================= */}
      {activeTab === 'bancos' && (
        <>
          <section className="card">
            <h2 className="section-title">Registrar Entidad Bancaria (BANCOS)</h2>
            <form onSubmit={handleSaveBanco}>
              <div className="grid-3">
                <label className="form-group">
                  <span>Código de Banco (id_Banco)</span>
                  <input
                    className="input"
                    maxLength={10}
                    value={bancoForm.idBanco}
                    onChange={e => setBancoForm({ ...bancoForm, idBanco: e.target.value.toUpperCase() })}
                    placeholder="Ej. BAN-000001 (Auto si vacío)"
                  />
                  <small style={{ fontSize: '11px', color: '#64748b' }}>Dejar vacío para correlativo automático</small>
                </label>

                <label className="form-group">
                  <span>Nombre del Banco (ban_Nombre) <strong style={{ color: '#ef4444' }}>*</strong></span>
                  <input
                    className="input"
                    minLength={3}
                    maxLength={50}
                    pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-&/]+"
                    title="Entre 3 y 50 caracteres (letras, números, espacios y signos básicos)"
                    value={bancoForm.nombre}
                    onChange={e => setBancoForm({ ...bancoForm, nombre: e.target.value })}
                    placeholder="Ej: Banco Pichincha, Banco Guayaquil"
                    required
                  />
                </label>

                <label className="form-group">
                  <span>Estado (ESTADO_BAN)</span>
                  <select
                    className="select"
                    value={bancoForm.estado}
                    onChange={e => setBancoForm({ ...bancoForm, estado: e.target.value })}
                  >
                    <option value="">-- Seleccione estado --</option>
                    <option value="ACT">Activo (ACT)</option>
                    <option value="INA">Inactivo (INA)</option>
                  </select>
                </label>
              </div>

              <div className="form-actions" style={{ marginTop: '12px' }}>
                <button type="submit" className="btn btn-primary" disabled={bancoLoading}>
                  <Plus size={16} /> {bancoLoading ? 'Guardando...' : 'Guardar Banco'}
                </button>
              </div>
            </form>
            {bancoNotice && <p className="form-notice" role="status">{bancoNotice}</p>}
          </section>

          <section className="card">
            <div className="section-heading">
              <div>
                <h2>Directorio de Entidades Bancarias</h2>
                <p>{bancos.length} entidades bancarias registradas en la tabla BANCOS</p>
              </div>
            </div>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Código (id_Banco)</th>
                    <th>Nombre de la Entidad Bancaria</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {bancos.map(b => (
                    <tr key={b.id}>
                      <td><code>{b.id}</code></td>
                      <td><strong>{b.nombre}</strong></td>
                      <td>
                        <span className={`badge ${b.estado === 'ACT' ? 'badge-APR' : 'badge-ANU'}`}>
                          {b.estado === 'ACT' ? 'Activo' : 'Inactivo'}
                        </span>
                      </td>
                      <td>
                        <div className="inline-actions">
                          <button
                            type="button"
                            className="btn btn-outline"
                            onClick={() => {
                              setEditingBanco(b);
                              setEditBancoForm({ nombre: b.nombre, estado: b.estado || 'ACT' });
                            }}
                          >
                            <Edit3 size={14} /> Editar
                          </button>
                          <button
                            type="button"
                            className="btn btn-outline"
                            onClick={() => toggleBancoStatus(b)}
                          >
                            {b.estado === 'ACT' ? 'Inactivar' : 'Activar'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!bancos.length && (
                    <tr>
                      <td colSpan={4} className="empty-state">
                        No hay bancos registrados. Utilice el formulario superior para añadir entidades bancarias.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* Modal Edición de Banco */}
          {editingBanco && (
            <div className="modal-backdrop" role="presentation" onClick={e => { if (e.target === e.currentTarget) setEditingBanco(null); }}>
              <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="edit-banco-title">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">MODIFICAR ENTIDAD</span>
                    <h2 id="edit-banco-title">{editingBanco.id}</h2>
                  </div>
                  <button type="button" className="icon-button" aria-label="Cerrar modal" onClick={() => setEditingBanco(null)}>
                    <X size={18} />
                  </button>
                </div>

                <form onSubmit={handleUpdateBanco}>
                  <div className="grid-2">
                    <label className="form-group">
                      <span>Nombre del Banco *</span>
                      <input
                        className="input"
                        minLength={3}
                        maxLength={50}
                        pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-&/]+"
                        title="Entre 3 y 50 caracteres (letras, números, espacios y signos básicos)"
                        value={editBancoForm.nombre}
                        onChange={e => setEditBancoForm({ ...editBancoForm, nombre: e.target.value })}
                        required
                      />
                    </label>

                    <label className="form-group">
                      <span>Estado *</span>
                      <select
                        className="select"
                        value={editBancoForm.estado}
                        onChange={e => setEditBancoForm({ ...editBancoForm, estado: e.target.value })}
                      >
                        <option value="">-- Seleccione estado --</option>
                        <option value="ACT">Activo (ACT)</option>
                        <option value="INA">Inactivo (INA)</option>
                      </select>
                    </label>
                  </div>

                  <div className="form-actions" style={{ marginTop: '16px' }}>
                    <button type="button" className="btn btn-outline" onClick={() => setEditingBanco(null)}>
                      Cancelar
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={bancoLoading}>
                      {bancoLoading ? 'Guardando...' : 'Guardar Cambios'}
                    </button>
                  </div>
                </form>
              </section>
            </div>
          )}
        </>
      )}

      {/* =========================================================================
          PESTAÑA 4: CENTROS DE COSTOS (CENTROS_COSTOS)
          ========================================================================= */}
      {activeTab === 'centros_costos' && (
        <>
          <section className="card">
            <h2 className="section-title">Registrar Centro de Costo (CENTROS_COSTOS)</h2>
            <form onSubmit={handleSaveCco}>
              <div className="grid-4">
                <label className="form-group">
                  <span>Código (id_CentroCosto)</span>
                  <input
                    className="input"
                    maxLength={10}
                    value={ccoForm.idCentroCosto}
                    onChange={e => setCcoForm({ ...ccoForm, idCentroCosto: e.target.value.toUpperCase() })}
                    placeholder="Ej. CCO-000001 (Auto)"
                  />
                  <small style={{ fontSize: '11px', color: '#64748b' }}>Dejar vacío para correlativo automático</small>
                </label>

                <label className="form-group">
                  <span>Departamento (DEPARTAMENTOS) <strong style={{ color: '#ef4444' }}>*</strong></span>
                  <select
                    className="select"
                    value={ccoForm.idDepartamento}
                    onChange={e => setCcoForm({ ...ccoForm, idDepartamento: e.target.value })}
                    required
                  >
                    <option value="">-- Seleccione un departamento --</option>
                    {departments.map(d => (
                      <option key={d.id} value={d.id}>{d.nombre} ({d.id})</option>
                    ))}
                  </select>
                </label>

                <label className="form-group">
                  <span>Nombre del Centro de Costo <strong style={{ color: '#ef4444' }}>*</strong></span>
                  <input
                    className="input"
                    minLength={3}
                    maxLength={50}
                    pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-&/]+"
                    title="Entre 3 y 50 caracteres (letras, números, espacios y signos básicos)"
                    value={ccoForm.nombre}
                    onChange={e => setCcoForm({ ...ccoForm, nombre: e.target.value })}
                    placeholder="Ej. Bodega Matriz, Ventas POS"
                    required
                  />
                </label>

                <label className="form-group">
                  <span>Presupuesto Mensual (USD) <strong style={{ color: '#ef4444' }}>*</strong></span>
                  <input
                    className="input"
                    type="number"
                    min="0"
                    max="1000000"
                    step="0.01"
                    value={ccoForm.presupuestoMensual}
                    onChange={e => setCcoForm({ ...ccoForm, presupuestoMensual: Number(e.target.value) })}
                    required
                  />
                </label>
              </div>

              <div className="form-actions" style={{ marginTop: '12px' }}>
                <button type="submit" className="btn btn-primary" disabled={ccoLoading}>
                  <Plus size={16} /> {ccoLoading ? 'Guardando...' : 'Guardar Centro de Costo'}
                </button>
              </div>
            </form>
            {ccoNotice && <p className="form-notice" role="status">{ccoNotice}</p>}
          </section>

          <section className="card">
            <div className="section-heading">
              <div>
                <h2>Directorio de Centros de Costos</h2>
                <p>{centrosCostos.length} centros de costos registrados en la tabla CENTROS_COSTOS</p>
              </div>
            </div>

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Código (id_CentroCosto)</th>
                    <th>Centro de Costo</th>
                    <th>Departamento Asignado</th>
                    <th>Presupuesto Mensual</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {centrosCostos.map(cco => (
                    <tr key={cco.id}>
                      <td><code>{cco.id}</code></td>
                      <td><strong>{cco.nombre}</strong></td>
                      <td>{cco.departamento || cco.idDepartamento}</td>
                      <td>{money(Number(cco.presupuestoMensual || 0))}</td>
                      <td>
                        <span className={`badge ${cco.estado === 'ACT' ? 'badge-APR' : 'badge-ANU'}`}>
                          {cco.estado === 'ACT' ? 'Activo' : 'Inactivo'}
                        </span>
                      </td>
                      <td>
                        <div className="inline-actions">
                          <button
                            type="button"
                            className="btn btn-outline"
                            onClick={() => {
                              setEditingCco(cco);
                              setEditCcoForm({
                                idDepartamento: cco.idDepartamento,
                                nombre: cco.nombre,
                                presupuestoMensual: Number(cco.presupuestoMensual || 0),
                                estado: cco.estado || 'ACT',
                              });
                            }}
                          >
                            <Edit3 size={14} /> Editar
                          </button>
                          <button
                            type="button"
                            className="btn btn-outline"
                            onClick={() => toggleCcoStatus(cco)}
                          >
                            {cco.estado === 'ACT' ? 'Inactivar' : 'Activar'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!centrosCostos.length && (
                    <tr>
                      <td colSpan={6} className="empty-state">
                        No hay centros de costos registrados. Utilice el formulario superior para añadir nuevos registros.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* Modal Edición Centro de Costo */}
          {editingCco && (
            <div className="modal-backdrop" role="presentation" onClick={e => { if (e.target === e.currentTarget) setEditingCco(null); }}>
              <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="edit-cco-title">
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">MODIFICAR CENTRO DE COSTO</span>
                    <h2 id="edit-cco-title">{editingCco.id}</h2>
                  </div>
                  <button type="button" className="icon-button" aria-label="Cerrar modal" onClick={() => setEditingCco(null)}>
                    <X size={18} />
                  </button>
                </div>

                <form onSubmit={handleUpdateCco}>
                  <div className="grid-2">
                    <label className="form-group">
                      <span>Nombre del Centro de Costo *</span>
                      <input
                        className="input"
                        minLength={3}
                        maxLength={50}
                        pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-&/]+"
                        title="Entre 3 y 50 caracteres (letras, números, espacios y signos básicos)"
                        value={editCcoForm.nombre}
                        onChange={e => setEditCcoForm({ ...editCcoForm, nombre: e.target.value })}
                        required
                      />
                    </label>

                    <label className="form-group">
                      <span>Departamento *</span>
                      <select
                        className="select"
                        value={editCcoForm.idDepartamento}
                        onChange={e => setEditCcoForm({ ...editCcoForm, idDepartamento: e.target.value })}
                        required
                      >
                        <option value="">-- Seleccione un departamento --</option>
                        {departments.map(d => (
                          <option key={d.id} value={d.id}>{d.nombre} ({d.id})</option>
                        ))}
                      </select>
                    </label>

                    <label className="form-group">
                      <span>Presupuesto Mensual ($) *</span>
                      <input
                        className="input"
                        type="number"
                        min="0"
                        max="1000000"
                        step="0.01"
                        value={editCcoForm.presupuestoMensual}
                        onChange={e => setEditCcoForm({ ...editCcoForm, presupuestoMensual: Number(e.target.value) })}
                        required
                      />
                    </label>

                    <label className="form-group">
                      <span>Estado *</span>
                      <select
                        className="select"
                        value={editCcoForm.estado}
                        onChange={e => setEditCcoForm({ ...editCcoForm, estado: e.target.value })}
                      >
                        <option value="">-- Seleccione estado --</option>
                        <option value="ACT">Activo (ACT)</option>
                        <option value="INA">Inactivo (INA)</option>
                      </select>
                    </label>
                  </div>

                  <div className="form-actions" style={{ marginTop: '16px' }}>
                    <button type="button" className="btn btn-outline" onClick={() => setEditingCco(null)}>
                      Cancelar
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={ccoLoading}>
                      {ccoLoading ? 'Guardando...' : 'Guardar Cambios'}
                    </button>
                  </div>
                </form>
              </section>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export const Reports = () => {
  const { state } = useGlobalStore();
  const [pendingOrders, setPendingOrders] = useState<number | null>(null);
  const [purchaseLoadError, setPurchaseLoadError] = useState('');
  const validInvoices = state.invoices.filter(invoice => invoice.status !== 'ANU');
  const salesTotal = validInvoices.reduce((sum, invoice) => sum + invoice.total, 0);
  const inventoryValue = state.products.filter(product => product.status === 'ACTIVE').reduce((sum, product) => sum + product.stock * product.cost, 0);
  const activeProducts = state.products.filter(product => product.status === 'ACTIVE');
  const lowStock = activeProducts.filter(product => product.stock <= product.minStock);
  const payrollTotal = state.payrolls.filter(payroll => payroll.status === 'APR').reduce((sum, payroll) => sum + payroll.amount, 0);
  const topProducts = useMemo(() => {
    const quantityById = new Map<string, number>();
    for (const invoice of validInvoices) for (const item of invoice.items) {
      if (!item.product) continue;
      quantityById.set(item.product.id, (quantityById.get(item.product.id) ?? 0) + item.qty);
    }
    return [...quantityById.entries()].sort((left, right) => right[1] - left[1]).slice(0, 5);
  }, [validInvoices]);

  useEffect(() => {
    void purchaseApi.listOrders()
      .then(orders => {
        setPendingOrders(orders.filter(order => order.estado === 'ABI').length);
        setPurchaseLoadError('');
      })
      .catch(error => setPurchaseLoadError(error instanceof Error ? error.message : 'No se pudieron cargar las compras.'));
  }, []);

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">ANÁLISIS DEL NEGOCIO</span><h1>Reportes</h1><p>Indicadores comerciales y financieros consolidados.</p></div><span className="demo-badge">USD</span></div>
      <div className="metric-grid">
        <article className="metric-card"><div className="metric-icon metric-burgundy"><FileText size={18} /></div><span>Ventas netas</span><strong>{money(salesTotal)}</strong><small>{validInvoices.length} facturas no anuladas</small></article>
        <article className="metric-card"><div className="metric-icon metric-green"><PackageIcon /></div><span>Valor de inventario</span><strong>{money(inventoryValue)}</strong><small>Existencia × costo de compra</small></article>
        <article className="metric-card"><div className="metric-icon metric-amber"><BookOpen size={18} /></div><span>Productos por reponer</span><strong>{lowStock.length}</strong><small>Activos en mínimo o agotados</small></article>
        <article className="metric-card"><div className="metric-icon metric-neutral"><Calculator size={18} /></div><span>Nómina aprobada</span><strong>{money(payrollTotal)}</strong><small>{purchaseLoadError || `${pendingOrders ?? '—'} órdenes ABI pendientes`}</small></article>
      </div>
      <section className="card"><div className="section-heading"><div><h2>Productos más vendidos</h2><p>Unidades acumuladas en las facturas activas.</p></div></div><div className="table-scroll"><table><thead><tr><th>Producto</th><th>Categoría</th><th>Unidades</th><th>Existencia actual</th><th>Valor de inventario</th></tr></thead><tbody>
        {topProducts.map(([productId, quantity]) => {
          const product = state.products.find(candidate => candidate.id === productId);
          if (!product) return null;
          return <tr key={productId}><td>{product.name}</td><td>{product.category}</td><td>{quantity}</td><td>{product.stock}</td><td>{money(product.stock * product.cost)}</td></tr>;
        })}
        {!topProducts.length && <tr><td colSpan={5} className="empty-state">Registra ventas para generar el reporte de rotación.</td></tr>}
      </tbody></table></div></section>
    </div>
  );
};

const PackageIcon = () => <BookOpen size={18} />;
