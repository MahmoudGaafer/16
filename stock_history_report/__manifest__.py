{
    "name": "Stock History Report",
    "summary": "Export stock history for specified datetime ranges across one or multiple warehouses or locations.",
    "version": "16.0",
    "category": "Warehouse/Reports",
    "author": "Mahmoud Gaafer",
    "maintainer": "Mahmoud Gaafer",
    "website": "https://www.linkedin.com/in/mahmoud-gaafer-b530191a9",
    "license": "LGPL-3",
    "price": 20.0,
    "currency": "USD",
    "depends": ["stock", "base"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_valuation_report_view.xml"
    ],
    'images': ['static/description/banner.jpg'],
    "application": True,
    "installable": True,
    "auto_install": False
}
