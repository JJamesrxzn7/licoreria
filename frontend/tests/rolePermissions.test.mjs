import assert from 'node:assert/strict';
import { test } from 'node:test';
import { canPerform } from '../src/rolePermissions.ts';

const user = (...roles) => ({ roles });
const modules = ['COMPRAS', 'VENTAS', 'INVENTARIOS', 'TALENTO_HUMANO', 'CONTABILIDAD'];
const actions = ['CREAR', 'VER', 'APROBAR', 'ANULAR'];

test('la matriz concede solo las acciones de cada nivel y módulo', () => {
  for (const module of modules) {
    for (const [level, allowed] of [
      ['OPERATIVO', ['CREAR', 'VER']],
      ['AUXILIAR', ['APROBAR', 'VER']],
      ['JEFE', ['ANULAR', 'VER']],
    ]) {
      for (const target of modules) {
        for (const action of actions) {
          assert.equal(canPerform(user(`${level}_${module}`), target, action),
            module === target && allowed.includes(action), `${level}_${module}: ${target} ${action}`);
        }
      }
    }
  }
});

test('administrador, roles acumulados y roles desconocidos', () => {
  for (const module of modules) for (const action of actions) {
    assert.equal(canPerform(user(' Administrador '), module, action), true);
  }
  assert.equal(canPerform(user('operativo_ventas', 'Auxiliar_VENTAS'), 'VENTAS', 'CREAR'), true);
  assert.equal(canPerform(user('operativo_ventas', 'Auxiliar_VENTAS'), 'VENTAS', 'APROBAR'), true);
  assert.equal(canPerform(user('operativo_ventas', 'Auxiliar_VENTAS'), 'VENTAS', 'ANULAR'), false);
  assert.equal(canPerform(user('AUXILIAR_VENTAS_EXTRA'), 'VENTAS', 'APROBAR'), false);
  assert.equal(canPerform(null, 'VENTAS', 'VER'), false);
});
