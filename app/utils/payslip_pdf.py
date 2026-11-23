import io
import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from app.utils.currency import amount_to_indian_words, format_inr

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

def generate_payslip_pdf(
    salary: Any,
    employee: Any,
    department_name: str = "General",
    company_name: str = "WorkPulse EMS Pvt. Ltd.",
    company_address: str = "DLF Cyber City, Tower B, Phase III, Gurugram, Haryana - 122002"
) -> bytes:
    """
    Generates a professional, high-resolution PDF payslip formatted for Indian enterprise payroll.
    Returns the generated PDF as raw bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CompanyTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1E1B4B"),
        alignment=TA_CENTER
    )
    subtitle_style = ParagraphStyle(
        "CompanySubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748B"),
        alignment=TA_CENTER
    )
    period_style = ParagraphStyle(
        "PayPeriod",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#4338CA"),
        alignment=TA_CENTER
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#0F172A")
    )
    cell_label = ParagraphStyle(
        "CellLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#475569")
    )
    cell_value = ParagraphStyle(
        "CellValue",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#0F172A")
    )
    cell_amount = ParagraphStyle(
        "CellAmount",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#0F172A")
    )
    cell_amount_bold = ParagraphStyle(
        "CellAmountBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#0F172A")
    )
    net_pay_label = ParagraphStyle(
        "NetPayLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1E1B4B")
    )
    net_pay_val = ParagraphStyle(
        "NetPayVal",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#16A34A")
    )
    words_style = ParagraphStyle(
        "WordsStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#334155")
    )
    footer_text = ParagraphStyle(
        "FooterText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#94A3B8"),
        alignment=TA_CENTER
    )

    story = []

    # 1. Header
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph(company_address, subtitle_style))
    story.append(Spacer(1, 8))

    month_int = salary.month or (salary.payment_date.month if hasattr(salary.payment_date, 'month') else 1)
    year_int = salary.year or (salary.payment_date.year if hasattr(salary.payment_date, 'year') else 2026)
    month_name = MONTH_NAMES[month_int] if 1 <= month_int <= 12 else str(month_int)

    story.append(Paragraph(f"PAYSLIP FOR {month_name.upper()} {year_int}", period_style))
    story.append(Spacer(1, 10))

    # 2. Employee Details Table
    emp_code = getattr(employee, "employee_code", f"EMP-{employee.id}")
    emp_name = getattr(employee, "full_name", "Employee")
    position = getattr(employee, "position", "Staff")
    hire_date_str = str(getattr(employee, "hire_date", ""))
    pay_date_str = str(getattr(salary, "payment_date", date.today()))
    pay_method = str(getattr(salary, "payment_method", "BANK_TRANSFER")).replace("_", " ")
    status_str = str(getattr(salary, "status", "PAID"))
    lop_days_val = getattr(salary, "lop_days", Decimal("0.0"))
    days_in_month = calendar.monthrange(year_int, month_int)[1]

    emp_table_data = [
        [
            Paragraph("Employee Code:", cell_label),
            Paragraph(emp_code, cell_value),
            Paragraph("Full Name:", cell_label),
            Paragraph(emp_name, cell_value)
        ],
        [
            Paragraph("Department:", cell_label),
            Paragraph(department_name, cell_value),
            Paragraph("Designation:", cell_label),
            Paragraph(position, cell_value)
        ],
        [
            Paragraph("Date of Joining:", cell_label),
            Paragraph(hire_date_str, cell_value),
            Paragraph("Payroll Period:", cell_label),
            Paragraph(f"{days_in_month} Days ({month_name} {year_int})", cell_value)
        ],
        [
            Paragraph("Payment Date:", cell_label),
            Paragraph(pay_date_str, cell_value),
            Paragraph("Payment Mode:", cell_label),
            Paragraph(pay_method, cell_value)
        ],
        [
            Paragraph("Loss of Pay (LOP):", cell_label),
            Paragraph(f"{lop_days_val} Days", cell_value),
            Paragraph("Salary Status:", cell_label),
            Paragraph(status_str, cell_value)
        ]
    ]

    emp_table = Table(emp_table_data, colWidths=[105, 155, 105, 155])
    emp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(emp_table)
    story.append(Spacer(1, 12))

    # 3. Earnings & Deductions Table
    basic_val = getattr(salary, "basic_salary", Decimal("0.00"))
    hra_val = getattr(salary, "hra", Decimal("0.00"))
    da_val = getattr(salary, "da", Decimal("0.00"))
    conv_val = getattr(salary, "conveyance", Decimal("0.00"))
    med_val = getattr(salary, "medical", Decimal("0.00"))
    spec_val = getattr(salary, "special_allowance", Decimal("0.00"))
    bonus_val = getattr(salary, "bonus", Decimal("0.00"))
    ot_val = getattr(salary, "overtime_pay", Decimal("0.00"))
    other_allow = getattr(salary, "allowances", Decimal("0.00"))

    pf_val = getattr(salary, "pf_deduction", Decimal("0.00"))
    pt_val = getattr(salary, "professional_tax", Decimal("0.00"))
    tds_val = getattr(salary, "tds_deduction", Decimal("0.00"))
    esi_val = getattr(salary, "esi_deduction", Decimal("0.00"))
    lop_val = getattr(salary, "loss_of_pay", Decimal("0.00"))
    other_ded = getattr(salary, "deductions", Decimal("0.00"))

    gross_earnings = (
        Decimal(str(basic_val)) + Decimal(str(hra_val)) + Decimal(str(da_val)) +
        Decimal(str(conv_val)) + Decimal(str(med_val)) + Decimal(str(spec_val)) +
        Decimal(str(bonus_val)) + Decimal(str(ot_val)) + Decimal(str(other_allow))
    )
    total_deductions = (
        Decimal(str(pf_val)) + Decimal(str(pt_val)) + Decimal(str(tds_val)) +
        Decimal(str(esi_val)) + Decimal(str(lop_val)) + Decimal(str(other_ded))
    )
    net_val = getattr(salary, "net_salary", gross_earnings - total_deductions)

    breakup_data = [
        # Table Headers
        [
            Paragraph("EARNINGS", section_heading),
            Paragraph("AMOUNT (INR)", cell_amount_bold),
            Paragraph("DEDUCTIONS", section_heading),
            Paragraph("AMOUNT (INR)", cell_amount_bold)
        ],
        [
            Paragraph("Basic Salary", cell_value),
            Paragraph(format_inr(basic_val), cell_amount),
            Paragraph("Provident Fund (EPF)", cell_value),
            Paragraph(format_inr(pf_val), cell_amount)
        ],
        [
            Paragraph("House Rent Allowance (HRA)", cell_value),
            Paragraph(format_inr(hra_val), cell_amount),
            Paragraph("Professional Tax (PT)", cell_value),
            Paragraph(format_inr(pt_val), cell_amount)
        ],
        [
            Paragraph("Dearness Allowance (DA)", cell_value),
            Paragraph(format_inr(da_val), cell_amount),
            Paragraph("Employee State Insurance (ESIC)", cell_value),
            Paragraph(format_inr(esi_val), cell_amount)
        ],
        [
            Paragraph("Conveyance Allowance", cell_value),
            Paragraph(format_inr(conv_val), cell_amount),
            Paragraph("TDS / Income Tax", cell_value),
            Paragraph(format_inr(tds_val), cell_amount)
        ],
        [
            Paragraph("Medical Allowance", cell_value),
            Paragraph(format_inr(med_val), cell_amount),
            Paragraph("Loss of Pay (LOP)", cell_value),
            Paragraph(format_inr(lop_val), cell_amount)
        ],
        [
            Paragraph("Special Allowance", cell_value),
            Paragraph(format_inr(spec_val), cell_amount),
            Paragraph("Other Statutory Deductions", cell_value),
            Paragraph(format_inr(other_ded), cell_amount)
        ],
        [
            Paragraph("Bonus / Incentive", cell_value),
            Paragraph(format_inr(bonus_val), cell_amount),
            Paragraph("", cell_value),
            Paragraph("", cell_amount)
        ],
        [
            Paragraph("Overtime Pay", cell_value),
            Paragraph(format_inr(ot_val), cell_amount),
            Paragraph("", cell_value),
            Paragraph("", cell_amount)
        ],
        [
            Paragraph("Other Allowances", cell_value),
            Paragraph(format_inr(other_allow), cell_amount),
            Paragraph("", cell_value),
            Paragraph("", cell_amount)
        ],
        # Totals Row
        [
            Paragraph("Gross Earnings:", cell_label),
            Paragraph(format_inr(gross_earnings), cell_amount_bold),
            Paragraph("Total Deductions:", cell_label),
            Paragraph(format_inr(total_deductions), cell_amount_bold)
        ]
    ]

    breakup_table = Table(breakup_data, colWidths=[160, 100, 160, 100])
    breakup_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor("#EEF2F6")),
        ('BACKGROUND', (2, 0), (3, 0), colors.HexColor("#FEE2E2")),
        ('BACKGROUND', (0, -1), (1, -1), colors.HexColor("#F1F5F9")),
        ('BACKGROUND', (2, -1), (3, -1), colors.HexColor("#FEF2F2")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(breakup_table)
    story.append(Spacer(1, 10))

    # 4. Net Salary Highlight Box
    net_in_words = amount_to_indian_words(net_val)
    net_box_data = [
        [
            Paragraph("NET TAKE-HOME PAY", net_pay_label),
            Paragraph(format_inr(net_val), net_pay_val)
        ],
        [
            Paragraph(f"<b>Amount in Words:</b> {net_in_words}", words_style),
            Paragraph("", cell_value)
        ]
    ]
    net_table = Table(net_box_data, colWidths=[360, 160])
    net_table.setStyle(TableStyle([
        ('SPAN', (0, 1), (1, 1)),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F0FDF4")),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor("#22C55E")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(net_table)
    story.append(Spacer(1, 24))

    # 5. Signatures and Disclaimers
    sig_data = [
        [
            Paragraph("<b>Employee Signature</b>", cell_label),
            Paragraph("<b>Authorized HR Signatory</b>", cell_amount_bold)
        ],
        [
            Spacer(1, 30),
            Spacer(1, 30)
        ],
        [
            Paragraph("____________________________", cell_label),
            Paragraph("____________________________", cell_amount)
        ],
        [
            Paragraph(f"Date: {pay_date_str}", cell_value),
            Paragraph(f"For {company_name}", cell_amount)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[260, 260])
    sig_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(KeepTogether([sig_table]))
    story.append(Spacer(1, 16))

    # 6. Footer Disclaimer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceAfter=6))
    story.append(Paragraph(
        "Note: This is a system-generated electronic payslip generated by WorkPulse EMS. No physical signature is required.",
        footer_text
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
