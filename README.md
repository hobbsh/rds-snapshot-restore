# rds-snapshot-restore

This script looks for the most recent snapshot for a given `DBInstanceIdentifier` and restores it to a new instance in the same or different VPC.

#### Usage

The following targets an RDS instance named `mydata` and will restore it to an instance called `staging-mydata-[some unix timestamp]`, create a CNAME called `mydata.staging.example.com` in a Route53 zone with `staging` in the name (specified by `-m`). Since `-V` and `-S` are specified, the new instance will be in a different VPC. The VPC used matches the `Name: staging` key/value tag and the `database` security group is used.  Since `--noop` is used, no action is done.
```
./snapshot_restore.py -p staging -t mydata -u staging-db-subnet-group -S database -c mydata -m staging -D staging.example.com --noop -V staging
```

Another scenario would be to restore the snapshot to an instance in the same VPC but with a prefix `staging` on its name - `staging-mydata.example.com`:
```
./snapshot_restore.py -p staging -t mydata -c mydata -z Z9999999999
```

#### Requirements

This script assumes:
- You have a running RDS instance with at least one snapshot
- You use Route53 hosted zones
- Your RDS instances are in VPCs

#### Arguments

```
usage: snapshot_restore.py [-h] -t TARGET_INSTANCE [-r AWS_REGION]
                           [-i INSTANCE_CLASS] [-p PREFIX]
                           [-u SUBNET_GROUP_NAME]
                           [-S SECURITY_GROUP_NAMES [SECURITY_GROUP_NAMES ...]]
                           [-V VPC_TAG_NAME] -D DNS_SUFFIX -c CNAME_NAME
                           [-m ZONE_MATCH_STRING] [-z ZONE_ID]
                           [-s SNAPSHOT_TYPE] [-n]

Restore the most recent snapshot of a given RDS instance to a new instance

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_INSTANCE, --target TARGET_INSTANCE
                        Name of the RDS instance to restore the snapshot from
                        - this is the DBInstanceIdentifier of the target
                        instance
  -r AWS_REGION, --region AWS_REGION
                        AWS Region to use. Currently can only target and
                        restore to the same region. Defaults to us-west-2.
  -i INSTANCE_CLASS, --instance-class INSTANCE_CLASS
                        Instance class to use for the new instance. Defaults
                        to db.t2.medium
  -p PREFIX, --prefix PREFIX
                        Prefix for the new instance DBInstanceIdentifier
  -u SUBNET_GROUP_NAME, --subnet-name SUBNET_GROUP_NAME
                        Name of the database subnet group to use for the new
                        instance. Defaults to the subnet group of the target
                        instance if not specified
  -S SECURITY_GROUP_NAMES [SECURITY_GROUP_NAMES ...], --sec-group-names SECURITY_GROUP_NAMES [SECURITY_GROUP_NAMES ...]
                        Names of the VPC security group to use for the new
                        instance. Defaults to the security group of the target
                        instance if not specified. Specify multiple separated
                        by a space. Must also specify --vpc-tag-name
  -V VPC_TAG_NAME, --vpc-tag-name VPC_TAG_NAME
                        VPC "Name" tag value. Required when using --sec-group-names
  -D DNS_SUFFIX, --dns-suffix DNS_SUFFIX
                        DNS Suffix for your private Route53 zone
  -c CNAME_NAME, --cname-name CNAME_NAME
                        Name of the CNAME to create for the new instance
  -m ZONE_MATCH_STRING, --match-zone ZONE_MATCH_STRING
                        String to match a Route53 Hosted Zone name on to
                        determine the zone ID. Useful if you rebuild private
                        DNS zones often. Overrides --zone-id if specified.
  -z ZONE_ID, --zone-id ZONE_ID
                        Route53 Zone ID to use for the new instance CNAME.
                        Defaults to the zone id of the target instance. Is
                        overridden by --match-zone.
  -s SNAPSHOT_TYPE, --snapshot-type SNAPSHOT_TYPE
                        Snapshot type to search filter on. Defaults to 'automated'.
  -n, --noop            Enable NOOP mode - will not perform any restore tasks.
```

