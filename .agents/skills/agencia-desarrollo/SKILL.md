---
name: agencia-de-desarrollo
description: Utiliza esta skill cuando el usuario pida crear un proyecto de software completo o módulos complejos. Esta herramienta genera un "Plan de Misión" con especialistas coordinados.
---

### Modo de Uso para el Agente (Antigravity)
1.  **Ejecución:** Corre `python director.py "Descripción de la misión"`.
2.  **Entrada:** El Director analizará el contexto global del proyecto (DB, Stack, Historial).
3.  **Salida:** Recibirás un JSON con:
    *   `global_context`: Reglas y conocimientos compartidos a todos los sub-agentes.
    *   `specialists`: Sub-agentes asignados con misiones locales (`particular_context`).
4.  **Orquestación:** Ejecuta las tareas de los especialistas en el orden lógico. 
5.  **QA:** Al llegar a la sección de QA, **DETENTE** y pide autorización explícita al usuario para proceder con la verificación final.
