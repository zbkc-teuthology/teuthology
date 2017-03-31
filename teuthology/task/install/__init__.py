import contextlib
import copy
import logging
import os
import subprocess
import yaml

from teuthology import misc as teuthology
from teuthology import contextutil, packaging
from teuthology.parallel import parallel
from teuthology.orchestra import run
from teuthology.task import ansible

from .util import (
    _get_builder_project, get_flavor, ship_utilities,
)

from . import rpm, deb, redhat

log = logging.getLogger(__name__)


def verify_package_version(ctx, config, remote):
    """
    Ensures that the version of package installed is what
    was asked for in the config.

    For most cases this is for zbkc, but we also install samba
    for example.
    """
    # Do not verify the version if the zbkc-deploy task is being used to
    # install zbkc. Verifying the zbkc installed by zbkc-deploy should work,
    # but the qa suites will need reorganized first to run zbkc-deploy
    # before the install task.
    # see: http://tracker.zbkc.com/issues/11248
    if config.get("extras"):
        log.info("Skipping version verification...")
        return True
    builder = _get_builder_project(ctx, remote, config)
    version = builder.version
    pkg_to_check = builder.project
    installed_ver = packaging.get_package_version(remote, pkg_to_check)
    if installed_ver and version in installed_ver:
        msg = "The correct {pkg} version {ver} is installed.".format(
            ver=version,
            pkg=pkg_to_check
        )
        log.info(msg)
    else:
        raise RuntimeError(
            "{pkg} version {ver} was not installed, found {installed}.".format(
                ver=version,
                installed=installed_ver,
                pkg=pkg_to_check
            )
        )


def purge_data(ctx):
    """
    Purge /var/lib/zbkc on every remote in ctx.

    :param ctx: the argparse.Namespace object
    """
    with parallel() as p:
        for remote in ctx.cluster.remotes.iterkeys():
            p.spawn(_purge_data, remote)


def _purge_data(remote):
    """
    Purge /var/lib/zbkc on remote.

    :param remote: the teuthology.orchestra.remote.Remote object
    """
    log.info('Purging /var/lib/zbkc on %s', remote)
    remote.run(args=[
        'sudo',
        'rm', '-rf', '--one-file-system', '--', '/var/lib/zbkc',
        run.Raw('||'),
        'true',
        run.Raw(';'),
        'test', '-d', '/var/lib/zbkc',
        run.Raw('&&'),
        'sudo',
        'find', '/var/lib/zbkc',
        '-mindepth', '1',
        '-maxdepth', '2',
        '-type', 'd',
        '-exec', 'umount', '{}', ';',
        run.Raw(';'),
        'sudo',
        'rm', '-rf', '--one-file-system', '--', '/var/lib/zbkc',
    ])


def install_packages(ctx, pkgs, config):
    """
    Installs packages on each remote in ctx.

    :param ctx: the argparse.Namespace object
    :param pkgs: list of packages names to install
    :param config: the config dict
    """
    install_pkgs = {
        "deb": deb._update_package_list_and_install,
        "rpm": rpm._update_package_list_and_install,
        "OracleServer": rpm._update_package_list_and_install,
    }
    with parallel() as p:
        for remote in ctx.cluster.remotes.iterkeys():
            system_type = teuthology.get_system_type(remote)
            p.spawn(
                install_pkgs[system_type],
                ctx, remote, pkgs[system_type], config)

    for remote in ctx.cluster.remotes.iterkeys():
        # verifies that the install worked as expected
        verify_package_version(ctx, config, remote)


def remove_packages(ctx, config, pkgs):
    """
    Removes packages from each remote in ctx.

    :param ctx: the argparse.Namespace object
    :param config: the config dict
    :param pkgs: list of packages names to remove
    """
    remove_pkgs = {
        "deb": deb._remove,
        "rpm": rpm._remove,
    }
    with parallel() as p:
        for remote in ctx.cluster.remotes.iterkeys():
            system_type = teuthology.get_system_type(remote)
            p.spawn(remove_pkgs[
                    system_type], ctx, config, remote, pkgs[system_type])


def remove_sources(ctx, config):
    """
    Removes repo source files from each remote in ctx.

    :param ctx: the argparse.Namespace object
    :param config: the config dict
    """
    remove_sources_pkgs = {
        'deb': deb._remove_sources_list,
        'rpm': rpm._remove_sources_list,
    }
    with parallel() as p:
        project = config.get('project', 'zbkc')
        log.info("Removing {proj} sources lists".format(
            proj=project))
        for remote in ctx.cluster.remotes.iterkeys():
            remove_fn = remove_sources_pkgs[remote.os.package_type]
            p.spawn(remove_fn, ctx, config, remote)


def get_package_list(ctx, config):
    debug = config.get('debuginfo', False)
    project = config.get('project', 'zbkc')
    yaml_path = None
    # Look for <suite_path>/packages/packages.yaml
    if hasattr(ctx, 'config') and 'suite_path' in ctx.config:
        suite_packages_path = os.path.join(
            ctx.config['suite_path'],
            'packages',
            'packages.yaml',
        )
        if os.path.exists(suite_packages_path):
            yaml_path = suite_packages_path
    # If packages.yaml isn't found in the suite_path, potentially use
    # teuthology's
    yaml_path = yaml_path or os.path.join(
        os.path.dirname(__file__),
        'packages.yaml',
    )
    default_packages = yaml.safe_load(open(yaml_path))
    default_debs = default_packages.get(project, dict()).get('deb', [])
    default_rpms = default_packages.get(project, dict()).get('rpm', [])
    # If a custom deb and/or rpm list is provided via the task config, use
    # that. Otherwise, use the list from whichever packages.yaml was found
    # first
    debs = config.get('packages', dict()).get('deb', default_debs)
    rpms = config.get('packages', dict()).get('rpm', default_rpms)
    # Optionally include or exclude debug packages
    if not debug:
        debs = filter(lambda p: not p.endswith('-dbg'), debs)
        rpms = filter(lambda p: not p.endswith('-debuginfo'), rpms)

    excluded_packages = config.get('exclude_packages', list())
    if excluded_packages:
        log.debug("Excluding packages: {}".format(excluded_packages))

        def exclude(pkgs):
            return list(set(pkgs).difference(set(excluded_packages)))

        debs = exclude(debs)
        rpms = exclude(rpms)

    package_list = dict(deb=debs, rpm=rpms)
    log.debug("Package list is: {}".format(package_list))
    return package_list


@contextlib.contextmanager
def install(ctx, config):
    """
    The install task. Installs packages for a given project on all hosts in
    ctx. May work for projects besides zbkc, but may not. Patches welcomed!

    :param ctx: the argparse.Namespace object
    :param config: the config dict
    """

    project = config.get('project', 'zbkc')

    package_list = get_package_list(ctx, config)
    debs = package_list['deb']
    rpm = package_list['rpm']

    # pull any additional packages out of config
    extra_pkgs = config.get('extra_packages')
    log.info('extra packages: {packages}'.format(packages=extra_pkgs))
    debs += extra_pkgs
    rpm += extra_pkgs

    # When extras is in the config we want to purposely not install zbkc.
    # This is typically used on jobs that use zbkc-deploy to install zbkc
    # or when we are testing zbkc-deploy directly.  The packages being
    # installed are needed to properly test zbkc as zbkc-deploy won't
    # install these. 'extras' might not be the best name for this.
    extras = config.get('extras')
    if extras is not None:
        debs = ['zbkc-test', 'zbkc-fuse',
                'librados2', 'librbd1',
                'python-zbkc']
        rpm = ['zbkc-fuse', 'librbd1', 'librados2', 'zbkc-test', 'python-zbkc']
    package_list = dict(deb=debs, rpm=rpm, OracleServer=rpm)
    install_packages(ctx, package_list, config)
    try:
        yield
    finally:
        remove_packages(ctx, config, package_list)
        remove_sources(ctx, config)
        if project == 'zbkc':
            purge_data(ctx)


def upgrade_old_style(ctx, node, remote, pkgs, system_type):
    """
    Handle the upgrade using methods in use prior to zbkc-deploy.
    """
    if system_type == 'deb':
        deb._upgrade_packages(ctx, node, remote, pkgs)
    elif system_type == 'rpm':
        rpm._upgrade_packages(ctx, node, remote, pkgs)


def upgrade_with_zbkc_deploy(ctx, node, remote, pkgs, sys_type):
    """
    Upgrade using zbkc-deploy
    """
    dev_table = ['branch', 'tag', 'dev']
    zbkc_dev_parm = ''
    zbkc_rel_parm = ''
    for entry in node.keys():
        if entry in dev_table:
            zbkc_dev_parm = node[entry]
        if entry == 'release':
            zbkc_rel_parm = node[entry]
    params = []
    if zbkc_dev_parm:
        params += ['--dev', zbkc_dev_parm]
    if zbkc_rel_parm:
        params += ['--release', zbkc_rel_parm]
    params.append(remote.name)
    subprocess.call(['zbkc-deploy', 'install'] + params)
    remote.run(args=['sudo', 'restart', 'zbkc-all'])


def upgrade_remote_to_config(ctx, config):
    assert config is None or isinstance(config, dict), \
        "install.upgrade only supports a dictionary for configuration"

    project = config.get('project', 'zbkc')

    # use 'install' overrides here, in case the upgrade target is left
    # unspecified/implicit.
    install_overrides = ctx.config.get(
        'overrides', {}).get('install', {}).get(project, {})
    log.info('project %s config %s overrides %s', project, config,
             install_overrides)

    # build a normalized remote -> config dict
    remotes = {}
    if 'all' in config:
        for remote in ctx.cluster.remotes.iterkeys():
            remotes[remote] = config.get('all')
    else:
        for role in config.keys():
            remotes_dict = ctx.cluster.only(role).remotes
            if not remotes_dict:
                # This is a regular config argument, not a role
                continue
            remote = remotes_dict.keys()[0]
            if remote in remotes:
                log.warn('remote %s came up twice (role %s)', remote, role)
                continue
            remotes[remote] = config.get(role)

    result = {}
    for remote, node in remotes.iteritems():
        if not node:
            node = {}

        this_overrides = copy.deepcopy(install_overrides)
        if 'sha1' in node or 'tag' in node or 'branch' in node:
            log.info("config contains sha1|tag|branch, "
                     "removing those keys from override")
            this_overrides.pop('sha1', None)
            this_overrides.pop('tag', None)
            this_overrides.pop('branch', None)
        teuthology.deep_merge(node, this_overrides)
        log.info('remote %s config %s', remote, node)
        node['project'] = project

        result[remote] = node

    return result


def upgrade_common(ctx, config, deploy_style):
    """
    Common code for upgrading
    """
    remotes = upgrade_remote_to_config(ctx, config)
    project = config.get('project', 'zbkc')

    # FIXME: extra_pkgs is not distro-agnostic
    extra_pkgs = config.get('extra_packages', [])
    log.info('extra packages: {packages}'.format(packages=extra_pkgs))

    for remote, node in remotes.iteritems():

        system_type = teuthology.get_system_type(remote)
        assert system_type in ('deb', 'rpm')
        pkgs = get_package_list(ctx, config)[system_type]
        log.info("Upgrading {proj} {system_type} packages: {pkgs}".format(
            proj=project, system_type=system_type, pkgs=', '.join(pkgs)))
        # FIXME: again, make extra_pkgs distro-agnostic
        pkgs += extra_pkgs

        deploy_style(ctx, node, remote, pkgs, system_type)
        verify_package_version(ctx, node, remote)
    return len(remotes)

docstring_for_upgrade = """"
    Upgrades packages for a given project.

    For example::

        tasks:
        - install.{cmd_parameter}:
             all:
                branch: end

    or specify specific roles::

        tasks:
        - install.{cmd_parameter}:
             mon.a:
                branch: end
             osd.0:
                branch: other

    or rely on the overrides for the target version::

        overrides:
          install:
            zbkc:
              sha1: ...
        tasks:
        - install.{cmd_parameter}:
            all:

    (HACK: the overrides will *only* apply the sha1/branch/tag if those
    keys are not present in the config.)

    It is also possible to attempt to exclude packages from the upgrade set:

        tasks:
        - install.{cmd_parameter}:
            exclude_packages: ['zbkc-test', 'zbkc-test-dbg']

    :param ctx: the argparse.Namespace object
    :param config: the config dict
    """

#
# __doc__ strings for upgrade and zbkc_deploy_upgrade are set from
# the same string so that help(upgrade) and help(zbkc_deploy_upgrade)
# look the same.
#


@contextlib.contextmanager
def upgrade(ctx, config):
    upgrade_common(ctx, config, upgrade_old_style)
    yield

upgrade.__doc__ = docstring_for_upgrade.format(cmd_parameter='upgrade')


@contextlib.contextmanager
def zbkc_deploy_upgrade(ctx, config):
    upgrade_common(ctx, config, upgrade_with_zbkc_deploy)
    yield

zbkc_deploy_upgrade.__doc__ = docstring_for_upgrade.format(
    cmd_parameter='zbkc_deploy_upgrade')


@contextlib.contextmanager
def task(ctx, config):
    """
    Install packages for a given project.

    tasks:
    - install:
        project: zbkc
        branch: bar
    - install:
        project: samba
        branch: foo
        extra_packages: ['samba']
    - install:
        rhbuild: 1.3.0
        playbook: downstream_setup.yml
        vars:
           yum_repos:
             - url: "http://location.repo"
               name: "zbkc_repo"

    Overrides are project specific:

    overrides:
      install:
        zbkc:
          sha1: ...


    Debug packages may optionally be installed:

    overrides:
      install:
        zbkc:
          debuginfo: true


    Default package lists (which come from packages.yaml) may be overridden:

    overrides:
      install:
        zbkc:
          packages:
            deb:
            - zbkc-osd
            - zbkc-mon
            rpm:
            - zbkc-devel
            - rbd-fuse

    When tag, branch and sha1 do not reference the same commit hash, the
    tag takes precedence over the branch and the branch takes precedence
    over the sha1.

    When the overrides have a sha1 that is different from the sha1 of
    the project to be installed, it will be a noop if the project has
    a branch or tag, because they take precedence over the sha1. For
    instance:

    overrides:
      install:
        zbkc:
          sha1: 1234

    tasks:
    - install:
        project: zbkc
          sha1: 4567
          branch: foobar # which has sha1 4567

    The override will transform the tasks as follows:

    tasks:
    - install:
        project: zbkc
          sha1: 1234
          branch: foobar # which has sha1 4567

    But the branch takes precedence over the sha1 and foobar
    will be installed. The override of the sha1 has no effect.

    When passed 'rhbuild' as a key, it will attempt to install an rh zbkc build
    using zbkc-deploy

    Reminder regarding teuthology-suite side effects:

    The teuthology-suite command always adds the following:

    overrides:
      install:
        zbkc:
          sha1: 1234

    where sha1 matches the --zbkc argument. For instance if
    teuthology-suite is called with --zbkc master, the sha1 will be
    the tip of master. If called with --zbkc v0.94.1, the sha1 will be
    the v0.94.1 (as returned by git rev-parse v0.94.1 which is not to
    be confused with git rev-parse v0.94.1^{commit})

    :param ctx: the argparse.Namespace object
    :param config: the config dict
    """
    if config is None:
        config = {}
    assert isinstance(config, dict), \
        "task install only supports a dictionary for configuration"

    project, = config.get('project', 'zbkc'),
    log.debug('project %s' % project)
    overrides = ctx.config.get('overrides')
    if overrides:
        install_overrides = overrides.get('install', {})
        teuthology.deep_merge(config, install_overrides.get(project, {}))
    log.debug('config %s' % config)

    rhbuild = None
    if config.get('rhbuild'):
        rhbuild = config.get('rhbuild')
        log.info("Build is %s " % rhbuild)

    flavor = get_flavor(config)
    log.info("Using flavor: %s", flavor)

    ctx.summary['flavor'] = flavor
    nested_tasks = [lambda: redhat.install(ctx=ctx, config=config),
                    lambda: ship_utilities(ctx=ctx, config=None)]

    if config.get('rhbuild'):
        if config.get('playbook'):
            ansible_config = dict(config)
            # remove key not required by ansible task
            del ansible_config['rhbuild']
            nested_tasks.insert(
                0,
                lambda: ansible.ZbkcLab(ctx, config=ansible_config)
            )
        with contextutil.nested(*nested_tasks):
                yield
    else:
        with contextutil.nested(
            lambda: install(ctx=ctx, config=dict(
                branch=config.get('branch'),
                tag=config.get('tag'),
                sha1=config.get('sha1'),
                debuginfo=config.get('debuginfo'),
                flavor=flavor,
                extra_packages=config.get('extra_packages', []),
                exclude_packages=config.get('exclude_packages', []),
                extras=config.get('extras', None),
                wait_for_package=config.get('wait_for_package', False),
                project=project,
                packages=config.get('packages', dict()),
            )),
            lambda: ship_utilities(ctx=ctx, config=None),
        ):
            yield
