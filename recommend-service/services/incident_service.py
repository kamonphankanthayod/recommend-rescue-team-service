# services/incident_service.py

import json
import os

USE_MOCK = os.environ.get("USE_MOCK", "true") == "true"

def get_incident(incident_id, trace_id):
    if USE_MOCK:
        return _get_mock(incident_id)
    else:
        return _call_real_service(incident_id, trace_id)

def _get_mock(incident_id):
    with open("mocks/incident_mock.json") as f:
        data = json.load(f)

    return data.get(incident_id)

# import requests

def _call_real_service(incident_id, trace_id):
    # url = f"https://rescue-service/v1/rescue-requests/{request_id}"    # แก้ endpoint ตรงนี้ด้วยจ่ะ

    # headers = {
    #     "X-Trace-Id": trace_id
    # }

    # response = requests.get(url, headers=headers, timeout=3)

    # if response.status_code == 200:
    #     return response.json()

    # elif response.status_code == 404:
    #     return None

    # else:
    #     raise Exception("External service error")
    return None