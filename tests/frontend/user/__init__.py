from flask import url_for

from tests import FrontendDataTestBase, FixtureDataTestBase, FactoryDataTestBase
from tests.fixtures import permissions
from tests.fixtures.dummy import net
from tests.fixtures.dummy import port

from tests.factories.user import UserFactory
from tests.factories.config import ConfigFactory
from tests.factories.property import MembershipFactory, AdminPropertyGroupFactory


class LegacyUserFrontendTestBase(FrontendDataTestBase, FixtureDataTestBase):
    """Test base providing access to `user_show`

    The user being logged in is :py:cls:`UserData.user1_admin`.

    Legacy, because using the `fixture` package.
    """
    datasets = frozenset(permissions.datasets | {net.SubnetData, port.SwitchPatchPortData})

    def setUp(self):
        self.login = permissions.UserData.user1_admin.login
        self.password = permissions.UserData.user1_admin.password
        super().setUp()


class UserFrontendTestBase(FrontendDataTestBase, FactoryDataTestBase):
    def create_factories(self):
        self.login = 'hans_der_nette_admin'
        self.password = 'This is 1 strong testpassword!!'
        self.admin = UserFactory(login=self.login, password=self.password)
        admin_group = AdminPropertyGroupFactory()
        MembershipFactory.create(user=self.admin, group=admin_group)
        self.config = ConfigFactory()


class UserLogTestBase(LegacyUserFrontendTestBase):
    def get_logs(self, user_id=None, **kw):
        """Request the logs, assert validity, and return the response.

        By default, the logs are fetched for the user logging in.

        The following assertions are made:
          * The response code is 200
          * The response content_type contains ``"json"``
          * The response's JSON contains an ``"items"`` key

        :returns: ``response.json['items']``
        """
        if user_id is None:
            user_id = self.user_id
        log_endpoint = url_for('user.user_show_logs_json',
                               user_id=user_id,
                               **kw)
        response = self.assert_response_code(log_endpoint, code=200)
        self.assertIn("json", response.content_type.lower())
        json = response.json
        self.assertIsNotNone(json.get('items'))
        return json['items']
