#!/usr/bin/env python
#
# Copyright Wylie Hobbs - 2018
#

import boto3
import json
import time
import sys
import argparse
import logging

aws_region = None

def main(args):
    global aws_region
    aws_region = args.aws_region

    now = str(time.time()).split('.')[0]
    new_instance = None

    new_instance_attributes = set_new_instance_attributes(args)

    logging.info("New instance attributes are: %s" % new_instance_attributes)

    write_attribute_to_file(f'{args.data_folder}/db_instance_name',new_instance_attributes['name'])

    if not args.noop:
        restore_rds_snapshot(new_instance_attributes)
        new_instance = modify_new_rds_instance(new_instance_attributes)

        if new_instance:
            endpoint = new_instance['DBInstance']['Endpoint']['Address']
            update_dns(new_instance_attributes, endpoint)

            if new_instance_attributes['existing_instances']:
                destroy_old_instances(new_instance_attributes['existing_instances'])

    else:
        logging.info("NOOP: Would restore snapshot %s" % (new_instance_attributes['restore_snapshot_id']))


def set_new_instance_attributes(args):
    now = str(time.time()).split('.')[0]
    target_attributes = get_target_instance_attributes(args.target_instance)
    target_name = target_attributes['DBInstanceIdentifier']

    # Get security group IDs based on the security group names specified
    # Otherwise, use the target instance's security group IDs
    # Specify security group names if you are restoring to a different VPC
    if args.security_group_names:
        if args.vpc_tag_name:
            vpc_id = get_vpc_id_by_name_tag(args.vpc_tag_name)
            security_group_ids = get_security_groups(vpc_id, args.security_group_names)
        else:
            logging.critical("You must specifiy a VPC Name Tag to search for when using the -S option. Exiting")
            sys.exit(1)
    else:
        security_group_ids = [vsg['VpcSecurityGroupId'] for vsg in target_attributes['VpcSecurityGroups']]

    # Set the DB Subnet group if specified - otherwise, use the target instance's
    if args.subnet_group_name:
        db_subnet_group = args.subnet_group_name
    else:
        db_subnet_group = target_attributes['DBSubnetGroup']['DBSubnetGroupName']

    # Set the Route53 Hosted Zone ID
    if args.zone_match_string and not args.zone_id:
        zone_id = get_route53_zone_id(args.zone_match_string)
    elif args.zone_id and not args.zone_match_string:
        zone_id = args.zone_id
    else:
        logging.critical('You must use --zone-id or --match-zone in order for DNS update to work. Both cannot be specified at the same time. Exiting.')
        sys.exit(1)

    # If prefix is specified, prepend it to the new_instance_name
    if args.prefix:
        new_instance_base = "%s-%s" % (args.prefix, target_name)
    else:
        new_instance_base = target_name

    new_instance_name = "%s-%s" % (new_instance_base, now)
    tag_key = "%s-automated-restore" % new_instance_base

    restore_snapshot_id = get_recent_rds_snapshot(
        args.snapshot_type, target_name)

    new_instance_attributes = {
        'name': new_instance_name,
        'existing_instances': find_snapshot_restored_instances(new_instance_base),
        'security_group_ids': security_group_ids,
        'db_subnet_group': db_subnet_group,
        'zone_id': zone_id,
        'instance_class': args.instance_class,
        'restore_snapshot_id': restore_snapshot_id,
        'snapshot_type': args.snapshot_type,
        'dns_suffix': args.dns_suffix,
        'cname_name': args.cname_name,
        'publicly_accessible': False,
        'multi_az': False,
        'region': args.aws_region,
        'auto_minor_version_upgrade': False,
        'tag_key': tag_key
    }

    return new_instance_attributes

def get_target_instance_attributes(instance_identifier):
    client = boto3.client('rds', region_name=aws_region)

    response = client.describe_db_instances(
        DBInstanceIdentifier=instance_identifier
    )

    if response:
        return response['DBInstances'][0]
    else:
        logging.critical("Could not find an instance that matches %s. Exiting." % instance_identifier)
        sys.exit(1)

def get_vpc_id_by_name_tag(vpc_name_tag_value):
    ec2 = boto3.resource('ec2', region_name=aws_region)
    client = boto3.client('ec2', region_name=aws_region)

    filter_string = "%s*" % vpc_name_tag_value
    filters = [{'Name': 'tag:Name', 'Values': [filter_string]}]
    vpcs = list(ec2.vpcs.filter(Filters=filters))  # Only use the first match

    for vpc in vpcs:
        vpc_metadata = client.describe_vpcs(
            VpcIds=[
                vpc.id,
            ]
        )

    vpc_id = vpc_metadata['Vpcs'][0]['VpcId']

    return vpc_id

def get_security_groups(vpc_id, group_names):
    """ Gets VPC security groups in a given VPC that match a list of names
        Returns a list of VPC security group IDs
    """
    client = boto3.client('ec2', region_name=aws_region)
    security_groups = []
    for group_name in group_names:
        security_group = client.describe_security_groups(
            Filters=[
                {
                    'Name': 'vpc-id',
                    'Values': [
                        vpc_id,
                    ]
                },
                {
                    'Name': 'group-name',
                    'Values': [
                        group_name,
                    ]
                }
            ]
        )

        security_groups.append(security_group['SecurityGroups'][0]['GroupId'])

    if security_groups:
        return security_groups
    else:
        logging.info("Could not find any security groups in VPC %s that match %s. Exiting." % (vpc_id, group_names))
        sys.exit(1)


def find_snapshot_restored_instances(instance_match_string):
    logging.info("Determine if there are currently any existing snapshot-restored instances matching %s tag" % instance_match_string)

    client = boto3.client('rds', region_name=aws_region)
    existing_instances = []
    try:
        all_instances = client.describe_db_instances()

        for instance in all_instances['DBInstances']:
            instance_id = instance['DBInstanceIdentifier']
            if instance_match_string in instance_id:
                existing_instances.append(instance_id)

        if existing_instances:
            logging.info("These instances were found and will be deleted when the new one is active %s" % existing_instances)

        return existing_instances

    except:
        logging.critical("No existing instances found with with substring %s" %
              instance_match_string)
        return None


def get_recent_rds_snapshot(snapshot_type, target_rds_instance):
    client = boto3.client('rds', region_name=aws_region)

    logging.info("Finding most recent %s snapshot from master instance %s" %
           (snapshot_type, target_rds_instance))

    # Get all snapshots for the account, which we will filter in the next step
    snapshots = client.describe_db_snapshots(
        DBInstanceIdentifier=target_rds_instance,
        SnapshotType=snapshot_type,
        MaxRecords=20
    )['DBSnapshots']

    # From https://github.com/truffls/rds_snapshot_restore/blob/master/rds_snapshot_restore.py
    # sort descending and retrieve most current entry
    try:
        most_current_snapshot = sorted(
            snapshots,
            key=lambda x: x.get('SnapshotCreateTime'),
            reverse=True)[0]
    except IndexError:
        raise StandardError('Could not find a snapshot')
        logging.info(sys.exc_info()[0])

    identifier = most_current_snapshot.get('DBSnapshotIdentifier')

    if identifier:
        logging.info("Most recent snapshot for %s is %s - using it to restore from" % (target_rds_instance, identifier))
        return identifier
    else:
        raise StandardError(
            'ERROR: Could not determine most current snapshot with filter %s'
            % target_rds_instance)


def restore_rds_snapshot(attributes):
    """Create new RDS instance as a mirror of the target instance (from snapshot)"""
    client = boto3.client('rds', region_name=aws_region)

    logging.info('Making sure database subnet group %s exists' % attributes['db_subnet_group'])
    # Verify that the specified database subnet group is real
    db_subnet_group = client.describe_db_subnet_groups(
        DBSubnetGroupName=attributes['db_subnet_group']
    )


    if db_subnet_group:
        logging.info('Restoring snapshot %s to new instance %s' % (attributes['restore_snapshot_id'], attributes['name']))

        response = client.restore_db_instance_from_db_snapshot(
            DBInstanceIdentifier=attributes['name'],
            DBSnapshotIdentifier=attributes['restore_snapshot_id'],
            DBInstanceClass=attributes['instance_class'],
            PubliclyAccessible=attributes['publicly_accessible'],
            MultiAZ=attributes['multi_az'],
            AutoMinorVersionUpgrade=attributes['auto_minor_version_upgrade'],
            DBSubnetGroupName=attributes['db_subnet_group'],
            Tags=[
                {
                    'Key': attributes['tag_key'],
                    'Value': 'true'
                },
            ]
        )

        logging.info("Restore initiated, waiting for database to become available...")

        waiter = client.get_waiter('db_instance_available')
        waiter.wait(
            DBInstanceIdentifier=attributes['name'],
            WaiterConfig={
                'Delay': 15,
                'MaxAttempts': 60
            }
        )

    else:
        raise StandardError(
            'ERROR: Could not find subnet group %s' % attributes['db_subnet_group'])


def modify_new_rds_instance(attributes):
    """
    Modify new instance with desired parameters
    """
    client = boto3.client('rds', region_name=aws_region)

    try:
        logging.info('Modifying db instance %s' % attributes['name'])

        response = client.modify_db_instance(
            DBInstanceIdentifier=attributes['name'],
            VpcSecurityGroupIds=attributes['security_group_ids'],
            BackupRetentionPeriod=0
        )

        waiter = client.get_waiter('db_instance_available')
        waiter.wait(
            DBInstanceIdentifier=attributes['name'],
            WaiterConfig={
                'Delay': 15,
                'MaxAttempts': 60
            }
        )

        return response

    except:
        raise StandardError(
            'ERROR: Could there was a problem modifying the instance %s' % attributes['name'])


def get_route53_zone_id(zone_match_string):

    client = boto3.client('route53', region_name=aws_region)

    logging.info("Looking for private route53 zone with %s in the name" % zone_match_string)
    try:
        response = client.list_hosted_zones()

        for zone in response['HostedZones']:
            if zone_match_string in zone['Name']:
                zone_id = zone['Id'].split('/')[2]


        if zone_id:
            logging.info("Found zone %s that has %s in its name" % (zone_id, zone_match_string))
            return zone_id
        else:
            logging.critical("Could not find Route53 zone with %s in the name. Try using the -z option or fix your match string. Exiting" % zone_match_string)
            sys.exit(1)

    except Exception as e:
        logging.critical("Error retrieving zone id for %s - %s" %
               (zone_match_string, str(e)))
        raise


def update_dns(attributes, target):
    """
    Create CNAME for new instance - this makes the new instance "live"
    Source is the record name, target is the target address, i.e. a DB endpoint address
    """
    client = boto3.client('route53', region_name=aws_region)

    dns_name = "%s.%s" % (attributes['cname_name'], attributes['dns_suffix'])
    logging.info("Creating/updating DNS in zone %s for record %s with value %s" % (attributes['zone_id'], dns_name, target))

    write_attribute_to_file(f'{args.data_folder}/dns_record_name',dns_name)
    write_attribute_to_file(f'{args.data_folder}/dns_record_value',target)

    try:
        response = client.change_resource_record_sets(
            HostedZoneId=attributes['zone_id'],
            ChangeBatch={
                'Changes': [{
                    'Action': 'UPSERT',
                    'ResourceRecordSet': {
                        'Name': dns_name,
                        'Type': 'CNAME',
                        'TTL': 300,
                        'ResourceRecords': [{'Value': target}]
                    }
                }]
            })

        waiter = client.get_waiter('resource_record_sets_changed')
        waiter.wait(Id=response['ChangeInfo']['Id'])

        write_delete_patch(dns_name,target)

    except Exception as e:
        logging.critical("Error updating DNS for endpoint %s - %s" % (target, str(e)))
        raise

def write_attribute_to_file(path,value):

    try:
        f = open(path,"w+")
        f.write(value)
        f.close()
    except Exception as e:
        logging.critical("Error while writing attribute %s to file %s - %s" % (value,path, str(e)))
        raise


def destroy_old_instances(old_rds_instances):
    """
    Delete the old instance once we know the new one is healthy
    """
    client = boto3.client('rds', region_name=aws_region)

    for instance in old_rds_instances:
        logging.info("Destroying old instance %s" % instance)

        try:
            response = client.delete_db_instance(
                DBInstanceIdentifier=instance,
                SkipFinalSnapshot=True
            )

            waiter = client.get_waiter('db_instance_deleted')
            waiter.wait(
                DBInstanceIdentifier=instance,
                WaiterConfig={
                    'Delay': 15,
                    'MaxAttempts': 60
                }
            )
        except Exception as e:
            logging.critical("Error deleting %s - %s" % (instance, str(e)))
            raise

def write_delete_patch(dns_name,value):
    delete_patch = {
        'Comment': 'Delete single record set',
        'Changes': [
            {
                'Action': 'DELETE',
                'ResourceRecordSet':{
                    'Name': f'{dns_name}.',
                    'Type': 'CNAME',
                    'TTL': 300,
                    'ResourceRecords': [
                        {
                            'Value': value
                        }
                    ]
                }
            }       
        ]
    }

    write_attribute_to_file(f'{args.data_folder}/dns_delete_patch',json.dumps(delete_patch))


def build_parser():
    parser = argparse.ArgumentParser(description='Restore the most recent snapshot of a given RDS instance to a new instance')
    parser.add_argument('-t', '--target', required=True, type=str, dest='target_instance', 
        help='Name of the RDS instance to restore the snapshot from - this is the DBInstanceIdentifier of the target instance')
    parser.add_argument(
        '-r', '--region', required=False, type=str, dest='aws_region', default='us-west-2', help='AWS Region to use. Currently can only target and restore to the same region. Defaults to "us-west-2"')
    parser.add_argument(
        '-i', '--instance-class', required=False, type=str, dest='instance_class', default='db.t2.medium', help='Instance class to use for the new instance. Defaults to db.t2.medium')
    parser.add_argument(
        '-p', '--prefix', required=False, type=str, dest='prefix', default='', help='Prefix for the new instance DBInstanceIdentifier')
    parser.add_argument(
        '-u', '--subnet-name', required=False, type=str, dest='subnet_group_name', help='Name of the database subnet group to use for the new instance. Defaults to the subnet group of the target instance if not specified')
    parser.add_argument(
        '-S', '--sec-group-names', required=False, nargs='+', type=str, dest='security_group_names', help='Names of the VPC security group to use for the new instance. Defaults to the security group of the target instance if not specified. Specify multiple separated by a space. Must also specify --vpc-tag-name.')
    parser.add_argument(
        '-V', '--vpc-tag-name', required=False, type=str, dest='vpc_tag_name', help='VPC "Name" tag value. Required when using --sec-group-names')
    parser.add_argument(
        '-D', '--dns-suffix', required=True, type=str, dest='dns_suffix', help='DNS Suffix for your private Route53 zone')
    parser.add_argument(
        '-c', '--cname-name', required=True, type=str, dest='cname_name', help='Name of the CNAME to create for the new instance')
    parser.add_argument(
        '-m', '--match-zone', required=False, type=str, dest='zone_match_string', help='String to match a Route53 Hosted Zone name on to determine the zone ID. Useful if you rebuild private DNS zones often. Overrides --zone-id if specified.')
    parser.add_argument(
        '-z', '--zone-id', required=False, type=str, dest='zone_id', help='Route53 Zone ID to use for the new instance CNAME. Defaults to the zone id of the target instance. Is overridden by --match-zone.')
    parser.add_argument(
        '-s', '--snapshot-type', required=False, type=str, dest='snapshot_type', default='automated', help='Snapshot type to search filter on. Defaults to "automated"')
    parser.add_argument(
        '-f', '--data-folder', required=False, type=str, dest='data_folder', default='./', help='Path to the folder where RDS instance and DNS data will be stored')
    parser.add_argument(
        '-n', '--noop', required=False, dest='noop', action='store_true', default=False, help='Enable NOOP mode - will not perform any restore tasks')

    return parser

if __name__ == '__main__':

    parser = build_parser()
    args = parser.parse_args()

    loglevel = logging.INFO
    logging.basicConfig(level=loglevel)

    main(args)
