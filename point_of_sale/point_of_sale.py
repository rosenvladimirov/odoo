# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    Copyright (C) 2013-Today GRAP (http://www.grap.coop)
#    @author Julien WESTE
#    Copyright (C) 2014 Akretion (<http://www.akretion.com>).
#    @author Sylvain LE GAL (https://twitter.com/legalsylvain)
#    @author Sylvain Calador (sylvain.calador@akretion.com).
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

import logging
import psycopg2
import time
import copy
from datetime import datetime

from openerp import tools
from openerp.osv import fields, osv
from openerp.tools import float_is_zero
from openerp.tools.translate import _

import openerp.addons.decimal_precision as dp
import openerp.addons.product.product

_logger = logging.getLogger(__name__)

class pos_config(osv.osv):
    _name = 'pos.config'

    POS_CONFIG_STATE = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('deprecated', 'Deprecated')
    ]

    def _get_currency(self, cr, uid, ids, fieldnames, args, context=None):
        result = dict.fromkeys(ids, False)
        for pos_config in self.browse(cr, uid, ids, context=context):
            if pos_config.journal_id:
                currency_id = pos_config.journal_id.currency.id or pos_config.journal_id.company_id.currency_id.id
            else:
                currency_id = self.pool['res.users'].browse(cr, uid, uid, context=context).company_id.currency_id.id
            result[pos_config.id] = currency_id
        return result

    _columns = {
        'name' : fields.char('Point of Sale Name', select=1,
             required=True, help="An internal identification of the point of sale"),
        'journal_ids' : fields.many2many('account.journal', 'pos_config_journal_rel',
             'pos_config_id', 'journal_id', 'Available Payment Methods',
             domain="[('journal_user', '=', True ), ('type', 'in', ['bank', 'cash'])]",),
        'picking_type_id': fields.many2one('stock.picking.type', 'Picking Type'),
        'stock_location_id': fields.many2one('stock.location', 'Stock Location', domain=[('usage', '=', 'internal')], required=True),
        'journal_id' : fields.many2one('account.journal', 'Sale Journal',
             domain=[('type', '=', 'sale')],
             help="Accounting journal used to post sales entries."),
        'currency_id' : fields.function(_get_currency, type="many2one", string="Currency", relation="res.currency"),
        'iface_self_checkout' : fields.boolean('Self Checkout Mode', # FIXME : this field is obsolete
             help="Check this if this point of sale should open by default in a self checkout mode. If unchecked, Odoo uses the normal cashier mode by default."),
        'iface_cashdrawer' : fields.boolean('Cashdrawer', help="Automatically open the cashdrawer"),
        'iface_payment_terminal' : fields.boolean('Payment Terminal', help="Enables Payment Terminal integration"),
        'iface_electronic_scale' : fields.boolean('Electronic Scale', help="Enables Electronic Scale integration"),
        'iface_vkeyboard' : fields.boolean('Virtual KeyBoard', help="Enables an integrated Virtual Keyboard"),
        'iface_print_via_proxy' : fields.boolean('Print via Proxy', help="Bypass browser printing and prints via the hardware proxy"),
        'iface_fprint_via_proxy': fields.boolean('Fiscal Printer on proxy', help="A Fiscal printer is available on the Proxy"),
        'iface_scan_via_proxy' : fields.boolean('Scan via Proxy', help="Enable barcode scanning with a remotely connected barcode scanner"),
        'iface_invoicing': fields.boolean('Invoicing',help='Enables invoice generation from the Point of Sale'),
        'iface_big_scrollbars': fields.boolean('Large Scrollbars',help='For imprecise industrial touchscreens'),
        'iface_price_display_taxed': fields.boolean('Display price with taxes',help='Enables show prices with taxes on the Point of Sale'),
        'receipt_header': fields.text('Receipt Header',help="A short text that will be inserted as a header in the printed receipt"),
        'receipt_footer': fields.text('Receipt Footer',help="A short text that will be inserted as a footer in the printed receipt"),
        'proxy_ip':       fields.char('IP Address', help='The hostname or ip address of the hardware proxy, Will be autodetected if left empty', size=45),

        'state' : fields.selection(POS_CONFIG_STATE, 'Status', required=True, readonly=True, copy=False),
        'sequence_id' : fields.many2one('ir.sequence', 'Order IDs Sequence', readonly=True,
            help="This sequence is automatically created by Odoo but you can change it "\
                "to customize the reference numbers of your orders.", copy=False),
        'session_ids': fields.one2many('pos.session', 'config_id', 'Sessions'),
        'group_by' : fields.boolean('Group Journal Items', help="Check this if you want to group the Journal Items by Product while closing a Session"),
        'pricelist_id': fields.many2one('product.pricelist','Pricelist', required=True),
        'company_id': fields.many2one('res.company', 'Company', required=True),
        'product_id': fields.many2one('product.product', 'Advance Product', domain=[('type', '=', 'money')], help="""Select a product of type service which is called 'Advance Product'.
                            You may have to create it and set it as a default value on this field."""),
        'barcode_product':  fields.char('Product Barcodes', size=64, help='The pattern that identifies product barcodes'),
        'barcode_cashier':  fields.char('Cashier Barcodes', size=64, help='The pattern that identifies cashier login barcodes'),
        'barcode_customer': fields.char('Customer Barcodes',size=64, help='The pattern that identifies customer\'s client card barcodes'),
        'barcode_price':    fields.char('Price Barcodes',   size=64, help='The pattern that identifies a product with a barcode encoded price'),
        'barcode_weight':   fields.char('Weight Barcodes',  size=64, help='The pattern that identifies a product with a barcode encoded weight'),
        'barcode_discount': fields.char('Discount Barcodes',  size=64, help='The pattern that identifies a product with a barcode encoded discount'),
        'payment_loan': fields.boolean('Work with credit',help='Enables to sell on credit in the Point of Sale'),
        'allow_store_draft_order': fields.boolean('Allow to Store Draft Orders',help="If you check this field,"
                                                                                     "  users will have the possibility to let some PoS orders in a draft"
                                                                                     " state, and allow the customer to paid later.\n"
                                                                                     "Order in a draft state will not generate entries during the close"
                                                                                     " of the session."),
        'required_password': fields.boolean('Password Required', default=False, help="Required password when change cashier on POS screen"),
    }

    def _check_cash_control(self, cr, uid, ids, context=None):
        return all(
            (sum(int(journal.cash_control) for journal in record.journal_ids) <= 1)
            for record in self.browse(cr, uid, ids, context=context)
        )

    def _check_company_location(self, cr, uid, ids, context=None):
        for config in self.browse(cr, uid, ids, context=context):
            if config.stock_location_id.company_id and config.stock_location_id.company_id.id != config.company_id.id:
                return False
        return True

    def _check_company_journal(self, cr, uid, ids, context=None):
        for config in self.browse(cr, uid, ids, context=context):
            if config.journal_id and config.journal_id.company_id.id != config.company_id.id:
                return False
        return True

    def _check_company_payment(self, cr, uid, ids, context=None):
        for config in self.browse(cr, uid, ids, context=context):
            journal_ids = [j.id for j in config.journal_ids]
            if self.pool['account.journal'].search(cr, uid, [
                    ('id', 'in', journal_ids),
                    ('company_id', '!=', config.company_id.id)
                ], count=True, context=context):
                return False
        return True

    _constraints = [
        (_check_cash_control, "You cannot have two cash controls in one Point Of Sale !", ['journal_ids']),
        (_check_company_location, "The company of the stock location is different than the one of point of sale", ['company_id', 'stock_location_id']),
        (_check_company_journal, "The company of the sale journal is different than the one of point of sale", ['company_id', 'journal_id']),
        (_check_company_payment, "The company of a payment method is different than the one of point of sale", ['company_id', 'journal_ids']),
    ]

    def name_get(self, cr, uid, ids, context=None):
        result = []
        states = {
            'opening_control': _('Opening Control'),
            'opened': _('In Progress'),
            'closing_control': _('Closing Control'),
            'closed': _('Closed & Posted'),
        }
        for record in self.browse(cr, uid, ids, context=context):
            if (not record.session_ids) or (record.session_ids[0].state=='closed'):
                result.append((record.id, record.name+' ('+_('not used')+')'))
                continue
            session = record.session_ids[0]
            result.append((record.id, record.name + ' ('+session.user_id.name+')')) #, '+states[session.state]+')'))
        return result

    def _default_sale_journal(self, cr, uid, context=None):
        company_id = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id.id
        res = self.pool.get('account.journal').search(cr, uid, [('type', '=', 'sale'), ('company_id', '=', company_id)], limit=1, context=context)
        return res and res[0] or False

    def _default_pricelist(self, cr, uid, context=None):
        res = self.pool.get('product.pricelist').search(cr, uid, [('type', '=', 'sale')], limit=1, context=context)
        return res and res[0] or False

    def _get_default_location(self, cr, uid, context=None):
        wh_obj = self.pool.get('stock.warehouse')
        user = self.pool.get('res.users').browse(cr, uid, uid, context)
        res = wh_obj.search(cr, uid, [('company_id', '=', user.company_id.id)], limit=1, context=context)
        if res and res[0]:
            return wh_obj.browse(cr, uid, res[0], context=context).lot_stock_id.id
        return False

    def _get_default_company(self, cr, uid, context=None):
        company_id = self.pool.get('res.users')._get_company(cr, uid, context=context)
        return company_id

    _defaults = {
        'state' : POS_CONFIG_STATE[0][0],
        'journal_id': _default_sale_journal,
        'group_by' : True,
        'pricelist_id': _default_pricelist,
        'iface_invoicing': True,
        'stock_location_id': _get_default_location,
        'company_id': _get_default_company,
        'barcode_product': '*',
        'barcode_cashier': '041*',
        'barcode_customer':'042*',
        'barcode_order':'043*',
        'barcode_weight':  '21xxxxxNNDDD', 
        'barcode_discount':'22xxxxxxxxNN',
        'barcode_price':   '23xxxxxNNNDD',
    }

    def onchange_picking_type_id(self, cr, uid, ids, picking_type_id, context=None):
        p_type_obj = self.pool.get("stock.picking.type")
        p_type = p_type_obj.browse(cr, uid, picking_type_id, context=context)
        if p_type.default_location_src_id and p_type.default_location_src_id.usage == 'internal' and p_type.default_location_dest_id and p_type.default_location_dest_id.usage == 'customer':
            return {'value': {'stock_location_id': p_type.default_location_src_id.id}}
        return False

    def set_active(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state' : 'active'}, context=context)

    def set_inactive(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state' : 'inactive'}, context=context)

    def set_deprecate(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state' : 'deprecated'}, context=context)

    def create(self, cr, uid, values, context=None):
        ir_sequence = self.pool.get('ir.sequence')
        # force sequence_id field to new pos.order sequence
        values['sequence_id'] = ir_sequence.create(cr, uid, {
            'name': 'POS Order %s' % values['name'],
            'padding': 4,
            'prefix': "%s/"  % values['name'],
            'code': "pos.order",
            'company_id': values.get('company_id', False),
        }, context=context)

        # TODO master: add field sequence_line_id on model
        # this make sure we always have one available per company
        ir_sequence.create(cr, uid, {
            'name': 'POS order line %s' % values['name'],
            'padding': 4,
            'prefix': "%s/"  % values['name'],
            'code': "pos.order.line",
            'company_id': values.get('company_id', False),
        }, context=context)

        return super(pos_config, self).create(cr, uid, values, context=context)

    def unlink(self, cr, uid, ids, context=None):
        for obj in self.browse(cr, uid, ids, context=context):
            if obj.sequence_id:
                obj.sequence_id.unlink()
        return super(pos_config, self).unlink(cr, uid, ids, context=context)

class pos_session(osv.osv):
    _name = 'pos.session'
    _order = 'id desc'

    POS_SESSION_STATE = [
        ('opening_control', 'Opening Control'),  # Signal open
        ('opened', 'In Progress'),                    # Signal closing
        ('closing_control', 'Closing Control'),  # Signal close
        ('closed', 'Closed & Posted'),
    ]

    def _compute_cash_all(self, cr, uid, ids, fieldnames, args, context=None):
        result = dict()

        for record in self.browse(cr, uid, ids, context=context):
            result[record.id] = {
                'cash_journal_id' : False,
                'cash_register_id' : False,
                'cash_control' : False,
            }
            for st in record.statement_ids:
                if st.journal_id.cash_control == True:
                    result[record.id]['cash_control'] = True
                    result[record.id]['cash_journal_id'] = st.journal_id.id
                    result[record.id]['cash_register_id'] = st.id

        return result

    _columns = {
        'config_id' : fields.many2one('pos.config', 'Point of Sale',
                                      help="The physical point of sale you will use.",
                                      required=True,
                                      select=1,
                                      domain="[('state', '=', 'active')]",
                                     ),

        'name' : fields.char('Session ID', required=True, readonly=True),
        'user_id' : fields.many2one('res.users', 'Responsible',
                                    required=True,
                                    select=1,
                                    readonly=True,
                                    states={'opening_control' : [('readonly', False)]}
                                   ),
        'currency_id' : fields.related('config_id', 'currency_id', type="many2one", relation='res.currency', string="Currnecy"),
        'start_at' : fields.datetime('Opening Date', readonly=True),
        'stop_at' : fields.datetime('Closing Date', readonly=True),

        'state' : fields.selection(POS_SESSION_STATE, 'Status',
                required=True, readonly=True,
                select=1, copy=False),

        'sequence_number': fields.integer('Order Sequence Number', help='A sequence number that is incremented with each order'),
        'login_number':  fields.integer('Login Sequence Number', help='A sequence number that is incremented each time a user resumes the pos session'),

        'cash_control' : fields.function(_compute_cash_all,
                                         multi='cash',
                                         type='boolean', string='Has Cash Control'),
        'cash_journal_id' : fields.function(_compute_cash_all,
                                            multi='cash',
                                            type='many2one', relation='account.journal',
                                            string='Cash Journal', store=True),
        'cash_register_id' : fields.function(_compute_cash_all,
                                             multi='cash',
                                             type='many2one', relation='account.bank.statement',
                                             string='Cash Register', store=True),

        'opening_details_ids' : fields.related('cash_register_id', 'opening_details_ids',
                type='one2many', relation='account.cashbox.line',
                string='Opening Cash Control'),
        'details_ids' : fields.related('cash_register_id', 'details_ids',
                type='one2many', relation='account.cashbox.line',
                string='Cash Control'),

        'cash_register_balance_end_real' : fields.related('cash_register_id', 'balance_end_real',
                type='float',
                digits_compute=dp.get_precision('Account'),
                string="Ending Balance",
                help="Total of closing cash control lines.",
                readonly=True),
        'cash_register_balance_start' : fields.related('cash_register_id', 'balance_start',
                type='float',
                digits_compute=dp.get_precision('Account'),
                string="Starting Balance",
                help="Total of opening cash control lines.",
                readonly=True),
        'cash_register_total_entry_encoding' : fields.related('cash_register_id', 'total_entry_encoding',
                string='Total Cash Transaction',
                readonly=True,
                help="Total of all paid sale orders"),
        'cash_register_balance_end' : fields.related('cash_register_id', 'balance_end',
                type='float',
                digits_compute=dp.get_precision('Account'),
                string="Theoretical Closing Balance",
                help="Sum of opening balance and transactions.",
                readonly=True),
        'cash_register_difference' : fields.related('cash_register_id', 'difference',
                type='float',
                string='Difference',
                help="Difference between the theoretical closing balance and the real closing balance.",
                readonly=True),

        'journal_ids' : fields.related('config_id', 'journal_ids',
                                       type='many2many',
                                       readonly=True,
                                       relation='account.journal',
                                       string='Available Payment Methods'),
        'order_ids' : fields.one2many('pos.order', 'session_id', 'Orders'),

        'statement_ids' : fields.one2many('account.bank.statement', 'pos_session_id', 'Bank Statement', readonly=True),
    }

    _defaults = {
        'name' : '/',
        'user_id' : lambda obj, cr, uid, context: uid,
        'state' : 'opening_control',
        'sequence_number': 1,
        'login_number': 0,
    }

    _sql_constraints = [
        ('uniq_name', 'unique(name)', "The name of this POS Session must be unique !"),
    ]

    def _check_unicity(self, cr, uid, ids, context=None):
        for session in self.browse(cr, uid, ids, context=None):
            # open if there is no session in 'opening_control', 'opened', 'closing_control' for one user
            domain = [
                ('state', 'not in', ('closed','closing_control')),
                ('user_id', '=', session.user_id.id)
            ]
            count = self.search_count(cr, uid, domain, context=context)
            if count>1:
                return False
        return True

    def _check_pos_config(self, cr, uid, ids, context=None):
        for session in self.browse(cr, uid, ids, context=None):
            domain = [
                ('state', '!=', 'closed'),
                ('config_id', '=', session.config_id.id)
            ]
            count = self.search_count(cr, uid, domain, context=context)
            if count>1:
                return False
        return True

    _constraints = [
        (_check_unicity, "You cannot create two active sessions with the same responsible!", ['user_id', 'state']),
        (_check_pos_config, "You cannot create two active sessions related to the same point of sale!", ['config_id']),
    ]

    def create(self, cr, uid, values, context=None):
        context = dict(context or {})
        config_id = values.get('config_id', False) or context.get('default_config_id', False)
        if not config_id:
            raise osv.except_osv( _('Error!'),
                _("You should assign a Point of Sale to your session."))

        # journal_id is not required on the pos_config because it does not
        # exists at the installation. If nothing is configured at the
        # installation we do the minimal configuration. Impossible to do in
        # the .xml files as the CoA is not yet installed.
        jobj = self.pool.get('pos.config')
        pos_config = jobj.browse(cr, uid, config_id, context=context)
        context.update({'company_id': pos_config.company_id.id})
        if not pos_config.journal_id:
            jid = jobj.default_get(cr, uid, ['journal_id'], context=context)['journal_id']
            if jid:
                jobj.write(cr, openerp.SUPERUSER_ID, [pos_config.id], {'journal_id': jid}, context=context)
            else:
                raise osv.except_osv( _('error!'),
                    _("Unable to open the session. You have to assign a sale journal to your point of sale."))

        # define some cash journal if no payment method exists
        if not pos_config.journal_ids:
            journal_proxy = self.pool.get('account.journal')
            cashids = journal_proxy.search(cr, uid, [('journal_user', '=', True), ('type','=','cash')], context=context)
            if not cashids:
                cashids = journal_proxy.search(cr, uid, [('type', '=', 'cash')], context=context)
                if not cashids:
                    cashids = journal_proxy.search(cr, uid, [('journal_user','=',True)], context=context)

            journal_proxy.write(cr, openerp.SUPERUSER_ID, cashids, {'journal_user': True})
            jobj.write(cr, openerp.SUPERUSER_ID, [pos_config.id], {'journal_ids': [(6,0, cashids)]})


        pos_config = jobj.browse(cr, uid, config_id, context=context)
        bank_statement_ids = []
        for journal in pos_config.journal_ids:
            bank_values = {
                'journal_id' : journal.id,
                'user_id' : uid,
                'company_id' : pos_config.company_id.id
            }
            statement_id = self.pool.get('account.bank.statement').create(cr, uid, bank_values, context=context)
            bank_statement_ids.append(statement_id)

        values.update({
            'name': self.pool['ir.sequence'].get(cr, uid, 'pos.session', context=context),
            'statement_ids' : [(6, 0, bank_statement_ids)],
            'config_id': config_id
        })
        res = super(pos_session, self).create(cr, uid, values, context=context)
        """Recover all PoS Order in 'draft' state and associate them to the new
        Pos Session"""
        pos_order_obj = self.pool['pos.order']
        draftOrders_ids = pos_order_obj.search(cr, uid, [('state', '=', 'draft'), ('user_id', '=', uid)], context=context)
        if draftOrders_ids:
            pos_order_obj.write(cr, uid, draftOrders_ids, {'session_id': res.id}, context=context)
        return res

    def unlink(self, cr, uid, ids, context=None):
        for obj in self.browse(cr, uid, ids, context=context):
            for statement in obj.statement_ids:
                statement.unlink(context=context)
        return super(pos_session, self).unlink(cr, uid, ids, context=context)

    def open_cb(self, cr, uid, ids, context=None):
        """
        call the Point Of Sale interface and set the pos.session to 'opened' (in progress)
        """
        context = dict(context or {})

        if isinstance(ids, (int, long)):
            ids = [ids]

        this_record = self.browse(cr, uid, ids[0], context=context)
        this_record.signal_workflow('open')

        context.update(active_id=this_record.id)

        return {
            'type' : 'ir.actions.act_url',
            'url'  : '/pos/web/',
            'target': 'self',
        }

    def login(self, cr, uid, ids, context=None):
        this_record = self.browse(cr, uid, ids[0], context=context)
        this_record.write({
            'login_number': this_record.login_number+1,
        })

    def wkf_action_open(self, cr, uid, ids, context=None):
        # second browse because we need to refetch the data from the DB for cash_register_id
        for record in self.browse(cr, uid, ids, context=context):
            values = {}
            if not record.start_at:
                values['start_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            values['state'] = 'opened'
            record.write(values)
            for st in record.statement_ids:
                st.button_open()

        return self.open_frontend_cb(cr, uid, ids, context=context)

    def wkf_action_opening_control(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state' : 'opening_control'}, context=context)

    def wkf_action_closing_control(self, cr, uid, ids, context=None):
        for session in self.browse(cr, uid, ids, context=context):
            """Remove all PoS Orders in 'draft' to the sessions we want
            to close.
            Check if there is any Partial Paid Orders"""
            self._remove_session_from_draft_orders(cr, uid, session, context=context)
            for statement in session.statement_ids:
                if (statement != session.cash_register_id) and (statement.balance_end != statement.balance_end_real):
                    self.pool.get('account.bank.statement').write(cr, uid, [statement.id], {'balance_end_real': statement.balance_end})
        return self.write(cr, uid, ids, {'state' : 'closing_control', 'stop_at' : time.strftime('%Y-%m-%d %H:%M:%S')}, context=context)

    def wkf_action_close(self, cr, uid, ids, context=None):
        # Close CashBox
        for record in self.browse(cr, uid, ids, context=context):
            for st in record.statement_ids:
                if abs(st.difference) > st.journal_id.amount_authorized_diff:
                    # The pos manager can close statements with maximums.
                    if not self.pool.get('ir.model.access').check_groups(cr, uid, "point_of_sale.group_pos_manager"):
                        raise osv.except_osv( _('Error!'),
                            _("Your ending balance is too different from the theoretical cash closing (%.2f), the maximum allowed is: %.2f. You can contact your manager to force it.") % (st.difference, st.journal_id.amount_authorized_diff))
                if (st.journal_id.type not in ['bank', 'cash']):
                    raise osv.except_osv(_('Error!'),
                        _("The type of the journal for your payment method should be bank or cash "))
                getattr(st, 'button_confirm_%s' % st.journal_id.type)(context=context)
        self._confirm_orders(cr, uid, ids, context=context)
        self.write(cr, uid, ids, {'state' : 'closed'}, context=context)

        obj = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'point_of_sale', 'menu_point_root')[1]
        return {
            'type' : 'ir.actions.client',
            'name' : 'Point of Sale Menu',
            'tag' : 'reload',
            'params' : {'menu_id': obj},
        }

    def _remove_session_from_draft_orders(self, cr, uid, session, context=None):
        pos_order_obj = self.pool.get('pos.order')
        order_ids = []
        for order in session.order_ids:
            # Check if there is a partial payment
            #if order.is_partial_paid:
            #    raise osv.except_osv(
            #            _('Warning!'),
            #            _("You cannot confirm this session, because '%s' is"
            #            " still in 'draft' state with associated payments.(%s)\n\n"
            #            " Please finish to pay rest (%s) of this Order first. " % ((order.name).encode('utf-8', 'replace'), order.is_partial_paid, abs(order.amount_total - order.amount_paid))))
            # remove session id on the current Order if it is in draft state
            if (order.state == 'draft' or order.state == 'progress') and\
                    session.config_id.allow_store_draft_order:
                order_ids.append(order.id)
        if order_ids:
            pos_order_obj.write(cr, uid, order_ids, {'session_id': False}, context=context)
        return True

    def _confirm_orders(self, cr, uid, ids, context=None):
        pos_order_obj = self.pool.get('pos.order')
        for session in self.browse(cr, uid, ids, context=context):
            company_id = session.config_id.journal_id.company_id.id
            local_context = dict(context or {}, force_company=company_id)
            order_ids = [order.id for order in session.order_ids if order.state == 'paid']

            move_id = pos_order_obj._create_account_move(cr, uid, session.start_at, session.name, session.config_id.journal_id.id, company_id, context=context)

            pos_order_obj._create_account_move_line(cr, uid, order_ids, session, move_id, context=local_context)

            for order in session.order_ids:
                if order.state == 'done':
                    continue
                if order.state not in ('paid', 'invoiced'):
                    raise osv.except_osv(
                        _('Error!'),
                        _("You cannot confirm all orders of this session, because they have not the 'paid' status"))
                else:
                    pos_order_obj.signal_workflow(cr, uid, [order.id], 'done')

        return True

    def open_frontend_cb(self, cr, uid, ids, context=None):
        context = dict(context or {})
        if not ids:
            return {}
        for session in self.browse(cr, uid, ids, context=context):
            if session.user_id.id != uid:
                raise osv.except_osv(
                        _('Error!'),
                        _("You cannot use the session of another users. This session is owned by %s. Please first close this one to use this point of sale." % session.user_id.name))
        context.update({'active_id': ids[0]})
        return {
            'type' : 'ir.actions.act_url',
            'target': 'self',
            'url':   '/pos/web/',
        }

class pos_order(osv.osv):
    _name = "pos.order"
    _description = "Point of Sale"
    _order = "id desc"
    #_track = {
    #    'state': {
    #        'pos.mt_po_picking': lambda self, cr, uid, obj, ctx=None: True,
    #    },
    #}

    def _amount_line_tax(self, cr, uid, line, context=None):
        account_tax_obj = self.pool['account.tax']
        #taxes_ids = [tax for tax in line.product_id.taxes_id if tax.company_id.id == line.order_id.company_id.id]
        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
        taxes = account_tax_obj.compute_all(cr, uid, line.tax_ids, price, line.qty, line.product_id, line.order_id.partner_id or False)['taxes']
        val = 0.0
        for c in taxes:
            val += c.get('amount', 0.0)
        return val

    def _order_fields(self, cr, uid, ui_order, context=None):
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        return {
            'name':         ui_order['name'],
            'user_id':      ui_order['user_id'] or False,
            'session_id':   ui_order['pos_session_id'],
            'ean_uid':      ui_order['ean_uid'],
            'lines':        ui_order['lines'],
            'pos_reference':ui_order['name'],
            'pricelist_id': ui_order['pricelist_id'],
            'fiscal_position': ui_order['fiscal_position'] or user.company_id.partner_id.property_account_position,
            'partner_id':   ui_order['partner_id'] or False,
        }

    def _payment_fields(self, cr, uid, ui_paymentline, context=None):
        return {
            'amount':       ui_paymentline['amount'] or 0.0,
            'payment_date': ui_paymentline['name'],
            'statement_id': ui_paymentline['statement_id'],
            'payment_name': ui_paymentline.get('note',False),
            'journal':      ui_paymentline['journal_id'],
        }

    # This deals with orders that belong to a closed session. In order
    # to recover from this we:
    # - assign the order to another compatible open session
    # - if that doesn't exist, create a new one
    def _get_valid_session(self, cr, uid, order, context=None):
        session = self.pool.get('pos.session')
        closed_session = session.browse(cr, uid, order['pos_session_id'], context=context)
        open_sessions = session.search(cr, uid, [('state', '=', 'opened'),
                                                 ('config_id', '=', closed_session.config_id.id),
                                                 ('user_id', '=', closed_session.user_id.id)],
                                       limit=1, order="start_at DESC", context=context)

        if open_sessions:
            return open_sessions[0]
        else:
            new_session_id = session.create(cr, uid, {
                'config_id': closed_session.config_id.id,
            }, context=context)
            new_session = session.browse(cr, uid, new_session_id, context=context)

            # bypass opening_control (necessary when using cash control)
            new_session.signal_workflow('open')

            return new_session_id

    def _process_draft_order(self, cr, uid, orders, context=None):
        order_ids = []
        for order_tmp in orders:
            order_data = order_tmp['data']
            fields = self._order_fields(cr, uid, order_data, context=context)
            statements_data = order_data['statement_ids']
            order_data.pop('statement_ids')
            order_id = order_tmp.get('order_id', False)
            if order_id:
                # write
                order = self.search(cr, uid, [('id', '=', order_id)], context=context)
                if order:
                    id = self.write(cr, uid, order, fields, context=context)
                else:
                    id = self.create(cr, uid, fields, context=context)
            else:
                # create Order
                id = self.create(cr, uid, fields, context=context)
            order_ids.append(id)
        return order_ids

    def _process_refund_order(self, cr, uid, orders, context=None):
        order_ids = []
        for order_tmp in orders:
            del order_tmp['data']['order_id']
            for inx, line in enumerate(order_tmp['data']['lines']):
                if line[2].get('order_id', False):
                    del order_tmp['data']['lines'][inx][2]['order_id']

            order_id, pay_orders = self._process_order(cr, uid, order_tmp['data'], context=context)
            order_ids.append(order_id)
            try:
                self.signal_workflow(cr, uid, [order_id], 'progress')
            except psycopg2.OperationalError:
                # do not hide transactional errors, the order(s) won't be saved!
                raise
            except Exception as e:
                _logger.error('Could not fully process the POS Order: %s', tools.ustr(e))

        return order_ids

    def _process_pay_order(self, cr, uid, orders, context=None):
        #prod_obj = self.pool.get('product.product')
        pl_obj = self.pool.get('product.pricelist')
        part_obj = self.pool.get('res.partner')
        prod_obj = self.pool.get('product.product')
        order_ids = []
        for order_tmp in orders:
            _logger.debug("Advance line %s" % order_tmp)
            # payment allwise make invoice
            order_id = order_tmp['data'].get('order_id', False)
            if order_id:
                order = self._order_fields(cr, uid, order_tmp['data'], context=context)
                curr = pl_obj.browse(cr, uid, order['pricelist_id'], context=context)
                part = part_obj.browse(cr, uid, order['partner_id'], context=context)
                lines = []
                inv = {
                    'name': '',
                    'origin': order['name'],
                    'date_invoice': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'account_id': part.property_account_receivable.id,
                    'type': 'out_invoice',
                    'reference': order['name'],
                    'partner_id': order['partner_id'],
                    'pricelist_id': order['pricelist_id'],
                    'fiscal_position': order_tmp['data']['fiscal_position'],
                    'currency_id': curr.currency_id.id, # considering partner's sale pricelist's currency
                }
                for line in order['lines']:
                    inv_line = {
                        'product_id': line[2]['product_id'],
                        'product_uom': line[2]['product_uom'],
                        'quantity': line[2]['qty'],
                        'price_unit': line[2]['price_unit'],
                        'name': line[2]['product_description_sale'] or ("[%s] %s" % (line[2]['product_id'], prod_obj.browse(cr, uid, line[2]['product_id'], context=context).name)),
                        'discount': line[2]['discount'],
                        'invoice_line_tax_id': line[2]['tax_ids'],
                    }
                    lines.append(inv_line)
                _logger.debug("Get payments %s:%s:%s:%s:%s" % (inv, lines, order, curr, part))
                inv_id = self._make_invoice(cr, uid, inv, lines, context)
                ## self.write(cr, uid, [order_id], {'invoice_id': inv_id, 'state': 'invoiced'}, context=context)
                # multi invoice version
                cr.execute('insert into pos_order_invoice_rel (order_id,invoice_id) values (%s,%s)', (order_id, inv_id))
                self.invalidate_cache(cr, uid, ['invoice_ids'], [order_id], context=context)
                self.signal_workflow(cr, uid, [order_id], 'invoice')
                #order_obj = self.browse(cr, uid, order_id, context)
                #self.pool['account.invoice'].signal_workflow(cr, uid, [order_obj.invoice_id.id], 'invoice_open')
                journal_ids = set()
                for payments in order_tmp['data']['statement_ids']:
                    self.add_payment(cr, uid, order_id, self._payment_fields(cr, uid, payments[2], context=context), context=context)
                    journal_ids.add(payments[2]['journal_id'])
                order_ids.append(order_id)
        return order_ids

    def _process_base_order(self, cr, uid, orders, context=None):
        order_ids = []
        for tmp_order in orders:
            to_invoice = tmp_order['to_invoice']
            order = tmp_order['data']
            order_id, pay_orders = self._process_order(cr, uid, order, context=context)
            order_ids.append(order_id)

            try:
                self.signal_workflow(cr, uid, [order_id], 'progress')
            except psycopg2.OperationalError:
                # do not hide transactional errors, the order(s) won't be saved!
                raise
            except Exception as e:
                _logger.error('Could not fully process the POS Order: %s', tools.ustr(e))

            if pay_orders:
                pay_order = dict(to_invoice=True, data=pay_orders)
                order_id = self._process_pay_order(cr, uid, [pay_order], context=context)
                order_ids += order_id

            if to_invoice:
                self.action_invoice(cr, uid, [order_id], context)
        return order_ids

    def _process_order(self, cr, uid, order, context=None):
        session = self.pool.get('pos.session').browse(cr, uid, order['pos_session_id'], context=context)

        if session.state == 'closing_control' or session.state == 'closed':
            session_id = self._get_valid_session(cr, uid, order, context=context)
            session = self.pool.get('pos.session').browse(cr, uid, session_id, context=context)
            order['pos_session_id'] = session_id

        _logger.debug("Get order %s" % (order))

        new_order = False
        pay_order = False
        order_id = order.get('order_id', False)
        #first check for advance payment
        new_lines = []
        for inx, line in enumerate(order['lines']):
            if line[2]['product_type'] == 'money':
                new_lines.append(line)
                order['lines'].remove(line)
            else:
                del order['lines'][inx][2]['product_type']

        # second separate advance payments lines
        new_statement = []
        for inx, line in enumerate(order['statement_ids']):
            if line[2]['type'] == 'advance':
                new_statement.append(line)
                order['statement_ids'].remove(line)

        fields = self._order_fields(cr, uid, order, context=context)
        _logger.debug("Get order fields %s=>%s" % (order_id, fields))
        if not order_id:
            # write
            #self.write(cr, uid, order_id, fields, context=context)
            new_order = True
            # create Order
            order_id = self.create(cr, uid, fields, context=context)

        journal_ids = set()
        #_logger.info("Process order %s:%s->%s=>%s" % (order_id,self.browse(cr,uid,[order_id],context=context),order,order['statement_ids']))
        for payments in order['statement_ids']:
            if payments:
                self.add_payment(cr, uid, order_id, self._payment_fields(cr, uid, payments[2], context=context), context=context)
                journal_ids.add(payments[2]['journal_id'])

        if session.sequence_number <= order['sequence_number'] and new_order:
            session.write({'sequence_number': order['sequence_number'] + 1})
            session.refresh()

        if not float_is_zero(order['amount_return'], self.pool.get('decimal.precision').precision_get(cr, uid, 'Account')):
            cash_journal = session.cash_journal_id.id
            if not cash_journal:
                # Select for change one of the cash journals used in this payment
                cash_journal_ids = self.pool['account.journal'].search(cr, uid, [
                    ('type', '=', 'cash'),
                    ('id', 'in', list(journal_ids)),
                ], limit=1, context=context)
                if not cash_journal_ids:
                    # If none, select for change one of the cash journals of the POS
                    # This is used for example when a customer pays by credit card
                    # an amount higher than total amount of the order and gets cash back
                    cash_journal_ids = [statement.journal_id.id for statement in session.statement_ids
                                        if statement.journal_id.type == 'cash']
                    if not cash_journal_ids:
                        raise osv.except_osv( _('error!'),
                            _("No cash statement found for this session. Unable to record returned cash."))
                cash_journal = cash_journal_ids[0]
            self.add_payment(cr, uid, order_id, {
                'amount': -order['amount_return'],
                'payment_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                'payment_name': _('return'),
                'journal': cash_journal,
            }, context=context)

        if new_lines and new_statement:
            pay_order = copy.deepcopy(order)
            pay_order['lines'] = new_lines
            pay_order['order_id'] = order_id
            pay_order['statement_ids'] = new_statement

        return order_id, pay_order

    def create_from_ui(self, cr, uid, orders, context=None):
        # Keep only new orders
        submitted_references = [o['data']['name'] for o in orders]
        existing_order_ids = self.search(cr, uid, [('pos_reference', 'in', submitted_references)], context=context)
        existing_orders = self.read(cr, uid, existing_order_ids, ['pos_reference'], context=context)
        existing_references = set([o['pos_reference'] for o in existing_orders])
        existing_ids = set([o['id'] for o in existing_orders])

        orders_to_save = orders = [o for o in orders if o['data']['name'] not in existing_references or o['data'].get('order_id', False) in existing_ids]
        #orders_to_replace = orders = [o for o in orders if o['data']['name'] in existing_references]
        #_logger.debug("JSON order %s" % orders_to_save)
        _logger.info("Existing orders %s==>%s:%s:%s=>%s" % (orders_to_save,existing_orders, existing_ids, existing_references, orders))

        order_ids = []
        draft_orders = []
        refund_orders = []
        pay_orders = []
        state = 'new'
        for tmp_order in orders_to_save:
            try:
                state = tmp_order['data']['po_state']
            except KeyError:
                _logger.debug("No po_state %s" % KeyError)
            else:
                if state  == 'standart':
                    draft_orders.append(tmp_order)
                    orders.remove(tmp_order)
                elif state == 'refund':
                    refund_orders.append(tmp_order)
                    orders.remove(tmp_order)
                #elif state == 'merge':
                elif state == 'pay':
                    pay_orders.append(tmp_order)
                    orders.remove(tmp_order)
        orders_to_save = orders
        # First process draft orders
        if draft_orders:
            order_id = self._process_draft_order(cr, uid, draft_orders, context=context)
            order_ids += order_id
        # next process refund orders
        if refund_orders:
            order_id = self._process_refund_order(cr, uid, refund_orders, context=context)
            order_ids += order_id
        # next process payment for old orders
        if pay_orders:
            order_id = self._process_pay_order(cr, uid, pay_orders, context=context)
            order_ids += order_id

        # finaly rest of orders
        if orders_to_save:
            order_id = self._process_base_order(cr, uid, orders_to_save, context=context)
            order_ids += order_id

        # checк rest and send paid signal
        for tmp_order in self.browse(cr, uid, order_ids, context=context):
            if float_is_zero(tmp_order.amount_total - tmp_order.amount_paid, self.pool.get('decimal.precision').precision_get(cr, uid, 'Account')):
                _logger.debug("Paid %s" % tmp_order)
                if tmp_order.invoice_ids:
                    self.signal_workflow(cr, uid, [tmp_order.id], 'invoice')
                try:
                    self.signal_workflow(cr, uid, [tmp_order.id], 'paid')
                except psycopg2.OperationalError:
                    # do not hide transactional errors, the order(s) won't be saved!
                    raise
                except Exception as e:
                    _logger.error('Could not fully process the POS Order: %s', tools.ustr(e))
        return order_ids

    def write(self, cr, uid, ids, vals, context=None):
        res = super(pos_order, self).write(cr, uid, ids, vals, context=context)
        #If you change the partner of the PoS order, change also the partner of the associated bank statement lines
        partner_obj = self.pool.get('res.partner')
        bsl_obj = self.pool.get("account.bank.statement.line")
        if 'partner_id' in vals:
            for posorder in self.browse(cr, uid, ids, context=context):
                if posorder.invoice_ids:
                    raise osv.except_osv( _('Error!'), _("You cannot change the partner of a POS order for which an invoice has already been issued."))
                if vals['partner_id']:
                    p_id = partner_obj.browse(cr, uid, vals['partner_id'], context=context)
                    part_id = partner_obj._find_accounting_partner(p_id).id
                else:
                    part_id = False
                bsl_ids = [x.id for x in posorder.statement_ids]
                bsl_obj.write(cr, uid, bsl_ids, {'partner_id': part_id}, context=context)
        return res

    def unlink(self, cr, uid, ids, context=None):
        for rec in self.browse(cr, uid, ids, context=context):
            if rec.state not in ('draft','cancel'):
                raise osv.except_osv(_('Unable to Delete!'), _('In order to delete a sale, it must be new or cancelled.'))
            else:
                cr.execute('delete from pos_order_invoice_rel where order_id = %s', [rec.id])
                self.invalidate_cache(cr, uid, ['invoice_ids'], [rec.id], context=context)
                #self.pool.get('stock.picking').unlink(cr, uid, rec.picking_ids, context=context)
                #cr.execute('delete from picking_ids where order_id = %s', [rec.id])
                #self.invalidate_cache(cr, uid, ['picking_ids'], [rec.id], context=context)
        return super(pos_order, self).unlink(cr, uid, ids, context=context)

    def onchange_partner_id(self, cr, uid, ids, part=False, context=None):
        if not part:
            return {'value': {}}
        pricelist = self.pool.get('res.partner').browse(cr, uid, part, context=context).property_product_pricelist.id
        return {'value': {'pricelist_id': pricelist}}

    def _amount_all(self, cr, uid, ids, name, args, context=None):
        cur_obj = self.pool.get('res.currency')
        res = {}
        for order in self.browse(cr, uid, ids, context=context):
            res[order.id] = {
                'amount_total': 0.0,
                'amount_paid': 0.0,
                'amount_return': 0.0,
                'amount_rest': 0.0,
                'amount_tax': 0.0,
            }
            val1 = val2 = 0.0
            cur = order.pricelist_id.currency_id
            for payment in order.statement_ids:
                res[order.id]['amount_paid'] +=  payment.amount
                res[order.id]['amount_return'] += (payment.amount < 0 and payment.amount or 0)
            for line in order.lines:
                val1 += self._amount_line_tax(cr, uid, line, context=context)
                val2 += line.price_subtotal
            res[order.id]['amount_tax'] = cur_obj.round(cr, uid, cur, val1)
            amount_untaxed = cur_obj.round(cr, uid, cur, val2)
            res[order.id]['amount_total'] = res[order.id]['amount_tax'] + amount_untaxed
            res[order.id]['amount_rest'] = res[order.id]['amount_total'] - res[order.id]['amount_paid']
        return res

    def _amount_partial_paid(self, cr, uid, ids, name, args, context=None):
        res = {}
        for order in self.browse(cr, uid, ids, context=context):
            _logger.info("Partical %s" % (order.amount_rest))
            if not float_is_zero(order.amount_rest, self.pool.get('decimal.precision').precision_get(cr, uid, 'Account')):
                res[order.id] = True
        return res

    def _invoice_exists(self, cursor, user, ids, name, arg, context=None):
        res = {}
        for po in self.browse(cursor, user, ids, context=context):
            #_logger.info("POS order info %s" % sale.virtual_line)
            res[po.id] = False
            if po.invoice_ids:
                res[po.id] = True
        return res

    def _invoiced(self, cursor, user, ids, name, arg, context=None):
        res = {}
        for po in self.browse(cursor, user, ids, context=context):
            res[po.id] = True
            invoice_existence = False
            for invoice in po.invoice_ids:
                if invoice.state!='cancel':
                    invoice_existence = True
                    if invoice.state != 'paid':
                        res[sale.id] = False
                        break
            if not invoice_existence or po.state == 'manual':
                res[sale.id] = False
        return res

    def _invoiced_search(self, cursor, user, obj, name, args, context=None):
        if not len(args):
            return []
        clause = ''
        po_clause = ''
        no_invoiced = False
        for arg in args:
            if (arg[1] == '=' and arg[2]) or (arg[1] == '!=' and not arg[2]):
                clause += 'AND inv.state = \'paid\''
            else:
                clause += 'AND inv.state != \'cancel\' AND po.state != \'cancel\'  AND inv.state <> \'paid\'  AND rel.order_id = po.id '
                po_clause = ',  pos_order AS po '
                no_invoiced = True

        cursor.execute('SELECT rel.order_id ' \
                'FROM pos_order_invoice_rel AS rel, account_invoice AS inv '+ po_clause + \
                'WHERE rel.invoice_id = inv.id ' + clause)
        res = cursor.fetchall()
        if no_invoiced:
            cursor.execute('SELECT po.id ' \
                    'FROM pos_order AS po ' \
                    'WHERE po.id NOT IN ' \
                        '(SELECT rel.order_id ' \
                        'FROM pos_order_invoice_rel AS rel) and po.state != \'cancel\'')
            res.extend(cursor.fetchall())
        # check in virtual orders
        #cursor.execute('SELECT sol.order_id ' \
        #               'FROM pos_order_virtual AS vir, pos_order_line AS pol ' \
        #               'WHERE pol.id IN vir.order_line_ids AND vir.order_ids IN %s', (tuple([x[0] for x in res]),))
        #res_vir = cursor.fetchall()
        #if res_vir:
        #    res = res_vir
        if not res:
            return [('id', '=', 0)]
        _logger.debug("Based All orders with invoce relations %s" % res)
        return [('id', 'in', [x[0] for x in res])]

    _columns = {
        'name': fields.char('Order Ref', required=True, readonly=True, copy=False),
        'ean_uid': fields.char('EAN Number Ref', size=13, required=True, readonly=True, copy=False),
        'company_id':fields.many2one('res.company', 'Company', required=True, readonly=True),
        'date_order': fields.datetime('Order Date', readonly=True, select=True),
        'user_id': fields.many2one('res.users', 'Salesman', help="Person who uses the the cash register. It can be a reliever, a student or an interim employee."),
        'amount_tax': fields.function(_amount_all, string='Taxes', digits_compute=dp.get_precision('Account'), multi='all'),
        'amount_total': fields.function(_amount_all, string='Total', digits_compute=dp.get_precision('Account'),  multi='all'),
        'amount_paid': fields.function(_amount_all, string='Paid', states={'draft': [('readonly', False)], 'progress': [('readonly', False)]}, readonly=True, digits_compute=dp.get_precision('Account'), multi='all'),
        'amount_return': fields.function(_amount_all, string='Returned', states={'draft': [('readonly', False)]}, readonly=True, digits_compute=dp.get_precision('Account'), multi='all'),
        'amount_rest': fields.function(_amount_all, string='Rest from Partially Paid/Refund', states={'draft': [('readonly', False)], 'progress': [('readonly', False)]}, readonly=True, digits_compute=dp.get_precision('Account'), multi='all'),
        'is_partial_paid': fields.function(_amount_partial_paid, string='Is Partially Paid', type='boolean', store=True),
        'taxes': fields.one2many('pos.order.tax', 'pos_order', 'Taxes Lines', states={'draft': [('readonly', False)]}, readonly=True, copy=True),
        'fiscal_position': fields.many2one('account.fiscal.position', 'Fiscal Position'),
        'lines': fields.one2many('pos.order.line', 'order_id', 'Order Lines', states={'draft': [('readonly', False)]}, readonly=True, copy=True),
        'statement_ids': fields.one2many('account.bank.statement.line', 'pos_statement_id', 'Payments', states={'draft': [('readonly', False)], 'progress': [('readonly', False)]}, readonly=True),
        'pricelist_id': fields.many2one('product.pricelist', 'Pricelist', required=True, states={'draft': [('readonly', False)]}, readonly=True),
        'partner_id': fields.many2one('res.partner', 'Customer', change_default=True, select=1, states={'draft': [('readonly', False)], 'progress': [('readonly', False)], 'paid': [('readonly', False)]}),
        'sequence_number': fields.integer('Sequence Number', help='A session-unique sequence number for the order'),

        'session_id' : fields.many2one('pos.session', 'Session',
                                        #required=True,
                                        select=1,
                                        domain="[('state', '=', 'opened')]",
                                        states={'draft' : [('readonly', False)]},
                                        readonly=True),

        'state': fields.selection([('draft', 'New'),
                                   ('cancel', 'Cancelled'),
                                   ('progress', 'PO in progress'),
                                   ('paid', 'Paid'),
                                   ('done', 'Posted'),
                                   ('invoiced', 'Invoiced')],
                                  'Status', readonly=True, copy=False),

        #'invoice_id': fields.many2one('account.invoice', 'Invoice', copy=False, help="Compatible with unfixed pos"),
        'invoice_ids': fields.many2many('account.invoice', 'pos_order_invoice_rel', 'order_id', 'invoice_id', 'Invoices', readonly=True, copy=False, help="This is the list of invoices that have been generated for this pos sales order. The same sales order may have been invoiced in several times (by line for example)."),
        'invoice_exists': fields.function(_invoice_exists, string='Invoiced', fnct_search=_invoiced_search, type='boolean', help="It indicates that sales order has at least one invoice."),
        'account_move': fields.many2one('account.move', 'Journal Entry', readonly=True, copy=False),
        'picking_id': fields.many2one('stock.picking', 'Picking', readonly=True, copy=False),
        'picking_ids': fields.many2many('stock.picking', 'pos_order_picking_rel', 'order_id', 'picking_id', 'Pickings', readonly=True, copy=False, help="This is list of picking movies that been generated for this pos sales order."),
        'picking_type_id': fields.related('session_id', 'config_id', 'picking_type_id', string="Picking Type", type='many2one', relation='stock.picking.type'),
        'location_id': fields.related('session_id', 'config_id', 'stock_location_id', string="Location", type='many2one', store=True, relation='stock.location'),
        'note': fields.text('Internal Notes'),
        'nb_print': fields.integer('Number of Print', readonly=True, copy=False),
        'pos_reference': fields.char('Receipt Ref', readonly=True, copy=False),
        'sale_journal': fields.related('session_id', 'config_id', 'journal_id', relation='account.journal', type='many2one', string='Sale Journal', store=True, readonly=True),
    }

    def _default_session(self, cr, uid, context=None):
        so = self.pool.get('pos.session')
        session_ids = so.search(cr, uid, [('state','=', 'opened'), ('user_id','=',uid)], context=context)
        return session_ids and session_ids[0] or False

    def _default_pricelist(self, cr, uid, context=None):
        session_ids = self._default_session(cr, uid, context)
        if session_ids:
            session_record = self.pool.get('pos.session').browse(cr, uid, session_ids, context=context)
            return session_record.config_id.pricelist_id and session_record.config_id.pricelist_id.id or False
        return False

    def _get_out_picking_type(self, cr, uid, context=None):
        return self.pool.get('ir.model.data').xmlid_to_res_id(
                    cr, uid, 'point_of_sale.picking_type_posout', context=context)

    _defaults = {
        'user_id': lambda self, cr, uid, context: uid,
        'state': 'draft',
        'name': '/',
        'date_order': lambda *a: time.strftime('%Y-%m-%d %H:%M:%S'),
        'nb_print': 0,
        'sequence_number': 1,
        'session_id': _default_session,
        'company_id': lambda self,cr,uid,c: self.pool.get('res.users').browse(cr, uid, uid, c).company_id.id,
        'pricelist_id': _default_pricelist,
    }

    def create(self, cr, uid, values, context=None):
        if values.get('session_id'):
            # set name based on the sequence specified on the config
            session = self.pool['pos.session'].browse(cr, uid, values['session_id'], context=context)
            values['name'] = session.config_id.sequence_id._next()
        else:
            # fallback on any pos.order sequence
            values['name'] = self.pool.get('ir.sequence').get_id(cr, uid, 'pos.order', 'code', context=context)
        return super(pos_order, self).create(cr, uid, values, context=context)

    def test_paid(self, cr, uid, ids, context=None):
        """A Point of Sale is paid when the sum
        @return: True
        """
        for order in self.browse(cr, uid, ids, context=context):
            if order.lines and not order.amount_total:
                return True
            if (not order.lines) or (not order.statement_ids) or \
                (abs(order.amount_total-order.amount_paid) > 0.00001):
                return False
        return True

    def create_picking(self, cr, uid, ids, context=None):
        """Create a picking for each order and validate it."""
        picking_obj = self.pool.get('stock.picking')
        partner_obj = self.pool.get('res.partner')
        move_obj = self.pool.get('stock.move')

        for order in self.browse(cr, uid, ids, context=context):
            if all(t == 'service' for t in order.lines.mapped('product_id.type')):
                continue
            addr = order.partner_id and partner_obj.address_get(cr, uid, [order.partner_id.id], ['delivery']) or {}
            picking_type = order.picking_type_id
            picking_id = False
            if picking_type:
                picking_id = picking_obj.create(cr, uid, {
                    'origin': order.name,
                    'partner_id': addr.get('delivery',False),
                    'date_done' : order.date_order,
                    'picking_type_id': picking_type.id,
                    'company_id': order.company_id.id,
                    'move_type': 'direct',
                    'note': order.note or "",
                    'invoice_state': 'none',
                }, context=context)
                self.write(cr, uid, [order.id], {'picking_id': picking_id}, context=context)
                cr.execute('insert into pos_order_picking_rel (order_id,picking_id) values (%s,%s)', (order.id, picking_id))
                self.invalidate_cache(cr, uid, ['picking_ids'], [order.id], context=context)

            location_id = order.location_id.id
            if order.partner_id:
                destination_id = order.partner_id.property_stock_customer.id
            elif picking_type:
                if not picking_type.default_location_dest_id:
                    raise osv.except_osv(_('Error!'), _('Missing source or destination location for picking type %s. Please configure those fields and try again.' % (picking_type.name,)))
                destination_id = picking_type.default_location_dest_id.id
            else:
                destination_id = partner_obj.default_get(cr, uid, ['property_stock_customer'], context=context)['property_stock_customer']

            move_list = []
            for line in order.lines:
                if line.product_id and line.product_id.type == 'service' and line.product_id.type == 'money':
                    continue

                move_list.append(move_obj.create(cr, uid, {
                    'name': line.name,
                    'product_uom': line.product_id.uom_id.id,
                    'product_uos': line.product_id.uom_id.id,
                    'picking_id': picking_id,
                    'picking_type_id': picking_type.id,
                    'product_id': line.product_id.id,
                    'product_uos_qty': abs(line.qty),
                    'product_uom_qty': abs(line.qty),
                    'state': 'draft',
                    'location_id': location_id if line.qty >= 0 else destination_id,
                    'location_dest_id': destination_id if line.qty >= 0 else location_id,
                }, context=context))

            if picking_id:
                picking_obj.action_confirm(cr, uid, [picking_id], context=context)
                picking_obj.force_assign(cr, uid, [picking_id], context=context)
                picking_obj.action_done(cr, uid, [picking_id], context=context)
            elif move_list:
                move_obj.action_confirm(cr, uid, move_list, context=context)
                move_obj.force_assign(cr, uid, move_list, context=context)
                move_obj.action_done(cr, uid, move_list, context=context)
        return True

    def cancel_order(self, cr, uid, ids, context=None):
        """ Changes order state to cancel
        @return: True
        """
        stock_picking_obj = self.pool.get('stock.picking')
        for order in self.browse(cr, uid, ids, context=context):
            stock_picking_obj.action_cancel(cr, uid, [order.picking_id.id])
            if stock_picking_obj.browse(cr, uid, order.picking_id.id, context=context).state <> 'cancel':
                raise osv.except_osv(_('Error!'), _('Unable to cancel the picking.'))
        self.write(cr, uid, ids, {'state': 'cancel'}, context=context)
        return True

    def search_read_orders(self, cr, uid, query, limit=10, offset=0, context=None):
        _logger.debug("query %s" % query)
        if not query:
            condition = [
                ('state', '=', 'draft'),
                ('statement_ids', '=', False)
            ]
        else:
            condition = [
                '|', '|',
                ('ean_uid', 'ilike', query),
                ('name', 'ilike', query),
                ('partner_id', 'ilike', query)
            ]
            offset = 0
        fields = ['name', 'partner_id', 'amount_total']
        return self.search_read(cr, uid, condition, fields, context=context, limit=limit, offset=offset)

    def load_order(self, cr, uid, order_id, context=None):
        orderlines = []
        ol_obj = self.pool.get('pos.order.line')
        order = self.browse(cr, uid, order_id, context=context)
        _logger.debug("Load order from frontend %s:%s:%s:%s" % (order_id, order, order.lines, order.invoice_ids))
        invoices = self.pool.get('account.invoice').browse(cr, uid, [i.id for i in order.invoice_ids], context=context)
        # read lines in original order
        order_lines_ids = [l.id for l in order.lines]
        for l in ol_obj.browse(cr, uid, order_lines_ids, context=context):
            orderlines.append(dict(
                                    id=l.id,
                                    order_id=order.id,
                                    product_id=(l.product_id.id, "[%s] %s" % (l.product_id.id, l.product_id.name)),
                                    type=l.product_id.product_tmpl_id.type,
                                    price_unit=l.price_unit,
                                    qty=l.qty,
                                    discount=l.discount,
                                ))
        # check advance payments and read lines
        for invoice in invoices:
            inv_lines_ids = [l.id for l in invoice.invoice_line]
            for l in self.pool.get('account.invoice.line').browse(cr, uid, inv_lines_ids, context=context):
                if l.product_id.product_tmpl_id.type == 'money':
                    orderlines.append(dict(
                                        id=False,
                                        order_id=order.id,
                                        product_id=(l.product_id.id, "%s [%s]" % (l.product_id.name,_('invoice')+': '+invoice.internal_number)),
                                        type=l.product_id.product_tmpl_id.type,
                                        price_unit=l.price_unit,
                                        qty=l.quantity,
                                        discount=l.discount,
                                    ))
        # check refunds and read lines
        refund_ids = self.search(cr, uid, [('pos_reference','=',order.pos_reference + ' REFUND')], context=context)
        for order_refund in self.browse(cr, uid, refund_ids, context=context):
            for l in ol_obj.browse(cr, uid, order_refund.id, context=context):
                orderlines.append(dict(
                                        id=l.id,
                                        order_id=order.id,
                                        product_id=(l.product_id.id, "(%s)-[%s] %s" % (order_refund.pos_reference,l.product_id.id, l.product_id.name)),
                                        type=l.product_id.product_tmpl_id.type,
                                        price_unit=l.price_unit,
                                        qty=l.qty,
                                        discount=l.discount,
                                    ))

        _logger.debug("lines browse %s" % orderlines)
        return {
            'id': order.id,
            'name': order.pos_reference,
            'partner_id': order.partner_id.id,
            'orderlines': orderlines,
        }

    def add_payment(self, cr, uid, order_id, data, context=None):
        """Create a new payment for the order"""
        context = dict(context or {})
        statement_line_obj = self.pool.get('account.bank.statement.line')
        property_obj = self.pool.get('ir.property')
        order = self.browse(cr, uid, order_id, context=context)
        date = data.get('payment_date', time.strftime('%Y-%m-%d'))
        if len(date) > 10:
            timestamp = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            ts = fields.datetime.context_timestamp(cr, uid, timestamp, context)
            date = ts.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        args = {
            'amount': data['amount'],
            'date': date,
            'name': order.name + ': ' + (data.get('payment_name', '') or ''),
            'partner_id': order.partner_id and self.pool.get("res.partner")._find_accounting_partner(order.partner_id).id or False,
        }

        journal_id = data.get('journal', False)
        statement_id = data.get('statement_id', False)
        assert journal_id or statement_id, "No statement_id or journal_id passed to the method!"

        journal = self.pool['account.journal'].browse(cr, uid, journal_id, context=context)
        # use the company of the journal and not of the current user
        company_cxt = dict(context, force_company=journal.company_id.id)
        account_def = property_obj.get(cr, uid, 'property_account_receivable', 'res.partner', context=company_cxt)
        args['account_id'] = (order.partner_id and order.partner_id.property_account_receivable \
                             and order.partner_id.property_account_receivable.id) or (account_def and account_def.id) or False

        if not args['account_id']:
            if not args['partner_id']:
                msg = _('There is no receivable account defined to make payment.')
            else:
                msg = _('There is no receivable account defined to make payment for the partner: "%s" (id:%d).') % (order.partner_id.name, order.partner_id.id,)
            raise osv.except_osv(_('Configuration Error!'), msg)

        context.pop('pos_session_id', False)

        for statement in order.session_id.statement_ids:
            if statement.id == statement_id:
                journal_id = statement.journal_id.id
                break
            elif statement.journal_id.id == journal_id:
                statement_id = statement.id
                break

        if not statement_id:
            raise osv.except_osv(_('Error!'), _('You have to open at least one cashbox.'))

        args.update({
            'statement_id': statement_id,
            'pos_statement_id': order_id,
            'journal_id': journal_id,
            'ref': order.session_id.name,
        })

        statement_line_obj.create(cr, uid, args, context=context)

        return statement_id

    def refund(self, cr, uid, ids, context=None):
        """Create a copy of order  for refund order"""
        clone_list = []
        line_obj = self.pool.get('pos.order.line')

        for order in self.browse(cr, uid, ids, context=context):
            current_session_ids = self.pool.get('pos.session').search(cr, uid, [
                ('state', '!=', 'closed'),
                ('user_id', '=', uid)], context=context)
            if not current_session_ids:
                raise osv.except_osv(_('Error!'), _('To return product(s), you need to open a session that will be used to register the refund.'))

            clone_id = self.copy(cr, uid, order.id, {
                'name': order.name + ' REFUND', # not used, name forced by create
                'session_id': current_session_ids[0],
                'date_order': time.strftime('%Y-%m-%d %H:%M:%S'),
            }, context=context)
            clone_list.append(clone_id)

        for clone in self.browse(cr, uid, clone_list, context=context):
            for order_line in clone.lines:
                line_obj.write(cr, uid, [order_line.id], {
                    'qty': -order_line.qty
                }, context=context)

        abs = {
            'name': _('Return Products'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'pos.order',
            'res_id':clone_list[0],
            'view_id': False,
            'context':context,
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
        }
        return abs

    def action_invoice_state(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state':'invoiced'}, context=context)

    def manual_invoice(self, cr, uid, ids, context=None):
        """ create invoices for the given sales orders (ids), and open the form
            view of one of the newly created invoices
        """
        mod_obj = self.pool.get('ir.model.data')

        # create invoices through the pos orders' workflow
        inv_ids0 = set(inv.id for pos in self.browse(cr, uid, ids, context) for inv in pos.invoice_ids)
        self.signal_workflow(cr, uid, ids, 'manual_invoice')
        inv_ids1 = set(inv.id for pos in self.browse(cr, uid, ids, context) for inv in pos.invoice_ids)
        # determine newly created invoices
        new_inv_ids = list(inv_ids1 - inv_ids0)

        res = mod_obj.get_object_reference(cr, uid, 'account', 'invoice_form')
        res_id = res and res[1] or False,

        return {
            'name': _('Customer Invoices'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': [res_id],
            'res_model': 'account.invoice',
            'context': "{'type':'out_invoice'}",
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'res_id': new_inv_ids and new_inv_ids[0] or False,
        }

    def _make_invoice(self, cr, uid, inv, lines, context=None):
        inv_ref = self.pool.get('account.invoice')
        inv_line_ref = self.pool.get('account.invoice.line')
        inv_id = inv_ref.create(cr, uid, inv, context=context)
        for inv_line in lines:
            inv_line['invoice_id'] = inv_id
            _logger.debug("Invoice line before %s" % inv_line)
            #inv_line.update(inv_line_ref.product_id_change(cr, uid, [],
            #                                            inv['pricelist_id'],
            #                                            inv_line['product_id'],
            #                                            inv_line['product_uom'],
            #                                            inv['date_invoice'],
            #                                            inv_line['quantity'],
            #                                            partner_id = inv['partner_id'],
            #                                            fposition_id = inv['fiscal_position'],
            #                                            price_unit = inv_line['price_unit'])['value'])
            #_logger.debug("Invoice line after %s" % inv_line)
            inv_line_ref.create(cr, uid, inv_line, context=context)
        inv_ref.button_reset_taxes(cr, uid, [inv_id], context=context)
        inv_ref.signal_workflow(cr, uid, [inv_id], 'validate')
        inv_ref.signal_workflow(cr, uid, [inv_id], 'invoice_open')
        return inv_id

    def action_invoice(self, cr, uid, ids, context=None):
        inv_ids = []
        lines = []
        product_obj = self.pool.get('product.product')

        for order in self.pool.get('pos.order').browse(cr, uid, ids, context=context):
            # fix for multi invoice mode
            ##if order.invoice_id:
            ##    inv_ids.append(order.invoice_id.id)
            ##    continue

            if not order.partner_id:
                raise osv.except_osv(_('Error!'), _('Please provide a partner for the sale.'))

            acc = order.partner_id.property_account_receivable.id
            inv = {
                'name': order.name,
                'origin': order.name,
                'date_invoice': order.date_order,
                'account_id': acc,
                'journal_id': order.sale_journal.id or None,
                'type': 'out_invoice',
                'reference': order.name,
                'partner_id': order.partner_id.id,
                'pricelist_id': order.pricelist_id.id,
                'fiscal_position': order.fiscal_position.id,
                'comment': order.note or '',
                'currency_id': order.pricelist_id.currency_id.id, # considering partner's sale pricelist's currency
            }
            # fix dnot need all come from fronted
            ## inv.update(inv_ref.onchange_partner_id(cr, uid, [], 'out_invoice', order.partner_id.id)['value'])
            # FORWARDPORT TO SAAS-6 ONLY!
            ## inv.update({'fiscal_position': False})
            if not inv.get('account_id', None):
                inv['account_id'] = acc

            # firest get old invoices
            for inv_id in order.invoice_ids:
                for il in inv_ref.browse(cr, uid, inv_id, context=context):
                    inv_line = {
                        'product_id': il.product_id.id,
                        'quantity': -il.qty,
                        'account_analytic_id': il.account_analytic_id,
                        'price_unit': il.price_unit,
                        'discount': il.discount,
                        'name': il.name,
                        'invoice_line_tax_id': il.invoice_line_tax_id,
                    }
                    lines.append(inv_line)
            for line in order.lines:
                inv_line = {
                    'product_id': line.product_id.id,
                    'quantity': line.qty,
                    'product_uom': line.product_id.uom_id.id,
                }
                inv_name = product_obj.name_get(cr, uid, [line.product_id.id], context=context)[0][1]
                if not inv_line.get('account_analytic_id', False):
                    inv_line['account_analytic_id'] = \
                        self._prepare_analytic_account(cr, uid, line,
                                                       context=context)
                inv_line['price_unit'] = line.price_unit
                inv_line['discount'] = line.discount
                inv_line['name'] = inv_name
                inv_line['invoice_line_tax_id'] = line.tax_ids
                #inv_line['invoice_line_tax_id'] = [(6, 0, inv_line['invoice_line_tax_id'])]
                lines.append(inv_line)

            inv_id = self._make_invoice(cr, uid, inv, lines, context=context)
            inv_ids.append(inv_id)
            # old versin
            ##self.write(cr, uid, [order.id], {'invoice_id': inv_id, 'state': 'invoiced'}, context=context)
            # multi invoice version
            cr.execute('insert into pos_order_invoice_rel (order_id,invoice_id) values (%s,%s)', (order.id, inv_id))
            self.invalidate_cache(cr, uid, ['invoice_ids'], [order.id], context=context)
            #self.signal_workflow(cr, uid, [order.id], 'invoice')
        if not inv_ids: return {}
        return self._view_invoice(cr, uid, inv_ids, context=context)

        #mod_obj = self.pool.get('ir.model.data')
        #res = mod_obj.get_object_reference(cr, uid, 'account', 'invoice_form')
        #res_id = res and res[1] or False
        #return {
        #    'name': _('Customer Invoice'),
        #    'view_type': 'form',
        #    'view_mode': 'form',
        #    'view_id': [res_id],
        #    'res_model': 'account.invoice',
        #    'context': "{'type':'out_invoice'}",
        #    'type': 'ir.actions.act_window',
        #    'nodestroy': True,
        #    'target': 'current',
        #    'res_id': inv_ids and inv_ids[0] or False,
        #}

    def _view_invoice(self, cr, uid, inv_ids, context=None):
        '''
        This function returns an action that display existing invoices of given pos order ids. It can either be a in a list or in a form view, if there is only one invoice to show.
        '''
        mod_obj = self.pool.get('ir.model.data')
        act_obj = self.pool.get('ir.actions.act_window')
        res_domain = {}

        #compute the number of invoices to display
        #choose the view_mode accordingly
        res = mod_obj.get_object_reference(cr, uid, 'account', 'action_invoice_tree1')
        id = res and res[1] or False
        result = act_obj.read(cr, uid, [id], context=context)[0]

        if len(inv_ids)>1:
            result['domain'] = "[('id','in',["+','.join(map(str, inv_ids))+"])]"
        else:
            res = mod_obj.get_object_reference(cr, uid, 'account', 'invoice_form')
            result['views'] = [(res and res[1] or False, 'form')]
            result['res_id'] = inv_ids and inv_ids[0] or False
        _logger.info("View invoce %s" % result['domain'])
        return result

    def action_view_invoice(self, cr, uid, ids, context=None):
        _logger.debug("Action invoice %s" % ids)
        inv_ids = []
        for po in self.browse(cr, uid, ids, context=context):
            inv_ids += [invoice.id for invoice in po.invoice_ids]
            _logger.debug("Action invoice %s:%s" % (ids, inv_ids))
        return self._view_invoice(cr, uid, inv_ids, context=context)

    #def _amount_line_tax(self, cr, uid, line, context=None):
    #    price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
    #    taxes = line.tax_ids.compute_all(cr, uid, price, line.qty, product=line.product_id, partner=line.order_id.partner_id)['taxes']
    #    val = 0.0
    #    for c in taxes:
    #        val += c.get('amount', 0.0)
    #    return val

    def _tax_list_get(self, cr, uid, order_ids, context=None):
        agg_taxes = {}
        tax_lines = []
        for order in self.browse(cr, uid, order_ids, context=context):
            for line in order.lines:
                tax_lines.append({
                    'base': line.price_subtotal,
                    'taxes': line._compute_taxes()['taxes']
                })

        for tax_line in tax_lines:
            base = tax_line['base']
            for tax in tax_line['taxes']:
                tax_id = str(tax['id'])
                if tax_id in agg_taxes:
                    agg_taxes[tax_id]['base'] += base
                    agg_taxes[tax_id]['amount'] += tax['amount']
                else:
                    agg_taxes[tax_id] = {
                        'tax_id': tax_id,
                        'name': tax['name'],
                        'base': base,
                        'amount': tax['amount'],
                    }
        return agg_taxes

    def compute_tax_detail(self, cr, uid, order_ids, context=None):
        taxes_to_delete = False
        for order in self.browse(cr, uid, order_ids, context=context):
            taxes_to_delete = self.pool.get('pos.order.tax').search(cr, uid, [('pos_order', '=', order.id)], context=context)
            # Update order taxes list
            for key, tax in order._tax_list_get().iteritems():
                current = taxes_to_delete.filtered(lambda r: r.tax.id == tax['tax_id'])
                if current:
                    current.write({
                        'base': tax['base'],
                        'amount': tax['amount'],
                    })
                    taxes_to_delete -= current
                else:
                    self.pool.get('pos.order.tax').create(cr, uid,
                                                    {'pos_order': order.id,
                                                    'tax': tax['tax_id'],
                                                    'name': tax['name'],
                                                    'base': tax['base'],
                                                    'amount': tax['amount'],},
                                                    context=context)
        if taxes_to_delete:
            taxes_to_delete.unlink()

    def _install_tax_detail(self, cr, uid, context=None):
        """Create tax details to pos.order's already paid, done or invoiced.
        """
        # Find orders with state : paid, done or invoiced
        orders = self.search(cr, uid, [('state', 'in', ('paid', 'done', 'invoiced')),('taxes', '=', False)], context=context)
        # Compute tax detail
        orders.compute_tax_detail(cr, uid, orders, context=context)
        _logger.info("%d orders computed installing module.", len(orders))

    def create_account_move(self, cr, uid, ids, context=None):
        return self._create_account_move_line(cr, uid, ids, None, None, context=context)

    def _prepare_analytic_account(self, cr, uid, line, context=None):
        '''This method is designed to be inherited in a custom module'''
        return False

    def _create_account_move(self, cr, uid, dt, ref, journal_id, company_id, context=None):
        local_context = dict(context or {}, company_id=company_id)
        start_at_datetime = datetime.strptime(dt, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        date_tz_user = fields.datetime.context_timestamp(cr, uid, start_at_datetime, context=context)
        date_tz_user = date_tz_user.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        period_id = self.pool['account.period'].find(cr, uid, dt=date_tz_user, context=local_context)
        return self.pool['account.move'].create(cr, uid, {'ref': ref, 'journal_id': journal_id, 'period_id': period_id[0]}, context=context)

    def _create_account_move_line(self, cr, uid, ids, session=None, move_id=None, context=None):
        # Tricky, via the workflow, we only have one id in the ids variable
        """Create a account move line of order grouped by products or not."""
        account_move_obj = self.pool.get('account.move')
        account_period_obj = self.pool.get('account.period')
        account_tax_obj = self.pool.get('account.tax')
        property_obj = self.pool.get('ir.property')
        cur_obj = self.pool.get('res.currency')
        tax_line = self.pool.get('pos.order.tax')

        # first remove all records in order.tax.line
        tax_line.unlink(cr, uid, ids, context=context)

        #session_ids = set(order.session_id for order in self.browse(cr, uid, ids, context=context))

        if session and not all(session.id == order.session_id.id for order in self.browse(cr, uid, ids, context=context)):
            raise osv.except_osv(_('Error!'), _('Selected orders do not have the same session!'))

        grouped_data = {}
        have_to_group_by = session and session.config_id.group_by or False

        def compute_tax(amount, tax, line):
            if amount > 0:
                tax_code_id = tax['base_code_id']
                tax_amount = line.price_subtotal * tax['base_sign']
            else:
                tax_code_id = tax['ref_base_code_id']
                tax_amount = abs(line.price_subtotal) * tax['ref_base_sign']

            return (tax_code_id, tax_amount,)

        for order in self.browse(cr, uid, ids, context=context):
            if order.account_move:
                continue
            if order.state != 'paid':
                continue
            current_company = order.sale_journal.company_id

            group_tax = {}
            account_def = property_obj.get(cr, uid, 'property_account_receivable', 'res.partner', context=context)

            order_account = order.partner_id and \
                            order.partner_id.property_account_receivable and \
                            order.partner_id.property_account_receivable.id or \
                            account_def and account_def.id

            if move_id is None:
                # Create an entry for the sale
                move_id = self._create_account_move(cr, uid, order.session_id.start_at, order.name, order.sale_journal.id, order.company_id.id, context=context)

            move = account_move_obj.browse(cr, uid, move_id, context=context)

            def insert_data(data_type, values):
                # if have_to_group_by:

                sale_journal_id = order.sale_journal.id

                # 'quantity': line.qty,
                # 'product_id': line.product_id.id,
                values.update({
                    'date': order.date_order[:10],
                    'ref': order.name,
                    'partner_id': order.partner_id and self.pool.get("res.partner")._find_accounting_partner(order.partner_id).id or False,
                    'journal_id' : sale_journal_id,
                    'period_id': move.period_id.id,
                    'move_id' : move_id,
                    'company_id': current_company.id,
                })

                if data_type == 'product':
                    key = ('product', values['partner_id'], values['product_id'], values['analytic_account_id'], values['debit'] > 0)
                elif data_type == 'tax':
                    key = ('tax', values['partner_id'], values['tax_code_id'], values['debit'] > 0)
                elif data_type == 'counter_part':
                    key = ('counter_part', values['partner_id'], values['account_id'], values['debit'] > 0)
                else:
                    return

                grouped_data.setdefault(key, [])

                # if not have_to_group_by or (not grouped_data[key]):
                #     grouped_data[key].append(values)
                # else:
                #     pass

                if have_to_group_by:
                    if not grouped_data[key]:
                        grouped_data[key].append(values)
                    else:
                        for line in grouped_data[key]:
                            if line.get('tax_code_id') == values.get('tax_code_id'):
                                current_value = line
                                current_value['quantity'] = current_value.get('quantity', 0.0) +  values.get('quantity', 0.0)
                                current_value['credit'] = current_value.get('credit', 0.0) + values.get('credit', 0.0)
                                current_value['debit'] = current_value.get('debit', 0.0) + values.get('debit', 0.0)
                                current_value['tax_amount'] = current_value.get('tax_amount', 0.0) + values.get('tax_amount', 0.0)
                                current_value['amount_currency'] = current_value.get('amount_currency', 0.0) + values.get('amount_currency', 0.0)
                                break
                        else:
                            grouped_data[key].append(values)
                else:
                    grouped_data[key].append(values)

            #because of the weird way the pos order is written, we need to make sure there is at least one line,
            #because just after the 'for' loop there are references to 'line' and 'income_account' variables (that
            #are set inside the for loop)
            #TOFIX: a deep refactoring of this method (and class!) is needed in order to get rid of this stupid hack
            assert order.lines, _('The POS order must have lines when calling this method')
            # Create an move for each order line

            cur = order.pricelist_id.currency_id
            round_per_line = True
            if order.company_id.tax_calculation_rounding_method == 'round_globally':
                round_per_line = False
            for line in order.lines:
                tax_amount = 0
                taxes = []
                # [pos_pricelist] Only change in the next line:
                # for t in line.product_id.taxes_id:
                for t in line.tax_ids if 'tax_ids' in line._fields else line.product_id.taxes_id:
                    if t.company_id.id == current_company.id:
                        taxes.append(t)
                computed_taxes = account_tax_obj.compute_all(cr, uid, taxes, line.price_unit * (100.0-line.discount) / 100.0, line.qty)['taxes']

                for tax in computed_taxes:
                    tax_amount += cur_obj.round(cr, uid, cur, tax['amount']) if round_per_line else tax['amount']
                    if tax_amount < 0:
                        group_key = (tax['ref_tax_code_id'], tax['base_code_id'], tax['account_collected_id'], tax['id'])
                    else:
                        group_key = (tax['tax_code_id'], tax['base_code_id'], tax['account_collected_id'], tax['id'])

                    group_tax.setdefault(group_key, 0)
                    group_tax[group_key] += cur_obj.round(cr, uid, cur, tax['amount']) if round_per_line else tax['amount']

                amount = line.price_subtotal

                # Search for the income account
                if  line.product_id.property_account_income.id:
                    income_account = line.product_id.property_account_income.id
                elif line.product_id.categ_id.property_account_income_categ.id:
                    income_account = line.product_id.categ_id.property_account_income_categ.id
                else:
                    raise osv.except_osv(_('Error!'), _('Please define income '\
                        'account for this product: "%s" (id:%d).') \
                        % (line.product_id.name, line.product_id.id, ))

                # Empty the tax list as long as there is no tax code:
                tax_code_id = False
                tax_amount = 0
                while computed_taxes:
                    tax = computed_taxes.pop(0)
                    tax_code_id, tax_amount = compute_tax(amount, tax, line)

                    # If there is one we stop
                    if tax_code_id:
                        break

                # Create a move for the line
                insert_data('product', {
                    'name': line.product_id.name,
                    'quantity': line.qty,
                    'amount_currency': amount,
                    'product_id': line.product_id.id,
                    'account_id': income_account,
                    'analytic_account_id': self._prepare_analytic_account(cr, uid, line, context=context),
                    'credit': ((amount>0) and amount) or 0.0,
                    'debit': ((amount<0) and -amount) or 0.0,
                    'tax_code_id': tax_code_id,
                    'tax_amount': tax_amount,
                    'partner_id': order.partner_id and self.pool.get("res.partner")._find_accounting_partner(order.partner_id).id or False
                })

                # For each remaining tax with a code, whe create a move line
                for tax in computed_taxes:
                    tax_code_id, tax_amount = compute_tax(amount, tax, line)
                    if not tax_code_id:
                        continue

                    insert_data('tax', {
                        'name': _('Tax'),
                        'product_id':line.product_id.id,
                        'quantity': line.qty,
                        'amount_currency': amount,
                        'account_id': income_account,
                        'credit': 0.0,
                        'debit': 0.0,
                        'tax_code_id': tax_code_id,
                        'tax_amount': tax_amount,
                        'partner_id': order.partner_id and self.pool.get("res.partner")._find_accounting_partner(order.partner_id).id or False
                    })

            # Create a move for each tax group
            (tax_code_pos, base_code_pos, account_pos, tax_id)= (0, 1, 2, 3)

            for key, tax_amount in group_tax.items():
                tax = self.pool.get('account.tax').browse(cr, uid, key[tax_id], context=context)
                insert_data('tax', {
                    'name': _('Tax') + ' ' + tax.name,
                    'quantity': line.qty,
                    'product_id': line.product_id.id,
                    'account_id': key[account_pos] or income_account,
                    'credit': ((tax_amount>0) and tax_amount) or 0.0,
                    'debit': ((tax_amount<0) and -tax_amount) or 0.0,
                    'tax_code_id': key[tax_code_pos],
                    'tax_amount': abs(tax_amount) * tax.tax_sign if tax_amount>=0 else abs(tax_amount) * tax.ref_tax_sign,
                    'partner_id': order.partner_id and self.pool.get("res.partner")._find_accounting_partner(order.partner_id).id or False
                })

            # counterpart
            insert_data('counter_part', {
                'name': _("Trade Receivables"), #order.name,
                'account_id': order_account,
                'credit': ((order.amount_total < 0) and -order.amount_total) or 0.0,
                'debit': ((order.amount_total > 0) and order.amount_total) or 0.0,
                'partner_id': order.partner_id and self.pool.get("res.partner")._find_accounting_partner(order.partner_id).id or False
            })

            order.write({'state':'done', 'account_move': move_id})
        # create tax lines data
        for group_key, group_data in grouped_data.iteritems():
            if group_key == 'tax':
                tax_line.create(cr, uid, {'pos_order': order.id, 'name': group_data['name'], 'tax': group_data['tax_code_id'], 'base': group_data['amount_currency'], 'amount': group_data['tax_amount']}, context=context)
        all_lines = []
        for group_key, group_data in grouped_data.iteritems():
            for value in group_data:
                all_lines.append((0, 0, value),)
        if move_id: #In case no order was changed
            self.pool.get("account.move").write(cr, uid, [move_id], {'line_id':all_lines}, context=context)

        return True

    def action_payment(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'state': 'payment'}, context=context)

    def action_progress(self, cr, uid, ids, context=None):
        _logger.info("Action progress %s" % ids)
        self.write(cr, uid, ids, {'state': 'progress'}, context=context)
        self.create_picking(cr, uid, ids, context=context)
        return True

    def action_paid(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state': 'paid'}, context=context)
        #self.create_picking(cr, uid, ids, context=context)
        return True

    def action_cancel(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state': 'cancel'}, context=context)
        return True

    def action_done(self, cr, uid, ids, context=None):
        self.create_account_move(cr, uid, ids, context=context)
        return True

class account_bank_statement(osv.osv):
    _inherit = 'account.bank.statement'
    _columns= {
        'user_id': fields.many2one('res.users', 'User', readonly=True),
    }
    _defaults = {
        'user_id': lambda self,cr,uid,c={}: uid
    }

class account_bank_statement_line(osv.osv):
    _inherit = 'account.bank.statement.line'
    _columns= {
        'pos_statement_id': fields.many2one('pos.order', ondelete='cascade'),
    }

class pos_order_line(osv.osv):
    _name = "pos.order.line"
    _description = "Lines of Point of Sale"
    _rec_name = "product_id"

    def _compute_taxes(self, cr, uid, ids, context=None):
        res = {
            'total': 0,
            'total_included': 0,
            'taxes': [],
        }
        account_tax_obj = self.pool.get('account.tax')
        cur_obj = self.pool.get('res.currency')
        for line in self.browse(cr, uid, ids, context=context):
            #taxes_ids = [ tax for tax in line.product_id.taxes_id if tax.company_id.id == line.order_id.company_id.id ]
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            #_logger.info('original point of sale: %s' % price)
            taxes = account_tax_obj.compute_all(cr, uid, line.tax_ids, price, line.qty, product=line.product_id, partner=line.order_id.partner_id or False)
            cur = line.order_id.pricelist_id.currency_id
            res['total'] += taxes['total']
            res['total_included'] += taxes['total_included']
            res['taxes'] += taxes['taxes']
        return res

    def _amount_line_all(self, cr, uid, ids, field_names, arg, context=None):
        res = dict([(i, {}) for i in ids])
        taxes = self._compute_taxes(cr, uid, ids, context=context)
        for line in self.browse(cr, uid, ids, context=context):
            res[line.id]['price_subtotal'] = taxes['total']
            res[line.id]['price_subtotal_incl'] = taxes['total_included']
        return res

    def onchange_product_id(self, cr, uid, ids, pricelist, product_id, qty=0, partner_id=False, context=None):
       context = context or {}
       if not product_id:
            return {}
       if not pricelist:
           raise osv.except_osv(_('No Pricelist!'),
               _('You have to select a pricelist in the sale form !\n' \
               'Please set one before choosing a product.'))

       price = self.pool.get('product.pricelist').price_get(cr, uid, [pricelist],
               product_id, qty or 1.0, partner_id)[pricelist]

       result = self.onchange_qty(cr, uid, ids, product_id, 0.0, qty, price, context=context)
       result['value']['price_unit'] = price
       return result

    def onchange_qty(self, cr, uid, ids, product, discount, qty, price_unit, context=None):
        result = {}
        if not product:
            return result
        account_tax_obj = self.pool.get('account.tax')
        cur_obj = self.pool.get('res.currency')

        prod = self.pool.get('product.product').browse(cr, uid, product, context=context)

        price = price_unit * (1 - (discount or 0.0) / 100.0)
        taxes = account_tax_obj.compute_all(cr, uid, prod.taxes_id, price, qty, product=prod, partner=False)

        result['price_subtotal'] = taxes['total']
        result['price_subtotal_incl'] = taxes['total_included']
        return {'value': result}

    _columns = {
        'company_id': fields.many2one('res.company', 'Company', required=True),
        'name': fields.char('Line No', required=True, copy=False),
        'notice': fields.char('Discount Notice'),
        'product_id': fields.many2one('product.product', 'Product', domain=[('sale_ok', '=', True)], required=True, change_default=True),
        'tax_ids': fields.many2many('account.tax', 'pline_tax_rel', 'pos_line_id', 'tax_id', 'Taxes', readonly=True, domain=[('type_tax_use', '=', 'sale')]),
        #'product_tmpl_id' : fields.related('product_id', 'product_tmpl_id', type='many2one', relation='product.template', string='Product Template'),
        #'type' : fields.related('product_tmpl_id', 'type', type='many2one', relation='product.template', string='Product Type'),
        'price_unit': fields.float(string='Unit Price', digits_compute=dp.get_precision('Product Price')),
        'qty': fields.float('Quantity', digits_compute=dp.get_precision('Product UoS')),
        'price_subtotal': fields.function(_amount_line_all, multi='pos_order_line_amount', digits_compute=dp.get_precision('Product Price'), string='Subtotal w/o Tax', store=True),
        'price_subtotal_incl': fields.function(_amount_line_all, multi='pos_order_line_amount', digits_compute=dp.get_precision('Account'), string='Subtotal', store=True),
        'discount': fields.float('Discount (%)', digits_compute=dp.get_precision('Account')),
        'order_id': fields.many2one('pos.order', 'Order Ref', ondelete='cascade'),
        'create_date': fields.datetime('Creation Date', readonly=True),
    }

    _defaults = {
        'name': lambda obj, cr, uid, context: obj.pool.get('ir.sequence').get(cr, uid, 'pos.order.line', context=context),
        'qty': lambda *a: 1,
        'discount': lambda *a: 0.0,
        'company_id': lambda self,cr,uid,c: self.pool.get('res.users').browse(cr, uid, uid, c).company_id.id,
    }

class ean_wizard(osv.osv_memory):
    _name = 'pos.ean_wizard'
    _columns = {
        'ean13_pattern': fields.char('Reference', size=13, required=True, translate=True),
    }
    def sanitize_ean13(self, cr, uid, ids, context):
        for r in self.browse(cr,uid,ids):
            ean13 = openerp.addons.product.product.sanitize_ean13(r.ean13_pattern)
            m = context.get('active_model')
            m_id =  context.get('active_id')
            self.pool[m].write(cr,uid,[m_id],{'ean13':ean13})
        return { 'type' : 'ir.actions.act_window_close' }

class PosOrderTax(osv.osv):
    _name = 'pos.order.tax'

    _columns = {
        'pos_order': fields.many2one('pos.order', 'POS Order', ondelete='cascade', index=True),
        'tax': fields.many2one('account.tax', 'Tax'),
        'name': fields.char('Tax Description', required=True),
        'base': fields.float('Base', digits=dp.get_precision('Account')),
        'amount': fields.float('Amount', digits=dp.get_precision('Account')),
    }

class pos_category(osv.osv):
    _name = "pos.category"
    _description = "Public Category"
    _order = "sequence, name"

    _constraints = [
        (osv.osv._check_recursion, 'Error ! You cannot create recursive categories.', ['parent_id'])
    ]

    def name_get(self, cr, uid, ids, context=None):
        res = []
        for cat in self.browse(cr, uid, ids, context=context):
            names = [cat.name]
            pcat = cat.parent_id
            while pcat:
                names.append(pcat.name)
                pcat = pcat.parent_id
            res.append((cat.id, ' / '.join(reversed(names))))
        return res

    def _name_get_fnc(self, cr, uid, ids, prop, unknow_none, context=None):
        res = self.name_get(cr, uid, ids, context=context)
        return dict(res)

    def _get_image(self, cr, uid, ids, name, args, context=None):
        result = dict.fromkeys(ids, False)
        for obj in self.browse(cr, uid, ids, context=context):
            result[obj.id] = tools.image_get_resized_images(obj.image)
        return result

    def _set_image(self, cr, uid, id, name, value, args, context=None):
        return self.write(cr, uid, [id], {'image': tools.image_resize_image_big(value)}, context=context)

    _columns = {
        'name': fields.char('Name', required=True, translate=True),
        'complete_name': fields.function(_name_get_fnc, type="char", string='Name'),
        'parent_id': fields.many2one('pos.category','Parent Category', select=True),
        'child_id': fields.one2many('pos.category', 'parent_id', string='Children Categories'),
        'sequence': fields.integer('Sequence', help="Gives the sequence order when displaying a list of product categories."),

        # NOTE: there is no 'default image', because by default we don't show thumbnails for categories. However if we have a thumbnail
        # for at least one category, then we display a default image on the other, so that the buttons have consistent styling.
        # In this case, the default image is set by the js code.
        # NOTE2: image: all image fields are base64 encoded and PIL-supported
        'image': fields.binary("Image",
            help="This field holds the image used as image for the cateogry, limited to 1024x1024px."),
        'image_medium': fields.function(_get_image, fnct_inv=_set_image,
            string="Medium-sized image", type="binary", multi="_get_image",
            store={
                'pos.category': (lambda self, cr, uid, ids, c={}: ids, ['image'], 10),
            },
            help="Medium-sized image of the category. It is automatically "\
                 "resized as a 128x128px image, with aspect ratio preserved. "\
                 "Use this field in form views or some kanban views."),
        'image_small': fields.function(_get_image, fnct_inv=_set_image,
            string="Smal-sized image", type="binary", multi="_get_image",
            store={
                'pos.category': (lambda self, cr, uid, ids, c={}: ids, ['image'], 10),
            },
            help="Small-sized image of the category. It is automatically "\
                 "resized as a 64x64px image, with aspect ratio preserved. "\
                 "Use this field anywhere a small image is required."),
    }

class product_template(osv.osv):
    _inherit = 'product.template'

    _columns = {
        'income_pdt': fields.boolean('Point of Sale Cash In', help="Check if, this is a product you can use to put cash into a statement for the point of sale backend."),
        'expense_pdt': fields.boolean('Point of Sale Cash Out', help="Check if, this is a product you can use to take cash from a statement for the point of sale backend, example: money lost, transfer to bank, etc."),
        'available_in_pos': fields.boolean('Available in the Point of Sale', help='Check if you want this product to appear in the Point of Sale'),
        'to_weight' : fields.boolean('To Weigh With Scale', help="Check if the product should be weighted using the hardware scale integration"),
        'pos_categ_id': fields.many2one('pos.category','Point of Sale Category', help="Those categories are used to group similar products for point of sale."),
    }

    _defaults = {
        'to_weight' : False,
        'available_in_pos': True,
    }

    def unlink(self, cr, uid, ids, context=None):
        product_ctx = dict(context or {}, active_test=False)
        if self.search_count(cr, uid, [('id', 'in', ids), ('available_in_pos', '=', True)], context=product_ctx):
            if self.pool['pos.session'].search_count(cr, uid, [('state', '!=', 'closed')], context=context):
                raise osv.except_osv(_('Error!'),
                    _('You cannot delete a product saleable in point of sale while a session is still opened.'))
        return super(product_template, self).unlink(cr, uid, ids, context=context)

class res_partner(osv.osv):
    _inherit = 'res.partner'

    def create_from_ui(self, cr, uid, partner, context=None):
        """ create or modify a partner from the point of sale ui.
            partner contains the partner's fields. """

class account_journal_cashbox_line(osv.osv):
    _inherit = 'account.journal.cashbox.line'

    def _get_image(self, cr, uid, ids, name, args, context=None):
        result = dict.fromkeys(ids, False)
        for obj in self.browse(cr, uid, ids, context=context):
            result[obj.id] = tools.image_get_resized_images(obj.image, avoid_resize_medium=True)
        return result

    def _set_image(self, cr, uid, id, name, value, args, context=None):
        return self.write(cr, uid, [id], {'image': tools.image_resize_image_big(value)}, context=context)

    _columns = {
        'image': fields.binary("Image",
            help="This field holds the image used as image for the banknote or coin, limited to 1024x1024px."),
        'image_medium': fields.function(_get_image, fnct_inv=_set_image,
            string="Medium-sized image", type="binary", multi="_get_image",
            store={
                'account.journal.cashbox.line': (lambda self, cr, uid, ids, c={}: ids, ['image'], 10),
            },
            help="Medium-sized image of the banknote or coin. It is automatically "\
                 "resized as a 128x128px image, with aspect ratio preserved, "\
                 "only when the image exceeds one of those sizes. Use this field in form views or some kanban views."),
        'image_small': fields.function(_get_image, fnct_inv=_set_image,
            string="Small-sized image", type="binary", multi="_get_image",
            store={
                'account.journal.cashbox.line': (lambda self, cr, uid, ids, c={}: ids, ['image'], 10),
            },
            help="Small-sized image of the banknote or coin. It is automatically "\
                 "resized as a 64x64px image, with aspect ratio preserved. "\
                 "Use this field anywhere a small image is required."),
    }

#class account_fiscal_position_tax(osv.osv):
#    _inherit = "account.fiscal.position.tax"
#    _columns = {
#        'company_id': fields.many2one('res.company', 'Company'),
#    }
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
