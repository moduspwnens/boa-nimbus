#!/usr/bin/env python
import sys

from setuptools import setup, find_packages

requires = [
    "boto3==1.4.1",
    "botocore==1.4.67",
    "docutils==0.12",
    "futures==3.0.5",
    "jmespath==0.9.0",
    "python-dateutil==2.5.3",
    "s3transfer==0.1.9",
    "six==1.10.0"
]

setup_options = dict(
    name='boa-nimbus',
    version='0.0.1',
    description='boa-nimbus CLI',
    long_description=open('README.md').read(),
    author='Benn Linger',
    url='https://github.com/moduspwnens/boa-nimbus',
    packages=find_packages(exclude=['tests*']),
    install_requires=requires,
    include_package_data=True,
    entry_points = '''
        [console_scripts]
        boa-nimbus=boa_nimbus.cli:main
    ''',
    classifiers=(
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
    ),
)

setup(**setup_options)