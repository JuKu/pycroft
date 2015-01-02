# -*- coding: utf-8 -*-
# Copyright (c) 2015 The Pycroft Authors. See the AUTHORS file.
# This file is part of the Pycroft project and licensed under the terms of
# the Apache License, Version 2.0. See the LICENSE file for details.
"""
    web.blueprints.dormitories
    ~~~~~~~~~~~~~~

    This module defines view functions for /dormitories
    :copyright: (c) 2012 by AG DSN.
"""

from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, url_for
from flask.ext.login import current_user
from pycroft import lib
from pycroft.helpers import dormitory
from pycroft.model.session import session
from pycroft.model.dormitory import Room, Dormitory
from web.blueprints.navigation import BlueprintNavigation
from web.blueprints.dormitories.forms import RoomForm, DormitoryForm, \
    RoomLogEntry
from web.blueprints.access import BlueprintAccess

bp = Blueprint('dormitories', __name__, )
access = BlueprintAccess(bp, ['dormitories_show'])
nav = BlueprintNavigation(bp, "Wohnheime", blueprint_access=access)


@bp.route('/')
@nav.navigate(u"Wohnheime")
# careful with permissions here, redirects!
def overview():
    dormitories_list = Dormitory.q.all()
    dormitories_list = dormitory.sort_dormitories(dormitories_list)
    return render_template('dormitories/overview.html',
        dormitories=dormitories_list)


@bp.route('/show/<dormitory_id>')
@access.require('dormitories_show')
def dormitory_show(dormitory_id):
    dormitory = Dormitory.q.get(dormitory_id)
    rooms_list = dormitory.rooms
    return render_template('dormitories/dormitory_show.html',
        page_title=u"Wohnheim " + dormitory.short_name, rooms=rooms_list)


@bp.route('/room/show/<room_id>', methods=['GET', 'POST'])
@access.require('dormitories_show')
def room_show(room_id):
    room = Room.q.get(room_id)
    form = RoomLogEntry()

    if form.validate_on_submit():
        lib.logging.log_room_event(form.message.data, current_user, room)
        flash(u'Kommentar hinzugefügt', 'success')

    room_log_list = room.room_log_entries[::-1]

    return render_template('dormitories/room_show.html',
        page_title=u"Raum " + str(room.dormitory.short_name) + u" " + \
                   str(room.level) + u"-" + str(room.number),
        room=room,
        room_log=room_log_list,
        form=form)


# ToDo: Review this!
@bp.route('/levels/<int:dormitory_id>')
@access.require('dormitories_show')
def dormitory_levels(dormitory_id):
    dormitory = Dormitory.q.get(dormitory_id)
    rooms_list = Room.q.filter_by(
        dormitory_id=dormitory_id).order_by(Room.level).distinct()
    levels_list = [room.level for room in rooms_list]
    levels_list = list(set(levels_list))

    return render_template('dormitories/levels.html',
        levels=levels_list, dormitory_id=dormitory_id, dormitory=dormitory,
        page_title=u"Etagen Wohnheim {}".format(dormitory.short_name))


# ToDo: Review this!
@bp.route('/levels/<int:dormitory_id>/rooms/<int:level>')
@access.require('dormitories_show')
def dormitory_level_rooms(dormitory_id, level):
    dormitory = Dormitory.q.get(dormitory_id)
    rooms_list = Room.q.filter_by(
        dormitory_id=dormitory_id, level=level).order_by(Room.number)

    level_l0 = "{:02d}".format(level)

    #TODO depending on, whether a user is living in the room, the room is
    # a link to the user. If there is more then one user, the room is
    # duplicated
    return render_template('dormitories/rooms.html', rooms=rooms_list, level=level_l0,
                           dormitory=dormitory, page_title=u"Zimmer der Etage {:d} des Wohnheims {}".format(level,
                                                              dormitory.short_name))
