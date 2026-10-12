import { useEffect, useMemo, useState } from 'react';
import { ArrowDownToLine, ArrowUpRight, Plus, Save, Trash2, Users, Wine } from 'lucide-react';
import { useGlobalStore } from '../context';
import { catalogApi, customerApi, hrApi, purchaseApi, supplierApi } from '../api';
import { Customer, Employee, Supplier } from '../types';

const money = (value: number) => `$${value.toFixed(2)}`;

export const Dashboard = () => {
  const { state, updateState } = useGlobalStore();
  const [taxInput, setTaxInput] = useState(String(state.settings.taxRate));
  const [pendingPurchases, setPendingPurchases] = useState<number | null>(null);
  const [purchaseLoadError, setPurchaseLoadError] = useState('');
  const grossSales = state.invoices.filter(invoice => invoice.status !== 'ANU').reduce((sum, invoice) => sum + invoice.total, 0);
  const lowStock = state.products.filter(product => product.status === 'ACTIVE' && product.stock <= product.minStock);
  const totalStock = state.products.filter(product => product.status === 'ACTIVE').reduce((sum, product) => sum + product.stock, 0);

  useEffect(() => {
    void purchaseApi.listOrders()
      .then(orders => {
        setPendingPurchases(orders.filter(order => order.estado === 'ABI').length);
        setPurchaseLoadError('');
      })
      .catch(error => setPurchaseLoadError(error instanceof Error ? error.message : 'No se pudieron cargar las compras.'));
  }, []);

  const chartDays = useMemo(() => Array.from({ length: 7 }, (_, offset) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - offset));
    const key = date.toLocaleDateString('es-EC');
    const amount = state.invoices.filter(invoice => new Date(invoice.date).toLocaleDateString('es-EC') === key)
      .reduce((sum, invoice) => sum + invoice.total, 0);
    return { label: date.toLocaleDateString('es-EC', { weekday: 'short' }), amount };
  }), [state.invoices]);
  const maxSales = Math.max(...chartDays.map(day => day.amount), 1);

  const saveTaxRate = () => {
    const value = Number(taxInput);
    if (!Number.isFinite(value) || value < 0 || value > 100) return alert('La tasa debe estar entre 0 y 100%.');
    updateState(draft => { draft.settings.taxRate = value; return draft; });
  };

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">PANEL DE CONTROL · MARIADB</span><h1>Buenos días, equipo</h1><p>Resumen operativo de La Cava conectado a la base de datos.</p></div><span className="demo-badge">Quito, Ecuador</span></div>
      <div className="metric-grid">
        <article className="metric-card"><div className="metric-icon metric-burgundy"><ArrowUpRight size={19} /></div><span>Ventas registradas</span><strong>{money(grossSales)}</strong><small>{state.invoices.length} facturas registradas</small></article>
        <article className="metric-card"><div className="metric-icon metric-green"><Wine size={19} /></div><span>Unidades en bodega</span><strong>{totalStock}</strong><small>{state.products.length} referencias de licor</small></article>
        <article className="metric-card"><div className="metric-icon metric-amber"><ArrowDownToLine size={19} /></div><span>Alertas de stock</span><strong>{lowStock.length}</strong><small>Productos en mínimo o agotados</small></article>
        <article className="metric-card"><div className="metric-icon metric-neutral"><Users size={19} /></div><span>Compras por preparar</span><strong>{pendingPurchases ?? '—'}</strong><small>{purchaseLoadError || 'Órdenes ABI en MariaDB'}</small></article>
      </div>
      <div className="dashboard-grid">
        <section className="card sales-chart">
          <div className="section-heading"><div><h2>Ventas recientes</h2><p>Últimos 7 días · USD</p></div><span className="report-period">Esta semana</span></div>
          <div className="bar-chart" role="img" aria-label="Ventas de los últimos siete días">
            {chartDays.map(day => <div className="bar-column" key={day.label}><span>{day.amount ? money(day.amount) : ''}</span><div className="bar-track"><i style={{ height: `${Math.max(day.amount / maxSales * 100, 3)}%` }} /></div><small>{day.label}</small></div>)}
          </div>
        </section>
        <section className="card stock-panel">
          <div className="section-heading"><div><h2>Reponer pronto</h2><p>Existencia igual o inferior al mínimo</p></div><span className="low-stock-count">{lowStock.length}</span></div>
          {lowStock.length ? lowStock.slice(0, 5).map(product => <div className="stock-alert-row" key={product.id}><div><strong>{product.name}</strong><small>{product.sku} · Percha {product.shelf}</small></div><span>{product.stock} / {product.minStock}</span></div>) : <p className="empty-state">No hay productos bajo el mínimo.</p>}
        </section>
      </div>
      <div className="dashboard-grid lower-grid">
        <section className="card"><div className="section-heading"><div><h2>Movimientos recientes</h2><p>Facturas creadas desde el POS</p></div></div>
          <div className="table-scroll"><table><thead><tr><th>Documento</th><th>Cliente</th><th>Fecha</th><th>Total</th><th>Estado</th></tr></thead><tbody>
            {state.invoices.slice(-5).reverse().map(invoice => <tr key={invoice.id}><td>{invoice.id}</td><td>{state.customers.find(customer => customer.id === invoice.customerId)?.name ?? invoice.customerId}</td><td>{new Date(invoice.date).toLocaleDateString('es-EC')}</td><td>{money(invoice.total)}</td><td><span className={`badge badge-${invoice.status}`}>{invoice.status}</span></td></tr>)}
            {!state.invoices.length && <tr><td colSpan={5} className="empty-state">Las ventas que registres aparecerán aquí.</td></tr>}
          </tbody></table></div>
        </section>
        <section className="card tax-settings"><div className="section-heading"><div><h2>Configuración de IVA</h2><p>Tasa aplicada a órdenes y facturas</p></div></div>
          <label className="form-group">Tasa de impuesto (%)<input className="input" type="number" min="0" max="100" step="0.1" value={taxInput} onChange={event => setTaxInput(event.target.value)} /></label>
          <button className="btn btn-outline" type="button" onClick={saveTaxRate}>Guardar tasa</button>
        </section>
      </div>
    </div>
  );
};

export const Customers = () => {
  const { state, updateState } = useGlobalStore();
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState('');
  const [cities, setCities] = useState<Array<{ id: string; nombre: string; provincia: string }>>([]);
  const [form, setForm] = useState<Partial<Customer>>({ type: 'NAT', creditLimit: 0, discountRate: 0, status: 'ACTIVE', cityId: 'UIO' });

  const loadCustomers = async () => {
    try {
      const remoteCustomers = await customerApi.listCustomers();
      if (Array.isArray(remoteCustomers)) {
        updateState(draft => {
          draft.customers = remoteCustomers;
          return draft;
        });
      }
    } catch {
      // Conserva estado local
    }
  };

  useEffect(() => {
    void loadCustomers();
    void catalogApi.getCiudades().then(list => {
      if (list && list.length) {
        setCities(list);
        if (!form.cityId) setForm(prev => ({ ...prev, cityId: list[0].id }));
      }
    }).catch(() => null);
  }, []);

  const visibleCustomers = state.customers.filter(customer => `${customer.name} ${customer.ciRuc} ${customer.city}`.toLowerCase().includes(search.toLowerCase()));

  const save = async () => {
    if (!form.name?.trim() || !form.ciRuc?.trim()) return setNotice('Ingresa nombre e identificación.');
    const selectedCity = cities.find(c => c.id === form.cityId);
    try {
      const res = await customerApi.createCustomer({
        nombre: form.name.trim(),
        ciRuc: form.ciRuc.trim(),
        idCiudad: form.cityId || 'UIO',
        telefono: form.contact?.trim() || '',
        email: form.email?.trim() || '',
        direccion: form.address?.trim() || '',
        cupoCredito: Number(form.creditLimit || 0),
        descuento: Number(form.discountRate || 0),
      });
      setNotice(`Cliente ${res.id} registrado en MariaDB.`);
      void loadCustomers();
    } catch (err) {
      const newCustomer: Customer = {
        id: `CLI-${Date.now()}`, name: form.name.trim(), ciRuc: form.ciRuc.trim(), contact: form.contact?.trim() ?? '',
        email: form.email?.trim() ?? '', city: selectedCity?.nombre ?? form.city?.trim() ?? 'Quito',
        cityId: form.cityId || 'UIO', address: form.address?.trim() ?? '',
        type: form.type ?? 'NAT', creditLimit: Number(form.creditLimit ?? 0), creditUsed: 0,
        discountRate: Number(form.discountRate ?? 0), status: form.status ?? 'ACTIVE',
      };
      updateState(draft => { draft.customers.push(newCustomer); return draft; });
      setNotice('Cliente guardado localmente.');
    }
    setForm({ type: 'NAT', creditLimit: 0, discountRate: 0, status: 'ACTIVE', cityId: cities[0]?.id || 'UIO' });
  };

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">RELACIÓN COMERCIAL · MARIADB</span><h1>Clientes</h1><p>Datos de contacto, condiciones de crédito y descuentos en MariaDB.</p></div></div>
      <section className="card"><h2 className="section-title">Registrar cliente</h2>
        <div className="grid-4">
          <label className="form-group">Cédula / RUC<input className="input" value={form.ciRuc ?? ''} onChange={event => setForm({ ...form, ciRuc: event.target.value })} /></label>
          <label className="form-group">Nombre / razón social<input className="input" value={form.name ?? ''} onChange={event => setForm({ ...form, name: event.target.value })} /></label>
          <label className="form-group">Tipo<select className="select" value={form.type ?? 'NAT'} onChange={event => setForm({ ...form, type: event.target.value as Customer['type'] })}><option value="NAT">Persona natural</option><option value="JUR">Persona jurídica</option></select></label>
          <label className="form-group">Teléfono<input className="input" value={form.contact ?? ''} onChange={event => setForm({ ...form, contact: event.target.value })} /></label>
          <label className="form-group">Correo<input className="input" type="email" value={form.email ?? ''} onChange={event => setForm({ ...form, email: event.target.value })} /></label>
          <label className="form-group">Ciudad (Cargada desde BD)
            <select className="select" value={form.cityId ?? 'UIO'} onChange={event => setForm({ ...form, cityId: event.target.value })}>
              {cities.map(c => <option key={c.id} value={c.id}>{c.nombre} ({c.provincia})</option>)}
              {!cities.length && <option value="UIO">Quito (Pichincha)</option>}
            </select>
          </label>
          <label className="form-group">Dirección<input className="input" value={form.address ?? ''} onChange={event => setForm({ ...form, address: event.target.value })} /></label>
          <label className="form-group">Límite de crédito<input className="input" type="number" min="0" step="0.01" value={form.creditLimit ?? 0} onChange={event => setForm({ ...form, creditLimit: Number(event.target.value) })} /></label>
          <label className="form-group">Descuento (%)<input className="input" type="number" min="0" max="100" value={form.discountRate ?? 0} onChange={event => setForm({ ...form, discountRate: Number(event.target.value) })} /></label>
          <div className="form-action"><button type="button" className="btn btn-primary" onClick={save}><Plus size={16} /> Guardar cliente</button></div>
        </div>
        {notice && <p className="form-notice" role="status">{notice}</p>}
      </section>
      <section className="card"><div className="section-heading"><div><h2>Directorio</h2><p>{visibleCustomers.length} registros</p></div><input className="input table-search" aria-label="Buscar clientes" placeholder="Buscar nombre, identificación o ciudad" value={search} onChange={event => setSearch(event.target.value)} /></div>
        <div className="table-scroll"><table><thead><tr><th>Identificación</th><th>Cliente</th><th>Tipo</th><th>Contacto</th><th>Ciudad</th><th>Crédito disponible</th><th>Descuento</th><th>Estado</th></tr></thead>
          <tbody>{visibleCustomers.map(customer => <tr key={customer.id}><td>{customer.ciRuc}</td><td>{customer.name}</td><td>{customer.type}</td><td>{customer.contact || '—'}</td><td>{customer.city || '—'}</td><td>{money(Math.max(customer.creditLimit - customer.creditUsed, 0))}</td><td>{customer.discountRate}%</td><td><span className={`badge badge-${customer.status === 'ACTIVE' ? 'active' : 'inactive'}`}>{customer.status === 'ACTIVE' ? 'Activo' : 'Inactivo'}</span></td></tr>)}</tbody>
        </table></div>
      </section>
    </div>
  );
};

export const Suppliers = () => {
  const { state, updateState } = useGlobalStore();
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState('');
  const [noticeType, setNoticeType] = useState<'success' | 'error'>('success');
  const [cities, setCities] = useState<Array<{ id: string; nombre: string; provincia: string }>>([]);
  const [form, setForm] = useState<{
    ruc: string;
    name: string;
    contact: string;
    mobile: string;
    email: string;
    cityId: string;
    address: string;
  }>({
    ruc: '',
    name: '',
    contact: '',
    mobile: '',
    email: '',
    cityId: 'UIO',
    address: '',
  });

  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const nextSupplierId = useMemo(() => {
    let maxNum = 0;
    for (const s of state.suppliers) {
      if (!s.id) continue;
      const m = s.id.match(/(\d+)/);
      if (m) {
        const val = parseInt(m[1], 10);
        if (!isNaN(val) && val > maxNum) maxNum = val;
      }
    }
    return `prv_${String(maxNum + 1).padStart(6, '0')}`;
  }, [state.suppliers]);

  const loadSuppliers = async () => {
    try {
      const remoteSuppliers = await supplierApi.listSuppliers();
      if (Array.isArray(remoteSuppliers)) {
        updateState(draft => {
          draft.suppliers = remoteSuppliers;
          return draft;
        });
      }
    } catch {
      // Estado existente
    }
  };

  useEffect(() => {
    void loadSuppliers();
    void catalogApi.getCiudades().then(list => {
      if (list && list.length) {
        setCities(list);
        if (!form.cityId) setForm(prev => ({ ...prev, cityId: list[0].id }));
      }
    }).catch(() => null);
  }, []);

  // Funciones de validación
  const validateField = (name: string, value: string): string => {
    const val = (value || '').trim();
    switch (name) {
      case 'ruc':
        if (!val) return 'El RUC es obligatorio.';
        if (val.length !== 13) return `El RUC debe tener exactamente 13 dígitos numéricos (actual: ${val.length}).`;
        return '';
      case 'name':
        if (!val) return 'La razón social / nombre es obligatoria.';
        if (val.length < 3) return 'Debe tener al menos 3 caracteres.';
        return '';
      case 'contact':
        if (!val) return '';
        if (val.length < 9 || val.length > 10) return 'El teléfono debe tener entre 9 y 10 dígitos numéricos.';
        return '';
      case 'mobile':
        if (!val) return 'El número de celular es obligatorio.';
        if (!/^09\d{8}$/.test(val)) return 'El celular debe tener 10 dígitos y empezar con 09 (ej: 0991234567).';
        return '';
      case 'email':
        if (!val) return 'El correo electrónico es obligatorio.';
        if (!val.includes('@') || !val.includes('.')) return 'El correo debe contener "@" y un punto "." obligatoriamente.';
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) return 'Formato de correo no válido (ej: proveedor@empresa.com).';
        return '';
      case 'address':
        if (!val) return 'La dirección es obligatoria.';
        if (!/\bav/i.test(val)) return 'La dirección debe incluir la palabra o abreviatura "Av" (ej: Av. Amazonas).';
        return '';
      default:
        return '';
    }
  };

  const handleBlur = (field: string) => {
    setTouched(prev => ({ ...prev, [field]: true }));
    const errorMsg = validateField(field, (form as any)[field] ?? '');
    setErrors(prev => ({ ...prev, [field]: errorMsg }));
  };

  const handleRucChange = (val: string) => {
    const digitsOnly = val.replace(/\D/g, '').slice(0, 13);
    setForm(prev => ({ ...prev, ruc: digitsOnly }));
    if (touched.ruc) {
      setErrors(prev => ({ ...prev, ruc: validateField('ruc', digitsOnly) }));
    }
  };

  const handlePhoneChange = (val: string) => {
    const digitsOnly = val.replace(/\D/g, '').slice(0, 10);
    setForm(prev => ({ ...prev, contact: digitsOnly }));
    if (touched.contact) {
      setErrors(prev => ({ ...prev, contact: validateField('contact', digitsOnly) }));
    }
  };

  const handleMobileChange = (val: string) => {
    const digitsOnly = val.replace(/\D/g, '').slice(0, 10);
    setForm(prev => ({ ...prev, mobile: digitsOnly }));
    if (touched.mobile) {
      setErrors(prev => ({ ...prev, mobile: validateField('mobile', digitsOnly) }));
    }
  };

  const handleNameChange = (val: string) => {
    setForm(prev => ({ ...prev, name: val }));
    if (touched.name) {
      setErrors(prev => ({ ...prev, name: validateField('name', val) }));
    }
  };

  const handleEmailChange = (val: string) => {
    setForm(prev => ({ ...prev, email: val }));
    if (touched.email) {
      setErrors(prev => ({ ...prev, email: validateField('email', val) }));
    }
  };

  const handleAddressChange = (val: string) => {
    setForm(prev => ({ ...prev, address: val }));
    if (touched.address) {
      setErrors(prev => ({ ...prev, address: validateField('address', val) }));
    }
  };

  const validateAll = () => {
    const newErrors: Record<string, string> = {
      ruc: validateField('ruc', form.ruc),
      name: validateField('name', form.name),
      contact: validateField('contact', form.contact),
      mobile: validateField('mobile', form.mobile),
      email: validateField('email', form.email),
      address: validateField('address', form.address),
    };
    setErrors(newErrors);
    setTouched({
      ruc: true,
      name: true,
      contact: true,
      mobile: true,
      email: true,
      address: true,
    });
    return Object.values(newErrors).every(err => !err);
  };

  const save = async () => {
    if (!validateAll()) {
      setNoticeType('error');
      setNotice('Por favor revisa y corrige los campos marcados en rojo antes de guardar.');
      return;
    }

    const selectedCity = cities.find(c => c.id === form.cityId);
    const assignedId = nextSupplierId;

    try {
      await supplierApi.createSupplier({
        id: assignedId,
        nombre: form.name.trim(),
        ruc: form.ruc.trim(),
        idCiudad: form.cityId || 'UIO',
        telefono: form.contact?.trim() || '',
        celular: form.mobile?.trim() || '',
        email: form.email?.trim() || '',
        direccion: form.address?.trim() || '',
      });
      setNoticeType('success');
      setNotice(`Proveedor ${form.name.trim()} (${assignedId}) registrado exitosamente.`);
      void loadSuppliers();
    } catch {
      const supplier: Supplier = {
        id: assignedId,
        name: form.name.trim(),
        ruc: form.ruc.trim(),
        contact: form.contact?.trim() ?? '',
        mobile: form.mobile?.trim() ?? '',
        email: form.email?.trim() ?? '',
        city: selectedCity?.nombre ?? 'Quito',
        cityId: form.cityId || 'UIO',
        address: form.address?.trim() ?? '',
        status: 'ACTIVE',
      };
      updateState(draft => {
        draft.suppliers.push(supplier);
        return draft;
      });
      setNoticeType('success');
      setNotice(`Proveedor ${form.name.trim()} (${assignedId}) registrado exitosamente.`);
    }

    setForm({
      ruc: '',
      name: '',
      contact: '',
      mobile: '',
      email: '',
      cityId: cities[0]?.id || 'UIO',
      address: '',
    });
    setTouched({});
    setErrors({});
  };

  const deleteSupplier = (id: string) => {
    updateState(draft => {
      draft.suppliers = draft.suppliers.filter(s => s.id !== id);
      return draft;
    });
    setNoticeType('success');
    setNotice('Registro de proveedor eliminado.');
  };

  const visibleSuppliers = state.suppliers.filter(supplier =>
    `${supplier.id} ${supplier.name} ${supplier.ruc} ${supplier.city || ''} ${supplier.mobile || ''}`.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ABASTECIMIENTO</span>
          <h1>Proveedores</h1>
          <p>Directorio y registro de proveedores comerciales.</p>
        </div>
      </div>

      <section className="card">
        <div className="section-heading">
          <div>
            <h2 className="section-title" style={{ margin: 0 }}>Registrar proveedor</h2>
            <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--muted, #64748b)' }}>
              Código asignado correlativo: <span className="id-badge">{nextSupplierId}</span>
            </p>
          </div>
        </div>

        <div className="grid-4" style={{ marginTop: '16px' }}>
          <label className="form-group">
            <span>RUC (13 dígitos numéricos) <strong style={{ color: '#ef4444' }}>*</strong></span>
            <input
              className={`input ${touched.ruc && errors.ruc ? 'is-invalid' : ''}`}
              placeholder="Ej: 1790012345001"
              maxLength={13}
              value={form.ruc}
              onChange={e => handleRucChange(e.target.value)}
              onBlur={() => handleBlur('ruc')}
            />
            {touched.ruc && errors.ruc && <span className="field-error">{errors.ruc}</span>}
          </label>

          <label className="form-group">
            <span>Razón social <strong style={{ color: '#ef4444' }}>*</strong></span>
            <input
              className={`input ${touched.name && errors.name ? 'is-invalid' : ''}`}
              placeholder="Ej: Cervecería Nacional S.A."
              value={form.name}
              onChange={e => handleNameChange(e.target.value)}
              onBlur={() => handleBlur('name')}
            />
            {touched.name && errors.name && <span className="field-error">{errors.name}</span>}
          </label>

          <label className="form-group">
            <span>Teléfono fijo / contacto</span>
            <input
              className={`input ${touched.contact && errors.contact ? 'is-invalid' : ''}`}
              placeholder="Ej: 022456789 (9-10 dígitos)"
              maxLength={10}
              value={form.contact}
              onChange={e => handlePhoneChange(e.target.value)}
              onBlur={() => handleBlur('contact')}
            />
            {touched.contact && errors.contact && <span className="field-error">{errors.contact}</span>}
          </label>

          <label className="form-group">
            <span>Celular <strong style={{ color: '#ef4444' }}>*</strong></span>
            <input
              className={`input ${touched.mobile && errors.mobile ? 'is-invalid' : ''}`}
              placeholder="Ej: 0991234567 (10 dígitos)"
              maxLength={10}
              value={form.mobile}
              onChange={e => handleMobileChange(e.target.value)}
              onBlur={() => handleBlur('mobile')}
            />
            {touched.mobile && errors.mobile && <span className="field-error">{errors.mobile}</span>}
          </label>

          <label className="form-group">
            <span>Correo electrónico <strong style={{ color: '#ef4444' }}>*</strong></span>
            <input
              className={`input ${touched.email && errors.email ? 'is-invalid' : ''}`}
              type="email"
              placeholder="ejemplo@proveedor.com"
              value={form.email}
              onChange={e => handleEmailChange(e.target.value)}
              onBlur={() => handleBlur('email')}
            />
            {touched.email && errors.email && <span className="field-error">{errors.email}</span>}
          </label>

          <label className="form-group">
            <span>Ciudad</span>
            <select
              className="select"
              value={form.cityId}
              onChange={e => setForm(prev => ({ ...prev, cityId: e.target.value }))}
            >
              {cities.map(c => (
                <option key={c.id} value={c.id}>
                  {c.nombre} ({c.provincia})
                </option>
              ))}
              {!cities.length && <option value="UIO">Quito (Pichincha)</option>}
            </select>
          </label>

          <label className="form-group" style={{ gridColumn: 'span 2' }}>
            <span>Dirección (Debe incluir "Av") <strong style={{ color: '#ef4444' }}>*</strong></span>
            <input
              className={`input ${touched.address && errors.address ? 'is-invalid' : ''}`}
              placeholder="Ej: Av. Galo Plaza Lasso N45-12 y Los Pinos"
              value={form.address}
              onChange={e => handleAddressChange(e.target.value)}
              onBlur={() => handleBlur('address')}
            />
            {touched.address && errors.address && <span className="field-error">{errors.address}</span>}
          </label>
        </div>

        <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button type="button" className="btn btn-primary" onClick={save}>
            <Save size={16} /> Guardar proveedor
          </button>
        </div>

        {notice && (
          <p
            className="form-notice"
            role="status"
            style={{
              color: noticeType === 'error' ? '#ef4444' : undefined,
              borderColor: noticeType === 'error' ? '#fca5a5' : undefined,
              background: noticeType === 'error' ? '#fef2f2' : undefined,
              marginTop: '14px',
            }}
          >
            {notice}
          </p>
        )}
      </section>

      <section className="card">
        <div className="section-heading">
          <div>
            <h2>Directorio de proveedores</h2>
            <p>{visibleSuppliers.length} registros</p>
          </div>
          <input
            className="input table-search"
            aria-label="Buscar proveedores"
            placeholder="Buscar por ID, RUC o razón social"
            value={search}
            onChange={event => setSearch(event.target.value)}
          />
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>RUC</th>
                <th>Razón social</th>
                <th>Teléfono</th>
                <th>Celular</th>
                <th>Correo</th>
                <th>Ciudad</th>
                <th>Dirección</th>
                <th style={{ width: '48px', textAlign: 'center' }}>Acción</th>
              </tr>
            </thead>
            <tbody>
              {visibleSuppliers.map(supplier => (
                <tr key={supplier.id}>
                  <td><code style={{ fontWeight: 600 }}>{supplier.id}</code></td>
                  <td>{supplier.ruc}</td>
                  <td>{supplier.name}</td>
                  <td>{supplier.contact || '—'}</td>
                  <td>{supplier.mobile || '—'}</td>
                  <td>{supplier.email || '—'}</td>
                  <td>{supplier.city || '—'}</td>
                  <td>{supplier.address || '—'}</td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      type="button"
                      className="btn btn-outline"
                      title="Eliminar registro"
                      style={{ padding: '4px 8px', color: '#ef4444', borderColor: '#fca5a5' }}
                      onClick={() => deleteSupplier(supplier.id)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
              {!visibleSuppliers.length && (
                <tr>
                  <td colSpan={9} className="empty-state">
                    No hay proveedores registrados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};


export const HR = () => {
  const { state, updateState } = useGlobalStore();
  const [employeeForm, setEmployeeForm] = useState<Partial<Employee>>({ status: 'ACTIVE', salary: 0, familyDependents: 0 });
  const [employeeId, setEmployeeId] = useState(state.employees.find(employee => employee.status === 'ACTIVE')?.id ?? '');
  const [bonus, setBonus] = useState(0);
  const [deductions, setDeductions] = useState(0);
  const [employeeNotice, setEmployeeNotice] = useState('');
  const [payrollNotice, setPayrollNotice] = useState('');

  const loadHR = async () => {
    try {
      const [remoteEmployees, remotePayrolls] = await Promise.all([
        hrApi.listEmployees().catch(() => null),
        hrApi.listPayrolls().catch(() => null),
      ]);
      if (remoteEmployees !== null || remotePayrolls !== null) {
        updateState(draft => {
          if (Array.isArray(remoteEmployees)) {
            draft.employees = remoteEmployees;
            if (!employeeId && remoteEmployees[0]) setEmployeeId(remoteEmployees[0].id);
          }
          if (Array.isArray(remotePayrolls)) draft.payrolls = remotePayrolls;
          return draft;
        });
      }
    } catch {
      // Conserva estado local
    }
  };

  useEffect(() => {
    void loadHR();
  }, []);

  const saveEmployee = () => {
    if (!employeeForm.name?.trim() || !employeeForm.ci?.trim() || !employeeForm.department?.trim() || !employeeForm.role?.trim()) return setEmployeeNotice('Completa identificación, nombre, departamento y cargo.');
    const employee: Employee = { id: `EMP-${Date.now()}`, ci: employeeForm.ci.trim(), name: employeeForm.name.trim(), department: employeeForm.department.trim(), role: employeeForm.role.trim(), salary: Number(employeeForm.salary || 0), status: employeeForm.status ?? 'ACTIVE', familyDependents: Number(employeeForm.familyDependents ?? 0) };
    updateState(draft => { draft.employees.push(employee); return draft; });
    setEmployeeId(employee.id);
    setEmployeeForm({ status: 'ACTIVE', salary: 0, familyDependents: 0 });
    setEmployeeNotice('Empleado agregado al registro.');
  };

  const createPayroll = async () => {
    const employee = state.employees.find(candidate => candidate.id === employeeId && candidate.status === 'ACTIVE');
    if (!employee) return setPayrollNotice('Selecciona un empleado activo.');
    const now = new Date();
    const startDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
    const endDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-28`;

    try {
      const res = await hrApi.createPayroll({
        descripcion: `Rol de pago ${employee.name}`,
        fechaInicio: startDate,
        fechaFin: endDate,
        idEmpleado: employee.id,
        sueldoBase: employee.salary,
        bonificaciones: bonus,
        descuentos: deductions,
      });
      setPayrollNotice(`Rol de pago ${res.id} registrado en MariaDB como ABI.`);
      void loadHR();
    } catch {
      const periodKey = now.toISOString().slice(0, 7);
      const payrollId = `NOM-${periodKey}-${employee.id}`;
      const payable = employee.salary + bonus - deductions;
      updateState(draft => {
        draft.payrolls.push({ id: payrollId, date: now.toISOString(), employeeId: employee.id, baseSalary: employee.salary, bonus, deductions, amount: payable, status: 'PEN' });
        return draft;
      });
      setPayrollNotice('Rol de pago creado localmente.');
    }
    setBonus(0);
    setDeductions(0);
  };

  const approvePayroll = async (payrollId: string) => {
    try {
      await hrApi.approvePayroll(payrollId);
      setPayrollNotice(`Rol de pago ${payrollId} aprobado en MariaDB.`);
      void loadHR();
    } catch {
      updateState(draft => {
        const payroll = draft.payrolls.find(p => p.id === payrollId);
        if (payroll) payroll.status = 'APR';
        return draft;
      });
      setPayrollNotice('Rol de pago aprobado localmente.');
    }
  };

  const activeEmployees = state.employees.filter(employee => employee.status === 'ACTIVE');
  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">EQUIPO Y COMPENSACIÓN · MARIADB</span><h1>Talento humano</h1><p>Personal, cargos y roles de pago sincronizados.</p></div></div>
      <section className="card"><h2 className="section-title">Registrar empleado</h2>
        <div className="grid-4">
          <label className="form-group">Cédula<input className="input" value={employeeForm.ci ?? ''} onChange={event => setEmployeeForm({ ...employeeForm, ci: event.target.value })} /></label>
          <label className="form-group">Nombre completo<input className="input" value={employeeForm.name ?? ''} onChange={event => setEmployeeForm({ ...employeeForm, name: event.target.value })} /></label>
          <label className="form-group">Departamento<input className="input" value={employeeForm.department ?? ''} onChange={event => setEmployeeForm({ ...employeeForm, department: event.target.value })} /></label>
          <label className="form-group">Cargo<input className="input" value={employeeForm.role ?? ''} onChange={event => setEmployeeForm({ ...employeeForm, role: event.target.value })} /></label>
          <label className="form-group">Sueldo base<input className="input" type="number" min="0" step="0.01" value={employeeForm.salary ?? 0} onChange={event => setEmployeeForm({ ...employeeForm, salary: Number(event.target.value) })} /></label>
          <label className="form-group">Cargas familiares<input className="input" type="number" min="0" step="1" value={employeeForm.familyDependents ?? 0} onChange={event => setEmployeeForm({ ...employeeForm, familyDependents: Number(event.target.value) })} /></label>
          <div className="form-action"><button type="button" className="btn btn-primary" onClick={saveEmployee}><Plus size={16} /> Guardar empleado</button></div>
        </div>
        {employeeNotice && <p className="form-notice" role="status">{employeeNotice}</p>}
      </section>
      <section className="card"><div className="section-heading"><div><h2>Preparar rol de pago</h2><p>Periodo actual · cálculo de ingresos y retenciones.</p></div></div>
        <div className="grid-4">
          <label className="form-group">Empleado<select className="select" value={employeeId} onChange={event => setEmployeeId(event.target.value)}>{activeEmployees.map(employee => <option key={employee.id} value={employee.id}>{employee.name} · {employee.department}</option>)}</select></label>
          <label className="form-group">Bonificaciones<input className="input" type="number" min="0" step="0.01" value={bonus} onChange={event => setBonus(Number(event.target.value))} /></label>
          <label className="form-group">Descuentos<input className="input" type="number" min="0" step="0.01" value={deductions} onChange={event => setDeductions(Number(event.target.value))} /></label>
          <div className="form-action"><button type="button" className="btn btn-secondary" onClick={createPayroll}>Generar rol pendiente</button></div>
        </div>
        {payrollNotice && <p className="form-notice" role="status">{payrollNotice}</p>}
      </section>
      <section className="card"><h2 className="section-title">Empleados</h2><div className="table-scroll"><table><thead><tr><th>Identificación</th><th>Empleado</th><th>Departamento</th><th>Cargo</th><th>Sueldo base</th><th>Cargas</th><th>Estado</th></tr></thead><tbody>
        {state.employees.map(employee => <tr key={employee.id}><td>{employee.ci}</td><td>{employee.name}</td><td>{employee.department}</td><td>{employee.role}</td><td>{money(employee.salary)}</td><td>{employee.familyDependents}</td><td>{employee.status}</td></tr>)}
      </tbody></table></div></section>
      <section className="card"><h2 className="section-title">Roles de pago</h2><div className="table-scroll"><table><thead><tr><th>Periodo</th><th>Empleado</th><th>Base</th><th>Bonos</th><th>Descuentos</th><th>Neto</th><th>Estado</th><th>Acción</th></tr></thead><tbody>
        {state.payrolls.map(payroll => <tr key={payroll.id}><td>{payroll.date.slice(0, 7)}</td><td>{state.employees.find(employee => employee.id === payroll.employeeId)?.name ?? payroll.employeeId}</td><td>{money(payroll.baseSalary)}</td><td>{money(payroll.bonus)}</td><td>{money(payroll.deductions)}</td><td>{money(payroll.amount)}</td><td><span className={`badge badge-${payroll.status}`}>{payroll.status}</span></td><td>{(payroll.status === 'PEN' || payroll.status === 'ABI') && <button type="button" className="btn btn-outline" onClick={() => approvePayroll(payroll.id)}>Aprobar</button>}</td></tr>)}
        {!state.payrolls.length && <tr><td colSpan={8} className="empty-state">Todavía no hay roles de pago.</td></tr>}
      </tbody></table></div></section>
    </div>
  );
};
