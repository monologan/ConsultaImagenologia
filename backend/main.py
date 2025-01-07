# Backend (main.py)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import pyodbc
from fpdf import FPDF
from pydantic import BaseModel
from typing import List
import os

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de la conexión a SQL Server
DB_CONNECTION = {
    'driver': '{SQL Server}',
    'server': '192.168.42.241',
    'database': 'interlab',
    'uid': 'HRCV',
    'pwd': 'HRCV'
    #'trusted_connection': 'yes'
}

#############test conexion

@app.get("/test-connection")
async def test_connection():
    try:
        conn = pyodbc.connect(**DB_CONNECTION)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")  # Simple query to test connection
        result = cursor.fetchone()
        
        return {
            "status": "success",
            "message": "Conexión establecida correctamente",
            "details": {
                "server": DB_CONNECTION['server'],
                "database": DB_CONNECTION['database']
            }
        }
    except pyodbc.Error as e:
        return {
            "status": "error",
            "message": "Error de conexión",
            "error": str(e)
        }
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

class Record(BaseModel):
    cedula: str
    # Agregar aquí los demás campos de tu vista

@app.get("/api/records/{cedula}")
async def get_records(cedula: str):
    try:
        conn = pyodbc.connect(**DB_CONNECTION)
        cursor = conn.cursor()
        
        # Ajusta la consulta según tu vista
        query = """
            SELECT nombreordenes, factnumero, numeroidentificacion, concat(primernombre , segundonombre, primerapellido, segundoapellido) as Nombre, nombreresultado FROM resultadolocal  WITH (NOLOCK) WHERE numeroidentificacion = ? 
        """
        cursor.execute(query, cedula)
        
        columns = [column[0] for column in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
            
        return {"data": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/pdf/{cedula}")
async def generate_pdf(cedula: str):
    try:
        # Obtener los datos
        records = await get_records(cedula)
        
        # Crear PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        # Agregar contenido al PDF
        pdf.cell(200, 10, txt=f"Reporte para cédula: {cedula}", ln=1, align='C')
        
        for record in records["data"]:
            for key, value in record.items():
                pdf.cell(200, 10, txt=f"{key}: {value}", ln=1, align='L')
        
        # Crear directorio para PDFs si no existe
        os.makedirs("pdfs", exist_ok=True)
        
        # Guardar PDF
        filename = f"pdfs/reporte_{cedula}.pdf"
        pdf.output(filename)
        
        # Retornar el archivo PDF directamente
        return FileResponse(
            path=filename,
            filename=f"reporte_{cedula}.pdf",
            media_type="application/pdf"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))