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
# Additional DB connection for LAB system
DB_CONNECTION_RX = {
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

            # Test conexion labo
@app.get("/test-connection_labo")
async def test_connection():
    conn = None
    cursor = None
    try:
        # Intentar establecer la conexión
        conn = pyodbc.connect(**DB_CONNECTION_RX)
        cursor = conn.cursor()
        cursor.execute("SELECT @@version")  # Consulta más informativa que retorna la versión de SQL Server
        result = cursor.fetchone()
        
        return {
            "status": "success",
            "message": "Conexión establecida correctamente",
            "details": {
                "server": DB_CONNECTION_RX['server'],
                "database": DB_CONNECTION_RX['database'],
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
async def get_records(cedula: str = None, fechanacimiento: str = None, tipocodigo: str = None):
    try:
        if not any([cedula, fechanacimiento, tipocodigo]):
            raise HTTPException(
                status_code=400, 
                detail="Se requiere al menos uno de los siguientes campos: cédula, fecha de nacimiento o tipo de código"
            )
        
        conn = pyodbc.connect(**DB_CONNECTION_RX)
        cursor = conn.cursor()
              
        query = '''
        SELECT
            CONVERT(varchar, FECHATOMAMUESTRA, 103) as Fecha,
            ORDENES.NOMBREEXAMEN as NombreExamen,
            NUMEROIDENTIFICACION as Documento,
            CONCAT(primernombre, ' ', segundonombre, ' ', primerapellido, ' ', segundoapellido) as Nombre
        FROM
            ORDENES WITH (NOLOCK)
        WHERE
            NUMEROIDENTIFICACION = ?
        GROUP BY
            FECHATOMAMUESTRA,
            ORDENES.NOMBREEXAMEN,
            NUMEROIDENTIFICACION,
            CONCAT(primernombre, ' ', segundonombre, ' ', primerapellido, ' ', segundoapellido)
        ORDER BY
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
@app.get("/api/rx-records")
async def get_rx_records(cedula: str = None, fechanacimiento: str = None, tipocodigo: str = None):
    try:
        if not any([cedula, fechanacimiento, tipocodigo]):
            raise HTTPException(
                status_code=400, 
                detail="Se requiere al menos uno de los siguientes campos: cédula, fecha de nacimiento o tipo de código"
            )
        
        conn = pyodbc.connect(**DB_CONNECTION_RX)
        cursor = conn.cursor()
              
        query = '''
        SELECT
            CONVERT(varchar, FECHATOMAMUESTRA, 103) as Fecha,
            SECCION as Descripcion,
            'LAB' AS Modalidad
        FROM
            ORDENES WITH (NOLOCK)
            INNER JOIN RESULTADOS WITH (NOLOCK) ON RESULTADOS.FACTNUMERO = ORDENES.FACTNUMERO 
        WHERE
            NUMEROIDENTIFICACION = ?
        GROUP BY
            SECCION,
            FECHATOMAMUESTRA
        ORDER BY
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
        filtered_records = {"data": [records["data"][i] for i in request.selectedIndices]}
        
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
            else:
                print(f"Logo no encontrado en: {logo_path}")
        except Exception as e:
            print(f"Error al cargar el logo: {str(e)}")

        # Header information
        if filtered_records["data"]:
            first_record = filtered_records["data"][0]
            pdf.set_font("Arial", 'B', size=12)
            pdf.cell(0, 10, "RESULTADOS DE LABORATORIO", ln=True, align='C')
            pdf.ln(5)

            # Patient information
            pdf.set_font("Arial", size=10)
            pdf.cell(40, 8, "Documento:", 0, 0)
            pdf.cell(60, 8, cedula, 0, 0)
            pdf.cell(40, 8, "fechanacimiento:", 0, 0)
            pdf.cell(50, 8, str(first_record.get("FACTNUMERO", "")), 0, 1)

            nombre_completo = (f"{first_record.get('primernombre', '')} {first_record.get('segundonombre', '')} "
                             f"{first_record.get('primerapellido', '')} {first_record.get('segundoapellido', '')}").strip()
            pdf.cell(40, 8, "Paciente:", 0, 0)
            pdf.cell(150, 8, nombre_completo, 0, 1)

            pdf.cell(40, 8, "Fecha Toma:", 0, 0)
            pdf.cell(60, 8, str(first_record.get("fechatomamuestra", "")), 0, 0)
            pdf.cell(40, 8, "Hora Toma:", 0, 0)
            pdf.cell(50, 8, str(first_record.get("horatomamuestra", "")), 0, 1)
            pdf.ln(5)

            # Results table
            pdf.set_font("Arial", 'B', size=8)
            # Define specific columns we want to show
            columns = ["NombreExamen", "Resultado", "Unidad", "ValorMin-ValorMax","FechaValidacion"]
            headers = ["Examen", "Resultado", "Unidades", "Valor Ref","Fecha Validacion"]
            col_widths = [90, 25, 25, 25, 25]  # Total should be close to page_width (190-200)

            # Table headers
            for header, width in zip(headers, col_widths):
                pdf.cell(width, 10, header, 1, 0, 'C')
            pdf.ln()

            # Table content
            pdf.set_font("Arial", size=6)
            for record in filtered_records["data"]:
                for col, width in zip(columns, col_widths):
                    value = str(record.get(col, "")) if record.get(col) is not None else ""
                    pdf.cell(width, 8, value, 1, 0, 'L')
                pdf.ln()

            # Add observations if any
            pdf.ln(5)
            pdf.set_font("Arial", 'B', size=10)
            pdf.cell(0, 8, "Observaciones:", 0, 1)
            pdf.set_font("Arial", size=9)
            for record in filtered_records["data"]:
                obs = record.get("labobservaciones", "")
                if obs and obs != "null":
                    pdf.multi_cell(0, 5, obs)

        # Get PDF content
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
@app.post("/api/rx-pdf/{cedula}")
async def generate_rx_pdf(cedula: str, request: PDFRequest):
    try:
        conn = pyodbc.connect(**DB_CONNECTION_RX)
        cursor = conn.cursor()
        
        query = '''
        SELECT
            CONVERT(varchar,
            FECHATOMAMUESTRA,
            103) as Fecha,
            SECCION as Descripcion,
            NUMEROIDENTIFICACION as Documento,
            RESULTADOS.NOMBREEXAMEN as Seccion,            
            RESULTADOS.CONSECUTIVO as Consecutivo,
            RESULTADOS.resultado as Resultado,
            RESULTADOS.unidades as Unidad,
            RESULTADOS.VALORREFERENCIAMIN as ValorMin,
            RESULTADOS.VALORREFERENCIAMAX as ValorMax,
            RESULTADOS.fechavalida as FechaValidacion,
            CONCAT(primernombre, ' ', segundonombre, ' ', primerapellido, ' ', segundoapellido) as NombreCompleto,
            ORDENES.NOMBREEXAMEN as OrdenExamen
            
        FROM
            ORDENES WITH (NOLOCK)
        INNER JOIN RESULTADOS WITH (NOLOCK) ON
            RESULTADOS.FACTNUMERO = ORDENES.FACTNUMERO
        WHERE
            NUMEROIDENTIFICACION = ? 
        group by
            SECCION,
            NUMEROIDENTIFICACION,
            RESULTADOS.NOMBREEXAMEN,
            RESULTADOS.CONSECUTIVO,
            RESULTADOS.resultado,
            RESULTADOS.unidades,
            RESULTADOS.VALORREFERENCIAMIN,
            RESULTADOS.VALORREFERENCIAMAX,
            RESULTADOS.fechavalida,
            FECHATOMAMUESTRA,
            CONCAT(primernombre, ' ', segundonombre, ' ', primerapellido, ' ', segundoapellido),
            ORDENES.NOMBREEXAMEN
                   
        order by resultados.NOMBREEXAMEN     
                
        '''        
        cursor.execute(query, cedula)
        results = cursor.fetchall()        
        # Group results by Consecutivo
        grouped_results = {}
        for record in results:
            key = record.Consecutivo  # Simplified key
            if key not in grouped_results:
                grouped_results[key] = []
            grouped_results[key].append(record)
            
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
            else:
                print(f"Logo no encontrado en: {logo_path}")
        except Exception as e:
            print(f"Error al cargar el logo: {str(e)}")

        # Header
        pdf.set_font("Arial", 'B', size=12)
        pdf.cell(0, 10, "RESULTADOS DE LABORATORIO", ln=True, align='C')
        pdf.ln(5)

        if results:
            first_record = results[0]
            # Patient information
            pdf.set_font("Arial", 'B', size=10)
            pdf.cell(40, 8, "Documento:", 0, 0)
            pdf.cell(60, 8, str(first_record.Documento), 0, 1)
            pdf.cell(40, 8, "Paciente:", 0, 0)
            pdf.cell(150, 8, str(first_record.NombreCompleto), 0, 1)
            pdf.ln(5)

            # Iterate through each group
            for consecutivo, group in grouped_results.items():  # Modified iteration
                # Add exam name and details for this group
                pdf.set_font("Arial", 'B', size=12)
                
                if group:  # Check if group has records
                    pdf.cell(0, 8, f"{group[0].Descripcion}", 0, 1, 'L')
                    pdf.cell(80, 8, f"{consecutivo} - {group[0].OrdenExamen}", 0, 1, 'L')

                pdf.ln(5)

                # Table headers
                pdf.set_font("Arial", 'B', size=10)
                headers = ["OrdenExamen","Prueba","Resultado", "Unidad", "Valor Min", "Valor Max", "Fecha Valid"]
                col_widths = [70,70, 20, 20, 20, 20, 30]

                for header, width in zip(headers, col_widths):
                    pdf.cell(width, 10, header, 1, 0, 'C')
                pdf.ln()

                # Table content for this group
                pdf.set_font("Arial", size=6)
                for record in group:
                    
                    
                    pdf.cell(70, 8, str(record.OrdenExamen), 1, 0, 'L')
                    pdf.cell(70, 8, str(record.Seccion), 1, 0, 'L')
                    pdf.cell(20, 8, str(record.Resultado), 1, 0, 'L')
                    pdf.cell(20, 8, str(record.Unidad), 1, 0, 'L')
                    pdf.cell(20, 8, str(record.ValorMin), 1, 0, 'L')
                    pdf.cell(20, 8, str(record.ValorMax), 1, 0, 'L')
                    pdf.cell(30, 8, str(record.FechaValidacion), 1, 0, 'L')
                    pdf.ln()
                
                pdf.ln(10)  # Add space between groups

        # Get PDF content
        pdf_content = pdf.output(dest='S').encode('latin-1')
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=reporte_rx_{cedula}.pdf"
            }
        )
        
    except Exception as e:
        print(f"Error generando PDF de RX: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()