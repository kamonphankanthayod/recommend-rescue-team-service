# Rescue Team Service

A serverless, event-driven microservice designed to manage rescue team profiles, monitor their availability, and provide automated team recommendations during disaster response scenarios. This project is built using Python and deployed via AWS Serverless Application Model (AWS SAM).

## Architecture Overview

This service implements an Event-Driven Architecture to ensure high availability, scalability, and loose coupling with other microservices. 

**Core Technologies:**
* **Compute:** AWS Lambda
* **API Routing:** Amazon API Gateway (HTTP API)
* **Database:** Amazon DynamoDB (Pay-per-request)
* **Messaging (Asynchronous):** Amazon SQS, Amazon SNS
* **Infrastructure as Code (IaC):** AWS SAM / CloudFormation
* **Language:** Python 3.9

## Project Structure

The repository is organized following standard serverless application practices:
```text
.
├── LICENSE
├── README.md
├── infra
│   ├── samconfig.toml           # SAM CLI configuration
│   └── template.yaml            # AWS SAM Infrastructure as Code definition
└── src
    ├── handlers
    │   ├── api/                 # Core REST API handlers (CRUD operations)
    │   ├── consumer/            # SQS Consumers for cross-service events
    │   ├── dispatchconsumer/    # SQS Consumer for dispatch completion events
    │   ├── testconsumer/        # Internal testing consumer
    │   └── worker/              # Heavy computation and scoring logic
    └── shared
        └── utils/               # Shared libraries (Auth, Error handling, Validation)
```

## Event-Driven Workflow

The service communicates asynchronously with external domains (e.g., Rescue Request Prioritization Service, ManageDispatch Service) through AWS messaging services:

1. Inbound Requests: Receives prioritized rescue requests via SQS (rescue_request_queue). The RecommendationConsumer processes the payload and invokes the ScoringWorker.

2. Asynchronous Processing: The ScoringWorker calculates the optimal rescue team based on requirements, updates the DynamoDB tables, and publishes the result to an SNS topic (recommendation-generated-topic).

3. Status Synchronization: Listens to dispatch_complete_queue via the DispatchStatusUpdater to automatically update team availability statuses when field operations conclude.

## Resiliency & Error Handling
To ensure fault tolerance in the asynchronous workflows, Dead Letter Queues (DLQ) are configured for all SQS queues.

- Messages that fail processing after 3 retries are automatically routed to their respective DLQ.
- Message retention is configured to allow sufficient time for debugging and manual redrive operations.
- CloudWatch Log Groups are configured with a 7-day retention policy for optimal cost management.

## API Endpoints

The service exposes the following internal endpoints via API Gateway for administrative and direct querying purposes.

**Teams:**
- POST /v1/teams - Register a new rescue team
- GET /v1/teams - List available teams
- GET /v1/teams/{team_id} - Retrieve specific team details
- PATCH /v1/teams/{team_id}/status - Update team operational status
- DELETE /v1/teams/{team_id} - Remove a rescue team

**Recommendations:**
- GET /v1/recommendations/{request_id} - Retrieve a specific recommendation result
- PATCH /v1/recommendations/{recommendation_id} - Update recommendation state
- DELETE /v1/recommendations/{recommendation_id} - Remove a recommendation record

> (*Note:* API requests require a valid Bearer Token in the Authorization header. Refer to shared/utils/auth.py for current authorization logic).


## Deployment Guide

### Prerequisites
- AWS CLI installed and configured with appropriate credentials.
- AWS SAM CLI installed.
- Python 3.9 installed locally.

### Steps to Deploy
1. **Clone the repository**
```bash
git clone <repository-url>
cd recommend-rescue-team-service
```

2. **Navigate to the infrastructure directory**
```bash
cd infra
```

3. **Build the SAM application**
This command prepares the deployment artifacts and resolves dependencies.
```bash
sam build
```

4. **Deploy to AWS**
For the first-time deployment, run the guided process to configure your stack parameters.
```bash
sam deploy --guided
```
For subsequent deployments after modifying code or infrastructure, simply run:
```bash
sam deploy
```

## Development Notes
- **Infrastructure Modifications:** Any additions to DynamoDB indexes, SQS queues, or Lambda permissions must be defined in infra/template.yaml.
- **Cross-Account Subscriptions:** SNS topic ARNs for cross-account event subscriptions are managed via conditional IAM policies in the SAM template. Ensure strict ARN validation is enabled for production environments.

## Source
- Demo video [https://drive.google.com/file/d/19s4bnKZ6OT7c0reGmhn96Hwh3sZsjjXo/view?usp=sharing](https://drive.google.com/file/d/19s4bnKZ6OT7c0reGmhn96Hwh3sZsjjXo/view?usp=sharing)
- Documentation [https://docs.google.com/document/d/1Tpxp_LGm1Szsp7ZmmHOlfccPyRza_9YtYsUICyDmuks/edit?usp=sharing](https://docs.google.com/document/d/1Tpxp_LGm1Szsp7ZmmHOlfccPyRza_9YtYsUICyDmuks/edit?usp=sharing)
