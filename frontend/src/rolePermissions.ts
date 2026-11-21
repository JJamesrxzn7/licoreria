import type { AuthUser } from './types';

export type Module = 'COMPRAS' | 'VENTAS' | 'INVENTARIOS' | 'TALENTO_HUMANO' | 'CONTABILIDAD';
export type Action = 'CREAR' | 'VER' | 'APROBAR' | 'ANULAR';

export function isSuperAdmin(user: AuthUser | null): boolean {
  if (!user) return false;
  return (
    user.roleIds.includes('ROL-ADM')
    || user.roleIds.includes('ROL-ADMIN')
    || user.roles.some(r => ['ADMIN', 'ADMINISTRADOR', 'SUPERADMINISTRADOR'].includes(r.trim().toUpperCase()))
  );
}

export function isDbaUser(user: AuthUser | null): boolean {
  if (!user) return false;
  return (
    user.roleIds.includes('ROL-DBA')
    || user.username.trim().toLowerCase() === 'dba'
    || user.roles.some(r => r.trim().toUpperCase().includes('DBA'))
  );
}

export function canPerform(user: AuthUser | null, module: Module, action: Action): boolean {
  if (!user) return false;
  // El DBA solo monitorea arquitectura y consulta bases de datos (Read-Only): no crea, aprueba ni anula en el ERP
  if (isDbaUser(user) && !isSuperAdmin(user)) {
    return action === 'VER';
  }
  if (isSuperAdmin(user)) {
    return true;
  }

  return user.roles.some(role => {
    const name = role.trim().toUpperCase();
    if (['ADMIN', 'ADMINISTRADOR', 'SUPERADMINISTRADOR'].includes(name)) return true;

    const separator = name.indexOf('_');
    if (separator < 0 || name.slice(separator + 1) !== module) return false;
    const level = name.slice(0, separator); // JEFE, SUPERVISOR, AUXILIAR, OPERATIVO, OPERADOR

    if (action === 'VER') {
      return ['OPERATIVO', 'OPERADOR', 'SUPERVISOR', 'AUXILIAR', 'JEFE'].includes(level);
    }
    if (action === 'CREAR') {
      return ['OPERATIVO', 'OPERADOR', 'SUPERVISOR', 'AUXILIAR', 'JEFE'].includes(level);
    }
    if (action === 'APROBAR') {
      return ['SUPERVISOR', 'AUXILIAR', 'JEFE'].includes(level);
    }
    if (action === 'ANULAR') {
      return level === 'JEFE';
    }
    return false;
  });
}
