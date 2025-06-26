import json
import os
import requests
import boto3
from datetime import datetime, timedelta
from openai import OpenAI # Using the OpenAI library

# Secret name in AWS Secrets Manager
SECRET_NAME = os.environ.get('SECRET_NAME', "prod/FraudNewsAgent/ApiKeys")
REGION_NAME = os.environ.get('AWS_REGION', "eu-north-1")

def get_secrets():
    """Retrieves secrets from AWS Secrets Manager."""
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=REGION_NAME)
    try:
        get_secret_value_response = client.get_secret_value(SecretId=SECRET_NAME)
    except Exception as e:
        print(f"Unable to retrieve secrets: {e}")
        raise e
    secret = get_secret_value_response['SecretString']
    return json.loads(secret)

def get_fraud_news(api_key):
    """Fetches fraud-related news from the last week."""
    one_week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    query = '("payment fraud" OR "financial crime" OR "identity theft" OR "kyc" OR "aml") AND (update OR news OR trend OR breach)'
    url = (f'https://newsapi.org/v2/everything?'
           f'q={query}&'
           f'from={one_week_ago}&'
           f'sortBy=popularity&'
           f'language=en&'
           f'pageSize=5&'
           f'apiKey={api_key}')
    response = requests.get(url)
    response.raise_for_status()
    return response.json().get('articles', [])

def summarize_text_with_openai(text_to_summarize, openai_client):
    """Summarizes text using the OpenAI API."""
    if not text_to_summarize:
        return "(No description available to summarize)"

    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes news article descriptions into a single, concise, professional sentence for a security news digest."},
                {"role": "user", "content": f"Please summarize this into one sentence: '{text_to_summarize}'"}
            ],
            temperature=0.5,
            max_tokens=80,
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(f"Error during OpenAI API call: {e}")
        return "(AI summary failed to generate)"

def format_digest_for_email(articles):
    """Formats a professional HTML email digest with AI summaries."""
    if not articles:
        return "No significant fraud news found this week."
    html_body = """
    <html><head></head><body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2>Weekly Fraud & Security News Digest</h2>
        <p>Here are the top stories from the past week:</p>"""
    for article in articles:
        html_body += f'<hr><p><strong><a href="{article["url"]}" target="_blank">{article["title"]}</a></strong><br><small>Source: {article["source"]}</small><br><em>{article["ai_summary"]}</em></p>'
    html_body += '<br><p><em>Automated digest by EV&GiVi.</em></p></body></html>'
    return html_body

def format_digest_for_linkedin(articles):
    """Formats a concise, engaging LinkedIn post."""
    if not articles:
        return None
    top_two = articles[:2]
    post_text = "This week's top fraud & security updates:\n\n"
    for article in top_two:
        post_text += f"➡️ {article['title']}\n{article['url']}\n\n"
    post_text += "#FraudPrevention #CyberSecurity #Fintech #RiskManagement #SecurityNews"
    return post_text

def send_email(html_body, secrets):
    """Sends the digest to multiple recipients using AWS SES."""
    ses_client = boto3.client('ses', region_name=REGION_NAME)
    recipient_list = secrets['RECIPIENT_EMAIL'].split(',')
    try:
        ses_client.send_email(
            Source=secrets['SENDER_EMAIL'], Destination={'ToAddresses': recipient_list},
            Message={'Subject': {'Data': f"Your Weekly Fraud News Digest - {datetime.now().strftime('%Y-%m-%d')}"},
                     'Body': {'Html': {'Data': html_body}}})
        print(f"Email sent successfully to: {', '.join(recipient_list)}")
    except Exception as e:
        print(f"Error sending email: {e}")

def post_to_linkedin(post_text, secrets):
    """Posts the digest to LinkedIn."""
    if not post_text:
        print("No content to post to LinkedIn."); return
    headers = {'Authorization': f"Bearer {secrets['LINKEDIN_ACCESS_TOKEN']}", 'Content-Type': 'application/json', 'X-Restli-Protocol-Version': '2.0.0'}
    payload = {"author": secrets['LINKEDIN_AUTHOR_URN'], "lifecycleState": "PUBLISHED",
               "specificContent": {"com.linkedin.ugc.ShareContent": {"shareCommentary": {"text": post_text}, "shareMediaCategory": "NONE"}},
               "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}}
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
        
        openai_client = OpenAI(api_key=secrets['OPENAI_API_KEY'])
        
        if 'SENDER_EMAIL' not in secrets or 'RECIPIENT_EMAIL' not in secrets:
            raise ValueError("SENDER_EMAIL and RECIPIENT_EMAIL must be in secrets")

        raw_articles = get_fraud_news(secrets['NEWS_API_KEY'])
        
        processed_articles = []
        for article in raw_articles:
            text_to_summarize = article.get('description') or article.get('content', '')
            ai_summary = summarize_text_with_openai(text_to_summarize, openai_client)
            
            processed_articles.append({
                'title': article['title'], 'url': article['url'],
                'source': article['source']['name'], 'ai_summary': ai_summary
            })

        email_html = format_digest_for_email(processed_articles)
        send_email(email_html, secrets)

        linkedin_text = format_digest_for_linkedin(processed_articles)
        post_to_linkedin(linkedin_text, secrets)

        print("Agent finished.")
        return {'statusCode': 200, 'body': json.dumps('Process completed successfully!')}
    except Exception as e:
        print(f"An error occurred: {e}")
        raise e