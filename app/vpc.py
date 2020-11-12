import logging
import time
import boto3
import sys

class VPC():

    def __init__(self,args):
        self.args = args
        self.client = boto3.client('ec2', region_name=self.args.aws_region)

    def get_vpc_id_by_name_tag(self,vpc_name_tag_value):
        ec2 = boto3.resource('ec2', region_name=self.args.aws_region)
        filter_string = "%s*" % vpc_name_tag_value
        filters = [{'Name': 'tag:Name', 'Values': [filter_string]}]
        vpcs = list(ec2.vpcs.filter(Filters=filters))  # Only use the first match

        for vpc in vpcs:
            vpc_metadata = self.client.describe_vpcs(
                VpcIds=[
                    vpc.id,
                ]
            )

        vpc_id = vpc_metadata['Vpcs'][0]['VpcId']

        return vpc_id

    def get_security_groups(self,vpc_id, group_names):
        """ Gets VPC security groups in a given VPC that match a list of names
            Returns a list of VPC security group IDs
        """

        if isinstance(group_names,str):
             group_names = group_names.split(' ')

        security_groups = []
        for group_name in group_names:
            security_group = self.client.describe_security_groups(
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
                            f'{group_name}*',
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
