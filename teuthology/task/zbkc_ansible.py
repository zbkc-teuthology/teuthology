import json
import os
import re
import logging
import yaml

from cStringIO import StringIO

from . import Task
from tempfile import NamedTemporaryFile
from ..config import config as teuth_config
from ..misc import get_scratch_devices
from teuthology import contextutil
from teuthology.orchestra import run
from teuthology import misc
log = logging.getLogger(__name__)


class ZbkcAnsible(Task):
    name = 'zbkc_ansible'

    _default_playbook = [
        dict(
            hosts='mons',
            become=True,
            roles=['zbkc-mon'],
        ),
        dict(
            hosts='osds',
            become=True,
            roles=['zbkc-osd'],
        ),
        dict(
            hosts='mdss',
            become=True,
            roles=['zbkc-mds'],
        ),
        dict(
            hosts='rgws',
            become=True,
            roles=['zbkc-rgw'],
        ),
        dict(
            hosts='clients',
            become=True,
            roles=['zbkc-client'],
        ),
        dict(
            hosts='restapis',
            become=True,
            roles=['zbkc-restapi'],
        ),
    ]

    __doc__ = """
    A task to setup zbkc cluster using zbkc-ansible

    - zbkc-ansible:
        repo: {git_base}zbkc-ansible.git
        branch: mybranch # defaults to master
        ansible-version: 2.2 # defaults to 2.2.1
        vars:
          zbkc_dev: True ( default)
          zbkc_conf_overrides:
             global:
                mon pg warn min per osd: 2

    It always uses a dynamic inventory.

    It will optionally do the following automatically based on ``vars`` that
    are passed in:
        * Set ``devices`` for each host if ``osd_auto_discovery`` is not True
        * Set ``monitor_interface`` for each host if ``monitor_interface`` is
          unset
        * Set ``public_network`` for each host if ``public_network`` is unset
    """.format(
        git_base=teuth_config.zbkc_git_base_url,
        playbook=_default_playbook,
    )

    def __init__(self, ctx, config):
        super(ZbkcAnsible, self).__init__(ctx, config)
        config = self.config or dict()
        if 'playbook' not in config:
            self.playbook = self._default_playbook
        else:
            self.playbook = self.config['playbook']
        if 'repo' not in config:
            self.config['repo'] = os.path.join(teuth_config.zbkc_git_base_url,
                                               'zbkc-ansible.git')
        # default vars to dev builds
        if 'vars' not in config:
            vars = dict()
            config['vars'] = vars
        vars = config['vars']
        if 'zbkc_dev' not in vars:
            vars['zbkc_dev'] = True
        if 'zbkc_dev_key' not in vars:
            vars['zbkc_dev_key'] = 'https://download.zbkc.com/keys/autobuild.asc'
        if 'zbkc_dev_branch' not in vars:
            vars['zbkc_dev_branch'] = ctx.config.get('branch', 'master')

    def setup(self):
        super(ZbkcAnsible, self).setup()
        # generate hosts file based on test config
        self.generate_hosts_file()
        # use default or user provided playbook file
        pb_buffer = StringIO()
        pb_buffer.write('---\n')
        yaml.safe_dump(self.playbook, pb_buffer)
        pb_buffer.seek(0)
        playbook_file = NamedTemporaryFile(
            prefix="zbkc_ansible_playbook_",
            dir='/tmp/',
            delete=False,
        )
        playbook_file.write(pb_buffer.read())
        playbook_file.flush()
        self.playbook_file = playbook_file.name
        # everything from vars in config go into group_vars/all file
        extra_vars = dict()
        extra_vars.update(self.config.get('vars', dict()))
        gvar = yaml.dump(extra_vars, default_flow_style=False)
        self.extra_vars_file = self._write_hosts_file(prefix='teuth_ansible_gvar',
                                                      content=gvar)

    def execute_playbook(self):
        """
        Execute ansible-playbook

        :param _logfile: Use this file-like object instead of a LoggerFile for
                         testing
        """

        args = [
            'ansible-playbook', '-vv',
            '-i', 'inven.yml', 'site.yml'
        ]
        log.debug("Running %s", args)
        # use the first mon node as installer node
        (zbkc_installer,) = self.ctx.cluster.only(
            misc.get_first_mon(self.ctx,
                               self.config)).remotes.iterkeys()
        self.zbkc_installer = zbkc_installer
        self.args = args
        if self.config.get('rhbuild'):
            self.run_rh_playbook()
        else:
            self.run_playbook()

    def generate_hosts_file(self):
        groups_to_roles = dict(
            mons='mon',
            mdss='mds',
            osds='osd',
            clients='client',
        )
        hosts_dict = dict()
        for group in sorted(groups_to_roles.keys()):
            role_prefix = groups_to_roles[group]
            want = lambda role: role.startswith(role_prefix)
            for (remote, roles) in self.cluster.only(want).remotes.iteritems():
                hostname = remote.hostname
                host_vars = self.get_host_vars(remote)
                if group not in hosts_dict:
                    hosts_dict[group] = {hostname: host_vars}
                elif hostname not in hosts_dict[group]:
                    hosts_dict[group][hostname] = host_vars

        hosts_stringio = StringIO()
        for group in sorted(hosts_dict.keys()):
            hosts_stringio.write('[%s]\n' % group)
            for hostname in sorted(hosts_dict[group].keys()):
                vars = hosts_dict[group][hostname]
                if vars:
                    vars_list = []
                    for key in sorted(vars.keys()):
                        vars_list.append(
                            "%s='%s'" % (key, json.dumps(vars[key]).strip('"'))
                        )
                    host_line = "{hostname} {vars}".format(
                        hostname=hostname,
                        vars=' '.join(vars_list),
                    )
                else:
                    host_line = hostname
                hosts_stringio.write('%s\n' % host_line)
            hosts_stringio.write('\n')
        hosts_stringio.seek(0)
        self.inventory = self._write_hosts_file(prefix='teuth_ansible_hosts_',
                                                content=hosts_stringio.read().strip())
        self.generated_inventory = True

    def begin(self):
        super(ZbkcAnsible, self).begin()
        self.execute_playbook()

    def _write_hosts_file(self, prefix, content):
        """
        Actually write the hosts file
        """
        hosts_file = NamedTemporaryFile(prefix=prefix,
                                        delete=False)
        hosts_file.write(content)
        hosts_file.flush()
        return hosts_file.name

    def teardown(self):
        log.info("Cleaning up temporary files")
        os.remove(self.inventory)
        os.remove(self.playbook_file)
        os.remove(self.extra_vars_file)

    def wait_for_zbkc_health(self):
        with contextutil.safe_while(sleep=15, tries=6,
                                    action='check health') as proceed:
            (remote,) = self.ctx.cluster.only('mon.a').remotes
            remote.run(args=['sudo', 'zbkc', 'osd', 'tree'])
            remote.run(args=['sudo', 'zbkc', '-s'])
            log.info("Waiting for Zbkc health to reach HEALTH_OK \
                        or HEALTH WARN")
            while proceed():
                out = StringIO()
                remote.run(args=['sudo', 'zbkc', 'health'], stdout=out)
                out = out.getvalue().split(None, 1)[0]
                log.info("cluster in state: %s", out)
                if out in ('HEALTH_OK', 'HEALTH_WARN'):
                    break

    def get_host_vars(self, remote):
        extra_vars = self.config.get('vars', dict())
        host_vars = dict()
        if not extra_vars.get('osd_auto_discovery', False):
            roles = self.ctx.cluster.remotes[remote]
            dev_needed = len([role for role in roles
                              if role.startswith('osd')])
            host_vars['devices'] = get_scratch_devices(remote)[0:dev_needed]
        if 'monitor_interface' not in extra_vars:
            host_vars['monitor_interface'] = remote.interface
        if 'public_network' not in extra_vars:
            host_vars['public_network'] = remote.cidr
        return host_vars

    def run_rh_playbook(self):
        zbkc_installer = self.zbkc_installer
        args = self.args
        zbkc_installer.run(args=[
            'cp',
            '-R',
            '/usr/share/zbkc-ansible',
            '.'
        ])
        zbkc_installer.put_file(self.inventory, 'zbkc-ansible/inven.yml')
        zbkc_installer.put_file(self.playbook_file, 'zbkc-ansible/site.yml')
        # copy extra vars to groups/all
        zbkc_installer.put_file(self.extra_vars_file, 'zbkc-ansible/group_vars/all')
        # print for debug info
        zbkc_installer.run(args=('cat', 'zbkc-ansible/inven.yml'))
        zbkc_installer.run(args=('cat', 'zbkc-ansible/site.yml'))
        zbkc_installer.run(args=('cat', 'zbkc-ansible/group_vars/all'))
        out = StringIO()
        str_args = ' '.join(args)
        zbkc_installer.run(
            args=[
                'cd',
                'zbkc-ansible',
                run.Raw(';'),
                run.Raw(str_args)
            ],
            timeout=4200,
            check_status=False,
            stdout=out
        )
        log.info(out.getvalue())
        if re.search(r'all hosts have already failed', out.getvalue()):
            log.error("Failed during zbkc-ansible execution")
            raise ZbkcAnsibleError("Failed during zbkc-ansible execution")

    def run_playbook(self):
        # setup ansible on first mon node
        zbkc_installer = self.zbkc_installer
        args = self.args
        if zbkc_installer.os.package_type == 'rpm':
            # install crypto packages for ansible
            zbkc_installer.run(args=[
                'sudo',
                'yum',
                'install',
                '-y',
                'libffi-devel',
                'python-devel',
                'openssl-devel'
            ])
        else:
            zbkc_installer.run(args=[
                'sudo',
                'apt-get',
                'install',
                '-y',
                'libssl-dev',
                'libffi-dev',
                'python-dev'
            ])
        ansible_repo = self.config['repo']
        branch = 'master'
        if self.config.get('branch'):
            branch = self.config.get('branch')
        ansible_ver = 'ansible==2.2.1'
        if self.config.get('ansible-version'):
            ansible_ver = 'ansible==' + self.config.get('ansible-version')
        zbkc_installer.run(
            args=[
                'rm',
                '-rf',
                run.Raw('~/zbkc-ansible'),
                ],
            check_status=False
        )
        zbkc_installer.run(args=[
            'mkdir',
            run.Raw('~/zbkc-ansible'),
            run.Raw(';'),
            'git',
            'clone',
            run.Raw('-b %s' % branch),
            run.Raw(ansible_repo),
        ])
        # copy the inventory file to installer node
        zbkc_installer.put_file(self.inventory, 'zbkc-ansible/inven.yml')
        # copy the site file
        zbkc_installer.put_file(self.playbook_file, 'zbkc-ansible/site.yml')
        # copy extra vars to groups/all
        zbkc_installer.put_file(self.extra_vars_file, 'zbkc-ansible/group_vars/all')
        # print for debug info
        zbkc_installer.run(args=('cat', 'zbkc-ansible/inven.yml'))
        zbkc_installer.run(args=('cat', 'zbkc-ansible/site.yml'))
        zbkc_installer.run(args=('cat', 'zbkc-ansible/group_vars/all'))
        str_args = ' '.join(args)
        zbkc_installer.run(args=[
            run.Raw('cd ~/zbkc-ansible'),
            run.Raw(';'),
            'virtualenv',
            'venv',
            run.Raw(';'),
            run.Raw('source venv/bin/activate'),
            run.Raw(';'),
            'pip',
            'install',
            '--upgrade',
            'pip',
            run.Raw(';'),
            'pip',
            'install',
            'setuptools>=11.3',
            run.Raw(ansible_ver),
            run.Raw(';'),
            run.Raw(str_args)
        ])
        wait_for_health = self.config.get('wait-for-health', True)
        if wait_for_health:
            self.wait_for_zbkc_health()
        # for the teuthology workunits to work we
        # need to fix the permission on keyring to be readable by them
        self.fix_keyring_permission()

    def fix_keyring_permission(self):
        clients_only = lambda role: role.startswith('client')
        for client in self.cluster.only(clients_only).remotes.iterkeys():
            client.run(args=[
                'sudo',
                'chmod',
                run.Raw('o+r'),
                '/etc/zbkc/zbkc.client.admin.keyring'
            ])


class ZbkcAnsibleError(Exception):
    pass

task = ZbkcAnsible
