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
    allow_origins=["http://localhost:3000"],  # Update this
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
        if not all([cedula, fechanacimiento, tipocodigo]):
            raise HTTPException(
                status_code=400, 
                detail="Se requieren todos los campos: cédula, fecha de nacimiento y tipo de código"
            )
        
        conn = pyodbc.connect(**DB_CONNECTION_LAB)
        cursor = conn.cursor()

        # Primero verificamos que los datos coincidan
        validation_query = '''
        SELECT COUNT (*)
        FROM ORDENES WITH (NOLOCK)
        INNER JOIN RESULTADOS WITH (NOLOCK) ON 
            RESULTADOS.FACTNUMERO = ORDENES.FACTNUMERO
        WHERE 
            ORDENES.NUMEROIDENTIFICACION = ? 
            AND YEAR(ORDENES.FECHANACIMIENTO) = ?
            AND ORDENES.TIPOIDENTIFICACION = ?
        '''
        
        cursor.execute(validation_query, (cedula, fechanacimiento, tipocodigo))
        count = cursor.fetchone()[0]

        if count == 0:
            raise HTTPException(
                status_code=404,
                detail="No se encontraron registros con los datos proporcionados o los datos no coinciden"
            )
        
        # Si los datos son válidos, continuamos con la consulta original
        # if full_data:
        query = '''
            SELECT DISTINCT
                CONVERT(varchar, FECHATOMAMUESTRA, 103) as Fecha,
                ORDENES.NOMBREEXAMEN as NombreExamen,
                resultados.nombreexamen as Prueba,
                resultados.resultado as Resultado,
                resultados.unidades as Unidad, 
                concat(RESULTADOS.VALORREFERENCIAMIN, ' - ', RESULTADOS.VALORREFERENCIAMAX ) AS ValorRef,
                NUMEROIDENTIFICACION as Documento,
                CONCAT(primernombre, ' ', segundonombre, ' ', primerapellido, ' ', segundoapellido) as Nombre,
                ORDENES.FACTNUMERO,
                ORDENES.CONSELABO,
                ORDENES.CONSECUTIVO,
                FECHATOMAMUESTRA
            FROM
                ORDENES WITH (NOLOCK)
            INNER JOIN RESULTADOS WITH (NOLOCK) ON
                RESULTADOS.FACTNUMERO = ORDENES.FACTNUMERO
                and ordenes.CONSELABO = resultados.CONSELABO
                and ordenes.CONSECUTIVO = resultados.CONSECUTIVO
            WHERE
                ORDENES.NUMEROIDENTIFICACION = ?
                AND YEAR(ORDENES.FECHANACIMIENTO) = ?
                AND ORDENES.TIPOIDENTIFICACION = ?
            ORDER BY
                FECHATOMAMUESTRA DESC,
                ORDENES.NOMBREEXAMEN,
                resultados.nombreexamen
            '''
        # else:
        #     query = '''
        #     SELECT
        #         CONVERT(varchar, FECHATOMAMUESTRA, 103) as Fecha,
        #         ORDENES.NOMBREEXAMEN as NombreExamen,
        #         MAX(resultados.nombreexamen) as Prueba,
        #         MAX(resultados.resultado) as Resultado,
        #         MAX(resultados.unidades) as Unidad,
        #         MAX(concat(RESULTADOS.VALORREFERENCIAMIN, ' - ', RESULTADOS.VALORREFERENCIAMAX )) AS ValorRef,
        #         ORDENES.NUMEROIDENTIFICACION as Documento,
        #         MAX(CONCAT(primernombre, ' ', segundonombre, ' ', primerapellido, ' ', segundoapellido)) as Nombre,
        #         ORDENES.FACTNUMERO,
        #         ORDENES.CONSELABO,
        #         ORDENES.CONSECUTIVO,
        #         FECHATOMAMUESTRA
        #     FROM
        #         ORDENES WITH (NOLOCK)
        #     INNER JOIN RESULTADOS WITH (NOLOCK) ON
        #         RESULTADOS.FACTNUMERO = ORDENES.FACTNUMERO
        #         and ordenes.CONSELABO = resultados.CONSELABO
        #         and ordenes.CONSECUTIVO = resultados.CONSECUTIVO
        #     WHERE
        #         ORDENES.NUMEROIDENTIFICACION = ?
        #         AND YEAR(ORDENES.FECHANACIMIENTO) = ?
        #         AND ORDENES.TIPOIDENTIFICACION = ?
        #     GROUP BY
        #         FECHATOMAMUESTRA,
        #         ORDENES.NOMBREEXAMEN,
        #         ORDENES.NUMEROIDENTIFICACION,
        #         ORDENES.FACTNUMERO,
        #         ORDENES.CONSELABO,
        #         ORDENES.CONSECUTIVO
        #     ORDER BY
        #         FECHATOMAMUESTRA DESC,
        #         ORDENES.NOMBREEXAMEN
        #     '''

        cursor.execute(query, (cedula, fechanacimiento, tipocodigo))
        
        columns = [column[0] for column in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
            
        return {"data": results}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

class PDFRequest(BaseModel):
    selectedIndices: List[int]
@app.post("/api/pdf/{cedula}")
async def generate_pdf(
    request: PDFRequest, 
    cedula: str,
    fechanacimiento: str = None,
    tipocodigo: str = None
):
    try:
        print(f"Recibiendo solicitud PDF con parámetros:", {
            "cedula": cedula,
            "fechanacimiento": fechanacimiento,
            "tipocodigo": tipocodigo,
            "selectedIndices": request.selectedIndices if request else None
        })

        # Validaciones iniciales...
        if not all([cedula, fechanacimiento, tipocodigo]):
            raise HTTPException(status_code=400, detail="Faltan parámetros requeridos")

        # Obtener registros
        records_response = await get_records(
            cedula=cedula,
            fechanacimiento=fechanacimiento,
            tipocodigo=tipocodigo,
        )

        if not records_response.get("data"):
            raise HTTPException(status_code=404, detail="No se encontraron registros")

        # Crear PDF
        pdf = FPDF()
        pdf.add_page()
        
        # Agregar logo al PDF
        logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.jpg")
        if os.path.exists(logo_path):
            # SVG no es soportado directamente por FPDF, usar un formato compatible como PNG o JPG
            # Si tienes el logo en PNG o JPG, usa esa ruta en lugar de SVG
            pdf.image(logo_path, x=3, y=8, w=60)
        
        # Configurar fuente
        pdf.set_font("Arial", "B", 16)
        
        # Título
        pdf.cell(0, 10, "Resultados de Laboratorio", ln=True, align="C")
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(193, 229, 252)
        pdf.set_text_color(25, 48, 129)
        pdf.cell(0, 5, "Laboratorio Clinico", ln=True, align="R")
        pdf.cell(0, 5, "Nit: 82200831-5", ln=True, align="R")
        pdf.cell(0, 5, "CALLE 20 # 14-45  Tel:6022317323 - 3167717018", ln=True, align="R")
        pdf.cell(0, 5, "TULUA VALLE DEL CAUCA", ln=True, align="R")
        pdf.ln(2)
        # Información del paciente
        pdf.set_font("Arial", "B", 12)
        pdf.set_fill_color(240, 240, 240)  # Light gray background
        pdf.set_text_color(0, 0, 0)
        selected_record = records_response["data"][request.selectedIndices[0]]
        selected_factnumero = selected_record['FACTNUMERO']
        selected_conselabo = selected_record['CONSELABO']
        selected_consecutivo = selected_record['CONSECUTIVO']
        
        pdf.cell(0, 5, f"Paciente: {selected_record['Nombre']}",0, 1, 'L', True)
        pdf.cell(0, 5, f"Documento: {selected_record['Documento']}",0, 1, 'L', True)
        pdf.cell(0, 5, f"Fecha: {selected_record['Fecha']}",0, 1, 'L', True)
        pdf.ln(5)
        # Resultados
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, f"Resultados del examen: {selected_record['NombreExamen']}", ln=True)
        pdf.ln(5)
        # Encabezados de la tabla
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(143, 188, 139)  # Light gray background
        pdf.set_text_color(0, 0, 0)
        pdf.cell(115, 7, "Prueba", 0, 0, 'C', True)
        pdf.cell(25, 7, "Resultado",0, 0, 'C', True)
        pdf.cell(25, 7, "Unidad",0, 0, 'C', True)
        pdf.cell(25, 7, "Valor Ref.",0, 0, 'C', True)
        pdf.ln()
        # Datos de la tabla
        pdf.set_font("Arial", "", 8)
        # Filtrar los registros que corresponden al examen seleccionado
        selected_index = request.selectedIndices[0]
        selected_record = records_response["data"][selected_index]
        
        # Print debug info
        print(f"Selected index: {selected_index}")
        print(f"Selected record: {selected_record['NombreExamen']}, FACTNUMERO: {selected_record['FACTNUMERO']}")
        
        # Get the unique identifiers for this record
        selected_factnumero = selected_record['FACTNUMERO']
        selected_conselabo = selected_record['CONSELABO']
        selected_consecutivo = selected_record['CONSECUTIVO']
        selected_fecha = selected_record['FECHATOMAMUESTRA']
        
        # Get all results for this specific exam
        exam_results = []
        seen_pruebas = set()  # To avoid duplicate tests
        
        for r in records_response["data"]:
            if (r['FACTNUMERO'] == selected_factnumero and
                r['CONSELABO'] == selected_conselabo and
                r['CONSECUTIVO'] == selected_consecutivo and
                r['NombreExamen'] == selected_record['NombreExamen']):
                
                # Only add if we haven't seen this test before
                if r['Prueba'] not in seen_pruebas:
                    seen_pruebas.add(r['Prueba'])
                    exam_results.append(r)
        
        # Debug info
        print(f"Found {len(exam_results)} unique tests for this exam")
        
        # Ordenar los resultados por fecha de toma de muestra
        exam_results.sort(key=lambda x: x['FECHATOMAMUESTRA'], reverse=True)
        # Imprimir todas las pruebas del examen
        for result in exam_results:
            pdf.cell(115, 7, result['Prueba'], 0)
            pdf.cell(25, 7, result['Resultado'], 0)
            pdf.cell(25, 7, result['Unidad'], 0)
            pdf.cell(25, 7, result['ValorRef'], 0)
            pdf.ln()
        
        # Generar el contenido del PDF
        try:
            pdf_content = pdf.output(dest='S').encode('latin-1')
        except Exception as e:
            print(f"Error al generar el PDF: {str(e)}")
            raise HTTPException(status_code=500, detail="Error al generar el PDF")
        
        # Retornar el PDF
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=resultado_{cedula}.pdf",
                "Access-Control-Expose-Headers": "Content-Disposition",
                "Access-Control-Allow-Origin": "*"
            }
        )

    except HTTPException as he:
        print(f"Error HTTP: {str(he.detail)}")
        raise he
    except Exception as e:
        print(f"Error inesperado: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error inesperado: {str(e)}"
        )