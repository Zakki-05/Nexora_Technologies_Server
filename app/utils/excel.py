import io
import zipfile
import xml.sax.saxutils as saxutils
from typing import List, Any

def create_xlsx(headers: List[str], rows: List[List[Any]], sheet_name: str = "Report") -> io.BytesIO:
    """
    Generates a genuine Office Open XML (.xlsx) workbook using only Python standard library.
    Compatible with Microsoft Excel, Google Sheets, LibreOffice Calc, and Apple Numbers.
    """
    output = io.BytesIO()

    # Content Types
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="xml" ContentType="application/xml"/>\n'
        '  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\n'
        '  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
        '</Types>'
    )

    # Package Relationships (_rels/.rels)
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>\n'
        '</Relationships>'
    )

    # Workbook (xl/workbook.xml)
    safe_sheet_name = saxutils.escape(sheet_name)
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        '  <sheets>\n'
        f'    <sheet name="{safe_sheet_name}" sheetId="1" r:id="rId1"/>\n'
        '  </sheets>\n'
        '</workbook>'
    )

    # Workbook Relationships (xl/_rels/workbook.xml.rels)
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>\n'
        '</Relationships>'
    )

    # Worksheet (xl/worksheets/sheet1.xml)
    sheet_rows_xml = []
    
    # Header row (row 1)
    header_cells = []
    for col_idx, header in enumerate(headers, start=1):
        escaped_val = saxutils.escape(str(header or ""))
        header_cells.append(f'<c t="inlineStr"><is><t>{escaped_val}</t></is></c>')
    sheet_rows_xml.append(f'<row r="1">{"".join(header_cells)}</row>')

    # Data rows (rows 2..)
    for row_idx, row in enumerate(rows, start=2):
        row_cells = []
        for val in row:
            if val is None:
                val_str = ""
            else:
                val_str = str(val)
            escaped_val = saxutils.escape(val_str)
            
            # Check if numeric for native excel numeric display
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                row_cells.append(f'<c><v>{val}</v></c>')
            else:
                row_cells.append(f'<c t="inlineStr"><is><t>{escaped_val}</t></is></c>')
        sheet_rows_xml.append(f'<row r="{row_idx}">{"".join(row_cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        '  <sheetData>\n'
        f'    {"".join(sheet_rows_xml)}\n'
        '  </sheetData>\n'
        '</worksheet>'
    )

    # Assemble Zip File
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", package_rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    output.seek(0)
    return output
