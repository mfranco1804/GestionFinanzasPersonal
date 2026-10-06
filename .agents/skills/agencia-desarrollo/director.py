import sys
import json
import os
import re
from datetime import datetime

class Director:
    def __init__(self, root_path="."):
        self.root_path = root_path
        self.history_path = os.path.join(root_path, ".agent", "skills", "agencia-desarrollo", "history")
        os.makedirs(self.history_path, exist_ok=True)

    def extract_db_schema(self):
        """Intenta extraer las tablas de la base de datos leyendo database.py"""
        schema = {}
        db_file = os.path.join(self.root_path, "database.py")
        if os.path.exists(db_file):
            with open(db_file, "r", encoding="utf-8") as f:
                content = f.read()
                # Buscar CREATE TABLE
                tables = re.findall(r'CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\)', content, re.DOTALL)
                for table_name, columns_raw in tables:
                    cols = [c.strip().split()[0] for c in columns_raw.split(",") if c.strip()]
                    schema[table_name] = cols
        return schema

    def detect_stack(self):
        """Detecta las tecnologías principales basadas en archivos presentes."""
        stack = []
        if os.path.exists(os.path.join(self.root_path, "requirements.txt")):
            stack.append("Python (requirements.txt)")
        if os.path.exists(os.path.join(self.root_path, "app.py")):
            stack.append("Flask/Python Web App")
        if os.path.exists(os.path.join(self.root_path, "package.json")):
            stack.append("Node.js/NPM")
        return stack

    def create_mission_plan(self, description):
        """Genera el plan de misión con contexto global y particular."""
        stack = self.detect_stack()
        db_schema = self.extract_db_schema()
        
        # Lógica de decisión de roles basada en la descripción
        roles = []
        if any(w in description.lower() for w in ["base de datos", "tabla", "sql", "guardar"]):
            roles.append({
                "titulo": "Arquitecto de Datos",
                "particular_context": "Tu objetivo es diseñar o modificar el esquema SQL. "
                                     "Debes asegurar que las relaciones sean íntegras y eficientes.",
                "archivos_impactados": ["database.py"]
            })
            
        if any(w in description.lower() for w in ["interfaz", "pantalla", "html", "css", "vista", "diseño"]):
            roles.append({
                "titulo": "Especialista Frontend",
                "particular_context": "Tu objetivo es crear interfaces hermosas y responsivas. "
                                     "Usa los templates de base y los estilos existentes para mantener consistencia.",
                "archivos_impactados": ["templates/"]
            })

        if not roles: # Default roles if nothing specific detected
            roles = [
                {"titulo": "Ingeniero Fullstack", "particular_context": "Encargado de la lógica end-to-end.", "archivos_impactados": ["app.py", "database.py"]}
            ]

        plan = {
            "timestamp": datetime.now().isoformat(),
            "mision": description,
            "global_context": {
                "stack_tecnologico": stack,
                "esquema_db_actual": db_schema,
                "reglas_generales": [
                    "Mantener el código limpio y documentado.",
                    "No borrar comentarios existentes.",
                    "Asegurar compatibilidad con el servidor Windows actual."
                ]
            },
            "specialists": roles,
            "qa_protocol": {
                "requires_user_approval": True,
                "verification_steps": [
                    "Verificar que los nuevos cambios no rompan las rutas existentes.",
                    "Validar que la base de datos se migre correctamente si hay cambios.",
                    "Comprobar la responsividad de la UI."
                ]
            }
        }
        
        # Guardar en historial
        hist_file = os.path.join(self.history_path, f"mission_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=4)
            
        return plan

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Falta la descripción de la misión."}))
        return
        
    mision = sys.argv[1]
    director = Director()
    plan = director.create_mission_plan(mision)
    
    # Imprimir JSON para que el agente lo lea
    print(json.dumps(plan, indent=4))

if __name__ == "__main__":
    main()
