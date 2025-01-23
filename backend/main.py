# Backend (main.py)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
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
    'database': 'HOSPIVISUAL',
    'uid': 'HRCV',
    'pwd': 'HRCV'
    #'trusted_connection': 'yes'
}
# Test conexion
@app.get("/test-connection")
async def test_connection():
    conn = None
    cursor = None
    try:
        # Intentar establecer la conexión
        conn = pyodbc.connect(**DB_CONNECTION)
        cursor = conn.cursor()
        cursor.execute("SELECT @@version")  # Consulta más informativa que retorna la versión de SQL Server
        result = cursor.fetchone()
        
        return {
            "status": "success",
            "message": "Conexión establecida correctamente",
            "details": {
                "server": DB_CONNECTION['server'],
                "database": DB_CONNECTION['database'],
                "sql_version": result[0] if result else None
            }
        }
    except pyodbc.Error as e:
        # Manejo más específico del error
        error_message = str(e)
        if "Login failed" in error_message:
            error_detail = "Error de autenticación: Verifique las credenciales (uid/pwd)"
        elif "Cannot connect to server" in error_message:
            error_detail = "No se puede conectar al servidor: Verifique la dirección IP y que el servidor esté activo"
        else:
            error_detail = error_message
            
        return {
            "status": "error",
            "message": "Error de conexión",
            "error": error_detail
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

class Record(BaseModel):
    cedula: str    
    # Agregar aquí los demás campos de tu vista
@app.get("/api/records")
async def get_records(cedula: str = None, factura: str = None):
    try:
        if not cedula and not factura:
            raise HTTPException(status_code=400, detail="Se requiere cédula o número de factura")
        
        conn = pyodbc.connect(**DB_CONNECTION)
        cursor = conn.cursor()
              
        query = '''SELECT  FORMAT(FECHATOMAMUESTRA, 'yyyy-MM-dd') as 'Fecha Toma', NOMBREordenes as 'Tipo Examen',
            concat(primernombre+' ', segundonombre+' ', primerapellido+' ', segundoapellido) as Nombre
        FROM INTERLAB.dbo.resultadolocal rl WITH (NOLOCK)
            INNER JOIN HOSPIVISUAL.dbo.factura f WITH (NOLOCK) 
                ON rl.FACTNUMERO = f.factnumero
        WHERE 
            (rl.numeroidentificacion = ? OR ? IS NULL)
            AND (f.factnumero = ? OR ? IS NULL)

        group by FECHATOMAMUESTRA, NOMBREordenes, concat(primernombre+' ', segundonombre+' ', primerapellido+' ', segundoapellido)
        '''

        cursor.execute(query, cedula, cedula, factura, factura)
        
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

class PDFRequest(BaseModel):
    selectedIndices: List[int]

@app.post("/api/pdf/{cedula}")
async def generate_pdf(cedula: str, request: PDFRequest):
    try:
        # Obtener los datos
        records = await get_records(cedula)
        
        # Filter records based on selectedIndices
        filtered_records = {"data": [records["data"][i] for i in request.selectedIndices]}
        
        # Create PDF using filtered records
        pdf = FPDF()
        pdf.add_page()
        
        # Configuración de la página
        page_width = pdf.w
        
        # Agregar logo
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            logo_path = os.path.join(current_dir, 'static', 'logo.jpg')
            
            if os.path.exists(logo_path):
                # Dimensiones y posicionamiento del logo
                logo_width = 50  # ancho en mm
                logo_height = 30  # altura en mm
                x_position = (page_width - logo_width) / 2
                
                pdf.image(logo_path, x=x_position, y=10, w=logo_width, h=logo_height)
                pdf.ln(25)  # Espacio después del logo
            else:
                print(f"Logo no encontrado en: {logo_path}")
        except Exception as e:
            print(f"Error al cargar el logo: {str(e)}")
         
        # Título del reporte
        pdf.set_font("Arial", 'B', size=14)
        pdf.cell(200, 10, txt="Reporte de Resultados", ln=1, align='C')
        
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Cédula: {cedula}", ln=1, align='C')
        pdf.ln(5) 
        
        # Crear tabla
        if filtered_records["data"]:
            # Encabezados de la tabla
            pdf.set_font("Arial", 'B', size=10)
            headers = list(filtered_records["data"][0].keys())
            col_width = page_width / len(headers)
            
            for header in headers:
                pdf.cell(col_width, 10, header, 1, 0, 'C')
            pdf.ln()
            
            # Datos de la tabla
            pdf.set_font("Arial", size=8)
            for record in filtered_records["data"]:
                for value in record.values():
                    value_str = str(value) if value is not None else ''
                    pdf.cell(col_width, 10, value_str, 1, 0, 'C')
                pdf.ln()
        
        
        # En lugar de guardar en archivo, obtener el PDF en memoria
        pdf_content = pdf.output(dest='S').encode('latin-1')
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=reporte_{cedula}.pdf"
            }
        )
        
    except Exception as e:
        print(f"Error generando PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))