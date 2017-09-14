##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
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

from openerp.osv import fields, osv
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp

class pos_advance_payment_inv(osv.osv_memory):
    _name = "pos.advance.payment.inv"
    _description = "PO Advance Payment Invoice"

    _columns = {
        'advance_payment_method':fields.selection(
            [('all', 'Invoice the whole sales order'), ('percentage','Percentage'), ('fixed','Fixed price (deposit)'),
                ('lines', 'Some order lines')],
            'What do you want to invoice?', required=True,
            help="""Use Invoice the whole sale order to create the final invoice.
                Use Percentage to invoice a percentage of the total amount.
                Use Fixed Price to invoice a specific amound in advance.
                Use Some Order Lines to invoice a selection of the sales order lines."""),
        'qtty': fields.float('Quantity', digits=(16, 2), required=True),
        'product_id': fields.many2one('product.product', 'Advance Product',
            domain=[('type', '=', 'money')],
            help="""Select a product of type service which is called 'Advance Product'.
                You may have to create it and set it as a default value on this field."""),
        'amount': fields.float('Advance Amount', digits_compute= dp.get_precision('Account'),
            help="The amount to be invoiced in advance."),
    }

    def _get_advance_product(self, cr, uid, context=None):
        try:
            product = self.pool.get('ir.model.data').get_object(cr, uid, 'sale', 'advance_product_0')
        except ValueError:
            # a ValueError is returned if the xml id given is not found in the table ir_model_data
            return False
        return product.id

    _defaults = {
        'advance_payment_method': 'all',
        'qtty': 1.0,
        'product_id': _get_advance_product,
    }

    def _translate_advance(self, cr, uid, percentage=False, context=None):
        return _("Advance of %s %%") if percentage else _("Advance of %s %s")

    def onchange_method(self, cr, uid, ids, advance_payment_method, product_id, context=None):
        if advance_payment_method == 'percentage':
            return {'value': {'amount':0, 'product_id':False }}
        if product_id:
            product = self.pool.get('product.product').browse(cr, uid, product_id, context=context)
            return {'value': {'amount': product.list_price}}
        return {'value': {'amount': 0}}

    def _prepare_advance_invoice_vals(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        pos_obj = self.pool.get('pos.order')
        ir_property_obj = self.pool.get('ir.property')
        fiscal_obj = self.pool.get('account.fiscal.position')
        inv_line_obj = self.pool.get('account.invoice.line')
        wizard = self.browse(cr, uid, ids[0], context)
        pos_ids = context.get('active_ids', [])
        tax_obj = self.pool.get('account.tax')

        result = []
        for po in pos_obj.browse(cr, uid, pos_ids, context=context):
            val = inv_line_obj.product_id_change(cr, uid, [], False, wizard.product_id.id,
                    False, False, partner_id=po.partner_id.id)
            res = val['value']

            # determine and check income account
            if not wizard.product_id.id :
                prop = ir_property_obj.get(cr, uid,
                            'property_account_income_categ', 'product.category', context=context)
                prop_id = prop and prop.id or False
                account_id = fiscal_obj.map_account(cr, uid, False, prop_id)
                #tax_id = fiscal_obj.map_tax(cr, uid, sale.fiscal_position or False, wizard.product_id, context=context)
                if not account_id:
                    raise osv.except_osv(_('Configuration Error!'),
                            _('There is no income account defined as global property.'))
                res['account_id'] = account_id
            if not res.get('account_id'):
                raise osv.except_osv(_('Configuration Error!'),
                        _('There is no income account defined for this product: "%s" (id:%d).') % \
                            (wizard.product_id.name, wizard.product_id.id,))

            # determine invoice amount
            if wizard.amount <= 0.00:
                raise osv.except_osv(_('Incorrect Data'),
                    _('The value of Advance Amount must be positive.'))
            if wizard.advance_payment_method == 'percentage':
                inv_lines_values = []
                for po_line in po.lines:
                    name = self._translate_advance(cr, uid, percentage=True, context=dict(context, lang=po.partner_id.lang)) % (wizard.amount)
                    # create the invoice line
                    inv_line_values = {
                        'name': name + '\n' + po_line.name,
                        'origin': po.name,
                        'account_id': res['account_id'],
                        'price_unit': (po_line.product_uos_qty * po_line.price_unit * wizard.amount) / 100,
                        'price_unit_vat': 0.0,
                        'quantity': 1.0,
                        'discount': po_line.discount,
                        'uos_id': res.get('uos_id', False),
                        'product_id': False,
                        'invoice_line_tax_id': [(6, 0, po_line.tax_ids.ids)],
                    }
                    inv_lines_values.append((0, 0, inv_line_values))
            else:
                inv_amount = wizard.amount
                if not res.get('name'):
                    #TODO: should find a way to call formatLang() from rml_parse
                    symbol = po.pricelist_id.currency_id.symbol
                    if po.pricelist_id.currency_id.position == 'after':
                        symbol_order = (inv_amount, symbol)
                    else:
                        symbol_order = (symbol, inv_amount)
                    res['name'] = self._translate_advance(cr, uid, context=dict(context, lang=po.partner_id.lang)) % symbol_order

                # determine taxes
                if res.get('invoice_line_tax_id'):
                    taxes = tax_obj.browse(cr, uid, res.get('invoice_line_tax_id'), context=context)
                    res['invoice_line_tax_id'] = [(6, 0, res.get('invoice_line_tax_id'))]
                    if taxes:
                        inv_amount = taxes.compute_all(inv_amount, 1, inverce=True)['total_included']
                else:
                    res['invoice_line_tax_id'] = False

                # create the invoice
                inv_line_values = {
                    'name': res.get('name'),
                    'origin': po.name,
                    'account_id': res['account_id'],
                    'price_unit': inv_amount,
                    'price_unit_vat': 0.0,
                    'quantity': wizard.qtty or 1.0,
                    'discount': False,
                    'uos_id': res.get('uos_id', False),
                    'product_id': wizard.product_id.id,
                    'invoice_line_tax_id': res.get('invoice_line_tax_id'),
                }
                inv_lines_values = [(0, 0, inv_line_values)]

            inv_values = {
                'name': po.name,
                'origin': po.name,
                'type': 'out_invoice',
                'reference': False,
                'account_id': po.partner_id.property_account_receivable.id,
                'partner_id': po.partner_invoice_id.id,
                'pricelist_id': po.pricelist_id.id,
                'invoice_line': inv_lines_values,
                'currency_id': po.pricelist_id.currency_id.id,
                'comment': '',
                'fiscal_position': po.partner_id.property_account_position.id,
            }
            result.append((sale.id, inv_values))
        return result

    def _create_invoices(self, cr, uid, inv_values, po_id, context=None):
        inv_obj = self.pool.get('account.invoice')
        pos_obj = self.pool.get('pos.order')
        inv_id = inv_obj.create(cr, uid, inv_values, context=context)
        inv_obj.button_reset_taxes(cr, uid, [inv_id], context=context)
        # add the invoice to the sales order's invoices
        pos_obj.write(cr, uid, po_id, {'invoice_ids': [(4, inv_id)]}, context=context)
        return inv_id

    def create_invoices(self, cr, uid, ids, context=None):
        """ create invoices for the active sales orders """
        pos_obj = self.pool.get('pos.order')
        act_window = self.pool.get('ir.actions.act_window')
        wizard = self.browse(cr, uid, ids[0], context)
        pos_ids = context.get('active_ids', [])
        if wizard.advance_payment_method == 'all':
            # create the final invoices of the active po orders
            res = pos_obj.manual_invoice(cr, uid, pos_ids, context)
            if context.get('open_invoices', False):
                return res
            return {'type': 'ir.actions.act_window_close'}

        assert wizard.advance_payment_method in ('fixed', 'percentage')

        inv_ids = []
        for po_id, inv_values in self._prepare_advance_invoice_vals(cr, uid, ids, context=context):
            inv_ids.append(self._create_invoices(cr, uid, inv_values, po_id, context=context))

        if context.get('open_invoices', False):
            return self.open_invoices( cr, uid, ids, po_ids, context=context)
        return {'type': 'ir.actions.act_window_close'}

    def open_invoices(self, cr, uid, ids, invoice_ids, context=None):
        """ open a view on one of the given invoice_ids """
        ir_model_data = self.pool.get('ir.model.data')
        form_res = ir_model_data.get_object_reference(cr, uid, 'account', 'invoice_form')
        form_id = form_res and form_res[1] or False
        tree_res = ir_model_data.get_object_reference(cr, uid, 'account', 'invoice_tree')
        tree_id = tree_res and tree_res[1] or False

        return {
            'name': _('Advance Invoice'),
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': 'account.invoice',
            'res_id': invoice_ids[0],
            'view_id': False,
            'views': [(form_id, 'form'), (tree_id, 'tree')],
            'context': "{'type': 'out_invoice'}",
            'type': 'ir.actions.act_window',
        }


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
