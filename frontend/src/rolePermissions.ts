import type { AuthUser } from './types';

type Module = 'COMPRAS' | 'VENTAS' | 'INVENTARIOS' | 'TALENTO_HUMANO' | 'CONTABILIDAD';
type Action = 'CREAR' | 'VER' | 'APROBAR' | 'ANULAR';

export function canPerform(user: AuthUser | null, module: Module, action: Action): boolean {
  if (!user) return false;
  return user.roles.some(role => {
    const name = role.trim().toUpperCase();
    if (name === 'ADMINISTRADOR') return true;
    const separator = name.indexOf('_');
    if (separator < 0 || name.slice(separator + 1) !== module) return false;
    const level = name.slice(0, separator);
    if (action === 'VER') return ['OPERATIVO', 'AUXILIAR', 'JEFE'].includes(level);
    return (level === 'OPERATIVO' && action === 'CREAR')
      || (level === 'AUXILIAR' && action === 'APROBAR')
      || (level === 'JEFE' && action === 'ANULAR');
  });
}
