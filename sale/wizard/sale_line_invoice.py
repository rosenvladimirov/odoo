# -*- coding: utf-8 -*-
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

from openerp.osv import osv, fields
from openerp.tools.translate import _
from openerp import workflow
import logging
_logger = logging.getLogger(__name__)

class sale_order_line_make_invoice(osv.osv_memory):
    _name = "sale.order.line.make.invoice"
    _description = "Sale OrderLine Make_invoice"

    def _prepare_invoice(self, cr, uid, order, lines, context=None):
        a = order.partner_id.property_account_receivable.id
        if order.partner_id and order.partner_id.property_payment_term.id:
            pay_term = order.partner_id.property_payment_term.id
        else:
            pay_term = False
        return {
            'name': order.client_order_ref or '',
            'origin': order.name,
            'type': 'out_invoice',
            'reference': "P%dSO%d" % (order.partner_id.id, order.id),
            'account_id': a,
            'partner_id': order.partner_invoice_id.id,
            'invoice_line': [(6, 0, lines)],
            'currency_id' : order.pricelist_id.currency_id.id,
            'comment': order.note,
            'payment_term': pay_term,
            'fiscal_position': order.fiscal_position.id or order.partner_id.property_account_position.id,
            'user_id': order.user_id and order.user_id.id or False,
            'company_id': order.company_id and order.company_id.id or False,
            'date_invoice': fields.date.today(),
            'section_id': order.section_id.id,
        }

    def group_orders(self, cr, uid, order_line_ids, context=None):
        order_id = False
        record = False
        virtual = 0
        for sol in self.pool.get('sale.order.line').browse(cr, uid, order_line_ids, context=context):
            if order_id != sol.order_id:
                order_id = sol.order_id
                virtual = virtual + 1

        if virtual>1:
            record = self.pool.get('sale.order.virtual').create(cr, uid, {'order_line_ids': order_line_ids}, context=context)
            #record = self.pool.get('sale.order.virtual').browse(cr, uid, rec, context=context)
            #_logger.info("VO SO %s:%s" % (rec,record.order_ids))
        return record

    def make_invoices(self, cr, uid, ids, context=None):
        """
             To make invoices.

             @param self: The object pointer.
             @param cr: A database cursor
             @param uid: ID of the user currently logged in
             @param ids: the ID or list of IDs
             @param context: A standard dictionary

             @return: A dictionary which of fields with values.

        """
        if context is None: context = {}
        res = False
        inv_res = []
        invoices = {}
        order_to_validate = {}
        order_to_block = {}

    #TODO: merge with sale.py/make_invoice
        def make_invoice(order, lines):
            """
                 To make invoices.

                 @param order:
                 @param lines:

                 @return:

            """
            inv = self._prepare_invoice(cr, uid, order, lines)
            inv_id = self.pool.get('account.invoice').create(cr, uid, inv)
            return inv_id

        sales_order_line_obj = self.pool.get('sale.order.line')
        sales_order_obj = self.pool.get('sale.order')
        sales_order_virtual_obj = self.pool.get('sale.order.virtual')
        self.group_orders(cr, uid, context.get('active_ids', []),context=context)
        for line in sales_order_line_obj.browse(cr, uid, context.get('active_ids', []), context=context):
            if (not line.invoiced) and (line.state not in ('draft', 'cancel')):
                vo_id = sales_order_virtual_obj.search(cr, uid, [('order_line_ids', '=', line.id)], context=context)
                virtual_order_id = sales_order_virtual_obj.browse(cr, uid, vo_id, context=context)
                _logger.debug("VO Check %s:%s->%s" % (line, virtual_order_id, line.order_id))
                order_id = virtual_order_id.order_ids or line.order_id
                if not order_id in invoices:
                    invoices[order_id] = []
                line_id = sales_order_line_obj.invoice_line_create(cr, uid, [line.id])
                for lid in line_id:
                    invoices[order_id].append(lid)
        for order, il in invoices.items():
            res = make_invoice(order, il)
            inv_res.append(res)
            cr.execute('INSERT INTO sale_order_invoice_rel \
                    (order_id,invoice_id) values (%s,%s)', (order.id, res))
            sales_order_obj.invalidate_cache(cr, uid, ['invoice_ids'], [order.id], context=context)
            #flag = True
            sales_order_obj.message_post(cr, uid, [order.id], body=_("Invoice created"), context=context)
            data_sale = sales_order_obj.browse(cr, uid, order.id, context=context)
            vo_id = sales_order_virtual_obj.search(cr, uid, [('order_ids', '=', order.id)], context=context)
            virtual_order_id = sales_order_virtual_obj.browse(cr, uid, vo_id, context=context)
            _logger.debug("Check for vo %s=>%s:%s" % (order.id, data_sale, virtual_order_id))
            lines = virtual_order_id.order_line_ids or data_sale.order_line
            for line in lines:
                if order_to_block.has_key(line.order_id) == False:
                    order_to_validate[line.order_id] = line
                if not line.invoiced and line.state != 'cancel':
                    if order_to_validate.has_key(line.order_id):
                        del order_to_validate[line.order_id]
                    order_to_block[line.order_id] =  line
                #    flag = False
                #    break
            #if flag:
                # fix by rosen
                #line.order_id.write({'state': 'progress'})
                #workflow.trg_validate(uid, 'sale.order', line.order.id, 'all_lines', cr)
        for order, line in order_to_validate.items():
            _logger.debug("Update for order %s" % (order.id))
            sales_order_obj.message_post(cr, uid, [order.id], body=_("Invoice created from virtual order"), context=context)
            line.order_id.write({'state': 'progress'})
            workflow.trg_validate(uid, 'sale.order', order.id, 'all_lines', cr)
        if not invoices:
            raise osv.except_osv(_('Warning!'), _('Invoice cannot be created for this Sales Order Line due to one of the following reasons:\n1.The state of this sales order line is either "draft" or "cancel"!\n2.The Sales Order Line is Invoiced!'))
        if context.get('open_invoices', False):
            return self.open_invoices(cr, uid, ids, inv_res, context=context)
        return {'type': 'ir.actions.act_window_close'}

    def open_invoices(self, cr, uid, ids, invoice_ids, context=None):
        """ open a view on one of the given invoice_ids """
        ir_model_data = self.pool.get('ir.model.data')
        form_res = ir_model_data.get_object_reference(cr, uid, 'account', 'invoice_form')
        form_id = form_res and form_res[1] or False
        tree_res = ir_model_data.get_object_reference(cr, uid, 'account', 'invoice_tree')
        tree_id = tree_res and tree_res[1] or False
        ret = {
            'name': _('Invoice'),
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': 'account.invoice',
            'view_id': False,
            'views': [(form_id, 'form'), (tree_id, 'tree')],
            'context': {'type': 'out_invoice'},
            'type': 'ir.actions.act_window',
        }
        if len(invoice_ids) > 1:
            ret['domain'] = "[('id','in', ["+','.join(map(str, invoice_ids))+"])]"
        elif len(invoice_ids) == 1:
            ret['views'] = [(form_id, 'form')]
            ret['res_id'] = invoice_ids[0]
        else:
            result = {'type': 'ir.actions.act_window_close'}
        #_logger.info("Action after it %s" % ret)
        return ret
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
