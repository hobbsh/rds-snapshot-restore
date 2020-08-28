import logging
import sys
from kubernetes import client, config
import re

class K8S():

    def __init__(self):

        config.load_kube_config()

        try:
            self.client = client.CoreV1Api()
        except:
            print(sys.exc_info())
            sys.exit(1)

    def get_k8s_namespaces(self,pattern=''):

        ns_list = []
        namespaces = self.client.list_namespace()

        for ns in namespaces.items:
            ns_name = ns.metadata.name
            if (re.search(pattern, ns_name)):
                ns_list.append(ns_name)
        
        return ns_list
