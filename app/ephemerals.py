import re
import sys
import logging
from rds import RDS
from route53 import ROUTE53
from k8s import K8S

class EPHEMERALS():
    def __init__(self, args):
        self.args = args

    def ephemeral_zombie_clean(self,args):
        k8s = K8S()
        rds = RDS(self.args)
        route53 = ROUTE53(self.args)            

        namespaces = k8s.get_k8s_namespaces(pattern=self.args.target_instance)
        rds_instances = rds.get_rds_instances(pattern=self.args.target_instance)

        #Check if any RDS instance does not have matching K8s NS
        rds_zombies = []
        for rds_instance in rds_instances:
            found = False
            for ns in namespaces:                
                if (re.search(ns, rds_instance['instance_name'])):
                    found = True
            if (not found): rds_zombies.append(rds_instance)

        if not rds_zombies:
            logging.info("No ephemeral zombies found")
            sys.exit(0)
            
        logging.info(f"Found ephemeral zombies:{rds_zombies}")

        attributes = {} 
        attributes['dns_suffix'] = self.args.dns_suffix
        attributes['zone_id'] = self.args.zone_id

        #Deleting Zombies and associated CNAME records
        zombie_names = []
        for zombie in rds_zombies:
            ephemeral_name = zombie['instance_name'][:10]
            attributes['cname_name'] = f"{ephemeral_name}-rds"
            print(zombie['instance_address'])
            #route53.update_dns(attributes, zombie['instance_address'],action='DELETE')
            zombie_names.append(zombie['instance_name'])

        #rds.destroy_old_instances(zombie_names)


