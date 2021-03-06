import pytest

from vakt.checker import RegexChecker
from vakt.storage.memory import MemoryStorage
from vakt.rules.net import CIDRRule
from vakt.rules.inquiry import SubjectEqualRule
from vakt.effects import DENY_ACCESS, ALLOW_ACCESS
from vakt.policy import Policy
from vakt.guard import Guard, Inquiry


# Create all required test policies
st = MemoryStorage()
policies = [
    Policy(
        uid='1',
        description="""
        Max, Nina, Ben, Henry are allowed to create, delete, get the resources
        only if the client IP matches and the inquiry states that any of them is the resource owner
        """,
        effect=ALLOW_ACCESS,
        subjects=('Max', 'Nina', '<Ben|Henry>'),
        resources=('myrn:example.com:resource:123', 'myrn:example.com:resource:345', 'myrn:something:foo:<.+>'),
        actions=('<create|delete>', 'get'),
        rules={
            'ip': CIDRRule('127.0.0.1/32'),
            'owner': SubjectEqualRule(),
        },
    ),
    Policy(
        uid='2',
        description='Allows Max to update any resource',
        effect=ALLOW_ACCESS,
        subjects=['Max'],
        actions=['update'],
        resources=['<.*>'],
    ),
    Policy(
        uid='3',
        description='Max is not allowed to print any resource',
        effect=DENY_ACCESS,
        subjects=['Max'],
        actions=['print'],
        resources=['<.*>'],
    ),
    Policy(
        uid='4'
    ),
    Policy(
        uid='5',
        description='Allows Nina to update any resources that have only digits',
        effect=ALLOW_ACCESS,
        subjects=['Nina'],
        actions=['update'],
        resources=['<[\d]+>'],
    ),
]
for p in policies:
    st.add(p)


@pytest.mark.parametrize('desc, inquiry, should_be_allowed', [
    (
        'Empty inquiry carries no information, so nothing is allowed, even empty Policy #4',
        Inquiry(),
        False,
    ),
    (
        'Max is allowed to update anything',
        Inquiry(
            subject='Max',
            resource='myrn:example.com:resource:123',
            action='update'
        ),
        True,
    ),
    (
        'Max is allowed to update anything, even empty one',
        Inquiry(
            subject='Max',
            resource='',
            action='update'
        ),
        True,
    ),
    (
        'Max, but not max is allowed to update anything (case-sensitive comparison)',
        Inquiry(
            subject='max',
            resource='myrn:example.com:resource:123',
            action='update'
        ),
        False,
    ),
    (
        'Max is not allowed to print anything',
        Inquiry(
            subject='Max',
            resource='myrn:example.com:resource:123',
            action='print',
        ),
        False,
    ),
    (
        'Max is not allowed to print anything, even if no resource is given',
        Inquiry(
            subject='Max',
            action='print'
        ),
        False,
    ),
    (
        'Max is not allowed to print anything, even an empty resource',
        Inquiry(
            subject='Max',
            action='print',
            resource=''
        ),
        False,
    ),
    (
        'Policy #1 matches and has allow-effect',
        Inquiry(
            subject='Nina',
            action='delete',
            resource='myrn:example.com:resource:123',
            context={
                'owner': 'Nina',
                'ip': '127.0.0.1'
            }
        ),
        True,
    ),
    (
        'Policy #1 matches - Henry is listed in the allowed subjects regexp',
        Inquiry(
            subject='Henry',
            action='get',
            resource='myrn:example.com:resource:123',
            context={
                'owner': 'Henry',
                'ip': '127.0.0.1'
            }
        ),
        True,
    ),
    (
        'Policy #1 does not match - one of the contexts was not found (misspelled)',
        Inquiry(
            subject='Nina',
            action='delete',
            resource='myrn:example.com:resource:123',
            context={
                'owner': 'Nina',
                'IP': '127.0.0.1'
            }
        ),
        False,
    ),
    (
        'Policy #1 does not match - one of the contexts is missing',
        Inquiry(
            subject='Nina',
            action='delete',
            resource='myrn:example.com:resource:123',
            context={
                'ip': '127.0.0.1'
            }
        ),
        False,
    ),
    (
        'Policy #1 does not match - context says that owner is Ben, not Nina',
        Inquiry(
            subject='Nina',
            action='delete',
            resource='myrn:example.com:resource:123',
            context={
                'owner': 'Ben',
                'ip': '127.0.0.1'
            }
        ),
        False,
    ),
    (
        'Policy #1 does not match - context says IP is not in the allowed range',
        Inquiry(
            subject='Nina',
            action='delete',
            resource='myrn:example.com:resource:123',
            context={
                'owner': 'Nina',
                'ip': '0.0.0.0'
            }
        ),
        False,
    ),
    (
        'Policy #5 does not match - action is update, but subjects does not match',
        Inquiry(
            subject='Sarah',
            action='update',
            resource='88',
        ),
        False,
    ),
    (
        'Policy #5 does not match - action is update, subject is Nina, but resource-name is not digits',
        Inquiry(
            subject='Nina',
            action='update',
            resource='abcd',
        ),
        False,
    ),
])
def test_is_allowed(desc, inquiry, should_be_allowed):
    g = Guard(st, RegexChecker())
    assert should_be_allowed == g.is_allowed(inquiry)


def test_is_allowed_for_none_policies():
    g = Guard(MemoryStorage(), RegexChecker())
    assert not g.is_allowed(Inquiry(subject='foo', action='bar', resource='baz'))


def test_not_allowed_when_similar_policies_have_at_least_one_deny_access():
    st = MemoryStorage()
    policies = (
        Policy(
            uid='1',
            effect=ALLOW_ACCESS,
            subjects=['foo'],
            actions=['bar'],
            resources=['baz'],
        ),
        Policy(
            uid='2',
            effect=DENY_ACCESS,
            subjects=['foo'],
            actions=['bar'],
            resources=['baz'],
        ),
    )
    for p in policies:
        st.add(p)
    g = Guard(st, RegexChecker())
    assert not g.is_allowed(Inquiry(subject='foo', action='bar', resource='baz'))


def test_guard_if_unexpected_exception_raised():
    # for testing unexpected exception
    class BadMemoryStorage(MemoryStorage):
        def find_for_inquiry(self, inquiry=None, checker=None):
            raise Exception('This is test class that raises errors')
    g = Guard(BadMemoryStorage(), RegexChecker())
    assert not g.is_allowed(Inquiry(subject='foo', action='bar', resource='baz'))
