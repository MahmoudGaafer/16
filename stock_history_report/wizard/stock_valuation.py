from odoo import models, fields, api
import xlsxwriter
import io
import base64
from datetime import datetime


class StockValuationWizard(models.TransientModel):
    _name = 'stock.valuation.report'
    _description = 'Stock Valuation Wizard'

    to_date = fields.Datetime(string="at Date", required=True)
    warehouse_ids = fields.Many2many(
        'stock.warehouse', string="Warehouses", help="Select warehouses for stock valuation"
    )
    location_ids = fields.Many2many(
        'stock.location',
        string="Locations",
        help="Select internal locations for stock valuation",
    )
    location_type = fields.Selection(
        [('production', 'Production'), ('internal', 'Internal'), ('transit', 'Transit')],
        string="Location Type"
    )
    all_locations_ids = fields.Boolean(default=False, string="All Child Locations")

    category_id = fields.Many2one(
        'product.category', string="Category", help="Select product category for stock valuation"
    )
    supplier_id = fields.Many2one(
        'res.partner',
        string="Supplier",
        help="Select a supplier to filter the stock valuation"
    )
    warehouse_stock = fields.Boolean(default=False, string='Warehouses')
    location_stock = fields.Boolean(default=False, string='Locations')
    all_supplier_ids = fields.Boolean(default=False, string='All Suppliers')
    gentextfile = fields.Binary('Generated Report', readonly=True)
    report_filename = fields.Char(default="Stock_Valuation_Report.xlsx", readonly=True)

    @api.onchange('location_type')
    def _compute_parent_location_domain(self):
        if self.location_type:
            filtered_locations = self.env['stock.location'].search([
                ('usage', '=', self.location_type)
            ])
            return {
                'domain': {
                    'location_ids': [('id', 'in', filtered_locations.ids)]
                }
            }
        else:
            return {
                'domain': {
                    'location_ids': []
                }
            }

    def generate_report(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet("Stock Valuation Report")

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#4F81BD',
            'font_color': 'white',
            'border': 2
        })
        subtitle_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#B8CCE4',
            'font_color': 'black',
            'border': 1
        })
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#1F4E78',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        subheader_format = workbook.add_format({
            'bold': True,
            'bg_color': '#DDEBF7',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        normal_format = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})
        numeric_format = workbook.add_format(
            {'border': 1, 'num_format': '#,##0.00', 'align': 'right', 'valign': 'vcenter'})

        sheet.merge_range('A1:H1', "Stock History Report", title_format)
        sheet.merge_range('A2:H2', f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", subtitle_format)
        sheet.merge_range('A3:B3', "Date Range", subheader_format)
        sheet.merge_range('C3:H3', f"{self.to_date}", normal_format)
        sheet.merge_range('A4:B4', "Warehouses", subheader_format)
        sheet.merge_range('C4:H4', ", ".join(self.warehouse_ids.mapped('name')), normal_format)
        sheet.merge_range('A5:B5', "Locations", subheader_format)
        sheet.merge_range('C5:H5', ", ".join(self.location_ids.mapped('name')), normal_format)
        sheet.merge_range('A6:B6', "Category", subheader_format)
        sheet.merge_range('C6:H6', self.category_id.name if self.category_id else '', normal_format)
        sheet.merge_range('A7:B7', "Supplier", subheader_format)
        sheet.merge_range('C7:H7', self.supplier_id.name if self.category_id else '', normal_format)

        headers = [
            "Barcode", "Internal Reference", "Product Name", "Category",
            "Cost (Unit)", "Price (Unit)"
        ]

        location_names = []
        location_ids = []
        for location in self.location_ids:
            if self.all_locations_ids:
                location_names += location.child_internal_location_ids.mapped('display_name')
                location_ids += location.child_internal_location_ids.ids
            else:
                location_names.append(location.display_name)
        if len(location_ids) > 0:
            self.write(
                {'location_ids': [(4, loc_id) for loc_id in set(location_ids)]})

        warehouse_names = self.warehouse_ids.mapped('name') if self.warehouse_ids else []
        if not self.warehouse_ids and not self.location_ids:
            warehouses = self.env['stock.warehouse'].search([])
            warehouse_names = warehouses.mapped('name')

        headers.extend(location_names)
        headers.extend(warehouse_names)
        headers.append("Total Value")
        headers.append("Suppliers")

        sheet.set_row(8, 25)
        row = 8
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)

        domain = []
        if self.category_id:
            domain.append(('categ_id', 'child_of', self.category_id.id))
        if self.supplier_id and not self.all_supplier_ids:
            domain.append(('seller_ids.partner_id.name', '=', self.supplier_id.name))

        row += 1
        products = self.env['product.product'].search(domain)
        for product in products:
            barcode = product.barcode or ""
            internal_ref = product.default_code or ""
            name = product.name
            category = product.categ_id.name or "Uncategorized"
            cost = product.standard_price
            price = product.lst_price

            supplier_names = list(set(seller.partner_id.name for seller in product.seller_ids))
            supplier_names_str = ", ".join(supplier_names) if supplier_names else "No Supplier"

            stock_move_model = self.env['stock.move']
            moves = stock_move_model.search([
                ('product_id', '=', product.id),
                ('state', 'not in', ['cancel', 'draft']),
                ('create_date', '<=', self.to_date),
            ])
            location_quantities = {}
            warehouse_quantities = {}

            if not self.warehouse_ids and not self.location_ids:
                warehouses = self.env['stock.warehouse'].search([])
                for warehouse in warehouses:
                    quantity = 0
                    for move in moves:
                        if move.location_dest_id.id == warehouse.lot_stock_id.id:
                            quantity += move.quantity_done
                        if move.location_id.id == warehouse.lot_stock_id.id:
                            quantity -= move.quantity_done
                    warehouse_quantities[warehouse.name] = quantity

            if self.warehouse_ids:
                for warehouse in self.warehouse_ids:
                    quantity = 0
                    for move in moves:
                        if move.location_dest_id.id == warehouse.lot_stock_id.id:
                            quantity += move.quantity_done
                        if move.location_id.id == warehouse.lot_stock_id.id:
                            quantity -= move.quantity_done
                    warehouse_quantities[warehouse.name] = quantity

            if self.location_ids:
                for location in self.location_ids:
                    quantity = 0
                    for move in moves:
                        if move.location_dest_id.id == location.id:
                            quantity += move.quantity_done
                        if move.location_id.id == location.id:
                            quantity -= move.quantity_done
                    location_quantities[location.display_name] = quantity

            sheet.write(row, 0, barcode, normal_format)
            sheet.write(row, 1, internal_ref, normal_format)
            sheet.write(row, 2, name, normal_format)
            sheet.write(row, 3, category, normal_format)
            sheet.write(row, 4, cost, numeric_format)
            sheet.write(row, 5, price, numeric_format)

            col = 6
            total_value = 0
            for location_name in location_names:
                quantity = location_quantities.get(location_name, 0)
                total_value += quantity * cost
                sheet.write(row, col, quantity, numeric_format)
                col += 1

            for warehouse_name in warehouse_names:
                quantity = warehouse_quantities.get(warehouse_name, 0)
                total_value += quantity * cost
                sheet.write(row, col, quantity, numeric_format)
                col += 1

            sheet.write(row, col, total_value, numeric_format)
            sheet.write(row, col + 1, supplier_names_str, normal_format)
            row += 1

        sheet.set_column(0, 0, 15)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 30)
        sheet.set_column(3, 3, 20)
        sheet.set_column(4, 5, 15)
        sheet.set_column(6, 7, 20)
        for i in range(8, 8 + len(location_names) * 2 + len(warehouse_names) * 2):
            sheet.set_column(i, i, 20)

        workbook.close()
        output.seek(0)

        file_data = base64.b64encode(output.read())
        self.write({
            'gentextfile': file_data,
            'report_filename': f"Stock_History_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        })

        return {
            'type': 'ir.actions.act_url',
            'name': 'Stock History Report',
            'url': f'/web/content/stock.valuation.report/{self.id}/gentextfile/{self.report_filename}?download=true',
            'target': 'new',
        }
