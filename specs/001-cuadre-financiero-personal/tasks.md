# Tareas de Implementación: Módulo Cuadre Financiero Personal

- [x] 1. Configuración de Entorno y Modelo de Datos
  - [x] 1.1 Configurar el stack idéntico a APH (Python/Flask + SQLite + Bootstrap 5 + Vanilla JS).
  - [x] 1.2 Diseñar el esquema de base de datos relacional en `database.py` con WAL mode y migraciones.
  - [x] 1.3 Implementar utilidades de fechas (semanas 1..5 de calendario mensual) y precisión monetaria a 2 decimales.

- [x] 2. Core de Ingresos Personales
  - [x] 2.1 Definir fuentes de ingresos (Sueldo quincenal/mensual, Freelance, Rendimientos, Extras).
  - [x] 2.2 Registro de transacciones de ingreso asociadas a pote (`EFECTIVO`, `BINANCE`, `BOLIVARES`) y tasa.
  - [x] 2.3 Resumen semanal consolidado por pote con soporte para fórmulas aritméticas (`=...`).

- [x] 3. Core de Gastos Personales (Modelo de 3 Potes)
  - [x] 3.1 Registro de egresos con fecha, semana, categoría, descripción y pote.
  - [x] 3.2 Visualización de tarjetas KPI de egresos por pote (Efectivo, Binance USDT, Bolívares convertidos a USD).
  - [x] 3.3 Barra de filtros segmentada: [Todos] [Efectivo] [Binance] [Bolívares].

- [x] 4. Módulo de Cambios Internos y Fondo de Ahorro
  - [x] 4.1 Registro de traspasos y compras/ventas de divisas entre potes (origen -> destino con tasa).
  - [x] 4.2 Gestión del Fondo de Ahorro (aportes del mes y saldo acumulado protegido).
  - [x] 4.3 Conciliación de saldos netos por pote.

- [x] 5. Módulo de Balance Mensual, Arqueo Físico y Ganancias/Pérdidas
  - [x] 5.1 Cálculo de efectivo teórico disponible frente a efectivo físico en mano.
  - [x] 5.2 Determinación de estado de arqueo (Cuadrado / Faltante / Sobrante).
  - [x] 5.3 Consolidación patrimonial líquida (Efectivo + Binance + Cuentas bancarias a tasa).
  - [x] 5.4 Cálculo de superávit o déficit del mes (Ingresos - Gastos).

- [x] 6. Frontend y Experiencia de Usuario
  - [x] 6.1 Implementación del dashboard y vistas con estilos limpios y profesionales (`templates/base.html`, `templates/cuadre.html`).
  - [x] 6.2 Pruebas de flujo completo con suite automatizada (`test_app.py`).
  - [x] 6.3 Script de lanzamiento en un clic (`iniciar_sistema.bat`).

- [x] 7. Sistema Multi-Tasa Dinámico (BCV Dólar, BCV Euro, Binance P2P USDT)
  - [x] 7.1 Sincronización automática de tasas al iniciar la aplicación.
  - [x] 7.2 Modal de edición y ajuste manual de tasas con selector de valuación en vivo para el pote de Bolívares.
  - [x] 7.3 Switch de valuación en vivo en KPI cards y tablas (`BCV`, `USDT`, `EURO`).

- [x] 8. Integración WhatsApp Financial Hub (Método A + Método B + Parser Universal)
  - [x] 8.1 Parser universal de 3 vías con normalización sin acentos (NFKD) para clasificar Gastos, Ingresos y Cambios en un solo grupo sin solapamiento.
  - [x] 8.2 Soporte dual e indistinto para palabras con o sin tilde (`cobre`/`cobré`, `nomina`/`nómina`, `cambie`/`cambié`, `vendi`/`vendí`, `pague`/`pagué`, `dia`/`día`).
  - [x] 8.3 Método A: Importación de archivo de chat exportado (`.txt`) con protección anti-duplicados por hash SHA-256.
  - [x] 8.4 Método B: Sincronización en vivo con WhatsApp Web (Playwright) y vinculación 1-clic por QR.
  - [x] 8.5 Bandeja de Entrada (Inbox) interactiva con edición en línea y migración en lote o individual a tablas contables reales.

