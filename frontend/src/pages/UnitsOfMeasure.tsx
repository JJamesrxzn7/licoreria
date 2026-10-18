import React, { useEffect, useState } from 'react';
import { Scale, Plus, Edit3, Trash2, CheckCircle2, AlertCircle, X, HelpCircle } from 'lucide-react';
import { unitApi } from '../api';
import { UnitOfMeasure } from '../types';

const RE_SQLI = /(--|\/\*|\*\/|;|'|"|<script|UNION\s+SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE|TRUNCATE\s+TABLE|EXEC\s*\()/i;

export const UnitsOfMeasure: React.FC = () => {
  const [units, setUnits] = useState<UnitOfMeasure[]>([]);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Formulario nuevo
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [newFactor, setNewFactor] = useState<number | string>(1);

  // Modal edición
  const [editingUnit, setEditingUnit] = useState<UnitOfMeasure | null>(null);
  const [editName, setEditName] = useState('');
  const [editFactor, setEditFactor] = useState<number | string>(1);

  const loadUnits = async () => {
    setLoading(true);
    try {
      const data = await unitApi.list();
      if (Array.isArray(data)) {
        setUnits(data.map(u => ({ ...u, factor: Number(u.factor) || 1 })));
      }
    } catch (err: any) {
      setNotice({ type: 'error', message: err.message || 'Error al cargar unidades de medida.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadUnits();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanId = newId.trim().toUpperCase();
    const cleanName = newName.trim();
    const numFactor = Number(newFactor);

    if (!cleanId || cleanId.length > 3) {
      setNotice({ type: 'error', message: 'El código de unidad debe tener entre 1 y 3 caracteres (CHAR(3)).' });
      return;
    }
    if (!/^[A-Z0-9]+$/.test(cleanId)) {
      setNotice({ type: 'error', message: 'El código solo puede contener letras y números sin espacios (ej: CAJ, BOT, SIX).' });
      return;
    }
    if (cleanName.length < 2 || cleanName.length > 20) {
      setNotice({ type: 'error', message: 'La descripción de la unidad debe tener entre 2 y 20 caracteres (CHAR(20)).' });
      return;
    }
    if (RE_SQLI.test(cleanName) || RE_SQLI.test(cleanId)) {
      setNotice({ type: 'error', message: 'Se detectaron caracteres o patrones no permitidos (anti-SQLi).' });
      return;
    }
    if (isNaN(numFactor) || numFactor <= 0) {
      setNotice({ type: 'error', message: 'El factor de conversión debe ser un número positivo mayor a 0 (ej: 12 para caja, 1 para botella).' });
      return;
    }
    if (numFactor > 99999.99) {
      setNotice({ type: 'error', message: 'El factor de conversión supera el límite máximo permitido (99,999.99).' });
      return;
    }

    try {
      const res = await unitApi.create({
        id: cleanId,
        nombre: cleanName,
        factor: numFactor,
      });
      setNotice({ type: 'success', message: res.mensaje || `Unidad de medida '${cleanId}' creada exitosamente.` });
      setNewId('');
      setNewName('');
      setNewFactor(1);
      void loadUnits();
    } catch (err: any) {
      setNotice({ type: 'error', message: err.message || 'Error al crear la unidad de medida.' });
    }
  };

  const handleStartEdit = (u: UnitOfMeasure) => {
    setEditingUnit(u);
    setEditName(u.nombre);
    setEditFactor(u.factor);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUnit) return;
    const cleanName = editName.trim();
    const numFactor = Number(editFactor);

    if (cleanName.length < 2 || cleanName.length > 20) {
      setNotice({ type: 'error', message: 'La descripción de la unidad debe tener entre 2 y 20 caracteres.' });
      return;
    }
    if (RE_SQLI.test(cleanName)) {
      setNotice({ type: 'error', message: 'La descripción contiene caracteres no permitidos.' });
      return;
    }
    if (isNaN(numFactor) || numFactor <= 0 || numFactor > 99999.99) {
      setNotice({ type: 'error', message: 'El factor de conversión debe ser un número positivo entre 0.01 y 99,999.99.' });
      return;
    }

    try {
      const res = await unitApi.update(editingUnit.id, {
        nombre: cleanName,
        factor: numFactor,
      });
      setNotice({ type: 'success', message: res.mensaje || `Unidad '${editingUnit.id}' actualizada.` });
      setEditingUnit(null);
      void loadUnits();
    } catch (err: any) {
      setNotice({ type: 'error', message: err.message || 'Error al actualizar la unidad de medida.' });
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm(`¿Confirmas que deseas eliminar la unidad de medida '${id}'? Solo se permitirá si no está asignada a productos.`)) {
      return;
    }
    try {
      const res = await unitApi.delete(id);
      setNotice({ type: 'success', message: res.mensaje || `Unidad '${id}' eliminada exitosamente.` });
      void loadUnits();
    } catch (err: any) {
      setNotice({ type: 'error', message: err.message || 'Error al eliminar la unidad de medida.' });
    }
  };

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ABASTECIMIENTO & INVENTARIOS</span>
          <h1>Unidades de Medida</h1>
          <p>Catálogo maestro de unidades de compra, venta y factores de conversión (tabla UNIDADES_MEDIDAS).</p>
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
          {notice.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
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

      {/* Formulario de Registro */}
      <section className="card" style={{ padding: '20px', marginBottom: '24px' }}>
        <h2 className="section-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Scale size={18} /> Registrar Nueva Unidad de Medida
        </h2>
        <p style={{ margin: '0 0 16px 0', fontSize: '0.85rem', color: '#64748b' }}>
          Define el código de 3 letras, la descripción y el factor de conversión respecto a la unidad base de venta.
        </p>

        <form onSubmit={handleCreate}>
          <div className="grid-3" style={{ gap: '16px', alignItems: 'flex-start' }}>
            <label className="form-group">
              <span>Código de Unidad (id_Unidad_Medida) <strong style={{ color: '#ef4444' }}>*</strong></span>
              <input
                className="input"
                maxLength={3}
                pattern="[A-Za-z0-9]{1,3}"
                title="1 a 3 caracteres alfanuméricos (ej: CAJ, BOT, SIX, LIT, UND)"
                placeholder="Ej. CAJ"
                value={newId}
                onChange={e => setNewId(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))}
                required
              />
              <small style={{ fontSize: '11px', color: '#64748b' }}>Máximo 3 caracteres CHAR(3)</small>
            </label>

            <label className="form-group">
              <span>Descripción (um_Descripcion) <strong style={{ color: '#ef4444' }}>*</strong></span>
              <input
                className="input"
                maxLength={20}
                placeholder="Ej. Caja x12 botellas"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                required
              />
              <small style={{ fontSize: '11px', color: '#64748b' }}>Máximo 20 caracteres CHAR(20)</small>
            </label>

            <label className="form-group">
              <span>Factor de Conversión (um_FactorConversion) <strong style={{ color: '#ef4444' }}>*</strong></span>
              <input
                className="input"
                type="number"
                min="0.01"
                max="99999.99"
                step="0.01"
                placeholder="Ej. 12.00"
                value={newFactor}
                onChange={e => setNewFactor(e.target.value)}
                required
              />
              <small style={{ fontSize: '11px', color: '#64748b' }}>
                Unidades mínimas contenidas (Ej: Caja x12 = 12.00, Botella = 1.00)
              </small>
            </label>
          </div>

          <div style={{ background: '#f8fafc', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0', marginTop: '16px', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
            <HelpCircle size={18} color="#6366f1" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div style={{ fontSize: '0.85rem', color: '#475569' }}>
              <strong>¿Para qué sirve el Factor de Conversión?</strong> Si compra el licor en <em>Cajas de 12 botellas</em> (U.M. Compra) y lo vende por <em>Botellas individuales</em> (U.M. Venta), el factor de conversión permite al sistema calcular automáticamente el ingreso real a bodega y el costo por unidad para el kárdex y catálogo de productos.
            </div>
          </div>

          <div className="form-actions" style={{ marginTop: '16px' }}>
            <button type="submit" className="btn btn-primary">
              <Plus size={16} /> Guardar Unidad de Medida
            </button>
          </div>
        </form>
      </section>

      {/* Directorio de Unidades de Medida */}
      <section className="card">
        <div className="section-heading">
          <div>
            <h2>Directorio de Unidades de Medida Registradas</h2>
            <p>{units.length} unidades disponibles para asignar a productos</p>
          </div>
        </div>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th style={{ width: '120px' }}>Código (PK)</th>
                <th>Descripción (um_Descripcion)</th>
                <th style={{ width: '180px', textAlign: 'right' }}>Factor de Conversión</th>
                <th>Equivalencia Comercial</th>
                <th style={{ width: '140px', textAlign: 'center' }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {units.map(unit => (
                <tr key={unit.id}>
                  <td>
                    <code style={{ fontSize: '0.95rem', fontWeight: 700, color: '#4338ca', background: '#e0e7ff', padding: '3px 8px', borderRadius: '4px' }}>
                      {unit.id}
                    </code>
                  </td>
                  <td>
                    <strong>{unit.nombre}</strong>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <strong style={{ fontSize: '0.95rem', color: '#0f172a' }}>
                      {Number(unit.factor).toFixed(2)}
                    </strong>
                  </td>
                  <td>
                    <span style={{ fontSize: '0.85rem', color: '#475569' }}>
                      1 {unit.id} = {Number(unit.factor).toFixed(0)} unidad(es) base
                    </span>
                  </td>
                  <td>
                    <div className="inline-actions" style={{ justifyContent: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-outline"
                        style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                        onClick={() => handleStartEdit(unit)}
                        title="Modificar unidad"
                      >
                        <Edit3 size={14} /> Editar
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline"
                        style={{ padding: '4px 8px', fontSize: '0.8rem', color: '#ef4444', borderColor: '#fca5a5' }}
                        onClick={() => handleDelete(unit.id)}
                        title="Eliminar unidad"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && !units.length && (
                <tr>
                  <td colSpan={5} className="empty-state">
                    No hay unidades de medida registradas. Utilice el formulario superior para añadir unidades.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Modal Edición de Unidad */}
      {editingUnit && (
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
            maxWidth: '500px',
            width: '100%',
            padding: '24px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e5e7eb', paddingBottom: '12px', marginBottom: '16px' }}>
              <div>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6366f1', textTransform: 'uppercase' }}>
                  MODIFICAR UNIDAD DE MEDIDA
                </span>
                <h2 style={{ margin: '4px 0 0 0', fontSize: '1.25rem', color: '#111827' }}>
                  Código: {editingUnit.id}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setEditingUnit(null)}
                style={{ background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer', color: '#6b7280' }}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSaveEdit}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <label className="form-group">
                  <span>Código (No editable)</span>
                  <input
                    className="input"
                    value={editingUnit.id}
                    disabled
                    readOnly
                    style={{ background: '#f8fafc', cursor: 'not-allowed', fontWeight: 600 }}
                  />
                </label>

                <label className="form-group">
                  <span>Descripción (um_Descripcion) *</span>
                  <input
                    className="input"
                    maxLength={20}
                    value={editName}
                    onChange={e => setEditName(e.target.value)}
                    required
                  />
                  <small style={{ fontSize: '11px', color: '#64748b' }}>Máximo 20 caracteres (CHAR(20))</small>
                </label>

                <label className="form-group">
                  <span>Factor de Conversión (um_FactorConversion) *</span>
                  <input
                    className="input"
                    type="number"
                    min="0.01"
                    max="99999.99"
                    step="0.01"
                    value={editFactor}
                    onChange={e => setEditFactor(e.target.value)}
                    required
                  />
                </label>
              </div>

              <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setEditingUnit(null)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                >
                  Guardar Cambios
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
