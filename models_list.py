import google.generativeai as genai
import os

# You would run this on a machine where you can provide your API key
# For example, you could temporarily add it as an environment variable
# Or just paste it in for a quick check.
# Make sure to replace "YOUR_GOOGLE_API_KEY"
genai.configure(api_key="YOUR_GOOGLE_API_KEY") 

print("--- Available Gemini Models ---")

# The API returns a list of all models. We'll filter for the ones
# that can be used for text generation, which is what we're doing.
for model in genai.list_models():
  if 'generateContent' in model.supported_generation_methods:
    print(model.name)
