import { useEffect, useMemo, useState } from 'react';
import { Search, ShoppingCart, Trash2, ShieldAlert } from 'lucide-react';
import { useGlobalStore } from '../context';
import { CartItem, Product } from '../types';
import { customerApi, productApi, salesApi } from '../api';

const accountForMethod: Record<'CASH' | 'CARD' | 'TRANSFER' | 'CREDIT', string> = {
  CASH: 'a1',
  CARD: 'a2',
  TRANSFER: 'a2',
  CREDIT: 'a3',
};

export const POS = () => {
  const { state, updateState } = useGlobalStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [cart, setCart] = useState<CartItem[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<'CASH' | 'CARD' | 'TRANSFER' | 'CREDIT'>('CASH');
  const [customerId, setCustomerId] = useState(state.customers[0]?.id || '');
  const [discountRate, setDiscountRate] = useState(0);
  const [installments, setInstallments] = useState(1);
  const [ageVerified, setAgeVerified] = useState(false);
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  // Sincronizar catálogo y clientes desde MariaDB
  const syncFromApi = async () => {
    try {
      const [remoteProducts, remoteCustomers] = await Promise.all([
        productApi.listProducts().catch(() => null),
        customerApi.listCustomers().catch(() => null),
      ]);
      if (remoteProducts !== null || remoteCustomers !== null) {
        updateState(draft => {
          if (Array.isArray(remoteProducts)) draft.products = remoteProducts;
          if (Array.isArray(remoteCustomers)) {
            draft.customers = remoteCustomers;
            if (!customerId && remoteCustomers[0]) setCustomerId(remoteCustomers[0].id);
          }
          return draft;
        });
      }
    } catch {
      // Si la API no está iniciada, mantiene el estado local
    }
  };

  useEffect(() => {
    void syncFromApi();
  }, []);

  const categories = useMemo(() => Array.from(new Set(state.products.map(product => product.category))), [state.products]);
  const reservedByProduct = useMemo(() => state.deliveries
    .filter(delivery => delivery.status === 'PENDING')
    .flatMap(delivery => delivery.items)
    .reduce<Record<string, number>>((reserved, item) => {
      reserved[item.productId] = (reserved[item.productId] ?? 0) + item.expectedQty;
      return reserved;
    }, {}), [state.deliveries]);

  const filteredProducts = useMemo(() => {
    const search = searchTerm.trim().toLocaleLowerCase();
    return state.products.filter(product => product.status === 'ACTIVE'
      && product.stock - (reservedByProduct[product.id] ?? 0) > 0
      && (!categoryFilter || product.category === categoryFilter)
      && (!search || [product.name, product.sku, product.barcode, product.brand]
        .some(value => value.toLocaleLowerCase().includes(search))));
  }, [state.products, searchTerm, categoryFilter, reservedByProduct]);

  const addToCart = (product: Product) => {
    const available = product.stock - (reservedByProduct[product.id] ?? 0);
    const existing = cart.find(item => item.product.id === product.id);
    if (available <= 0 || (existing && existing.qty >= available)) return setNotice('No hay más unidades disponibles para agregar.');
    setAgeVerified(false);
    setNotice('');
    setCart(previous => {
      if (existing) {
        return previous.map(item => item.product.id === product.id
          ? { ...item, qty: item.qty + 1, subtotal: (item.qty + 1) * product.price }
          : item);
      }
      return [...previous, { product, qty: 1, discount: 0, subtotal: product.price }];
    });
  };

  const removeFromCart = (productId: string) => {
    setAgeVerified(false);
    setCart(previous => previous.filter(item => item.product.id !== productId));
  };
  const updateCartQty = (productId: string, qty: number) => {
    const product = state.products.find(item => item.id === productId);
    if (!product) return;
    if (qty <= 0) return removeFromCart(productId);
    if (!Number.isInteger(qty)) return setNotice('La cantidad vendida debe ser un número entero.');
    if (qty > product.stock - (reservedByProduct[product.id] ?? 0)) return setNotice('La cantidad supera las existencias disponibles.');
    setAgeVerified(false);
    setNotice('');
    setCart(previous => previous.map(item => item.product.id === productId
      ? { ...item, qty, subtotal: qty * item.product.price }
      : item));
  };

  const subtotal = cart.reduce((sum, item) => sum + item.subtotal, 0);
  const safeDiscountRate = Number.isFinite(discountRate) ? Math.min(100, Math.max(0, discountRate)) : 0;
  const discount = subtotal * safeDiscountRate / 100;
  const taxableSubtotal = subtotal - discount;
  const taxRate = state.settings.taxRate || 15;
  const tax = taxableSubtotal * taxRate / 100;
  const total = taxableSubtotal + tax;
  const selectedCustomer = state.customers.find(customer => customer.id === customerId);
  const creditAvailable = selectedCustomer ? selectedCustomer.creditLimit - selectedCustomer.creditUsed : 0;

  const handleCheckout = async () => {
    if (!cart.length) return setNotice('Agrega al menos un producto al carrito.');
    if (total <= 0) return setNotice('El total de la factura debe ser mayor que cero.');
    if (!selectedCustomer || selectedCustomer.status !== 'ACTIVE') return setNotice('Selecciona un cliente activo.');
    if (!ageVerified) return setNotice('Confirma que verificaste que el cliente es mayor de edad antes de continuar.');
    if (cart.some(item => {
      const current = state.products.find(product => product.id === item.product.id);
      return !Number.isInteger(item.qty) || !current || current.status !== 'ACTIVE' || current.stock - (reservedByProduct[current.id] ?? 0) < item.qty;
    })) return setNotice('El inventario cambió o no alcanza para completar la venta. Actualiza el carrito.');
    if (paymentMethod === 'CREDIT' && total > creditAvailable) {
      return setNotice(`El crédito disponible es $${Math.max(creditAvailable, 0).toFixed(2)}; ajusta la venta o elige otra forma de pago.`);
    }
    if (paymentMethod === 'CREDIT' && (!Number.isInteger(installments) || installments < 1 || installments > 12)) {
      return setNotice('El crédito permite de 1 a 12 cuotas.');
    }

    setSaving(true);
    let invoiceId = `FAC-${Date.now()}`;
    let deliveryId = `EGR-${Date.now()}`;

    // Intentar registrar en MariaDB mediante la API
    try {
      const apiResponse = await salesApi.createInvoice({
        idCliente: customerId,
        descripcion: `Venta POS ${paymentMethod}`,
        tasaIVA: taxRate,
        metodoPago: paymentMethod,
        cuotas: paymentMethod === 'CREDIT' ? installments : 1,
        items: cart.map(item => ({
          idProducto: item.product.id,
          cantidad: item.qty,
          precioUnitario: item.product.price,
        })),
      });
      invoiceId = apiResponse.id;
      deliveryId = apiResponse.deliveryId || deliveryId;
      setNotice(`Venta ${invoiceId} registrada en MariaDB.`);
    } catch (apiError) {
      const msg = apiError instanceof Error ? apiError.message : String(apiError);
      setNotice(`Venta guardada localmente (${msg}).`);
    } finally {
      setSaving(false);
    }

    const lines = [
      { accountId: accountForMethod[paymentMethod], debit: total, credit: 0 },
      { accountId: 'a8', debit: 0, credit: taxableSubtotal },
      ...(tax > 0 ? [{ accountId: 'a6', debit: 0, credit: tax }] : []),
    ];

    updateState(draft => {
      draft.invoices.push({
        id: invoiceId,
        date: new Date().toISOString(),
        customerId,
        items: cart.map(item => ({ ...item, product: { ...item.product } })),
        subtotal,
        discount,
        taxRate,
        tax,
        total,
        paymentMethod,
        installments: paymentMethod === 'CREDIT' ? installments : 1,
        status: 'APR',
      });
      draft.deliveries.push({
        id: deliveryId,
        invoiceId,
        date: new Date().toISOString(),
        status: 'PENDING',
        items: cart.map(item => ({ productId: item.product.id, expectedQty: item.qty, deliveredQty: 0, diff: 0, reason: '' })),
      });
      if (paymentMethod === 'CREDIT') {
        const customer = draft.customers.find(candidate => candidate.id === customerId);
        if (customer) customer.creditUsed += total;
      }
      draft.journalEntries.push({
        id: `ASI-${Date.now()}`,
        date: new Date().toISOString(),
        description: `Venta POS ${invoiceId}`,
        status: 'PEN',
        lines,
      });
      return draft;
    });

    setCart([]);
    setDiscountRate(0);
    setAgeVerified(false);
    setPaymentMethod('CASH');
    void syncFromApi();
  };

  return (
    <div>
      <div className="page-heading">
        <div><span className="eyebrow">VENTA SEGURA · CONEXIÓN MARIADB</span><h1>Punto de venta</h1></div>
        <div className="search-control"><Search size={18} /><input aria-label="Buscar productos" placeholder="Nombre, marca, SKU o código de barras" value={searchTerm} onChange={event => setSearchTerm(event.target.value)} /></div>
      </div>
      {notice && <p className="form-notice" role="status">{notice}</p>}
      <div className="pos-container">
        <section className="card pos-catalog" aria-label="Catálogo de productos">
          <div className="section-heading"><div><h2>Catálogo</h2><p>{filteredProducts.length} productos disponibles</p></div>
            <select className="select" aria-label="Filtrar categoría" value={categoryFilter} onChange={event => setCategoryFilter(event.target.value)}>
              <option value="">Todas las categorías</option>{categories.map(category => <option key={category}>{category}</option>)}
            </select>
          </div>
          <div className="pos-products">
            {filteredProducts.map(product => {
              const available = product.stock - (reservedByProduct[product.id] ?? 0);
              return <button type="button" key={product.id} className="pos-product-card" onClick={() => addToCart(product)} aria-label={`Agregar ${product.name} al carrito`}>
                <span className="product-category">{product.category}</span>
                <span className="product-card-name">{product.name}</span>
                <span className="product-meta">{product.brand} · {product.ml} ml · {product.abv}%</span>
                <span className="product-price">${product.price.toFixed(2)}</span>
                <span className={available <= product.minStock ? 'stock-low' : 'stock-ok'}>Disponible: {available}</span>
              </button>;
            })}
            {!filteredProducts.length && <p className="empty-state">No hay productos que coincidan con la búsqueda.</p>}
          </div>
        </section>

        <section className="card pos-cart" aria-label="Carrito de venta">
          <h2 className="cart-title"><ShoppingCart size={20} /> Carrito <span>{cart.length}</span></h2>
          <div className="cart-items">
            {cart.map(item => (
              <div key={item.product.id} className="cart-item">
                <div className="cart-product"><strong>{item.product.name}</strong><span>${item.product.price.toFixed(2)} / {item.product.sellUnit.toLowerCase()}</span></div>
                <div className="cart-controls">
                  <input aria-label={`Cantidad de ${item.product.name}`} type="number" min="1" max={item.product.stock - (reservedByProduct[item.product.id] ?? 0)} value={item.qty} onChange={event => updateCartQty(item.product.id, Number(event.target.value))} />
                  <strong>${item.subtotal.toFixed(2)}</strong>
                  <button type="button" className="icon-button" aria-label={`Quitar ${item.product.name}`} onClick={() => removeFromCart(item.product.id)}><Trash2 size={16} /></button>
                </div>
              </div>
            ))}
            {!cart.length && <p className="empty-state">Elige productos del catálogo para comenzar.</p>}
          </div>
          <div className="cart-totals">
            <label className="form-group"><span>Cliente</span>
              <select className="select" value={customerId} onChange={event => {
                setCustomerId(event.target.value);
                setAgeVerified(false);
                const customer = state.customers.find(candidate => candidate.id === event.target.value);
                setDiscountRate(customer?.discountRate ?? 0);
              }}>
                {state.customers.filter(customer => customer.status === 'ACTIVE').map(customer => <option key={customer.id} value={customer.id}>{customer.name}</option>)}
              </select>
            </label>
            <label className="form-group"><span>Forma de pago</span>
              <select className="select" value={paymentMethod} onChange={event => setPaymentMethod(event.target.value as typeof paymentMethod)}>
                <option value="CASH">Efectivo</option><option value="CARD">Tarjeta</option><option value="TRANSFER">Transferencia</option><option value="CREDIT">Crédito</option>
              </select>
            </label>
            {paymentMethod === 'CREDIT' && <div className="credit-fields">
              <p>Crédito disponible: <strong>${Math.max(creditAvailable, 0).toFixed(2)}</strong></p>
              <label className="form-group"><span>Cuotas (máximo 12)</span><input className="input" type="number" min="1" max="12" value={installments} onChange={event => setInstallments(Number(event.target.value))} /></label>
            </div>}
            <label className="form-group"><span>Descuento (%)</span><input className="input" type="number" min="0" max="100" step="0.5" value={discountRate} onChange={event => setDiscountRate(Number(event.target.value))} /></label>
            <label className="age-check"><ShieldAlert size={18} /><input type="checkbox" checked={ageVerified} onChange={event => setAgeVerified(event.target.checked)} /> Confirmo que verifiqué la mayoría de edad del cliente.</label>
            <div className="total-row"><span>Subtotal</span><strong>${subtotal.toFixed(2)}</strong></div>
            <div className="total-row"><span>Descuento</span><strong>−${discount.toFixed(2)}</strong></div>
            <div className="total-row"><span>Impuestos ({taxRate}%)</span><strong>${tax.toFixed(2)}</strong></div>
            <div className="total-row grand"><span>Total</span><strong>${total.toFixed(2)}</strong></div>
            <button type="button" className="btn btn-primary checkout-button" disabled={!cart.length || saving} onClick={handleCheckout}>
              {saving ? 'Registrando...' : 'Completar venta'}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
};
