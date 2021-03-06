from functools import partial
from itertools import chain

import factory

from pycroft.model.user import Membership, PropertyGroup

from .base import BaseFactory
from .user import UserFactory


class MembershipFactory(BaseFactory):
    class Meta:
        model = Membership
    begins_at = None
    ends_at = None

    user = factory.SubFactory(UserFactory)
    # note: group is non-nullable!
    group = None


def _maybe_append_seq(n, prefix):
    """Append a sequence value to a prefix if non-zero"""
    if not n:
        return prefix
    return "{} {}".format(prefix, n)


class PropertyGroupFactory(BaseFactory):
    class Meta:
        model = PropertyGroup
        exclude = ('granted', 'denied')
    granted = frozenset()
    denied = frozenset()

    name = factory.Sequence(lambda n: "Property group %s" % n)

    @factory.lazy_attribute
    def property_grants(self):
        return dict(chain(((k, True) for k in self.granted),
                          ((k, False) for k in self.denied)))


class AdminPropertyGroupFactory(PropertyGroupFactory):
    name = factory.Sequence(partial(_maybe_append_seq, prefix="Admin-Gruppe"))
    granted = frozenset((
        'user_show', 'user_change', 'user_mac_change',
        'finance_show', 'finance_change',
        'infrastructure_show', 'infrastructure_change',
        'facilities_show', 'facilities_change',
        'groups_show', 'groups_change_membership', 'groups_change',
        'groups_traffic_show', 'groups_traffic_change',
    ))
