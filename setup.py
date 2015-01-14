import os
import tempfile
from setuptools import setup
from distutils.core import Command

test_requires = ['moto']
try:
    import unittest.mock
except ImportError:
    test_requires.append('mock')


class TestCommand(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        if self.distribution.install_requires:
            self.distribution.fetch_build_eggs(self.distribution.install_requires)
        if self.distribution.tests_require:
            self.distribution.fetch_build_eggs(self.distribution.tests_require)

        from django.conf import settings
        settings.configure(
            DATABASES={
                'default': {
                    'NAME': 'test.db',
                    'TEST_NAME': 'test.db',
                    'ENGINE': 'django.db.backends.sqlite3'
                }
            },
            INSTALLED_APPS = (
                'django.contrib.auth',
                'django.contrib.contenttypes',
                'django.contrib.sessions',
                'django.contrib.staticfiles',
                'bakery',
            ),
            TEMPLATE_DIRS = (
                os.path.abspath(
                     os.path.join(
                         os.path.dirname(__file__),
                         'bakery',
                         'tests',
                         'templates',
                     ),
                ),
            ),
            BUILD_DIR = tempfile.mkdtemp(),
            STATIC_ROOT = os.path.abspath(
                 os.path.join(
                     os.path.dirname(__file__),
                     'bakery',
                     'tests',
                     'static',
                 ),
            ),
            STATIC_URL = '/static/',
            MEDIA_ROOT = os.path.abspath(
                 os.path.join(
                     os.path.dirname(__file__),
                     'bakery',
                     'tests',
                     'media',
                 ),
            ),
            MEDIA_URL = '/media/',
            BAKERY_VIEWS = ('bakery.tests.MockDetailView',),
            # The publish management command needs these to exit, but
            # we're mocking boto, so we can put nonesense in here
            AWS_ACCESS_KEY_ID = 'MOCK_ACCESS_KEY_ID',
            AWS_SECRET_ACCESS_KEY = 'MOCK_SECRET_ACCESS_KEY',
        )
        from django.core.management import call_command
        import django
        if django.VERSION[:2] >= (1, 7):
            django.setup()
        call_command('test', 'bakery')


setup(
    name='django-bakery',
    version='0.7.2',
    description='A set of helpers for baking your Django site out as flat files',
    author='The Los Angeles Times Data Desk',
    author_email='datadesk@latimes.com',
    url='http://www.github.com/datadesk/django-bakery/',
    packages=(
        'bakery',
        'bakery.management',
        'bakery.management.commands',
        'bakery.tests',
        'bakery.tests.static',
        'bakery.tests.media',
        'bakery.tests.templates',
    ),
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    install_requires=[
        'six>=1.5.2',
        'boto>=2.28',
    ],
    tests_require=test_requires,
    cmdclass={'test': TestCommand}
)
