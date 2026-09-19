"""Idempotent Resource Initializer for LocalStack DynamoDB and S3.

Phase 4: Creates the DynamoDB table and S3 bucket if they do not already exist.
Runs exclusively against the configured local LocalStack endpoint.
"""

import logging
from typing import Optional
import boto3
from botocore.exceptions import ClientError

from app.config.settings import settings

logger = logging.getLogger("jarvis.persistence.init")


def init_localstack_resources(
    endpoint_url: str = settings.LOCALSTACK_ENDPOINT_URL,
    table_name: str = settings.DYNAMODB_TABLE_NAME,
    audit_table_name: str = settings.DYNAMODB_AUDIT_TABLE_NAME,
    bucket_name: str = settings.S3_BUCKET_NAME,
    region_name: str = settings.AWS_REGION,
    notification_table_name: Optional[str] = None,
) -> bool:
    """Initialize DynamoDB tables and S3 bucket on LocalStack idempotently.

    Returns True if successfully initialized or already existing, False if unreachable.
    """
    try:
        # 1. DynamoDB Cases Table Initialization
        dynamodb = boto3.client(
            "dynamodb",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        existing_tables = dynamodb.list_tables().get("TableNames", [])
        if table_name not in existing_tables:
            logger.info("LocalStack: Creating DynamoDB table '%s'...", table_name)
            dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {"AttributeName": "case_id", "KeyType": "HASH"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "case_id", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            logger.info("LocalStack: DynamoDB table '%s' created.", table_name)
        else:
            logger.info("LocalStack: DynamoDB table '%s' already exists.", table_name)

        # 1b. DynamoDB Audit Table Initialization
        if audit_table_name not in existing_tables:
            logger.info("LocalStack: Creating DynamoDB audit table '%s'...", audit_table_name)
            dynamodb.create_table(
                TableName=audit_table_name,
                KeySchema=[
                    {"AttributeName": "event_id", "KeyType": "HASH"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "event_id", "AttributeType": "S"},
                    {"AttributeName": "case_id", "AttributeType": "S"},
                ],
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "CaseIndex",
                        "KeySchema": [
                            {"AttributeName": "case_id", "KeyType": "HASH"},
                        ],
                        "Projection": {
                            "ProjectionType": "ALL",
                        },
                    }
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            logger.info("LocalStack: DynamoDB audit table '%s' created.", audit_table_name)
        else:
            logger.info("LocalStack: DynamoDB audit table '%s' already exists.", audit_table_name)

        # 1c. DynamoDB Notifications Table Initialization (Phase 8.4)
        if notification_table_name and notification_table_name not in existing_tables:
            logger.info("LocalStack: Creating DynamoDB notification table '%s'...", notification_table_name)
            dynamodb.create_table(
                TableName=notification_table_name,
                KeySchema=[
                    {"AttributeName": "notification_id", "KeyType": "HASH"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "notification_id", "AttributeType": "S"},
                    {"AttributeName": "case_id", "AttributeType": "S"},
                ],
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "CaseNotificationIndex",
                        "KeySchema": [
                            {"AttributeName": "case_id", "KeyType": "HASH"},
                        ],
                        "Projection": {
                            "ProjectionType": "ALL",
                        },
                    }
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            logger.info("LocalStack: DynamoDB notification table '%s' created.", notification_table_name)
        else:
            logger.info("LocalStack: DynamoDB notification table '%s' already exists.", notification_table_name)

        # 2. S3 Bucket Initialization
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        existing_buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
        if bucket_name not in existing_buckets:
            logger.info("LocalStack: Creating S3 bucket '%s'...", bucket_name)
            if region_name == "us-east-1":
                s3.create_bucket(Bucket=bucket_name)
            else:
                s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": region_name},
                )
            logger.info("LocalStack: S3 bucket '%s' created.", bucket_name)
        else:
            logger.info("LocalStack: S3 bucket '%s' already exists.", bucket_name)

        return True

    except ClientError as exc:
        logger.error("ClientError connecting to LocalStack: %s", exc)
        return False
    except Exception as exc:
        logger.warning("LocalStack not reachable at '%s': %s", endpoint_url, exc)
        return False
