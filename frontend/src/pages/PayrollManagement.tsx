import React, { useState, useEffect } from 'react';
import {
  Calculator, Plus, Trash2, CheckCircle, AlertCircle,
  Eye, ArrowUpRight, ArrowDownRight
} from 'lucide-react';
import { useGlobalStore } from '../context';
import { Payroll, Employee, BonusCatalogItem, DeductionCatalogItem } from '../types';
import { hrApi } from '../api';

const money = (val: number | string | undefined) =>
  `$${Number(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const RE_SQLI = /(--|\/\*|\*\/|;|'|"|<script|UNION\s+SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE|TRUNCATE\s+TABLE|EXEC\s*\()/i;

interface BonusLineEntry {
  bonusId: string;
  bonusName: string;
  amount: number;
}

interface DeductionLineEntry {
  deductionId: string;
  deductionName: string;
  amount: number;
}

export const PayrollManagement: React.FC = () => {
  const { state, updateState } = useGlobalStore();
  const [payrolls, setPayrolls] = useState<Payroll[]>(state.payrolls);
  const [employees, setEmployees] = useState<Employee[]>(state.employees);
  const [bonusCatalog, setBonusCatalog] = useState<BonusCatalogItem[]>([]);
  const [deductionCatalog, setDeductionCatalog] = useState<DeductionCatalogItem[]>([]);

  // Notificaciones
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Formulario de cabecera del rol
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = String(now.getMonth() + 1).padStart(2, '0');
  const defaultStartDate = `${currentYear}-${currentMonth}-01`;
  const lastDay = new Date(currentYear, now.getMonth() + 1, 0).getDate();
  const defaultEndDate = `${currentYear}-${currentMonth}-${String(lastDay).padStart(2, '0')}`;

  const [selectedEmpId, setSelectedEmpId] = useState<string>('');
  const [description, setDescription] = useState<string>(`Rol de pagos ${currentMonth}/${currentYear}`);
  const [startDate, setStartDate] = useState<string>(defaultStartDate);
  const [endDate, setEndDate] = useState<string>(defaultEndDate);
  const [baseSalary, setBaseSalary] = useState<number>(500);

  // Líneas del rol en preparación
  const [bonusLines, setBonusLines] = useState<BonusLineEntry[]>([]);
  const [deductionLines, setDeductionLines] = useState<DeductionLineEntry[]>([]);

  // Controles de selección de línea para añadir
  const [selectedBonusId, setSelectedBonusId] = useState<string>('');
  const [bonusAmount, setBonusAmount] = useState<number>(0);

  const [selectedDeductionId, setSelectedDeductionId] = useState<string>('');
  const [deductionAmount, setDeductionAmount] = useState<number>(0);

  // Inspección modal de detalle
  const [inspectingPayroll, setInspectingPayroll] = useState<Payroll | null>(null);

  // Cargar datos
  const loadPayrollData = async () => {
    try {
      const [remotePayrolls, remoteEmps, remoteBonuses, remoteDeductions] = await Promise.all([
        hrApi.listPayrolls().catch(() => null),
        hrApi.listEmployees().catch(() => null),
        hrApi.listBonuses().catch(() => []),
        hrApi.listDeductions().catch(() => []),
      ]);

      if (Array.isArray(remoteBonuses) && remoteBonuses.length) {
        setBonusCatalog(remoteBonuses);
        if (!selectedBonusId) {
          setSelectedBonusId(remoteBonuses[0].id);
          setBonusAmount(Number(remoteBonuses[0].valor || 0));
        }
      }
      if (Array.isArray(remoteDeductions) && remoteDeductions.length) {
        setDeductionCatalog(remoteDeductions);
        if (!selectedDeductionId) {
          setSelectedDeductionId(remoteDeductions[0].id);
          setDeductionAmount(Number(remoteDeductions[0].valor || 0));
        }
      }
      if (Array.isArray(remoteEmps) && remoteEmps.length) {
        setEmployees(remoteEmps);
        updateState(draft => {
          draft.employees = remoteEmps;
          return draft;
        });
        if (!selectedEmpId) {
          const firstActive = remoteEmps.find(e => e.status === 'ACTIVE') || remoteEmps[0];
          setSelectedEmpId(firstActive.id);
          setBaseSalary(Number(firstActive.salary || 500));
        }
      } else if (state.employees.length && !selectedEmpId) {
        const firstActive = state.employees.find(e => e.status === 'ACTIVE') || state.employees[0];
        setSelectedEmpId(firstActive.id);
        setBaseSalary(Number(firstActive.salary || 500));
      }

      if (Array.isArray(remotePayrolls)) {
        setPayrolls(remotePayrolls);
        updateState(draft => {
          draft.payrolls = remotePayrolls;
          return draft;
        });
      }
    } catch {
      // Usar estado local
    }
  };

  useEffect(() => {
    void loadPayrollData();
  }, []);

  // Al cambiar empleado, actualizar sueldo base
  const handleEmployeeChange = (empId: string) => {
    setSelectedEmpId(empId);
    const emp = employees.find(e => e.id === empId);
    if (emp) {
      setBaseSalary(Number(emp.salary || 0));
    }
  };

  // Al cambiar selección de bono en dropdown, precargar su valor referencial
  const handleBonusSelectChange = (bonusId: string) => {
    setSelectedBonusId(bonusId);
    const item = bonusCatalog.find(b => b.id === bonusId);
    if (item) {
      setBonusAmount(Number(item.valor || 0));
    }
  };

  // Al cambiar selección de descuento en dropdown, precargar valor referencial
  const handleDeductionSelectChange = (dedId: string) => {
    setSelectedDeductionId(dedId);
    const item = deductionCatalog.find(d => d.id === dedId);
    if (item) {
      if (item.id === 'DES-000001' || item.nombre.includes('IESS')) {
        // Cálculo automático aporte IESS 9.45%
        const iessCalc = Number((baseSalary * 0.0945).toFixed(2));
        setDeductionAmount(iessCalc);
      } else {
        setDeductionAmount(Number(item.valor || 0));
      }
    }
  };

  // Agregar línea de bonificación
  const handleAddBonusLine = () => {
    if (!selectedBonusId) {
      setNotice({ type: 'error', message: 'Debe seleccionar una bonificación del catálogo.' });
      return;
    }
    const cat = bonusCatalog.find(b => b.id === selectedBonusId);
    const name = cat?.nombre || selectedBonusId;

    if (bonusAmount <= 0) {
      setNotice({ type: 'error', message: 'El valor de la bonificación debe ser mayor a 0.' });
      return;
    }
    if (bonusAmount > 10000) {
      setNotice({ type: 'error', message: 'El valor de la bonificación no puede exceder $10,000.00.' });
      return;
    }

    setBonusLines(prev => [...prev, { bonusId: selectedBonusId, bonusName: name, amount: bonusAmount }]);
    setNotice(null);
  };

  // Eliminar línea de bono
  const handleRemoveBonusLine = (index: number) => {
    setBonusLines(prev => prev.filter((_, i) => i !== index));
  };

  // Agregar línea de deducción
  const handleAddDeductionLine = () => {
    if (!selectedDeductionId) {
      setNotice({ type: 'error', message: 'Debe seleccionar un descuento del catálogo.' });
      return;
    }
    const cat = deductionCatalog.find(d => d.id === selectedDeductionId);
    const name = cat?.nombre || selectedDeductionId;

    if (deductionAmount <= 0) {
      setNotice({ type: 'error', message: 'El valor del descuento debe ser mayor a 0.' });
      return;
    }
    if (deductionAmount > 10000) {
      setNotice({ type: 'error', message: 'El valor del descuento no puede exceder $10,000.00.' });
      return;
    }

    setDeductionLines(prev => [...prev, { deductionId: selectedDeductionId, deductionName: name, amount: deductionAmount }]);
    setNotice(null);
  };

  // Eliminar línea de descuento
  const handleRemoveDeductionLine = (index: number) => {
    setDeductionLines(prev => prev.filter((_, i) => i !== index));
  };

  // Atajo: autocalcular IESS 9.45%
  const handleAutoCalcIESS = () => {
    const iessConcept = deductionCatalog.find(d => d.id === 'DES-000001' || d.nombre.includes('IESS'));
    const iessValue = Number((baseSalary * 0.0945).toFixed(2));
    const dedId = iessConcept ? iessConcept.id : 'DES-000001';
    const dedName = iessConcept ? iessConcept.nombre : 'Aporte Individual IESS (9.45%)';

    // Evitar duplicar
    if (deductionLines.some(l => l.deductionId === dedId)) {
      setNotice({ type: 'error', message: 'El descuento de IESS ya está añadido a la lista.' });
      return;
    }

    setDeductionLines(prev => [...prev, { deductionId: dedId, deductionName: dedName, amount: iessValue }]);
    setNotice({ type: 'success', message: `Aporte IESS 9.45% calculado ($${iessValue}) agregado a las deducciones.` });
  };

  // Totales calculados en vivo
  const totalBonos = bonusLines.reduce((acc, curr) => acc + curr.amount, 0);
  const totalDescuentos = deductionLines.reduce((acc, curr) => acc + curr.amount, 0);
  const netoPagar = Number((baseSalary + totalBonos - totalDescuentos).toFixed(2));

  // Guardar rol de pago transaccional
  const handleCreatePayroll = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEmpId) {
      setNotice({ type: 'error', message: 'Selecciona un colaborador para preparar el rol de pagos.' });
      return;
    }
    const cleanDesc = description.trim();
    if (!cleanDesc || cleanDesc.length < 5 || cleanDesc.length > 40) {
      setNotice({ type: 'error', message: 'La descripción del rol debe tener entre 5 y 40 caracteres.' });
      return;
    }
    if (RE_SQLI.test(cleanDesc)) {
      setNotice({ type: 'error', message: 'La descripción contiene caracteres o sentencias no permitidas (SQL injection detectado).' });
      return;
    }
    if (!startDate || !endDate) {
      setNotice({ type: 'error', message: 'Debes definir la fecha de inicio y fin del periodo (PAGOS).' });
      return;
    }
    if (new Date(startDate) > new Date(endDate)) {
      setNotice({ type: 'error', message: 'La fecha de inicio no puede ser posterior a la fecha de fin.' });
      return;
    }
    if (baseSalary < 0 || baseSalary > 50000) {
      setNotice({ type: 'error', message: 'El sueldo base debe estar entre $0.00 y $50,000.00.' });
      return;
    }
    if (netoPagar < 0) {
      setNotice({ type: 'error', message: 'El neto a pagar no puede ser negativo. Los descuentos superan los ingresos.' });
      return;
    }

    try {
      const res = await hrApi.createPayroll({
        descripcion: description.trim() || `Rol de pago ${startDate} a ${endDate}`,
        fechaInicio: startDate,
        fechaFin: endDate,
        idEmpleado: selectedEmpId,
        sueldoBase: baseSalary,
        bonificaciones: totalBonos,
        descuentos: totalDescuentos,
        lineasBonos: bonusLines.map(b => ({
          idBonificacion: b.bonusId,
          fecha: endDate,
          valor: b.amount,
        })),
        lineasDescuentos: deductionLines.map(d => ({
          idDescuento: d.deductionId,
          fecha: endDate,
          valor: d.amount,
        })),
      });

      setNotice({
        type: 'success',
        message: `${res.mensaje || 'Rol de pago generado exitosamente.'} Código: ${res.id}. Neto: $${res.neto || netoPagar}.`,
      });

      // Limpiar líneas tras guardar
      setBonusLines([]);
      setDeductionLines([]);
      void loadPayrollData();
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Error al generar el rol de pago en la base de datos.' });
    }
  };

  // Aprobar rol de pago
  const handleApprovePayroll = async (payrollId: string) => {
    try {
      const res = await hrApi.approvePayroll(payrollId);
      setNotice({
        type: 'success',
        message: `${res.mensaje || 'Rol de pago aprobado exitosamente.'} Asiento contable generado automáticamente vía trigger.`,
      });
      void loadPayrollData();
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Error al aprobar el rol de pago.' });
    }
  };

  // Anular rol de pago
  const handleAnnulPayroll = async (payrollId: string) => {
    if (!window.confirm(`¿Confirmas que deseas anular el rol de pago ${payrollId}?`)) return;

    try {
      const res = await hrApi.annulPayroll(payrollId);
      setNotice({ type: 'success', message: res.mensaje || 'Rol de pago anulado exitosamente.' });
      void loadPayrollData();
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Error al anular el rol de pago.' });
    }
  };

  const selectedEmployeeObj = employees.find(e => e.id === selectedEmpId);

  return (
    <div>
      {/* Encabezado */}
      <div className="page-heading">
        <div>
          <span className="eyebrow">TALENTO HUMANO Y COMPENSACIONES</span>
          <h1>Gestión de Roles de Pago</h1>
          <p>Preparación transaccional línea por línea: catálogo de BONIFICACIONES, DESCUENTOS, periodos PAGOS e impacto contable automático.</p>
        </div>
      </div>

      {notice && (
        <div style={{
          padding: '12px 16px',
          marginBottom: '16px',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          backgroundColor: notice.type === 'success' ? '#ecfdf5' : '#fef2f2',
          color: notice.type === 'success' ? '#065f46' : '#991b1b',
          border: `1px solid ${notice.type === 'success' ? '#a7f3d0' : '#fecaca'}`,
        }}>
          {notice.type === 'success' ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
          <span>{notice.message}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 'bold' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Formulario Transaccional de Preparación */}
      <section className="card" style={{ padding: '20px', marginBottom: '24px' }}>
        <div className="section-heading" style={{ marginBottom: '16px' }}>
          <div>
            <h2 className="section-title" style={{ margin: 0 }}>Preparar Rol de Pago Individual</h2>
            <p style={{ margin: 0, fontSize: '0.85rem', color: '#6b7280' }}>
              Define el periodo (PAGOS), sueldo base y añade conceptos individuales desde los catálogos.
            </p>
          </div>
        </div>

        <form onSubmit={handleCreatePayroll}>
          {/* Cabecera del Rol: Colaborador y Periodo */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', marginBottom: '20px' }}>
            <label className="form-group" style={{ gridColumn: 'span 2' }}>
              Colaborador (EMPLEADOS) *
              <select
                className="select"
                value={selectedEmpId}
                onChange={e => handleEmployeeChange(e.target.value)}
                required
              >
                <option value="">-- Seleccione un colaborador --</option>
                {employees.filter(e => e.status === 'ACTIVE').map(emp => (
                  <option key={emp.id} value={emp.id}>
                    {emp.name} · {emp.department} · Sueldo: {money(emp.salary)}
                  </option>
                ))}
              </select>
            </label>

            <label className="form-group" style={{ gridColumn: 'span 2' }}>
              Descripción / Glosa del Rol (pag_Descripcion) *
              <input
                className="input"
                minLength={5}
                maxLength={40}
                pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9\s\.\-&/]+"
                title="Entre 5 y 40 caracteres (letras, números y signos básicos)."
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Ej: Nómina mensual Octubre 2026"
                required
              />
            </label>

            <label className="form-group">
              Fecha Inicio Periodo (pag_Fecha_Inicio) *
              <input
                className="input"
                type="date"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                required
              />
            </label>

            <label className="form-group">
              Fecha Fin Periodo (pag_Fecha_Fin) *
              <input
                className="input"
                type="date"
                value={endDate}
                onChange={e => setEndDate(e.target.value)}
                required
              />
            </label>

            <label className="form-group">
              Sueldo Base del Periodo ($) *
              <input
                className="input"
                type="number"
                min="0"
                step="0.01"
                value={baseSalary}
                onChange={e => setBaseSalary(Number(e.target.value))}
                required
              />
            </label>

            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', background: '#f3f4f6', padding: '10px 14px', borderRadius: '8px' }}>
              <span style={{ fontSize: '0.75rem', color: '#6b7280', textTransform: 'uppercase', fontWeight: 600 }}>Cargo Actual</span>
              <strong style={{ color: '#111827', fontSize: '0.95rem' }}>{selectedEmployeeObj?.role || 'Colaborador'}</strong>
              <span style={{ fontSize: '0.75rem', color: '#4b5563' }}>CI: {selectedEmployeeObj?.ci}</span>
            </div>
          </div>

          {/* Constructor Línea por Línea: Bonificaciones y Descuentos */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', borderTop: '1px solid #e5e7eb', paddingTop: '20px', marginBottom: '20px' }}>
            
            {/* SECCIÓN 1: BONIFICACIONES (BONxEMPxPAG) */}
            <div style={{ background: '#f0fdf4', padding: '16px', borderRadius: '10px', border: '1px solid #bbf7d0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#166534', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <ArrowUpRight size={18} /> Bonificaciones e Ingresos Extra
                </h3>
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#15803d' }}>
                  Subtotal: +{money(totalBonos)}
                </span>
              </div>

              {/* Selector de nuevo bono */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px auto', gap: '8px', marginBottom: '12px', alignItems: 'flex-end' }}>
                <label style={{ fontSize: '0.75rem', color: '#374151' }}>
                  Concepto (BONIFICACIONES)
                  <select
                    className="select"
                    style={{ height: '36px', fontSize: '0.85rem' }}
                    value={selectedBonusId}
                    onChange={e => handleBonusSelectChange(e.target.value)}
                  >
                    <option value="">-- Seleccione una bonificación --</option>
                    {bonusCatalog.map(b => (
                      <option key={b.id} value={b.id}>{b.nombre} ({money(b.valor)})</option>
                    ))}
                  </select>
                </label>

                <label style={{ fontSize: '0.75rem', color: '#374151' }}>
                  Monto ($)
                  <input
                    className="input"
                    type="number"
                    min="0"
                    step="0.01"
                    style={{ height: '36px', fontSize: '0.85rem' }}
                    value={bonusAmount}
                    onChange={e => setBonusAmount(Number(e.target.value))}
                  />
                </label>

                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ height: '36px', padding: '0 12px', backgroundColor: '#15803d', borderColor: '#15803d' }}
                  onClick={handleAddBonusLine}
                >
                  <Plus size={15} /> Añadir
                </button>
              </div>

              {/* Lista de bonificaciones agregadas */}
              <div style={{ background: '#ffffff', borderRadius: '6px', border: '1px solid #dcfce7', minHeight: '120px', maxHeight: '180px', overflowY: 'auto' }}>
                {bonusLines.map((line, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '8px 12px',
                      borderBottom: '1px solid #f0fdf4',
                      fontSize: '0.85rem',
                    }}
                  >
                    <div>
                      <strong style={{ color: '#166534' }}>{line.bonusName}</strong>
                      <span style={{ fontSize: '0.75rem', color: '#6b7280', marginLeft: '6px' }}>({line.bonusId})</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 600, color: '#15803d' }}>+{money(line.amount)}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveBonusLine(idx)}
                        style={{ border: 'none', background: 'none', color: '#ef4444', cursor: 'pointer', padding: '2px' }}
                        title="Quitar bono"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
                {!bonusLines.length && (
                  <div style={{ textAlign: 'center', padding: '24px', color: '#9ca3af', fontSize: '0.85rem' }}>
                    Sin bonos adicionales agregados a este rol.
                  </div>
                )}
              </div>
            </div>

            {/* SECCIÓN 2: DEDUCCIONES (DESxEMPxPAG) */}
            <div style={{ background: '#fef2f2', padding: '16px', borderRadius: '10px', border: '1px solid #fecaca' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#991b1b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <ArrowDownRight size={18} /> Descuentos y Deducciones de Ley
                </h3>
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#b91c1c' }}>
                  Subtotal: -{money(totalDescuentos)}
                </span>
              </div>

              {/* Selector de nuevo descuento */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px auto', gap: '8px', marginBottom: '12px', alignItems: 'flex-end' }}>
                <label style={{ fontSize: '0.75rem', color: '#374151' }}>
                  Concepto (DESCUENTOS)
                  <select
                    className="select"
                    style={{ height: '36px', fontSize: '0.85rem' }}
                    value={selectedDeductionId}
                    onChange={e => handleDeductionSelectChange(e.target.value)}
                  >
                    <option value="">-- Seleccione un descuento --</option>
                    {deductionCatalog.map(d => (
                      <option key={d.id} value={d.id}>{d.nombre} ({money(d.valor)})</option>
                    ))}
                  </select>
                </label>

                <label style={{ fontSize: '0.75rem', color: '#374151' }}>
                  Monto ($)
                  <input
                    className="input"
                    type="number"
                    min="0"
                    step="0.01"
                    style={{ height: '36px', fontSize: '0.85rem' }}
                    value={deductionAmount}
                    onChange={e => setDeductionAmount(Number(e.target.value))}
                  />
                </label>

                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ height: '36px', padding: '0 12px', backgroundColor: '#dc2626', borderColor: '#dc2626' }}
                  onClick={handleAddDeductionLine}
                >
                  <Plus size={15} /> Añadir
                </button>
              </div>

              {/* Botón rápido IESS */}
              <div style={{ marginBottom: '10px' }}>
                <button
                  type="button"
                  className="btn btn-outline"
                  style={{ fontSize: '0.75rem', padding: '3px 8px', color: '#b91c1c', borderColor: '#fca5a5' }}
                  onClick={handleAutoCalcIESS}
                >
                  ⚡ Autocalcular 9.45% IESS (${(baseSalary * 0.0945).toFixed(2)})
                </button>
              </div>

              {/* Lista de deducciones agregadas */}
              <div style={{ background: '#ffffff', borderRadius: '6px', border: '1px solid #fee2e2', minHeight: '120px', maxHeight: '180px', overflowY: 'auto' }}>
                {deductionLines.map((line, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '8px 12px',
                      borderBottom: '1px solid #fef2f2',
                      fontSize: '0.85rem',
                    }}
                  >
                    <div>
                      <strong style={{ color: '#991b1b' }}>{line.deductionName}</strong>
                      <span style={{ fontSize: '0.75rem', color: '#6b7280', marginLeft: '6px' }}>({line.deductionId})</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 600, color: '#dc2626' }}>-{money(line.amount)}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveDeductionLine(idx)}
                        style={{ border: 'none', background: 'none', color: '#ef4444', cursor: 'pointer', padding: '2px' }}
                        title="Quitar descuento"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
                {!deductionLines.length && (
                  <div style={{ textAlign: 'center', padding: '24px', color: '#9ca3af', fontSize: '0.85rem' }}>
                    Sin deducciones agregadas a este rol.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Resumen de Liquidación y Confirmación */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: '#f8fafc',
            border: '2px solid #e2e8f0',
            borderRadius: '10px',
            padding: '16px 20px',
          }}>
            <div style={{ display: 'flex', gap: '30px', alignItems: 'center' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase' }}>Sueldo Base</span>
                <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#1e293b' }}>{money(baseSalary)}</div>
              </div>
              <div style={{ color: '#94a3b8', fontSize: '1.2rem' }}>+</div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#16a34a', textTransform: 'uppercase' }}>Bonificaciones</span>
                <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#16a34a' }}>+{money(totalBonos)}</div>
              </div>
              <div style={{ color: '#94a3b8', fontSize: '1.2rem' }}>-</div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#dc2626', textTransform: 'uppercase' }}>Deducciones</span>
                <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#dc2626' }}>-{money(totalDescuentos)}</div>
              </div>
              <div style={{ color: '#94a3b8', fontSize: '1.2rem' }}>=</div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#4f46e5', textTransform: 'uppercase', fontWeight: 700 }}>Líquido a Pagar (Neto)</span>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#4f46e5' }}>{money(netoPagar)}</div>
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ padding: '12px 24px', fontSize: '0.95rem' }}
            >
              <Calculator size={18} /> Generar Rol de Pago (PAGOS)
            </button>
          </div>
        </form>
      </section>

      {/* Tabla Maestra de Roles de Pago */}
      <section className="card">
        <div className="section-heading">
          <div>
            <h2 className="section-title">Historial de Roles de Pago Generados (PAGOS + PAGxEMP)</h2>
            <p style={{ margin: 0, fontSize: '0.85rem', color: '#6b7280' }}>
              Los roles aprobados transfieren automáticamente su importe al Libro Diario contable mediante trigger SQL.
            </p>
          </div>
        </div>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Código Pago</th>
                <th>Descripción / Periodo</th>
                <th>Colaborador</th>
                <th>Departamento</th>
                <th>Sueldo Base</th>
                <th>Bonos</th>
                <th>Descuentos</th>
                <th>Neto a Pagar</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {payrolls.map(p => {
                const emp = employees.find(e => e.id === p.employeeId);
                const empName = p.employeeName || emp?.name || p.employeeId;
                const deptName = p.department || emp?.department || 'Ventas';

                return (
                  <tr key={p.id}>
                    <td><code>{p.id}</code></td>
                    <td>
                      <strong>{p.description || `Rol ${p.id}`}</strong>
                      <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                        {p.startDate ? `${String(p.startDate).slice(0, 10)} a ${String(p.endDate).slice(0, 10)}` : String(p.date).slice(0, 10)}
                      </div>
                    </td>
                    <td>{empName}</td>
                    <td>{deptName}</td>
                    <td>{money(p.baseSalary)}</td>
                    <td style={{ color: '#16a34a' }}>+{money(p.bonus)}</td>
                    <td style={{ color: '#dc2626' }}>-{money(p.deductions)}</td>
                    <td><strong style={{ color: '#4f46e5' }}>{money(p.amount)}</strong></td>
                    <td>
                      <span className={`badge badge-${p.status === 'APR' ? 'APR' : p.status === 'ANU' ? 'ANU' : 'ABI'}`}>
                        {p.status}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <button
                          type="button"
                          className="btn btn-outline"
                          style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                          onClick={() => setInspectingPayroll(p)}
                          title="Inspeccionar desglose línea por línea"
                        >
                          <Eye size={13} /> Desglose
                        </button>

                        {(p.status === 'ABI' || p.status === 'PEN') && (
                          <>
                            <button
                              type="button"
                              className="btn btn-outline"
                              style={{ padding: '4px 8px', fontSize: '0.75rem', color: '#059669', borderColor: '#6ee7b7' }}
                              onClick={() => handleApprovePayroll(p.id)}
                              title="Aprobar rol e impactar en Contabilidad"
                            >
                              Aprobar
                            </button>
                            <button
                              type="button"
                              className="btn btn-outline"
                              style={{ padding: '4px 8px', fontSize: '0.75rem', color: '#dc2626', borderColor: '#fca5a5' }}
                              onClick={() => handleAnnulPayroll(p.id)}
                              title="Anular rol de pago"
                            >
                              Anular
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!payrolls.length && (
                <tr>
                  <td colSpan={10} className="empty-state">
                    No existen roles de pago registrados en el sistema.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Modal de Desglose Línea por Línea */}
      {inspectingPayroll && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            maxWidth: '650px',
            width: '100%',
            padding: '24px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #e5e7eb', paddingBottom: '12px', marginBottom: '16px' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#6366f1', fontWeight: 700, textTransform: 'uppercase' }}>
                  DETALLE DE ROL DE PAGO: {inspectingPayroll.id}
                </span>
                <h2 style={{ margin: '4px 0 0 0', fontSize: '1.25rem', color: '#111827' }}>
                  {inspectingPayroll.employeeName || inspectingPayroll.employeeId}
                </h2>
                <div style={{ fontSize: '0.85rem', color: '#6b7280', marginTop: '2px' }}>
                  Glosa: {inspectingPayroll.description || 'Nómina'} · Estado: <strong>{inspectingPayroll.status}</strong>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setInspectingPayroll(null)}
                style={{ background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer', color: '#6b7280' }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
              {/* Desglose Bonificaciones */}
              <div style={{ background: '#f0fdf4', padding: '14px', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '0.85rem', color: '#166534' }}>
                  Líneas de Bonificación (BONxEMPxPAG)
                </h4>
                {inspectingPayroll.bonusLines && inspectingPayroll.bonusLines.length ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {inspectingPayroll.bonusLines.map((bl, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                        <span>{bl.bonusName || bl.bonusId}</span>
                        <strong style={{ color: '#15803d' }}>+{money(bl.amount)}</strong>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: '0.8rem', color: '#6b7280' }}>
                    Sin conceptos específicos registrados. Monto total: +{money(inspectingPayroll.bonus)}
                  </div>
                )}
              </div>

              {/* Desglose Deducciones */}
              <div style={{ background: '#fef2f2', padding: '14px', borderRadius: '8px', border: '1px solid #fecaca' }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '0.85rem', color: '#991b1b' }}>
                  Líneas de Deducción (DESxEMPxPAG)
                </h4>
                {inspectingPayroll.deductionLines && inspectingPayroll.deductionLines.length ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {inspectingPayroll.deductionLines.map((dl, i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                        <span>{dl.deductionName || dl.deductionId}</span>
                        <strong style={{ color: '#dc2626' }}>-{money(dl.amount)}</strong>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: '0.8rem', color: '#6b7280' }}>
                    Sin conceptos específicos registrados. Monto total: -{money(inspectingPayroll.deductions)}
                  </div>
                )}
              </div>
            </div>

            {/* Total Liquidado */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              background: '#f8fafc',
              padding: '12px 16px',
              borderRadius: '8px',
              border: '1px solid #e2e8f0',
            }}>
              <div>
                <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Base: {money(inspectingPayroll.baseSalary)}</span> · 
                <span style={{ fontSize: '0.8rem', color: '#16a34a', marginLeft: '6px' }}>Bonos: +{money(inspectingPayroll.bonus)}</span> · 
                <span style={{ fontSize: '0.8rem', color: '#dc2626', marginLeft: '6px' }}>Desc: -{money(inspectingPayroll.deductions)}</span>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span style={{ fontSize: '0.75rem', color: '#4f46e5', textTransform: 'uppercase', fontWeight: 700 }}>Total Neto</span>
                <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#4f46e5' }}>{money(inspectingPayroll.amount)}</div>
              </div>
            </div>

            <div style={{ marginTop: '16px', textAlign: 'right' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setInspectingPayroll(null)}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
