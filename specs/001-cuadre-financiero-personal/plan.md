# Plan de Implementación: Módulo de Cuadre Financiero Personal

**Rama**: `001-cuadre-financiero-personal` | **Fecha**: 2026-10-02 | **Spec**: [spec.md](file:///c:/Users/Miguel%20F/.gemini/antigravity/scratch/App%20Gestion%20Personal/specs/001-cuadre-financiero-personal/spec.md)

---

## 1. Resumen Ejecutivo y Enfoque

Implementar el sistema de **Cuadre Financiero Personal** adaptando las lecciones y lógica matemática de `APH` (eliminando compras a proveedores, reorientando ventas hacia sueldos/fuentes diversas, preservando los 3 potes y los gastos, y adaptando el balance de ganancias/pérdidas al patrimonio y flujo de efectivo personal).

Aprovechando las skills instaladas en `.agents/skills`:
- `finance-expert` & `accounting`: Para garantizar la precisión contable de doble entrada simplificada, reconciliación de arqueo físico y cálculos de tasas multimoneda.
- `database-schema-design` & `sqlite-database-expert`: Para estructurar la persistencia relacional con control transaccional e integridad referencial.
- `stitch-design-taste` & `frontend-design`: Para la interfaz visual (estilo tabla dinámica con vista segmentada por pote, badges de estado y diseño limpio sin saturación).

---

## 2. Opciones de Plataforma y Stack Tecnológico

Dada la reestructuración completa del proyecto, se presentan dos vías de ejecución:

| Aspecto | Opción A: Web App Local / Híbrida (Recomendada si se busca paridad exacta con APH) | Opción B: Android Nativa (Kotlin + Compose + Room) |
|---|---|---|
| **Tecnología** | Python (Flask / FastAPI) + SQLite + HTML5/CSS/Vanilla JS (o Vite/Vue/React) | Kotlin + Jetpack Compose + Room SQLite + Navigation Compose |
| **Ventajas** | - Reutilización directa del código y lógica depurada de `api_cuadre.py` y `cuadre.html`.<br>- Experiencia de tabla/hoja de cálculo tipo Excel muy cómoda en pantalla completa.<br>- Muy fácil de desplegar o usar localmente en PC o acceder por red local desde el móvil. | - Experiencia 100% nativa en el dispositivo móvil.<br>- Acceso táctil inmediato sin depender de navegador o servidor.<br>- Cero consumo en segundo plano. |
| **Tiempo de Entrega MVP** | Extremadamente rápido (1 a 2 iteraciones aprovechando componentes de APH). | Progresivo por pantallas y ViewModels en Android. |

*Nota: La lógica matemática y la estructura de datos es 100% agnóstica a la plataforma y se define en la fase 1.*

---

## 3. Estructura de Fases de Desarrollo

### Fase 1: Motor Contable y Base de Datos (Core Engine)
- [ ] 1.1 Crear esquema de base de datos SQLite con tablas:
  - `finanzas_ingresos`: id, mes, semana, fecha, fuente, pote, monto_original, tasa, monto_usd, descripcion.
  - `finanzas_gastos`: id, mes, semana, fecha, descripcion, categoria, pote/moneda, monto_original, tasa, monto_usd, referencia.
  - `finanzas_cambios_internos`: id, mes, fecha, pote_origen, monto_origen, pote_destino, monto_destino, tasa, nota.
  - `finanzas_ahorros`: id, mes, fecha, tipo (`APORTE`/`RETIRO`), concepto, monto_usd, referencia.
  - `finanzas_balance_mensual`: mes, saldo_inicio_efectivo, efectivo_en_mano, tasa_bcv, cuentas_bancarias_json, meta_ahorro, notas.
  - `finanzas_inyecciones`: aportes externos no operativos.
- [ ] 1.2 Implementar motor de cálculo matemático a 2 decimales (`r2(val)`).
- [ ] 1.3 Implementar generador de semanas de calendario del mes (Lunes a Sábado o Lunes a Domingo con días activos en el mes).

### Fase 2: Módulo de Ingresos Personales
- [ ] 2.1 API / Repositorio CRUD para registrar sueldos fijos, honorarios, comisiones y extras.
- [ ] 2.2 Asignación al pote correspondiente (Efectivo $, Binance USDT, Bolívares Bs a tasa).
- [ ] 2.3 Matriz semanal y agregación por semanas 1 a 5.

### Fase 3: Módulo de Gastos Personales (Idéntico al de APH)
- [ ] 3.1 CRUD de Gastos con soporte para monedas (`EFECTIVO`, `BINANCE`, `BS`) y tasa del día.
- [ ] 3.2 Categorización personal (Alimentación, Hogar/Servicios, Salud, Transporte, Ocio, Personales, etc.).
- [ ] 3.3 Filtro segmentado interactivo por Pote (`Todos`, `Efectivo`, `Binance`, `Bolívares`).

### Fase 4: Cambios Internos entre Potes y Ahorros
- [ ] 4.1 Registro de operaciones de cambio de divisas / transferencias entre cuentas (ej: Efectivo -> Binance, Binance -> Bolívares).
- [ ] 4.2 Registro de aportes al fondo de ahorros (conteo como salida del flujo operativo hacia reserva acumulada).
- [ ] 4.3 Cálculo de saldos netos por pote.

### Fase 5: Balance Mensual, Arqueo Físico y Rendimiento
- [ ] 5.1 Pilar 1: Arqueo de Caja Físico:
  - Entrada de `efectivo_en_mano`.
  - Comparativa con `efectivo_teorico`.
  - Diagnóstico visual de arqueo (`CUADRADO`, `SOBRANTE`, `FALTANTE`).
- [ ] 5.2 Pilar 2: Posición de Liquidez y Patrimonio Líquido:
  - Saldo en Efectivo + Binance USDT + Cuentas bancarias en Bs convertidas a tasa.
- [ ] 5.3 Pilar 3: Rendimiento y Flujo de Caja:
  - Total Ingresos vs Total Gastos.
  - Superávit neto / Capacidad de ahorro.

### Fase 6: UI / UX y Dashboard
- [ ] 6.1 Implementación de interfaz moderna con cards KPIs de los 3 potes.
- [ ] 6.2 Pestañas de navegación ágil:
  - 1. Ingresos Semanales
  - 2. Gastos Personales
  - 3. Cambios entre Potes & Ahorro
  - 4. Balance Mensual & Arqueo
