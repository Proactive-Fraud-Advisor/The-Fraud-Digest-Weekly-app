import json
import os
import requests
import boto3
from datetime import datetime, timedelta

# Name of the secret in AWS Secrets Manager
SECRET_NAME = "rod/FraudNewsAgent/ApiKeys" 
REGION_NAME = "eu-north-1" # Or your preferred region

def get_secrets():
    """Retrieves secrets from AWS Secrets Manager."""
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=REGION_NAME)
    
    try:
        get_secret_value_response = client.get_secret_value(SecretId=SECRET_NAME)
    except Exception as e:
        print(f"Unable to retrieve secrets: {e}")
        raise e

    # Decrypts the secret using the associated KMS key
    secret = get_secret_value_response['SecretString']
    return json.loads(secret)

def get_fraud_news(api_key):
    """Fetches fraud-related news from the last week."""
    one_week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    # A more robust query
    query = '("payment fraud" OR "financial crime" OR "identity theft" OR "kyc" OR "aml" OR "messaging spam" OR "daiting scam" OR "policy abuse") AND (update OR news OR trend)'
    
    url = (f'https://newsapi.org/v2/everything?'
           f'q={query}&'
           f'from={one_week_ago}&'
           f'sortBy=popularity&'
           f'language=en&'
           f'pageSize=5&' # Get 5 top articles
           f'apiKey={api_key}')
    
    response = requests.get(url)
    response.raise_for_status() # Raises an exception for bad status codes
    return response.json().get('articles', [])

def format_digest_for_email(articles):
    """Formats a professional HTML email digest."""
    if not articles:
        return "No significant fraud news found this week."

    html_body = """
    <html>
    <head></head>
    <body style="font-family: Arial, sans-serif;">
        <h2>Weekly Fraud & Security News Digest</h2>
        <p>Here are the top stories from the past week:</p>
    """
    for article in articles:
        title = article['title']
        url = article['url']
        source = article['source']['name']
        html_body += f'<p><strong><a href="{url}">{title}</a></strong><br><small>Source: {source}</small></p>'

    html_body += '<p><em>Automated digest by your friendly Givi-bot.</em></p></body></html>'
    return html_body

def format_digest_for_linkedin(articles):
    """Formats a concise, engaging LinkedIn post."""
    if not articles:
        return None
        
    # We'll post the top 2 articles to keep it short and sweet for social media
    top_two = articles[:2]
    post_text = "This week's top fraud & security updates:\n\n"
    for article in top_two:
        post_text += f"➡️ {article['title']}\n{article['url']}\n\n"

    post_text += "#FraudPrevention #CyberSecurity #Fintech #RiskManagement #SecurityNews"
    return post_text

def send_email(html_body, secrets):
    """Sends the digest to multiple recipients using AWS SES."""
    ses_client = boto3.client('ses', region_name=REGION_NAME)
    
    # This is the fix: Take the comma-separated string of emails from your secret...
    # ...and split it into a proper Python list, which is what SES needs.
    recipient_list = secrets['RECIPIENT_EMAIL'].split(',')
    
    try:
        ses_client.send_email(
            Source=secrets['SENDER_EMAIL'],
            Destination={'ToAddresses': recipient_list}, # Use the new list here
            Message={
                'Subject': {'Data': f"Your Weekly Fraud News Digest - {datetime.now().strftime('%Y-%m-%d')}"},
                'Body': {'Html': {'Data': html_body}}
            }
        )
        print(f"Email sent successfully to: {', '.join(recipient_list)}")
    except Exception as e:
        print(f"Error sending email: {e}")

def post_to_linkedin(post_text, secrets):
    """Posts the digest to LinkedIn."""
    if not post_text:
        print("No content to post to LinkedIn.")
        return

    headers = {
        'Authorization': f"Bearer {secrets['LINKEDIN_ACCESS_TOKEN']}",
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0'
    }
    payload = {
        "author": secrets['LINKEDIN_AUTHOR_URN'],
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": post_text
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }
    
    response = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=payload)
    if 200 <= response.status_code < 300:
        print("Posted to LinkedIn successfully!")
    else:
        print(f"Error posting to LinkedIn: {response.status_code} - {response.text}")


def lambda_handler(event, context):
    """Main function for AWS Lambda."""
    print("Agent starting...")
    try:
        secrets = get_secrets()
        
        # Make sure you add these two keys to your secret in Secrets Manager!
        if 'SENDER_EMAIL' not in secrets or 'RECIPIENT_EMAIL' not in secrets:
             raise ValueError("SENDER_EMAIL and RECIPIENT_EMAIL must be in secrets")

        articles = get_fraud_news(secrets['NEWS_API_KEY'])
        
        # 1. Email Flow
        email_html = format_digest_for_email(articles)
        send_email(email_html, secrets)

        # 2. LinkedIn Flow
        linkedin_text = format_digest_for_linkedin(articles)
        post_to_linkedin(linkedin_text, secrets)

        print("Agent finished.")
        return {'statusCode': 200, 'body': json.dumps('Process completed!')}
    except Exception as e:
        print(f"An error occurred: {e}")
        # This ensures any error is logged clearly in CloudWatch
        raise e

