import test from 'node:test';
import assert from 'node:assert/strict';
import {
  deliveryDocument, invoiceDocument, purchaseDocument, receptionDocument, renderCommercialPdf,
} from '../src/commercialPdf.ts';

const invoice = {
  id: 'FAC001', date: '2026-03-10', status: 'ANU', customerId: 'C1',
  customerName: 'María Pérez', paymentMethod: 'CASH',
  subtotal: '25.00', discount: 1, tax: 3.6, total: 27.6,
  items: [{ productId: 'P1', productName: 'Ron añejo', qty: 2, price: '12.50', subtotal: '25.00' }],
};
const order = {
  id: 'OC001', fecha: '2026-03-10', fechaEntrega: null, estado: 'APR', proveedor: 'Proveedor',
  proveedorId: 'PR1', subtotal: '20.00', iva: '3.00', total: '23.00',
  items: [{ productoId: 'P1', producto: 'Ron', cantidad: 2, costoUnitario: '10.00', subtotal: '20.00' }],
};
const reception = {
  id: 'REC001', poId: 'OC001', date: '2026-03-10', status: 'APR',
  items: [{ productId: 'P1', productName: 'Ron', expectedQty: 4, receivedQty: 3, diff: -1, reason: 'Rotura' }],
};
const delivery = {
  id: 'ENT001', invoiceId: 'FAC001', date: '2026-03-10', status: 'ENT',
  items: [{ productId: 'P1', expectedQty: 4, deliveredQty: 0, diff: -4, reason: 'Sin stock' }],
};

test('factura usa detalle histórico del API y conserva estado y totales', () => {
  const doc = invoiceDocument(invoice, []);
  assert.deepEqual(doc.rows[0], ['Ron añejo', '2', '$12.50', '$25.00']);
  assert.deepEqual(doc.fields.find(([key]) => key === 'Cliente'), ['Cliente', 'María Pérez']);
  assert.deepEqual(doc.fields.find(([key]) => key === 'Estado'), ['Estado', 'ANU']);
  assert.deepEqual(doc.totals.at(-1), ['Total', '$27.60']);
  const local = invoiceDocument({ ...invoice, items: [{ product: { id: 'P2', name: 'Vino', price: 4 }, qty: 2, subtotal: 8 }] }, []);
  assert.deepEqual(local.rows[0], ['Vino', '2', '$4.00', '$8.00']);
});

test('orden usa importes y fechas almacenados', () => {
  const doc = purchaseDocument(order);
  assert.deepEqual(doc.rows[0], ['Ron', '2', '$10.00', '$20.00']);
  assert.deepEqual(doc.fields.find(([key]) => key === 'Fecha'), ['Fecha', '2026-03-10']);
  assert.deepEqual(doc.fields.find(([key]) => key === 'Entrega prevista'), ['Entrega prevista', 'No disponible']);
  assert.deepEqual(doc.totals.at(-1), ['Total', '$23.00']);
});

test('movimientos confirmados y pendientes no confunden cantidades', () => {
  assert.deepEqual(receptionDocument(reception, []).rows[0], ['Ron', '4', '3', '-1', 'Rotura']);
  assert.deepEqual(deliveryDocument(delivery, [{ id: 'P1', name: 'Vino' }]).rows[0], ['Vino', '4', '0', '-4', 'Sin stock']);
  assert.deepEqual(deliveryDocument(delivery, [], [invoice]).fields.at(-1), ['Cliente', 'María Pérez']);
  assert.deepEqual(receptionDocument({ ...reception, status: 'PEN' }, []).rows[0],
    ['Ron', '4', 'No confirmado', 'No confirmado', '—']);
  assert.deepEqual(deliveryDocument({ ...delivery, status: 'ANU' }, []).rows[0],
    ['P1', '4', 'No confirmado', 'No confirmado', '—']);
});

test('PDF real incluye cabecera, detalle, totales, leyenda y saltos de página', () => {
  for (const doc of [invoiceDocument(invoice, []), purchaseDocument(order), receptionDocument(reception, []), deliveryDocument(delivery, [])]) {
    const pdf = renderCommercialPdf(doc);
    const output = pdf.output();
    assert.ok(output.startsWith('%PDF-'));
    assert.ok(output.includes(doc.id));
    assert.ok(output.includes('comprobante'));
    assert.ok(output.includes(doc.rows[0][0]));
    if (doc.totals) assert.ok(output.includes(doc.totals.at(-1)[1]));
  }
  const longDoc = purchaseDocument({ ...order, items: Array.from({ length: 100 }, (_, i) => ({ ...order.items[0], producto: `Producto ${i}` })) });
  const longPdf = renderCommercialPdf(longDoc);
  assert.ok(longPdf.getNumberOfPages() > 1);
  assert.ok(longPdf.output().includes('Producto 99'));
  assert.ok(longPdf.output().includes('$23.00'));
  const empty = renderCommercialPdf(purchaseDocument({ ...order, items: [] })).output();
  assert.ok(empty.includes('Sin detalle disponible'));
});
