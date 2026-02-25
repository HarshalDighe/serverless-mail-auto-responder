import uuid
import datetime
import os
import boto3
import base64
import json
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# AWS Clients
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
secrets = boto3.client('secretsmanager')

TABLE_NAME = os.environ['TABLE_NAME']
BUCKET_NAME = os.environ['BUCKET_NAME']
SECRET_NAME = os.environ['SECRET_NAME']

KEYWORDS = ["invoice", "payment", "bill"]


def get_secret():
    response = secrets.get_secret_value(SecretId=SECRET_NAME)
    return json.loads(response['SecretString'])


def extract_email(sender_raw):
    if not sender_raw:
        return "unknown"
    match = re.search(r'<(.+?)>', sender_raw)
    return match.group(1) if match else sender_raw


def lambda_handler(event, context):

    print("Lambda started")

    try:
        secret = get_secret()

        creds = Credentials(
            None,
            refresh_token=secret['refresh_token'],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=secret['gmail_client_id'],
            client_secret=secret['gmail_client_secret']
        )

        service = build('gmail', 'v1', credentials=creds)

        # Pagination support
        messages = []
        next_page_token = None

        while True:
            response = service.users().messages().list(
                userId='me',
                q='is:unread',
                pageToken=next_page_token
            ).execute()

            messages.extend(response.get('messages', []))
            next_page_token = response.get('nextPageToken')

            if not next_page_token:
                break

        if not messages:
            print("No unread emails found.")
            return

        table = dynamodb.Table(TABLE_NAME)

        for msg in messages:

            transaction_id = str(uuid.uuid4())
            timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            print(json.dumps({
                "transaction_id": transaction_id,
                "status": "Processing email"
            }))

            msg_id = msg['id']
            result = "NO"
            remark = "Keyword not found"

            try:
                message = service.users().messages().get(
                    userId='me',
                    id=msg_id
                ).execute()

                headers = message['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "")
                sender_raw = next((h['value'] for h in headers if h['name'] == 'From'), "")

                sender = extract_email(sender_raw)

                # Keyword check
                if subject and any(k in subject.lower() for k in KEYWORDS):

                    template = s3.get_object(
                        Bucket=BUCKET_NAME,
                        Key="invoice_template.html"
                    )['Body'].read().decode()

                    raw_message = base64.urlsafe_b64encode(
                        f"To: {sender}\n"
                        f"Subject: Re: {subject}\n"
                        f"Content-Type: text/html\n\n"
                        f"{template}".encode()
                    ).decode()

                    service.users().messages().send(
                        userId="me",
                        body={'raw': raw_message}
                    ).execute()

                    result = "YES"
                    remark = "Auto responder sent"

                # Mark email as read
                service.users().messages().modify(
                    userId='me',
                    id=msg_id,
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()

            except Exception as process_error:
                result = "NO"
                remark = str(process_error)
                print(json.dumps({
                    "transaction_id": transaction_id,
                    "error": remark
                }))

            # Store in DynamoDB
            try:
                if result == "YES":
                    table.put_item(
                        Item={
                        'transaction_id': transaction_id,
                        'sender_email': sender,
                        'timestamp': timestamp,
                        'result': result,
                        'remark': remark
                    }
                )
            except Exception as ddb_error:
                print(json.dumps({
                    "transaction_id": transaction_id,
                    "ddb_error": str(ddb_error)
                }))

        print("Lambda completed successfully")

    except Exception as e:
        print("Fatal Error:", str(e))
        raise e
