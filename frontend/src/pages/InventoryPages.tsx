import { useEffect, useMemo, useState } from 'react';
import { Check, Plus, Search, X } from 'lucide-react';
import { useGlobalStore } from '../context';
import { productApi, purchaseApi, warehouseApi, PurchaseCatalogs, PurchaseOrderRecord } from '../api';
import { Adjustment, Delivery, Product, Reception } from '../types';

const money = (value: number) => `$${value.toFixed(2)}`;

export const Catalog = () => {
  const { state, updateState } = useGlobalStore();
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [notice, setNotice] = useState('');
  const [form, setForm] = useState<Partial<Product>>({
    status: 'ACTIVE', category: 'Vino tinto', ml: 750, abv: 0, cost: 0, price: 0, stock: 0,
    minStock: 0, buyUnit: 'Caja', sellUnit: 'Botella', purchaseFactor: 1,
  });

  const loadProducts = async () => {
    try {
      const remoteProducts = await productApi.listProducts();
      if (Array.isArray(remoteProducts)) {
        updateState(draft => {
          draft.products = remoteProducts;
          return draft;
        });
      }
    } catch {
      // Conserva catálogo local
    }
  };

  useEffect(() => {
    void loadProducts();
  }, []);

  const products = useMemo(() => state.products.filter(product => `${product.name} ${product.sku} ${product.barcode} ${product.brand} ${product.category}`.toLowerCase().includes(search.toLowerCase())), [state.products, search]);

  const saveProduct = async () => {
    if (!form.name?.trim() || !form.sku?.trim()) return setNotice('Completa al menos el nombre y el código.');
    const cost = Number(form.cost || 0);
    const price = Number(form.price || 0);
    if (price <= 0) return setNotice('El precio de venta debe ser mayor a 0.');

    try {
      const res = await productApi.createProduct({
        nombre: form.name.trim(),
        costoCompra: cost,
        precioVenta: price,
        stockInicial: Number(form.stock || 0),
      });
      setNotice(`Producto ${res.id} registrado en MariaDB.`);
      void loadProducts();
    } catch (err) {
      const product: Product = {
        id: `PROD-${Date.now()}`, name: form.name.trim(), sku: form.sku.trim(), barcode: form.barcode?.trim() ?? '',
        brand: form.brand?.trim() || 'General', category: form.category?.trim() || 'Licores', ml: Number(form.ml || 750), abv: Number(form.abv || 0),
        cost, price, stock: Number(form.stock || 0), minStock: Number(form.minStock || 0),
        buyUnit: form.buyUnit?.trim() || 'Caja', sellUnit: form.sellUnit?.trim() || 'Botella',
        purchaseFactor: Number(form.purchaseFactor || 1), shelf: form.shelf?.trim() ?? '', status: form.status ?? 'ACTIVE',
      };
      updateState(draft => {
        draft.products.push(product);
        return draft;
      });
      setNotice('Producto registrado localmente.');
    }

    setForm({ status: 'ACTIVE', category: 'Vino tinto', ml: 750, abv: 0, cost: 0, price: 0, stock: 0, minStock: 0, buyUnit: 'Caja', sellUnit: 'Botella', purchaseFactor: 1 });
    setShowForm(false);
  };

  const toggleStatus = (productId: string) => {
    updateState(draft => {
      const product = draft.products.find(candidate => candidate.id === productId);
      if (product) product.status = product.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
      return draft;
    });
  };

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">BODEGA · CATÁLOGO · MARIADB</span><h1>Inventario de licores</h1><p>Presentaciones, costos, unidades de compra y existencias en MariaDB.</p></div><button type="button" className="btn btn-primary" onClick={() => setShowForm(value => !value)}><Plus size={16} /> Nuevo producto</button></div>
      {showForm && <section className="card"><h2 className="section-title">Ficha de producto</h2><div className="grid-4">
        <label className="form-group">SKU / Código<input className="input" value={form.sku ?? ''} onChange={event => setForm({ ...form, sku: event.target.value })} /></label>
        <label className="form-group">Nombre<input className="input" value={form.name ?? ''} onChange={event => setForm({ ...form, name: event.target.value })} /></label>
        <label className="form-group">Marca<input className="input" value={form.brand ?? ''} onChange={event => setForm({ ...form, brand: event.target.value })} /></label>
        <label className="form-group">Categoría<input className="input" value={form.category ?? ''} onChange={event => setForm({ ...form, category: event.target.value })} /></label>
        <label className="form-group">Código de barras<input className="input" value={form.barcode ?? ''} onChange={event => setForm({ ...form, barcode: event.target.value })} /></label>
        <label className="form-group">Presentación (ml)<input className="input" type="number" min="0" value={form.ml ?? 0} onChange={event => setForm({ ...form, ml: Number(event.target.value) })} /></label>
        <label className="form-group">Alcohol (% ABV)<input className="input" type="number" min="0" max="100" step="0.1" value={form.abv ?? 0} onChange={event => setForm({ ...form, abv: Number(event.target.value) })} /></label>
        <label className="form-group">Costo unitario<input className="input" type="number" min="0" step="0.01" value={form.cost ?? 0} onChange={event => setForm({ ...form, cost: Number(event.target.value) })} /></label>
        <label className="form-group">Precio de venta<input className="input" type="number" min="0" step="0.01" value={form.price ?? 0} onChange={event => setForm({ ...form, price: Number(event.target.value) })} /></label>
        <label className="form-group">Stock inicial<input className="input" type="number" min="0" value={form.stock ?? 0} onChange={event => setForm({ ...form, stock: Number(event.target.value) })} /></label>
        <label className="form-group">Stock mínimo<input className="input" type="number" min="0" value={form.minStock ?? 0} onChange={event => setForm({ ...form, minStock: Number(event.target.value) })} /></label>
        <label className="form-group">Unidad de compra<input className="input" value={form.buyUnit ?? ''} onChange={event => setForm({ ...form, buyUnit: event.target.value })} /></label>
        <label className="form-group">Unidad de venta<input className="input" value={form.sellUnit ?? ''} onChange={event => setForm({ ...form, sellUnit: event.target.value })} /></label>
        <label className="form-group">Unidades por compra<input className="input" type="number" min="1" value={form.purchaseFactor ?? 1} onChange={event => setForm({ ...form, purchaseFactor: Number(event.target.value) })} /></label>
        <label className="form-group">Percha<input className="input" value={form.shelf ?? ''} onChange={event => setForm({ ...form, shelf: event.target.value })} /></label>
        <div className="form-action"><button className="btn btn-primary" type="button" onClick={saveProduct}><Check size={16} /> Guardar producto</button></div>
      </div>{notice && <p className="form-notice" role="status">{notice}</p>}</section>}
      {!showForm && notice && <p className="form-notice" role="status">{notice}</p>}
      <section className="card"><div className="section-heading"><div><h2>Catálogo</h2><p>{products.length} referencias</p></div><div className="search-control table-search"><Search size={16} /><input aria-label="Buscar productos" placeholder="Nombre, marca, SKU o código" value={search} onChange={event => setSearch(event.target.value)} /></div></div>
        <div className="table-scroll"><table><thead><tr><th>SKU / producto</th><th>Categoría</th><th>Presentación</th><th>ABV</th><th>Compra → venta</th><th>Percha</th><th>Costo</th><th>Precio</th><th>Stock</th><th>Estado</th><th>Acción</th></tr></thead><tbody>
          {products.map(product => <tr key={product.id}><td><strong>{product.sku}</strong><br />{product.name}<small className="table-subtext">{product.brand} · {product.barcode || 'Sin código'}</small></td><td>{product.category}</td><td>{product.ml} ml</td><td>{product.abv}%</td><td>{product.buyUnit} (×{product.purchaseFactor}) → {product.sellUnit}</td><td>{product.shelf || '—'}</td><td>{money(product.cost)}</td><td>{money(product.price)}</td><td><span className={product.stock <= product.minStock ? 'stock-low' : ''}>{product.stock} / min. {product.minStock}</span></td><td><span className={`badge badge-${product.status === 'ACTIVE' ? 'active' : 'inactive'}`}>{product.status === 'ACTIVE' ? 'Activo' : 'Inactivo'}</span></td><td><button type="button" className="btn btn-outline" onClick={() => toggleStatus(product.id)}>{product.status === 'ACTIVE' ? 'Dar de baja' : 'Reactivar'}</button></td></tr>)}
          {!products.length && <tr><td className="empty-state" colSpan={11}>No hay productos que coincidan.</td></tr>}
        </tbody></table></div>
      </section>
    </div>
  );
};

export const PurchaseOrders = () => {
  const { state } = useGlobalStore();
  const [catalogs, setCatalogs] = useState<PurchaseCatalogs | null>(null);
  const [orders, setOrders] = useState<PurchaseOrderRecord[]>([]);
  const [supplierId, setSupplierId] = useState('');
  const [items, setItems] = useState<Array<{ productId: string; qty: number; cost: number }>>([]);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadData = async (showLoading = true): Promise<boolean> => {
    if (showLoading) setLoading(true);
    try {
      const [loadedCatalogs, loadedOrders] = await Promise.all([
        purchaseApi.getCatalogs(),
        purchaseApi.listOrders(),
      ]);
      setCatalogs(loadedCatalogs);
      setOrders(loadedOrders);
      setSupplierId(current => current || loadedCatalogs.proveedores.find(supplier => supplier.estado === 'ACT')?.id || '');
      setItems(current => current.length ? current : [{
        productId: loadedCatalogs.productos.find(product => product.estado === 'ACT')?.id ?? '',
        qty: 1,
        cost: Number(loadedCatalogs.productos.find(product => product.estado === 'ACT')?.costo ?? 0),
      }]);
      setNotice('');
      return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'No se pudieron cargar los datos de compras.');
      return false;
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const updateItem = (index: number, field: 'productId' | 'qty' | 'cost', value: string | number) => setItems(previous => previous.map((item, itemIndex) => {
    if (itemIndex !== index) return item;
    if (field === 'productId') {
      const product = catalogs?.productos.find(candidate => candidate.id === value);
      return { ...item, productId: String(value), cost: Number(product?.costo ?? 0) };
    }
    return { ...item, [field]: Number(value) };
  }));

  const createOrder = async () => {
    if (!supplierId || !items.length || items.some(item => !item.productId || !Number.isInteger(item.qty) || item.qty < 1 || item.cost < 0 || !Number.isFinite(item.qty + item.cost))) return setNotice('Selecciona proveedor y productos con cantidades enteras y costos válidos.');
    if (new Set(items.map(item => item.productId)).size !== items.length) return setNotice('Cada producto debe aparecer una sola vez en la orden.');
    setSaving(true);
    try {
      const result = await purchaseApi.createOrder({
        idProveedor: supplierId,
        fechaEntrega: null,
        tasaIVA: state.settings.taxRate,
        items: items.map(item => ({ idProducto: item.productId, cantidad: item.qty, costoUnitario: item.cost })),
      });
      const refreshed = await loadData(false);
      setItems([{
        productId: catalogs?.productos.find(product => product.estado === 'ACT')?.id ?? '',
        qty: 1,
        cost: Number(catalogs?.productos.find(product => product.estado === 'ACT')?.costo ?? 0),
      }]);
      if (refreshed) setNotice(`Orden ${result.id} creada en MariaDB como ABI.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'No se pudo crear la orden.');
    } finally {
      setSaving(false);
    }
  };

  const changeStatus = async (orderId: string, status: 'APR' | 'ANU') => {
    setSaving(true);
    try {
      if (status === 'APR') await purchaseApi.approveOrder(orderId);
      else await purchaseApi.annulOrder(orderId);
      const refreshed = await loadData(false);
      if (refreshed) setNotice(status === 'APR' ? `Orden ${orderId} aprobada en MariaDB.` : `Orden ${orderId} anulada en MariaDB.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'No se pudo actualizar el estado de la orden.');
    } finally {
      setSaving(false);
    }
  };

  const activeSuppliers = catalogs?.proveedores.filter(supplier => supplier.estado === 'ACT') ?? [];
  const activeProducts = catalogs?.productos.filter(product => product.estado === 'ACT') ?? [];
  const formSubtotal = items.reduce((sum, item) => sum + item.qty * item.cost, 0);
  const formTax = Math.round(formSubtotal * state.settings.taxRate) / 100;

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">ABASTECIMIENTO · MARIADB</span><h1>Órdenes de compra</h1><p>Las órdenes se consultan y registran mediante la API en MariaDB.</p></div></div>
      {loading && <p className="helper-text" role="status">Conectando con la API y cargando compras...</p>}
      <section className="card"><h2 className="section-title">Nueva orden</h2>
        <div className="grid-3"><label className="form-group">Proveedor<select className="select" value={supplierId} onChange={event => setSupplierId(event.target.value)} disabled={loading || saving}><option value="">Seleccionar proveedor</option>{activeSuppliers.map(supplier => <option key={supplier.id} value={supplier.id}>{supplier.nombre}</option>)}</select></label>
          {items.map((item, index) => <div className="purchase-line" key={index}>
            <label className="form-group">Producto<select className="select" value={item.productId} onChange={event => updateItem(index, 'productId', event.target.value)} disabled={loading || saving}><option value="">Seleccionar producto</option>{activeProducts.map(product => <option key={product.id} value={product.id}>{product.nombre}</option>)}</select></label>
            <label className="form-group">Cantidad<input className="input" type="number" min="1" step="1" value={item.qty} onChange={event => updateItem(index, 'qty', event.target.value)} disabled={saving} /></label>
            <label className="form-group">Costo unitario<input className="input" type="number" min="0" step="0.01" value={item.cost} onChange={event => updateItem(index, 'cost', event.target.value)} disabled={saving} /></label>
            {items.length > 1 && <button type="button" className="icon-button" aria-label="Quitar producto de la orden" disabled={saving} onClick={() => setItems(previous => previous.filter((_, itemIndex) => itemIndex !== index))}><X size={16} /></button>}
          </div>)}
        </div>
        <div className="form-actions"><button type="button" className="btn btn-outline" disabled={loading || saving || !activeProducts.length} onClick={() => {
          const product = activeProducts.find(candidate => !items.some(item => item.productId === candidate.id)) ?? activeProducts[0];
          setItems(previous => [...previous, { productId: product?.id ?? '', qty: 1, cost: Number(product?.costo ?? 0) }]);
        }}><Plus size={15} /> Añadir producto</button><button type="button" className="btn btn-primary" disabled={loading || saving || !activeSuppliers.length || !activeProducts.length} onClick={createOrder}>{saving ? 'Guardando...' : `Crear orden ABI · ${money(formSubtotal + formTax)}`}</button></div>
        {catalogs && (!activeSuppliers.length || !activeProducts.length) && <p className="helper-text">La base de datos debe tener proveedores y productos con estado ACT para crear órdenes.</p>}
        {notice && <p className="form-notice" role="status">{notice}</p>}
      </section>
      <section className="card"><h2 className="section-title">Historial de órdenes en MariaDB</h2><div className="table-scroll"><table><thead><tr><th>Orden</th><th>Fecha</th><th>Proveedor</th><th>Productos</th><th>Subtotal</th><th>IVA</th><th>Total</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
        {orders.map(order => <tr key={order.id}><td>{order.id}</td><td>{new Date(order.fecha).toLocaleDateString('es-EC')}</td><td>{order.proveedor}</td><td>{order.items.map(item => `${item.producto} × ${item.cantidad}`).join(', ')}</td><td>{money(Number(order.subtotal))}</td><td>{money(Number(order.iva))}</td><td>{money(Number(order.total))}</td><td><span className={`badge badge-${order.estado}`}>{order.estado}</span></td><td>{order.estado === 'ABI' && <div className="inline-actions"><button type="button" className="btn btn-secondary" disabled={saving} onClick={() => void changeStatus(order.id, 'APR')}>Aprobar</button><button type="button" className="btn btn-outline" disabled={saving} onClick={() => void changeStatus(order.id, 'ANU')}>Anular</button></div>}</td></tr>)}
        {!loading && !orders.length && <tr><td colSpan={9} className="empty-state">No hay órdenes registradas en MariaDB.</td></tr>}
      </tbody></table></div>
      </section>
    </div>
  );
};

export const Receptions = () => {
  const { state, updateState } = useGlobalStore();
  const [quantities, setQuantities] = useState<Record<string, Record<string, string>>>({});
  const [reasons, setReasons] = useState<Record<string, Record<string, string>>>({});
  const [notice, setNotice] = useState('');

  const loadReceptions = async () => {
    try {
      const remoteReceptions = await warehouseApi.listReceptions();
      if (remoteReceptions && remoteReceptions.length) {
        updateState(draft => {
          draft.receptions = remoteReceptions;
          return draft;
        });
      }
    } catch {
      // Conserva estado local
    }
  };

  useEffect(() => {
    void loadReceptions();
  }, []);

  const completeReception = async (reception: Reception) => {
    const rows = reception.items.map(item => {
      const raw = quantities[reception.id]?.[item.productId] ?? String(item.expectedQty);
      const receivedQty = Number(raw);
      return { ...item, receivedQty, diff: receivedQty - item.expectedQty, reason: reasons[reception.id]?.[item.productId]?.trim() ?? '' };
    });
    if (rows.some(item => !Number.isInteger(item.receivedQty) || item.receivedQty < 0)) return setNotice('La cantidad recibida debe ser un entero no negativo.');

    try {
      await warehouseApi.confirmReception(reception.id, rows);
      setNotice(`Recepción ${reception.id} confirmada e ingresada en MariaDB.`);
      void loadReceptions();
    } catch (err) {
      updateState(draft => {
        const draftReception = draft.receptions.find(r => r.id === reception.id);
        if (draftReception) {
          draftReception.status = 'COMPLETED';
          draftReception.items = rows;
        }
        return draft;
      });
      setNotice('Recepción actualizada localmente.');
    }
  };

  const pending = state.receptions.filter(reception => reception.status === 'PEN' || reception.status === 'PENDING');
  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">BODEGA · RECEPCIÓN · MARIADB</span><h1>Recepciones</h1><p>Verifica cantidades físicas de compras recibidas.</p></div></div>
      {notice && <p className="form-notice" role="status">{notice}</p>}
      {pending.map(reception => <section className="card" key={reception.id}>
        <div className="section-heading"><div><h2>{reception.id} <span className="badge badge-PENDING">Pendiente</span></h2><p>Orden de compra {reception.poId} · {new Date(reception.date).toLocaleDateString('es-EC')}</p></div></div>
        <div className="table-scroll"><table><thead><tr><th>Producto</th><th>Solicitado</th><th>Recibido</th><th>Diferencia</th><th>Motivo de diferencia</th></tr></thead><tbody>
          {reception.items.map(item => <tr key={item.productId}><td>{state.products.find(product => product.id === item.productId)?.name ?? item.productId}</td><td>{item.expectedQty}</td>
            <td><input className="input compact-input" type="number" min="0" value={quantities[reception.id]?.[item.productId] ?? item.expectedQty} onChange={event => setQuantities(previous => ({ ...previous, [reception.id]: { ...previous[reception.id], [item.productId]: event.target.value } }))} /></td>
            <td>{Number(quantities[reception.id]?.[item.productId] ?? item.expectedQty) - item.expectedQty}</td>
            <td><input className="input" aria-label={`Motivo de diferencia para ${item.productId}`} value={reasons[reception.id]?.[item.productId] ?? ''} onChange={event => setReasons(previous => ({ ...previous, [reception.id]: { ...previous[reception.id], [item.productId]: event.target.value } }))} placeholder="Obligatorio si hay diferencia" /></td>
          </tr>)}
        </tbody></table></div>
        <button type="button" className="btn btn-primary" onClick={() => completeReception(reception)}>Registrar cantidades recibidas</button>
      </section>)}
      <section className="card"><div className="section-heading"><div><h2>Historial de recepciones</h2><p>Recepciones procesadas y pendientes.</p></div></div><div className="table-scroll"><table><thead><tr><th>Recepción</th><th>Orden</th><th>Fecha</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>
        {state.receptions.map(reception => <tr key={reception.id}><td>{reception.id}</td><td>{reception.poId}</td><td>{new Date(reception.date).toLocaleDateString('es-EC')}</td><td><span className={`badge badge-${reception.status}`}>{reception.status}</span></td><td>{reception.items.map(item => `${item.productId}: ${item.receivedQty}/${item.expectedQty}`).join(' · ')}</td></tr>)}
        {!state.receptions.length && <tr><td colSpan={5} className="empty-state">Las órdenes aprobadas generarán recepciones aquí.</td></tr>}
      </tbody></table></div></section>
    </div>
  );
};

export const Deliveries = () => {
  const { state, updateState } = useGlobalStore();
  const [quantities, setQuantities] = useState<Record<string, Record<string, string>>>({});
  const [reasons, setReasons] = useState<Record<string, Record<string, string>>>({});
  const [notice, setNotice] = useState('');

  const loadDeliveries = async () => {
    try {
      const remoteDeliveries = await warehouseApi.listDeliveries();
      if (remoteDeliveries && remoteDeliveries.length) {
        updateState(draft => {
          draft.deliveries = remoteDeliveries;
          return draft;
        });
      }
    } catch {
      // Conserva estado local
    }
  };

  useEffect(() => {
    void loadDeliveries();
  }, []);

  const completeDelivery = async (delivery: Delivery) => {
    const rows = delivery.items.map(item => {
      const deliveredQty = Number(quantities[delivery.id]?.[item.productId] ?? item.expectedQty);
      return { ...item, deliveredQty, diff: deliveredQty - item.expectedQty, reason: reasons[delivery.id]?.[item.productId]?.trim() ?? '' };
    });
    if (rows.some(item => !Number.isInteger(item.deliveredQty) || item.deliveredQty < 0)) return setNotice('La cantidad entregada debe ser un entero no negativo.');

    try {
      await warehouseApi.confirmDelivery(delivery.id, rows);
      setNotice(`Entrega ${delivery.id} confirmada y despachada en MariaDB.`);
      void loadDeliveries();
    } catch (err) {
      updateState(draft => {
        const draftDelivery = draft.deliveries.find(d => d.id === delivery.id);
        if (draftDelivery) {
          draftDelivery.status = 'COMPLETED';
          draftDelivery.items = rows;
        }
        return draft;
      });
      setNotice('Entrega actualizada localmente.');
    }
  };

  const pendingDeliveries = state.deliveries.filter(delivery => delivery.status === 'PEN' || delivery.status === 'PENDING');
  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">BODEGA · DESPACHO · MARIADB</span><h1>Entregas de ventas</h1><p>Verifica cantidades y registra despachos de facturas.</p></div></div>
      {notice && <p className="form-notice" role="status">{notice}</p>}
      {pendingDeliveries.map(delivery => {
        const invoice = state.invoices.find(candidate => candidate.id === delivery.invoiceId);
        return <section className="card" key={delivery.id}>
          <div className="section-heading"><div><h2>{delivery.id} <span className="badge badge-PENDING">Pendiente</span></h2><p>Factura {delivery.invoiceId} · {state.customers.find(customer => customer.id === invoice?.customerId)?.name ?? 'Cliente'} · {new Date(delivery.date).toLocaleDateString('es-EC')}</p></div></div>
          <div className="table-scroll"><table><thead><tr><th>Producto</th><th>Solicitado</th><th>Entregado</th><th>Diferencia</th><th>Motivo</th></tr></thead><tbody>
            {delivery.items.map(item => <tr key={item.productId}><td>{state.products.find(product => product.id === item.productId)?.name ?? item.productId}</td><td>{item.expectedQty}</td>
              <td><input className="input compact-input" type="number" min="0" value={quantities[delivery.id]?.[item.productId] ?? item.expectedQty} onChange={event => setQuantities(previous => ({ ...previous, [delivery.id]: { ...previous[delivery.id], [item.productId]: event.target.value } }))} /></td>
              <td>{Number(quantities[delivery.id]?.[item.productId] ?? item.expectedQty) - item.expectedQty}</td>
              <td><input className="input" aria-label={`Motivo de diferencia para ${item.productId}`} placeholder="Obligatorio si hay diferencia" value={reasons[delivery.id]?.[item.productId] ?? ''} onChange={event => setReasons(previous => ({ ...previous, [delivery.id]: { ...previous[delivery.id], [item.productId]: event.target.value } }))} /></td>
            </tr>)}
          </tbody></table></div>
          <button type="button" className="btn btn-primary" onClick={() => completeDelivery(delivery)}>Confirmar cantidades entregadas</button>
        </section>;
      })}
      <section className="card"><div className="section-heading"><div><h2>Historial de entregas</h2><p>Despachos registrados desde el punto de venta.</p></div></div><div className="table-scroll"><table><thead><tr><th>Entrega</th><th>Factura</th><th>Cliente</th><th>Fecha</th><th>Estado</th><th>Detalle</th></tr></thead><tbody>
        {state.deliveries.map(delivery => <tr key={delivery.id}><td>{delivery.id}</td><td>{delivery.invoiceId}</td><td>{delivery.invoiceId}</td><td>{new Date(delivery.date).toLocaleDateString('es-EC')}</td><td><span className={`badge badge-${delivery.status}`}>{delivery.status}</span></td><td>{delivery.items.map(item => `${item.productId}: ${item.deliveredQty}/${item.expectedQty}`).join(' · ')}</td></tr>)}
        {!state.deliveries.length && <tr><td colSpan={6} className="empty-state">Las facturas aprobadas en el POS generarán órdenes de entrega aquí.</td></tr>}
      </tbody></table></div></section>
    </div>
  );
};

export const Adjustments = () => {
  const { state, updateState } = useGlobalStore();
  const [form, setForm] = useState({ type: 'OUT' as Adjustment['type'], productId: '', qty: 1, reason: '', responsible: 'EMP-000001' });
  const [notice, setNotice] = useState('');

  const loadAdjustments = async () => {
    try {
      const remoteAdjustments = await warehouseApi.listAdjustments();
      if (remoteAdjustments && remoteAdjustments.length) {
        updateState(draft => {
          draft.adjustments = remoteAdjustments;
          return draft;
        });
      }
    } catch {
      // Conserva estado local
    }
  };

  useEffect(() => {
    void loadAdjustments();
  }, []);

  const saveManualAdjustment = async () => {
    if (!form.productId || !form.reason.trim()) return setNotice('Selecciona producto e ingresa motivo.');
    try {
      const res = await warehouseApi.createAdjustment({
        idProducto: form.productId,
        tipo: form.type,
        cantidad: form.qty,
        motivo: form.reason.trim(),
      });
      setNotice(`Ajuste ${res.id} registrado en MariaDB como ABI.`);
      void loadAdjustments();
    } catch {
      const adjustment: Adjustment = { id: `AJ-${Date.now()}`, date: new Date().toISOString(), type: form.type, productId: form.productId, qty: form.qty, reason: form.reason.trim(), responsible: form.responsible, status: 'ABI' };
      updateState(draft => { draft.adjustments.push(adjustment); return draft; });
      setNotice('Ajuste guardado localmente.');
    }
    setForm({ type: 'OUT', productId: '', qty: 1, reason: '', responsible: 'EMP-000001' });
  };

  const changeAdjustmentStatus = async (adjustmentId: string, status: 'APR' | 'ANU') => {
    try {
      if (status === 'APR') await warehouseApi.approveAdjustment(adjustmentId);
      else await warehouseApi.annulAdjustment(adjustmentId);
      setNotice(status === 'APR' ? `Ajuste ${adjustmentId} aprobado e impactado en MariaDB.` : `Ajuste ${adjustmentId} anulado en MariaDB.`);
      void loadAdjustments();
    } catch {
      updateState(draft => {
        const draftAdjustment = draft.adjustments.find(a => a.id === adjustmentId);
        if (draftAdjustment) draftAdjustment.status = status;
        return draft;
      });
      setNotice(`Ajuste ${status === 'APR' ? 'aprobado' : 'anulado'} localmente.`);
    }
  };

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">CONTROL DE BODEGA · MARIADB</span><h1>Ajustes físicos</h1><p>Registro de mermas y sobrantes con impacto en inventario.</p></div></div>
      <section className="card"><h2 className="section-title">Registrar ajuste</h2><div className="grid-4">
        <label className="form-group">Tipo<select className="select" value={form.type} onChange={event => setForm({ ...form, type: event.target.value as Adjustment['type'] })}><option value="OUT">Salida · merma / rotura</option><option value="IN">Entrada · sobrante</option></select></label>
        <label className="form-group">Producto<select className="select" value={form.productId} onChange={event => setForm({ ...form, productId: event.target.value })}><option value="">Seleccionar</option>{state.products.map(product => <option key={product.id} value={product.id}>{product.name} · stock {product.stock}</option>)}</select></label>
        <label className="form-group">Cantidad<input className="input" type="number" min="1" step="1" value={form.qty} onChange={event => setForm({ ...form, qty: Number(event.target.value) })} /></label>
        <label className="form-group">Motivo<input className="input" value={form.reason} onChange={event => setForm({ ...form, reason: event.target.value })} placeholder="Causa del ajuste" /></label>
        <div className="form-action"><button type="button" className="btn btn-primary" onClick={saveManualAdjustment}>Crear ajuste ABI</button></div>
      </div></section>
      {notice && <p className="form-notice" role="status">{notice}</p>}
      <section className="card"><h2 className="section-title">Historial de ajustes</h2><div className="table-scroll"><table><thead><tr><th>Fecha</th><th>Producto</th><th>Tipo</th><th>Cantidad</th><th>Responsable</th><th>Motivo</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
        {state.adjustments.map(adjustment => <tr key={adjustment.id}><td>{new Date(adjustment.date).toLocaleDateString('es-EC')}</td><td>{state.products.find(product => product.id === adjustment.productId)?.name ?? adjustment.productId}</td><td>{adjustment.type === 'IN' ? 'Ingreso' : 'Egreso'}</td><td>{adjustment.qty}</td><td>{adjustment.responsible}</td><td>{adjustment.reason}</td><td><span className={`badge badge-${adjustment.status}`}>{adjustment.status}</span></td><td>{adjustment.status === 'ABI' && <div className="inline-actions"><button className="btn btn-secondary" type="button" onClick={() => changeAdjustmentStatus(adjustment.id, 'APR')}>Aprobar</button><button className="btn btn-outline" type="button" onClick={() => changeAdjustmentStatus(adjustment.id, 'ANU')}>Anular</button></div>}</td></tr>)}
        {!state.adjustments.length && <tr><td colSpan={8} className="empty-state">No hay ajustes registrados.</td></tr>}
      </tbody></table></div></section>
    </div>
  );
};
