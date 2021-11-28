"""A setup tools based setup module.
"""

import setuptools

APP_NAME = "ser2tcp"
VERSION = "3.0"
AUTHOR = "Pavel Revak"
AUTHOR_EMAIL = "pavel.revak@gmail.com"
DESCRIPTION = "Serial bridge to TCP or TELNET"
URL = "https://github.com/pavelrevak/pyswd"
KEYWORDS = 'serial tcp telnet bridge'


def get_long_description():
    """Return long description from README.md file"""
    import os
    import codecs
    current_dir = os.path.abspath(os.path.dirname(__file__))
    readme_file = os.path.join(current_dir, 'README.md')
    with codecs.open(readme_file, encoding='utf-8') as readme_file:
        long_description = readme_file.read()
    return long_description


setuptools.setup(
    name=APP_NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=get_long_description(),
    url=URL,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    license='MIT',
    keywords=KEYWORDS,

    classifiers=[
        # https://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Embedded Systems',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],

    packages=[
        'ser2tcp',
    ],

    install_requires=[
        'pyserial (>=3.0)'
    ],

    entry_points={
        'console_scripts': [
            '%s=ser2tcp._app:main' % APP_NAME,
        ],
    },
    include_package_data=True,
)
