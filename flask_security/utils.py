# -*- coding: utf-8 -*-
"""
    flask.ext.security.utils
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Flask-Security utils module

    :copyright: (c) 2012 by Matt Wright.
    :license: MIT, see LICENSE for more details.
"""

import base64
import os
from contextlib import contextmanager
from importlib import import_module

from flask import url_for, flash, current_app, request, session, render_template

from .signals import user_registered, password_reset_requested


def generate_token():
    return base64.urlsafe_b64encode(os.urandom(30))


def do_flash(message, category):
    if config_value(current_app, 'FLASH_MESSAGES'):
        flash(message, category)


def get_class_from_string(app, key):
    """Get a reference to a class by its configuration key name."""
    cv = config_value(app, key).split('::')
    cm = import_module(cv[0])
    return getattr(cm, cv[1])


def get_url(endpoint_or_url):
    """Returns a URL if a valid endpoint is found. Otherwise, returns the
    provided value."""
    try:
        return url_for(endpoint_or_url)
    except:
        return endpoint_or_url


def get_post_login_redirect():
    """Returns the URL to redirect to after a user logs in successfully"""
    return (get_url(request.args.get('next')) or
            get_url(request.form.get('next')) or
            find_redirect('SECURITY_POST_LOGIN_VIEW'))


def find_redirect(key):
    """Returns the URL to redirect to after a user logs in successfully"""
    result = (get_url(session.pop(key.lower(), None)) or
              get_url(current_app.config[key.upper()] or None) or '/')

    session.pop(key.lower(), None)

    return result


def config_value(app, key, default=None):
    return app.config.get('SECURITY_' + key.upper(), default)


def send_mail(subject, recipient, template, context=None):
    from flask.ext.mail import Message

    context = context or {}

    msg = Message(subject,
                  sender=current_app.security.email_sender,
                  recipients=[recipient])

    base = 'security/email'
    msg.body = render_template('%s/%s.txt' % (base, template), **context)
    msg.html = render_template('%s/%s.html' % (base, template), **context)

    current_app.mail.send(msg)


@contextmanager
def capture_registrations(confirmation_sent_at=None):
    users = []

    def _on(user, app):
        if confirmation_sent_at:
            user.confirmation_sent_at = confirmation_sent_at
            current_app.security.datastore._save_model(user)

        users.append(user)

    user_registered.connect(_on)

    try:
        yield users
    finally:
        user_registered.disconnect(_on)


@contextmanager
def capture_reset_password_requests(reset_password_sent_at=None):
    users = []

    def _on(user, app):
        if reset_password_sent_at:
            user.reset_password_sent_at = reset_password_sent_at
            current_app.security.datastore._save_model(user)

        users.append(user)

    password_reset_requested.connect(_on)

    try:
        yield users
    finally:
        password_reset_requested.disconnect(_on)
