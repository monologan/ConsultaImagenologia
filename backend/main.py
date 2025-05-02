# Backend (main.py)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
import mysql.connector
import pyodbc
from fpdf import FPDF
from pydantic import BaseModel
from typing import List
import os
from textwrap import wrap
from datetime import datetime

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
# DB connection for RX system
DB_CONNECTION_RX = {
    'host': '186.118.137.244',
    'port': 3306,
    'database': 'DBIMGDIAG',
    'user': 'hrcv',
    'password': 'vcfsS8f8LGuQJxM7'
}
# Test conexion
@app.get("/test-connection")
async def test_connection():
    conn = None
    cursor = None
    try:
        # Intentar establecer la conexión con MySQL
        conn = mysql.connector.connect(**DB_CONNECTION_RX)
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")  # Consulta para obtener la versión de MySQL
        result = cursor.fetchone()
        
        return {
            "status": "success",
            "message": "Conexión establecida correctamente",
            "details": {
                "server": DB_CONNECTION_RX['host'],
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
# Add a new endpoint to get RX records
@app.get("/api/rx-records")
async def get_rx_records(cedula:str = None, nombre:str = None):
    try:
        if not all([cedula, nombre]):
            raise HTTPException(
                status_code=400, 
                detail="Se requieren todos los campos: cédula, nombre"
            )
        
        conn = mysql.connector.connect(**DB_CONNECTION_RX)
        cursor = conn.cursor(dictionary=True)

        # Consulta para obtener datos de radiología
        query = '''
            SELECT NOMBRE_PACIENTE, ID_PACIENTE FROM DBIMGDIAG.HRCV AS h  
            WHERE
                NOMBRE_PACIENTE = %s
                AND ID_PACIENTE = %s
            LIMIT 20    
        '''
        
        cursor.execute(query, (nombre, cedula))
        results = cursor.fetchall()
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail="No se encontraron registros de radiología con los datos proporcionados"
            )
            
        return {"data": results}
    
    except mysql.connector.Error as e:
        error_message = str(e)
        if "Access denied" in error_message:
            raise HTTPException(status_code=401, detail="Error de autenticación en la base de datos de radiología")
        elif "Can't connect" in error_message:
            raise HTTPException(status_code=503, detail="No se puede conectar al servidor de radiología")
        else:
            raise HTTPException(status_code=500, detail=f"Error de MySQL: {error_message}")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

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
                ORDENES.horaordenamiento as horaOrd,
                ORDENES.horatomamuestra as horaToma,
                ORDENES.epsnombre as EPS,
                resultados.usuariovalida as Bacteriologo,
                ordenes.medico as Profesional,
                resultados.resultado as Resultado,
                CONVERT(varchar, fechavalida, 103) fechavalida,
                CONVERT(varchar, fechavalida, 108) horavalida,                
                ordenes.edad,
                resultados.unidades as Unidad, 
                concat(RESULTADOS.VALORREFERENCIAMIN, ' - ', RESULTADOS.VALORREFERENCIAMAX ) AS ValorRef,
                NUMEROIDENTIFICACION as Documento,
                CONCAT(primernombre, ' ', segundonombre, ' ', primerapellido, ' ', segundoapellido) as Nombre,
                ORDENES.FACTNUMERO,
                ORDENES.CONSELABO,
                ORDENES.CONSECUTIVO,
                FECHATOMAMUESTRA,
                CASE
                    resultado WHEN 'MEMO' 
                THEN COMENTARIORESU
                ELSE RESULTADO
                END resultado
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
                resultados.nombreexamen,
                resultados.usuariovalida,
                ORDENES.horaordenamiento,
                ORDENES.horatomamuestra,
                ORDENES.epsnombre
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
        pdf = FPDF(orientation="P", unit="mm", format="Letter")
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
        pdf.ln(5)
        # Agregar fecha y hora de impresión
        fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        pdf.set_font("Arial", "B", 8)
        pdf.set_text_color(50, 48, 129)
        pdf.cell(0, 5, f"Fecha de Impresión: {fecha_actual}", ln=True, align="L")
        
        pdf.ln(2)
        # Información del paciente
        pdf.set_font("Arial", "B", 12)
        pdf.set_fill_color(240, 240, 240)  # Light gray background
        pdf.set_text_color(0, 0, 0)
        selected_record = records_response["data"][request.selectedIndices[0]]
        selected_factnumero = selected_record['FACTNUMERO']
        selected_conselabo = selected_record['CONSELABO']
        selected_consecutivo = selected_record['CONSECUTIVO']
        
        # Keep labels bold but make values regular
        pdf.cell(45, 5, f"Paciente: ", 0, 0, 'L', True)
        pdf.set_font("Arial", "", 8)
        pdf.cell(80, 5, f"{selected_record['Nombre']}", 0, 0, 'L', True)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(45, 5, f"Documento: ", 0, 0, 'L', True)
        pdf.set_font("Arial", "", 8)
        pdf.cell(0, 5, f"{selected_record['Documento']}", 0, 1, 'L', True)
        
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(45, 5, f"EAPBS: ", 0, 0, 'L', True)
        pdf.set_font("Arial", "", 8)
        pdf.cell(80, 5, f"{selected_record['EPS']}", 0, 0, 'L', True)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(45, 5, f"Fecha de Ingreso: ", 0, 0, 'L', True)
        pdf.set_font("Arial", "", 8)
        pdf.cell(0, 5, f"{selected_record['Fecha']}", 0, 1, 'L', True)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(45, 5, f"Profesional: ", 0, 0, 'L', True)
        pdf.set_font("Arial", "", 8)
        pdf.cell(80, 5, f"{selected_record['Profesional']}", 0, 0, 'L', True)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(45, 5, f"Edad: ", 0, 0, 'L', True)
        pdf.set_font("Arial", "", 8)
        pdf.cell(0, 5, f"{selected_record['edad']}", 0, 1, 'L', True)

        pdf.set_font("Arial", "B", 12)
        pdf.cell(45, 5, f"Fecha de Validacion: ", 0, 0, 'L', True)
        pdf.set_font("Arial", "", 8)
        pdf.cell(80, 5, f"{selected_record['fechavalida']} {selected_record['horavalida']}", 0, 0, 'L', True)
        
        pdf.set_font("Arial", "B", 12)
        pdf.cell(45, 5, f"Orden: ", 0, 0, 'L', True)
        pdf.set_font("Arial", "", 8)
        pdf.cell(0, 5, f"{selected_record['FACTNUMERO']}", 0, 1, 'L', True)
        
        pdf.ln(5)
        # Resultados
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, f"Resultados del examen: {selected_record['NombreExamen']}", ln=True)
        pdf.ln(5)
        # Encabezados de la tabla
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(143, 188, 139)  # Light gray background
        pdf.set_text_color(0, 0, 0)
        pdf.cell(100, 7, "Prueba", 0, 0, 'L', True)
        pdf.cell(55, 7, "Resultado",0, 0, 'L', True)
        pdf.cell(20, 7, "Unidad",0, 0, 'C', True)
        pdf.cell(21, 7, "Valor Ref.",0, 1, 'C', True)
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
            # Check if we need a new page before printing each row
            if pdf.get_y() > 250:  # Leave space for signature
                pdf.add_page()
                # Re-add headers
                pdf.set_font("Arial", "B", 10)
                pdf.set_fill_color(143, 188, 139)
                pdf.cell(100, 7, "Prueba", 0, 0, 'C', True)
                pdf.cell(55, 7, "Resultado",0, 0, 'C', True)
                pdf.cell(20, 7, "Unidad",0, 0, 'C', True)
                pdf.cell(21, 7, "Valor Ref.",0, 1, 'C', True)
                pdf.set_font("Arial", "", 8)
            
            # Define the width of the "Resultado" column and the maximum length for each line
            resultado_width = 55  # Width of the multi_cell
            max_line_length = resultado_width - 0  # 2px shorter than the width

            # Split the "Resultado" text into lines that fit within the column width
            wrapped_lines = wrap(result['resultado'].strip(), width=max_line_length // 2)  # Adjust width as needed

            # Determine the height of each line and the total height of the wrapped content
            line_height = 4
            wrapped_height = len(wrapped_lines) * line_height

            # Determine the maximum height for the row
            row_height = max(7, wrapped_height)

            # Draw the first cell (Prueba)
            pdf.cell(100, row_height, result['Prueba'], 0, 0, 'L')

            # Save the current X and Y positions
            x_after_prueba = pdf.get_x()
            y_start = pdf.get_y()

            # Iterate through the wrapped lines and render them as separate cells
            pdf.set_xy(x_after_prueba, y_start)
            for line in wrapped_lines:
                pdf.cell(resultado_width, line_height, line, 0, 2, 'L')  # Move to the next line after each cell

            # Move back to the starting Y position for the next cells
            pdf.set_xy(x_after_prueba + resultado_width, y_start)

            # Draw the remaining cells with the same row height
            pdf.cell(20, row_height, result['Unidad'], 0, 0, 'C')
            pdf.cell(21, row_height, result['ValorRef'], 0, 1, 'C')

        # Check if we need a new page for signature
        if pdf.get_y() > 220:  # If less than ~3cm from bottom
            pdf.add_page()
        
        # Añadir espacio para la firma
        pdf.ln(20)  # Espacio antes de la firma
        
        # Buscar la firma del bacteriólogo
        bacteriologo = selected_record['Bacteriologo']
        # Buscar firma en diferentes formatos de imagen
        signature_found = False
        
        # Mover a la posición calculada para la firma
        # pdf.set_y(signature_y)
        
        for ext in ['.png', '.jpg', '.jpeg']:
            firma_path = os.path.join(os.path.dirname(__file__), "static", "firmas", f"{bacteriologo}{ext}")
            if os.path.exists(firma_path):
                # Añadir la firma como imagen
                pdf.image(firma_path, x=10, y=pdf.get_y(), w=50)
                pdf.ln(15)  # Espacio después de la firma
                signature_found = True
                break
        
        # Si no se encuentra la firma, solo mostrar la línea
        if not signature_found:
            pdf.ln(10)  # Menos espacio si no hay firma
            
        # Añadir línea para la firma
        pdf.line(10, pdf.get_y(), 60, pdf.get_y())
        
        # Añadir nombre del bacteriólogo bajo la línea
        pdf.set_font("Arial", "B", 10)
        #pdf.cell(80, 5, f"{bacteriologo}", 0, 1, 'L')
        pdf.set_font("Arial", "", 8)
        pdf.cell(80, 5, "Bacteriólogo", 0, 1, 'L')
        
        # Continuar con el código existente para generar el PDF
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