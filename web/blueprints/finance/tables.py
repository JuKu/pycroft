from flask import url_for
from wtforms.widgets.core import html_params

from web.blueprints.helpers.table import BootstrapTable, Column, SplittedTable


class FinanceTable(BootstrapTable):
    def __init__(self, *a, user_id=None, **kw):
        """Init

        :param int user_id: An optional user_id.  If set, this causes
            a “details” button to be rendered in the toolbar
            referencing the user.
        """
        table_args = {
            'data-side-pagination': 'server',
            # 'data-search': 'true',
            'data-sort-order': 'desc',
            'data-sort-name': 'valid_on',
        }
        original_table_args = kw.pop('table_args', {})
        table_args.update(original_table_args)
        super().__init__(*a, columns=[
            Column(name='posted_at', title='Erstellt um'),
            Column(name='valid_on', title='Gültig am'),
            Column(name='description', title='Beschreibung', formatter='linkFormatter'),
            Column(name='amount', title='Wert', formatter='coloredFormatter',
                   cell_style='tdRelativeCellStyle'),
        ], table_args=table_args, **kw)
        self.user_id = user_id

    def generate_toolbar(self):
        """Generate a toolbar with a details button

        If a user_id was passed in the constructor, this renders a
        “details” button reaching the finance overview of the user's account.
        """
        if self.user_id is None:
            return
        args = {
            'class': "btn btn-primary",
            'href': url_for("user.user_account", user_id=self.user_id)
        }
        yield "<a {}>".format(html_params(**args))
        yield "<span class=\"glyphicon glyphicon-stats\"></span>"
        yield "Details"
        yield "</a>"


class FinanceTableSplitted(FinanceTable, SplittedTable):
    def __init__(self, *a, **kw):
        splits = (('soll', "Soll"), ('haben', "Haben"))
        table_args = {
            'data-row-style': False,
            'data-sort-name': False,  # the "valid_on" col doesn't exist here
        }
        table_args.update(kw.pop('table_args', {}))
        super().__init__(*a, splits=splits, table_args=table_args, **kw)
