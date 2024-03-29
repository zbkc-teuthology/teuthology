from setuptools import setup, find_packages
import re

module_file = open("teuthology/__init__.py").read()
metadata = dict(re.findall(r"__([a-z]+)__\s*=\s*['\"]([^'\"]*)['\"]", module_file))
long_description = open('README.rst').read()

setup(
    name='teuthology',
    version=metadata['version'],
    packages=find_packages(),
    package_data={
     'teuthology.task': ['valgrind.supp', 'adjust-ulimits', 'edit_sudoers.sh', 'daemon-helper'],
     'teuthology.task': ['valgrind.supp', 'adjust-ulimits', 'edit_sudoers.sh', 'daemon-helper'],
     'teuthology.openstack': [
         'archive-key',
         'archive-key.pub',
         'openstack-centos-6.5-user-data.txt',
         'openstack-centos-7.0-user-data.txt',
         'openstack-centos-7.1-user-data.txt',
         'openstack-centos-7.2-user-data.txt',
         'openstack-debian-8.0-user-data.txt',
         'openstack-opensuse-42.1-user-data.txt',
         'openstack-teuthology.cron',
         'openstack-teuthology.init',
         'openstack-ubuntu-12.04-user-data.txt',
         'openstack-ubuntu-14.04-user-data.txt',
         'openstack-user-data.txt',
         'openstack.yaml',
         'setup-openstack.sh'
     ],
    },
    author='Zbkc Storage, Inc.',
    author_email='zbkc-qa@zbkc.com',
    description='Zbkc test framework',
    license='MIT',
    keywords='teuthology test zbkc cluster',
    url='https://github.com/zbkc/teuthology',
    long_description=long_description,
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Quality Assurance',
        'Topic :: Software Development :: Testing',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Filesystems',
    ],
    install_requires=['setuptools',
                      'gevent',
                      # For teuthology-coverage
                      'MySQL-python == 1.2.3',
                      'PyYAML',
                      'argparse >= 1.2.1',
                      'beanstalkc >= 0.2.0',
                      'boto >= 2.0b4',
                      'bunch >= 1.0.0',
                      'configobj',
                      'six >= 1.9', # python-openstackclient won't work properly with less
                      'httplib2',
                      'paramiko',
                      'pexpect',
                      'requests != 2.13.0',
                      'raven',
                      'web.py',
                      'docopt',
                      'psutil >= 2.1.0',
                      'configparser',
                      'pytest',
                      'pytest-capturelog',
                      'mock',
                      'fudge',
                      'ansible>=2.0',
                      'pyopenssl>=0.13',
                      'ndg-httpsclient',
                      'pyasn1',
                      # python-novaclient is specified here, even though it is
                      # redundant, because python-openstackclient requires
                      # Babel, and installs 2.3.3, which is forbidden by
                      # python-novaclient 4.0.0
                      'python-novaclient',
                      'python-openstackclient',
                      # Copy the below from python-openstackclient's
                      # requirements to avoid a conflict
                      'openstacksdk!=0.9.11,!=0.9.12,>=0.9.10',
                      # with openstacklient >= 2.1.0, neutronclient no longer is
                      # a dependency but we need it anyway.
                      'python-neutronclient',
                      'prettytable',
                      'libvirt-python',
                      'python-dateutil',
                      'manhole',
                      'apache-libcloud',
                      # For apache-libcloud when using python < 2.7.9
                      'backports.ssl_match_hostname',
                      ],


    # to find the code associated with entry point
    # A.B:foo first cd into directory A, open file B
    # and find sub foo
    entry_points={
        'console_scripts': [
            'teuthology = scripts.run:main',
            'teuthology-openstack = scripts.openstack:main',
            'teuthology-nuke = scripts.nuke:main',
            'teuthology-suite = scripts.suite:main',
            'teuthology-ls = scripts.ls:main',
            'teuthology-worker = scripts.worker:main',
            'teuthology-lock = scripts.lock:main',
            'teuthology-schedule = scripts.schedule:main',
            'teuthology-updatekeys = scripts.updatekeys:main',
            'teuthology-update-inventory = scripts.update_inventory:main',
            'teuthology-coverage = scripts.coverage:main',
            'teuthology-results = scripts.results:main',
            'teuthology-report = scripts.report:main',
            'teuthology-kill = scripts.kill:main',
            'teuthology-queue = scripts.queue:main',
            'teuthology-prune-logs = scripts.prune_logs:main',
            'teuthology-describe-tests = scripts.describe_tests:main',
            ],
        },

    )
