# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2014 OpenSur.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


from openerp.osv import osv, fields

# Add Language Flag
class res_lang(osv.osv):
    _name="res.lang"
    _inherit="res.lang"
    _description="Idiomas"

    _columns={
        'currency_id': fields.many2one('res.currency', 'Currency', required=True),
        'property_product_pricelist': fields.property(
            type='many2one',
            relation='product.pricelist',
            domain=[('type','=','sale')],
            string="Sale Pricelist",
            help="This pricelist will be used, instead of the default one, for sales to the current partner"),
    }
res_lang()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
