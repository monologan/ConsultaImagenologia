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
# DB connection for LAB system
DB_CONNECTION_LAB = {
    'driver': '{SQL Server}',
    'server': '192.168.42.162\MSSQLENTERPRISE',
    'database': 'interlab',
    'uid': 'interlab',
    'pwd': 'Interlab2019'
}
# Test conexion
@app.get("/test-connection")
async def test_connection():
    conn = None
    cursor = None
    try:
        # Intentar establecer la conexión
        conn = pyodbc.connect(**DB_CONNECTION_LAB)
        cursor = conn.cursor()
        cursor.execute("SELECT @@version")  # Consulta más informativa que retorna la versión de SQL Server
        result = cursor.fetchone()
        
        return {
            "status": "success",
            "message": "Conexión establecida correctamente",
            "details": {
                "server": DB_CONNECTION_LAB['server'],
                "database": DB_CONNECTION_LAB['database'],
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

            # Test conexion labo

class Record(BaseModel):
    cedula: str    
    # Agregar aquí los demás campos de tu vista
@app.get("/api/records")
async def get_records(cedula: str = None, fechanacimiento: str = None, tipocodigo: str = None):
    try:
        if not any([cedula, fechanacimiento, tipocodigo]):
            raise HTTPException(
                status_code=400, 
                detail="Se requiere al menos uno de los siguientes campos: cédula, fecha de nacimiento o tipo de código"
            )
        
        conn = pyodbc.connect(**DB_CONNECTION_LAB)
        cursor = conn.cursor()
              
        query = '''
        SELECT
            CONVERT(varchar, FECHATOMAMUESTRA, 103) as Fecha,
            ORDENES.NOMBREEXAMEN as NombreExamen, 
            resultados.resultado as Resultado,
            resultados.unidades as Unidad,
            NUMEROIDENTIFICACION as Documento,
            CONCAT(primernombre, ' ', segundonombre, ' ', primerapellido, ' ', segundoapellido) as Nombre
        FROM
            ORDENES WITH (NOLOCK)
        INNER JOIN RESULTADOS WITH (NOLOCK) ON
            RESULTADOS.FACTNUMERO = ORDENES.FACTNUMERO
            and ordenes.CONSELABO = resultados.CONSELABO
	        and ordenes.CONSECUTIVO = resultados.CONSECUTIVO
        WHERE
            NUMEROIDENTIFICACION = ?
        GROUP BY
            ORDENES.NOMBREEXAMEN,            
            resultados.resultado,
            resultados.unidades,
            FECHATOMAMUESTRA,
            NUMEROIDENTIFICACION,
            CONCAT(primernombre, ' ', segundonombre, ' ', primerapellido, ' ', segundoapellido)
        ORDER BY
        	ORDENES.NOMBREEXAMEN,
            FECHATOMAMUESTRA DESC
            
        '''

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

class PDFRequest(BaseModel):
    selectedIndices: List[int]
@app.post("/api/pdf/{cedula}")
async def generate_pdf(cedula: str, request: PDFRequest):
    try:
        # Obtener los datos
        records = await get_records(cedula)
        if not records["data"] or not request.selectedIndices:
            raise HTTPException(status_code=400, detail="No se encontraron registros")
        
        # Obtener el primer registro seleccionado para identificar el examen
        first_selected = records["data"][request.selectedIndices[0]]
        exam_name = first_selected["NombreExamen"]
        
        # Filtrar todos los resultados que correspondan a ese examen
        exam_records = [
            record for record in records["data"] 
            if record["NombreExamen"] == exam_name
        ]
        
        # Ordenar por fecha (más reciente primero)
        exam_records.sort(key=lambda x: x["Fecha"], reverse=True)
        
        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        page_width = pdf.w
        
        # Add logo
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            logo_path = os.path.join(current_dir, 'static', 'logo.jpg')
            
            if os.path.exists(logo_path):
                logo_width = 50
                logo_height = 30
                x_position = (page_width - logo_width) / 2
                pdf.image(logo_path, x=x_position, y=10, w=logo_width, h=logo_height)
                pdf.ln(35)
        except Exception as e:
            print(f"Error al cargar el logo: {str(e)}")

        # Header information
        pdf.set_font("Arial", 'B', size=12)
        pdf.cell(0, 10, f"HISTORIAL DE RESULTADOS - {exam_name}", ln=True, align='C')
        pdf.ln(5)

        # Patient information
        pdf.set_font("Arial", size=10)
        pdf.cell(40, 8, "Documento:", 0, 0)
        pdf.cell(60, 8, cedula, 0, 0)
        pdf.cell(40, 8, "Paciente:", 0, 0)
        pdf.cell(50, 8, exam_records[0].get("Nombre", ""), 0, 1)
        pdf.ln(5)

        # Define columns and widths
        columns = ["Fecha", "Resultado","Unidad"]
        headers = ["Fecha", "Resultado", "Unidad"]
        col_widths = [50, 70, 70]  # Ajustados para mejor visualización

        # Table headers
        pdf.set_font("Arial", 'B', size=8)
        for header, width in zip(headers, col_widths):
            pdf.cell(width, 10, header, 1, 0, 'C')
        pdf.ln()

        # Table content
        pdf.set_font("Arial", size=8)
        for record in exam_records:
            for col, width in zip(columns, col_widths):
                value = str(record.get(col, "")) if record.get(col) is not None else ""
                # Ajustar la alineación según el tipo de dato
                align = 'C' if col == "Fecha" else 'L'
                pdf.cell(width, 8, value, 1, 0, align)
            pdf.ln()

        # Add observations if any
        pdf.ln(5)
        pdf.set_font("Arial", 'B', size=10)
        pdf.cell(0, 8, "Observaciones:", 0, 1)
        pdf.set_font("Arial", size=9)
        for record in exam_records:
            obs = record.get("labobservaciones", "")
            if obs and obs != "null":
                pdf.multi_cell(0, 5, obs)

        # Get PDF content
        pdf_content = pdf.output(dest='S').encode('latin-1')
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=historial_{exam_name}_{cedula}.pdf"
            }
        )
        
    except Exception as e:
        print(f"Error generando PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))