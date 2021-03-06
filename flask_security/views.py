# -*- coding: utf-8 -*-
"""
    flask.ext.security.views
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Flask-Security views module

    :copyright: (c) 2012 by Matt Wright.
    :license: MIT, see LICENSE for more details.
"""

from flask import current_app as app, redirect, request, session, \
     render_template
from flask.ext.login import login_user, logout_user
from flask.ext.principal import Identity, AnonymousIdentity, identity_changed
from werkzeug.local import LocalProxy

from .confirmable import confirm_by_token, \
     reset_confirmation_token, send_confirmation_instructions
from .exceptions import TokenExpiredError, UserNotFoundError, \
     ConfirmationError, BadCredentialsError, ResetPasswordError
from .recoverable import reset_by_token, \
     reset_password_reset_token
from .signals import user_registered
from .utils import get_post_login_redirect, do_flash


# Convenient references
_security = LocalProxy(lambda: app.security)

_datastore = LocalProxy(lambda: app.security.datastore)

_logger = LocalProxy(lambda: app.logger)


def _do_login(user, remember=True):
    if login_user(user, remember):
        identity_changed.send(app._get_current_object(),
                              identity=Identity(user.id))

        _logger.debug('User %s logged in' % user)
        return True
    return False


def authenticate():
    """View function which handles an authentication attempt. If authentication
    is successful the user is redirected to, if set, the value of the `next`
    form parameter. If that value is not set the user is redirected to the
    value of the `SECURITY_POST_LOGIN_VIEW` configuration value. If
    authenticate fails the user an appropriate error message is flashed and
    the user is redirected to the referring page or the login view.
    """
    form = _security.LoginForm()

    try:
        user = _security.auth_provider.authenticate(form)

        if _do_login(user, remember=form.remember.data):
            return redirect(get_post_login_redirect())

        raise BadCredentialsError('Inactive user')

    except BadCredentialsError, e:
        msg = str(e)

    except Exception, e:
        msg = 'Unknown authentication error'

    do_flash(msg, 'error')
    _logger.debug('Unsuccessful authentication attempt: %s' % msg)

    return redirect(request.referrer or _security.login_manager.login_view)


def logout():
    """View function which logs out the current user. When completed the user
    is redirected to the value of the `next` query string parameter or the
    `SECURITY_POST_LOGIN_VIEW` configuration value.
    """
    for key in ('identity.name', 'identity.auth_type'):
        session.pop(key, None)

    identity_changed.send(app._get_current_object(),
                          identity=AnonymousIdentity())

    logout_user()
    _logger.debug('User logged out')

    return redirect(request.args.get('next', None) or
                    _security.post_logout_view)


def register():
    """View function which registers a new user and, if configured so, the user
    isautomatically logged in. If required confirmation instructions are sent
    via email.  After registration is completed the user is redirected to, if
    set, the value of the `SECURITY_POST_REGISTER_VIEW` configuration value.
    Otherwise the user is redirected to the `SECURITY_POST_LOGIN_VIEW`
    configuration value.
    """
    form = _security.RegisterForm(csrf_enabled=not app.testing)

    # Exit early if the form doesn't validate
    if form.validate_on_submit():
        # Create user and send signal
        user = _datastore.create_user(**form.to_dict())

        user_registered.send(user, app=app._get_current_object())

        # Send confirmation instructions if necessary
        if _security.confirm_email:
            send_confirmation_instructions(user)

        _logger.debug('User %s registered' % user)

        # Login the user if allowed
        if not _security.confirm_email or _security.login_without_confirmation:
            _do_login(user)

        return redirect(_security.post_register_view or
                        _security.post_login_view)

    return redirect(request.referrer or
                    _security.register_url)


def confirm():
    """View function which confirms a user's email address using a token taken
    from the value of the `confirmation_token` query string argument.
    """

    try:
        token = request.args.get('confirmation_token', None)
        user = confirm_by_token(token)

    except ConfirmationError, e:
        do_flash(str(e), 'error')
        return redirect('/')  # TODO: Don't just redirect to root

    except TokenExpiredError, e:
        reset_confirmation_token(e.user)

        msg = 'You did not confirm your email within %s. ' \
              'A new confirmation code has been sent to %s' % (
               _security.confirm_email_within_text, e.user.email)

        do_flash(msg, 'error')
        return redirect('/')  # TODO: Don't redirect to root

    _logger.debug('User %s confirmed' % user)
    do_flash('Your email has been confirmed. You may now log in.', 'success')

    return redirect(_security.post_confirm_view or
                    _security.post_login_view)


def forgot():
    """View function that handles the generation of a password reset token.
    """

    form = _security.ForgotPasswordForm(csrf_enabled=not app.testing)

    if form.validate_on_submit():
        try:
            user = _datastore.find_user(**form.to_dict())

            reset_password_reset_token(user)

            do_flash('Instructions to reset your password have been '
                     'sent to %s' % user.email, 'success')

        except UserNotFoundError:
            do_flash('The email you provided could not be found', 'error')

        return redirect(_security.post_forgot_view)

    return render_template('security/passwords/new.html',
                           forgot_password_form=form)


def reset():
    """View function that handles the reset of a user's password.
    """

    form = _security.ResetPasswordForm(csrf_enabled=not app.testing)

    if form.validate_on_submit():
        try:
            reset_by_token(**form.to_dict())

        except ResetPasswordError, e:
            do_flash(str(e), 'error')

        except TokenExpiredError, e:
            do_flash('You did not reset your password within'
                     '%s.' % _security.reset_password_within_text)

    return redirect(request.referrer or
                    _security.reset_password_error_view)
