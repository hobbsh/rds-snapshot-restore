# rds-snapshot-restore

This script looks for the most recent snapshot for a given `DBInstanceIdentifier` and restores it to a new instance in the same or different VPC.

Alternatively, you can specify a snapshot directly instead of a RDS instance, you can do this by passing `--from-snapshot` and `--target "my-snapshot-name"`

It is designed to only have one restored instance at once (it will spin up the new one then delete the old). Once the old istance is deleted, it changes the DNS record to point to the new instance. It should only take a 15 or so minutes to run (tested on a 600GB m4.2xlarge).

## Use Cases

* Restore RDS snapshot for Ephemerals

#### Usage

The following example would restore a RDS instance from the latest snapshot with a name matching `pseudonymised-instance*`.
The new RDS instance will be named `eph-666-pseudonymised-instance-[unix-timestamp]`, it will be configured with the SG `ephemerals-rds-dev` , the subnet group `ephemerals-generic-01-dev`, and with db param group `ephemerals`
A CNAME will be created, `eph-666-rds.dev.eu-west-1.stuart` -> `eph-666-pseudonymised-instance-[unix-timestamp].abcdefghij.eu-west-1.rds.amazonaws.com`

```
python3 snapshot_restore.py --region "eu-west-1" --prefix "eph-666" --target "pseudonymised-instance" --cname-name "eph-666-rds" --zone-id "Z3U91PH8BA5CP3" \
--dns-suffix "dev.eu-west-1.stuart" --data-folder "/data" --extra-tags "Environment:dev;Service:ephemeral;ephemeral-id:eph-666" --instance-class "db.t2.large" \
--snapshot-type "manual" --sec-group-names "ephemerals-rds-dev" --subnet-group-name "ephemerals-generic-01-dev" --vpc-tag-name "Development" --db-param-group "ephemerals" --from-snapshot
```

The DB instance name, the DNS CNAME record name and value, as well as an AWS Route53 delete batch are stored locally inside the folder specified by `--data-folder`. 
They can be used to delete the RDS instance and CNAME.

#### Requirements

This script assumes:
- You have a running RDS instance with at least one snapshot
- You use Route53 hosted zones
- Your RDS instances are in VPCs

#### Arguments

```
usage: snapshot_restore.py [-h] [-t TARGET_INSTANCE] [-r AWS_REGION] [-i INSTANCE_CLASS] [-p PREFIX] [-u SUBNET_GROUP_NAME] [-S SECURITY_GROUP_NAMES [SECURITY_GROUP_NAMES ...]]
                           [-V VPC_TAG_NAME] [-D DNS_SUFFIX] [-c CNAME_NAME] [-m ZONE_MATCH_STRING] [-z ZONE_ID] [-s SNAPSHOT_TYPE] [-f DATA_FOLDER] [-e EXTRA_TAGS] [-x]
                           [-y DB_PARAM_GROUP] [-Z] [-n] [-R] [-X REPLICA_SUFFIX] [-C REPLICA_CNAME_NAME] [-I REPLICA_INSTANCE_CLASS] [-N NEW_INSTANCE_NAME] [-P SRC_RDS_SNAPSHOT]

Restore the most recent snapshot of a given RDS instance or a to a new instance

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_INSTANCE, --target TARGET_INSTANCE
                        Name of the RDS instance to restore the snapshot from - this is the DBInstanceIdentifier of the target instance
  -r AWS_REGION, --region AWS_REGION
                        AWS Region to use. Currently can only target and restore to the same region. Defaults to "us-west-2"
  -i INSTANCE_CLASS, --instance-class INSTANCE_CLASS
                        Instance class to use for the new instance. Defaults to db.t2.medium
  -p PREFIX, --prefix PREFIX
                        Prefix for the new instance DBInstanceIdentifier
  -u SUBNET_GROUP_NAME, --subnet-group-name SUBNET_GROUP_NAME
                        Name of the database subnet group to use for the new instance. Defaults to the subnet group of the target instance if not specified
  -S SECURITY_GROUP_NAMES [SECURITY_GROUP_NAMES ...], --sec-group-names SECURITY_GROUP_NAMES [SECURITY_GROUP_NAMES ...]
                        Names of the VPC security group to use for the new instance. Defaults to the security group of the target instance if not specified. Specify multiple
                        separated by a space. Must also specify --vpc-tag-name.
  -V VPC_TAG_NAME, --vpc-tag-name VPC_TAG_NAME
                        VPC "Name" tag value. Required when using --sec-group-names
  -D DNS_SUFFIX, --dns-suffix DNS_SUFFIX
                        DNS Suffix for your private Route53 zone
  -c CNAME_NAME, --cname-name CNAME_NAME
                        Name of the CNAME to create for the new instance
  -m ZONE_MATCH_STRING, --match-zone ZONE_MATCH_STRING
                        String to match a Route53 Hosted Zone name on to determine the zone ID. Useful if you rebuild private DNS zones often. Overrides --zone-id if specified.
  -z ZONE_ID, --zone-id ZONE_ID
                        Route53 Zone ID to use for the new instance CNAME. Defaults to the zone id of the target instance. Is overridden by --match-zone.
  -s SNAPSHOT_TYPE, --snapshot-type SNAPSHOT_TYPE
                        Snapshot type to search filter on. Defaults to "automated"
  -f DATA_FOLDER, --data-folder DATA_FOLDER
                        Path to the folder where RDS instance name and DNS data will be stored
  -e EXTRA_TAGS, --extra-tags EXTRA_TAGS
                        Additional Tags for the new RDS instance. Format like -e "tag1_key:tag1_value;tag2_key:tag2_value"
  -x, --from-snapshot   Set this flag to restore directly from a snapshot
  -y DB_PARAM_GROUP, --db-param-group DB_PARAM_GROUP
                        Name of the parameter group applied to the new RDS instance
  -Z, --ephemeral-zombie-clean
                        Remove RDS Instances and Route53 CNAME for resources when there is no K8s namespace associated
  -n, --noop            Enable NOOP mode - will not perform any restore tasks
  -R, --read-replica    Create DB read replica
  -X REPLICA_SUFFIX, --replica-suffix REPLICA_SUFFIX
                        Suffix for the DB replica DBInstanceIdentifier
  -C REPLICA_CNAME_NAME, --replica-cname-name REPLICA_CNAME_NAME
                        Name of the CNAME to create for the new instance replica
  -I REPLICA_INSTANCE_CLASS, --replica-instance-class REPLICA_INSTANCE_CLASS
                        Instance class to use for the new instance replica. Defaults to db.t2.medium
  -N NEW_INSTANCE_NAME, --new-instance-name NEW_INSTANCE_NAME
                        New name of the RDS instance
  -P SRC_RDS_SNAPSHOT, --source-rds-snapshot SRC_RDS_SNAPSHOT
                        RDS Instance to retrieve snapshot from
```
