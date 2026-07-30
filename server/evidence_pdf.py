"""
Magneetar Evidence PDF Generator
Generates actual PDF documents for theft evidence cases using ReportLab.
"""
import base64
import os
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable
)
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
from reportlab.platypus.frames import Frame

from config import settings
from evidence import evidence_builder


class EvidencePDFGenerator:
    """Generate forensic-quality PDF evidence reports."""

    # Brand colors
    PRIMARY = colors.HexColor("#1a1a2e")
    ACCENT = colors.HexColor("#00FF88")
    DANGER = colors.HexColor("#FF3355")
    WARNING = colors.HexColor("#FF8800")
    TEXT_DARK = colors.HexColor("#0a0a0a")
    TEXT_LIGHT = colors.HexColor("#ffffff")
    BORDER = colors.HexColor("#cccccc")
    BG_LIGHT = colors.HexColor("#f5f5f5")

    @staticmethod
    def _header_footer(canvas, doc):
        """Draw header and footer on each page."""
        canvas.saveState()
        # Header bar
        canvas.setFillColor(EvidencePDFGenerator.PRIMARY)
        canvas.rect(0, A4[1] - 25*mm, A4[0], 25*mm, fill=1, stroke=0)
        canvas.setFillColor(EvidencePDFGenerator.ACCENT)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(15*mm, A4[1] - 16*mm, "MAGNEETAR")
        canvas.setFont("Helvetica", 6)
        canvas.setFillColor(colors.white)
        canvas.drawString(15*mm, A4[1] - 22*mm, "EVIDENCE REPORT — CONFIDENTIAL")
        # Footer
        canvas.setFillColor(colors.HexColor("#999999"))
        canvas.setFont("Helvetica", 6)
        canvas.drawCentredString(A4[0] / 2, 10*mm,
            f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Page {doc.page}")
        canvas.restoreState()

    @staticmethod
    def generate(case_id: str) -> Optional[bytes]:
        """
        Generate a complete PDF report for an evidence case.
        Returns PDF bytes, or None if the case doesn't exist.
        """
        # Get case data from evidence builder
        data = evidence_builder.compile_pdf_data(case_id)
        if not data:
            return None

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=35*mm,
            bottomMargin=20*mm,
            leftMargin=20*mm,
            rightMargin=20*mm,
        )

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='CaseTitle',
            fontName='Helvetica-Bold',
            fontSize=18,
            leading=22,
            textColor=EvidencePDFGenerator.PRIMARY,
            spaceAfter=4*mm,
        ))
        styles.add(ParagraphStyle(
            name='SectionHeader',
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=EvidencePDFGenerator.PRIMARY,
            spaceBefore=6*mm,
            spaceAfter=3*mm,
            borderPadding=(0, 0, 2, 0),
        ))
        styles.add(ParagraphStyle(
            name='Label',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#666666"),
        ))
        styles.add(ParagraphStyle(
            name='Value',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            textColor=EvidencePDFGenerator.TEXT_DARK,
            spaceAfter=2*mm,
        ))
        styles.add(ParagraphStyle(
            name='Monospace',
            fontName='Courier',
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#333333"),
            spaceAfter=1*mm,
        ))
        styles.add(ParagraphStyle(
            name='AlertLine',
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#cc0000"),
            spaceAfter=1*mm,
        ))

        elements = []
        case = data.get("case", {})
        device = data.get("device", {})
        locations = data.get("locations", [])
        media_items = data.get("media", [])
        alerts = data.get("alerts", [])

        # ── Cover Section ──────────────────────────────────────────────────
        elements.append(Paragraph(f"Evidence Case: {case_id}", styles['CaseTitle']))
        elements.append(HRFlowable(width="100%", thickness=1,
            color=EvidencePDFGenerator.ACCENT, spaceAfter=4*mm))

        # Status badge
        status = case.get("status", "unknown").upper()
        status_color = {
            "ACTIVE": EvidencePDFGenerator.ACCENT,
            "CLOSED": colors.HexColor("#666666"),
            "GENERATED": EvidencePDFGenerator.ACCENT,
        }.get(status, EvidencePDFGenerator.WARNING)
        elements.append(Paragraph(
            f'<font color="{status_color.hexval()}"><b>STATUS: {status}</b></font>',
            styles['Value']
        ))
        elements.append(Spacer(1, 3*mm))

        # ── Device Information ─────────────────────────────────────────────
        elements.append(Paragraph("DEVICE INFORMATION", styles['SectionHeader']))
        elements.append(HRFlowable(width="100%", thickness=0.5,
            color=EvidencePDFGenerator.BORDER, spaceAfter=2*mm))

        device_data = [
            ["Device ID", device.get("id", "Unknown")],
            ["Model", device.get("model", "Unknown")],
            ["OS Version", device.get("os_version", "Unknown")],
            ["IMEI Hash", device.get("imei_hash", "N/A")],
        ]
        t = Table(device_data, colWidths=[40*mm, 110*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), EvidencePDFGenerator.BG_LIGHT),
            ('TEXTCOLOR', (0, 0), (-1, -1), EvidencePDFGenerator.TEXT_DARK),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, EvidencePDFGenerator.BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 3*mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3*mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 3*mm),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 3*mm))

        # ── Case Timeline ──────────────────────────────────────────────────
        theft_time = case.get("theft_time", "Unknown")
        created_at = case.get("created_at", "Unknown")
        if theft_time and theft_time != "Unknown":
            elements.append(Paragraph("THEFT TIMELINE", styles['SectionHeader']))
            elements.append(HRFlowable(width="100%", thickness=0.5,
                color=EvidencePDFGenerator.BORDER, spaceAfter=2*mm))
            timeline_data = [
                ["Theft Detected", theft_time],
                ["Case Created", created_at],
                ["Locations Recorded", str(case.get("item_counts", {}).get("locations", 0))],
                ["Photos Captured", str(case.get("item_counts", {}).get("photos", 0))],
                ["Audio Recordings", str(case.get("item_counts", {}).get("audio", 0))],
            ]
            t = Table(timeline_data, colWidths=[40*mm, 110*mm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), EvidencePDFGenerator.BG_LIGHT),
                ('TEXTCOLOR', (0, 0), (-1, -1), EvidencePDFGenerator.TEXT_DARK),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, EvidencePDFGenerator.BORDER),
                ('TOPPADDING', (0, 0), (-1, -1), 3*mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3*mm),
                ('LEFTPADDING', (0, 0), (-1, -1), 3*mm),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 3*mm))

        # ── Location Trail ─────────────────────────────────────────────────
        if locations:
            elements.append(Paragraph("LOCATION TRAIL", styles['SectionHeader']))
            elements.append(HRFlowable(width="100%", thickness=0.5,
                color=EvidencePDFGenerator.BORDER, spaceAfter=2*mm))

            # Show first 50 locations in a table
            loc_preview = locations[:50]
            loc_header = ["#", "Time", "Latitude", "Longitude", "Speed", "Battery"]
            loc_data = [loc_header]
            for i, loc in enumerate(loc_preview, 1):
                loc_data.append([
                    str(i),
                    str(loc.get("timestamp", "") or "")[:19],
                    f'{loc.get("lat", 0):.6f}',
                    f'{loc.get("lng", 0):.6f}',
                    f'{loc.get("speed", 0):.1f} m/s' if loc.get("speed") else "N/A",
                    f'{loc.get("battery_percent", "?")}%',
                ])

            col_widths = [8*mm, 35*mm, 30*mm, 30*mm, 25*mm, 20*mm]
            t = Table(loc_data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), EvidencePDFGenerator.PRIMARY),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 7),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('FONTNAME', (0, 1), (-1, -1), 'Courier'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, EvidencePDFGenerator.BORDER),
                ('TOPPADDING', (0, 0), (-1, -1), 2*mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2*mm),
            ]))
            elements.append(t)
            if len(locations) > 50:
                elements.append(Paragraph(
                    f"... and {len(locations) - 50} more location records (see dashboard)",
                    styles['Monospace']
                ))
            elements.append(Spacer(1, 3*mm))

        # ── Media Evidence ─────────────────────────────────────────────────
        if media_items:
            elements.append(PageBreak())
            elements.append(Paragraph("MEDIA EVIDENCE", styles['SectionHeader']))
            elements.append(HRFlowable(width="100%", thickness=0.5,
                color=EvidencePDFGenerator.BORDER, spaceAfter=2*mm))

            for item in media_items:
                media_type = item.get("type", "unknown")
                media_time = str(item.get("timestamp", ""))[:19]
                media_hash = item.get("sha256_hash", "")[:16] + "..."

                elements.append(Paragraph(
                    f'<b>{media_type.upper()}</b> — {media_time}',
                    styles['Value']
                ))
                elements.append(Paragraph(
                    f'SHA-256: {media_hash}',
                    styles['Monospace']
                ))

                # Include first photo inline as base64-decoded image
                if media_type == "photo" and item.get("sha256_hash"):
                    try:
                        media_rows = evidence_builder.get_media_for_case(case_id)
                        for m in media_rows:
                            if m.get("id") == item.get("id") and m.get("data_b64"):
                                img_data = base64.b64decode(m["data_b64"])
                                img_buffer = BytesIO(img_data)
                                img = Image(img_buffer, width=80*mm, height=60*mm)
                                elements.append(img)
                                break
                    except Exception:
                        pass

                elements.append(Spacer(1, 2*mm))

        # ── Alert History ──────────────────────────────────────────────────
        if alerts:
            elements.append(PageBreak())
            elements.append(Paragraph("ALERT HISTORY", styles['SectionHeader']))
            elements.append(HRFlowable(width="100%", thickness=0.5,
                color=EvidencePDFGenerator.BORDER, spaceAfter=2*mm))

            for alert in alerts[:30]:
                alert_type = alert.get("alert_type", "unknown").replace("_", " ").upper()
                alert_time = str(alert.get("sent_at", ""))[:19]
                alert_msg = alert.get("message", "")[:100]
                elements.append(Paragraph(
                    f'<b>{alert_time}</b> — {alert_type}',
                    styles['AlertLine']
                ))
                if alert_msg:
                    elements.append(Paragraph(alert_msg, styles['Monospace']))
                elements.append(Spacer(1, 1*mm))

        # ── Chain of Custody ───────────────────────────────────────────────
        chain = data.get("chain_of_custody", "")
        if chain:
            elements.append(Spacer(1, 5*mm))
            elements.append(Paragraph("CHAIN OF CUSTODY", styles['SectionHeader']))
            elements.append(HRFlowable(width="100%", thickness=0.5,
                color=EvidencePDFGenerator.BORDER, spaceAfter=2*mm))
            elements.append(Paragraph(
                "SHA-256 Hash Chain — verifies integrity of all evidence items.",
                styles['Monospace']
            ))
            elements.append(Paragraph(
                f'<font face="Courier" size="6">{chain}</font>',
                styles['Monospace']
            ))
            elements.append(Spacer(1, 3*mm))
            elements.append(Paragraph(
                "<i>Verify this hash independently using the Magneetar dashboard.</i>",
                ParagraphStyle('Disclaimer', fontName='Helvetica-Oblique',
                    fontSize=7, textColor=colors.HexColor("#999999"))
            ))

        # ── Footer Note ────────────────────────────────────────────────────
        elements.append(Spacer(1, 5*mm))
        elements.append(HRFlowable(width="100%", thickness=0.5,
            color=EvidencePDFGenerator.BORDER, spaceAfter=2*mm))
        elements.append(Paragraph(
            f"This report was automatically generated by Magneetar v{getattr(settings, 'APP_VERSION', '1.0.0')} "
            f"on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
            ParagraphStyle('Footer', fontName='Helvetica', fontSize=6,
                textColor=colors.HexColor("#999999"))
        ))

        # Build the PDF
        doc.build(elements, onFirstPage=EvidencePDFGenerator._header_footer,
                  onLaterPages=EvidencePDFGenerator._header_footer)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes


# Singleton
pdf_generator = EvidencePDFGenerator()


def generate_evidence_pdf(case_id: str) -> Optional[bytes]:
    """Generate a PDF for the given evidence case."""
    return pdf_generator.generate(case_id)
