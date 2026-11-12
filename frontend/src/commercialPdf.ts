import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { PurchaseOrderRecord } from './api';
import type { Customer, Delivery, Invoice, Product, Reception } from './types';

type Field = [string, string];
export interface CommercialDocument {
  title: string;
  id: string;
  fields: Field[];
  columns: string[];
  rows: string[][];
  totals?: Field[];
}

const value = (input: unknown) => input === null || input === undefined || input === '' ? 'No disponible' : String(input);
const amount = (input: unknown) => {
  if (input === null || input === undefined || input === '') return 'No disponible';
  const number = Number(input);
  return Number.isFinite(number) ? `$${number.toFixed(2)}` : 'No disponible';
};
const date = (input: string | null | undefined) => {
  if (!input) return 'No disponible';
  // Date-only values should not shift to the previous day in the local timezone.
  if (/^\d{4}-\d{2}-\d{2}$/.test(input)) return input;
  const parsed = new Date(input);
  return Number.isNaN(parsed.getTime()) ? input : parsed.toLocaleString('es-EC');
};

const paymentLabels: Record<string, string> = {
  CASH: 'Efectivo', CARD: 'Tarjeta', TRANSFER: 'Transferencia', CREDIT: 'Crédito',
};

// The sales endpoint returns flat line fields, while locally created invoices use CartItem.
type InvoiceLine = Invoice['items'][number] & {
  productId?: string; productName?: string; price?: number | string;
};
type InvoiceWithCustomer = Invoice & { customerName?: string };

export function invoiceDocument(invoice: Invoice, customers: Customer[]): CommercialDocument {
  const customer = customers.find(item => item.id === invoice.customerId);
  const remote = invoice as InvoiceWithCustomer;
  return {
    title: 'Factura comercial', id: invoice.id,
    fields: [
      ['Fecha', date(invoice.date)], ['Estado', value(invoice.status)],
      ['Cliente', remote.customerName || customer?.name || value(invoice.customerId)],
      ['Identificación', value(customer?.ciRuc)],
      ['Forma de pago', paymentLabels[invoice.paymentMethod] || value(invoice.paymentMethod)],
    ],
    columns: ['Producto', 'Cantidad', 'Precio unitario', 'Importe'],
    rows: (invoice.items || []).map(raw => {
      const item = raw as InvoiceLine;
      return [item.productName || item.product?.name || item.productId || item.product?.id || 'No disponible',
        value(item.qty), amount(item.price ?? item.product?.price), amount(item.subtotal)];
    }),
    totals: [['Subtotal', amount(invoice.subtotal)], ['Descuento', amount(invoice.discount)],
      ['IVA', amount(invoice.tax)], ['Total', amount(invoice.total)]],
  };
}

export function purchaseDocument(order: PurchaseOrderRecord): CommercialDocument {
  return {
    title: 'Orden de compra', id: order.id,
    fields: [['Fecha', date(order.fecha)], ['Entrega prevista', date(order.fechaEntrega)],
      ['Estado', value(order.estado)], ['Proveedor', value(order.proveedor)], ['ID proveedor', value(order.proveedorId)]],
    columns: ['Producto', 'Cantidad', 'Costo unitario', 'Importe'],
    rows: (order.items || []).map(item => [item.producto || item.productoId, value(item.cantidad), amount(item.costoUnitario), amount(item.subtotal)]),
    totals: [['Subtotal', amount(order.subtotal)], ['IVA', amount(order.iva)], ['Total', amount(order.total)]],
  };
}

type WarehouseItem = { productId: string; productName?: string; expectedQty: number; diff: number; reason: string };
const productName = (item: WarehouseItem, products: Product[]) =>
  item.productName || products.find(product => product.id === item.productId)?.name || item.productId;

export function receptionDocument(reception: Reception, products: Product[]): CommercialDocument {
  const confirmed = reception.status === 'APR' || reception.status === 'COMPLETED';
  return {
    title: 'Recepción de compra', id: reception.id,
    fields: [['Fecha', date(reception.date)], ['Estado', value(reception.status)], ['Orden de compra', value(reception.poId)]],
    columns: ['Producto', 'Solicitado', 'Recibido', 'Diferencia', 'Motivo'],
    rows: (reception.items || []).map(item => [productName(item, products), value(item.expectedQty),
      confirmed ? value(item.receivedQty) : 'No confirmado', confirmed ? value(item.diff) : 'No confirmado',
      confirmed ? (item.reason || '—') : '—']),
  };
}

export function deliveryDocument(delivery: Delivery, products: Product[], invoices: Invoice[] = [], customers: Customer[] = []): CommercialDocument {
  const confirmed = delivery.status === 'APR' || delivery.status === 'ENT' || delivery.status === 'COMPLETED';
  const invoice = invoices.find(item => item.id === delivery.invoiceId) as InvoiceWithCustomer | undefined;
  const customerName = invoice?.customerName || customers.find(item => item.id === invoice?.customerId)?.name;
  return {
    title: 'Entrega de venta', id: delivery.id,
    fields: [['Fecha', date(delivery.date)], ['Estado', value(delivery.status)], ['Factura', value(delivery.invoiceId)],
      ...(customerName ? [['Cliente', customerName] as Field] : [])],
    columns: ['Producto', 'Solicitado', 'Entregado', 'Diferencia', 'Motivo'],
    rows: (delivery.items || []).map(item => [productName(item, products), value(item.expectedQty),
      confirmed ? value(item.deliveredQty) : 'No confirmado', confirmed ? value(item.diff) : 'No confirmado',
      confirmed ? (item.reason || '—') : '—']),
  };
}

export function renderCommercialPdf(document: CommercialDocument): jsPDF {
  const pdf = new jsPDF();
  pdf.setFontSize(18);
  pdf.text(document.title, 14, 18);
  pdf.setFontSize(11);
  pdf.text(`Documento: ${document.id}`, 14, 26);
  pdf.setFontSize(9);
  pdf.text('Documento comercial interno. No es un comprobante electrónico SRI.', 14, 32);
  autoTable(pdf, {
    startY: 37, body: document.fields, theme: 'plain',
    styles: { fontSize: 9, cellPadding: 1.5, overflow: 'linebreak' },
    columnStyles: { 0: { fontStyle: 'bold', cellWidth: 42 } },
  });
  const afterHeader = (pdf as jsPDF & { lastAutoTable: { finalY: number } }).lastAutoTable.finalY;
  autoTable(pdf, {
    startY: afterHeader + 5, head: [document.columns],
    body: document.rows.length ? document.rows : [['Sin detalle disponible', ...document.columns.slice(1).map(() => '')]],
    theme: 'grid', styles: { fontSize: 8, cellPadding: 2, overflow: 'linebreak' },
    headStyles: { fillColor: [100, 30, 45] },
  });
  if (document.totals?.length) {
    const afterDetails = (pdf as jsPDF & { lastAutoTable: { finalY: number } }).lastAutoTable.finalY;
    autoTable(pdf, {
      startY: afterDetails + 4, body: document.totals, theme: 'plain',
      margin: { left: 130, right: 14 }, styles: { fontSize: 9, cellPadding: 1.5 },
      columnStyles: { 0: { fontStyle: 'bold' }, 1: { halign: 'right' } },
    });
  }
  const pages = pdf.getNumberOfPages();
  for (let page = 1; page <= pages; page++) {
    pdf.setPage(page);
    pdf.setFontSize(8);
    pdf.text(`Página ${page} de ${pages}`, 196, 290, { align: 'right' });
  }
  return pdf;
}

export function downloadCommercialPdf(document: CommercialDocument): void {
  const filename = `${document.title}-${document.id}`.replace(/[^\w-]+/g, '-');
  renderCommercialPdf(document).save(`${filename}.pdf`);
}
