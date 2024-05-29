import re
from bs4 import BeautifulSoup
import logging
from urllib.parse import urlparse, urlunparse
import os
from openai import OpenAI
import tiktoken

logger = logging.getLogger('feed_logger')
OPENAI_PROXY = os.environ.get('OPENAI_PROXY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'

def clean_url(url):
    parsed_url = urlparse(url)
    # 重建 URL，不包括片段和查询字符串
    clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path.rstrip('/'), '', '', ''))
    # 转换为小写
    clean_url = clean_url.lower()
    return clean_url

def clean_html(html_content):
    """
    This function is used to clean the HTML content.
    It will remove all the <script>, <style>, <img>, <a>, <video>, <audio>, <iframe>, <input> tags.
    Returns:
        Cleaned text for summarization
    """
    soup = BeautifulSoup(html_content, "html.parser")

    for script in soup.find_all("script"):
        script.decompose()

    for style in soup.find_all("style"):
        style.decompose()

    for img in soup.find_all("img"):
        img.decompose()

    for a in soup.find_all("a"):
        a.decompose()

    for video in soup.find_all("video"):
        video.decompose()

    for audio in soup.find_all("audio"):
        audio.decompose()
    
    for iframe in soup.find_all("iframe"):
        iframe.decompose()
    
    for input in soup.find_all("input"):
        input.decompose()

    return soup.get_text()

def clean_txt_and_truncate(article, model, clean_bool=True):
    if clean_bool:
        cleaned_article = clean_html(article.content)
    cleaned_article = article.content
    encoding = tiktoken.encoding_for_model(model)
    token_length = len(encoding.encode(cleaned_article))

    max_length_of_models = {
        'gpt-3.5-turbo': 16200,
        'gpt-4': 127800,
        'gpt-4-32k': 127800,
    }

    # Truncate the text if it exceeds the model's token limit
    if token_length > max_length_of_models[model]:
        truncated_article = encoding.decode(encoding.encode(cleaned_article)[:max_length_of_models[model]])
        return truncated_article
    else:
        return cleaned_article

def generate_untitled(entry):
    try: return entry.title
    except: 
        try: return entry.article[:50]
        except: return entry.link

def passes_filters(entry, feed, filter_type):
    # if there are no filters, return True
    if not feed.filters.filter(usage=filter_type).exists():
        return True
    if filter_type == 'feed_filter':
        filter_relational_operator = feed.filter_relational_operator
    elif filter_type == 'summary_filter':
        filter_relational_operator = feed.filter_relational_operator_summary
    results = []
    for filter in feed.filters.filter(usage=filter_type):
        if filter.field == 'title':
            content = generate_untitled(entry)
        elif filter.field == 'content':
            try:
                content = entry.content[0].value
            except:
                try: content = entry.description
                except: content = entry.content

        elif filter.field == 'link':
            content = entry.url
        if match_content(content, filter):
#            logger.info(f"  Filter {filter_type}, Entry {entry.title} passed filter {filter}")
            results.append(True)
        else:
            results.append(False)

    if filter_relational_operator == 'all':
        if all(results):
            return True
        else:
            logger.info(f"  Filter {filter_type}, Entry {entry.title} did not pass all filters")
            return False
    elif filter_relational_operator == 'any':
        if any(results):
            return True
        else:
            logger.info(f"  Filter {filter_type}, Entry {entry.title} did not pass any filters")
            return False
    elif filter_relational_operator == 'none':
        if not any(results):
            return True
        else:
            logger.info(f"  Filter {filter_type}, Entry {entry.title} passed at least one filter")
            return False

def match_content(content, filter):
    if filter.match_type == 'contains':
        return filter.value in content
    elif filter.match_type == 'does_not_contain':
        return filter.value not in content
    elif filter.match_type == 'matches_regex':
        return re.search(filter.value, content) is not None
    elif filter.match_type == 'does_not_match_regex':
        return re.search(filter.value, content) is None
    elif filter.match_type == 'shorter_than':
        return len(content) < int(filter.value)
    elif filter.match_type == 'longer_than':
        return len(content) > int(filter.value)


def generate_summary(article, model, language, additional_prompt=None):
    if not model or not OPENAI_API_KEY:
        logger.info('  OpenAI API key or model not set, skipping summary generation')
        return 
    try:
        client_params = {
            "api_key": OPENAI_API_KEY,
            "base_url": OPENAI_BASE_URL
        }
        completion_params = {
            "model": model,
        }
        if OPENAI_PROXY:
            client_params["http_client"] = httpx.Client(proxy=OPENAI_PROXY)

        client = OpenAI(**client_params)
        if not additional_prompt:
            truncated_query = clean_txt_and_truncate(article, model, clean_bool=True)
            additional_prompt = f"Please summarize this article, and output the result only in JSON format. First item of the json is a one-line summary in 15 words named as 'summary_one_line', second item is the 150-word summary named as 'summary_long'. Output result in {language} language."
            messages = [
                {"role": "system", "content": "You are a helpful assistant for summarizing articles, designed to output JSON format."},
                {"role": "user", "content": f"{truncated_query}"},
                {"role": "assistant", "content": f"{additional_prompt}"},
            ]
            completion_params["response_format"] = { "type": "json_object" }
            completion_params["messages"] = messages
            custom_prompt = False
        else:
            truncated_query = clean_txt_and_truncate(article, model, clean_bool=False)
            messages = [
                {"role": "system", "content": "You are a helpful assistant for processing article content, designed to only output result in pure HTML, do not block the HTML code using ```, and do not output any other format."},
                {"role": "user", "content": f"{truncated_query}"},
                {"role": "assistant", "content": f"{additional_prompt}"},
            ]
            completion_params["messages"] = messages
            custom_prompt = True
        completion = client.chat.completions.create(**completion_params)
        return completion.choices[0].message.content, custom_prompt
    except Exception as e:
        logger.error(f'Failed to generate summary for article {article.title}: {str(e)}')