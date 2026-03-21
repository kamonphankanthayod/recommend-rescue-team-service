# GET method for get recommendation

import os
import json
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from utils.error_response import format_error_response

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ["TABLE_NAME"])    #TABLE_NAME = "recommendations"


def decimal_to_number(obj):
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    raise TypeError

def format_get_recommendation(item):
    # ป้องกัน Key Error กรณีที่ของเพิ่ง PENDING และยังไม่มี ranked_teams
    ranked_teams = []
    for t in item.get("ranked_teams", []):
        ranked_teams.append({
            "team_id": t["team_id"],
            "rank": int(t["rank"]),
            "total_score": float(t["total_score"]),
            "score_breakdown": {
                "specialization_score": float(t["score_breakdown"]["specialization_score"]),
                "distance_score": float(t["score_breakdown"]["distance_score"]),
                "availability_score": float(t["score_breakdown"]["availability_score"]),
                "severity_weight": float(t["score_breakdown"]["severity_weight"]),
            },
            "explanation": t["explanation"]
        })
    # ดัก Cast confidence_score เป็น int ถ้าไม่มีเศษ
    conf_score = item.get("confidence_score", Decimal("0"))
    formatted_conf_score = int(conf_score) if conf_score % 1 == 0 else float(conf_score)

    return {
        "recommendation_id": item["recommendation_id"],
        "request_id": item["request_id"],
        "recommendation_status": item["recommendation_status"],
        "confidence_score": formatted_conf_score,
        "ranked_teams": ranked_teams,
        "model_version": item.get("model_version", ""),
        "evaluated_at": item.get("evaluated_at", ""),
        "created_at": item.get("created_at", "")
    }

def get_recommendation_by_request_id(event):
    trace_id = event["requestContext"]["requestId"]
    request_id = event.get("pathParameters", {}).get("request_id")

    print(f"[{trace_id}] START --- GET /v1/recommendations/{request_id}")

    try:
        ## Validation Error: 400 Bad Request
        if not request_id:
            print(f"[{trace_id}] 400 VALIDATION_ERROR - request_id is required")

            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "request_id is required",
                trace_id,
                [{"field": "request_id", "issue": "missing"}]
            )
        
        response = table.query(
            IndexName="request_id-index",
            KeyConditionExpression=Key("request_id").eq(request_id)
        )

        items = response.get("Items", [])

        ## Error: 404 Not Found
        if not items:
            print(f"[{trace_id}] 404 REFERENCE_NOT_FOUND - No recommendation found for request_id: {request_id}")
            return format_error_response(
                404,
                "REFERENCE_NOT_FOUND",
                "recommendation not found for request_id",
                trace_id
            )

        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        latest_item = items[0]

        print(f"[{trace_id}] Found {len(items)} versions. Picking the latest one: {latest_item.get('recommendation_id')}")

        item = format_get_recommendation(latest_item)
        print(f"[{trace_id}] Data: {json.dumps(item, default=decimal_to_number)}")
        
        ## Success: 200 Success
        print(f"[{trace_id}] 200 Success - Get recommendation success for request_id: {request_id}")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(item, default=decimal_to_number)
        }

    ## Error: 500 INTERNAL_SERVER_ERROR
    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - Error: {str(e)}")
        return format_error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            "Fail to get recommendation detail",
            trace_id
        )