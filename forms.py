from flaskext.uploads import UploadSet
from flaskext.wtf import (
    BooleanField,
    file,
    FileField,
    Form,
    PasswordField,
    RadioField,
    SubmitField,
    TextAreaField,
    TextField,
    ValidationError,
    validators,
)

import models


savefiles = UploadSet('savefiles', ('user','zip'))


class RegistrationForm(Form):
    username = TextField('Username',
                         [validators.Required(),
                          validators.Length(min=3, max=30, message='Username must be %(min)d - %(max)d chars'),
                          validators.Regexp('^[A-Za-z0-9\-_]+$', message='Username may only contain letters, numbers, dashes and underscores')])
    email = TextField('Email',
                      [validators.Required(),
                       validators.Email(),
                       validators.Length(max=255)])
    password = PasswordField('Password',
                             [validators.Required(),
                              validators.EqualTo('password_confirm', message='Passwords did not match')])
    password_confirm = PasswordField('Confirm Password')
    submit = SubmitField('Register')

    def validate_username(form, field):
        user = models.User.query.filter_by(username=field.data).all()
        if user:
            raise ValidationError, 'Username already exists'


class LoginForm(Form):
    username = TextField('Username', [validators.Required()])
    password = PasswordField('Password', [validators.Required()])
    remember = BooleanField('Stay logged in')
    submit = SubmitField('Login')


class UserSettingsForm(Form):
    password = PasswordField('Current Password', [validators.Required()])
    email = TextField('Email',
                      [validators.Required(),
                       validators.Email(),
                       validators.Length(max=255)])
    new_password = PasswordField('New Password',
                                 [validators.Optional(),
                                  validators.EqualTo('new_password_confirm', message='New passwords did not match')])
    new_password_confirm = PasswordField('Confirm New Password')
    submit = SubmitField('Change Settings')


class UploadForm(Form):
    save = FileField('Your save file',
                     [file.FileRequired(),
                      file.FileAllowed(savefiles, 'Only .user files or .zip or .gz compressed uploads allowed')])
    upload_all = RadioField('Upload all?',
                            choices=[(1, 'Upload all solutions'), (0, 'Let me choose which solutions to upload')],
                            default=1, coerce=int)
    submit = SubmitField('Upload')


class SolutionForm(Form):
    description = TextAreaField('Description/Notes',
                                [validators.Optional(),
                                 validators.Length(max=255)])
    youtube = TextField('YouTube Link',
                        [validators.Optional(),
                         validators.Length(max=255),
                         validators.Regexp('^(http://)?(www\.)?youtu\.?be[\./]', message='Not a valid YouTube URL')])
    submit = SubmitField('Update')
