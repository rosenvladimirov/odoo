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
from openerp import models, fields, api, tools, _
import openerp.addons.decimal_precision as dp
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
_logger = logging.getLogger(__name__)

class SeleOrderVirtual(models.Model):
    _name = 'sale.order.virtual'
    _description = "Virtual orders for groups"

    name = fields.Char('Virtual Order Refence', required=True, translate=True)
    order_line_ids = fields.One2many('sale.order.line','virtual_sale_order_id', string="Orders lines", copy=True, readonly=True)
    order_ids = fields.One2many('sale.order','virtual_sale_order_id', string="Order", copy=True, readonly=True)

    def init(self, cr):
        tools.drop_view_if_exists(cr, 'sale_order_line_virtual')
        cr.execute("""CREATE OR REPLACE VIEW sale_order_line_virtual AS (
                 SELECT sol.id, sol.virtual_sale_order_id, sol.order_partner_id, sol.order_id, so.id AS virtual_order_id 
                   FROM sale_order AS so, sale_order_line AS sol, sale_order_virtual AS vir 
                 WHERE vir.id = so.virtual_sale_order_id AND vir.id = sol.virtual_sale_order_id)""")

    @api.model
    def _create_new_vo(self, vals, OrigSO, names):
        _logger.info("New SO %s" % OrigSO.date_order)
        if not vals:
            vals = {}
        new_so = {
            'origin': names,
            'name': '(%s)-%s' % (OrigSO.partner_id.id, names),
            'partner_id': OrigSO.partner_id.id,
            'date_order': datetime.strptime(OrigSO.date_order, "%Y-%m-%d %H:%M:%S") + relativedelta(days=31),
            'client_order_ref': OrigSO.client_order_ref,
            'pricelist_id':
                OrigSO.pricelist_id and OrigSO.pricelist_id.id or False,
            'currency_id':
                OrigSO.currency_id and OrigSO.currency_id.id or False,
            'user_id': OrigSO.user_id.id,
            'section_id': OrigSO.section_id and OrigSO.section_id.id or False,
            'payment_term':
                OrigSO.payment_term and OrigSO.payment_term.id or False,
            'fiscal_position':
                OrigSO.fiscal_position and OrigSO.fiscal_position.id or False,
            'company_id': OrigSO.company_id and OrigSO.company_id.id or False,
            #'order_line': vals['order_line_ids'],
            'state': 'virtualized',
            #'virtual_sale_order_id': OrigSO.id
        }
        NewSO = OrigSO.create(new_so)
        vals['order_ids'] = [(6, 0, [NewSO.id])]
        return vals

    #@api.returns("sale.order.virtual")
    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            seq = self.env['ir.sequence']
            vals['name'] = seq.next_by_code('sale.order.virtual') or '/'

        if self._context.get('force_create'):
            return super(SeleOrderVirtual, self).create(vals)

        if vals.get('order_line_ids'):
            last_order = False
            dsp_last_order = 0
            orders = {}
            names = ''
            OrigSOL = self.env['sale.order.line'].browse(vals.get('order_line_ids'))
            for line in OrigSOL:
                if not last_order:
                    last_order = line.order_id
                if line.order_id.partner_id.id != last_order.partner_id.id or \
                    (line.order_id.partner_id.id == last_order.partner_id.id and \
                    (line.order_id.pricelist_id.id != last_order.pricelist_id.id or \
                    line.order_id.currency_id.id != last_order.currency_id.id or \
                    line.order_id.fiscal_position.id != last_order.fiscal_position.id)):
                    last_order = line.order_id
                    names = ''
                if dsp_last_order != line.order_id:
                    dsp_last_order = line.order_id
                    names += line.order_id.name + '|'
                if not orders.get(last_order.id):
                    orders[last_order.id] = {'order_id': line.order_id, 'lines': [], 'name': names}
                orders[last_order.id]['lines'].append(line.id)
                #_logger.info('Orders %s=>%s:%s:%s->%s->%s' % (names,orders,last_order.id,line.order_id.id,line.order_id.partner_id.id,last_order.partner_id.id))
            #remove last '|' in names

            for k,v in orders.items():
                if not self.env['sale.order'].browse(k).virtual_sale_order_id:
                    vals['order_line_ids'] = [(6, 0, v['lines'])]
                    name = v['name']
                    if len(name) >= 1:
                        name = name[:-1]
                    vals = self._create_new_vo(vals, v['order_id'], name)
                    _logger.info("Make vo %s" % vals)
                    ctx = dict(self._context or {}, force_create=True)
                    record = super(SeleOrderVirtual, self).with_context(ctx).create(vals)
                    _logger.info("VO %s" % record)
        return record

    @api.multi
    def write(self, vals):
        if vals.get('order_line_ids'):
            for sol in self:
                orders = {}
                OrigSOL = self.env['sale.order.line'].browse(vals.get('order_line_ids'))
                for line in OrigSOL:
                    if not line.order_id.id in sol.order_ids:
                        vals['order_line_ids'].remove(vals['order_line_ids'].index(line.id))
        return super(SeleOrderVirtual, self).write(vals)

    @api.onchange('name', 'order_ids')
    def onchange_order_ids(self):
        order_id = self.env['sale.order'].browse(self.order_ids)
        if order_id:
            self.name = '(%s)-%s' % (self.name, order_id.name)

#class SaleOrderLine(models.Model):
#    _inherit = 'sale.order.line'
#
#    virtual_sale_order_id = fields.Many2one('sale.order.virtual', string='Virtual Order', copy=False, required=True)
#    display_order_id = fields.Char(string="Order Reference", compute='_compute_display_order_id', store=False)
#
#    @api.multi
#    def _compute_display_order_id(self):
#        for order_line in self:
#            order_line.display_order_id = order_line.order_id.name

class SaleOrder(models.Model):
    _inherit = 'sale.order'

#    virtual_sale_order_id = fields.Many2one('sale.order.virtual', string='Virtual Order', copy=False, ondelete='cascade', required=True, states={'draft': [('readonly', False)], 'sent': [('readonly', False)], 'virtualized': [('readonly', False)]})
    virtual_line = fields.One2many('sale.order.line',related='virtual_sale_order_id.order_line_ids', string="Virtul Orders lines", copy=False, readonly=True)
