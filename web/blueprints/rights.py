# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Pycroft Authors. See the AUTHORS file.
# This file is part of the Pycroft project and licensed under the terms of
# the Apache License, Version 2.0. See the LICENSE file for details.
"""
    web.blueprints.rights
    ~~~~~~~~~~~~~~

    This module defines view functions for /rights

    :copyright: (c) 2012 by AG DSN.
"""

from flask import Blueprint, render_template
from web import app

bp = Blueprint('bp_rights', __name__, )


@bp.route('/rights')
@bp.route('/rights/groups')
def rights_groups():
    return render_template('test.html', page_title = u"Gruppen", subnav = 'nav/rights.html')


@bp.route('/rights/rights')
def rights_rights():
    return render_template('test.html', page_title = u"Rechte", subnav = 'nav/rights.html')


app.register_blueprint(bp)