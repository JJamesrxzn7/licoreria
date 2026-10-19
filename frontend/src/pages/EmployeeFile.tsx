import React, { useState, useEffect } from 'react';
import {
  Plus, Trash2, Phone, Mail, MapPin,
  Award, Heart, AlertCircle, CheckCircle, Search, Edit3
} from 'lucide-react';
import { useGlobalStore } from '../context';
import { Employee, Dependent, CargoHistoryEntry } from '../types';
import { hrApi } from '../api';

const money = (val: number | string | undefined) =>
  `$${Number(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const RE_NAME = /^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$/;
const RE_SQLI = /(\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|EXEC|EXECUTE)\b|--|\/\*|\*\/|;|'|"|<script)/i;
const RE_EMAIL = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
const RE_MOBILE = /^09\d{8}$/;
const RE_PHONE_CONV = /^(0[2-7]\d{7}|\d{7})$/;

export const validateEcuadorianCedula = (cedula: string): boolean => {
  const clean = String(cedula || '').replace(/\D/g, '');
  if (clean.length !== 10) return false;
  const prov = parseInt(clean.slice(0, 2), 10);
  if (!((prov >= 1 && prov <= 24) || prov === 30)) return false;
  const tercer = parseInt(clean.charAt(2), 10);
  if (tercer >= 6) return false;
  const coefs = [2, 1, 2, 1, 2, 1, 2, 1, 2];
  let suma = 0;
  for (let i = 0; i < 9; i++) {
    const val = parseInt(clean.charAt(i), 10) * coefs[i];
    suma += val >= 10 ? val - 9 : val;
  }
  const verificador = (10 - (suma % 10)) % 10;
  return verificador === parseInt(clean.charAt(9), 10);
};

const now = new Date();
const maxBirthDateEmp = new Date(now.getFullYear() - 18, now.getMonth(), now.getDate()).toISOString().slice(0, 10);
const minBirthDateEmp = new Date(now.getFullYear() - 90, now.getMonth(), now.getDate()).toISOString().slice(0, 10);
const todayStr = now.toISOString().slice(0, 10);

export const EmployeeFile: React.FC = () => {
  const { state, updateState } = useGlobalStore();
  const [employees, setEmployees] = useState<Employee[]>(state.employees);
  const [departments, setDepartments] = useState<Array<{ id: string; nombre: string }>>([]);
  const [cargos, setCargos] = useState<Array<{ id: string; nombre: string }>>([]);
  
  // Selección de empleado activo
  const [selectedEmpId, setSelectedEmpId] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'personal' | 'cargos' | 'cargas'>('personal');
  const [searchFilter, setSearchFilter] = useState('');

  // Sub-listas del empleado seleccionado
  const [cargosHistory, setCargosHistory] = useState<CargoHistoryEntry[]>([]);
  const [dependents, setDependents] = useState<Dependent[]>([]);

  // Notificaciones
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Formulario de Nuevo Empleado (Modal)
  const [isNewEmpModalOpen, setIsNewEmpModalOpen] = useState(false);
  const [newEmpForm, setNewEmpForm] = useState({
    ci: '',
    nombre1: '',
    nombre2: '',
    apellido1: '',
    apellido2: '',
    sexo: 'M',
    fechaNacimiento: '1995-01-01',
    sueldo: 500,
    idDepartamento: '',
    idCargo: '',
    direccion: '',
    telefono: '',
    celular: '',
    email: '',
  });
  const [newEmpFieldErrors, setNewEmpFieldErrors] = useState<Partial<Record<keyof typeof newEmpForm, string>>>({});
  const [newEmpSubmitted, setNewEmpSubmitted] = useState(false);

  // Formulario de Edición de Datos Personales
  const [editEmpForm, setEditEmpForm] = useState({
    ci: '',
    nombre1: '',
    nombre2: '',
    apellido1: '',
    apellido2: '',
    sexo: 'M',
    fechaNacimiento: '1995-01-01',
    sueldo: 500,
    idDepartamento: '',
    direccion: '',
    telefono: '',
    celular: '',
    email: '',
  });

  // Formulario para Asignar Nuevo Cargo
  const [newCargoForm, setNewCargoForm] = useState({
    idCargo: '',
    fechaInicio: new Date().toISOString().slice(0, 10),
    fechaFin: '',
  });

  // Formulario para Nueva Carga Familiar
  const [newDependentForm, setNewDependentForm] = useState({
    ci: '',
    nombre1: '',
    nombre2: '',
    apellido1: '',
    apellido2: '',
    sexo: 'M',
    fechaNacimiento: '2015-01-01',
    parentesco: 'Hijo/a',
    estadoCivil: 'Soltero/a',
    dependencia: 'Total',
  });

  // Modal para Modificar Carga Familiar
  const [editingDependent, setEditingDependent] = useState<Dependent | null>(null);
  const [editDependentForm, setEditDependentForm] = useState({
    ci: '',
    nombre1: '',
    nombre2: '',
    apellido1: '',
    apellido2: '',
    sexo: 'M',
    fechaNacimiento: '2015-01-01',
    parentesco: 'Hijo/a',
    estadoCivil: 'Soltero/a',
    dependencia: 'Total',
  });

  // Cargar datos iniciales
  const loadInitialData = async () => {
    try {
      const [remoteEmps, remoteDepts, remoteCargos] = await Promise.all([
        hrApi.listEmployees().catch(() => null),
        hrApi.listDepartments().catch(() => null),
        hrApi.listCargos().catch(() => null),
      ]);

      if (Array.isArray(remoteDepts) && remoteDepts.length) {
        setDepartments(remoteDepts);
        if (!newEmpForm.idDepartamento) setNewEmpForm(prev => ({ ...prev, idDepartamento: remoteDepts[0].id }));
      }
      if (Array.isArray(remoteCargos) && remoteCargos.length) {
        setCargos(remoteCargos);
        if (!newEmpForm.idCargo) {
          setNewEmpForm(prev => ({ ...prev, idCargo: remoteCargos[0].id }));
          setNewCargoForm(prev => ({ ...prev, idCargo: remoteCargos[0].id }));
        }
      }
      if (Array.isArray(remoteEmps) && remoteEmps.length) {
        setEmployees(remoteEmps);
        updateState(draft => {
          draft.employees = remoteEmps;
          return draft;
        });
        if (!selectedEmpId) {
          setSelectedEmpId(remoteEmps[0].id);
        }
      } else if (state.employees.length && !selectedEmpId) {
        setSelectedEmpId(state.employees[0].id);
      }
    } catch {
      // Usar estado local de fallback
    }
  };

  useEffect(() => {
    void loadInitialData();
  }, []);

  // Empleado actualmente seleccionado
  const selectedEmployee = employees.find(e => e.id === selectedEmpId) || employees[0];

  // Sincronizar formulario de edición al cambiar de empleado seleccionado
  useEffect(() => {
    if (selectedEmployee) {
      setEditEmpForm({
        ci: selectedEmployee.ci || '',
        nombre1: selectedEmployee.nombre1 || selectedEmployee.name.split(' ')[0] || '',
        nombre2: selectedEmployee.nombre2 || '',
        apellido1: selectedEmployee.apellido1 || selectedEmployee.name.split(' ')[1] || '',
        apellido2: selectedEmployee.apellido2 || '',
        sexo: selectedEmployee.gender || 'M',
        fechaNacimiento: selectedEmployee.birthDate ? String(selectedEmployee.birthDate).slice(0, 10) : '1995-01-01',
        sueldo: Number(selectedEmployee.salary || 500),
        idDepartamento: selectedEmployee.departmentId || departments[0]?.id || 'DEP-TEST',
        direccion: selectedEmployee.address || '',
        telefono: selectedEmployee.phone || '',
        celular: selectedEmployee.mobile || '',
        email: selectedEmployee.email || '',
      });

      // Cargar cargos y cargas del empleado seleccionado
      void loadEmployeeDetails(selectedEmployee.id);
    }
  }, [selectedEmpId, employees]);

  const loadEmployeeDetails = async (empId: string) => {
    try {
      const [hist, deps] = await Promise.all([
        hrApi.listCargosHistory(empId).catch(() => []),
        hrApi.listDependents(empId).catch(() => []),
      ]);
      setCargosHistory(hist);
      setDependents(deps);
    } catch {
      setCargosHistory([]);
      setDependents([]);
    }
  };

  const validateEmployeeData = (form: {
    ci: string;
    nombre1: string;
    nombre2?: string;
    apellido1: string;
    apellido2?: string;
    sueldo: number;
    fechaNacimiento: string;
    direccion: string;
    telefono?: string;
    celular?: string;
    email?: string;
  }): string | null => {
    const ciClean = form.ci.replace(/\D/g, '');
    if (!validateEcuadorianCedula(ciClean)) {
      return 'La cédula ingresada no es válida según el algoritmo de verificación de Ecuador (10 dígitos).';
    }
    if (!form.nombre1.trim() || !form.apellido1.trim()) {
      return 'Primer nombre y primer apellido son requeridos.';
    }
    if (!RE_NAME.test(form.nombre1.trim()) || RE_SQLI.test(form.nombre1.trim())) {
      return 'El primer nombre solo puede contener letras y espacios, sin números ni sentencias SQL.';
    }
    if (form.nombre2 && form.nombre2.trim() && (!RE_NAME.test(form.nombre2.trim()) || RE_SQLI.test(form.nombre2.trim()))) {
      return 'El segundo nombre solo puede contener letras y espacios.';
    }
    if (!RE_NAME.test(form.apellido1.trim()) || RE_SQLI.test(form.apellido1.trim())) {
      return 'El primer apellido solo puede contener letras y espacios, sin números ni sentencias SQL.';
    }
    if (form.apellido2 && form.apellido2.trim() && (!RE_NAME.test(form.apellido2.trim()) || RE_SQLI.test(form.apellido2.trim()))) {
      return 'El segundo apellido solo puede contener letras y espacios.';
    }
    if (Number(form.sueldo) < 460) {
      return 'El sueldo base no puede ser inferior al Salario Básico Unificado vigente ($460.00 USD).';
    }
    if (form.fechaNacimiento > maxBirthDateEmp) {
      return 'El colaborador debe ser mayor de edad (al menos 18 años).';
    }
    if (form.fechaNacimiento < minBirthDateEmp) {
      return 'La fecha de nacimiento del colaborador no es válida (edad supera 90 años).';
    }
    if (!form.direccion.trim() || form.direccion.trim().length < 5) {
      return 'La dirección domiciliaria debe tener al menos 5 caracteres (emp_Direccion).';
    }
    if (RE_SQLI.test(form.direccion.trim())) {
      return 'La dirección contiene caracteres o sentencias no permitidas (protección SQL Injection).';
    }
    if (form.celular && form.celular.trim()) {
      const celClean = form.celular.replace(/\D/g, '');
      if (!RE_MOBILE.test(celClean)) {
        return 'El celular debe tener 10 dígitos y comenzar con 09 (ej. 0991234567).';
      }
    }
    if (form.telefono && form.telefono.trim()) {
      const telClean = form.telefono.replace(/\D/g, '');
      if (!RE_PHONE_CONV.test(telClean)) {
        return 'El teléfono convencional debe tener 7 dígitos o 9 dígitos iniciando con código de provincia (ej. 022345678).';
      }
    }
    if (form.email && form.email.trim()) {
      if (!RE_EMAIL.test(form.email.trim().toLowerCase()) || RE_SQLI.test(form.email.trim())) {
        return 'El formato de correo electrónico es inválido (ej. usuario@dominio.com).';
      }
    }
    return null;
  };

  const validateNewEmployeeFields = (form: typeof newEmpForm): Partial<Record<keyof typeof newEmpForm, string>> => {
    const errors: Partial<Record<keyof typeof newEmpForm, string>> = {};
    const setFieldError = (field: keyof typeof newEmpForm, message: string) => {
      if (message) errors[field] = message;
    };
    const validateName = (value: string, required: boolean, label: string) => {
      const clean = value.trim();
      if (required && clean.length < 2) return `${label} debe tener al menos 2 caracteres.`;
      if (clean.length > 30) return `${label} no puede superar 30 caracteres.`;
      if (clean && (!RE_NAME.test(clean) || RE_SQLI.test(clean))) return `${label} solo puede contener letras, espacios, puntos o guiones.`;
      return '';
    };

    setFieldError('ci', validateEcuadorianCedula(form.ci)
      ? ''
      : 'Ingresa una cédula ecuatoriana válida de 10 dígitos.');
    setFieldError('nombre1', validateName(form.nombre1, true, 'El primer nombre'));
    setFieldError('nombre2', validateName(form.nombre2, false, 'El segundo nombre'));
    setFieldError('apellido1', validateName(form.apellido1, true, 'El primer apellido'));
    setFieldError('apellido2', validateName(form.apellido2, false, 'El segundo apellido'));

    const salary = Number(form.sueldo);
    setFieldError('sueldo', !Number.isFinite(salary) || salary < 460
      ? 'El sueldo debe ser al menos $460.'
      : salary > 50000 ? 'El sueldo no puede superar $50.000.' : '');
    setFieldError('sexo', ['M', 'F'].includes(form.sexo) ? '' : 'Selecciona una opción.');
    setFieldError('fechaNacimiento', !form.fechaNacimiento
      ? 'Ingresa la fecha de nacimiento.'
      : form.fechaNacimiento > maxBirthDateEmp
        ? 'El empleado debe tener al menos 18 años.'
        : form.fechaNacimiento < minBirthDateEmp ? 'La edad no puede superar 90 años.' : '');
    setFieldError('idDepartamento', departments.some(department => department.id === form.idDepartamento)
      ? '' : 'Selecciona un departamento disponible.');
    setFieldError('idCargo', cargos.some(cargo => cargo.id === form.idCargo)
      ? '' : 'Selecciona un cargo inicial disponible.');
    setFieldError('direccion', form.direccion.trim().length < 5
      ? 'La dirección debe tener al menos 5 caracteres.'
      : form.direccion.trim().length > 60
        ? 'La dirección no puede superar 60 caracteres.'
        : RE_SQLI.test(form.direccion.trim()) ? 'Revisa los caracteres ingresados en la dirección.' : '');
    setFieldError('telefono', form.telefono && !RE_PHONE_CONV.test(form.telefono.replace(/\D/g, ''))
      ? 'Usa 7 dígitos o 9 incluyendo el código de provincia.' : '');
    setFieldError('celular', form.celular && !RE_MOBILE.test(form.celular.replace(/\D/g, ''))
      ? 'Usa 10 dígitos y comienza con 09.' : '');
    setFieldError('email', form.email && (!RE_EMAIL.test(form.email.trim().toLowerCase()) || form.email.length > 60 || RE_SQLI.test(form.email))
      ? 'Ingresa un correo válido de hasta 60 caracteres.' : '');
    return errors;
  };

  const updateNewEmployeeField = <K extends keyof typeof newEmpForm>(
    field: K,
    value: (typeof newEmpForm)[K],
  ) => {
    const nextForm = { ...newEmpForm, [field]: value };
    setNewEmpForm(nextForm);
    if (newEmpSubmitted) {
      setNewEmpFieldErrors(validateNewEmployeeFields(nextForm));
    }
  };

  const validateDependentData = (form: {
    ci: string;
    nombre1: string;
    nombre2?: string;
    apellido1: string;
    apellido2?: string;
    fechaNacimiento: string;
  }): string | null => {
    const ciClean = form.ci.replace(/\D/g, '');
    if (!validateEcuadorianCedula(ciClean)) {
      return 'La cédula de la carga familiar no es válida según el algoritmo de Ecuador (10 dígitos).';
    }
    if (!form.nombre1.trim() || !form.apellido1.trim()) {
      return 'Primer nombre y primer apellido de la carga familiar son obligatorios.';
    }
    if (!RE_NAME.test(form.nombre1.trim()) || RE_SQLI.test(form.nombre1.trim())) {
      return 'El primer nombre de la carga familiar solo puede contener letras y espacios.';
    }
    if (form.nombre2 && form.nombre2.trim() && (!RE_NAME.test(form.nombre2.trim()) || RE_SQLI.test(form.nombre2.trim()))) {
      return 'El segundo nombre de la carga familiar solo puede contener letras y espacios.';
    }
    if (!RE_NAME.test(form.apellido1.trim()) || RE_SQLI.test(form.apellido1.trim())) {
      return 'El primer apellido de la carga familiar solo puede contener letras y espacios.';
    }
    if (form.apellido2 && form.apellido2.trim() && (!RE_NAME.test(form.apellido2.trim()) || RE_SQLI.test(form.apellido2.trim()))) {
      return 'El segundo apellido de la carga familiar solo puede contener letras y espacios.';
    }
    if (form.fechaNacimiento > todayStr) {
      return 'La fecha de nacimiento de la carga familiar no puede ser en el futuro.';
    }
    return null;
  };

  // Crear nuevo empleado
  const handleCreateEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    setNewEmpSubmitted(true);
    const errors = validateNewEmployeeFields(newEmpForm);
    setNewEmpFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      const firstInvalid = Object.keys(errors)[0];
      document.getElementById(`new-employee-${firstInvalid}`)?.focus();
      setNotice({ type: 'error', message: 'Corrige los campos marcados en el formulario para continuar.' });
      return;
    }
    const ciClean = newEmpForm.ci.replace(/\D/g, '').slice(0, 10);

    try {
      const res = await hrApi.createEmployee({
        ci: ciClean,
        nombre1: newEmpForm.nombre1.trim(),
        nombre2: newEmpForm.nombre2.trim() || undefined,
        apellido1: newEmpForm.apellido1.trim(),
        apellido2: newEmpForm.apellido2.trim() || undefined,
        sexo: newEmpForm.sexo,
        fechaNacimiento: newEmpForm.fechaNacimiento,
        sueldo: Number(newEmpForm.sueldo),
        idDepartamento: newEmpForm.idDepartamento || departments[0]?.id || 'DEP-TEST',
        idCargo: newEmpForm.idCargo || cargos[0]?.id || 'CGO-000001',
        direccion: newEmpForm.direccion.trim(),
        telefono: newEmpForm.telefono.replace(/\D/g, '') || undefined,
        celular: newEmpForm.celular.replace(/\D/g, '') || undefined,
        email: newEmpForm.email.trim() || undefined,
      });

      setNotice({ type: 'success', message: res.mensaje || 'Empleado registrado con éxito.' });
      setIsNewEmpModalOpen(false);
      void loadInitialData();
      if (res.id) setSelectedEmpId(res.id);
    } catch (err: any) {
      const message = typeof err?.message === 'string' ? err.message : '';
      setNotice({
        type: 'error',
        message: /database|sql|mysql|maria|traceback|constraint|table|column/i.test(message)
          ? 'No se pudo registrar al colaborador. Revisa los datos e inténtalo nuevamente.'
          : message || 'No se pudo registrar al colaborador. Revisa los datos e inténtalo nuevamente.',
      });
    }
  };

  // Actualizar datos del empleado seleccionado
  const handleUpdateEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEmployee) return;

    const errorMsg = validateEmployeeData(editEmpForm);
    if (errorMsg) {
      setNotice({ type: 'error', message: errorMsg });
      return;
    }

    try {
      const res = await hrApi.updateEmployee(selectedEmployee.id, {
        ci: editEmpForm.ci.replace(/\D/g, '').slice(0, 10),
        nombre1: editEmpForm.nombre1.trim(),
        nombre2: editEmpForm.nombre2.trim() || undefined,
        apellido1: editEmpForm.apellido1.trim(),
        apellido2: editEmpForm.apellido2.trim() || undefined,
        sexo: editEmpForm.sexo,
        fechaNacimiento: editEmpForm.fechaNacimiento,
        sueldo: Number(editEmpForm.sueldo),
        idDepartamento: editEmpForm.idDepartamento,
        direccion: editEmpForm.direccion.trim(),
        telefono: editEmpForm.telefono.replace(/\D/g, '') || undefined,
        celular: editEmpForm.celular.replace(/\D/g, '') || undefined,
        email: editEmpForm.email.trim() || undefined,
      });

      setNotice({ type: 'success', message: res.mensaje || 'Ficha actualizada exitosamente.' });
      void loadInitialData();
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Error al actualizar los datos del empleado.' });
    }
  };

  // Asignar nuevo cargo (Crecimiento Empresarial)
  const handleAssignCargo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEmployee || !newCargoForm.idCargo) return;

    if (newCargoForm.fechaFin && newCargoForm.fechaFin < newCargoForm.fechaInicio) {
      setNotice({ type: 'error', message: 'La fecha de fin del cargo no puede ser anterior a la fecha de inicio.' });
      return;
    }

    try {
      const res = await hrApi.assignCargo(selectedEmployee.id, {
        idCargo: newCargoForm.idCargo,
        fechaInicio: newCargoForm.fechaInicio,
        fechaFin: newCargoForm.fechaFin ? newCargoForm.fechaFin : null,
      });

      setNotice({ type: 'success', message: res.mensaje || 'Cargo asignado exitosamente al historial.' });
      void loadEmployeeDetails(selectedEmployee.id);
      void loadInitialData();
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Error al asignar el cargo.' });
    }
  };

  // Registrar nueva carga familiar
  const handleAddDependent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEmployee) return;

    const errorMsg = validateDependentData(newDependentForm);
    if (errorMsg) {
      setNotice({ type: 'error', message: errorMsg });
      return;
    }

    const ciClean = newDependentForm.ci.replace(/\D/g, '').slice(0, 10);

    try {
      const res = await hrApi.createDependent(selectedEmployee.id, {
        ci: ciClean,
        nombre1: newDependentForm.nombre1.trim(),
        nombre2: newDependentForm.nombre2.trim() || undefined,
        apellido1: newDependentForm.apellido1.trim(),
        apellido2: newDependentForm.apellido2.trim() || undefined,
        sexo: newDependentForm.sexo,
        fechaNacimiento: newDependentForm.fechaNacimiento,
        parentesco: newDependentForm.parentesco,
        estadoCivil: newDependentForm.estadoCivil,
        dependencia: newDependentForm.dependencia,
      });

      setNotice({ type: 'success', message: res.mensaje || 'Carga familiar registrada exitosamente.' });
      setNewDependentForm({
        ci: '',
        nombre1: '',
        nombre2: '',
        apellido1: '',
        apellido2: '',
        sexo: 'M',
        fechaNacimiento: '2015-01-01',
        parentesco: 'Hijo/a',
        estadoCivil: 'Soltero/a',
        dependencia: 'Total',
      });
      void loadEmployeeDetails(selectedEmployee.id);
      void loadInitialData();
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Error al registrar la carga familiar.' });
    }
  };

  // Abrir modal de edición de carga
  const startEditDependent = (dep: Dependent) => {
    setEditingDependent(dep);
    setEditDependentForm({
      ci: dep.ci || '',
      nombre1: dep.nombre1 || (dep.name ? dep.name.split(' ')[0] : ''),
      nombre2: dep.nombre2 || '',
      apellido1: dep.apellido1 || (dep.name ? dep.name.split(' ')[1] || '' : ''),
      apellido2: dep.apellido2 || '',
      sexo: dep.sexo || 'M',
      fechaNacimiento: dep.fechaNacimiento ? String(dep.fechaNacimiento).slice(0, 10) : '2015-01-01',
      parentesco: dep.parentesco || 'Hijo/a',
      estadoCivil: dep.estadoCivil || 'Soltero/a',
      dependencia: dep.dependencia || 'Total',
    });
  };

  // Guardar modificación de carga familiar
  const handleUpdateDependent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEmployee || !editingDependent?.id) return;

    const errorMsg = validateDependentData(editDependentForm);
    if (errorMsg) {
      setNotice({ type: 'error', message: errorMsg });
      return;
    }

    const ciClean = editDependentForm.ci.replace(/\D/g, '').slice(0, 10);

    try {
      const res = await hrApi.updateDependent(selectedEmployee.id, editingDependent.id, {
        ci: ciClean,
        nombre1: editDependentForm.nombre1.trim(),
        nombre2: editDependentForm.nombre2.trim() || undefined,
        apellido1: editDependentForm.apellido1.trim(),
        apellido2: editDependentForm.apellido2.trim() || undefined,
        sexo: editDependentForm.sexo,
        fechaNacimiento: editDependentForm.fechaNacimiento,
        parentesco: editDependentForm.parentesco,
        estadoCivil: editDependentForm.estadoCivil,
        dependencia: editDependentForm.dependencia,
      });

      setNotice({ type: 'success', message: res.mensaje || 'Carga familiar actualizada exitosamente.' });
      setEditingDependent(null);
      void loadEmployeeDetails(selectedEmployee.id);
      void loadInitialData();
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Error al actualizar los datos de la carga familiar.' });
    }
  };

  // Eliminar carga familiar
  const handleDeleteDependent = async (cargaId: string) => {
    if (!selectedEmployee) return;
    if (!window.confirm('¿Confirmas que deseas eliminar esta carga familiar del registro?')) return;

    try {
      await hrApi.deleteDependent(selectedEmployee.id, cargaId);
      setNotice({ type: 'success', message: 'Carga familiar eliminada del expediente.' });
      void loadEmployeeDetails(selectedEmployee.id);
      void loadInitialData();
    } catch (err: any) {
      setNotice({ type: 'error', message: err?.message || 'Error al eliminar la carga familiar.' });
    }
  };

  const filteredEmployees = employees.filter(emp =>
    emp.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
    emp.ci.includes(searchFilter) ||
    emp.department.toLowerCase().includes(searchFilter.toLowerCase()) ||
    emp.role.toLowerCase().includes(searchFilter.toLowerCase())
  );

  return (
    <div>
      {/* Encabezado */}
      <div className="page-heading">
        <div>
          <span className="eyebrow">TALENTO HUMANO Y GESTIÓN DE PERSONAL</span>
          <h1>Ficha del Empleado</h1>
          <p>Expediente integral con datos personales, dirección, historial de cargos y registro detallado de cargas familiares.</p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            setNewEmpFieldErrors({});
            setNewEmpSubmitted(false);
            setNotice(null);
            setIsNewEmpModalOpen(true);
          }}
        >
          <Plus size={16} /> + Nuevo Colaborador
        </button>
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

      {/* Grid Principal: Lista a la izquierda, Ficha Detallada a la derecha */}
      <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '24px', alignItems: 'start' }}>
        
        {/* Columna Izquierda: Directorio de Empleados */}
        <section className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 className="section-title" style={{ margin: 0, fontSize: '1.05rem' }}>Personal ({employees.length})</h2>
            <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>Tabla EMPLEADOS</span>
          </div>

          <div style={{ position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: '10px', top: '10px', color: '#9ca3af' }} />
            <input
              className="input"
              style={{ paddingLeft: '32px' }}
              placeholder="Buscar por nombre, CI, cargo..."
              value={searchFilter}
              onChange={e => setSearchFilter(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '600px', overflowY: 'auto' }}>
            {filteredEmployees.map(emp => {
              const isSelected = emp.id === selectedEmployee?.id;
              return (
                <div
                  key={emp.id}
                  onClick={() => setSelectedEmpId(emp.id)}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    border: isSelected ? '2px solid #6366f1' : '1px solid #e5e7eb',
                    backgroundColor: isSelected ? '#f5f3ff' : '#ffffff',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <strong style={{ fontSize: '0.95rem', color: '#111827' }}>{emp.name}</strong>
                    <span className={`badge badge-${emp.status === 'ACTIVE' ? 'APR' : 'ANU'}`} style={{ fontSize: '0.7rem' }}>
                      {emp.status === 'ACTIVE' ? 'ACT' : 'INA'}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '4px' }}>
                    CI: <strong>{emp.ci}</strong> · {emp.department}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px', fontSize: '0.8rem' }}>
                    <span style={{ color: '#4f46e5', fontWeight: 500 }}>{emp.role}</span>
                    <span style={{ color: '#059669', fontWeight: 600 }}>{money(emp.salary)}</span>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '4px' }}>
                    Cargas familiares: {emp.familyDependents}
                  </div>
                </div>
              );
            })}
            {!filteredEmployees.length && (
              <div style={{ textAlign: 'center', padding: '24px', color: '#9ca3af' }}>
                No se encontraron colaboradores coincidentes.
              </div>
            )}
          </div>
        </section>

        {/* Columna Derecha: Expediente del Empleado Seleccionado */}
        {selectedEmployee ? (
          <section className="card" style={{ padding: '20px' }}>
            {/* Header del expediente */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e5e7eb', paddingBottom: '14px', marginBottom: '16px' }}>
              <div>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.05em', color: '#6366f1', textTransform: 'uppercase' }}>
                  EXPEDIENTE: {selectedEmployee.id}
                </span>
                <h2 style={{ margin: '4px 0 0 0', fontSize: '1.4rem', color: '#111827' }}>{selectedEmployee.name}</h2>
                <div style={{ fontSize: '0.85rem', color: '#6b7280', marginTop: '2px' }}>
                  Cédula: <strong>{selectedEmployee.ci}</strong> · Departamento: <strong>{selectedEmployee.department}</strong> · Cargo Actual: <strong>{selectedEmployee.role}</strong>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>Sueldo Nominal</span>
                <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#059669' }}>{money(selectedEmployee.salary)}</div>
              </div>
            </div>

            {/* Pestañas de navegación de la Ficha */}
            <div style={{ display: 'flex', gap: '8px', borderBottom: '2px solid #f3f4f6', marginBottom: '20px' }}>
              <button
                type="button"
                onClick={() => setActiveTab('personal')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  borderBottom: activeTab === 'personal' ? '3px solid #6366f1' : '3px solid transparent',
                  color: activeTab === 'personal' ? '#4f46e5' : '#6b7280',
                  marginBottom: '-2px',
                }}
              >
                <Edit3 size={16} /> Datos Personales y Contacto
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('cargos')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  borderBottom: activeTab === 'cargos' ? '3px solid #6366f1' : '3px solid transparent',
                  color: activeTab === 'cargos' ? '#4f46e5' : '#6b7280',
                  marginBottom: '-2px',
                }}
              >
                <Award size={16} /> Historial de Cargos ({cargosHistory.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('cargas')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  borderBottom: activeTab === 'cargas' ? '3px solid #6366f1' : '3px solid transparent',
                  color: activeTab === 'cargas' ? '#4f46e5' : '#6b7280',
                  marginBottom: '-2px',
                }}
              >
                <Heart size={16} /> Cargas Familiares ({dependents.length})
              </button>
            </div>

            {/* TAB 1: DATOS PERSONALES */}
            {activeTab === 'personal' && (
              <form onSubmit={handleUpdateEmployee}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px' }}>
                  <label className="form-group">
                    Cédula Identidad (10 dígitos) *
                    <input
                      className="input"
                      maxLength={10}
                      pattern="^\d{10}$"
                      title="Cédula ecuatoriana válida de 10 dígitos"
                      value={editEmpForm.ci}
                      onChange={e => setEditEmpForm({ ...editEmpForm, ci: e.target.value.replace(/\D/g, '').slice(0, 10) })}
                      required
                    />
                    {editEmpForm.ci.length === 10 && (
                      <span style={{ fontSize: '0.75rem', marginTop: '2px', color: validateEcuadorianCedula(editEmpForm.ci) ? '#059669' : '#dc2626' }}>
                        {validateEcuadorianCedula(editEmpForm.ci) ? '✓ Cédula válida' : '✗ Cédula no válida en Ecuador'}
                      </span>
                    )}
                  </label>
                  <label className="form-group">
                    Primer Nombre *
                    <input
                      className="input"
                      maxLength={30}
                      pattern="^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$"
                      title="Solo letras y espacios (máximo 30 caracteres)"
                      value={editEmpForm.nombre1}
                      onChange={e => setEditEmpForm({ ...editEmpForm, nombre1: e.target.value })}
                      required
                    />
                  </label>
                  <label className="form-group">
                    Segundo Nombre
                    <input
                      className="input"
                      maxLength={30}
                      pattern="^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$"
                      title="Solo letras y espacios (máximo 30 caracteres)"
                      value={editEmpForm.nombre2}
                      onChange={e => setEditEmpForm({ ...editEmpForm, nombre2: e.target.value })}
                    />
                  </label>
                  <label className="form-group">
                    Primer Apellido *
                    <input
                      className="input"
                      maxLength={30}
                      pattern="^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$"
                      title="Solo letras y espacios (máximo 30 caracteres)"
                      value={editEmpForm.apellido1}
                      onChange={e => setEditEmpForm({ ...editEmpForm, apellido1: e.target.value })}
                      required
                    />
                  </label>
                  <label className="form-group">
                    Segundo Apellido
                    <input
                      className="input"
                      maxLength={30}
                      pattern="^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$"
                      title="Solo letras y espacios (máximo 30 caracteres)"
                      value={editEmpForm.apellido2}
                      onChange={e => setEditEmpForm({ ...editEmpForm, apellido2: e.target.value })}
                    />
                  </label>
                  <label className="form-group">
                    Sexo *
                    <select
                      id="new-employee-idDepartamento"
                      className="select"
                      value={editEmpForm.sexo}
                      onChange={e => setEditEmpForm({ ...editEmpForm, sexo: e.target.value })}
                    >
                      <option value="">-- Seleccione sexo --</option>
                      <option value="M">Masculino (M)</option>
                      <option value="F">Femenino (F)</option>
                      <option value="H">Hombre / Otro (H)</option>
                    </select>
                  </label>
                  <label className="form-group">
                    Fecha de Nacimiento *
                    <input
                      className="input"
                      type="date"
                      max={maxBirthDateEmp}
                      min={minBirthDateEmp}
                      title="El colaborador debe tener al menos 18 años"
                      value={editEmpForm.fechaNacimiento}
                      onChange={e => setEditEmpForm({ ...editEmpForm, fechaNacimiento: e.target.value })}
                      required
                    />
                  </label>
                  <label className="form-group">
                    Sueldo Base ($) *
                    <input
                      className="input"
                      type="number"
                      min="460"
                      step="0.01"
                      title="Sueldo base mínimo: $460.00 (SBU)"
                      value={editEmpForm.sueldo}
                      onChange={e => setEditEmpForm({ ...editEmpForm, sueldo: Number(e.target.value) })}
                      required
                    />
                  </label>
                  <label className="form-group">
                    Departamento *
                    <select
                      id="new-employee-idCargo"
                      className="select"
                      value={editEmpForm.idDepartamento}
                      onChange={e => setEditEmpForm({ ...editEmpForm, idDepartamento: e.target.value })}
                    >
                      <option value="">-- Seleccione un departamento --</option>
                      {departments.map(d => (
                        <option key={d.id} value={d.id}>{d.nombre} ({d.id})</option>
                      ))}
                    </select>
                  </label>
                  
                  {/* Dirección requerida; teléfono convencional opcional */}
                  <label className="form-group" style={{ gridColumn: 'span 2' }}>
                    Dirección Física Domiciliaria (emp_Direccion) *
                    <div style={{ position: 'relative' }}>
                      <MapPin size={16} style={{ position: 'absolute', left: '10px', top: '10px', color: '#9ca3af' }} />
                      <input
                        className="input"
                        style={{ paddingLeft: '32px' }}
                        maxLength={60}
                        placeholder="Ej: Av. Amazonas N24-50 y Colón, Quito"
                        value={editEmpForm.direccion}
                        onChange={e => setEditEmpForm({ ...editEmpForm, direccion: e.target.value })}
                        required
                      />
                    </div>
                  </label>
                  <label className="form-group">
                    Teléfono convencional (opcional)
                    <div style={{ position: 'relative' }}>
                      <Phone size={16} style={{ position: 'absolute', left: '10px', top: '10px', color: '#9ca3af' }} />
                      <input
                        className="input"
                        style={{ paddingLeft: '32px' }}
                        maxLength={9}
                        placeholder="Ej: 022500123"
                        title="Teléfono convencional de 7 o 9 dígitos (ej. 022500123)"
                        value={editEmpForm.telefono}
                        onChange={e => setEditEmpForm({ ...editEmpForm, telefono: e.target.value.replace(/\D/g, '').slice(0, 9) })}
                      />
                    </div>
                  </label>
                  <label className="form-group">
                    Teléfono Celular Móvil (emp_Celular)
                    <input
                      className="input"
                      maxLength={10}
                      placeholder="Ej: 0991234567"
                      pattern="^09\d{8}$"
                      title="Celular de 10 dígitos comenzando con 09"
                      value={editEmpForm.celular}
                      onChange={e => setEditEmpForm({ ...editEmpForm, celular: e.target.value.replace(/\D/g, '').slice(0, 10) })}
                    />
                  </label>
                  <label className="form-group" style={{ gridColumn: 'span 2' }}>
                    Correo Electrónico (emp_Mail)
                    <div style={{ position: 'relative' }}>
                      <Mail size={16} style={{ position: 'absolute', left: '10px', top: '10px', color: '#9ca3af' }} />
                      <input
                        className="input"
                        style={{ paddingLeft: '32px' }}
                        type="email"
                        maxLength={60}
                        placeholder="empleado@cava.com"
                        value={editEmpForm.email}
                        onChange={e => setEditEmpForm({ ...editEmpForm, email: e.target.value })}
                      />
                    </div>
                  </label>
                </div>
                <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
                  <button type="submit" className="btn btn-primary">
                    Guardar Cambios de la Ficha
                  </button>
                </div>
              </form>
            )}

            {/* TAB 2: HISTORIAL DE CARGOS */}
            {activeTab === 'cargos' && (
              <div>
                <div style={{ marginBottom: '16px', background: '#f9fafb', padding: '16px', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
                  <h3 style={{ margin: '0 0 10px 0', fontSize: '1rem', color: '#374151' }}>Promover o Asignar Nuevo Cargo (CARGOSxEMPLEADO)</h3>
                  <form onSubmit={handleAssignCargo} style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr) auto', gap: '12px', alignItems: 'flex-end' }}>
                    <label className="form-group" style={{ margin: 0 }}>
                      Nuevo Cargo / Puesto *
                      <select
                        className="select"
                        value={newCargoForm.idCargo}
                        onChange={e => setNewCargoForm({ ...newCargoForm, idCargo: e.target.value })}
                        required
                      >
                        <option value="">-- Seleccione un cargo / puesto --</option>
                        {cargos.map(c => (
                          <option key={c.id} value={c.id}>{c.nombre} ({c.id})</option>
                        ))}
                      </select>
                    </label>
                    <label className="form-group" style={{ margin: 0 }}>
                      Fecha de Inicio (cxe_Fecha_Inicio) *
                      <input
                        className="input"
                        type="date"
                        value={newCargoForm.fechaInicio}
                        onChange={e => setNewCargoForm({ ...newCargoForm, fechaInicio: e.target.value })}
                        required
                      />
                    </label>
                    <label className="form-group" style={{ margin: 0 }}>
                      Fecha Fin (Opcional)
                      <input
                        className="input"
                        type="date"
                        value={newCargoForm.fechaFin}
                        onChange={e => setNewCargoForm({ ...newCargoForm, fechaFin: e.target.value })}
                      />
                    </label>
                    <button type="submit" className="btn btn-primary" style={{ height: '38px' }}>
                      <Plus size={16} /> Asignar Cargo
                    </button>
                  </form>
                </div>

                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Cargo Asignado</th>
                        <th>Código Cargo</th>
                        <th>Fecha de Inicio</th>
                        <th>Fecha de Fin</th>
                        <th>Condición</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cargosHistory.map((ch, idx) => (
                        <tr key={idx}>
                          <td><strong>{ch.cargoNombre}</strong></td>
                          <td><code>{ch.cargoId}</code></td>
                          <td>{String(ch.fechaInicio).slice(0, 10)}</td>
                          <td>{ch.fechaFin ? String(ch.fechaFin).slice(0, 10) : <span style={{ color: '#059669', fontWeight: 600 }}>Cargo Actual</span>}</td>
                          <td>{!ch.fechaFin ? 'Vigente' : 'Posición anterior'}</td>
                          <td><span className={`badge badge-${ch.estado === 'ACT' ? 'APR' : 'ANU'}`}>{ch.estado}</span></td>
                        </tr>
                      ))}
                      {!cargosHistory.length && (
                        <tr>
                          <td colSpan={6} className="empty-state">No se registran ascensos o cambios de cargo en la tabla CARGOSxEMPLEADO.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB 3: CARGAS FAMILIARES */}
            {activeTab === 'cargas' && (
              <div>
                {/* Formulario de registro de carga */}
                <div style={{ marginBottom: '20px', background: '#f9fafb', padding: '16px', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
                  <h3 style={{ margin: '0 0 12px 0', fontSize: '1rem', color: '#374151' }}>Registrar Dependiente / Familiar (CARGAS)</h3>
                  <form onSubmit={handleAddDependent}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                      <label className="form-group">
                        Cédula Carga (10 dígitos) *
                        <input
                          className="input"
                          maxLength={10}
                          pattern="^\d{10}$"
                          title="Cédula ecuatoriana válida de 10 dígitos"
                          placeholder="1722334455"
                          value={newDependentForm.ci}
                          onChange={e => setNewDependentForm({ ...newDependentForm, ci: e.target.value.replace(/\D/g, '').slice(0, 10) })}
                          required
                        />
                        {newDependentForm.ci.length === 10 && (
                          <span style={{ fontSize: '0.75rem', marginTop: '2px', color: validateEcuadorianCedula(newDependentForm.ci) ? '#059669' : '#dc2626' }}>
                            {validateEcuadorianCedula(newDependentForm.ci) ? '✓ Cédula válida' : '✗ Cédula no válida en Ecuador'}
                          </span>
                        )}
                      </label>
                      <label className="form-group">
                        Primer Nombre *
                        <input
                          className="input"
                          maxLength={30}
                          pattern="^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$"
                          title="Solo letras y espacios (máximo 30 caracteres)"
                          placeholder="Ej: Sofía"
                          value={newDependentForm.nombre1}
                          onChange={e => setNewDependentForm({ ...newDependentForm, nombre1: e.target.value })}
                          required
                        />
                      </label>
                      <label className="form-group">
                        Segundo Nombre
                        <input
                          className="input"
                          maxLength={30}
                          pattern="^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$"
                          title="Solo letras y espacios (máximo 30 caracteres)"
                          placeholder="Ej: Isabel"
                          value={newDependentForm.nombre2}
                          onChange={e => setNewDependentForm({ ...newDependentForm, nombre2: e.target.value })}
                        />
                      </label>
                      <label className="form-group">
                        Primer Apellido *
                        <input
                          className="input"
                          maxLength={30}
                          pattern="^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$"
                          title="Solo letras y espacios (máximo 30 caracteres)"
                          placeholder="Ej: Mendoza"
                          value={newDependentForm.apellido1}
                          onChange={e => setNewDependentForm({ ...newDependentForm, apellido1: e.target.value })}
                          required
                        />
                      </label>
                      <label className="form-group">
                        Segundo Apellido
                        <input
                          className="input"
                          maxLength={30}
                          pattern="^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s\.\-']+$"
                          title="Solo letras y espacios (máximo 30 caracteres)"
                          placeholder="Ej: Paredes"
                          value={newDependentForm.apellido2}
                          onChange={e => setNewDependentForm({ ...newDependentForm, apellido2: e.target.value })}
                        />
                      </label>
                      <label className="form-group">
                        Sexo *
                        <select
                          className="select"
                          value={newDependentForm.sexo}
                          onChange={e => setNewDependentForm({ ...newDependentForm, sexo: e.target.value })}
                          required
                        >
                          <option value="">-- Seleccione sexo --</option>
                          <option value="M">Masculino (M)</option>
                          <option value="F">Femenino (F)</option>
                        </select>
                      </label>
                      <label className="form-group">
                        Fecha Nacimiento *
                        <input
                          className="input"
                          type="date"
                          max={todayStr}
                          title="La fecha de nacimiento no puede ser futura"
                          value={newDependentForm.fechaNacimiento}
                          onChange={e => setNewDependentForm({ ...newDependentForm, fechaNacimiento: e.target.value })}
                          required
                        />
                      </label>
                      <label className="form-group">
                        Parentesco (car_Parentesco) *
                        <select
                          className="select"
                          value={newDependentForm.parentesco}
                          onChange={e => setNewDependentForm({ ...newDependentForm, parentesco: e.target.value })}
                          required
                        >
                          <option value="">-- Seleccione parentesco --</option>
                          <option value="Hijo/a">Hijo/a</option>
                          <option value="Cónyuge">Cónyuge</option>
                          <option value="Conviviente">Conviviente / Unión de Hecho</option>
                          <option value="Madre">Madre</option>
                          <option value="Padre">Padre</option>
                        </select>
                      </label>
                      <label className="form-group">
                        Estado Civil (car_EstadoCivil) *
                        <select
                          className="select"
                          value={newDependentForm.estadoCivil}
                          onChange={e => setNewDependentForm({ ...newDependentForm, estadoCivil: e.target.value })}
                          required
                        >
                          <option value="">-- Seleccione estado civil --</option>
                          <option value="Soltero/a">Soltero/a</option>
                          <option value="Casado/a">Casado/a</option>
                          <option value="Divorciado/a">Divorciado/a</option>
                          <option value="Viudo/a">Viudo/a</option>
                          <option value="Unión de Hecho">Unión de Hecho</option>
                        </select>
                      </label>
                      <label className="form-group">
                        Tipo de Dependencia *
                        <select
                          className="select"
                          value={newDependentForm.dependencia}
                          onChange={e => setNewDependentForm({ ...newDependentForm, dependencia: e.target.value })}
                          required
                        >
                          <option value="">-- Seleccione dependencia --</option>
                          <option value="Total">Total</option>
                          <option value="Parcial">Parcial</option>
                          <option value="Económica">Económica</option>
                        </select>
                      </label>
                      <div className="form-action" style={{ gridColumn: 'span 2', display: 'flex', alignItems: 'flex-end' }}>
                        <button type="submit" className="btn btn-primary" style={{ width: '100%', height: '38px' }}>
                          <Plus size={16} /> Guardar Carga Familiar
                        </button>
                      </div>
                    </div>
                  </form>
                </div>

                {/* Tabla de Cargas Familiares con opción de Modificar */}
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Cédula</th>
                        <th>Nombres y Apellidos</th>
                        <th>Parentesco</th>
                        <th>Sexo</th>
                        <th>F. Nacimiento</th>
                        <th>Estado Civil</th>
                        <th>Dependencia</th>
                        <th>Acción</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dependents.map((dep, idx) => (
                        <tr key={dep.id || idx}>
                          <td><strong>{dep.ci}</strong></td>
                          <td>{dep.name || `${dep.nombre1} ${dep.apellido1}`}</td>
                          <td><span className="badge badge-ABI">{dep.parentesco}</span></td>
                          <td>{dep.sexo === 'M' ? 'Masc.' : 'Fem.'}</td>
                          <td>{String(dep.fechaNacimiento).slice(0, 10)}</td>
                          <td>{dep.estadoCivil}</td>
                          <td>{dep.dependencia}</td>
                          <td>
                            {dep.id && (
                              <div style={{ display: 'flex', gap: '6px' }}>
                                <button
                                  type="button"
                                  className="btn btn-outline"
                                  style={{ padding: '4px 8px', color: '#4f46e5', borderColor: '#c7d2fe' }}
                                  onClick={() => startEditDependent(dep)}
                                  title="Modificar datos de la carga familiar"
                                >
                                  <Edit3 size={14} />
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-outline"
                                  style={{ padding: '4px 8px', color: '#dc2626', borderColor: '#fca5a5' }}
                                  onClick={() => handleDeleteDependent(dep.id!)}
                                  title="Eliminar carga familiar"
                                >
                                  <Trash2 size={14} />
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                      {!dependents.length && (
                        <tr>
                          <td colSpan={8} className="empty-state">
                            Este colaborador no tiene cargas familiares registradas en la tabla CARGAS.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>
        ) : (
          <div className="card" style={{ padding: '40px', textAlign: 'center', color: '#6b7280' }}>
            Selecciona un empleado de la lista para ver o editar su expediente completo.
          </div>
        )}
      </div>

      {/* Modal Modificar Carga Familiar */}
      {editingDependent && (
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e5e7eb', paddingBottom: '12px', marginBottom: '16px' }}>
              <div>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6366f1', textTransform: 'uppercase' }}>
                  MODIFICAR CARGA FAMILIAR: {editingDependent.id}
                </span>
                <h2 style={{ margin: '4px 0 0 0', fontSize: '1.25rem', color: '#111827' }}>
                  {editingDependent.name || `${editingDependent.nombre1} ${editingDependent.apellido1}`}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setEditingDependent(null)}
                style={{ background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer', color: '#6b7280' }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleUpdateDependent}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '14px' }}>
                <label className="form-group">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Cédula Carga (10 dígitos) *</span>
                    {editDependentForm.ci.length === 10 && (
                      validateEcuadorianCedula(editDependentForm.ci) ? (
                        <span style={{ color: '#16a34a', fontSize: '0.75rem', fontWeight: 600 }}>✓ Válida</span>
                      ) : (
                        <span style={{ color: '#dc2626', fontSize: '0.75rem', fontWeight: 600 }}>✗ Inválida</span>
                      )
                    )}
                  </div>
                  <input
                    className="input"
                    maxLength={10}
                    pattern="\d{10}"
                    title="Debe tener 10 dígitos numéricos válidos en Ecuador"
                    value={editDependentForm.ci}
                    onChange={e => setEditDependentForm({ ...editDependentForm, ci: e.target.value.replace(/\D/g, '').slice(0, 10) })}
                    required
                  />
                </label>
                <label className="form-group">
                  Sexo *
                  <select
                    className="select"
                    value={editDependentForm.sexo}
                    onChange={e => setEditDependentForm({ ...editDependentForm, sexo: e.target.value })}
                    required
                  >
                    <option value="">-- Seleccione sexo --</option>
                    <option value="M">Masculino (M)</option>
                    <option value="F">Femenino (F)</option>
                  </select>
                </label>
                <label className="form-group">
                  Primer Nombre *
                  <input
                    className="input"
                    maxLength={20}
                    pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s]+"
                    title="Solo letras y espacios (máximo 20 caracteres)"
                    value={editDependentForm.nombre1}
                    onChange={e => setEditDependentForm({ ...editDependentForm, nombre1: e.target.value })}
                    required
                  />
                </label>
                <label className="form-group">
                  Segundo Nombre
                  <input
                    className="input"
                    maxLength={20}
                    pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s]*"
                    title="Solo letras y espacios (máximo 20 caracteres)"
                    value={editDependentForm.nombre2}
                    onChange={e => setEditDependentForm({ ...editDependentForm, nombre2: e.target.value })}
                  />
                </label>
                <label className="form-group">
                  Primer Apellido *
                  <input
                    className="input"
                    maxLength={20}
                    pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s]+"
                    title="Solo letras y espacios (máximo 20 caracteres)"
                    value={editDependentForm.apellido1}
                    onChange={e => setEditDependentForm({ ...editDependentForm, apellido1: e.target.value })}
                    required
                  />
                </label>
                <label className="form-group">
                  Segundo Apellido
                  <input
                    className="input"
                    maxLength={20}
                    pattern="[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s]*"
                    title="Solo letras y espacios (máximo 20 caracteres)"
                    value={editDependentForm.apellido2}
                    onChange={e => setEditDependentForm({ ...editDependentForm, apellido2: e.target.value })}
                  />
                </label>
                <label className="form-group">
                  Fecha de Nacimiento *
                  <input
                    className="input"
                    type="date"
                    max={todayStr}
                    value={editDependentForm.fechaNacimiento}
                    onChange={e => setEditDependentForm({ ...editDependentForm, fechaNacimiento: e.target.value })}
                    required
                  />
                </label>
                <label className="form-group">
                  Parentesco *
                  <select
                    className="select"
                    value={editDependentForm.parentesco}
                    onChange={e => setEditDependentForm({ ...editDependentForm, parentesco: e.target.value })}
                    required
                  >
                    <option value="">-- Seleccione parentesco --</option>
                    <option value="Hijo/a">Hijo/a</option>
                    <option value="Cónyuge">Cónyuge</option>
                    <option value="Conviviente">Conviviente / Unión de Hecho</option>
                    <option value="Madre">Madre</option>
                    <option value="Padre">Padre</option>
                  </select>
                </label>
                <label className="form-group">
                  Estado Civil *
                  <select
                    className="select"
                    value={editDependentForm.estadoCivil}
                    onChange={e => setEditDependentForm({ ...editDependentForm, estadoCivil: e.target.value })}
                    required
                  >
                    <option value="">-- Seleccione estado civil --</option>
                    <option value="Soltero/a">Soltero/a</option>
                    <option value="Casado/a">Casado/a</option>
                    <option value="Divorciado/a">Divorciado/a</option>
                    <option value="Viudo/a">Viudo/a</option>
                    <option value="Unión de Hecho">Unión de Hecho</option>
                  </select>
                </label>
                <label className="form-group">
                  Tipo de Dependencia *
                  <select
                    className="select"
                    value={editDependentForm.dependencia}
                    onChange={e => setEditDependentForm({ ...editDependentForm, dependencia: e.target.value })}
                    required
                  >
                    <option value="">-- Seleccione dependencia --</option>
                    <option value="Total">Total</option>
                    <option value="Parcial">Parcial</option>
                    <option value="Económica">Económica</option>
                  </select>
                </label>
              </div>

              <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setEditingDependent(null)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                >
                  Guardar Modificación
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Nuevo Colaborador */}
      {isNewEmpModalOpen && (
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
            maxWidth: '750px',
            width: '100%',
            maxHeight: '90vh',
            overflowY: 'auto',
            padding: '24px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e5e7eb', paddingBottom: '12px', marginBottom: '16px' }}>
              <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#111827' }}>Registrar nuevo colaborador</h2>
              <button
                type="button"
                onClick={() => setIsNewEmpModalOpen(false)}
                style={{ background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer', color: '#6b7280' }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateEmployee} noValidate>
              {Object.keys(newEmpFieldErrors).length > 0 && (
                <div className="alert alert-error" role="alert">
                  <AlertCircle size={18} />
                  <div>
                    <strong>Corrige estos campos:</strong>
                    <ul className="validation-error-list">
                      {Object.entries(newEmpFieldErrors).map(([field, message]) => (
                        <li key={field}><strong>{({
                          ci: 'Cédula',
                          nombre1: 'Primer nombre',
                          nombre2: 'Segundo nombre',
                          apellido1: 'Primer apellido',
                          apellido2: 'Segundo apellido',
                          sueldo: 'Sueldo',
                          sexo: 'Sexo',
                          fechaNacimiento: 'Fecha de nacimiento',
                          idDepartamento: 'Departamento',
                          idCargo: 'Cargo inicial',
                          direccion: 'Dirección',
                          telefono: 'Teléfono',
                          celular: 'Celular',
                          email: 'Correo electrónico',
                        } as Record<string, string>)[field] ?? 'Campo'}</strong>: {message}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '14px' }}>
                <label className="form-group">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Cédula de Identidad (10 dígitos) *</span>
                    {newEmpForm.ci.length === 10 && (
                      validateEcuadorianCedula(newEmpForm.ci) ? (
                        <span style={{ color: '#16a34a', fontSize: '0.75rem', fontWeight: 600 }}>✓ Cédula válida</span>
                      ) : (
                        <span style={{ color: '#dc2626', fontSize: '0.75rem', fontWeight: 600 }}>✗ Cédula no válida</span>
                      )
                    )}
                  </div>
                  <input
                    id="new-employee-ci"
                    className="input"
                    maxLength={10}
                    pattern="\d{10}"
                    title="Debe ingresar exactamente 10 dígitos numéricos correspondientes a una cédula ecuatoriana válida"
                    placeholder="1712345678"
                    value={newEmpForm.ci}
                    onChange={e => updateNewEmployeeField('ci', e.target.value.replace(/\D/g, '').slice(0, 10))}
                    aria-invalid={Boolean(newEmpFieldErrors.ci)}
                    required
                  />
                  {newEmpSubmitted && newEmpFieldErrors.ci && <span className="field-error">{newEmpFieldErrors.ci}</span>}
                </label>
                <label className="form-group">
                  Sueldo Base ($ - Mín. SBU $460) *
                  <input
                    id="new-employee-sueldo"
                    className="input"
                    type="number"
                    min="460"
                    max="50000"
                    step="0.01"
                    placeholder="460.00"
                    value={newEmpForm.sueldo || ''}
                    onChange={e => updateNewEmployeeField('sueldo', Number(e.target.value))}
                    aria-invalid={Boolean(newEmpFieldErrors.sueldo)}
                    required
                  />
                  {newEmpSubmitted && newEmpFieldErrors.sueldo && <span className="field-error">{newEmpFieldErrors.sueldo}</span>}
                </label>
                <label className="form-group">
                  Primer nombre *
                  <input
                    id="new-employee-nombre1"
                    className="input"
                    maxLength={30}
                    placeholder="Ej: Carlos"
                    value={newEmpForm.nombre1}
                    onChange={e => updateNewEmployeeField('nombre1', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.nombre1)}
                    required
                  />
                  {newEmpSubmitted && newEmpFieldErrors.nombre1 && <span className="field-error">{newEmpFieldErrors.nombre1}</span>}
                </label>
                <label className="form-group">
                  Segundo nombre
                  <input
                    id="new-employee-nombre2"
                    className="input"
                    maxLength={30}
                    placeholder="Ej: Andrés"
                    value={newEmpForm.nombre2}
                    onChange={e => updateNewEmployeeField('nombre2', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.nombre2)}
                  />
                  {newEmpSubmitted && newEmpFieldErrors.nombre2 && <span className="field-error">{newEmpFieldErrors.nombre2}</span>}
                </label>
                <label className="form-group">
                  Primer apellido *
                  <input
                    id="new-employee-apellido1"
                    className="input"
                    maxLength={30}
                    placeholder="Ej: Mendoza"
                    value={newEmpForm.apellido1}
                    onChange={e => updateNewEmployeeField('apellido1', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.apellido1)}
                    required
                  />
                  {newEmpSubmitted && newEmpFieldErrors.apellido1 && <span className="field-error">{newEmpFieldErrors.apellido1}</span>}
                </label>
                <label className="form-group">
                  Segundo apellido
                  <input
                    id="new-employee-apellido2"
                    className="input"
                    maxLength={30}
                    placeholder="Ej: Castro"
                    value={newEmpForm.apellido2}
                    onChange={e => updateNewEmployeeField('apellido2', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.apellido2)}
                  />
                  {newEmpSubmitted && newEmpFieldErrors.apellido2 && <span className="field-error">{newEmpFieldErrors.apellido2}</span>}
                </label>
                <label className="form-group">
                  Sexo *
                  <select
                    className="select"
                    value={newEmpForm.sexo}
                    onChange={e => updateNewEmployeeField('sexo', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.sexo)}
                    required
                  >
                    <option value="">-- Seleccione sexo --</option>
                    <option value="M">Masculino (M)</option>
                    <option value="F">Femenino (F)</option>
                  </select>
                  {newEmpSubmitted && newEmpFieldErrors.sexo && <span className="field-error">{newEmpFieldErrors.sexo}</span>}
                </label>
                <label className="form-group">
                  Fecha de nacimiento *
                  <input
                    id="new-employee-fechaNacimiento"
                    className="input"
                    type="date"
                    min={minBirthDateEmp}
                    max={maxBirthDateEmp}
                    value={newEmpForm.fechaNacimiento}
                    onChange={e => updateNewEmployeeField('fechaNacimiento', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.fechaNacimiento)}
                    required
                  />
                  {newEmpSubmitted && newEmpFieldErrors.fechaNacimiento && <span className="field-error">{newEmpFieldErrors.fechaNacimiento}</span>}
                </label>
                <label className="form-group">
                  Departamento *
                  <select
                    className="select"
                    value={newEmpForm.idDepartamento}
                    onChange={e => updateNewEmployeeField('idDepartamento', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.idDepartamento)}
                    required
                  >
                    <option value="">-- Seleccione un departamento --</option>
                    {departments.map(d => (
                      <option key={d.id} value={d.id}>{d.nombre}</option>
                    ))}
                  </select>
                  {newEmpSubmitted && newEmpFieldErrors.idDepartamento && <span className="field-error">{newEmpFieldErrors.idDepartamento}</span>}
                </label>
                <label className="form-group">
                  Cargo Inicial *
                  <select
                    className="select"
                    value={newEmpForm.idCargo}
                    onChange={e => updateNewEmployeeField('idCargo', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.idCargo)}
                    required
                  >
                    <option value="">-- Seleccione un cargo inicial --</option>
                    {cargos.map(c => (
                      <option key={c.id} value={c.id}>{c.nombre}</option>
                    ))}
                  </select>
                  {newEmpSubmitted && newEmpFieldErrors.idCargo && <span className="field-error">{newEmpFieldErrors.idCargo}</span>}
                </label>

                <label className="form-group" style={{ gridColumn: 'span 2' }}>
                  Dirección *
                  <input
                    id="new-employee-direccion"
                    className="input"
                    maxLength={60}
                    placeholder="Ej: Calle Los Cedros 123 y Av. 10 de Agosto, Quito"
                    value={newEmpForm.direccion}
                    onChange={e => updateNewEmployeeField('direccion', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.direccion)}
                    required
                  />
                  {newEmpSubmitted && newEmpFieldErrors.direccion && <span className="field-error">{newEmpFieldErrors.direccion}</span>}
                </label>
                <label className="form-group">
                  Teléfono convencional (opcional)
                  <input
                    id="new-employee-telefono"
                    className="input"
                    maxLength={9}
                    pattern="[0-9]{7,9}"
                    title="7 a 9 dígitos numéricos (ej. 022123456)"
                    placeholder="022123456"
                    value={newEmpForm.telefono}
                    onChange={e => updateNewEmployeeField('telefono', e.target.value.replace(/\D/g, '').slice(0, 9))}
                    aria-invalid={Boolean(newEmpFieldErrors.telefono)}
                  />
                  {newEmpSubmitted && newEmpFieldErrors.telefono && <span className="field-error">{newEmpFieldErrors.telefono}</span>}
                </label>
                <label className="form-group">
                  Celular
                  <input
                    id="new-employee-celular"
                    className="input"
                    maxLength={10}
                    pattern="09[0-9]{8}"
                    title="10 dígitos numéricos iniciando con 09 (ej. 0991234567)"
                    placeholder="0991234567"
                    value={newEmpForm.celular}
                    onChange={e => updateNewEmployeeField('celular', e.target.value.replace(/\D/g, '').slice(0, 10))}
                    aria-invalid={Boolean(newEmpFieldErrors.celular)}
                  />
                  {newEmpSubmitted && newEmpFieldErrors.celular && <span className="field-error">{newEmpFieldErrors.celular}</span>}
                </label>
                <label className="form-group" style={{ gridColumn: 'span 2' }}>
                  Correo electrónico
                  <input
                    id="new-employee-email"
                    className="input"
                    type="email"
                    maxLength={60}
                    placeholder="colaborador@lacava.com"
                    value={newEmpForm.email}
                    onChange={e => updateNewEmployeeField('email', e.target.value)}
                    aria-invalid={Boolean(newEmpFieldErrors.email)}
                  />
                  {newEmpSubmitted && newEmpFieldErrors.email && <span className="field-error">{newEmpFieldErrors.email}</span>}
                </label>
              </div>

              <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsNewEmpModalOpen(false)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                >
                  <Plus size={16} /> Registrar Colaborador
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
