import json

from handlers.generate_recommendation import generate_recommendation
from handlers.get_recommendation import get_recommendation_by_request_id
from handlers.delete_recommendation import delete_recommendation
from handlers.update_recommendation import update_recommendation_status


def lambda_handler(event, context):
    print(json.dumps(event))
    path = event["rawPath"]     # "/v1/recommendations"
    method = event["requestContext"]["http"]["method"]     # "POST" || "GET" || "DELETE" || "PATCH"
    print(f"Received {method} request for path: {path}")

    if path == "/v1/recommendations" and method == "POST":
        return generate_recommendation(event)

    if path.startswith("/v1/recommendations/") and path.endswith("/status") and method == "PATCH":
        return update_recommendation_status(event)

    if path.startswith("/v1/recommendations/") and method == "GET":
        return get_recommendation_by_request_id(event)

    if path.startswith("/v1/recommendations/") and method == "DELETE":
        return delete_recommendation(event)

    return {
        "statusCode": 404,
        "body": "Not Found"
    }