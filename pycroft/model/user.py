# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Pycroft Authors. See the AUTHORS file.
# This file is part of the Pycroft project and licensed under the terms of
# the Apache License, Version 2.0. See the LICENSE file for details.
"""
    pycroft.model.user
    ~~~~~~~~~~~~~~

    This module contains the class User.

    :copyright: (c) 2011 by AG DSN.
"""
from base import ModelBase
from sqlalchemy import ForeignKey
from sqlalchemy import Column
from sqlalchemy.orm import backref, relationship, validates
from sqlalchemy.types import DateTime, Integer
from sqlalchemy.types import String
import re
from pycroft.helpers.user_helper import hash_password, verify_password



class User(ModelBase):
    login = Column(String(40), nullable=False)
    name = Column(String(255), nullable=False)
    registration_date = Column(DateTime, nullable=False)
    passwd_hash = Column(String)

    # many to one from User to Room
    room = relationship("Room", backref=backref("users", order_by=id))
    room_id = Column(Integer, ForeignKey("room.id"), nullable=False)

    login_regex = re.compile("^[a-z][a-z0-9_]{1,20}[a-z0-9]$")
    name_regex = re.compile("^(([a-z]{1,5}|[A-Z][a-z0-9]+)\\s)*"\
                            "([A-Z][a-z0-9]+)((-|\\s)"\
                            "[A-Z][a-z0-9]+|\\s[a-z]{1,5})*$")

    @validates('login')
    def validate_login(self, key, value):
        if not User.login_regex.match(value):
            raise Exception("invalid unix-login!")
        return value

    def check_password(self, plaintext_password):
        """verify a given plaintext password against the users passwd hash.

        """
        return verify_password(plaintext_reference, self.passwd_hash)

    def set_password(self, plain_password):
        """Store a hash of a given plaintext passwd for the user.

        """
        self.passwd_hash = hash_password(plain_password)
