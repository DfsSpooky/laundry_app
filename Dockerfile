# Dockerfile
# Esto le dice a Docker qué "materiales" base usar (Python 3.11)
FROM python:3.11-slim

# Evita que Python genere archivos basura (.pyc) y asegura que los logs se vean al instante
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Crea una carpeta dentro de nuestra "caja" para meter la aplicación
WORKDIR /app

# Copia solo el archivo de requerimientos e instala las dependencias primero.
# Esto es un truco para que las futuras construcciones sean más rápidas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ahora sí, copia todo el resto del proyecto a la carpeta /app dentro de la "caja"
COPY . .

# Este comando recolecta todos los archivos estáticos (CSS, JS) en una sola carpeta
RUN python manage.py collectstatic --no-input