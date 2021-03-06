# -*- coding: utf-8 -*-

import mock
from nose.tools import *  # noqa (PEP8 asserts)

from modularodm import Q
from modularodm.exceptions import ValidationError

import hmac
import hashlib
from StringIO import StringIO

from framework.auth.core import Auth

from website import settings
from website.models import User, Node
from website.conferences.views import _render_conference_node
from website.conferences.model import Conference
from website.conferences import utils, message
from website.util import api_url_for, web_url_for

from tests.base import OsfTestCase, fake
from tests.factories import ModularOdmFactory, FakerAttribute, ProjectFactory, UserFactory
from factory import Sequence, post_generation


class ConferenceFactory(ModularOdmFactory):
    FACTORY_FOR = Conference

    endpoint = Sequence(lambda n: 'conference{0}'.format(n))
    name = FakerAttribute('catch_phrase')
    active = True

    @post_generation
    def admins(self, create, extracted, **kwargs):
        self.admins = extracted or [UserFactory()]


def create_fake_conference_nodes(n, endpoint):
    nodes = []
    for i in range(n):
        node = ProjectFactory(is_public=True)
        node.add_tag(endpoint, Auth(node.creator))
        node.save()
        nodes.append(node)
    return nodes


class TestConferenceUtils(OsfTestCase):

    def test_get_or_create_user_exists(self):
        user = UserFactory()
        fetched, created = utils.get_or_create_user(user.fullname, user.username, True)
        assert_false(created)
        assert_equal(user._id, fetched._id)
        assert_false('is_spam' in fetched.system_tags)

    def test_get_or_create_user_not_exists(self):
        fullname = 'Roger Taylor'
        username = 'roger@queen.com'
        fetched, created = utils.get_or_create_user(fullname, username, False)
        assert_true(created)
        assert_equal(fetched.fullname, fullname)
        assert_equal(fetched.username, username)
        assert_false('is_spam' in fetched.system_tags)

    def test_get_or_create_user_is_spam(self):
        fullname = 'John Deacon'
        username = 'deacon@queen.com'
        fetched, created = utils.get_or_create_user(fullname, username, True)
        assert_true(created)
        assert_equal(fetched.fullname, fullname)
        assert_equal(fetched.username, username)
        assert_true('is_spam' in fetched.system_tags)

    def test_get_or_create_node_exists(self):
        node = ProjectFactory()
        fetched, created = utils.get_or_create_node(node.title, node.creator)
        assert_false(created)
        assert_equal(node._id, fetched._id)

    def test_get_or_create_node_title_not_exists(self):
        title = 'Night at the Opera'
        creator = UserFactory()
        node = ProjectFactory(creator=creator)
        fetched, created = utils.get_or_create_node(title, creator)
        assert_true(created)
        assert_not_equal(node._id, fetched._id)

    def test_get_or_create_node_user_not_exists(self):
        title = 'Night at the Opera'
        creator = UserFactory()
        node = ProjectFactory(title=title)
        fetched, created = utils.get_or_create_node(title, creator)
        assert_true(created)
        assert_not_equal(node._id, fetched._id)


class ContextTestCase(OsfTestCase):

    MAILGUN_API_KEY = 'mailkimp'

    @classmethod
    def setUpClass(cls):
        super(ContextTestCase, cls).setUpClass()
        settings.MAILGUN_API_KEY, cls._MAILGUN_API_KEY = cls.MAILGUN_API_KEY, settings.MAILGUN_API_KEY

    @classmethod
    def tearDownClass(cls):
        super(ContextTestCase, cls).tearDownClass()
        settings.MAILGUN_API_KEY = cls._MAILGUN_API_KEY

    def make_context(self, method='POST', **kwargs):
        data = {
            'X-Mailgun-Sscore': 0,
            'timestamp': '123',
            'token': 'secret',
            'signature': hmac.new(
                key=settings.MAILGUN_API_KEY,
                msg='{}{}'.format('123', 'secret'),
                digestmod=hashlib.sha256,
            ).hexdigest(),
        }
        data.update(kwargs.pop('data', {}))
        data = {
            key: value
            for key, value in data.iteritems()
            if value is not None
        }
        return self.app.app.test_request_context(method=method, data=data, **kwargs)


class TestProvisionNode(ContextTestCase):

    def setUp(self):
        super(TestProvisionNode, self).setUp()
        self.node = ProjectFactory()
        self.user = self.node.creator
        self.conference = ConferenceFactory()
        self.body = 'dragon on my back'
        self.content = 'dragon attack'
        self.attachment = StringIO(self.content)
        self.recipient = '{0}{1}-poster@osf.io'.format(
            'test-' if settings.DEV_MODE else '',
            self.conference.endpoint,
        )

    def make_context(self, **kwargs):
        data = {
            'attachment-count': '1',
            'attachment-1': (self.attachment, 'attachment-1'),
            'X-Mailgun-Sscore': 0,
            'recipient': self.recipient,
            'stripped-text': self.body,
        }
        data.update(kwargs.pop('data', {}))
        return super(TestProvisionNode, self).make_context(data=data, **kwargs)

    @mock.patch('website.conferences.utils.upload_attachments')
    def test_provision(self, mock_upload):
        with self.make_context():
            msg = message.ConferenceMessage()
            utils.provision_node(self.conference, msg, self.node, self.user)
        assert_true(self.node.is_public)
        assert_in(self.conference.admins[0], self.node.contributors)
        assert_in('emailed', self.node.system_tags)
        assert_in(self.conference.endpoint, self.node.system_tags)
        assert_in(self.conference.endpoint, self.node.tags)
        assert_not_in('spam', self.node.system_tags)
        mock_upload.assert_called_with(self.user, self.node, msg.attachments)

    @mock.patch('website.conferences.utils.upload_attachments')
    def test_provision_private(self, mock_upload):
        self.conference.public_projects = False
        self.conference.save()
        with self.make_context():
            msg = message.ConferenceMessage()
            utils.provision_node(self.conference, msg, self.node, self.user)
        assert_false(self.node.is_public)
        assert_in(self.conference.admins[0], self.node.contributors)
        assert_in('emailed', self.node.system_tags)
        assert_not_in('spam', self.node.system_tags)
        mock_upload.assert_called_with(self.user, self.node, msg.attachments)

    @mock.patch('website.conferences.utils.upload_attachments')
    def test_provision_spam(self, mock_upload):
        with self.make_context(data={'X-Mailgun-Sscore': message.SSCORE_MAX_VALUE + 1}):
            msg = message.ConferenceMessage()
            utils.provision_node(self.conference, msg, self.node, self.user)
        assert_false(self.node.is_public)
        assert_in(self.conference.admins[0], self.node.contributors)
        assert_in('emailed', self.node.system_tags)
        assert_in('spam', self.node.system_tags)
        mock_upload.assert_called_with(self.user, self.node, msg.attachments)

    @mock.patch('website.conferences.utils.requests.put')
    @mock.patch('website.addons.osfstorage.utils.get_upload_url')
    def test_upload(self, mock_get_url, mock_put):
        mock_get_url.return_value = 'http://queen.com/'
        self.attachment.filename = 'hammer-to-fall'
        self.attachment.content_type = 'application/json'
        utils.upload_attachment(self.user, self.node, self.attachment)
        mock_get_url.assert_called_with(
            self.node,
            self.user,
            len(self.content),
            self.attachment.content_type,
            self.attachment.filename,
        )
        mock_put.assert_called_with(
            mock_get_url.return_value,
            data=self.content,
            headers={'Content-Type': self.attachment.content_type},
        )

    @mock.patch('website.conferences.utils.requests.put')
    @mock.patch('website.addons.osfstorage.utils.get_upload_url')
    def test_upload_no_file_name(self, mock_get_url, mock_put):
        mock_get_url.return_value = 'http://queen.com/'
        self.attachment.filename = ''
        self.attachment.content_type = 'application/json'
        utils.upload_attachment(self.user, self.node, self.attachment)
        mock_get_url.assert_called_with(
            self.node,
            self.user,
            len(self.content),
            self.attachment.content_type,
            settings.MISSING_FILE_NAME,
        )
        mock_put.assert_called_with(
            mock_get_url.return_value,
            data=self.content,
            headers={'Content-Type': self.attachment.content_type},
        )


class TestMessage(ContextTestCase):

    def test_verify_signature_valid(self):
        with self.make_context():
            msg = message.ConferenceMessage()
            msg.verify_signature()

    def test_verify_signature_invalid(self):
        with self.make_context(data={'signature': 'fake'}):
            self.app.app.preprocess_request()
            msg = message.ConferenceMessage()
            with assert_raises(message.ConferenceError):
                msg.verify_signature()

    def test_is_spam_false_missing_headers(self):
        ctx = self.make_context(
            method='POST',
            data={'X-Mailgun-Sscore': message.SSCORE_MAX_VALUE - 1},
        )
        with ctx:
            msg = message.ConferenceMessage()
            assert not msg.is_spam

    def test_is_spam_false_all_headers(self):
        ctx = self.make_context(
            method='POST',
            data={
                'X-Mailgun-Sscore': message.SSCORE_MAX_VALUE - 1,
                'X-Mailgun-Dkim-Check-Result': message.DKIM_PASS_VALUES[0],
                'X-Mailgun-Spf': message.SPF_PASS_VALUES[0],
            },
        )
        with ctx:
            msg = message.ConferenceMessage()
            assert not msg.is_spam

    def test_is_spam_true_sscore(self):
        ctx = self.make_context(
            method='POST',
            data={'X-Mailgun-Sscore': message.SSCORE_MAX_VALUE + 1},
        )
        with ctx:
            msg = message.ConferenceMessage()
            assert msg.is_spam

    def test_is_spam_true_dkim(self):
        ctx = self.make_context(
            method='POST',
            data={'X-Mailgun-Dkim-Check-Result': message.DKIM_PASS_VALUES[0][::-1]},
        )
        with ctx:
            msg = message.ConferenceMessage()
            assert msg.is_spam

    def test_is_spam_true_spf(self):
        ctx = self.make_context(
            method='POST',
            data={'X-Mailgun-Spf': message.SPF_PASS_VALUES[0][::-1]},
        )
        with ctx:
            msg = message.ConferenceMessage()
            assert msg.is_spam

    def test_subject(self):
        ctx = self.make_context(
            method='POST',
            data={'subject': 'RE: Hip Hopera'},
        )
        with ctx:
            msg = message.ConferenceMessage()
            assert_equal(msg.subject, 'Hip Hopera')

    def test_recipient(self):
        address = 'test-conference@osf.io'
        ctx = self.make_context(
            method='POST',
            data={'recipient': address},
        )
        with ctx:
            msg = message.ConferenceMessage()
            assert_equal(msg.recipient, address)

    def test_text(self):
        text = 'welcome to my nuclear family'
        ctx = self.make_context(
            method='POST',
            data={'stripped-text': text},
        )
        with ctx:
            msg = message.ConferenceMessage()
            assert_equal(msg.text, text)

    def test_sender_name(self):
        names = [
            (' Fred', 'Fred'),
            (u'Me‰¨ü', u'Me‰¨ü'),
            (u'Fred <fred@queen.com>', u'Fred'),
            (u'"Fred" <fred@queen.com>', u'Fred'),
        ]
        for name in names:
            with self.make_context(data={'from': name[0]}):
                msg = message.ConferenceMessage()
                assert_equal(msg.sender_name, name[1])

    def test_route_invalid_pattern(self):
        with self.make_context(data={'recipient': 'spam@osf.io'}):
            self.app.app.preprocess_request()
            msg = message.ConferenceMessage()
            with assert_raises(message.ConferenceError):
                msg.route

    def test_route_invalid_test(self):
        recipient = '{0}conf-talk@osf.io'.format('' if settings.DEV_MODE else 'test-')
        with self.make_context(data={'recipient': recipient}):
            self.app.app.preprocess_request()
            msg = message.ConferenceMessage()
            with assert_raises(message.ConferenceError):
                msg.route

    def test_route_valid(self):
        recipient = '{0}conf-talk@osf.io'.format('test-' if settings.DEV_MODE else '')
        with self.make_context(data={'recipient': recipient}):
            self.app.app.preprocess_request()
            msg = message.ConferenceMessage()
            assert_equal(msg.conference_name, 'conf')
            assert_equal(msg.conference_category, 'talk')

    def test_attachments_count_zero(self):
        with self.make_context(data={'attachment-count': '0'}):
            msg = message.ConferenceMessage()
            assert_equal(msg.attachments, [])

    def test_attachments_count_one(self):
        content = 'slightly mad'
        sio = StringIO(content)
        ctx = self.make_context(
            method='POST',
            data={
                'attachment-count': 1,
                'attachment-1': (sio, 'attachment-1'),
            },
        )
        with ctx:
            msg = message.ConferenceMessage()
            assert_equal(len(msg.attachments), 1)
            assert_equal(msg.attachments[0].read(), content)


class TestConferenceEmailViews(OsfTestCase):

    def test_conference_data(self):
        conference = ConferenceFactory()

        # Create conference nodes
        n_conference_nodes = 3
        conf_nodes = create_fake_conference_nodes(
            n_conference_nodes,
            conference.endpoint,
        )
        # Create a non-conference node
        ProjectFactory()

        url = api_url_for('conference_data', meeting=conference.endpoint)
        res = self.app.get(url)
        assert_equal(res.status_code, 200)
        json = res.json
        assert_equal(len(json), n_conference_nodes)

    def test_conference_results(self):
        conference = ConferenceFactory()

        url = web_url_for('conference_results', meeting=conference.endpoint)
        res = self.app.get(url)
        assert_equal(res.status_code, 200)


class TestConferenceModel(OsfTestCase):

    def test_endpoint_and_name_are_required(self):
        with assert_raises(ValidationError):
            ConferenceFactory(endpoint=None, name=fake.company()).save()
        with assert_raises(ValidationError):
            ConferenceFactory(endpoint='spsp2014', name=None).save()


class TestConferenceIntegration(ContextTestCase):

    @mock.patch('website.conferences.utils.upload_attachments')
    def test_integration(self, mock_upload):
        fullname = 'John Deacon'
        username = 'deacon@queen.com'
        title = 'good songs'
        conference = ConferenceFactory()
        body = 'dragon on my back'
        content = 'dragon attack'
        recipient = '{0}{1}-poster@osf.io'.format(
            'test-' if settings.DEV_MODE else '',
            conference.endpoint,
        )
        res = self.app.post(
            api_url_for('meeting_hook'),
            {
                'X-Mailgun-Sscore': 0,
                'timestamp': '123',
                'token': 'secret',
                'signature': hmac.new(
                    key=settings.MAILGUN_API_KEY,
                    msg='{}{}'.format('123', 'secret'),
                    digestmod=hashlib.sha256,
                ).hexdigest(),
                'attachment-count': '1',
                'X-Mailgun-Sscore': 0,
                'from': '{0} <{1}>'.format(fullname, username),
                'recipient': recipient,
                'subject': title,
                'stripped-text': body,
            },
            upload_files=[
                ('attachment-1', 'attachment-1', content),
            ],
        )
        assert_true(mock_upload.called)
        users = User.find(Q('username', 'eq', username))
        assert_equal(users.count(), 1)
        nodes = Node.find(Q('title', 'eq', title))
        assert_equal(nodes.count(), 1)
        node = nodes[0]
        assert_equal(node.get_wiki_page('home').content, body)
