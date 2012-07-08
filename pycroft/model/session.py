# -*- coding: utf-8 -*-
"""
    pycroft.model.session
    ~~~~~~~~~~~~~~

    This module contains the session stuff for db actions.

    :copyright: (c) 2011 by AG DSN.
"""

from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import create_engine, pool


class DummySession(object):
    def __getattr__(self, item):
        # raise Exception("Session not inizialized")
        # Workaround for the forking debug server
        init_session()
        return getattr(session, item)


class SessionWrapper(object):
    active = True

    def __init__(self, autocommit=False, autoflush=True, connection_string=None, pooling=True):
        if connection_string is None:
            connection_string = "sqlite:////tmp/test.db"

        self._engine = create_engine(connection_string, echo=False)
        self._scoped_session = scoped_session(
                                sessionmaker(bind=self._engine,
                                             autocommit=autocommit,
                                             autoflush=autoflush))

    def __getattr__(self, item):
        if not self.active:
            raise AttributeError, item
        return getattr(self._scoped_session, item)

    def get_engine(self):
        return self._engine

    def disable_instance(self):
        self.active = False


def init_session(connection_string=None):
    global session
    if isinstance(session, DummySession):
        session = SessionWrapper(connection_string=connection_string)

def reinit_session(connection_string=None):
    global session

    if not isinstance(session, DummySession):
        session.disable_instance()
    session = SessionWrapper(connection_string=connection_string, pooling=False)

session = DummySession()
