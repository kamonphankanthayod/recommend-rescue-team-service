import json
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TEAM_TABLE_NAME"])


def lambda_handler(event, context):
    # print("RAW EVENT:", json.dumps(event))

    for record in event.get("Records", []):
        try:
            # -------------------------
            # 1. Parse SQS → SNS
            # -------------------------
            body = json.loads(record["body"])

            if "Message" in body:
                message = json.loads(body["Message"])
            else:
                message = body

            trace_id = message.get("trace_id", "unknown")
            team_id = message.get("teamId")

            print(f"[{trace_id}] Processing dispatch for team: {team_id}")

            if not team_id:
                raise ValueError("Missing teamId")

            # -------------------------
            # 2. Update team_status = BUSY (SAFE)
            # -------------------------
            updated_at = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

            try:
                table.update_item(
                    Key={"team_id": team_id},
                    UpdateExpression="SET team_status = :s, updated_at = :u",
                    ConditionExpression="team_status = :available",
                    ExpressionAttributeValues={
                        ":s": "BUSY",
                        ":u": updated_at,
                        ":available": "AVAILABLE"
                    }
                )

                print(f"[{trace_id}] SUCCESS - Team {team_id} set to BUSY")

            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    print(f"[{trace_id}] SKIP - Team {team_id} not AVAILABLE")
                    # ไม่ throw → ไม่ retry
                    continue
                else:
                    raise

        except Exception as e:
            print(f"[ERROR] {str(e)}")
            raise e  # ให้ SQS retry

    return {"status": "ok"}