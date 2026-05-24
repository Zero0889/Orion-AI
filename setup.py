import subprocess
import sys

print("Instalando dependencias...")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

print("Instalando navegadores de Playwright...")
subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)

print("\n✅ ¡Configuración completada! Ejecuta 'python main.py' para iniciar ORION.")
