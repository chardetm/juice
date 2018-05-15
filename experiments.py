#!/usr/bin/env python

import copy
import logging
import os
import math
from pprint import pformat
import traceback

import juice as j
from execo_engine.sweep import (ParamSweeper, sweep)

SWEEPER_DIR = os.path.join(os.getenv('HOME'), 'juice-sweeper-maria')

JOB_NAME = 'juice-tests-groups'
# WALLTIME = '08:18:00'
# WALLTIME = '44:55:00'
WALLTIME = '23:59:58'
RESERVATION = None
# RESERVATION = '2018-05-13 16:00:00'

DATABASES = ['cockroachdb']
# DATABASES = ['mariadb']
CLUSTER_SIZES = [9]
# CLUSTER_SIZES = [3, 25, 45, 100]
DELAYS = [150]
# DELAYS = [0]
REPLICAS_QUORUM = [3, 2, 1]

CLUSTER = 'ecotype'
SITE = 'nantes'

MAX_CLUSTER_SIZE = max(CLUSTER_SIZES)

NODES_PER_GROUP = 3


CONF = {
    'enable_monitoring': True,
    'g5k': {'dhcp': True,
            'env_name': 'debian9-x64-nfs',
            'job_name': JOB_NAME,
            # 'queue': 'testing',
            'walltime': WALLTIME,
            'reservation': RESERVATION,
            'resources': {'machines': [{'cluster': CLUSTER,
                                        'nodes': MAX_CLUSTER_SIZE,
                                        'roles': ['chrony',
                                                  'database',
                                                  'sysbench',
                                                  'openstack',
                                                  'rally'],
                                        'primary_network': 'n0',
                                        'secondary_networks': ['n1']},
                                       {'cluster': CLUSTER,
                                        'nodes': 1,
                                        'roles': ['registry', 'control'],
                                        'primary_network': 'n0',
                                        'secondary_networks': []}],
                          'networks': [{'id': 'n0',
                                        'roles': ['control_network'],
                                        'site': SITE,
                                        'type': 'prod'},
                                       {'id': 'n1',
                                        'roles': ['database_network'],
                                        'site': SITE,
                                        'type': 'kavlan'},
                                       ]}},
    'registry': {'ceph': True,
                 'ceph_id': 'discovery',
                 'ceph_keyring': '/home/discovery/.ceph/ceph.client.discovery.keyring',
                 'ceph_mon_host': ['ceph0.rennes.grid5000.fr',
                                   'ceph1.rennes.grid5000.fr',
                                   'ceph2.rennes.grid5000.fr'],
                 'ceph_rbd': 'discovery_kolla_registry/datas',
                 'type': 'none'},
    'tc': {'constraints': [{'delay': '10ms',
                            'src': 'database',
                            'dst': 'database',
                            'loss': 0,
                            'rate': '10gbit',
                            "network": "database_network"}],
           'default_delay': '0ms',
           'default_rate': '10gbit',
           'enable': True},
    'replicas_quorum': REPLICAS_QUORUM
}

SCENARIOS = [
      "keystone/authenticate-user-and-validate-token.yaml"
    , "keystone/create-add-and-list-user-roles.yaml"
    , "keystone/create-and-list-tenants.yaml"
    , "keystone/get-entities.yaml"
    , "keystone/create-user-update-password.yaml"
    , "keystone/create-user-set-enabled-and-delete.yaml"
    , "keystone/create-and-list-users.yaml"
]


logging.basicConfig(level=logging.INFO)


def init():
    try:
        j.g5k(config=CONF)
        j.inventory()
        # j.destroy()
        j.emulate(CONF['tc'])
    except Exception as e:
        logging.error(
            "Setup went wrong. This is not necessarily a bad news, "
            "in particular, if it is the first time you run the "
            "experiment: %s" % e)


def teardown():
    try:
        j.destroy()
        # j.emulate(CONF['tc'])
    except Exception as e:
        logging.warning(
            "Setup goes wrong. This is not necessarily a bad news, "
            "in particular, if it is the first time you run the "
            "experiment: %s" % e)


def conf_group(conf, combination):
    nb_nodes = combination['db-nodes']
    groups = range(int(math.ceil(nb_nodes/NODES_PER_GROUP)))
    machines = [{'cluster': 'ecotype',
                 'nodes': 1,
                 'roles': ['registry', 'control'],
                 'primary_network': 'n0',
                 'secondary_networks': ['n1']}]
    for i in groups:
        group = 'database' + str(i)
        machines.append({'cluster': CLUSTER,
                         'nodes': NODES_PER_GROUP,
                         'roles': ['chrony',
                                   group,
                                   'sysbench',
                                   'openstack',
                                   'rally'],
                         'primary_network': 'n0',
                         'secondary_networks': ['n1']})
    conf['g5k']['resources']['machines'] = machines
    return groups


def tc_groups(conf, groups, delay):
    constraints = []
    databases = []
    for i in groups:
        databases.append('database' + str(i))
    for src in databases:
        remaining_groups = [x for x in databases if x != src]
        for dst in remaining_groups:
            if src != dst:
                constraints.append({'delay': delay,
                                    'src': src,
                                    'dst': dst,
                                    'loss': 0,
                                    'rate': '10gbit',
                                    "network": "database_network"})
    conf['tc']['constraints'] = constraints
    conf['tc']['groups'] = databases
    print(conf['tc'])


def replicas(conf, combination):
    nb_nodes = combination['db-nodes']
    groups = range(int(math.ceil(nb_nodes/NODES_PER_GROUP)))
    replicas_quorum = combination['replicas_quorum']
    replicas_list = []
    for db in groups:
        if db == 0:
            replicas_list.append(replicas_quorum)
        elif db == 1:
            if replicas_quorum == 3:
                replicas_list.append(0)
            else:
                replicas_list.append(1)
        elif db == 2:
            if replicas_quorum == 1:
                replicas_list.append(1)
            else:
                replicas_list.append(0)
        else:
            replicas_list.append(0)
    print(replicas_list)
    conf['quorum'] = replicas_list
    return replicas_list

def keystone_exp():
    sweeper = ParamSweeper(
        SWEEPER_DIR,
        sweeps=sweep({
              'db':    DATABASES
            , 'delay': DELAYS
            , 'db-nodes': CLUSTER_SIZES
            , 'replicas_quorum': REPLICAS_QUORUM
        }))

    while sweeper.get_remaining():
        combination = sweeper.get_next()
        logging.info("Treating combination %s" % pformat(combination))

        try:
            # Setup parameters
            conf = copy.deepcopy(CONF)  # Make a deepcopy so we can run
                                        # multiple sweeps in parallels
            # conf['g5k']['resources']['machines'][0]['nodes'] = combination['db-nodes']
            delay = "%sms" % combination['delay']
            conf['tc']['constraints'][0]['delay'] = delay
            replicas_quorum = "%s" % combination['replicas_quorum']
            conf['replicas_quorum'] = replicas_quorum
            # Configuring groups
            groups = conf_group(conf, combination)
            # Configurating latency between groups and in the groups
            tc_groups(conf, groups, delay)
            # Configuring replicas for database
            replicas(conf, combination)
            db = combination['db']
            xp_name = "%s-%s-%s-%s" % (db, combination['db-nodes'], delay, replicas_quorum)

            # Let's get it started hun!
            j.deploy(conf, db, xp_name)
            j.openstack(db)
            j.emulate(conf['tc'])
            j.rally(SCENARIOS, "keystone", burst=False)
            j.backup()

            # Everything works well, mark combination as done
            sweeper.done(combination)
            logging.info("End of combination %s" % pformat(combination))

        except Exception as e:
          # Oh no, something goes wrong! Mark combination as cancel for
          # a later retry
            logging.error("Combination %s Failed with message %s" % (pformat(combination), e))
            sweeper.cancel(combination)
            traceback.print_exc()

        finally:
            teardown()

if __name__ == '__main__':
    # Do the initial reservation and boilerplate
    init()

    # Run experiment
    keystone_exp()
