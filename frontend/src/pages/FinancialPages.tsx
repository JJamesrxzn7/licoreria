import { useEffect, useMemo, useState } from 'react';
import { BookOpen, Calculator, FileText, Plus, X } from 'lucide-react';
import { useGlobalStore } from '../context';
import { accountingApi, purchaseApi, salesApi } from '../api';
import { Invoice, JournalEntry, JournalEntryLine } from '../types';

const money = (value: number) => `$${value.toFixed(2)}`;
const paymentLabel: Record<Invoice['paymentMethod'], string> = { CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia', CREDIT: 'Crédito' };

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
      setNotice(`Factura ${invoiceId} anulada en MariaDB.`);
      void loadSales();
    } catch (error) {
      updateState(draft => {
        const inv = draft.invoices.find(i => i.id === invoiceId);
        if (inv) inv.status = 'ANU';
        return draft;
      });
      setNotice(`Factura ${invoiceId} anulada localmente.`);
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
      <div className="page-heading"><div><span className="eyebrow">VENTAS · FACTURACIÓN · MARIADB</span><h1>Ventas y facturas</h1><p>Historial de ventas sincronizado con MariaDB.</p></div><div className="report-period">{visibleInvoices.length} documentos · {money(total)}</div></div>
      {notice && <p className="form-notice" role="status">{notice}</p>}
      <section className="card">
        <div className="section-heading"><div><h2>Registro de ventas</h2><p>Estados: ABI (Abierto), APR (Aprobado), ANU (Anulado).</p></div><div className="filter-group"><input className="input table-search" aria-label="Buscar facturas" placeholder="Buscar factura o cliente" value={search} onChange={event => setSearch(event.target.value)} /><select className="select filter-select" aria-label="Filtrar por estado" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="">Todos los estados</option><option value="ABI">ABI</option><option value="APR">APR</option><option value="ANU">ANU</option></select></div></div>
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
        {selected.status !== 'ANU' && <div className="form-actions" style={{ marginTop: '1rem' }}><button type="button" className="btn btn-outline" onClick={() => handleAnnul(selected.id)}>Anular factura en MariaDB</button></div>}
      </section></div>}
    </div>
  );
};

export const Accounting = () => {
  const { state, updateState } = useGlobalStore();
  const [description, setDescription] = useState('');
  const [lines, setLines] = useState<JournalEntryLine[]>([{ accountId: '', debit: 0, credit: 0 }, { accountId: '', debit: 0, credit: 0 }]);
  const [editingEntryId, setEditingEntryId] = useState('');
  const [notice, setNotice] = useState('');

  const [newAccCode, setNewAccCode] = useState('');
  const [newAccName, setNewAccName] = useState('');
  const [newAccType, setNewAccType] = useState('COR');
  const [accNotice, setAccNotice] = useState('');

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

  const saveAccount = async () => {
    if (!newAccCode.trim() || !newAccName.trim()) {
      setAccNotice('Ingresa código y nombre de la cuenta.');
      return;
    }
    try {
      await accountingApi.createAccount({
        idCuenta: newAccCode.trim(),
        nombre: newAccName.trim(),
        tipo: newAccType,
      });
      setAccNotice(`Cuenta ${newAccCode.trim()} registrada con éxito en MariaDB.`);
      setNewAccCode('');
      setNewAccName('');
      void loadAccounting();
    } catch (err) {
      setAccNotice('Error al crear la cuenta en la base de datos.');
    }
  };

  useEffect(() => {
    void loadAccounting();
  }, []);

  const totalDebit = lines.reduce((sum, line) => sum + line.debit, 0);
  const totalCredit = lines.reduce((sum, line) => sum + line.credit, 0);
  const balanced = Math.abs(totalDebit - totalCredit) < 0.005;

  const updateLine = (index: number, field: keyof JournalEntryLine, value: string) => {
    setLines(previous => previous.map((line, lineIndex) => lineIndex === index
      ? { ...line, [field]: field === 'accountId' ? value : Number(value) }
      : line));
  };

  const saveDraft = async () => {
    const validLines = lines.length >= 2 && lines.every(line => line.accountId
      && state.accounts.some(account => account.id === line.accountId)
      && Number.isFinite(line.debit) && Number.isFinite(line.credit)
      && line.debit >= 0 && line.credit >= 0
      && ((line.debit > 0 && line.credit === 0) || (line.credit > 0 && line.debit === 0)));
    if (!description.trim() || !validLines) return setNotice('Ingresa un concepto y al menos dos líneas válidas, cada una con una sola columna de valor.');
    if (editingEntryId && !state.journalEntries.some(entry => entry.id === editingEntryId && entry.source === 'MANUAL' && entry.status === 'ERR')) {
      setEditingEntryId('');
      return setNotice('El asiento ya no está disponible para corrección.');
    }

    try {
      const res = await accountingApi.createEntry({
        descripcion: description.trim(),
        lines: lines.map(line => ({ idCuenta: line.accountId, debe: line.debit, haber: line.credit })),
      });
      setNotice(`Asiento ${res.id} registrado en MariaDB.`);
      void loadAccounting();
    } catch {
      const entryId = editingEntryId || `ASI-MAN-${Date.now()}`;
      updateState(draft => {
        draft.journalEntries.push({ id: entryId, date: new Date().toISOString(), description: description.trim(), lines: lines.map(line => ({ ...line })), status: 'ABI', source: 'MANUAL' });
        return draft;
      });
      setNotice('Asiento guardado localmente.');
    }

    setEditingEntryId('');
    setDescription('');
    setLines([{ accountId: '', debit: 0, credit: 0 }, { accountId: '', debit: 0, credit: 0 }]);
  };

  const editManualEntry = (entry: JournalEntry) => {
    setEditingEntryId(entry.id);
    setDescription(entry.description);
    setLines(entry.lines.map(line => ({ ...line })));
    setNotice('Corrige el asiento y guárdalo para volver a enviarlo a aprobación.');
  };

  const approveEntry = async (entryId: string) => {
    try {
      await accountingApi.approveEntry(entryId);
      setNotice(`Asiento ${entryId} aprobado y contabilizado en MariaDB.`);
      void loadAccounting();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      updateState(draft => {
        const draftEntry = draft.journalEntries.find(candidate => candidate.id === entryId);
        if (draftEntry) draftEntry.status = 'APR';
        return draft;
      });
      setNotice(`Asiento actualizado (${msg}).`);
    }
  };

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">FINANZAS · MARIADB</span><h1>Contabilidad general</h1><p>Plan de cuentas, libro diario y control de partida doble.</p></div></div>
      <section className="card"><h2 className="section-title">Registrar cuenta contable</h2>
        <div className="grid-4">
          <label className="form-group">Código (ej. 1.1.01.01)<input className="input" value={newAccCode} onChange={e => setNewAccCode(e.target.value)} placeholder="Código" /></label>
          <label className="form-group">Nombre de la cuenta<input className="input" value={newAccName} onChange={e => setNewAccName(e.target.value)} placeholder="Ej. Caja General" /></label>
          <label className="form-group">Tipo de cuenta<select className="select" value={newAccType} onChange={e => setNewAccType(e.target.value)}><option value="COR">Corriente / Normal</option><option value="AHO">Ahorros</option></select></label>
          <div className="form-action"><button type="button" className="btn btn-primary" onClick={saveAccount}><Plus size={16} /> Guardar cuenta</button></div>
        </div>
        {accNotice && <p className="form-notice" role="status">{accNotice}</p>}
      </section>
      <section className="card"><div className="section-heading"><div><h2>Plan de cuentas</h2><p>Cuentas registradas en el sistema contable ({state.accounts.length} cuentas).</p></div></div>
        <div className="table-scroll"><table><thead><tr><th>Código</th><th>Cuenta</th><th>Tipo</th><th>Saldo</th></tr></thead><tbody>
          {state.accounts.map(account => <tr key={account.id}><td>{account.code}</td><td>{account.name}</td><td>{account.type}</td><td>{money(account.balance)}</td></tr>)}
          {!state.accounts.length && <tr><td colSpan={4} className="empty-state">No hay cuentas registradas. Agrega una cuenta arriba para comenzar.</td></tr>}
        </tbody></table></div>
      </section>
      <section className="card"><div className="section-heading"><div><h2>Nuevo asiento manual</h2><p>Guarda el asiento y luego apruébalo desde el libro diario.</p></div><span className={`balance-indicator ${balanced ? 'is-balanced' : 'is-unbalanced'}`}>Debe {money(totalDebit)} · Haber {money(totalCredit)}</span></div>
        <label className="form-group">Concepto<input className="input" value={description} onChange={event => setDescription(event.target.value)} placeholder="Descripción de la transacción" /></label>
        <div className="table-scroll"><table><thead><tr><th>Cuenta</th><th>Debe (USD)</th><th>Haber (USD)</th><th></th></tr></thead><tbody>
          {lines.map((line, index) => <tr key={index}><td><select className="select" value={line.accountId} onChange={event => updateLine(index, 'accountId', event.target.value)}><option value="">Seleccionar cuenta</option>{state.accounts.map(account => <option key={account.id} value={account.id}>{account.code} · {account.name}</option>)}</select></td><td><input className="input compact-input" type="number" min="0" step="0.01" value={line.debit} onChange={event => updateLine(index, 'debit', event.target.value)} /></td><td><input className="input compact-input" type="number" min="0" step="0.01" value={line.credit} onChange={event => updateLine(index, 'credit', event.target.value)} /></td><td><button type="button" className="icon-button" aria-label="Eliminar línea" onClick={() => setLines(previous => previous.filter((_, lineIndex) => lineIndex !== index))}><X size={15} /></button></td></tr>)}
        </tbody></table></div>
        <div className="form-actions"><button type="button" className="btn btn-outline" onClick={() => setLines(previous => [...previous, { accountId: '', debit: 0, credit: 0 }])}>Agregar línea</button>{editingEntryId && <button type="button" className="btn btn-outline" onClick={() => { setEditingEntryId(''); setDescription(''); setLines([{ accountId: '', debit: 0, credit: 0 }, { accountId: '', debit: 0, credit: 0 }]); setNotice('Corrección cancelada.'); }}>Cancelar corrección</button>}<button type="button" className="btn btn-primary" onClick={saveDraft}>{editingEntryId ? 'Guardar corrección ABI' : 'Guardar asiento ABI'}</button></div>
        {notice && <p className="form-notice" role="status">{notice}</p>}
      </section>
      <section className="card"><div className="section-heading"><div><h2>Libro diario</h2><p>Asientos de ventas, compras, nómina y asientos manuales.</p></div></div>
        <div className="table-scroll"><table><thead><tr><th>Asiento</th><th>Fecha</th><th>Concepto</th><th>Líneas</th><th>Debe</th><th>Haber</th><th>Estado</th><th>Acción</th></tr></thead><tbody>
          {state.journalEntries.map(entry => {
            const debit = entry.lines.reduce((sum, line) => sum + line.debit, 0);
            const credit = entry.lines.reduce((sum, line) => sum + line.credit, 0);
            return <tr key={entry.id}><td>{entry.id}</td><td>{new Date(entry.date).toLocaleDateString('es-EC')}</td><td>{entry.description}</td><td>{entry.lines.length}</td><td>{money(debit)}</td><td>{money(credit)}</td><td><span className={`badge badge-${entry.status}`}>{entry.status}</span></td><td>{(entry.status === 'PEN' || entry.status === 'ABI') && <button type="button" className="btn btn-secondary" onClick={() => approveEntry(entry.id)}>Verificar y aprobar</button>}{entry.status === 'ERR' && entry.source === 'MANUAL' && <button type="button" className="btn btn-outline" onClick={() => editManualEntry(entry)}>Corregir</button>}</td></tr>;
          })}
          {!state.journalEntries.length && <tr><td colSpan={8} className="empty-state">Los asientos generados aparecerán aquí.</td></tr>}
        </tbody></table></div>
      </section>
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
      <div className="page-heading"><div><span className="eyebrow">ANÁLISIS DEL NEGOCIO</span><h1>Reportes</h1><p>Indicadores comerciales y financieros sincronizados con MariaDB.</p></div><span className="demo-badge">MARIADB · USD</span></div>
      <div className="metric-grid">
        <article className="metric-card"><div className="metric-icon metric-burgundy"><FileText size={18} /></div><span>Ventas netas</span><strong>{money(salesTotal)}</strong><small>{validInvoices.length} facturas no anuladas</small></article>
        <article className="metric-card"><div className="metric-icon metric-green"><PackageIcon /></div><span>Valor de inventario</span><strong>{money(inventoryValue)}</strong><small>Existencia × costo de compra</small></article>
        <article className="metric-card"><div className="metric-icon metric-amber"><BookOpen size={18} /></div><span>Productos por reponer</span><strong>{lowStock.length}</strong><small>Activos en mínimo o agotados</small></article>
        <article className="metric-card"><div className="metric-icon metric-neutral"><Calculator size={18} /></div><span>Nómina aprobada</span><strong>{money(payrollTotal)}</strong><small>{purchaseLoadError || `${pendingOrders ?? '—'} órdenes ABI en MariaDB`}</small></article>
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
