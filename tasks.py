#!/usr/bin/env python

"""Tool to test Keystone over Galera and CockroachdB on Grid'5000 using Enoslib

Usage:
    juice [-h | --help] [-v | --version] <command> [<args>...]

Options:
    -h --help      Show this help
    -v --version   Show version number

Commands:
    deploy         Claim resources from g5k and configure them
    g5k            Claim resources on Grid'5000 (from a frontend)
    inventory      Generate the Ansible inventory file
    prepare        Configure the resources
    destroy        Destroy all the running dockers (not destroying the resources)
    backup         Backup the environment
"""

import os
import logging
import yaml

from docopt import docopt
from enoslib.api import run_ansible, generate_inventory, emulate_network, validate_network
from enoslib.task import enostask
from enoslib.infra.enos_g5k.provider import G5k

from utils.doc import doc, doc_lookup, DOC_GLOBAL

logging.basicConfig(level=logging.DEBUG)

DEFAULT_CONF = os.path.dirname(os.path.realpath(__file__))
DEFAULT_CONF = os.path.join(DEFAULT_CONF, "conf.yaml")

tc = {
    "enable": True,
    "default_delay": "20ms",
    "default_rate": "1gbit",
}


@doc()
def deploy(conf, db, **kwargs):
    """
usage: juice deploy  [--conf CONFIG_PATH] [--db {mariadb,cockroachdb}]

Claim resources from g5k and configure them.

Options:
  --conf CONFIG_PATH   Path to the configuration file describing the
                       deployment [default: ./conf.yaml].
  --db DATABASE        Database to deploy on [default: cockroachdb]
    """

    config = {}
    with open(conf) as f:
        config = yaml.load(f)

    g5k(config=config)
    inventory()
    prepare(db=db)


@doc()
@enostask(new=True)
def g5k(env=None, force=False, config=None,  **kwargs):
    provider = G5k(config["g5k"])
    roles, networks = provider.init(force_deploy=force)
    env["config"] = config
    env["roles"] = roles
    env["networks"] = networks


@doc()
@enostask()
def inventory(env=None, **kwargs):
    roles = env["roles"]
    networks = env["networks"]
    env["inventory"] = os.path.join(env["resultdir"], "hosts")
    generate_inventory(roles, networks, env["inventory"], check_networks=True)


@doc()
@enostask()
def prepare(env=None, db='cockroachdb', **kwargs):
    # Generate inventory
    extra_vars = {
        "registry": env["config"]["registry"],
        "db": db
    }
    env["db"] = db
    # use deploy of each role
    extra_vars.update({"enos_action": "deploy"})

    run_ansible(["ansible/site.yml"], env["inventory"], extra_vars=extra_vars)


@doc()
@enostask()
def emulate(env=None, **kwargs):
    inventory = env["inventory"]
    roles = env["roles"]
    emulate_network(roles, inventory, tc)


@doc()
@enostask()
def validate(env=None, **kwargs):
    inventory = env["inventory"]
    roles = env["roles"]
    validate_network(roles, inventory)


@doc()
@enostask()
def backup(env=None, **kwargs):
    extra_vars = {
        "enos_action": "backup",
        "backup_dir": os.path.join(os.getcwd(), "current")
    }
    run_ansible(["ansible/site.yml"], env["inventory"], extra_vars=extra_vars)


@doc()
@enostask()
def destroy(env=None, **kwargs):
    extra_vars = {}
    # Call destroy on each component
    extra_vars.update({
        "enos_action": "destroy",
        "db": env["db"]
    })
    run_ansible(["ansible/site.yml"], env["inventory"], extra_vars=extra_vars)


if __name__ == '__main__':

    args = docopt(__doc__,
                  version='juice version 1.0.0',
                  options_first=True)

    argv = [args['<command>']] + args['<args>']

    doc_lookup(args['<command>'], argv)
