import json

def lambda_handler(event, context):
    # TODO implement
    # print("RAW EVENT:", json.dumps(event))

    for record in event['Records']:
        
        # SQS body (string)
        sqs_body = json.loads(record["body"])
        # print("SQS BODY:", json.dumps(sqs_body))   ## can comment

        # SNS Message (string)
        if 'Message' in sqs_body:
            message = sqs_body["Message"]
            if isinstance(message, str):
                sns_message = json.loads(sqs_body["Message"])
                print("SNS MESSAGE:", json.dumps(sns_message))    ## can comment
            else:
                sns_message = message
        else:
            sns_message = sqs_body

        # payload จริง (ของ ResueRequestPrioritization Service)
        # payload = sns_message["body"]

        # print("PARSED PAYLOAD:", json.dumps(payload))    ## can comment

    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
