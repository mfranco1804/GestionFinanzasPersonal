import os
import unittest
import json
import sqlite3

# Usar base de datos de pruebas 100% aislada para NUNCA tocar la base de datos real del usuario
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_test_suite.db')

import database
database.DB_PATH = TEST_DB_PATH

from app import app
from database import init_db

class TestCuadrePersonal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Crear base de datos de prueba aislada
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass
        init_db()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        # Limpiar base de datos temporal de prueba
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    def test_01_index_redirect(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/cuadre', res.headers['Location'])

    def test_02_cuadre_view(self):
        res = self.client.get('/cuadre')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Ingresos Personales', res.data)

    def test_03_crear_ingresos_dinamicos(self):
        # 1. Ingreso en Efectivo
        payload_ef = {
            'mes': '2026-10',
            'fecha': '2026-10-02',
            'concepto': 'Sueldo Primera Quincena',
            'fuente': 'Sueldo / Salario Fijo',
            'moneda': 'EFECTIVO',
            'monto_original': 300.0,
            'tasa': 1.0,
            'referencia': 'Nómina Directa'
        }
        res_ef = self.client.post('/api/cuadre/ingresos',
                                  data=json.dumps(payload_ef),
                                  content_type='application/json')
        self.assertEqual(res_ef.status_code, 200)
        self.assertTrue(res_ef.get_json()['success'])

        # 2. Ingreso en Bolívares con tasa
        payload_bs = {
            'mes': '2026-10',
            'fecha': '2026-10-05',
            'concepto': 'Freelance Soporte Web',
            'fuente': 'Freelance / Proyectos',
            'moneda': 'BS',
            'monto_original': 4000.0,
            'tasa': 40.0, # 4000 / 40 = 100 USD
            'referencia': 'Pago Móvil Banesco'
        }
        res_bs = self.client.post('/api/cuadre/ingresos',
                                  data=json.dumps(payload_bs),
                                  content_type='application/json')
        self.assertEqual(res_bs.status_code, 200)
        self.assertTrue(res_bs.get_json()['success'])

        # 3. Consulta de Ingresos con Valuación en Vivo
        res_list = self.client.get('/api/cuadre/ingresos/2026-10')
        self.assertEqual(res_list.status_code, 200)
        data = res_list.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['totales_pote']['efectivo_usd'], 300.0)
        self.assertEqual(data['totales_pote']['bs_nominal'], 4000.0)
        self.assertIn('bs_live', data['totales_pote'])
        self.assertIn('bcv_usd', data['totales_pote']['bs_live'])
        self.assertIn('binance_usdt', data['totales_pote']['bs_live'])
        self.assertIn('bcv_euro', data['totales_pote']['bs_live'])
        self.assertEqual(data['totales_pote']['conteo'], 2)

    def test_04_crear_gasto_y_balance(self):
        # 1. Gasto en Efectivo
        payload_gasto = {
            'mes': '2026-10',
            'fecha': '2026-10-06',
            'descripcion': 'Supermercado y Alimentos',
            'categoria': 'Alimentación y Supermercado',
            'moneda': 'EFECTIVO',
            'monto_original': 120.0,
            'tasa': 1.0
        }
        res_g = self.client.post('/api/cuadre/gastos',
                                 data=json.dumps(payload_gasto),
                                 content_type='application/json')
        self.assertEqual(res_g.status_code, 200)
        self.assertTrue(res_g.get_json()['success'])

        # 2. Balance General del Mes
        res_res = self.client.get('/api/cuadre/balance/2026-10')
        self.assertEqual(res_res.status_code, 200)
        res_data = res_res.get_json()
        self.assertTrue(res_data['success'])
        self.assertIn('pilar1_arqueo', res_data)
        self.assertEqual(res_data['pilar1_arqueo']['ingresos_efectivo'], 300.0)
        self.assertEqual(res_data['pilar1_arqueo']['gastos_efectivo'], 120.0)

    def test_05_tasas_personalizadas_y_modo_manual(self):
        # 1. Modificar tasas manualmente
        payload_tasas = {
            'tasa_bcv': 850.50,
            'tasa_bcv_euro': 960.25,
            'tasa_usdt': 950.00
        }
        res_t = self.client.post('/api/tasas/manual',
                                 data=json.dumps(payload_tasas),
                                 content_type='application/json')
        self.assertEqual(res_t.status_code, 200)
        self.assertTrue(res_t.get_json()['success'])

        # 2. Consultar tasas
        res_manual = self.client.get('/api/tasas')
        self.assertEqual(res_manual.status_code, 200)
        res_m_data = res_manual.get_json()
        self.assertTrue(res_m_data['success'])
        self.assertEqual(res_m_data['tasa_bcv'], 850.50)
        self.assertEqual(res_m_data['tasa_bcv_euro'], 960.25)
        self.assertEqual(res_m_data['tasa_usdt'], 950.00)
        self.assertEqual(res_m_data['modo'], 'MANUAL')

    def test_06_whatsapp_methods(self):
        import io
        # 1. Test WhatsApp Estado
        res_st = self.client.get('/api/cuadre/whatsapp/estado')
        self.assertEqual(res_st.status_code, 200)
        st_data = res_st.get_json()
        self.assertTrue(st_data['success'])
        self.assertIn('pendientes_count', st_data)

        # 2. Test WhatsApp Config en BD aislada
        res_cfg = self.client.post('/api/cuadre/whatsapp/config',
                                   data=json.dumps({'grupo_nombre': 'Finanzas Test', 'enlace_grupo': 'https://chat.whatsapp.com/test'}),
                                   content_type='application/json')
        self.assertEqual(res_cfg.status_code, 200)

        # 3. Test Importar archivo .txt
        chat_content = """02/10/2026, 10:15 - Miguel: Cobré 250 $ de honorarios
02/10/2026, 11:30 - Miguel: Cobre 120 $ freelance
02/10/2026, 12:45 - Miguel: Pagué 45 $ supermercado
02/10/2026, 14:00 - Miguel: Pague 15 efectivo cafe
02/10/2026, 15:30 - Miguel: Cambié 50 usdt a bs tasa 45
02/10/2026, 16:15 - Miguel: Cambie 30 usdt a bs tasa 45
02/10/2026, 17:00 - Miguel: Almuerzo 12$
02/10/2026, 18:00 - Miguel: Gasolina 450 bs
"""
        data = {
            'archivo': (io.BytesIO(chat_content.encode('utf-8')), 'chat_whatsapp_test.txt')
        }
        res_imp = self.client.post('/api/cuadre/whatsapp/importar-archivo',
                                   data=data,
                                   content_type='multipart/form-data')
        self.assertEqual(res_imp.status_code, 200)
        imp_data = res_imp.get_json()
        self.assertTrue(imp_data['success'])
        self.assertEqual(imp_data['insertados'], 8)

    def test_07_telegram_bot_endpoints(self):
        # 1. Consultar estado inicial
        res_tg = self.client.get('/api/cuadre/telegram/estado')
        self.assertEqual(res_tg.status_code, 200)
        tg_data = res_tg.get_json()
        self.assertTrue(tg_data['success'])
        self.assertIn('activo', tg_data)
        self.assertIn('modo_guardado', tg_data)

        # 2. Desvincular chat de prueba
        res_desv = self.client.post('/api/cuadre/telegram/desvincular')
        self.assertEqual(res_desv.status_code, 200)
        self.assertTrue(res_desv.get_json()['success'])

    def test_08_proyeccion_financiera_endpoints(self):
        # 1. Renderizado de la vista HTML
        res_view = self.client.get('/proyeccion')
        self.assertEqual(res_view.status_code, 200)
        self.assertIn(b'Proyecci\xc3\xb3n: Gastos Fijos vs Entradas Fijas', res_view.data)

        # 2. Registrar gasto fijo anual (ej: Seguro Vehicular 600$ anual -> 50$/mes)
        payload_gasto_anual = {
            'tipo': 'GASTO',
            'concepto': 'Seguro de Vehículo',
            'categoria': 'Seguros & Salud (Póliza HCM, Seguro Auto, Medicinas)',
            'moneda': 'USD',
            'monto_original': 600.0,
            'frecuencia': 'ANUAL'
        }
        res_g1 = self.client.post('/api/proyeccion/item',
                                  data=json.dumps(payload_gasto_anual),
                                  content_type='application/json')
        self.assertEqual(res_g1.status_code, 200)
        d_g1 = res_g1.get_json()
        self.assertTrue(d_g1['success'])
        self.assertEqual(d_g1['calculos']['monto_mensual_usd'], 50.0)
        self.assertEqual(d_g1['calculos']['monto_anual_usd'], 600.0)
        gasto_id = d_g1['item_id']

        # 3. Registrar entrada fija mensual (ej: Sueldo Principal 1500$)
        payload_entrada = {
            'tipo': 'ENTRADA',
            'concepto': 'Sueldo Principal',
            'categoria': 'Sueldo / Salario Principal',
            'moneda': 'USD',
            'monto_original': 1500.0,
            'frecuencia': 'MENSUAL'
        }
        res_e1 = self.client.post('/api/proyeccion/item',
                                  data=json.dumps(payload_entrada),
                                  content_type='application/json')
        self.assertEqual(res_e1.status_code, 200)
        d_e1 = res_e1.get_json()
        self.assertTrue(d_e1['success'])
        self.assertEqual(d_e1['calculos']['monto_mensual_usd'], 1500.0)

        # 4. Registrar gasto semanal (ej: Mercado Semanal 70$ -> 70 * 52/12 = 303.33$/mes)
        payload_gasto_sem = {
            'tipo': 'GASTO',
            'concepto': 'Mercado Básico Semanal',
            'categoria': 'Alimentación & Despensa Fija',
            'moneda': 'USD',
            'monto_original': 70.0,
            'frecuencia': 'SEMANAL'
        }
        res_g2 = self.client.post('/api/proyeccion/item',
                                  data=json.dumps(payload_gasto_sem),
                                  content_type='application/json')
        self.assertEqual(res_g2.status_code, 200)
        self.assertEqual(res_g2.get_json()['calculos']['monto_mensual_usd'], 303.33)

        # 5. Consultar resumen general de proyección
        res_res = self.client.get('/api/proyeccion/resumen')
        self.assertEqual(res_res.status_code, 200)
        r_data = res_res.get_json()
        self.assertTrue(r_data['success'])
        self.assertEqual(r_data['kpis']['entradas_mensual'], 1500.0)
        self.assertEqual(r_data['kpis']['gastos_mensual'], 353.33)
        self.assertEqual(r_data['kpis']['margen_libre_mensual'], 1146.67)
        self.assertGreater(r_data['kpis']['ratio_cobertura'], 4.0)

        # 6. Simular escenario desactivando el seguro vehicular
        res_tog = self.client.patch(f'/api/proyeccion/item/{gasto_id}/toggle')
        self.assertEqual(res_tog.status_code, 200)
        self.assertFalse(res_tog.get_json()['activo'])

        # Recalcular resumen: el gasto mensual ahora debe ser 303.33 sin el seguro
        res_res2 = self.client.get('/api/proyeccion/resumen')
        self.assertEqual(res_res2.get_json()['kpis']['gastos_mensual'], 303.33)

if __name__ == '__main__':
    unittest.main()
