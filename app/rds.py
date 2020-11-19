import logging
import time
import sys
import boto3
import re
from vpc import VPC
from route53 import ROUTE53

class RDS():
    def __init__(self, args):
        self.args = args
        self.vpc = VPC(self.args)
        self.route53 = ROUTE53(self.args)

        self.client = boto3.client('rds', region_name=self.args.aws_region)

    def set_new_instance_attributes(self):
        now = str(time.time()).split('.')[0]

        if not self.args.from_snapshot:
            target_attributes = self.get_target_instance_attributes(self.args.target_instance)
            target_name = target_attributes['DBInstanceIdentifier']
        else:
            target_name = self.args.target_instance

        # Get security group IDs based on the security group names specified
        # Otherwise, use the target instance's security group IDs
        # Specify security group names if you are restoring to a different VPC
        if self.args.security_group_names:
            if self.args.vpc_tag_name:
                vpc_id = self.vpc.get_vpc_id_by_name_tag(self.args.vpc_tag_name)
                security_group_ids = self.vpc.get_security_groups(vpc_id, self.args.security_group_names)
            else:
                logging.critical("You must specifiy a VPC Name Tag to search for when using the -S option. Exiting")
                sys.exit(1)
        else:
            security_group_ids = [vsg['VpcSecurityGroupId'] for vsg in target_attributes['VpcSecurityGroups']]

        # Set the DB Subnet group if specified - otherwise, use the target instance's
        if self.args.subnet_group_name:
            db_subnet_group = self.args.subnet_group_name
        else:
            db_subnet_group = target_attributes['DBSubnetGroup']['DBSubnetGroupName']

        # Set the Route53 Hosted Zone ID
        if self.args.zone_match_string and not self.args.zone_id:
            zone_id = self.route53.get_route53_zone_id(self.args.zone_match_string)
        elif self.args.zone_id and not self.args.zone_match_string:
            zone_id = self.args.zone_id
        else:
            logging.critical('You must use --zone-id or --match-zone in order for DNS update to work. Both cannot be specified at the same time. Exiting.')
            sys.exit(1)

        # If prefix is specified, prepend it to the new_instance_name
        if self.args.prefix:
            new_instance_base = "%s-%s" % (self.args.prefix, target_name)
        else:
            new_instance_base = target_name

        new_instance_name = "%s-%s" % (new_instance_base, now)
        tag_key = "%s-automated-restore" % new_instance_base
        tags = [
            {
                'Key': f'{new_instance_base}-automated-restore', 
                'Value': 'true'
            }
        ]

        restore_snapshot_id = self.get_recent_rds_snapshot(
            self.args.snapshot_type, target_name)

        new_instance_attributes = {
            'name': new_instance_name,
            'existing_instances': self.find_snapshot_restored_instances(new_instance_base),
            'security_group_ids': security_group_ids,
            'db_subnet_group': db_subnet_group,
            'zone_id': zone_id,
            'instance_class': self.args.instance_class,
            'restore_snapshot_id': restore_snapshot_id,
            'snapshot_type': self.args.snapshot_type,
            'dns_suffix': self.args.dns_suffix,
            'cname_name': self.args.cname_name,
            'publicly_accessible': False,
            'multi_az': False,
            'region': self.args.aws_region,
            'auto_minor_version_upgrade': False,
            'tags': tags
        }

        return new_instance_attributes

    def get_target_instance_attributes(self,instance_identifier):

        response = self.client.describe_db_instances(
            DBInstanceIdentifier=instance_identifier
        )

        if response:
            return response['DBInstances'][0]
        else:
            logging.critical("Could not find an instance that matches %s. Exiting." % instance_identifier)
            sys.exit(1)

    def find_snapshot_restored_instances(self,instance_match_string):
        logging.info("Determine if there are currently any existing snapshot-restored instances matching %s tag" % instance_match_string)

        existing_instances = []
        try:
            all_instances = self.client.describe_db_instances()

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

    def get_recent_rds_snapshot(self,snapshot_type, target_rds_instance):

        logging.info("Finding most recent %s snapshot from master instance %s" %
            (snapshot_type, target_rds_instance))

        # Get all snapshots for the account, which we will filter in the next step
        snapshots = self.client.describe_db_snapshots(
            DBInstanceIdentifier=target_rds_instance,
            SnapshotType=snapshot_type,
            MaxRecords=20
        )['DBSnapshots']

        #Filter to get only "Ready" snapshots
        available_snapshots = list(filter(lambda d: d['Status'] in ['available'], snapshots))

        # From https://github.com/truffls/rds_snapshot_restore/blob/master/rds_snapshot_restore.py
        # sort descending and retrieve most current entry
        try:
            most_current_snapshot = sorted(
                available_snapshots,
                key=lambda x: x.get('SnapshotCreateTime'),
                reverse=True)[0]
        except IndexError:
            raise Exception('Could not find a snapshot')
            logging.info(sys.exc_info()[0])

        identifier = most_current_snapshot.get('DBSnapshotIdentifier')

        if identifier:
            logging.info("Most recent snapshot for %s is %s - using it to restore from" % (target_rds_instance, identifier))
            return identifier
        else:
            raise Exception(
                'ERROR: Could not determine most current snapshot with filter %s'
                % target_rds_instance)


    def restore_rds_snapshot(self,attributes):
        """Create new RDS instance as a mirror of the target instance (from snapshot)"""
        logging.info('Making sure database subnet group %s exists' % attributes['db_subnet_group'])
        # Verify that the specified database subnet group is real
        db_subnet_group = self.client.describe_db_subnet_groups(
            DBSubnetGroupName=attributes['db_subnet_group']
        )

        logging.info('Making sure database parameter group %s exists' % self.args.db_param_group)
        # Verify that the specified database param group is real
        db_param_group = self.client.describe_db_parameter_groups(
            DBParameterGroupName=self.args.db_param_group
        )

        if (db_subnet_group and db_param_group):
            logging.info('Restoring snapshot %s to new instance %s' % (attributes['restore_snapshot_id'], attributes['name']))

            response = self.client.restore_db_instance_from_db_snapshot(
                DBInstanceIdentifier=attributes['name'],
                DBSnapshotIdentifier=attributes['restore_snapshot_id'],
                DBInstanceClass=attributes['instance_class'],
                PubliclyAccessible=attributes['publicly_accessible'],
                MultiAZ=attributes['multi_az'],
                AutoMinorVersionUpgrade=attributes['auto_minor_version_upgrade'],
                DBSubnetGroupName=attributes['db_subnet_group'],
                Tags=attributes['tags'],
                DBParameterGroupName=self.args.db_param_group
            )

            logging.info("Restore initiated, waiting for database to become available...")

            waiter = self.client.get_waiter('db_instance_available')
            waiter.wait(
                DBInstanceIdentifier=attributes['name'],
                WaiterConfig={
                    'Delay': 15,
                    'MaxAttempts': 60
                }
            )

        else:
            raise Exception(
                'ERROR: Could not find subnet group %s' % attributes['db_subnet_group'])


    def modify_new_rds_instance(self,attributes):
        """
        Modify new instance with desired parameters
        """
        try:
            logging.info('Modifying db instance %s' % attributes['name'])

            if self.args.read_replica:
                backup_retention = 1
            else:
                backup_retention = 0

            response = self.client.modify_db_instance(
                DBInstanceIdentifier=attributes['name'],
                VpcSecurityGroupIds=attributes['security_group_ids'],
                BackupRetentionPeriod=backup_retention
            )

            waiter = self.client.get_waiter('db_instance_available')
            waiter.wait(
                DBInstanceIdentifier=attributes['name'],
                WaiterConfig={
                    'Delay': 15,
                    'MaxAttempts': 60
                }
            )

            return response

        except:
            raise Exception(
                'ERROR: Could there was a problem modifying the instance %s' % attributes['name'])


    def destroy_old_instances(self,old_rds_instances):
        """
        Delete the old instance once we know the new one is healthy
        """

        for instance in old_rds_instances:
            logging.info("Destroying old instance %s" % instance)

            try:
                response = self.client.delete_db_instance(
                    DBInstanceIdentifier=instance,
                    SkipFinalSnapshot=True
                )

                waiter = self.client.get_waiter('db_instance_deleted')
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

    def get_rds_instances(self,pattern=''):
        instances_lst = []
        try:
            rds_instances = self.client.describe_db_instances()['DBInstances']
            for instance in rds_instances:
                instance_attr = {
                    "instance_address": instance['Endpoint']['Address'],
                    "instance_name": instance['DBInstanceIdentifier']
                }       
                if (re.search(pattern, instance_attr['instance_name'])):
                    instances_lst.append(instance_attr)

            return instances_lst
             
        except Exception as e:
            logging.critical("Error retrieving list of instances - %s" % (str(e)))
            raise

    def create_read_replica(self,attributes):

        read_replica_id = f'{attributes["name"]}-{self.args.replica_suffix}'
        try:
            logging.info("Initiating read replica creation ...")

            replica = self.client.create_db_instance_read_replica(
                DBInstanceIdentifier=read_replica_id,
                SourceDBInstanceIdentifier=attributes["name"],
                Tags=attributes['tags'],
            )

            logging.info("Read replica creation initiated, waiting for database to become available...")

            waiter = self.client.get_waiter('db_instance_available')
            waiter.wait(
                DBInstanceIdentifier=read_replica_id,
                WaiterConfig={
                    'Delay': 15,
                    'MaxAttempts': 60
                }
            )

            return replica
        except Exception as e:
            logging.critical("Error while creating read replica - %s" % (str(e)))

