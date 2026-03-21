# DELETE method for delete recommendation

import os
import json

import boto3
from botocore.exceptions import ClientError

from utils.error_response import format_error_response
from utils.validator import is_valid_uuid

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ["TABLE_NAME"])    #TABLE_NAME = "recommendations"


def delete_recommendation(event):
    trace_id = event["requestContext"]["requestId"]
    recommendation_id = event.get("pathParameters", {}).get("recommendation_id")

    print(f"[{trace_id}] START --- DELETE /v1/recommendations/{recommendation_id}")

    try:
        ## Validation Error: 400 Bad Request
        if not recommendation_id:
            print(f"[{trace_id}] 400 VALIDATION_ERROR - recommendation_id is required")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "recommendation_id is required",
                trace_id,
                [{"field": "recommendation_id", "issue": "missing"}]
            )

        ## Validation Error: 400 Bad Request
        if not is_valid_uuid(recommendation_id):
            print(f"[{trace_id}] 400 VALIDATION_ERROR - invalid UUID format")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "recommendation_id must be a valid UUID",
                trace_id,
                [{"field": "recommendation_id", "issue": "invalid_format"}]
            )

        response = table.delete_item(
            Key={"recommendation_id": recommendation_id},
            ReturnValues="ALL_OLD"
        )

        deleted_item = response.get("Attributes")

        if deleted_item:
            print(f"[{trace_id}] Item existed and deleted")
        else:
            print(f"[{trace_id}] Item did not exist (idempotent delete)")

        print(f"[{trace_id}] 204 No Content - Recommendation deleted")

        return {
            "statusCode": 204,
            "body": ""
        }

    except ClientError as e:
        print(f"[{trace_id}] 500 DYNAMODB_ERROR - {str(e)}")

        return format_error_response(
            500,
            "DATABASE_ERROR",
            "Failed to delete recommendation",
            trace_id
        )

    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - {str(e)}")

        return format_error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            "Unexpected error occurred",
            trace_id
        )