"""A setup tools based setup module.
"""

import setuptools


setuptools.setup(
    name="ser2tcp",
    version="3.0",
    description="Serial proxy to TCP or TELNET",
    long_description=(
        "Python serial port proxy to TCP or TELNET"
        "Project page: https://github.com/pavelrevak/ser2tcp"),
    url="https://github.com/pavelrevak/ser2tcp",
    author="Pavel Revak",
    author_email="pavel.revak@gmail.com",
    license="MIT",
    keywords="serial tcp telnet",

    classifiers=[
        # https://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Embedded Systems',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],

    python_requires='>3.5',

    packages=[
        'ser2tcp',
    ],

    install_requires=[
        'pyserial (>=3.0)'
    ],

    entry_points={
        'console_scripts': [
            'ser2tcp=ser2tcp.main:main',
        ],
    },
    include_package_data=True,
)
