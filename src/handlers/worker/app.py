import os
import json
import math
from datetime import datetime
from decimal import Decimal
import uuid

import boto3
from boto3.dynamodb.conditions import Key

sns = boto3.client("sns")
dynamodb = boto3.resource('dynamodb')

table = dynamodb.Table(os.environ["REC_TABLE_NAME"])
team_table = dynamodb.Table(os.environ["TEAM_TABLE_NAME"])


# ---------------------------------------------------------
# SNS
# ---------------------------------------------------------
def publish_recommendation_generated_event(
    recommendation_id,
    request_id,
    request_type,
    incident_id,
    recommendation_status,
    confidence_score,
    ranked_teams,
    trace_id,
    request_location,
    people_count,
    special_needs,
    evaluate_id,
    priority_level,
    evaluate_reason,
    evaluated_at,
    created_at
):
    now = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

    message = {
        "header": {
            "message_type": "RecommendationGenerated",
            "message_id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "sent_at": now,
            "version": "v1"
        },
        "body": {
            "recommendation_id": recommendation_id,
            "request_id": request_id,
            "incident_id": incident_id,

            # ---- core result ----
            "recommendation_status": recommendation_status,
            "confidence_score": confidence_score,
            "ranked_teams": ranked_teams,
            "model_version": "v2.0.0",

            # ---- context (ช่วย dispatch ตัดสินใจ) ----
            "request_type": request_type,
            "priority_level": priority_level,
            "evaluate_reason": evaluate_reason,

            # ---- situation ----
            "location": request_location,
            "people_count": people_count,
            "special_needs": special_needs,

            # ---- trace back ----
            "evaluate_id": evaluate_id,

            # ---- timestamps ----
            "evaluated_at": evaluated_at,
            "created_at": created_at
        }
    }

    sns.publish(
        TopicArn=os.environ["SNS_TOPIC_ARN"],
        Message=json.dumps(message, default=str),

        # ใช้แค่ filtering
        MessageAttributes={
            "message_type": {
                "DataType": "String",
                "StringValue": "RecommendationGenerated"
            }
        }
    )


# ---------------------------------------------------------
# DATA ACCESS
# ---------------------------------------------------------
def get_available_teams_from_dynamodb():
    response = team_table.query(
        IndexName="team_status-index",
        KeyConditionExpression=Key("team_status").eq("AVAILABLE")
    )

    items = response.get("Items", [])

    teams = []
    for item in items:
        teams.append({
            "team_id": item["team_id"],
            "team_name": item["team_name"],
            "team_type": item.get("team_type"),
            "team_status": item["team_status"],
            "capabilities": item.get("capabilities", []),
            "specialties": item.get("specialties", []),
            "equipment": item.get("equipment", []),
            "capacity": int(item.get("capacity", 0)),
            "current_location": {
                "lat": float(item["current_location"]["lat"]),
                "lng": float(item["current_location"]["lng"])
            }
        })

    return teams


# ---------------------------------------------------------
# UTILS 
# ---------------------------------------------------------

# คำนวณระยะทางบนผิวโลกระหว่าง 2 จุดจาก latitude/longitude โดยใช้สูตรที่เรียกว่า Haversine Formula
def calculate_distance(lat1, lon1, lat2, lon2):    
    R = 6371.0    #กำหนดรัศมีโลก 6371 km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = math.sin(d_lat / 2)**2 + \
        math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * \
        math.sin(d_lon / 2)**2

    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))   # ได้ระยะทาง หน่วยเป็น km


def parse_special_needs(s):
    if not s:
        return set()

    if "chip:" in s:
        s = s.split("chip:")[1]

    return set([x.strip() for x in s.split("|")])


# ---------------------------------------------------------
# SCORING
# ---------------------------------------------------------
def score_team(team, event_data):
    breakdown = {}
    explanations = []

    request_type = event_data["request_type"]
    incident_type = (event_data.get("incident_type") or "").lower()
    people_count = event_data.get("people_count", 0)
    special_needs = parse_special_needs(event_data.get("special_needs"))
    team_type = team.get("team_type", "")
    
    # 1. Capability (30+10)
    if request_type in team["capabilities"]:
        breakdown["capability"] = 30
        explanations.append(f"Capability: {team['capabilities']} matched for this request")
    else:
        # breakdown["capability"] = 0
        return None
    
    # Incident type == team_type (10)
    INCIDENT_TEAM_HINT = {
        "fire": [
            "FIRE_TRUCK",
            "MEDICAL_TEAM",
            "SEARCH_AND_RESCUE"
        ],
        "flood": [
            "RESCUE_BOAT",
            "AIR_RESCUE",
            "MEDICAL_TEAM",
            "SEARCH_AND_RESCUE"
        ],
        "storm": [
            "SEARCH_AND_RESCUE",
            "AIR_RESCUE",
            "MEDICAL_TEAM"
        ],
        "earthquake": [
            "SEARCH_AND_RESCUE",
            "MEDICAL_TEAM",
            "AIR_RESCUE"
        ],
        "explosion": [
            "FIRE_TRUCK",
            "SEARCH_AND_RESCUE",
            "MEDICAL_TEAM"
        ],
        "generic": [
            "MEDICAL_TEAM",
            "SEARCH_AND_RESCUE"
        ]
    }

    if team_type in INCIDENT_TEAM_HINT.get(incident_type, []):
        breakdown["capability"] += 10
        explanations.append(f"Team type: {team['team_type']} matched for incident type: {incident_type}")
    else:
        breakdown["capability"] += 0

    # 2. Distance (30)
    d = calculate_distance(
        event_data["location"]["latitude"],
        event_data["location"]["longitude"],
        team["current_location"]["lat"],
        team["current_location"]["lng"]
    )
    
    MAX_DISTANCE = 300

    if d > MAX_DISTANCE:
        return None  # skip team นี้เลย

    # exponential decay
    # dist_score = 30 / (1 + math.exp((d - 25) / 10))
    # if d <= 1:
    #     dist_score = 30
    # elif d <= 10:
    #     dist_score = 30 - (d - 1) * 2
    # elif d <= 50:
    #     dist_score = 12 - (d - 10) * 0.2
    # else:
    #     dist_score = 30 / (1 + math.exp((d - 25) / 10))
    if team_type == "AIR_RESCUE":
        dist_score = 30 / (1 + math.exp((d - 50) / 15))
    elif team_type == "FIRE_TRUCK":
        dist_score = 30 / (1 + math.exp((d - 30) / 10))
    else:
        dist_score = 30 / (1 + math.exp((d - 25) / 8))

    # clamp + round
    dist_score = round(min(30, dist_score), 2)

    breakdown["distance"] = dist_score
    explanations.append(f"อยู่ห่างจากจุดเกิดเหตุประมาณ {round(d, 2)} km")

    # 3. Capacity (20)
    if people_count > 0:
        if team["capacity"] >= people_count:
            capacity_score = 20
            explanations.append(f"จำนวนของทีมกู้ภัยเพียงพอต่อการช่วยเหลือ")
        else:
            capacity_score = (team["capacity"] / people_count) * 20
    else:
        capacity_score = 20

    breakdown["capacity"] = round(capacity_score, 2)

    # 4. Special Needs (10)
    need_map = {
        "ผู้สูงอายุ": "ELDERLY_CARE",
        "เด็กเล็ก": "PEDIATRIC_CARE",
        "ผู้ใช้รถเข็น": "WHEELCHAIR_SUPPORT",
        "ผู้ป่วยติดเตียง": "STRETCHER_SUPPORT",
        "ผู้บาดเจ็บ": "ADVANCED_LIFE_SUPPORT",
        "หญิงตั้งครรภ์": "PREGNANCY_SUPPORT",
        "ต้องใช้ยาเร่งด่วน": "ADVANCED_LIFE_SUPPORT",
        "สัตว์เลี้ยง": "ANIMAL_HANDLING"
    }

    if special_needs:
        matched = 0

        for need in special_needs:
            mapped = need_map.get(need)
            if mapped in team.get("specialties", []) or mapped in team.get("capabilities", []):
                matched += 1
                explanations.append(f"มีความสามารถพิเศษในการดูแล '{need}'")

        special_score = (matched / len(special_needs)) * 10
    else:
        special_score = 10

    breakdown["special_needs"] = round(special_score, 2)


    # TOTAL (100)
    total = (
        breakdown["capability"] +
        breakdown["distance"] +
        breakdown["capacity"] +
        breakdown["special_needs"]
    )
    total = min(100, total)

    return {
        "rank": None,
        "team_id": team["team_id"],
        "team_name": team["team_name"],
        "total_score": round(total, 2),
        "score_breakdown": breakdown,
        "explanation": " | ".join(explanations)
    }


def generate_ranked_teams(event_data, teams):
    results = []

    for team in teams:
        if team["team_status"] != "AVAILABLE":
            continue

        try:
            scored = score_team(team, event_data)

            if scored is None:
                continue

            results.append(scored)

        except Exception as e:
            print(f"Skip team {team['team_id']} error: {str(e)}")

    # กันพังกรณีไม่มีทีมเลย
    if not results:
        return [{
            "rank": 1,
            "team_id": None,
            "team_name": "NO_AVAILABLE_TEAM",
            "total_score": 0,
            "score_breakdown": {},
            "explanation": "No available team matched criteria"
        }]

    results.sort(key=lambda x: x["total_score"], reverse=True)

    # for i, t in enumerate(results[:5]):
    #     t["rank"] = i + 1

    # return results[:5]

    final_results = []

    for i, t in enumerate(results[:5]):
        final_results.append({
            "rank": i + 1,
            "team_id": t["team_id"],
            "team_name": t["team_name"],
            "total_score": t["total_score"],
            "score_breakdown": t["score_breakdown"],
            "explanation": t["explanation"]
        })

    return final_results


# ---------------------------------------------------------
# HANDLER
# ---------------------------------------------------------
def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event))

    trace_id = event.get("trace_id", "unknown")
    recommendation_id = event.get("recommendation_id")
    request_id = event.get("request_id")
    request_type = event.get("request_type")
    incident_id = event.get("incident_id")
    created_at = event.get("created_at")
    #add-on
    evaluate_id = event.get("evaluate_id")
    priority_level = event.get("priority_level")
    evaluate_reason = event.get("evaluate_reason")
    request_location = event.get("location")
    people_count = event.get("people_count")
    special_needs = event.get("special_needs")

    try:
        print(f"[{trace_id}] WORKER START v1 - Processing recommendation_id: {recommendation_id} for request_id: {request_id}")
        # validation
        if not event.get("location"):
            raise ValueError("Missing location")

        # set CALCULATING
        table.update_item(
            Key={'recommendation_id': recommendation_id},
            UpdateExpression="SET recommendation_status = :s",
            ExpressionAttributeValues={':s': 'CALCULATING'}
        )
        print(f"[{trace_id}] DB UPDATE - Set status of recommendation to CALCULATING")

        event_data = {
            "request_type": event.get("request_type"),
            "incident_type": event.get("incident_type"),
            "location": event.get("location"),
            "people_count": event.get("people_count"),
            "special_needs": event.get("special_needs")
        }

        teams = get_available_teams_from_dynamodb()
        ranked = generate_ranked_teams(event_data, teams)

        ranked_db = json.loads(json.dumps(ranked), parse_float=Decimal)

        evaluated_at = datetime.utcnow().isoformat(timespec='milliseconds') + "Z"

        table.update_item(
            Key={'recommendation_id': recommendation_id},
            UpdateExpression="""
                SET recommendation_status = :s,
                    ranked_teams = :rt,
                    confidence_score = :cs,
                    model_version = :mv,
                    evaluated_at = :ea
            """,
            ExpressionAttributeValues={
                ':s': 'GENERATED',
                ':rt': ranked_db,
                ':cs': 4,
                ':mv': 'v2.0.0',
                ':ea': evaluated_at
            }
        )
        print(f"[{trace_id}] DB UPDATE - Set status to GENERATED")

        print(f"[{trace_id}] WORKER SUCCESS - Finished processing recommendation_id: {recommendation_id}")

        publish_recommendation_generated_event(
            recommendation_id,
            request_id,
            request_type,
            incident_id,
            "GENERATED",
            4,
            ranked,
            trace_id,
            request_location,
            people_count,
            special_needs,
            evaluate_id,
            priority_level,
            evaluate_reason,
            evaluated_at,
            created_at,
            #add-on
            
        )
        print(f"[{trace_id}] PUBLISH SNS - RecommendationGenerated")

        return {"status": "success"}

    except Exception as e:
        print(f"[{trace_id}] ERROR: {str(e)}")

        table.update_item(
            Key={'recommendation_id': recommendation_id},
            UpdateExpression="SET recommendation_status = :s",
            ExpressionAttributeValues={':s': 'FAILED'}
        )

        raise e