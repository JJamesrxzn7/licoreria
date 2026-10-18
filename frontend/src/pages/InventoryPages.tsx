import { useEffect, useMemo, useState } from 'react';
import { Calendar, Check, CheckCircle2, Edit3, Plus, Save, Scale, Search, Trash2, X } from 'lucide-react';
import { useGlobalStore } from '../context';
import { catalogApi, productApi, purchaseApi, warehouseApi, GeneralCatalogs, PurchaseCatalogs, PurchaseOrderRecord } from '../api';
import { Adjustment, Delivery, Product, Reception } from '../types';

const money = (value: number) => `$${value.toFixed(2)}`;

export const Catalog = () => {
  const { state, updateState } = useGlobalStore();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'ACTIVE' | 'INACTIVE'>('ALL');
  const [showForm, setShowForm] = useState(false);
  const [notice, setNotice] = useState('');
  const [catalogs, setCatalogs] = useState<GeneralCatalogs>({
    ciudades: [],
    unidadesMedida: [],
    categorias: [],
    marcas: [],
    perchas: [],
    bancos: [],
  });
  const [form, setForm] = useState<Partial<Product>>({
    status: 'ACTIVE', ml: 750, abv: 0, cost: 0, price: 0, stock: 0,
    minStock: 0, purchaseFactor: 1,
  });

  // Estado para Edición
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [editForm, setEditForm] = useState<Partial<Product>>({});
  const [editNotice, setEditNotice] = useState('');

  // Estado para confirmación de cambio de estado
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    product: Product | null;
    targetStatus: 'ACTIVE' | 'INACTIVE';
  }>({
    isOpen: false,
    product: null,
    targetStatus: 'INACTIVE',
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
    void catalogApi.getGenerales().then(data => {
      if (data) {
        setCatalogs(data);
        setForm(prev => ({
          ...prev,
          categoryId: prev.categoryId || data.categorias[0]?.id || 'CAT-000001',
          brandId: prev.brandId || data.marcas[0]?.id || 'MAR-000001',
          buyUnitId: prev.buyUnitId || data.unidadesMedida.find(u => u.id === 'CAJ')?.id || data.unidadesMedida[0]?.id || 'CAJ',
          sellUnitId: prev.sellUnitId || data.unidadesMedida.find(u => u.id === 'BOT')?.id || data.unidadesMedida[0]?.id || 'BOT',
          shelfId: prev.shelfId || data.perchas[0]?.id || 'PCH-000001',
        }));
      }
    }).catch(() => null);
  }, []);

  const activeCount = useMemo(() => state.products.filter(p => p.status === 'ACTIVE').length, [state.products]);
  const inactiveCount = useMemo(() => state.products.filter(p => p.status !== 'ACTIVE').length, [state.products]);

  const filteredProducts = useMemo(() => {
    return state.products
      .filter(product => {
        if (statusFilter === 'ACTIVE') return product.status === 'ACTIVE';
        if (statusFilter === 'INACTIVE') return product.status !== 'ACTIVE';
        return true;
      })
      .filter(product =>
        `${product.name} ${product.sku} ${product.barcode || ''} ${product.brand || ''} ${product.category || ''}`
          .toLowerCase()
          .includes(search.toLowerCase())
      );
  }, [state.products, search, statusFilter]);

  const nextProductId = useMemo(() => {
    let maxNum = 0;
    for (const p of state.products) {
      const code = p.sku || p.id;
      if (!code) continue;
      const m = code.match(/^PRD-(\d+)$/i);
      if (m) {
        const val = parseInt(m[1], 10);
        if (!isNaN(val) && val > maxNum) maxNum = val;
      }
    }
    return `PRD-${String(maxNum + 1).padStart(6, '0')}`;
  }, [state.products]);

  const saveProduct = async () => {
    if (!form.name?.trim()) return setNotice('La descripción del producto es obligatoria.');
    if (form.name.trim().length > 40) return setNotice('La descripción no puede exceder 40 caracteres (restricción de base de datos).');
    const cost = Number(form.cost || 0);
    const price = Number(form.price || 0);
    const initialStock = Number(form.stock || 0);
    if (price <= 0) return setNotice('El precio de venta debe ser mayor a 0.');
    if (price < cost) return setNotice('El precio de venta debe ser mayor o igual al costo de compra.');
    if (!Number.isInteger(initialStock) || initialStock < 0) return setNotice('El saldo inicial debe ser un número entero mayor o igual a 0.');

    const catId = form.categoryId || catalogs.categorias[0]?.id || 'CAT-000001';
    const brId = form.brandId || catalogs.marcas[0]?.id || 'MAR-000001';
    const buyUId = form.buyUnitId || catalogs.unidadesMedida[0]?.id || 'CAJ';
    const sellUId = form.sellUnitId || catalogs.unidadesMedida[0]?.id || 'BOT';
    const shId = form.shelfId || catalogs.perchas[0]?.id || 'PCH-000001';

    const selectedCategory = catalogs.categorias.find(c => c.id === catId);
    const selectedBrand = catalogs.marcas.find(m => m.id === brId);
    const selectedBuyUnit = catalogs.unidadesMedida.find(u => u.id === buyUId);
    const selectedSellUnit = catalogs.unidadesMedida.find(u => u.id === sellUId);
    const selectedShelf = catalogs.perchas.find(p => p.id === shId);

    const generatedId = nextProductId;

    try {
      const res = await productApi.createProduct({
        id: generatedId,
        nombre: form.name.trim(),
        idCategoria: catId,
        idMarca: brId,
        idPercha: shId,
        umCompra: buyUId,
        umVenta: sellUId,
        costoCompra: cost,
        precioVenta: price,
        stockInicial: initialStock,
      });
      setNotice(`Producto ${res.id} registrado exitosamente.`);
      void loadProducts();
    } catch {
      const buyFactor = Number(selectedBuyUnit?.factor) || 1;
      const sellFactor = Number(selectedSellUnit?.factor) || 1;
      const product: Product = {
        id: generatedId,
        name: form.name.trim(),
        sku: generatedId,
        barcode: '',
        brand: selectedBrand?.nombre || 'General',
        brandId: brId,
        category: selectedCategory?.nombre || 'Licores',
        categoryId: catId,
        ml: 750,
        abv: 0,
        cost,
        price,
        stock: initialStock,
        minStock: initialStock,
        buyUnit: selectedBuyUnit?.nombre || buyUId,
        buyUnitId: buyUId,
        sellUnit: selectedSellUnit?.nombre || sellUId,
        sellUnitId: sellUId,
        purchaseFactor: buyFactor,
        sellFactor: sellFactor,
        factorConversion: sellFactor > 0 ? Number((buyFactor / sellFactor).toFixed(2)) : 1,
        shelf: selectedShelf ? `Percha ${selectedShelf.letra}${selectedShelf.nivel}` : '—',
        shelfId: shId,
        status: 'ACTIVE',
      };
      updateState(draft => {
        draft.products.push(product);
        return draft;
      });
      setNotice(`Producto ${product.id} (${product.name}) registrado exitosamente.`);
    }

    setForm({
      name: '',
      cost: 0,
      price: 0,
      stock: 0,
      categoryId: catalogs.categorias[0]?.id || 'CAT-000001',
      brandId: catalogs.marcas[0]?.id || 'MAR-000001',
      buyUnitId: catalogs.unidadesMedida[0]?.id || 'CAJ',
      sellUnitId: catalogs.unidadesMedida[0]?.id || 'BOT',
      shelfId: catalogs.perchas[0]?.id || 'PCH-000001',
    });
    setShowForm(false);
  };

  const startEdit = (product: Product) => {
    setEditingProduct(product);
    setEditNotice('');
    setEditForm({
      ...product,
      categoryId: product.categoryId || catalogs.categorias.find(c => c.nombre === product.category)?.id || catalogs.categorias[0]?.id || 'CAT-000001',
      brandId: product.brandId || catalogs.marcas.find(m => m.nombre === product.brand)?.id || catalogs.marcas[0]?.id || 'MAR-000001',
      buyUnitId: product.buyUnitId || catalogs.unidadesMedida.find(u => u.nombre === product.buyUnit)?.id || 'CAJ',
      sellUnitId: product.sellUnitId || catalogs.unidadesMedida.find(u => u.nombre === product.sellUnit)?.id || 'BOT',
      shelfId: product.shelfId || catalogs.perchas.find(p => p.nombre === product.shelf)?.id || 'PCH-000001',
    });
  };

  const saveEdit = async () => {
    if (!editingProduct) return;
    if (!editForm.name?.trim()) return setEditNotice('La descripción del producto no puede estar vacía.');
    if (editForm.name.trim().length > 40) return setEditNotice('La descripción no puede exceder 40 caracteres.');
    const cost = Number(editForm.cost || 0);
    const price = Number(editForm.price || 0);
    if (price <= 0) return setEditNotice('El precio de venta debe ser mayor a 0.');
    if (price < cost) return setEditNotice('El precio de venta debe ser mayor o igual al costo de compra.');

    const catId = editForm.categoryId || catalogs.categorias[0]?.id || 'CAT-000001';
    const brId = editForm.brandId || catalogs.marcas[0]?.id || 'MAR-000001';
    const buyUId = editForm.buyUnitId || catalogs.unidadesMedida[0]?.id || 'CAJ';
    const sellUId = editForm.sellUnitId || catalogs.unidadesMedida[0]?.id || 'BOT';
    const shId = editForm.shelfId || catalogs.perchas[0]?.id || 'PCH-000001';

    const selectedCategory = catalogs.categorias.find(c => c.id === catId);
    const selectedBrand = catalogs.marcas.find(m => m.id === brId);
    const selectedBuyUnit = catalogs.unidadesMedida.find(u => u.id === buyUId);
    const selectedSellUnit = catalogs.unidadesMedida.find(u => u.id === sellUId);
    const selectedShelf = catalogs.perchas.find(p => p.id === shId);

    try {
      await productApi.updateProduct(editingProduct.id, {
        nombre: editForm.name.trim(),
        costoCompra: cost,
        precioVenta: price,
      });
    } catch {
      // Guardado en store
    }

    updateState(draft => {
      const p = draft.products.find(candidate => candidate.id === editingProduct.id);
      if (p) {
        const buyFactor = Number(selectedBuyUnit?.factor) || 1;
        const sellFactor = Number(selectedSellUnit?.factor) || 1;
        p.name = editForm.name!.trim();
        p.brand = selectedBrand?.nombre || p.brand;
        p.brandId = brId;
        p.category = selectedCategory?.nombre || p.category;
        p.categoryId = catId;
        p.cost = cost;
        p.price = price;
        p.buyUnit = selectedBuyUnit?.nombre || p.buyUnit;
        p.buyUnitId = buyUId;
        p.sellUnit = selectedSellUnit?.nombre || p.sellUnit;
        p.sellUnitId = sellUId;
        p.purchaseFactor = buyFactor;
        p.sellFactor = sellFactor;
        p.factorConversion = sellFactor > 0 ? Number((buyFactor / sellFactor).toFixed(2)) : 1;
        p.shelf = selectedShelf ? `Percha ${selectedShelf.letra}${selectedShelf.nivel}` : p.shelf;
        p.shelfId = shId;
      }
      return draft;
    });

    setNotice(`Producto ${editingProduct.sku || editingProduct.id} actualizado exitosamente.`);
    setEditingProduct(null);
  };

  const askToggleStatus = (product: Product, targetStatus: 'ACTIVE' | 'INACTIVE') => {
    setConfirmModal({
      isOpen: true,
      product,
      targetStatus,
    });
  };

  const executeToggleStatus = () => {
    const { product, targetStatus } = confirmModal;
    if (!product) return;

    updateState(draft => {
      const p = draft.products.find(candidate => candidate.id === product.id);
      if (p) p.status = targetStatus;
      return draft;
    });

    setNotice(
      targetStatus === 'ACTIVE'
        ? `Producto ${product.name} reactivado exitosamente.`
        : `Producto ${product.name} dado de baja (inactivo) exitosamente.`
    );
    setConfirmModal({ isOpen: false, product: null, targetStatus: 'INACTIVE' });
  };

  const currentBuyUnit = catalogs.unidadesMedida.find(u => u.id === (form.buyUnitId || 'CAJ'));
  const currentSellUnit = catalogs.unidadesMedida.find(u => u.id === (form.sellUnitId || 'BOT'));
  const currentBuyFactor = Number(currentBuyUnit?.factor) || 1;
  const currentSellFactor = Number(currentSellUnit?.factor) || 1;
  const currentRatio = currentSellFactor > 0 ? (currentBuyFactor / currentSellFactor) : 1;

  const editBuyUnit = catalogs.unidadesMedida.find(u => u.id === (editForm.buyUnitId || 'CAJ'));
  const editSellUnit = catalogs.unidadesMedida.find(u => u.id === (editForm.sellUnitId || 'BOT'));
  const editBuyFactor = Number(editBuyUnit?.factor) || 1;
  const editSellFactor = Number(editSellUnit?.factor) || 1;
  const editRatio = editSellFactor > 0 ? (editBuyFactor / editSellFactor) : 1;

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ABASTECIMIENTO · PRODUCTOS</span>
          <h1>Administración de productos</h1>
          <p>Control integral de catálogo según tabla PRODUCTOS, unidades de medida, costos, precios y saldos.</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setShowForm(value => !value)}>
          <Plus size={16} /> {showForm ? 'Cerrar formulario' : 'Nuevo producto'}
        </button>
      </div>

      {showForm && (
        <section className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 className="section-title" style={{ margin: 0 }}>Registrar nuevo producto</h2>
            <span style={{ fontSize: '13px', background: '#f8fafc', padding: '4px 10px', borderRadius: '6px', border: '1px solid #e2e8f0', color: '#475569' }}>
              Código generado: <strong style={{ color: 'var(--primary)', fontFamily: 'monospace' }}>{nextProductId}</strong>
            </span>
          </div>

          <div className="grid-3">
            <label className="form-group">
              <span>ID Producto (Generado automáticamente)</span>
              <input
                className="input"
                value={nextProductId}
                disabled
                readOnly
                style={{ background: '#f8fafc', cursor: 'not-allowed', fontWeight: 600, color: '#475569' }}
              />
            </label>

            <label className="form-group" style={{ gridColumn: 'span 2' }}>
              <span>Descripción del producto (pro_Descripcion) <strong style={{ color: '#ef4444' }}>*</strong></span>
              <input
                className="input"
                placeholder="Ej. Whisky Johnnie Walker Black Label 750ml"
                maxLength={40}
                value={form.name ?? ''}
                onChange={event => setForm({ ...form, name: event.target.value })}
              />
              <small style={{ fontSize: '11px', color: '#64748b' }}>Máximo 40 caracteres (CHAR(40))</small>
            </label>

            <label className="form-group">
              <span>Categoría (id_Categoria)</span>
              <select
                className="select"
                value={form.categoryId ?? ''}
                onChange={event => setForm({ ...form, categoryId: event.target.value })}
              >
                <option value="">-- Seleccione una categoría --</option>
                {catalogs.categorias.map(c => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                {!catalogs.categorias.length && <option value="CAT-000001">Cargando categorías...</option>}
              </select>
            </label>

            <label className="form-group">
              <span>Marca (id_Marca)</span>
              <select
                className="select"
                value={form.brandId ?? ''}
                onChange={event => setForm({ ...form, brandId: event.target.value })}
              >
                <option value="">-- Seleccione una marca --</option>
                {catalogs.marcas.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
                {!catalogs.marcas.length && <option value="MAR-000001">Cargando marcas...</option>}
              </select>
            </label>

            <label className="form-group">
              <span>Ubicación / Percha (Opcional)</span>
              <select
                className="select"
                value={form.shelfId ?? ''}
                onChange={event => setForm({ ...form, shelfId: event.target.value })}
              >
                <option value="">-- Seleccione una percha (Opcional) --</option>
                {catalogs.perchas.map(p => (
                  <option key={p.id} value={p.id}>
                    Percha {p.letra}{p.nivel} · {p.nombre}
                  </option>
                ))}
                {!catalogs.perchas.length && <option value="PCH-000001">A1 · Nivel 1</option>}
              </select>
            </label>

            <label className="form-group">
              <span>U.M. Compra (pro_UM_Compra)</span>
              <select
                className="select"
                value={form.buyUnitId ?? ''}
                onChange={event => setForm({ ...form, buyUnitId: event.target.value })}
              >
                <option value="">-- Seleccione unidad de compra --</option>
                {catalogs.unidadesMedida.map(u => <option key={u.id} value={u.id}>{u.id} · {u.nombre}</option>)}
                {!catalogs.unidadesMedida.length && <option value="CAJ">CAJ · Caja</option>}
              </select>
            </label>

            <label className="form-group">
              <span>U.M. Venta (pro_UM_Venta)</span>
              <select
                className="select"
                value={form.sellUnitId ?? ''}
                onChange={event => setForm({ ...form, sellUnitId: event.target.value })}
              >
                <option value="">-- Seleccione unidad de venta --</option>
                {catalogs.unidadesMedida.map(u => <option key={u.id} value={u.id}>{u.id} · {u.nombre}</option>)}
                {!catalogs.unidadesMedida.length && <option value="BOT">BOT · Botella</option>}
              </select>
            </label>

            <div style={{
              gridColumn: 'span 3',
              background: '#f0fdf4',
              border: '1px solid #bbf7d0',
              borderRadius: '8px',
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              color: '#166534',
              margin: '4px 0 8px'
            }}>
              <Scale size={22} style={{ flexShrink: 0, color: '#15803d' }} />
              <div style={{ fontSize: '13px', lineHeight: 1.4 }}>
                <strong>Factor de Conversión de Unidades (Bodegas & Compras ⇄ Ventas):</strong>
                <div style={{ marginTop: '2px', color: '#1e293b' }}>
                  Compra: <strong>{currentBuyUnit?.id || form.buyUnitId || 'CAJ'} ({currentBuyUnit?.nombre || 'Caja'})</strong> [factor {currentBuyFactor}] &nbsp;·&nbsp;
                  Venta: <strong>{currentSellUnit?.id || form.sellUnitId || 'BOT'} ({currentSellUnit?.nombre || 'Botella'})</strong> [factor {currentSellFactor}]
                </div>
                <div style={{ marginTop: '4px', fontWeight: 600 }}>
                  Factor calculado: <span style={{ fontSize: '15px', color: '#15803d', fontWeight: 700 }}>{currentRatio.toFixed(2)}x</span>
                  &nbsp;➜ <em>1 {currentBuyUnit?.nombre || form.buyUnitId || 'Caja'} equivale a {currentRatio % 1 === 0 ? currentRatio.toFixed(0) : currentRatio.toFixed(2)} {currentSellUnit?.nombre || form.sellUnitId || 'Botellas'}</em>
                </div>
              </div>
            </div>

            <label className="form-group">
              <span>Saldo Inicial (pro_Saldo_Inicial) <strong style={{ color: '#ef4444' }}>*</strong></span>
              <input
                className="input"
                type="number"
                min="0"
                step="1"
                value={form.stock ?? 0}
                onChange={event => setForm({ ...form, stock: Number(event.target.value) })}
              />
            </label>

            <label className="form-group">
              <span>Costo de compra ($) (pro_Valor_Compra) <strong style={{ color: '#ef4444' }}>*</strong></span>
              <input
                className="input"
                type="number"
                min="0"
                step="0.01"
                value={form.cost ?? 0}
                onChange={event => setForm({ ...form, cost: Number(event.target.value) })}
              />
            </label>

            <label className="form-group">
              <span>Precio de venta ($) (pro_Precio_Venta) <strong style={{ color: '#ef4444' }}>*</strong></span>
              <input
                className="input"
                type="number"
                min="0"
                step="0.01"
                value={form.price ?? 0}
                onChange={event => setForm({ ...form, price: Number(event.target.value) })}
              />
            </label>
          </div>

          <div className="form-action" style={{ marginTop: '20px' }}>
            <button className="btn btn-primary" type="button" onClick={saveProduct}>
              <Check size={16} /> Guardar producto
            </button>
          </div>
          {notice && <p className="form-notice" role="status">{notice}</p>}
        </section>
      )}

      {!showForm && notice && <p className="form-notice" role="status">{notice}</p>}

      <section className="card">
        <div className="section-heading">
          <div>
            <h2>Directorio de productos</h2>
            <p>{filteredProducts.length} referencias registradas</p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                type="button"
                className={`filter-badge-btn ${statusFilter === 'ALL' ? 'active' : ''}`}
                onClick={() => setStatusFilter('ALL')}
              >
                Todos ({state.products.length})
              </button>
              <button
                type="button"
                className={`filter-badge-btn ${statusFilter === 'ACTIVE' ? 'active' : ''}`}
                onClick={() => setStatusFilter('ACTIVE')}
              >
                Activos ({activeCount})
              </button>
              <button
                type="button"
                className={`filter-badge-btn ${statusFilter === 'INACTIVE' ? 'active' : ''}`}
                onClick={() => setStatusFilter('INACTIVE')}
              >
                Inactivos ({inactiveCount})
              </button>
            </div>

            <div className="search-control table-search">
              <Search size={16} />
              <input
                aria-label="Buscar productos"
                placeholder="Descripción, ID, marca o categoría"
                value={search}
                onChange={event => setSearch(event.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>ID Producto</th>
                <th>Descripción</th>
                <th>Categoría / Marca</th>
                <th>U.M. Compra</th>
                <th>U.M. Venta</th>
                <th>Factor Conv.</th>
                <th>Percha</th>
                <th>Valor Compra</th>
                <th>Precio Venta</th>
                <th>Saldo Inicial</th>
                <th>Saldo Final</th>
                <th>Estado</th>
                <th style={{ minWidth: '150px', textAlign: 'center' }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {filteredProducts.map(product => {
                const isLow = product.stock <= (product.minStock || 0) && product.stock > 0;
                const isZero = product.stock === 0;
                return (
                  <tr key={product.id}>
                    <td>
                      <code style={{ fontWeight: 600, color: 'var(--primary)' }}>{product.sku || product.id}</code>
                    </td>
                    <td>
                      <strong>{product.name}</strong>
                    </td>
                    <td>
                      <span>{product.category || '—'}</span>
                      <small className="table-subtext">{product.brand || '—'}</small>
                    </td>
                    <td>{product.buyUnit || 'CAJ'}</td>
                    <td>{product.sellUnit || 'BOT'}</td>
                    <td>
                      <span style={{
                        display: 'inline-block',
                        background: '#f0fdf4',
                        color: '#166534',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontWeight: 600,
                        fontSize: '12px',
                        border: '1px solid #bbf7d0'
                      }}>
                        {product.factorConversion ? `${Number(product.factorConversion).toFixed(2)}x` : '1.00x'}
                      </span>
                      <small className="table-subtext" style={{ fontSize: '11px', display: 'block' }}>
                        1 {product.buyUnit || 'CAJ'} = {product.factorConversion ? (Number(product.factorConversion) % 1 === 0 ? Number(product.factorConversion).toFixed(0) : Number(product.factorConversion).toFixed(2)) : 1} {product.sellUnit || 'BOT'}
                      </small>
                    </td>
                    <td>{product.shelf || '—'}</td>
                    <td>{money(product.cost)}</td>
                    <td style={{ fontWeight: 600, color: 'var(--primary)' }}>{money(product.price)}</td>
                    <td>{product.minStock ?? product.stock}</td>
                    <td>
                      <span className={isZero ? 'stock-low' : isLow ? 'stock-warning' : 'stock-ok'}>
                        {product.stock}
                      </span>
                    </td>
                    <td>
                      <span className={`badge badge-${product.status === 'ACTIVE' ? 'active' : 'inactive'}`}>
                        {product.status === 'ACTIVE' ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
                    <td>
                      <div className="inline-actions" style={{ justifyContent: 'center' }}>
                        <button
                          type="button"
                          className="btn btn-outline"
                          title="Editar producto"
                          style={{ padding: '6px 10px', fontSize: '12px' }}
                          onClick={() => startEdit(product)}
                        >
                          <Edit3 size={14} /> Editar
                        </button>
                        {product.status === 'ACTIVE' ? (
                          <button
                            type="button"
                            className="btn btn-outline"
                            title="Dar de baja producto"
                            style={{ padding: '6px 10px', fontSize: '12px', color: '#b42318' }}
                            onClick={() => askToggleStatus(product, 'INACTIVE')}
                          >
                            <Trash2 size={14} /> Dar de baja
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn btn-outline"
                            title="Reactivar producto"
                            style={{ padding: '6px 10px', fontSize: '12px', color: '#027a48' }}
                            onClick={() => askToggleStatus(product, 'ACTIVE')}
                          >
                            <CheckCircle2 size={14} /> Reactivar
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!filteredProducts.length && (
                <tr>
                  <td className="empty-state" colSpan={13}>
                    No hay productos que coincidan con el filtro.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Modal de Edición de Producto */}
      {editingProduct && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: '640px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Edit3 size={18} color="var(--primary)" />
                <h2 style={{ margin: 0, fontSize: '18px' }}>
                  Editar producto ({editingProduct.sku || editingProduct.id})
                </h2>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setEditingProduct(null)}
                aria-label="Cerrar modal"
              >
                <X size={18} />
              </button>
            </div>

            <div className="grid-2">
              <label className="form-group" style={{ gridColumn: 'span 2' }}>
                <span>ID Producto (No editable)</span>
                <input
                  className="input"
                  value={editingProduct.sku || editingProduct.id}
                  disabled
                  readOnly
                  style={{ background: '#f8fafc', cursor: 'not-allowed', fontWeight: 600 }}
                />
              </label>

              <label className="form-group" style={{ gridColumn: 'span 2' }}>
                <span>Descripción del producto (pro_Descripcion) <strong style={{ color: '#ef4444' }}>*</strong></span>
                <input
                  className="input"
                  maxLength={40}
                  value={editForm.name ?? ''}
                  onChange={e => setEditForm({ ...editForm, name: e.target.value })}
                />
                <small style={{ fontSize: '11px', color: '#64748b' }}>Máximo 40 caracteres (CHAR(40))</small>
              </label>

              <label className="form-group">
                <span>Categoría</span>
                <select
                  className="select"
                  value={editForm.categoryId ?? ''}
                  onChange={e => setEditForm({ ...editForm, categoryId: e.target.value })}
                >
                  <option value="">-- Seleccione una categoría --</option>
                  {catalogs.categorias.map(c => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                </select>
              </label>

              <label className="form-group">
                <span>Marca</span>
                <select
                  className="select"
                  value={editForm.brandId ?? ''}
                  onChange={e => setEditForm({ ...editForm, brandId: e.target.value })}
                >
                  <option value="">-- Seleccione una marca --</option>
                  {catalogs.marcas.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
                </select>
              </label>

              <label className="form-group">
                <span>U.M. Compra (pro_UM_Compra)</span>
                <select
                  className="select"
                  value={editForm.buyUnitId ?? ''}
                  onChange={e => setEditForm({ ...editForm, buyUnitId: e.target.value })}
                >
                  <option value="">-- Seleccione unidad de compra --</option>
                  {catalogs.unidadesMedida.map(u => <option key={u.id} value={u.id}>{u.id} · {u.nombre}</option>)}
                </select>
              </label>

              <label className="form-group">
                <span>U.M. Venta (pro_UM_Venta)</span>
                <select
                  className="select"
                  value={editForm.sellUnitId ?? ''}
                  onChange={e => setEditForm({ ...editForm, sellUnitId: e.target.value })}
                >
                  <option value="">-- Seleccione unidad de venta --</option>
                  {catalogs.unidadesMedida.map(u => <option key={u.id} value={u.id}>{u.id} · {u.nombre}</option>)}
                </select>
              </label>

              <div style={{
                gridColumn: 'span 2',
                background: '#f0fdf4',
                border: '1px solid #bbf7d0',
                borderRadius: '8px',
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                color: '#166534',
                fontSize: '12px'
              }}>
                <Scale size={18} style={{ flexShrink: 0, color: '#15803d' }} />
                <div>
                  <strong>Factor de Conversión:</strong> 1 {editBuyUnit?.nombre || editForm.buyUnitId || 'Caja'} = <strong>{editRatio % 1 === 0 ? editRatio.toFixed(0) : editRatio.toFixed(2)} {editSellUnit?.nombre || editForm.sellUnitId || 'Botellas'}</strong> (Ratio: {editRatio.toFixed(2)}x)
                </div>
              </div>

              <label className="form-group">
                <span>Valor / Costo compra ($) (pro_Valor_Compra)</span>
                <input
                  className="input"
                  type="number"
                  min="0"
                  step="0.01"
                  value={editForm.cost ?? 0}
                  onChange={e => setEditForm({ ...editForm, cost: Number(e.target.value) })}
                />
              </label>

              <label className="form-group">
                <span>Precio de venta ($) (pro_Precio_Venta) <strong style={{ color: '#ef4444' }}>*</strong></span>
                <input
                  className="input"
                  type="number"
                  min="0"
                  step="0.01"
                  value={editForm.price ?? 0}
                  onChange={e => setEditForm({ ...editForm, price: Number(e.target.value) })}
                />
              </label>

              <label className="form-group">
                <span>Ubicación / Percha</span>
                <select
                  className="select"
                  value={editForm.shelfId ?? ''}
                  onChange={e => setEditForm({ ...editForm, shelfId: e.target.value })}
                >
                  <option value="">-- Seleccione una percha (Opcional) --</option>
                  {catalogs.perchas.map(p => (
                    <option key={p.id} value={p.id}>
                      Percha {p.letra}{p.nivel} · {p.nombre}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {editNotice && (
              <p className="form-notice" role="status" style={{ color: '#ef4444', borderColor: '#fca5a5', background: '#fef2f2', marginTop: '12px' }}>
                {editNotice}
              </p>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => setEditingProduct(null)}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={saveEdit}
              >
                <Save size={15} /> Actualizar producto
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de Confirmación para Dar de baja / Reactivar */}
      {confirmModal.isOpen && confirmModal.product && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: '480px' }}>
            <h2 style={{ margin: '0 0 10px', fontSize: '18px' }}>
              {confirmModal.targetStatus === 'INACTIVE' ? '¿Dar de baja producto?' : '¿Reactivar producto?'}
            </h2>
            <p style={{ margin: '0 0 16px', fontSize: '13px', color: '#475569', lineHeight: 1.5 }}>
              {confirmModal.targetStatus === 'INACTIVE' ? (
                <>
                  ¿Estás seguro de que deseas dar de baja el producto <strong>{confirmModal.product.name}</strong> ({confirmModal.product.sku})?
                  <br />
                  <span style={{ display: 'block', marginTop: '8px', color: '#b42318', fontSize: '12px' }}>
                    ⚠️ El producto quedará en estado inactivo y no estará disponible para nuevas ventas en POS ni órdenes de compra.
                  </span>
                </>
              ) : (
                <>
                  ¿Deseas volver a habilitar el producto <strong>{confirmModal.product.name}</strong> ({confirmModal.product.sku}) para que vuelva a estar disponible en el punto de venta y compras?
                </>
              )}
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => setConfirmModal({ isOpen: false, product: null, targetStatus: 'INACTIVE' })}
              >
                Cancelar
              </button>
              <button
                type="button"
                className={confirmModal.targetStatus === 'INACTIVE' ? 'btn btn-danger' : 'btn btn-secondary'}
                onClick={executeToggleStatus}
              >
                {confirmModal.targetStatus === 'INACTIVE' ? (
                  <>
                    <Trash2 size={14} /> Sí, dar de baja
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={14} /> Sí, reactivar
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export const Products = Catalog;

export const PurchaseOrders = () => {
  const { state } = useGlobalStore();
  const [catalogs, setCatalogs] = useState<PurchaseCatalogs | null>(null);
  const [orders, setOrders] = useState<PurchaseOrderRecord[]>([]);
  const [supplierId, setSupplierId] = useState('');
  const [deliveryDate, setDeliveryDate] = useState<string>(() => {
    const d = new Date();
    d.setDate(d.getDate() + 3);
    return d.toISOString().split('T')[0];
  });
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
    if (!supplierId) return setNotice('Selecciona un proveedor para continuar.');
    if (!deliveryDate) return setNotice('Por favor selecciona la fecha estimada de entrega (oc_FechaEntrega).');
    const selectedSupplier = catalogs?.proveedores.find(s => s.id === supplierId);
    if (selectedSupplier && selectedSupplier.estado !== 'ACT') {
      return setNotice('No se puede realizar una compra a un proveedor inactivo. Debes activarlo primero en el directorio de proveedores.');
    }
    if (!items.length || items.some(item => !item.productId || !Number.isInteger(item.qty) || item.qty < 1 || item.cost < 0 || !Number.isFinite(item.qty + item.cost))) return setNotice('Selecciona proveedor y productos con cantidades enteras y costos válidos.');
    if (new Set(items.map(item => item.productId)).size !== items.length) return setNotice('Cada producto debe aparecer una sola vez en la orden.');
    setSaving(true);
    try {
      const result = await purchaseApi.createOrder({
        idProveedor: supplierId,
        fechaEntrega: deliveryDate,
        tasaIVA: state.settings.taxRate,
        items: items.map(item => ({ idProducto: item.productId, cantidad: item.qty, costoUnitario: item.cost })),
      });
      const refreshed = await loadData(false);
      setItems([{
        productId: catalogs?.productos.find(product => product.estado === 'ACT')?.id ?? '',
        qty: 1,
        cost: Number(catalogs?.productos.find(product => product.estado === 'ACT')?.costo ?? 0),
      }]);
      if (refreshed) setNotice(`Orden ${result.id} creada exitosamente como ABI.`);
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
      if (refreshed) setNotice(status === 'APR' ? `Orden ${orderId} aprobada exitosamente.` : `Orden ${orderId} anulada exitosamente.`);
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
      <div className="page-heading"><div><span className="eyebrow">ABASTECIMIENTO</span><h1>Órdenes de compra</h1><p>Registro y seguimiento de órdenes de aprovisionamiento.</p></div></div>
      {loading && <p className="helper-text" role="status">Cargando órdenes de compra...</p>}
      <section className="card">
        <h2 className="section-title">Nueva orden de compra</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '20px' }}>
          <label className="form-group">
            <span>Proveedor <strong style={{ color: '#ef4444' }}>*</strong></span>
            <select className="select" value={supplierId} onChange={event => setSupplierId(event.target.value)} disabled={loading || saving}>
              <option value="">-- Seleccione un proveedor --</option>
              {activeSuppliers.map(supplier => <option key={supplier.id} value={supplier.id}>{supplier.nombre}</option>)}
            </select>
          </label>
          <label className="form-group">
            <span>Fecha estimada de entrega (oc_FechaEntrega) <strong style={{ color: '#ef4444' }}>*</strong></span>
            <input
              type="date"
              className="input"
              value={deliveryDate}
              min={new Date().toISOString().split('T')[0]}
              onChange={event => setDeliveryDate(event.target.value)}
              disabled={loading || saving}
              required
            />
            <small style={{ fontSize: '11px', color: '#64748b' }}>Requerido para planificar la recepción en bodega</small>
          </label>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#334155', marginBottom: '10px' }}>Productos a incluir en la orden:</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {items.map((item, index) => (
              <div className="purchase-line" key={index} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: '12px', alignItems: 'end' }}>
                <label className="form-group" style={{ margin: 0 }}>
                  <span>Producto</span>
                  <select className="select" value={item.productId} onChange={event => updateItem(index, 'productId', event.target.value)} disabled={loading || saving}>
                    <option value="">-- Seleccione un producto --</option>
                    {activeProducts.map(product => <option key={product.id} value={product.id}>{product.nombre}</option>)}
                  </select>
                </label>
                <label className="form-group" style={{ margin: 0 }}>
                  <span>Cantidad</span>
                  <input className="input" type="number" min="1" step="1" value={item.qty} onChange={event => updateItem(index, 'qty', event.target.value)} disabled={saving} />
                </label>
                <label className="form-group" style={{ margin: 0 }}>
                  <span>Costo unitario ($)</span>
                  <input className="input" type="number" min="0" step="0.01" value={item.cost} onChange={event => updateItem(index, 'cost', event.target.value)} disabled={saving} />
                </label>
                {items.length > 1 && (
                  <button type="button" className="icon-button" style={{ marginBottom: '4px' }} aria-label="Quitar producto de la orden" disabled={saving} onClick={() => setItems(previous => previous.filter((_, itemIndex) => itemIndex !== index))}>
                    <X size={16} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="form-actions">
          <button type="button" className="btn btn-outline" disabled={loading || saving || !activeProducts.length} onClick={() => {
            const product = activeProducts.find(candidate => !items.some(item => item.productId === candidate.id)) ?? activeProducts[0];
            setItems(previous => [...previous, { productId: product?.id ?? '', qty: 1, cost: Number(product?.costo ?? 0) }]);
          }}><Plus size={15} /> Añadir producto</button>
          <button type="button" className="btn btn-primary" disabled={loading || saving || !activeSuppliers.length || !activeProducts.length} onClick={createOrder}>
            {saving ? 'Guardando...' : `Crear orden ABI · ${money(formSubtotal + formTax)}`}
          </button>
        </div>
        {catalogs && (!activeSuppliers.length || !activeProducts.length) && <p className="helper-text">Deben existir proveedores y productos activos para crear órdenes.</p>}
        {notice && <p className="form-notice" role="status">{notice}</p>}
      </section>

      <section className="card">
        <h2 className="section-title">Historial de órdenes de compra</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Orden</th>
                <th>Fecha Emisión</th>
                <th>Fecha Entrega</th>
                <th>Proveedor</th>
                <th>Productos</th>
                <th>Subtotal</th>
                <th>IVA</th>
                <th>Total</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {orders.map(order => (
                <tr key={order.id}>
                  <td><code style={{ fontWeight: 600, color: 'var(--primary)' }}>{order.id}</code></td>
                  <td>{new Date(order.fecha).toLocaleDateString('es-EC')}</td>
                  <td>
                    {order.fechaEntrega ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#1e40af', fontWeight: 500 }}>
                        <Calendar size={13} />
                        {new Date(order.fechaEntrega).toLocaleDateString('es-EC')}
                      </span>
                    ) : (
                      <span style={{ color: '#94a3b8' }}>—</span>
                    )}
                  </td>
                  <td><strong>{order.proveedor}</strong></td>
                  <td>{order.items.map(item => `${item.producto} × ${item.cantidad}`).join(', ')}</td>
                  <td>{money(Number(order.subtotal))}</td>
                  <td>{money(Number(order.iva))}</td>
                  <td style={{ fontWeight: 600, color: 'var(--primary)' }}>{money(Number(order.total))}</td>
                  <td><span className={`badge badge-${order.estado}`}>{order.estado}</span></td>
                  <td>
                    {order.estado === 'ABI' && (
                      <div className="inline-actions">
                        <button type="button" className="btn btn-secondary" disabled={saving} onClick={() => void changeStatus(order.id, 'APR')}>Aprobar</button>
                        <button type="button" className="btn btn-outline" disabled={saving} onClick={() => void changeStatus(order.id, 'ANU')}>Anular</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && !orders.length && (
                <tr><td colSpan={10} className="empty-state">No hay órdenes registradas.</td></tr>
              )}
            </tbody>
          </table>
        </div>
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
      setNotice(`Recepción ${reception.id} confirmada e ingresada exitosamente.`);
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
      setNotice('Recepción actualizada exitosamente.');
    }
  };

  const pending = state.receptions.filter(reception => reception.status === 'PEN' || reception.status === 'PENDING');
  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">BODEGA · RECEPCIÓN</span><h1>Recepciones</h1><p>Verifica cantidades físicas de compras recibidas.</p></div></div>
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
      setNotice(`Entrega ${delivery.id} confirmada y despachada exitosamente.`);
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
      setNotice('Entrega actualizada exitosamente.');
    }
  };

  const pendingDeliveries = state.deliveries.filter(delivery => delivery.status === 'PEN' || delivery.status === 'PENDING');
  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">BODEGA · DESPACHO</span><h1>Entregas de ventas</h1><p>Verifica cantidades y registra despachos de facturas.</p></div></div>
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
      setNotice(`Ajuste ${res.id} registrado exitosamente como ABI.`);
      void loadAdjustments();
    } catch {
      const adjustment: Adjustment = { id: `AJ-${Date.now()}`, date: new Date().toISOString(), type: form.type, productId: form.productId, qty: form.qty, reason: form.reason.trim(), responsible: form.responsible, status: 'ABI' };
      updateState(draft => { draft.adjustments.push(adjustment); return draft; });
      setNotice('Ajuste guardado exitosamente.');
    }
    setForm({ type: 'OUT', productId: '', qty: 1, reason: '', responsible: 'EMP-000001' });
  };

  const changeAdjustmentStatus = async (adjustmentId: string, status: 'APR' | 'ANU') => {
    try {
      if (status === 'APR') await warehouseApi.approveAdjustment(adjustmentId);
      else await warehouseApi.annulAdjustment(adjustmentId);
      setNotice(status === 'APR' ? `Ajuste ${adjustmentId} aprobado exitosamente.` : `Ajuste ${adjustmentId} anulado exitosamente.`);
      void loadAdjustments();
    } catch {
      updateState(draft => {
        const draftAdjustment = draft.adjustments.find(a => a.id === adjustmentId);
        if (draftAdjustment) draftAdjustment.status = status;
        return draft;
      });
      setNotice(`Ajuste ${status === 'APR' ? 'aprobado' : 'anulado'} exitosamente.`);
    }
  };

  return (
    <div>
      <div className="page-heading"><div><span className="eyebrow">CONTROL DE BODEGA</span><h1>Ajustes físicos</h1><p>Registro de mermas y sobrantes con impacto en inventario.</p></div></div>
      <section className="card"><h2 className="section-title">Registrar ajuste</h2><div className="grid-4">
        <label className="form-group">
          Tipo
          <select className="select" value={form.type} onChange={event => setForm({ ...form, type: event.target.value as Adjustment['type'] })}>
            <option value="">-- Seleccione tipo de ajuste --</option>
            <option value="OUT">Salida · merma / rotura</option>
            <option value="IN">Entrada · sobrante</option>
          </select>
        </label>
        <label className="form-group">
          Producto
          <select className="select" value={form.productId} onChange={event => setForm({ ...form, productId: event.target.value })}>
            <option value="">-- Seleccione un producto --</option>
            {state.products.map(product => <option key={product.id} value={product.id}>{product.name} · stock {product.stock}</option>)}
          </select>
        </label>
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
