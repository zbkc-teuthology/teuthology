from contextlib import closing
import logging
import os
import shutil
import subprocess
import MySQLdb
import yaml

import teuthology
from teuthology.config import config

log = logging.getLogger(__name__)

"""
The coverage database can be created in mysql with:

CREATE TABLE `coverage` (
  `run_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `rev` char(40) NOT NULL,
  `test` varchar(255) NOT NULL,
  `suite` varchar(255) NOT NULL,
  `lines` int(10) unsigned NOT NULL,
  `line_cov` float unsigned NOT NULL,
  `functions` int(10) unsigned NOT NULL,
  `function_cov` float unsigned NOT NULL,
  `branches` int(10) unsigned NOT NULL,
  `branch_cov` float unsigned NOT NULL,
  `run_date` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8

"""


def connect_to_db():
    db = MySQLdb.connect(
        host=config.coverage_db_host,
        user=config.coverage_db_user,
        db=config.coverage_db_name,
        passwd=config.coverage_db_password,
    )
    db.autocommit(False)
    return db


def store_coverage(test_coverage, rev, suite):
    with closing(connect_to_db()) as db:
        rows = []
        for test, coverage in test_coverage.iteritems():
            flattened_cov = [item for sublist in coverage for item in sublist]
            rows.append([rev, test, suite] + flattened_cov)
        log.debug('inserting rows into db: %s', str(rows))
        try:
            cursor = db.cursor()
            cursor.executemany(
                'INSERT INTO `coverage`'
                ' (`rev`, `test`, `suite`, `lines`, `line_cov`, `functions`,'
                ' `function_cov`, `branches`, `branch_cov`)'
                ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                rows)
        except Exception:
            log.exception('error updating database')
            db.rollback()
            raise
        else:
            db.commit()
            log.info('added coverage to database')
        finally:
            cursor.close()


def read_coverage(output):
    log.debug('reading coverage from output: %s', output)
    coverage = [None, None, None]
    prefixes = ['  lines......: ', '  functions..: ', '  branches...: ']
    for line in reversed(output.splitlines()):
        for i, prefix in enumerate(prefixes):
            if line.startswith(prefix):
                if '%' in line:
                    cov_num = int(line[line.find('(') + 1:line.find(' of')])
                    cov_percent = float(line[len(prefix):line.find('%')])
                    coverage[i] = (cov_num, cov_percent)
                else:
                    # may have no data for e.g. branches on the initial run
                    coverage[i] = (None, None)
                break
        if None not in coverage:
            break
    return coverage


def main(args):
    if args["--verbose"]:
        teuthology.log.setLevel(logging.DEBUG)

    log = logging.getLogger(__name__)

    log_path = os.path.join(args['<test_dir>'], 'coverage.log')
    teuthology.setup_log_file(log_path)

    try:
        analyze(
            args['<test_dir>'],
            args['--cov-tools-dir'],
            args['--lcov-output'],
            args['--html-output'],
            args['--skip-init']
        )
    except Exception:
        log.exception('error generating coverage')
        raise


def analyze(test_dir, cov_tools_dir, lcov_output, html_output, skip_init):
    tests = [
        f for f in sorted(os.listdir(test_dir))
        if not f.startswith('.')
        and os.path.isdir(os.path.join(test_dir, f))
        and os.path.exists(os.path.join(test_dir, f, 'summary.yaml'))
        and os.path.exists(os.path.join(test_dir, f, 'zbkc-sha1'))]

    test_summaries = {}
    for test in tests:
        summary = {}
        with file(os.path.join(test_dir, test, 'summary.yaml')) as f:
            g = yaml.safe_load_all(f)
            for new in g:
                summary.update(new)

        if summary['flavor'] != 'gcov':
            log.debug('Skipping %s, since it does not include coverage', test)
            continue
        test_summaries[test] = summary

    assert len(test_summaries) > 0

    suite = os.path.basename(test_dir)

    # only run cov-init once.
    # this only works if all tests were run against the same version.
    if not skip_init:
        log.info('initializing coverage data...')
        subprocess.check_call(
            args=[
                os.path.join(cov_tools_dir, 'cov-init.sh'),
                os.path.join(test_dir, tests[0]),
                lcov_output,
                os.path.join(
                    config.zbkc_build_output_dir,
                    '{suite}.tgz'.format(suite=suite),
                ),
            ])
        shutil.copy(
            os.path.join(lcov_output, 'base.lcov'),
            os.path.join(lcov_output, 'total.lcov')
        )

    test_coverage = {}
    for test, summary in test_summaries.iteritems():
        lcov_file = '{name}.lcov'.format(name=test)

        log.info('analyzing coverage for %s', test)
        proc = subprocess.Popen(
            args=[
                os.path.join(cov_tools_dir, 'cov-analyze.sh'),
                '-t', os.path.join(test_dir, test),
                '-d', lcov_output,
                '-o', test,
            ],
            stdout=subprocess.PIPE,
        )
        output, _ = proc.communicate()
        desc = summary.get('description', test)
        test_coverage[desc] = read_coverage(output)

        log.info('adding %s data to total', test)
        proc = subprocess.Popen(
            args=[
                'lcov',
                '-a', os.path.join(lcov_output, lcov_file),
                '-a', os.path.join(lcov_output, 'total.lcov'),
                '-o', os.path.join(lcov_output, 'total_tmp.lcov'),
            ],
            stdout=subprocess.PIPE,
        )
        output, _ = proc.communicate()

        os.rename(
            os.path.join(lcov_output, 'total_tmp.lcov'),
            os.path.join(lcov_output, 'total.lcov')
        )

    coverage = read_coverage(output)
    test_coverage['total for {suite}'.format(suite=suite)] = coverage
    log.debug('total coverage is %s', str(coverage))

    if html_output:
        subprocess.check_call(
            args=[
                'genhtml',
                '-s',
                '-o', os.path.join(html_output, 'total'),
                '-t', 'Total for {suite}'.format(suite=suite),
                '--',
                os.path.join(lcov_output, 'total.lcov'),
            ])

    store_coverage(test_coverage, summary['zbkc-sha1'], suite)
