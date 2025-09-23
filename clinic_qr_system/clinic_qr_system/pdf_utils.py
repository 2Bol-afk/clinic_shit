"""
PDF generation utilities for lab results and other documents.
"""
import io
import logging
from typing import Dict, Any, Optional
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("ReportLab not available. PDF generation will be disabled.")


def generate_lab_result_pdf(
    patient_name: str,
    patient_code: str,
    lab_type: str,
    lab_results: str,
    visit_id: int,
    completed_at: str,
    doctor_name: str = None,
    clinic_name: str = "Clinic QR System"
) -> Optional[bytes]:
    """
    Generate a PDF document for lab results.
    
    Args:
        patient_name: Patient's full name
        patient_code: Patient's unique code
        lab_type: Type of lab test performed
        lab_results: Lab test results text
        visit_id: Visit ID for reference
        completed_at: Date/time when lab was completed
        doctor_name: Name of the doctor who ordered the test
        clinic_name: Name of the clinic
        
    Returns:
        bytes: PDF content as bytes, or None if ReportLab is not available
    """
    if not REPORTLAB_AVAILABLE:
        logger.error("ReportLab not available. Cannot generate PDF.")
        return None
    
    try:
        # Create a BytesIO buffer to hold the PDF
        buffer = io.BytesIO()
        
        # Create the PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18
        )
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Create custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.darkblue
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=6
        )
        
        results_style = ParagraphStyle(
            'ResultsStyle',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            fontName='Courier',
            leftIndent=20
        )
        
        # Build the content
        story = []
        
        # Title
        story.append(Paragraph(f"{clinic_name}", title_style))
        story.append(Paragraph("Laboratory Results Report", title_style))
        story.append(Spacer(1, 20))
        
        # Patient Information
        story.append(Paragraph("Patient Information", heading_style))
        
        patient_data = [
            ['Patient Name:', patient_name],
            ['Patient Code:', patient_code],
            ['Visit ID:', str(visit_id)],
            ['Test Date:', completed_at],
            ['Test Type:', lab_type]
        ]
        
        if doctor_name:
            patient_data.append(['Ordering Doctor:', doctor_name])
        
        patient_table = Table(patient_data, colWidths=[2*inch, 4*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (1, -1), colors.white),
        ]))
        
        story.append(patient_table)
        story.append(Spacer(1, 20))
        
        # Lab Results
        story.append(Paragraph("Test Results", heading_style))
        story.append(Spacer(1, 10))
        
        # Format the results text
        formatted_results = lab_results.replace('\n', '<br/>')
        story.append(Paragraph(formatted_results, results_style))
        story.append(Spacer(1, 20))
        
        # Footer
        story.append(Spacer(1, 30))
        story.append(Paragraph("Important Notes:", heading_style))
        story.append(Paragraph(
            "• Please review your lab results carefully<br/>"
            "• If you have any questions about your results, please contact your doctor<br/>"
            "• You can log in to your patient portal to view your complete medical history<br/>"
            "• If you need to visit the clinic, please bring this report or your patient ID",
            normal_style
        ))
        story.append(Spacer(1, 20))
        
        # Footer information
        footer_data = [
            ['Generated on:', timezone.now().strftime('%Y-%m-%d %H:%M:%S')],
            ['Clinic:', clinic_name],
            ['Contact:', 'Please contact the clinic for any questions']
        ]
        
        footer_table = Table(footer_data, colWidths=[2*inch, 4*inch])
        footer_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        
        story.append(footer_table)
        
        # Build the PDF
        doc.build(story)
        
        # Get the PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        logger.info(f"Lab result PDF generated successfully for patient {patient_name} (Visit ID: {visit_id})")
        return pdf_content
        
    except Exception as e:
        logger.error(f"Failed to generate lab result PDF for patient {patient_name}: {e}")
        return None


def generate_lab_result_pdf_simple(
    patient_name: str,
    patient_code: str,
    lab_type: str,
    lab_results: str,
    visit_id: int,
    completed_at: str,
    doctor_name: str = None,
    clinic_name: str = "Clinic QR System"
) -> Optional[bytes]:
    """
    Generate a simple text-based PDF for lab results (fallback method).
    
    Args:
        patient_name: Patient's full name
        patient_code: Patient's unique code
        lab_type: Type of lab test performed
        lab_results: Lab test results text
        visit_id: Visit ID for reference
        completed_at: Date/time when lab was completed
        doctor_name: Name of the doctor who ordered the test
        clinic_name: Name of the clinic
        
    Returns:
        bytes: PDF content as bytes, or None if generation fails
    """
    try:
        # Create a simple text-based PDF using basic HTML to PDF conversion
        # This is a fallback method when ReportLab is not available
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Lab Results - {patient_name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .title {{ font-size: 24px; color: #2c5aa0; margin-bottom: 10px; }}
                .subtitle {{ font-size: 18px; color: #666; }}
                .section {{ margin: 20px 0; }}
                .section-title {{ font-size: 16px; color: #2c5aa0; margin-bottom: 10px; font-weight: bold; }}
                .info-table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                .info-table td {{ padding: 8px; border: 1px solid #ddd; }}
                .info-table td:first-child {{ background-color: #f5f5f5; font-weight: bold; width: 30%; }}
                .results {{ background-color: #f9f9f9; padding: 15px; border: 1px solid #ddd; font-family: monospace; white-space: pre-wrap; }}
                .footer {{ margin-top: 40px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="title">{clinic_name}</div>
                <div class="subtitle">Laboratory Results Report</div>
            </div>
            
            <div class="section">
                <div class="section-title">Patient Information</div>
                <table class="info-table">
                    <tr><td>Patient Name:</td><td>{patient_name}</td></tr>
                    <tr><td>Patient Code:</td><td>{patient_code}</td></tr>
                    <tr><td>Visit ID:</td><td>{visit_id}</td></tr>
                    <tr><td>Test Date:</td><td>{completed_at}</td></tr>
                    <tr><td>Test Type:</td><td>{lab_type}</td></tr>
                    {f'<tr><td>Ordering Doctor:</td><td>{doctor_name}</td></tr>' if doctor_name else ''}
                </table>
            </div>
            
            <div class="section">
                <div class="section-title">Test Results</div>
                <div class="results">{lab_results}</div>
            </div>
            
            <div class="section">
                <div class="section-title">Important Notes</div>
                <ul>
                    <li>Please review your lab results carefully</li>
                    <li>If you have any questions about your results, please contact your doctor</li>
                    <li>You can log in to your patient portal to view your complete medical history</li>
                    <li>If you need to visit the clinic, please bring this report or your patient ID</li>
                </ul>
            </div>
            
            <div class="footer">
                <p>Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Clinic: {clinic_name}</p>
                <p>Contact: Please contact the clinic for any questions</p>
            </div>
        </body>
        </html>
        """
        
        # Convert HTML to PDF using weasyprint if available, otherwise return HTML as text
        try:
            import weasyprint
            pdf_content = weasyprint.HTML(string=html_content).write_pdf()
            logger.info(f"Lab result PDF (WeasyPrint) generated successfully for patient {patient_name}")
            return pdf_content
        except ImportError:
            # Fallback: return HTML content as bytes (can be opened in browser and printed as PDF)
            logger.warning("WeasyPrint not available. Returning HTML content as fallback.")
            return html_content.encode('utf-8')
            
    except Exception as e:
        logger.error(f"Failed to generate simple lab result PDF for patient {patient_name}: {e}")
        return None


def get_pdf_generation_info() -> Dict[str, Any]:
    """
    Get information about PDF generation capabilities.
    
    Returns:
        Dict with PDF generation information
    """
    info = {
        'reportlab_available': REPORTLAB_AVAILABLE,
        'weasyprint_available': False,
        'pdf_generation_enabled': False
    }
    
    try:
        import weasyprint
        info['weasyprint_available'] = True
        info['pdf_generation_enabled'] = True
    except ImportError:
        pass
    
    if REPORTLAB_AVAILABLE:
        info['pdf_generation_enabled'] = True
    
    return info
