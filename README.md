<div align="center">
  <img src="https://github.com/user-attachments/assets/d38aff13-0271-41cb-86d6-65bc762c2b97" alt="RSSbrew Icon" width="180"/>
  <h1>RSSBrew</h1>
</div>

[中文](README-zh.md) | English

A self-hosted, easy-to-deploy RSS tool that allows you to aggregate multiple RSS feeds, apply custom filters, generate AI summaries and daily/weekly digests.

Telegram Discussion Group: [RSSBrew](https://t.me/rssbrew)

⚠️This project is still under development. The current version may contain bugs or incomplete features. Please report any issues you encounter. Suggestions and contributions are welcome. Documentation in progress. For now, please refer to [an intro in my blog](https://yinan.me/rssbrew-config).

### Example Feeds

https://public.rssbrew.com/feeds/HN%20comments/

## Demo

https://demo.rssbrew.com

username: `admin`

password: `changeme` (data will be reset weekly, please do not save important data and change password after use)

## Features

### 1. Custom Filters
Apply custom filters to your feeds to control what content gets through or not. You can filter based on Link, Title and Description.
Besides:
- Various match types including contains, does not contain, matches regex or not.
- Multiple filters can be grouped together with relationship operators: AND, OR, NOT, relationships between groups can also be set.
- You can set the filter scope to apply to filter out matched entries entirely or filter for summary generation only.
  
### 2. Aggregate Multiple Feeds
Easily combine multiple RSS feeds into a single processed feed, even more powerful when used with custom filters.

### 3. Article Summarization
Using AI (currently supports all OpenAI compatible models via user configuration) to generate and prepend a summary to the article. The default summaries include a one-line summary and a slightly longer summary. You can also customize your prompt to use AI for other purposes.
  
### 4. Digests with AI

If you are overwhelmed by the number of articles, you can set up digests aggregating articles into one entry on a daily or weekly basis.
You can optionally choose what to include in the digest (e.g. content, summary, ) and use AI to help you summarize the digest.

## INSTALL

Docker deployment, please refer to [INSTALL.md](INSTALL.md).

## LICENSE

This project is licensed under the AGPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## SUPPORT

If you find this project helpful, please consider leaving a star or supporting the development by donating to the author.

- [Buy Me A Coffee](https://www.buymeacoffee.com/yinan)

- [afdian](https://afdian.com/a/yinanc)

We would greatly appreciate your support to keep this project going.
