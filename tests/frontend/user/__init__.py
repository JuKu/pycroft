from flask import url_for

from tests import FrontendDataTestBase, FixtureDataTestBase, \
    FrontendWithAdminTestBase
from tests.factories import RoomFactory, SubnetFactory, PatchPortFactory
from tests.fixtures import permissions
from tests.fixtures.dummy import net
from tests.fixtures.dummy import port


class LegacyUserFrontendTestBase(FrontendDataTestBase, FixtureDataTestBase):
    """Test base providing access to `user_show`

    The user being logged in is :py:cls:`UserData.user1_admin`.

    Legacy, because using the `fixture` package.
    """
    datasets = frozenset(permissions.datasets | {net.SubnetData, port.PatchPortData})

    def setUp(self):
        self.login = permissions.UserData.user1_admin.login
        self.password = permissions.UserData.user1_admin.password
        super().setUp()


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


class UserFrontendTestBase(FrontendWithAdminTestBase):
    def create_factories(self):
        super().create_factories()
        # To move in a user we need to ensure:
        # 1. default traffic groups for a building
        self.room = RoomFactory(building__with_traffic_group=True)
        self.subnet = SubnetFactory()
        self.patch_port = PatchPortFactory(room=self.room, patched=True,
                                           switch_port__switch__host__owner=self.admin)
        # 2. A pool of default vlans so an IP can be found
        self.patch_port.switch_port.default_vlans.append(self.subnet.vlan)
