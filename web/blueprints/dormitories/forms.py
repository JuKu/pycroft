# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Pycroft Authors. See the AUTHORS file.
# This file is part of the Pycroft project and licensed under the terms of
# the Apache License, Version 2.0. See the LICENSE file for details.


from flaskext.wtf import Form, TextField, validators, BooleanField, \
    QuerySelectField
from pycroft.model.dormitory import Dormitory


def dormitory_query():
    return Dormitory.q.order_by(Dormitory.short_name)


class RoomForm(Form):
    number = TextField(u"Nummer")
    level = TextField(u"Etage")
    inhabitable = BooleanField(u"Bewohnbar")
    dormitory_id = QuerySelectField(u"Wohnheim",
                                    get_label='short_name',
                                    query_factory=dormitory_query)


class DormitoryForm(Form):
    short_name = TextField(u"Kürzel")
    number = TextField(u"Nummer")
    street = TextField(u"Straße", validators=[validators.Length(min=5)])