import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import ALL_FRONTEND_ROUTES, rutas_permitidas


class RutasPermitidasTests(unittest.TestCase):
    def test_ventas_solo_ve_rutas_de_ventas(self):
        permissions = [
            {"id_Permiso": "PRM-000009", "prm_Modulo": "VENTAS", "prm_Accion": "CREAR"},
            {"id_Permiso": "PRM-000010", "prm_Modulo": "VENTAS", "prm_Accion": "VER"},
        ]
        self.assertEqual(
            rutas_permitidas(["ROL-000009"], ["Operativo_VENTAS"], permissions),
            ["dashboard", "pos", "sales", "customers"],
        )

    def test_sin_permiso_de_ver_no_abre_modulo(self):
        permissions = [
            {"id_Permiso": "PRM-000009", "prm_Modulo": "VENTAS", "prm_Accion": "CREAR"}
        ]
        self.assertEqual(rutas_permitidas([], [], permissions), ["dashboard"])

    def test_administrador_conserva_todas_las_rutas(self):
        self.assertEqual(rutas_permitidas(["ROL-ADMIN"], [], []), ALL_FRONTEND_ROUTES)


if __name__ == "__main__":
    unittest.main()
