from odoo import _, models

class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_moyee_portal_invoice_status(self):
        self.ensure_one()
        state = self.payment_state or ''
        if state == 'paid':
            return {'label': _('Paid'), 'class': 'moyee-status-delivered'}
        elif state == 'in_payment':
            return {'label': _('Incasso in progress'), 'class': 'moyee-status-upcoming'}
        elif state in ('not_paid', 'partial'):
            return {'label': _('Not paid'), 'class': 'moyee-status-cancelled'}
        else:
            return {'label': _('Not paid'), 'class': 'moyee-status-cancelled'}
