# KCG Cement Odoo

## Cement Sales module

`custom_addons/cement_sales` is an Odoo 18 custom module for maintaining cement
sales customer records. It provides customer name, phone, email, company name,
customer type, and active status fields, with list and form views accessible
from the **Cement Sales → Customers** menu.

## Install

1. Make sure `custom_addons` is included in the Odoo server's `addons_path`.
2. Restart the Odoo server so it discovers the module, then update the Apps
   list in developer mode.
3. Search for **Cement Sales** in Apps and install it.

Internal users are granted read, create, write, and delete access to customer
records by the module's access control entry.
