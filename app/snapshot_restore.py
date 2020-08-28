#!/usr/bin/env python
#
# Copyright Wylie Hobbs - 2018
#

import argparse
import logging
import time
import sys
import re
from rds import RDS
from route53 import ROUTE53
from helpers import HELPERS
from k8s import K8S
from ephemerals import EPHEMERALS

def build_parser():
    parser = argparse.ArgumentParser(description='Restore the most recent snapshot of a given RDS instance or a to a new instance')
    parser.add_argument(
        '-t', '--target', required=True, type=str, dest='target_instance', help='Name of the RDS instance to restore the snapshot from - this is the DBInstanceIdentifier of the target instance')
    parser.add_argument(
        '-r', '--region', required=False, type=str, dest='aws_region', default='us-west-2', help='AWS Region to use. Currently can only target and restore to the same region. Defaults to "us-west-2"')
    parser.add_argument(
        '-i', '--instance-class', required=False, type=str, dest='instance_class', default='db.t2.medium', help='Instance class to use for the new instance. Defaults to db.t2.medium')
    parser.add_argument(
        '-p', '--prefix', required=False, type=str, dest='prefix', default='', help='Prefix for the new instance DBInstanceIdentifier')
    parser.add_argument(
        '-u', '--subnet-group-name', required=False, type=str, dest='subnet_group_name', help='Name of the database subnet group to use for the new instance. Defaults to the subnet group of the target instance if not specified')
    parser.add_argument(
        '-S', '--sec-group-names', required=False, nargs='+', type=str, dest='security_group_names', help='Names of the VPC security group to use for the new instance. Defaults to the security group of the target instance if not specified. Specify multiple separated by a space. Must also specify --vpc-tag-name.')
    parser.add_argument(
        '-V', '--vpc-tag-name', required=False, type=str, dest='vpc_tag_name', help='VPC "Name" tag value. Required when using --sec-group-names')
    parser.add_argument(
        '-D', '--dns-suffix', required=True, type=str, dest='dns_suffix', help='DNS Suffix for your private Route53 zone')
    parser.add_argument(
        '-c', '--cname-name', required=False, type=str, dest='cname_name', help='Name of the CNAME to create for the new instance')
    parser.add_argument(
        '-m', '--match-zone', required=False, type=str, dest='zone_match_string', help='String to match a Route53 Hosted Zone name on to determine the zone ID. Useful if you rebuild private DNS zones often. Overrides --zone-id if specified.')
    parser.add_argument(
        '-z', '--zone-id', required=False, type=str, dest='zone_id', help='Route53 Zone ID to use for the new instance CNAME. Defaults to the zone id of the target instance. Is overridden by --match-zone.')
    parser.add_argument(
        '-s', '--snapshot-type', required=False, type=str, dest='snapshot_type', default='automated', help='Snapshot type to search filter on. Defaults to "automated"')
    parser.add_argument(
        '-f', '--data-folder', required=False, type=str, dest='data_folder', default='./', help='Path to the folder where RDS instance name and DNS data will be stored')
    parser.add_argument(
        '-e', '--extra-tags', required=False, type=str, dest='extra_tags', help='Additional Tags for the new RDS instance. Format like -e "tag1_key:tag1_value;tag2_key:tag2_value"')
    parser.add_argument(
        '-x', '--from-snapshot', required=False, action='store_true', dest='from_snapshot', default=False, help='Set this flag to restore directly from a snapshot')
    parser.add_argument(
        '-y', '--db-param-group', required=False, dest='db_param_group', help='Name of the parameter group applied to the new RDS instance')
    parser.add_argument(
        '-Z', '--ephemeral-zombie-clean', required=False, dest="ephemeral_zombie_clean", action='store_true', help='Remove RDS Instances and Route53 CNAME for resources when there is no K8s namespace associated')
    parser.add_argument(
        '-n', '--noop', required=False, dest='noop', action='store_true', default=False, help='Enable NOOP mode - will not perform any restore tasks')

    return parser

def main(args):

    now = str(time.time()).split('.')[0]
    new_instance = None

    rds = RDS(args)
    route53 = ROUTE53(args)
    helpers = HELPERS(args)

    new_instance_attributes = rds.set_new_instance_attributes()

    if args.extra_tags:
        extra_tags = helpers.parse_extra_tags(args.extra_tags)
        new_instance_attributes['tags'] = new_instance_attributes['tags'] + extra_tags

    logging.info("New instance attributes are: %s" % new_instance_attributes)

    helpers.write_attribute_to_file(f'{args.data_folder}/db_instance_name',new_instance_attributes['name'])

    if not args.noop:
        rds.restore_rds_snapshot(new_instance_attributes)
        new_instance = rds.modify_new_rds_instance(new_instance_attributes)

        if new_instance:
            endpoint = new_instance['DBInstance']['Endpoint']['Address']
            route53.update_dns(new_instance_attributes, endpoint)

            if new_instance_attributes['existing_instances']:
                rds.destroy_old_instances(new_instance_attributes['existing_instances'])

    else:
        logging.info("NOOP: Would restore snapshot %s" % (new_instance_attributes['restore_snapshot_id']))
        
if __name__ == '__main__':

    parser = build_parser()
    args = parser.parse_args()

    loglevel = logging.INFO
    logging.basicConfig(level=loglevel)

    if (args.ephemeral_zombie_clean):
        ephemerals = EPHEMERALS(args)
        ephemerals.ephemeral_zombie_clean(args)
    else:
        main(args)
