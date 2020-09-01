import boto3
import logging
import sys
import json
from helpers import HELPERS

class ROUTE53():

    def __init__(self, args):
        self.args = args 
        self.helpers = HELPERS(self.args)
        self.client = boto3.client('route53', region_name=self.args.aws_region)
    
    def get_route53_zone_id(self,zone_match_string):

        logging.info("Looking for private route53 zone with %s in the name" % zone_match_string)
        try:
            response = self.client.list_hosted_zones()

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


    def update_dns(self,attributes, target,action='UPSERT'):
        """
        Create CNAME for new instance - this makes the new instance "live"
        Source is the record name, target is the target address, i.e. a DB endpoint address
        """

        dns_name = "%s.%s" % (attributes['cname_name'], attributes['dns_suffix'])

        logging.info("%s DNS in zone %s for record %s with value %s" % (action, attributes['zone_id'], dns_name, target))

        self.helpers.write_attribute_to_file(f'{self.args.data_folder}/dns_record_name',dns_name)
        self.helpers.write_attribute_to_file(f'{self.args.data_folder}/dns_record_value',target)

        try:
            response = self.client.change_resource_record_sets(
                HostedZoneId=attributes['zone_id'],
                ChangeBatch={
                    'Changes': [{
                        'Action': action,
                        'ResourceRecordSet': {
                            'Name': dns_name,
                            'Type': 'CNAME',
                            'TTL': 300,
                            'ResourceRecords': [{'Value': target}]
                        }
                    }]
                })

            waiter = self.client.get_waiter('resource_record_sets_changed')
            waiter.wait(Id=response['ChangeInfo']['Id'])

            self.write_delete_patch(dns_name,target)

        except Exception as e:
            logging.critical("Error updating DNS for endpoint %s - %s" % (target, str(e)))
            raise

    def get_records_set(self,zone_id):
        try:
            response = self.client.list_resource_record_sets(HostedZoneId=zone_id)
        except Exception as e:
            logging.critical("Error listing DNS records in zone %s - %s" % (zone_id, str(e)))
            raise
        return response['ResourceRecordSets']

    def write_delete_patch(self,dns_name,value):
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

        self.helpers.write_attribute_to_file(f'{self.args.data_folder}/dns_delete_patch',json.dumps(delete_patch))
