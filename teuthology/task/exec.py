"""
Exececute custom commands
"""
import logging

from teuthology import misc as teuthology

log = logging.getLogger(__name__)

def task(ctx, config):
    """
    Execute commands on a given role

        tasks:
        - zbkc:
        - kclient: [client.a]
        - exec:
            client.a:
              - "echo 'module libzbkc +p' > /sys/kernel/debug/dynamic_debug/control"
              - "echo 'module zbkc +p' > /sys/kernel/debug/dynamic_debug/control"
        - interactive:

    It stops and fails with the first command that does not return on success. It means
    that if the first command fails, the second won't run at all.

    To avoid confusion it is recommended to explicitly enclose the commands in 
    double quotes. For instance if the command is false (without double quotes) it will
    be interpreted as a boolean by the YAML parser.

    :param ctx: Context
    :param config: Configuration
    """
    log.info('Executing custom commands...')
    assert isinstance(config, dict), "task exec got invalid config"

    testdir = teuthology.get_testdir(ctx)

    if 'all' in config and len(config) == 1:
        a = config['all']
        roles = teuthology.all_roles(ctx.cluster)
        config = dict((id_, a) for id_ in roles)

    for role, ls in config.iteritems():
        (remote,) = ctx.cluster.only(role).remotes.iterkeys()
        log.info('Running commands on role %s host %s', role, remote.name)
        for c in ls:
            c.replace('$TESTDIR', testdir)
            remote.run(
                args=[
                    'sudo',
                    'TESTDIR={tdir}'.format(tdir=testdir),
                    'bash',
                    '-c',
                    c],
                )

